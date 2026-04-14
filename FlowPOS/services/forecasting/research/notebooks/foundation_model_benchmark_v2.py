"""
Extended benchmark: Chronos variants + statistical baselines.
Same Zeynos walk-forward setup.
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
    print(f"Data: {len(top_items)} items, {len(all_dates)} days")
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

# ---- Statistical baselines ----
def naive_walk_forward(grid, all_dates, top_items, method, buf=1.40):
    """Statistical baselines: same_weekday_avg, rolling_7d, seasonal_naive."""
    all_p, all_a, all_pr, all_ids = [], [], [], []
    for pred_start in range(30, len(all_dates), PREDICT_EVERY):
        pred_end = min(pred_start+PREDICT_EVERY, len(all_dates))
        train_end = all_dates[pred_start-1]
        train_start = train_end - pd.Timedelta(days=WINDOW_DAYS)
        pred_dates = all_dates[pred_start:pred_end]
        for iid in top_items:
            item = grid[grid["item_id"]==iid].set_index("date").sort_index()
            hist = item.loc[train_start:train_end]["quantity_sold"].values
            acts = item.loc[pred_dates[0]:pred_dates[-1]]["quantity_sold"].values
            price = item["item_price"].iloc[0]
            if len(hist)<14 or len(acts)==0: continue

            preds = []
            for i, d in enumerate(pred_dates):
                if i >= len(acts): break
                dow = d.dayofweek
                if method == "same_dow_avg":
                    # Average of same weekday in history
                    hist_dates = pd.date_range(train_start, train_end, freq="D")
                    same_dow = [hist[j] for j, hd in enumerate(hist_dates[:len(hist)]) if hd.dayofweek == dow]
                    pred = np.mean(same_dow) if same_dow else np.mean(hist[-7:])
                elif method == "rolling_7d":
                    pred = np.mean(hist[-7:])
                elif method == "seasonal_naive":
                    # Same day last week
                    pred = hist[-7+i] if len(hist) > 7-i else np.mean(hist[-7:])
                elif method == "ets_simple":
                    # Simple exponential smoothing
                    alpha = 0.3
                    level = hist[0]
                    for v in hist[1:]:
                        level = alpha * v + (1-alpha) * level
                    pred = level
                preds.append(pred * buf)

            for j in range(len(preds)):
                if j < len(acts):
                    all_p.append(preds[j])
                    all_a.append(acts[j])
                    all_pr.append(price)
                    all_ids.append(iid)

    mae, cost, waste, stockout = evaluate_all(all_a, all_p, all_pr, all_ids)
    return {"model": method, "mae": round(mae,4), "cost": round(cost,2),
            "waste": round(waste,2), "stockout": round(stockout,2),
            "n_predictions": len(all_a), "buffer": buf}

# ---- Chronos ----
def chronos_wf(grid, all_dates, top_items, model_name, buf=1.40):
    print(f"\nLoading {model_name}...")
    t0 = time.time()
    pipeline = BaseChronosPipeline.from_pretrained(model_name, device_map="cpu", torch_dtype=torch.float32)
    print(f"  Loaded in {time.time()-t0:.1f}s")
    all_p, all_a, all_pr, all_ids = [], [], [], []
    n = 0
    t0 = time.time()
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
            preds = np.median(fc[0].numpy(), axis=0) * buf
            preds = np.clip(preds, 0, None)
            for i in range(min(len(preds), len(acts))):
                all_p.append(preds[i]); all_a.append(acts[i])
                all_pr.append(price); all_ids.append(iid)
        n += 1
        if n % 10 == 0: print(f"  Round {n}, {len(all_p)} preds, {time.time()-t0:.0f}s")
    elapsed = time.time()-t0
    mae, cost, waste, stockout = evaluate_all(all_a, all_p, all_pr, all_ids)
    print(f"  Done: {n} rounds, {elapsed:.0f}s")
    del pipeline; gc.collect()
    return {"model": model_name.split("/")[-1], "mae": round(mae,4), "cost": round(cost,2),
            "waste": round(waste,2), "stockout": round(stockout,2),
            "n_predictions": len(all_a), "time_s": round(elapsed,1), "buffer": buf}

# ---- LightGBM ----
def lgb_wf(grid, all_dates, top_items, buf=1.40):
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
    all_p, all_a, all_pr, all_ids = [], [], [], []
    t0 = time.time()
    for ps in range(30, len(all_dates), PREDICT_EVERY):
        pe = min(ps+PREDICT_EVERY, len(all_dates))
        te = all_dates[ps-1]; ts = te - pd.Timedelta(days=WINDOW_DAYS)
        tr = df[(df["date"]>ts)&(df["date"]<=te)].dropna(subset=["l1","l7"],how="all")
        tst = df[df["date"].isin(all_dates[ps:pe])].dropna(subset=["l1","l7"],how="all")
        if len(tr)<50 or len(tst)==0: continue
        m = lgb.LGBMRegressor(n_estimators=200,learning_rate=0.05,num_leaves=31,
            min_child_samples=5,n_jobs=2,random_state=42,verbosity=-1)
        m.fit(tr[fc].fillna(0).astype(np.float32), tr["quantity_sold"].astype(np.float32))
        p = np.clip(m.predict(tst[fc].fillna(0).astype(np.float32))*buf, 0, None)
        all_p.extend(p); all_a.extend(tst["quantity_sold"].values)
        all_pr.extend(tst["item_price"].values); all_ids.extend(tst["item_id"].values)
        del m
    elapsed = time.time()-t0
    mae, cost, waste, stockout = evaluate_all(all_a, all_p, all_pr, all_ids)
    return {"model": "LightGBM-200", "mae": round(mae,4), "cost": round(cost,2),
            "waste": round(waste,2), "stockout": round(stockout,2),
            "n_predictions": len(all_a), "time_s": round(elapsed,1), "buffer": buf}

# ---- Main ----
print("Loading data...")
grid, all_dates, top_items = load_store_data()
results = []

# Statistical baselines
print("\n" + "="*60)
print("STATISTICAL BASELINES")
print("="*60)
for method in ["same_dow_avg", "rolling_7d", "seasonal_naive", "ets_simple"]:
    t0 = time.time()
    r = naive_walk_forward(grid, all_dates, top_items, method)
    r["time_s"] = round(time.time()-t0, 1)
    results.append(r)
    print(f"  {method:20s}  MAE: {r['mae']:.3f}  Cost: {r['cost']:>12,.0f} DKK  Time: {r['time_s']:.0f}s")

# LightGBM
print("\n" + "="*60)
print("LIGHTGBM")
print("="*60)
r = lgb_wf(grid, all_dates, top_items)
results.append(r)
print(f"  LightGBM-200         MAE: {r['mae']:.3f}  Cost: {r['cost']:>12,.0f} DKK  Time: {r['time_s']:.0f}s")

# Chronos variants
chronos_models = [
    "amazon/chronos-bolt-tiny",
    "amazon/chronos-bolt-mini",
    "amazon/chronos-bolt-small",
    "amazon/chronos-t5-tiny",      # original T5-based
    "amazon/chronos-t5-mini",
    "amazon/chronos-t5-small",
]

for mn in chronos_models:
    print(f"\n{'='*60}")
    print(f"{mn}")
    print(f"{'='*60}")
    try:
        r = chronos_wf(grid, all_dates, top_items, mn)
        results.append(r)
        print(f"  MAE: {r['mae']:.3f}  Cost: {r['cost']:>12,.0f} DKK  Time: {r['time_s']:.0f}s")
    except Exception as e:
        print(f"  FAILED: {e}")

# Final ranking
print(f"\n{'='*70}")
print("FINAL RANKING (buf=1.40, 60d window, Zeynos, 30 items)")
print(f"{'='*70}")
print(f"{'Model':<25} {'MAE':>8} {'Cost (DKK)':>12} {'Waste':>10} {'Stockout':>10} {'Time':>8}")
print("-"*75)
for r in sorted(results, key=lambda x: x["cost"]):
    t = f"{r.get('time_s',0):.0f}s"
    print(f"{r['model']:<25} {r['mae']:>8.3f} {r['cost']:>12,.0f} {r['waste']:>10,.0f} {r['stockout']:>10,.0f} {t:>8}")

with open("/home/yahyahammoudeh/Documents/loving loyalty internship/notebooks/results/foundation_model_results_v2.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print("\nSaved.")
