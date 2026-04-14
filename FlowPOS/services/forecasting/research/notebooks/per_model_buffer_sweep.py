"""
Per-model buffer sweep for all models that performed well.
Find each model's optimal buffer independently.
"""

import sys, time, json, sqlite3, gc, warnings
import numpy as np
import pandas as pd
import torch
from chronos import BaseChronosPipeline

warnings.filterwarnings("ignore")

DB_PATH = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/production.db"
STORE_ID = "5995723"
TOP_N_ITEMS = 30
WASTE_FRACTION = 0.3
STOCKOUT_MULT = 1.5
PREDICT_EVERY = 3
WINDOW_DAYS = 60

SHELF_PATH = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/production_shelf_life_final.csv"
shelf_df = pd.read_csv(SHELF_PATH)
SHELF_LOOKUP = {}
for _, row in shelf_df.iterrows():
    iid = str(row["item_id"])
    sl = float(row["shelf_life_days"]) if pd.notna(row["shelf_life_days"]) else 3.0
    ag = float(row["avg_gap_days"]) if pd.notna(row["avg_gap_days"]) else 1.0
    SHELF_LOOKUP[iid] = (sl, ag)

def eff_wf(item_id):
    sl, ag = SHELF_LOOKUP.get(str(item_id), (3.0, 1.0))
    if sl >= 9999: return 0.0
    return WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))

def load_store_data():
    conn = sqlite3.connect(DB_PATH)
    orders = pd.read_sql("SELECT id, place_id, created, status FROM fct_orders", conn)
    items = pd.read_sql("SELECT item_id, order_id, quantity, title FROM fct_order_items", conn)
    menu = pd.read_sql("SELECT id, price FROM dim_menu_items", conn)
    conn.close()
    orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
    items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
    menu["price"] = pd.to_numeric(menu["price"], errors="coerce")
    orders = orders[(orders["status"]=="Closed") & (orders["place_id"]==STORE_ID)]
    orders["date"] = pd.to_datetime(orders["created"], unit="s", errors="coerce").dt.normalize()
    merged = items.merge(orders[["id","date"]], left_on="order_id", right_on="id", how="inner")
    daily = merged.groupby(["date","item_id"])["quantity"].sum().reset_index(name="quantity_sold")
    top = daily.groupby("item_id")["quantity_sold"].sum().reset_index().sort_values("quantity_sold", ascending=False).head(TOP_N_ITEMS)
    top_items = top["item_id"].values
    daily = daily[daily["item_id"].isin(top_items)]
    ip = menu.rename(columns={"id":"item_id","price":"item_price"})
    modal = daily.merge(ip, on="item_id", how="left").groupby("item_id")["item_price"].agg(
        lambda x: x.mode().iloc[0] if len(x.mode())>0 else 75.0).reset_index()
    modal.columns = ["item_id","item_price"]
    all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    frames = []
    for iid in top_items:
        f = pd.DataFrame({"date": all_dates, "item_id": iid})
        s = daily[daily["item_id"]==iid][["date","quantity_sold"]]
        f = f.merge(s, on="date", how="left")
        f["quantity_sold"] = f["quantity_sold"].fillna(0)
        p = modal[modal["item_id"]==iid]["item_price"].values
        f["item_price"] = p[0] if len(p)>0 else 75.0
        frames.append(f)
    grid = pd.concat(frames, ignore_index=True).sort_values(["item_id","date"]).reset_index(drop=True)
    return grid, all_dates, top_items

def evaluate_all(actuals, preds, prices, item_ids):
    a, p = np.array(actuals,dtype=float), np.clip(np.array(preds,dtype=float),0,None)
    pr = np.array(prices,dtype=float)
    mae = np.abs(a-p).mean()
    wf = np.array([eff_wf(i) for i in item_ids])
    over, under = np.maximum(p-a,0), np.maximum(a-p,0)
    waste = (over*pr*wf).sum()
    stockout = (under*pr).sum()
    return mae, waste + STOCKOUT_MULT*stockout, waste, stockout


def collect_raw_predictions(grid, all_dates, top_items, model_type, model_name=None):
    """Collect raw (unbuffered) predictions for buffer sweep."""
    all_raw, all_a, all_pr, all_ids = [], [], [], []

    if model_type == "chronos":
        pipeline = BaseChronosPipeline.from_pretrained(model_name, device_map="cpu", torch_dtype=torch.float32)
        for ps in range(30, len(all_dates), PREDICT_EVERY):
            pe = min(ps+PREDICT_EVERY, len(all_dates))
            te = all_dates[ps-1]; ts = te - pd.Timedelta(days=WINDOW_DAYS)
            pd_dates = all_dates[ps:pe]; n_pred = len(pd_dates)
            for iid in top_items:
                item = grid[grid["item_id"]==iid].set_index("date").sort_index()
                hist = item.loc[ts:te]["quantity_sold"].values
                acts = item.loc[pd_dates[0]:pd_dates[-1]]["quantity_sold"].values
                price = item["item_price"].iloc[0]
                if len(hist)<14 or len(acts)==0: continue
                ctx = torch.tensor(hist, dtype=torch.float32).unsqueeze(0)
                fc = pipeline.predict(ctx, prediction_length=n_pred)
                preds = np.median(fc[0].numpy(), axis=0)
                for i in range(min(len(preds), len(acts))):
                    all_raw.append(float(preds[i]))
                    all_a.append(float(acts[i]))
                    all_pr.append(float(price))
                    all_ids.append(iid)
        del pipeline; gc.collect()

    elif model_type == "lgb":
        import lightgbm as lgb
        from sklearn.preprocessing import LabelEncoder
        df = grid.copy()
        df["dow"] = df["date"].dt.dayofweek
        df["is_wknd"] = df["dow"].isin([5,6]).astype(int)
        for lag in [1,3,7,14]:
            df[f"l{lag}"] = df.groupby("item_id")["quantity_sold"].shift(lag)
        sh = df.groupby("item_id")["quantity_sold"].shift(1)
        for w in [3,7,14]:
            df[f"r{w}"] = sh.groupby(df["item_id"]).transform(lambda x: x.rolling(w,min_periods=1).mean())
        df["rs7"] = sh.groupby(df["item_id"]).transform(lambda x: x.rolling(7,min_periods=2).std())
        le = LabelEncoder(); df["ie"] = le.fit_transform(df["item_id"].astype(str))
        fc = ["dow","is_wknd","l1","l3","l7","l14","r3","r7","r14","rs7","ie"]
        for ps in range(30, len(all_dates), PREDICT_EVERY):
            pe = min(ps+PREDICT_EVERY, len(all_dates))
            te = all_dates[ps-1]; ts = te - pd.Timedelta(days=WINDOW_DAYS)
            tr = df[(df["date"]>ts)&(df["date"]<=te)].dropna(subset=["l1","l7"],how="all")
            tst = df[df["date"].isin(all_dates[ps:pe])].dropna(subset=["l1","l7"],how="all")
            if len(tr)<50 or len(tst)==0: continue
            m = lgb.LGBMRegressor(n_estimators=200,learning_rate=0.05,num_leaves=31,
                min_child_samples=5,n_jobs=2,random_state=42,verbosity=-1)
            m.fit(tr[fc].fillna(0).astype(np.float32), tr["quantity_sold"].astype(np.float32))
            p = m.predict(tst[fc].fillna(0).astype(np.float32))
            all_raw.extend(p.tolist())
            all_a.extend(tst["quantity_sold"].values.tolist())
            all_pr.extend(tst["item_price"].values.tolist())
            all_ids.extend(tst["item_id"].values.tolist())
            del m

    elif model_type == "rolling_7d":
        for ps in range(30, len(all_dates), PREDICT_EVERY):
            pe = min(ps+PREDICT_EVERY, len(all_dates))
            te = all_dates[ps-1]; ts = te - pd.Timedelta(days=WINDOW_DAYS)
            pd_dates = all_dates[ps:pe]
            for iid in top_items:
                item = grid[grid["item_id"]==iid].set_index("date").sort_index()
                hist = item.loc[ts:te]["quantity_sold"].values
                acts = item.loc[pd_dates[0]:pd_dates[-1]]["quantity_sold"].values
                price = item["item_price"].iloc[0]
                if len(hist)<14 or len(acts)==0: continue
                pred = np.mean(hist[-7:])
                for i in range(len(acts)):
                    all_raw.append(float(pred))
                    all_a.append(float(acts[i]))
                    all_pr.append(float(price))
                    all_ids.append(iid)

    elif model_type == "same_dow_avg":
        for ps in range(30, len(all_dates), PREDICT_EVERY):
            pe = min(ps+PREDICT_EVERY, len(all_dates))
            te = all_dates[ps-1]; ts = te - pd.Timedelta(days=WINDOW_DAYS)
            pd_dates = all_dates[ps:pe]
            for iid in top_items:
                item = grid[grid["item_id"]==iid].set_index("date").sort_index()
                hist = item.loc[ts:te]["quantity_sold"]
                acts = item.loc[pd_dates[0]:pd_dates[-1]]["quantity_sold"].values
                price = item["item_price"].iloc[0]
                if len(hist)<14 or len(acts)==0: continue
                for i, d in enumerate(pd_dates):
                    if i >= len(acts): break
                    same = hist[hist.index.dayofweek == d.dayofweek].values
                    pred = np.mean(same) if len(same) > 0 else np.mean(hist.values[-7:])
                    all_raw.append(float(pred))
                    all_a.append(float(acts[i]))
                    all_pr.append(float(price))
                    all_ids.append(iid)

    return np.array(all_raw), np.array(all_a), np.array(all_pr), all_ids


def sweep_buffer(raw_preds, actuals, prices, item_ids, model_name):
    """Sweep buffer on pre-computed raw predictions."""
    buffers = [0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.45, 1.50]
    results = []
    for buf in buffers:
        preds = np.clip(raw_preds * buf, 0, None)
        mae, cost, waste, stockout = evaluate_all(actuals, preds, prices, item_ids)
        results.append({"model": model_name, "buffer": buf, "mae": round(mae,4),
                        "cost": round(cost,2), "waste": round(waste,2), "stockout": round(stockout,2)})
    return results


# ---- Main ----
print("Loading data...")
grid, all_dates, top_items = load_store_data()

models_to_test = [
    ("chronos-bolt-mini",  "chronos", "amazon/chronos-bolt-mini"),
    ("chronos-bolt-tiny",  "chronos", "amazon/chronos-bolt-tiny"),
    ("rolling_7d",         "rolling_7d", None),
    ("same_dow_avg",       "same_dow_avg", None),
    ("LightGBM-200",       "lgb", None),
]

all_results = []

for name, mtype, mpath in models_to_test:
    print(f"\n{'='*60}")
    print(f"Collecting raw predictions: {name}")
    print(f"{'='*60}")
    t0 = time.time()
    raw, acts, prices, ids = collect_raw_predictions(grid, all_dates, top_items, mtype, mpath)
    print(f"  {len(raw)} predictions in {time.time()-t0:.0f}s")

    print(f"  Buffer sweep...")
    sweep = sweep_buffer(raw, acts, prices, ids, name)
    all_results.extend(sweep)

    best = min(sweep, key=lambda x: x["cost"])
    print(f"  Best: buf={best['buffer']:.2f}  Cost={best['cost']:,.0f} DKK  MAE={best['mae']:.3f}")
    for r in sweep:
        print(f"    buf={r['buffer']:.2f}  Cost={r['cost']:>10,.0f}  waste={r['waste']:>8,.0f}  stockout={r['stockout']:>8,.0f}")

# Final comparison with per-model optimal buffer
print(f"\n{'='*70}")
print("FINAL: EACH MODEL WITH ITS OPTIMAL BUFFER")
print(f"{'='*70}")
print(f"{'Model':<22} {'Opt Buf':>8} {'Cost (DKK)':>12} {'Waste':>10} {'Stockout':>10} {'MAE':>8}")
print("-"*72)

for name, _, _ in models_to_test:
    model_sweep = [r for r in all_results if r["model"] == name]
    best = min(model_sweep, key=lambda x: x["cost"])
    print(f"{name:<22} {best['buffer']:>8.2f} {best['cost']:>12,.0f} {best['waste']:>10,.0f} {best['stockout']:>10,.0f} {best['mae']:>8.3f}")

with open("/home/yahyahammoudeh/Documents/loving loyalty internship/notebooks/results/buffer_sweep_per_model.json", "w") as f:
    json.dump(all_results, f, indent=2, default=str)
print("\nSaved.")
