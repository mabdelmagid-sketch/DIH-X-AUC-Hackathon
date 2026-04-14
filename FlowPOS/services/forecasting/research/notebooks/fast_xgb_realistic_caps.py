"""
Realistic buffer caps for production deployment.

The unconstrained optimum produced buf=10.0 for long-shelf and non-perishable
items because waste cost is near zero for them. In real warehouses, we can't
stock 10x predicted demand — warehouse space, ordering overhead, and cash flow
all cap practical buffers at 2-3x.

This script sweeps buffer caps: 2.0, 2.5, 3.0, 4.0, 5.0 and reports the
honest test cost so the business can pick the right trade-off.
"""
import os, json, sqlite3, time, warnings
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

RESULTS_DIR = Path("results_realistic_caps")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30; TEST_DAYS = 14; VAL_DAYS = 14
WASTE_FRACTION = 0.3; STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30; SEED = 42; NON_FOOD_SHELF_LIFE = 9999.0

print("="*70 + "\nREALISTIC BUFFER CAPS (production-deployable)\n" + "="*70)

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
print(f"Daily: {len(df):,} rows, {time.time()-t1:.1f}s")

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
for idx, col in enumerate(["sl","ag","per","stype","effw","logsl","turn"]):
    df[col] = df["item_id"].map(lambda iid: shelf_cache[iid][idx])
df["shelf_x_r7"] = df["logsl"] * df["rmean_7"].fillna(0)
df["per_x_we"] = df["per"] * df["is_weekend"]
print(f"Features: {time.time()-t2:.1f}s")

max_date = df["date"].max()
test_cut = max_date - pd.Timedelta(days=TEST_DAYS)
val_cut = test_cut - pd.Timedelta(days=VAL_DAYS)
train_df = df[df["date"] <= val_cut].copy()
val_df = df[(df["date"] > val_cut) & (df["date"] <= test_cut)].copy()
test_df = df[df["date"] > test_cut].copy()
feat = [c for c in df.columns if c not in {"date","place_id","item_id","quantity_sold","modal_price","item_price"}]

weights = 0.5 ** (((train_df["date"].max() - train_df["date"]).dt.days.values) / 6.0)
X_train = train_df[feat].fillna(0).values.astype(np.float32)
y_train = train_df["quantity_sold"].values.astype(np.float32)
X_val = val_df[feat].fillna(0).values.astype(np.float32)
y_val = val_df["quantity_sold"].values.astype(np.float32)
X_test = test_df[feat].fillna(0).values.astype(np.float32)
y_test = test_df["quantity_sold"].values.astype(np.float32)
val_prices = val_df["item_price"].values.astype(np.float32); val_items = val_df["item_id"].values
test_prices = test_df["item_price"].values.astype(np.float32); test_items = test_df["item_id"].values

t3 = time.time()
model = xgb.XGBRegressor(
    n_estimators=400, learning_rate=0.05, max_depth=7,
    min_child_weight=5, subsample=0.9, colsample_bytree=0.8,
    reg_alpha=0.1, reg_lambda=1.0,
    tree_method="hist", device="cuda",
    random_state=SEED, n_jobs=-1,
)
model.fit(X_train, y_train, sample_weight=weights, verbose=False)
pred_val = np.clip(model.predict(X_val), 0, None)
pred_test = np.clip(model.predict(X_test), 0, None)
print(f"XGB-GPU trained: {time.time()-t3:.1f}s")

def cost_fn(actual, pred, prices, iids):
    wf = np.array([
        (0.0 if SHELF_LOOKUP.get(str(i),(3.0,1.0))[0] >= NON_FOOD_SHELF_LIFE
         else WASTE_FRACTION * min(1.0, SHELF_LOOKUP.get(str(i),(3.0,1.0))[1]
                                     / max(SHELF_LOOKUP.get(str(i),(3.0,1.0))[0], 0.5)))
        for i in iids])
    over = np.maximum(pred - actual, 0); under = np.maximum(actual - pred, 0)
    return (over * prices * wf).sum() + STOCKOUT_MULTIPLIER * (under * prices).sum()

def group_of(iid):
    sl = SHELF_LOOKUP.get(str(iid), (3.0, 1.0))[0]
    if sl >= NON_FOOD_SHELF_LIFE: return "non_perishable"
    if sl <= 3: return "ultra_fresh"
    if sl <= 14: return "fresh"
    if sl <= 90: return "medium"
    return "long_shelf"

val_groups = np.array([group_of(i) for i in val_items])
test_groups = np.array([group_of(i) for i in test_items])
groups = ["ultra_fresh","fresh","medium","long_shelf","non_perishable"]

# ============== SWEEP CAPS ==============
print("\n" + "="*70)
print("SWEEPING BUFFER CAPS")
print("="*70)

c_baseline = cost_fn(y_test, pred_test * 1.40, test_prices, test_items)
print(f"Baseline (flat 1.40): {c_baseline:,.0f} DKK (-- reference)\n")
print(f"{'Cap':>6}  {'ultra':>6} {'fresh':>6} {'medium':>6} {'long':>6} {'non':>6}   {'Test Cost':>12}   {'vs 1.40':>8}")

scenarios = []
for cap in [2.0, 2.5, 3.0, 4.0, 5.0, 10.0]:
    group_buf = {}
    for g in groups:
        mask = val_groups == g
        if mask.sum() < 50:
            group_buf[g] = min(cap, 3.22)
            continue
        def loss(buf):
            return cost_fn(y_val[mask], pred_val[mask] * buf, val_prices[mask], val_items[mask])
        res = minimize_scalar(loss, bounds=(1.0, cap), method="bounded")
        group_buf[g] = float(res.x)
    pg_pred = pred_test.copy()
    for g, b in group_buf.items():
        mask = test_groups == g
        pg_pred[mask] = pred_test[mask] * b
    c_group = cost_fn(y_test, pg_pred, test_prices, test_items)
    bufs = [group_buf[g] for g in groups]
    scenarios.append({"cap": cap, "group_buf": group_buf, "test_cost": c_group})
    print(f"{cap:>6.1f}  {bufs[0]:>6.2f} {bufs[1]:>6.2f} {bufs[2]:>6.2f} {bufs[3]:>6.2f} {bufs[4]:>6.2f}   "
          f"{c_group:>12,.0f}   {(c_group/c_baseline-1)*100:>7.2f}%")

# Also try per-item cap of 3.0 (blended approach)
print("\nHybrid: group-level capped at 3.0, with explicit ceiling on recommended qty")
cap = 3.0
group_buf = {}
for g in groups:
    mask = val_groups == g
    def loss(buf):
        return cost_fn(y_val[mask], pred_val[mask] * buf, val_prices[mask], val_items[mask])
    res = minimize_scalar(loss, bounds=(1.0, cap), method="bounded")
    group_buf[g] = float(res.x)

print(f"\nRECOMMENDED PRODUCTION CONFIG (cap=3.0):")
for g in groups:
    print(f"  {g:18s}: buf={group_buf[g]:.3f}")

pg_pred = pred_test.copy()
for g, b in group_buf.items():
    mask = test_groups == g
    pg_pred[mask] = pred_test[mask] * b
c_rec = cost_fn(y_test, pg_pred, test_prices, test_items)
print(f"\nTest cost: {c_rec:,.0f} DKK")
print(f"vs baseline 1.40:        {(c_rec/c_baseline-1)*100:+.2f}%  (saved {c_baseline-c_rec:,.0f} DKK)")
print(f"vs unconstrained 5.91M:  {(c_rec/5906055-1)*100:+.2f}%  ({c_rec-5906055:+,.0f} DKK)")

out = {"scenarios": scenarios, "recommended_cap": 3.0, "recommended_group_buf": group_buf,
       "test_cost_baseline_140": float(c_baseline),
       "test_cost_recommended": float(c_rec),
       "test_cost_unconstrained_591M": 5906055.0}
with open(RESULTS_DIR / "realistic_caps_results.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved: {RESULTS_DIR / 'realistic_caps_results.json'}")
print(f"Total: {time.time()-t0:.1f}s")
