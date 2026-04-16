"""
TimesFM zero-shot: Google's 200M-param time series foundation model.
Compares against Chronos to see if a different FM does better.
"""
import os, time, json, sqlite3, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
warnings.filterwarnings("ignore")

# Install timesfm if not present
try:
    import timesfm
except ImportError:
    os.system("pip install -q timesfm[torch]==1.3.0 2>&1 | tail -3")
    import timesfm

DB_PATH = "data/raw/production.db"
SHELF_LIFE_PATH = "data/raw/production_shelf_life_final.csv"
LOCAL_BASE = "/home/yahyahammoudeh/Documents/loving loyalty internship"
if os.path.exists(os.path.join(LOCAL_BASE, DB_PATH)):
    DB_PATH = os.path.join(LOCAL_BASE, DB_PATH)
    SHELF_LIFE_PATH = os.path.join(LOCAL_BASE, SHELF_LIFE_PATH)

RESULTS_DIR = Path("results_timesfm")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30; TEST_DAYS = 14
WASTE_FRACTION = 0.3; STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30; NON_FOOD_SHELF_LIFE = 9999.0
CONTEXT_LEN = 96  # TimesFM can handle up to 512

t0 = time.time()
print("="*70); print("TimesFM zero-shot"); print("="*70)

# Load data
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
print(f"Data: {time.time()-t0:.1f}s, pairs={len(pairs)}")

max_date = df["date"].max()
test_cut = max_date - pd.Timedelta(days=TEST_DAYS)
test_dates = sorted(df[df["date"] > test_cut]["date"].unique())

# Load TimesFM
print("Loading TimesFM 2.0 (200M)...")
t_l = time.time()
try:
    tfm = timesfm.TimesFm(
        hparams=timesfm.TimesFmHparams(
            backend="gpu", per_core_batch_size=512,
            horizon_len=TEST_DAYS,
            context_len=CONTEXT_LEN,
            input_patch_len=32, output_patch_len=128,
            num_layers=50, model_dims=1280,
            use_positional_embedding=False,
        ),
        checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id="google/timesfm-2.0-500m-pytorch"),
    )
    model_name = "timesfm-2.0-500m"
except Exception as e:
    print(f"2.0 load failed ({e}), trying 1.0...")
    tfm = timesfm.TimesFm(
        hparams=timesfm.TimesFmHparams(
            backend="gpu", per_core_batch_size=512,
            horizon_len=TEST_DAYS, context_len=CONTEXT_LEN,
        ),
        checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id="google/timesfm-1.0-200m-pytorch"),
    )
    model_name = "timesfm-1.0-200m"
print(f"Loaded {model_name}: {time.time()-t_l:.1f}s")

# Build contexts
ctx_start = test_cut - pd.Timedelta(days=CONTEXT_LEN)
train_df = df[(df["date"] > ctx_start) & (df["date"] <= test_cut)].copy()
test_df = df[df["date"] > test_cut].copy()

# Group by (store, item) to get series
contexts = []
meta = []
for (pid, iid), g in train_df.groupby(["place_id","item_id"], observed=True):
    series = g["quantity_sold"].values.astype(np.float32)
    if len(series) < CONTEXT_LEN // 2:
        continue
    contexts.append(series)
    meta.append((pid, iid))

print(f"Series to forecast: {len(contexts)}")

# Forecast
t_f = time.time()
preds = tfm.forecast(contexts, freq=[0]*len(contexts))  # 0=daily
if isinstance(preds, tuple):
    preds = preds[0]
preds = np.array(preds)[:, :TEST_DAYS]
preds = np.clip(preds, 0, None)
print(f"Forecast: {time.time()-t_f:.1f}s  shape={preds.shape}")

# Match predictions to test_df rows
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

y_test = test_df["quantity_sold"].values.astype(np.float32)
test_prices = test_df["item_price"].values.astype(np.float32)
test_items = test_df["item_id"].values
test_mae = float(np.mean(np.abs(pred_test - y_test)))
print(f"TimesFM test MAE: {test_mae:.4f}")

# Cost + buffer sweep
def cost_fn(actual, pred, prices, iids):
    wf = np.array([
        (0.0 if SHELF_LOOKUP.get(str(i),(3.0,1.0))[0] >= NON_FOOD_SHELF_LIFE
         else WASTE_FRACTION * min(1.0, SHELF_LOOKUP.get(str(i),(3.0,1.0))[1]
                                      / max(SHELF_LOOKUP.get(str(i),(3.0,1.0))[0], 0.5)))
        for i in iids])
    over = np.maximum(pred - actual, 0); under = np.maximum(actual - pred, 0)
    return (over * prices * wf).sum() + STOCKOUT_MULTIPLIER * (under * prices).sum()

results = {}
for buf in [1.0, 1.4, 2.0, 2.5, 3.0, 4.0]:
    c = cost_fn(y_test, pred_test * buf, test_prices, test_items)
    print(f"  buf={buf:.1f}  cost={c:,.0f}")
    results[f"buf_{buf:.1f}"] = float(c)

out = {
    "model": model_name, "test_mae": test_mae,
    "buffer_sweep": results,
    "xgb_cap3_ref": 6558810, "chronos_ft_best": 9194415,
    "total_seconds": time.time() - t0,
}
with open(RESULTS_DIR / "timesfm_results.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved. Total: {time.time()-t0:.1f}s")
