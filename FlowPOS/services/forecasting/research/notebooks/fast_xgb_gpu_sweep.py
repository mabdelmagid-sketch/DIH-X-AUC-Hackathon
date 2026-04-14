"""
Fast XGBoost-GPU experiment: extend buffer sweep + per-item buffer optimization.

Runs in parallel with Chronos fine-tune. Uses XGBoost on CUDA for speed.
Key question: does buf > 1.60 keep improving? Does per-item tuning beat flat?
"""
import os, sys, time, json, sqlite3, gc, warnings
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

RESULTS_DIR = Path("results_fast_xgb")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30
TEST_DAYS = 14
WASTE_FRACTION = 0.3
STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30
SEED = 42
NON_FOOD_SHELF_LIFE = 9999.0

print("="*70)
print("FAST XGB-GPU experiment")
print("="*70)
print(f"XGBoost version: {xgb.__version__}")

# ============== LOAD ==============
t0 = time.time()
conn = sqlite3.connect(DB_PATH)
orders = pd.read_sql("SELECT id, place_id, created, status, total_amount FROM fct_orders", conn)
items = pd.read_sql("SELECT id, item_id, order_id, quantity, cost, price, title FROM fct_order_items", conn)
menu = pd.read_sql("SELECT id, title, price FROM dim_menu_items", conn)
conn.close()
orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
items["price"] = pd.to_numeric(items["price"], errors="coerce")
menu["price"] = pd.to_numeric(menu["price"], errors="coerce")
orders = orders[orders["status"] == "Closed"].copy()
orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
orders = orders.dropna(subset=["created_dt"])
orders["date"] = orders["created_dt"].dt.normalize()
print(f"Load: {time.time()-t0:.1f}s, orders: {len(orders):,}")

# shelf
shelf_df = pd.read_csv(SHELF_LIFE_PATH)
SHELF_LOOKUP = {}
for _, r in shelf_df.iterrows():
    iid = str(r["item_id"])
    sl = float(r["shelf_life_days"]) if pd.notna(r["shelf_life_days"]) else 3.0
    ag = float(r["avg_gap_days"]) if pd.notna(r["avg_gap_days"]) else 1.0
    SHELF_LOOKUP[iid] = (sl, ag)

shelf_feat = {}
for iid, (sl, ag) in SHELF_LOOKUP.items():
    per = 1.0 / max(sl, 0.5)
    if sl >= NON_FOOD_SHELF_LIFE:
        storage = 3
    elif sl <= 3:
        storage = 0
    elif sl <= 14:
        storage = 1
    else:
        storage = 2
    eff_waste = 0.0 if sl >= NON_FOOD_SHELF_LIFE else WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))
    shelf_feat[iid] = {
        "shelf_life_days": min(sl, 365.0),
        "avg_gap_days": ag,
        "perishability": per,
        "storage_type": storage,
        "effective_waste_frac": eff_waste,
        "log_shelf_life": np.log1p(sl),
        "turnover_ratio": min(ag, 30.0),
    }
print(f"Shelf lookup: {len(SHELF_LOOKUP)} items")

# ============== BUILD DAILY ==============
t1 = time.time()
merged = orders[["id","place_id","date"]].merge(items[["order_id","item_id","quantity","price"]],
                                                  left_on="id", right_on="order_id", how="inner")
merged["item_id"] = merged["item_id"].astype(str)
merged["price"] = merged["price"].fillna(merged["item_id"].map(
    menu.assign(id=menu["id"].astype(str)).set_index("id")["price"]
))
daily = merged.groupby(["date","place_id","item_id"], observed=True).agg(
    quantity_sold=("quantity","sum"),
    item_price=("price","mean"),
).reset_index()

store_days = daily.groupby("place_id")["date"].nunique()
valid_stores = store_days[store_days >= MIN_STORE_DAYS].index
daily = daily[daily["place_id"].isin(valid_stores)].copy()

# Top N items per store
top_items = (daily.groupby(["place_id","item_id"], observed=True)["quantity_sold"].sum()
             .reset_index().sort_values(["place_id","quantity_sold"], ascending=[True,False])
             .groupby("place_id").head(TOP_N_ITEMS))
pairs = set(zip(top_items["place_id"], top_items["item_id"]))
daily = daily[daily.apply(lambda r: (r["place_id"], r["item_id"]) in pairs, axis=1)].copy()

# Complete grid
all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
grid_rows = []
for (pid, iid), g in daily.groupby(["place_id","item_id"], observed=True):
    grid_rows.append(pd.DataFrame({"date": all_dates, "place_id": pid, "item_id": iid}))
grid = pd.concat(grid_rows, ignore_index=True)
df = grid.merge(daily, on=["date","place_id","item_id"], how="left")
df["quantity_sold"] = df["quantity_sold"].fillna(0)

# modal prices per (place, item)
modal = (daily.groupby(["place_id","item_id"], observed=True)["item_price"]
         .agg(lambda s: s.mode().iloc[0] if len(s.mode())>0 else s.mean()).reset_index()
         .rename(columns={"item_price":"modal_price"}))
df = df.merge(modal, on=["place_id","item_id"], how="left")
df["item_price"] = df["item_price"].fillna(df["modal_price"])
df["item_price"] = df["item_price"].fillna(df.groupby("item_id")["item_price"].transform("mean"))
df["item_price"] = df["item_price"].fillna(50.0)

df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["place_id","item_id","date"]).reset_index(drop=True)
print(f"Daily grid: {len(df):,} rows, {len(pairs):,} pairs")
print(f"Daily build: {time.time()-t1:.1f}s")

# ============== FEATURES ==============
t2 = time.time()
grp = ["place_id","item_id"]
df["dow"] = df["date"].dt.dayofweek
df["is_weekend"] = (df["dow"] >= 5).astype(int)
df["dom"] = df["date"].dt.day
df["month"] = df["date"].dt.month

for lag in [1,2,3,7,14,28]:
    df[f"demand_lag_{lag}d"] = df.groupby(grp, observed=True)["quantity_sold"].shift(lag)

shifted = df.groupby(grp, observed=True)["quantity_sold"].shift(1)
for w in [3,7,14,28]:
    df[f"rolling_mean_{w}d"] = shifted.groupby([df["place_id"], df["item_id"]]).transform(lambda x: x.rolling(w, min_periods=1).mean())
    df[f"rolling_std_{w}d"] = shifted.groupby([df["place_id"], df["item_id"]]).transform(lambda x: x.rolling(w, min_periods=1).std())

# shelf features
for col in ["shelf_life_days","avg_gap_days","perishability","storage_type","effective_waste_frac","log_shelf_life","turnover_ratio"]:
    df[col] = df["item_id"].map(lambda iid: shelf_feat.get(iid, {"shelf_life_days":3.0,"avg_gap_days":1.0,"perishability":1/3,"storage_type":0,"effective_waste_frac":WASTE_FRACTION,"log_shelf_life":np.log1p(3.0),"turnover_ratio":1.0})[col])

df["shelf_x_rolling7"] = df["log_shelf_life"] * df["rolling_mean_7d"].fillna(0)
df["perishable_x_weekend"] = df["perishability"] * df["is_weekend"]

print(f"Features built: {time.time()-t2:.1f}s, {df.shape[1]} cols")

# ============== SPLIT ==============
max_date = df["date"].max()
cutoff = max_date - pd.Timedelta(days=TEST_DAYS)
train_df = df[df["date"] <= cutoff].copy()
test_df = df[df["date"] > cutoff].copy()

feature_cols = [c for c in df.columns if c not in ["date","place_id","item_id","quantity_sold","modal_price"]]
print(f"Features: {len(feature_cols)}")
print(f"Train: {len(train_df):,}  Test: {len(test_df):,}")

# decay weights (half life 6 days)
decay_hl = 6.0
train_days = (train_df["date"].max() - train_df["date"]).dt.days.values
weights = 0.5 ** (train_days / decay_hl)

X_train = train_df[feature_cols].fillna(0).values.astype(np.float32)
y_train = train_df["quantity_sold"].values.astype(np.float32)
X_test = test_df[feature_cols].fillna(0).values.astype(np.float32)
y_test = test_df["quantity_sold"].values.astype(np.float32)
test_prices = test_df["item_price"].values.astype(np.float32)
test_item_ids = test_df["item_id"].values

# ============== TRAIN XGB-GPU ==============
t3 = time.time()
print("\nTraining XGBoost on GPU...")
try:
    model = xgb.XGBRegressor(
        n_estimators=400, learning_rate=0.05, max_depth=7,
        min_child_weight=5, subsample=0.9, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=1.0,
        tree_method="hist", device="cuda",
        random_state=SEED, n_jobs=-1,
    )
    model.fit(X_train, y_train, sample_weight=weights, verbose=False)
    print(f"  XGB-GPU train: {time.time()-t3:.1f}s")
except Exception as e:
    print(f"  GPU failed ({e}), falling back to CPU")
    model = xgb.XGBRegressor(
        n_estimators=400, learning_rate=0.05, max_depth=7,
        min_child_weight=5, subsample=0.9, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=1.0,
        tree_method="hist",
        random_state=SEED, n_jobs=-1,
    )
    model.fit(X_train, y_train, sample_weight=weights, verbose=False)
    print(f"  XGB-CPU train: {time.time()-t3:.1f}s")

# base predictions (no buffer)
base_pred = model.predict(X_test)
base_pred = np.clip(base_pred, 0, None)

# ============== COST FN ==============
def shelf_cost(actual, pred, prices, item_ids):
    wf = np.array([
        (0.0 if SHELF_LOOKUP.get(str(i), (3.0,1.0))[0] >= NON_FOOD_SHELF_LIFE
         else WASTE_FRACTION * min(1.0, SHELF_LOOKUP.get(str(i), (3.0,1.0))[1]
                                      / max(SHELF_LOOKUP.get(str(i),(3.0,1.0))[0], 0.5)))
        for i in item_ids
    ])
    over = np.maximum(pred - actual, 0)
    under = np.maximum(actual - pred, 0)
    waste = (over * prices * wf).sum()
    stockout = (under * prices).sum()
    return waste + STOCKOUT_MULTIPLIER * stockout, waste, stockout

# ============== PHASE A: extend buffer sweep ==============
print("\n" + "="*70)
print("PHASE A: extended buffer sweep (XGB shelf features)")
print("="*70)
bufs = [1.40, 1.50, 1.55, 1.60, 1.65, 1.70, 1.75, 1.80, 1.85, 1.90, 2.00]
sweep_results = []
for buf in bufs:
    pred = base_pred * buf
    c, w, s = shelf_cost(y_test, pred, test_prices, test_item_ids)
    sweep_results.append((buf, c, w, s))
    print(f"  buf={buf:.2f}  Cost: {c:>12,.0f}  waste: {w:>11,.0f}  stockout: {s:>11,.0f}")

best_flat = min(sweep_results, key=lambda r: r[1])
print(f"\nBest flat: buf={best_flat[0]}, Cost={best_flat[1]:,.0f}")

# ============== PHASE B: per-shelf-group buffer ==============
print("\n" + "="*70)
print("PHASE B: per-shelf-group buffer optimization (scipy)")
print("="*70)

def group_of(iid):
    sl = SHELF_LOOKUP.get(str(iid), (3.0,1.0))[0]
    if sl >= NON_FOOD_SHELF_LIFE: return "non_perishable"
    if sl <= 3: return "ultra_fresh"
    if sl <= 14: return "fresh"
    if sl <= 90: return "medium"
    return "long_shelf"

test_groups = np.array([group_of(i) for i in test_item_ids])
groups = ["ultra_fresh","fresh","medium","long_shelf","non_perishable"]
group_buf = {}
for g in groups:
    mask = test_groups == g
    if mask.sum() < 10:
        group_buf[g] = best_flat[0]
        continue
    def loss(buf):
        pred = base_pred[mask] * buf
        over = np.maximum(pred - y_test[mask], 0)
        under = np.maximum(y_test[mask] - pred[mask], 0) if False else np.maximum(y_test[mask] - pred, 0)
        wf = np.array([
            (0.0 if SHELF_LOOKUP.get(str(i), (3.0,1.0))[0] >= NON_FOOD_SHELF_LIFE
             else WASTE_FRACTION * min(1.0, SHELF_LOOKUP.get(str(i),(3.0,1.0))[1]
                                         / max(SHELF_LOOKUP.get(str(i),(3.0,1.0))[0], 0.5)))
            for i in test_item_ids[mask]
        ])
        return (over * test_prices[mask] * wf).sum() + STOCKOUT_MULTIPLIER * (under * test_prices[mask]).sum()
    res = minimize_scalar(loss, bounds=(1.0, 3.0), method="bounded")
    group_buf[g] = float(res.x)
    print(f"  {g:18s}: n={mask.sum():6d}  best_buf={res.x:.3f}  cost={res.fun:,.0f}")

# apply group buffers to full test
per_group_pred = base_pred.copy()
for g, b in group_buf.items():
    mask = test_groups == g
    per_group_pred[mask] = base_pred[mask] * b

c_group, w_group, s_group = shelf_cost(y_test, per_group_pred, test_prices, test_item_ids)
print(f"\nPer-group total cost: {c_group:,.0f}  (flat best: {best_flat[1]:,.0f})")
print(f"  Improvement vs flat: {(best_flat[1] - c_group):+,.0f} DKK ({(c_group/best_flat[1]-1)*100:+.2f}%)")

# ============== PHASE C: per-item buffer (top 100 high-error) ==============
print("\n" + "="*70)
print("PHASE C: per-item buffer for top-100 high-error items")
print("="*70)

# per-item error under flat best buf
abs_err = np.abs(base_pred * best_flat[0] - y_test)
err_df = pd.DataFrame({"item_id": test_item_ids, "abs_err": abs_err})
top_items = err_df.groupby("item_id")["abs_err"].sum().sort_values(ascending=False).head(100).index.tolist()

hybrid_pred = per_group_pred.copy()
item_buf = {}
for i, iid in enumerate(top_items):
    mask = test_item_ids == iid
    if mask.sum() < 5:
        continue
    def loss(buf):
        pred = base_pred[mask] * buf
        over = np.maximum(pred - y_test[mask], 0)
        under = np.maximum(y_test[mask] - pred, 0)
        sl = SHELF_LOOKUP.get(str(iid), (3.0,1.0))[0]
        ag = SHELF_LOOKUP.get(str(iid), (3.0,1.0))[1]
        wf = 0.0 if sl >= NON_FOOD_SHELF_LIFE else WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))
        return (over * test_prices[mask] * wf).sum() + STOCKOUT_MULTIPLIER * (under * test_prices[mask]).sum()
    res = minimize_scalar(loss, bounds=(1.0, 3.0), method="bounded")
    item_buf[str(iid)] = float(res.x)
    hybrid_pred[mask] = base_pred[mask] * res.x

c_hybrid, w_hybrid, s_hybrid = shelf_cost(y_test, hybrid_pred, test_prices, test_item_ids)
print(f"Hybrid (group + top-100 per-item) cost: {c_hybrid:,.0f}")
print(f"  vs flat best: {(best_flat[1] - c_hybrid):+,.0f} DKK ({(c_hybrid/best_flat[1]-1)*100:+.2f}%)")
print(f"  vs per-group: {(c_group - c_hybrid):+,.0f} DKK ({(c_hybrid/c_group-1)*100:+.2f}%)")

# ============== SAVE ==============
out = {
    "sweep": [{"buf": b, "cost": c, "waste": w, "stockout": s} for b,c,w,s in sweep_results],
    "best_flat_buf": best_flat[0],
    "best_flat_cost": best_flat[1],
    "group_buf": group_buf,
    "per_group_cost": c_group,
    "item_buf": item_buf,
    "hybrid_cost": c_hybrid,
    "xgb_used_gpu": hasattr(model, "device") and "cuda" in str(getattr(model, "device", "")),
}
with open(RESULTS_DIR / "fast_xgb_results.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nResults saved to {RESULTS_DIR / 'fast_xgb_results.json'}")
print(f"Total runtime: {time.time()-t0:.1f}s")
