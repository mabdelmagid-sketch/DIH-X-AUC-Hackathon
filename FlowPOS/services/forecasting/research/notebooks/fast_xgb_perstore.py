"""
Per-store buffer tuning on top of global XGB-GPU model.

Train XGB once globally -> predict on val + test.
For each store: tune flat buffer on val -> apply to test.
Compare:
  - Flat global buffer (baseline from clean run: 3.22)
  - Per-group buffer (baseline from clean run: 5.91M)
  - Per-store buffer (new)
  - Per-store + per-group fallback (new hybrid)

Proper train/val/test split -> no test leakage.
"""
import os, sys, time, json, sqlite3, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.optimize import minimize_scalar
warnings.filterwarnings("ignore")

DB_PATH = "data/raw/production.db"
SHELF_LIFE_PATH = "data/raw/production_shelf_life_final.csv"
LOCAL_BASE = "/home/yahyahammoudeh/Documents/loving loyalty internship"
if os.path.exists(os.path.join(LOCAL_BASE, DB_PATH)):
    DB_PATH = os.path.join(LOCAL_BASE, DB_PATH)
    SHELF_LIFE_PATH = os.path.join(LOCAL_BASE, SHELF_LIFE_PATH)

RESULTS_DIR = Path("results_fast_xgb_perstore")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30
TEST_DAYS = 14
VAL_DAYS = 14
WASTE_FRACTION = 0.3
STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30
MIN_STORE_VAL_ROWS = 100  # stores with fewer val rows fall back to per-group
SEED = 42
NON_FOOD_SHELF_LIFE = 9999.0

print("="*70)
print("PER-STORE XGB-GPU buffer tuning")
print("="*70)

# Load
t0 = time.time()
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
print(f"Load: {time.time()-t0:.1f}s")

# Build daily
t1 = time.time()
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
print(f"Daily grid: {len(df):,} rows, {time.time()-t1:.1f}s")

# Features
t2 = time.time()
grp = ["place_id","item_id"]
df["dow"] = df["date"].dt.dayofweek
df["is_weekend"] = (df["dow"] >= 5).astype(int)
df["dom"] = df["date"].dt.day
df["month"] = df["date"].dt.month
for lag in [1,2,3,7,14,28]:
    df[f"lag_{lag}"] = df.groupby(grp, observed=True)["quantity_sold"].shift(lag)
shifted = df.groupby(grp, observed=True)["quantity_sold"].shift(1)
for w in [3,7,14,28]:
    df[f"rmean_{w}"] = shifted.groupby([df["place_id"], df["item_id"]]).transform(lambda x: x.rolling(w, min_periods=1).mean())
    df[f"rstd_{w}"] = shifted.groupby([df["place_id"], df["item_id"]]).transform(lambda x: x.rolling(w, min_periods=1).std())

def get_shelf(iid):
    sl, ag = SHELF_LOOKUP.get(str(iid), (3.0, 1.0))
    per = 1.0 / max(sl, 0.5)
    storage = 3 if sl >= NON_FOOD_SHELF_LIFE else (0 if sl <= 3 else 1 if sl <= 14 else 2)
    eff = 0.0 if sl >= NON_FOOD_SHELF_LIFE else WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))
    return min(sl, 365.0), ag, per, storage, eff, np.log1p(sl), min(ag, 30.0)

shelf_cache = {iid: get_shelf(iid) for iid in df["item_id"].unique()}
for idx, col in enumerate(["sl","ag","per","store","effw","logsl","turn"]):
    df[col] = df["item_id"].map(lambda iid: shelf_cache[iid][idx])
df["shelf_x_r7"] = df["logsl"] * df["rmean_7"].fillna(0)
df["per_x_we"] = df["per"] * df["is_weekend"]
print(f"Features: {time.time()-t2:.1f}s, {df.shape[1]} cols")

# Splits
max_date = df["date"].max()
test_cut = max_date - pd.Timedelta(days=TEST_DAYS)
val_cut = test_cut - pd.Timedelta(days=VAL_DAYS)
train_df = df[df["date"] <= val_cut].copy()
val_df = df[(df["date"] > val_cut) & (df["date"] <= test_cut)].copy()
test_df = df[df["date"] > test_cut].copy()
feat = [c for c in df.columns if c not in ["date","place_id","item_id","quantity_sold","modal_price","item_price"]]

decay_hl = 6.0
train_days = (train_df["date"].max() - train_df["date"]).dt.days.values
weights = 0.5 ** (train_days / decay_hl)

X_train = train_df[feat].fillna(0).values.astype(np.float32)
y_train = train_df["quantity_sold"].values.astype(np.float32)
X_val = val_df[feat].fillna(0).values.astype(np.float32)
y_val = val_df["quantity_sold"].values.astype(np.float32)
X_test = test_df[feat].fillna(0).values.astype(np.float32)
y_test = test_df["quantity_sold"].values.astype(np.float32)
val_prices = val_df["item_price"].values.astype(np.float32)
val_items = val_df["item_id"].values
val_stores = val_df["place_id"].values
test_prices = test_df["item_price"].values.astype(np.float32)
test_items = test_df["item_id"].values
test_stores = test_df["place_id"].values

# Train
t3 = time.time()
print("\nTraining XGB-GPU...")
model = xgb.XGBRegressor(
    n_estimators=400, learning_rate=0.05, max_depth=7,
    min_child_weight=5, subsample=0.9, colsample_bytree=0.8,
    reg_alpha=0.1, reg_lambda=1.0,
    tree_method="hist", device="cuda",
    random_state=SEED, n_jobs=-1,
)
model.fit(X_train, y_train, sample_weight=weights, verbose=False)
print(f"Training: {time.time()-t3:.1f}s")

pred_val = np.clip(model.predict(X_val), 0, None)
pred_test = np.clip(model.predict(X_test), 0, None)

# Helpers
def cost_fn(actual, pred, prices, iids):
    wf = np.array([
        (0.0 if SHELF_LOOKUP.get(str(i),(3.0,1.0))[0] >= NON_FOOD_SHELF_LIFE
         else WASTE_FRACTION * min(1.0, SHELF_LOOKUP.get(str(i),(3.0,1.0))[1]
                                     / max(SHELF_LOOKUP.get(str(i),(3.0,1.0))[0], 0.5)))
        for i in iids])
    over = np.maximum(pred - actual, 0)
    under = np.maximum(actual - pred, 0)
    return (over * prices * wf).sum() + STOCKOUT_MULTIPLIER * (under * prices).sum()

def group_of(iid):
    sl = SHELF_LOOKUP.get(str(iid), (3.0, 1.0))[0]
    if sl >= NON_FOOD_SHELF_LIFE: return "non_perishable"
    if sl <= 3: return "ultra_fresh"
    if sl <= 14: return "fresh"
    if sl <= 90: return "medium"
    return "long_shelf"

# Tune per-group on val (same as clean script, reproduces baseline)
val_groups = np.array([group_of(i) for i in val_items])
test_groups = np.array([group_of(i) for i in test_items])

groups = ["ultra_fresh","fresh","medium","long_shelf","non_perishable"]
group_buf = {}
for g in groups:
    mask = val_groups == g
    if mask.sum() < 50:
        group_buf[g] = 1.40
        continue
    def loss(buf):
        return cost_fn(y_val[mask], pred_val[mask] * buf, val_prices[mask], val_items[mask])
    res = minimize_scalar(loss, bounds=(1.0, 10.0), method="bounded")
    group_buf[g] = float(res.x)

# Per-store flat buffer (on val)
print("\n" + "="*70)
print("TUNING PER-STORE FLAT BUFFER ON VALIDATION")
print("="*70)
unique_stores = np.unique(test_stores)
print(f"Stores: {len(unique_stores)}")
store_buf = {}
fallback_stores = []
t4 = time.time()
for pid in unique_stores:
    mask = val_stores == pid
    if mask.sum() < MIN_STORE_VAL_ROWS:
        fallback_stores.append(pid)
        continue
    def loss(buf):
        return cost_fn(y_val[mask], pred_val[mask] * buf, val_prices[mask], val_items[mask])
    res = minimize_scalar(loss, bounds=(1.0, 10.0), method="bounded")
    store_buf[pid] = float(res.x)
print(f"Tuned {len(store_buf)} stores ({len(fallback_stores)} fallback)  {time.time()-t4:.1f}s")

# Per-store x per-group buffer (tune buf per (store, group) on val)
print("\n" + "="*70)
print("TUNING PER-STORE x PER-GROUP BUFFER ON VAL")
print("="*70)
store_group_buf = {}
t5 = time.time()
for pid in unique_stores:
    store_group_buf[pid] = {}
    for g in groups:
        mask = (val_stores == pid) & (val_groups == g)
        if mask.sum() < 20:
            # fallback: global per-group buf
            store_group_buf[pid][g] = group_buf[g]
            continue
        def loss(buf):
            return cost_fn(y_val[mask], pred_val[mask] * buf, val_prices[mask], val_items[mask])
        res = minimize_scalar(loss, bounds=(1.0, 10.0), method="bounded")
        store_group_buf[pid][g] = float(res.x)
print(f"Tuned store x group in {time.time()-t5:.1f}s")

# ============ EVALUATE ON TEST ============
print("\n" + "="*70)
print("FINAL TEST EVALUATION")
print("="*70)

c_140 = cost_fn(y_test, pred_test * 1.40, test_prices, test_items)

# global per-group (baseline from clean run)
pg_pred = pred_test.copy()
for g, b in group_buf.items():
    mask = test_groups == g
    pg_pred[mask] = pred_test[mask] * b
c_group = cost_fn(y_test, pg_pred, test_prices, test_items)

# per-store flat
ps_pred = pred_test.copy()
for pid, b in store_buf.items():
    mask = test_stores == pid
    ps_pred[mask] = pred_test[mask] * b
# fallback stores use flat best
fallback_buf = float(np.mean(list(store_buf.values()))) if store_buf else 3.22
for pid in fallback_stores:
    mask = test_stores == pid
    ps_pred[mask] = pred_test[mask] * fallback_buf
c_perstore = cost_fn(y_test, ps_pred, test_prices, test_items)

# per-store x per-group
psg_pred = pred_test.copy()
for pid, gbufs in store_group_buf.items():
    for g, b in gbufs.items():
        mask = (test_stores == pid) & (test_groups == g)
        psg_pred[mask] = pred_test[mask] * b
c_psg = cost_fn(y_test, psg_pred, test_prices, test_items)

print(f"Baseline (flat 1.40):           {c_140:>14,.0f} DKK")
print(f"Per-group (global):             {c_group:>14,.0f} DKK  ({(c_group/c_140-1)*100:+.2f}%)")
print(f"Per-store (flat per store):     {c_perstore:>14,.0f} DKK  ({(c_perstore/c_140-1)*100:+.2f}%)")
print(f"Per-store x per-group:          {c_psg:>14,.0f} DKK  ({(c_psg/c_140-1)*100:+.2f}%)")

# Save
out = {
    "group_buf": group_buf,
    "store_buf": {str(k): v for k, v in store_buf.items()},
    "store_group_buf": {str(k): v for k, v in store_group_buf.items()},
    "test_cost_baseline_140": float(c_140),
    "test_cost_per_group": float(c_group),
    "test_cost_per_store": float(c_perstore),
    "test_cost_per_store_x_group": float(c_psg),
    "n_stores": int(len(unique_stores)),
    "n_stores_tuned": len(store_buf),
    "n_fallback_stores": len(fallback_stores),
}
with open(RESULTS_DIR / "fast_xgb_perstore_results.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved: {RESULTS_DIR / 'fast_xgb_perstore_results.json'}")
print(f"Total: {time.time()-t0:.1f}s")
