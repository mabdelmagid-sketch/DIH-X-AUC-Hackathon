"""
Extended buffer sweep: test buffers 1.40 - 2.50 for the top 3 models.
Previous sweep maxed out at 1.50; this finds the actual optimum.
"""
import sys, os, time, json, sqlite3, gc, warnings
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
    items = pd.read_sql("SELECT item_id, order_id, quantity FROM fct_order_items", conn)
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

def evaluate(actuals, preds, prices, item_ids):
    a = np.array(actuals, dtype=float)
    p = np.clip(np.array(preds, dtype=float), 0, None)
    pr = np.array(prices, dtype=float)
    mae = np.abs(a-p).mean()
    wf = np.array([eff_wf(i) for i in item_ids])
    waste = (np.maximum(p-a, 0) * pr * wf).sum()
    stockout = (np.maximum(a-p, 0) * pr).sum()
    return mae, waste + STOCKOUT_MULT*stockout, waste, stockout

def collect_raw(grid, all_dates, top_items, mtype, mname=None):
    raw, acts, prices, ids = [], [], [], []
    if mtype == "chronos":
        pipeline = BaseChronosPipeline.from_pretrained(mname, device_map="cpu", torch_dtype=torch.float32)
        for ps in range(30, len(all_dates), PREDICT_EVERY):
            pe = min(ps+PREDICT_EVERY, len(all_dates))
            te = all_dates[ps-1]; ts = te - pd.Timedelta(days=WINDOW_DAYS)
            pd_dates = all_dates[ps:pe]; n_pred = len(pd_dates)
            for iid in top_items:
                item = grid[grid["item_id"]==iid].set_index("date").sort_index()
                hist = item.loc[ts:te]["quantity_sold"].values
                a = item.loc[pd_dates[0]:pd_dates[-1]]["quantity_sold"].values
                price = item["item_price"].iloc[0]
                if len(hist)<14 or len(a)==0: continue
                ctx = torch.tensor(hist, dtype=torch.float32).unsqueeze(0)
                fc = pipeline.predict(ctx, prediction_length=n_pred)
                preds = np.median(fc[0].numpy(), axis=0)
                for i in range(min(len(preds), len(a))):
                    raw.append(float(preds[i])); acts.append(float(a[i]))
                    prices.append(float(price)); ids.append(iid)
        del pipeline; gc.collect()
    elif mtype == "rolling_7d":
        for ps in range(30, len(all_dates), PREDICT_EVERY):
            pe = min(ps+PREDICT_EVERY, len(all_dates))
            te = all_dates[ps-1]; ts = te - pd.Timedelta(days=WINDOW_DAYS)
            pd_dates = all_dates[ps:pe]
            for iid in top_items:
                item = grid[grid["item_id"]==iid].set_index("date").sort_index()
                hist = item.loc[ts:te]["quantity_sold"].values
                a = item.loc[pd_dates[0]:pd_dates[-1]]["quantity_sold"].values
                price = item["item_price"].iloc[0]
                if len(hist)<14 or len(a)==0: continue
                pred = float(np.mean(hist[-7:]))
                for i in range(len(a)):
                    raw.append(pred); acts.append(float(a[i]))
                    prices.append(float(price)); ids.append(iid)
    elif mtype == "same_dow_avg":
        for ps in range(30, len(all_dates), PREDICT_EVERY):
            pe = min(ps+PREDICT_EVERY, len(all_dates))
            te = all_dates[ps-1]; ts = te - pd.Timedelta(days=WINDOW_DAYS)
            pd_dates = all_dates[ps:pe]
            for iid in top_items:
                item = grid[grid["item_id"]==iid].set_index("date").sort_index()
                hist = item.loc[ts:te]["quantity_sold"]
                a = item.loc[pd_dates[0]:pd_dates[-1]]["quantity_sold"].values
                price = item["item_price"].iloc[0]
                if len(hist)<14 or len(a)==0: continue
                for i, d in enumerate(pd_dates):
                    if i >= len(a): break
                    same = hist[hist.index.dayofweek == d.dayofweek].values
                    pred = float(np.mean(same)) if len(same) > 0 else float(np.mean(hist.values[-7:]))
                    raw.append(pred); acts.append(float(a[i]))
                    prices.append(float(price)); ids.append(iid)
    return np.array(raw), np.array(acts), np.array(prices), ids

print("Loading data...")
grid, all_dates, top_items = load_store_data()

models = [
    ("chronos-bolt-mini", "chronos", "amazon/chronos-bolt-mini"),
    ("rolling_7d",        "rolling_7d", None),
    ("same_dow_avg",      "same_dow_avg", None),
]

EXTENDED_BUFFERS = [1.40, 1.45, 1.50, 1.55, 1.60, 1.65, 1.70, 1.75, 1.80, 1.85, 1.90, 1.95, 2.00, 2.10, 2.20, 2.30, 2.40, 2.50]

all_results = []
for name, mtype, mpath in models:
    print(f"\n=== {name} ===")
    t0 = time.time()
    raw, acts, prices, ids = collect_raw(grid, all_dates, top_items, mtype, mpath)
    print(f"  raw preds: {len(raw)} in {time.time()-t0:.0f}s")
    for buf in EXTENDED_BUFFERS:
        preds = np.clip(raw * buf, 0, None)
        mae, cost, waste, stockout = evaluate(acts, preds, prices, ids)
        all_results.append({"model": name, "buffer": buf, "mae": round(mae,4),
                            "cost": round(cost,2), "waste": round(waste,2), "stockout": round(stockout,2)})
        print(f"  buf={buf:.2f}  MAE={mae:.3f}  Cost={cost:>12,.0f}  waste={waste:>9,.0f}  stockout={stockout:>9,.0f}")
    best = min([r for r in all_results if r["model"]==name], key=lambda x: x["cost"])
    print(f"  -> BEST: buf={best['buffer']:.2f}  Cost={best['cost']:,.0f}")

print("\n" + "="*70)
print("FINAL: per-model optimum across extended buffer range")
print("="*70)
print(f"{'Model':<22} {'Opt Buf':>8} {'Cost (DKK)':>14} {'Waste':>10} {'Stockout':>10}")
print("-"*72)
for name, _, _ in models:
    best = min([r for r in all_results if r["model"]==name], key=lambda x: x["cost"])
    print(f"{name:<22} {best['buffer']:>8.2f} {best['cost']:>14,.0f} {best['waste']:>10,.0f} {best['stockout']:>10,.0f}")

with open("/home/yahyahammoudeh/Documents/loving loyalty internship/notebooks/results/buffer_sweep_extended.json", "w") as f:
    json.dump(all_results, f, indent=2, default=str)
print("\nSaved.")
