"""
Chronos-Bolt size comparison: Tiny / Mini / Small / Base zero-shot.
Tests whether bigger Chronos models help on this problem.
"""
import os, time, json, sqlite3, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from chronos import BaseChronosPipeline
warnings.filterwarnings("ignore")

DB_PATH = "data/raw/production.db"
SHELF_LIFE_PATH = "data/raw/production_shelf_life_final.csv"
LOCAL_BASE = "/home/yahyahammoudeh/Documents/loving loyalty internship"
if os.path.exists(os.path.join(LOCAL_BASE, DB_PATH)):
    DB_PATH = os.path.join(LOCAL_BASE, DB_PATH)
    SHELF_LIFE_PATH = os.path.join(LOCAL_BASE, SHELF_LIFE_PATH)

RESULTS_DIR = Path("results_chronos_sizes")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30; TEST_DAYS = 14; CONTEXT_LEN = 96
WASTE_FRACTION = 0.3; STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30; NON_FOOD_SHELF_LIFE = 9999.0
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

SIZES = [
    ("tiny",  "amazon/chronos-bolt-tiny"),
    ("mini",  "amazon/chronos-bolt-mini"),
    ("small", "amazon/chronos-bolt-small"),
    ("base",  "amazon/chronos-bolt-base"),
]

print("="*70); print("CHRONOS-BOLT SIZE COMPARISON"); print("="*70)
t0 = time.time()

# ===== DATA =====
conn = sqlite3.connect(DB_PATH)
orders = pd.read_sql("SELECT id, place_id, created, status FROM fct_orders", conn)
items = pd.read_sql("SELECT order_id, item_id, quantity, price FROM fct_order_items", conn)
menu = pd.read_sql("SELECT id, price FROM dim_menu_items", conn)
conn.close()
orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
items["price"] = pd.to_numeric(items["price"], errors="coerce")
menu["price"] = pd.to_numeric(menu["price"], errors="coerce")
orders = orders[orders["status"] == "Closed"].copy()
orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
orders = orders.dropna(subset=["created_dt"])
orders["date"] = orders["created_dt"].dt.normalize()

shelf_df = pd.read_csv(SHELF_LIFE_PATH)
SHELF_LOOKUP = {str(r["item_id"]): (
    float(r["shelf_life_days"]) if pd.notna(r["shelf_life_days"]) else 3.0,
    float(r["avg_gap_days"]) if pd.notna(r["avg_gap_days"]) else 1.0,
) for _, r in shelf_df.iterrows()}

merged = orders[["id","place_id","date"]].merge(items, left_on="id", right_on="order_id", how="inner")
merged["item_id"] = merged["item_id"].astype(str)
merged["price"] = merged["price"].fillna(merged["item_id"].map(
    menu.assign(id=menu["id"].astype(str)).set_index("id")["price"]))
daily = merged.groupby(["date","place_id","item_id"], observed=True).agg(
    quantity_sold=("quantity","sum"), item_price=("price","mean")).reset_index()
store_days = daily.groupby("place_id")["date"].nunique()
valid_stores = store_days[store_days >= MIN_STORE_DAYS].index
daily = daily[daily["place_id"].isin(valid_stores)].copy()
top_items = (daily.groupby(["place_id","item_id"], observed=True)["quantity_sold"].sum()
             .reset_index().sort_values(["place_id","quantity_sold"], ascending=[True,False])
             .groupby("place_id").head(TOP_N_ITEMS))
pairs = set(zip(top_items["place_id"], top_items["item_id"]))
daily = daily[daily.apply(lambda r: (r["place_id"], r["item_id"]) in pairs, axis=1)].copy()
all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
grid = pd.concat([pd.DataFrame({"date": all_dates, "place_id": pid, "item_id": iid})
                  for (pid, iid), _ in daily.groupby(["place_id","item_id"], observed=True)], ignore_index=True)
df = grid.merge(daily, on=["date","place_id","item_id"], how="left")
df["quantity_sold"] = df["quantity_sold"].fillna(0)
modal = daily.groupby(["place_id","item_id"], observed=True)["item_price"].agg(
    lambda s: s.mode().iloc[0] if len(s.mode())>0 else s.mean()).reset_index().rename(columns={"item_price":"modal_price"})
df = df.merge(modal, on=["place_id","item_id"], how="left")
df["item_price"] = df["item_price"].fillna(df["modal_price"])
df["item_price"] = df["item_price"].fillna(df.groupby("item_id")["item_price"].transform("mean"))
df["item_price"] = df["item_price"].fillna(50.0)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["place_id","item_id","date"]).reset_index(drop=True)
print(f"Data prep: {time.time()-t0:.1f}s")

max_date = df["date"].max()
test_cut = max_date - pd.Timedelta(days=TEST_DAYS)
ctx_start = test_cut - pd.Timedelta(days=CONTEXT_LEN)
train_df = df[(df["date"] > ctx_start) & (df["date"] <= test_cut)].copy()
test_df = df[df["date"] > test_cut].copy()

# Build contexts (series per pair)
contexts = []
meta = []
for (pid, iid), g in train_df.groupby(["place_id","item_id"], observed=True):
    series = g["quantity_sold"].values.astype(np.float32)
    if len(series) < 30:
        continue
    # pad to CONTEXT_LEN
    if len(series) < CONTEXT_LEN:
        series = np.concatenate([np.zeros(CONTEXT_LEN - len(series), dtype=np.float32), series])
    contexts.append(torch.tensor(series[-CONTEXT_LEN:]))
    meta.append((pid, iid))

print(f"Series: {len(contexts)}")

y_test = test_df["quantity_sold"].values.astype(np.float32)
test_prices = test_df["item_price"].values.astype(np.float32)
test_items = test_df["item_id"].values

def cost_fn(actual, pred, prices, iids):
    wf = np.array([
        (0.0 if SHELF_LOOKUP.get(str(i),(3.0,1.0))[0] >= NON_FOOD_SHELF_LIFE
         else WASTE_FRACTION * min(1.0, SHELF_LOOKUP.get(str(i),(3.0,1.0))[1]
                                      / max(SHELF_LOOKUP.get(str(i),(3.0,1.0))[0], 0.5)))
        for i in iids])
    over = np.maximum(pred - actual, 0); under = np.maximum(actual - pred, 0)
    return (over * prices * wf).sum() + STOCKOUT_MULTIPLIER * (under * prices).sum()

all_results = {}
BATCH = 256

for name, hf_id in SIZES:
    print(f"\n{'='*70}\n{name.upper()} ({hf_id})\n{'='*70}")
    try:
        t_l = time.time()
        pipe = BaseChronosPipeline.from_pretrained(hf_id, device_map=DEVICE, torch_dtype=torch.float32)
        n_params = sum(p.numel() for p in pipe.model.parameters())
        print(f"  loaded {n_params/1e6:.0f}M params in {time.time()-t_l:.1f}s")

        t_f = time.time()
        # batch forecast
        preds = []
        for i in range(0, len(contexts), BATCH):
            batch = contexts[i:i+BATCH]
            fc = pipe.predict_quantiles(context=batch, prediction_length=TEST_DAYS, quantile_levels=[0.5])
            # fc is (batch, horizon, 1) - mean/median
            if isinstance(fc, tuple):
                fc_arr = fc[1].cpu().numpy() if hasattr(fc[1], 'cpu') else np.array(fc[1])
                fc_arr = fc_arr[:, :, 0] if fc_arr.ndim == 3 else fc_arr
            else:
                fc_arr = fc.cpu().numpy() if hasattr(fc, 'cpu') else np.array(fc)
                fc_arr = fc_arr[:, :, 0] if fc_arr.ndim == 3 else fc_arr
            preds.append(fc_arr)
        preds = np.concatenate(preds, axis=0)
        preds = np.clip(preds, 0, None)
        print(f"  forecast: {time.time()-t_f:.1f}s, shape={preds.shape}")

        pred_map = {(pid, iid): preds[i] for i, (pid, iid) in enumerate(meta)}
        pred_test_arr = []
        for _, r in test_df.iterrows():
            k = (r["place_id"], r["item_id"])
            day_offset = (r["date"] - test_cut).days - 1
            if k in pred_map and 0 <= day_offset < TEST_DAYS:
                pred_test_arr.append(pred_map[k][day_offset])
            else:
                pred_test_arr.append(0.0)
        pred_test = np.array(pred_test_arr, dtype=np.float32)

        test_mae = float(np.mean(np.abs(pred_test - y_test)))
        print(f"  test MAE: {test_mae:.4f}")

        buf_sweep = {}
        for buf in [1.0, 1.4, 2.0, 2.5, 3.0, 4.0]:
            c = cost_fn(y_test, pred_test * buf, test_prices, test_items)
            buf_sweep[f"buf_{buf:.1f}"] = float(c)
            print(f"  buf={buf:.1f}  cost={c:,.0f}")

        all_results[name] = {
            "hf_id": hf_id, "n_params": n_params, "test_mae": test_mae,
            "buffer_sweep": buf_sweep,
        }
        del pipe
        torch.cuda.empty_cache()
    except Exception as e:
        print(f"  FAILED: {e}")
        all_results[name] = {"error": str(e)}

with open(RESULTS_DIR / "chronos_sizes_results.json", "w") as f:
    json.dump(all_results, f, indent=2, default=str)
print(f"\nSaved. Total: {time.time()-t0:.1f}s")
