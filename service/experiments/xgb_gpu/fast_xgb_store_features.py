"""
XGB-GPU with store-level features added.

New features from dim_places:
  - chain_id (label encoded)
  - area_id (label encoded)
  - type_id (label encoded)
  - primary_cuisine_id (first item in pipe-separated list)
  - seasonal (0/1)
  - store_age_days (from `created` timestamp)
  - hours_per_week (parsed from opening_hours JSON)
  - days_open_per_week
  - weekend_open (0/1)
  - closed_monday (0/1)

Clean train/val/test split, per-group buffer tuning on val.
Compare against previous 5,906,055 DKK per-group benchmark.
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

RESULTS_DIR = Path("results_xgb_store_feats")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30
TEST_DAYS = 14
VAL_DAYS = 14
WASTE_FRACTION = 0.3
STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30
SEED = 42
NON_FOOD_SHELF_LIFE = 9999.0

print("="*70)
print("XGB-GPU + STORE FEATURES")
print("="*70)

t0 = time.time()
conn = sqlite3.connect(DB_PATH)

# Orders / items / menu
orders = pd.read_sql("SELECT id, place_id, created, status FROM fct_orders", conn)
items = pd.read_sql("SELECT order_id, item_id, quantity, price FROM fct_order_items", conn)
menu = pd.read_sql("SELECT id, price FROM dim_menu_items", conn)

# Store metadata
places = pd.read_sql("""
    SELECT id, created, chain_id, area_id, type_id, cuisine_ids, seasonal, opening_hours
    FROM dim_places
""", conn)
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
print(f"Load: {time.time()-t0:.1f}s  |  places: {len(places)}")

# ==================== STORE FEATURE EXTRACTION ====================
t_s = time.time()

# Numeric conversions
for c in ["chain_id", "area_id", "type_id", "seasonal", "created"]:
    places[c] = pd.to_numeric(places[c], errors="coerce")

# Primary cuisine = first id in pipe-separated list
def primary_cuisine(s):
    if pd.isna(s) or s == "":
        return -1
    try:
        return int(str(s).split("|")[0])
    except Exception:
        return -1
places["primary_cuisine_id"] = places["cuisine_ids"].apply(primary_cuisine)

# Store age: created is unix seconds → days since
REFERENCE_TS = orders["created"].max()
places["store_age_days"] = ((REFERENCE_TS - places["created"]) / 86400.0).clip(lower=0)

# Opening hours parsing
def parse_hours(h):
    if not isinstance(h, str) or h.strip() == "":
        return pd.Series({"hours_per_week": np.nan, "days_open_per_week": np.nan,
                          "weekend_open": np.nan, "closed_monday": np.nan})
    try:
        d = json.loads(h)
    except Exception:
        return pd.Series({"hours_per_week": np.nan, "days_open_per_week": np.nan,
                          "weekend_open": np.nan, "closed_monday": np.nan})

    def to_h(t):
        if not t or t == "closed":
            return None
        try:
            parts = t.replace(",", ".").split(".")
            return float(parts[0]) + (float(parts[1]) / 60.0 if len(parts) > 1 else 0.0)
        except Exception:
            return None

    total = 0.0
    days_open = 0
    closed_mon = 0
    weekend_open = 0
    for day in ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]:
        if day not in d:
            continue
        frm = to_h(d[day].get("from"))
        to_ = to_h(d[day].get("to"))
        if frm is None or to_ is None:
            if day == "monday": closed_mon = 1
            continue
        span = (to_ - frm) if to_ >= frm else (to_ + 24 - frm)
        if span > 0:
            total += span
            days_open += 1
            if day in ("saturday","sunday"):
                weekend_open = 1
    if closed_mon == 0 and "monday" in d:
        mfrm = to_h(d["monday"].get("from"))
        if mfrm is None: closed_mon = 1
    return pd.Series({
        "hours_per_week": total,
        "days_open_per_week": float(days_open),
        "weekend_open": float(weekend_open),
        "closed_monday": float(closed_mon),
    })

hours_feats = places["opening_hours"].apply(parse_hours)
places = pd.concat([places, hours_feats], axis=1)

# Label-encode categorical store features
for c in ["chain_id", "area_id", "type_id", "primary_cuisine_id"]:
    places[c] = places[c].fillna(-1).astype(int)

store_feat_cols = [
    "chain_id","area_id","type_id","primary_cuisine_id","seasonal",
    "store_age_days","hours_per_week","days_open_per_week","weekend_open","closed_monday",
]
store_features = places[["id"] + store_feat_cols].copy()
store_features["id"] = store_features["id"].astype(str)
for c in store_feat_cols:
    store_features[c] = pd.to_numeric(store_features[c], errors="coerce")
print(f"Store features built: {time.time()-t_s:.1f}s  ({len(store_feat_cols)} cols)")
print(f"  coverage: {store_features.dropna(subset=store_feat_cols, how='all')['id'].nunique()} / {len(store_features)}")

# ==================== DAILY GRID (same as before) ====================
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
print(f"Daily grid: {len(df):,}, {time.time()-t1:.1f}s")

# ==================== FEATURE ENGINEERING ====================
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
for idx, col in enumerate(["sl","ag","per","store_type","effw","logsl","turn"]):
    df[col] = df["item_id"].map(lambda iid: shelf_cache[iid][idx])
df["shelf_x_r7"] = df["logsl"] * df["rmean_7"].fillna(0)
df["per_x_we"] = df["per"] * df["is_weekend"]

# Merge store features
df["place_id_str"] = df["place_id"].astype(str)
df = df.merge(store_features, left_on="place_id_str", right_on="id", how="left", suffixes=("", "_store"))
df = df.drop(columns=["id", "place_id_str"])
for c in store_feat_cols:
    df[c] = df[c].fillna(-1 if c in ("chain_id","area_id","type_id","primary_cuisine_id") else df[c].median())

print(f"Features: {time.time()-t2:.1f}s, {df.shape[1]} cols")

# ==================== SPLIT ====================
max_date = df["date"].max()
test_cut = max_date - pd.Timedelta(days=TEST_DAYS)
val_cut = test_cut - pd.Timedelta(days=VAL_DAYS)
train_df = df[df["date"] <= val_cut].copy()
val_df = df[(df["date"] > val_cut) & (df["date"] <= test_cut)].copy()
test_df = df[df["date"] > test_cut].copy()

exclude = {"date","place_id","item_id","quantity_sold","modal_price","item_price"}
feat = [c for c in df.columns if c not in exclude]
print(f"Features: {len(feat)}  Train: {len(train_df):,}  Val: {len(val_df):,}  Test: {len(test_df):,}")

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
test_prices = test_df["item_price"].values.astype(np.float32)
test_items = test_df["item_id"].values

# ==================== TRAIN ====================
t3 = time.time()
print("\nTraining XGB-GPU (store features)...")
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

# MAE on test (base predictions, no buffer)
val_mae = float(np.mean(np.abs(pred_val - y_val)))
test_mae = float(np.mean(np.abs(pred_test - y_test)))
print(f"Val MAE (base pred): {val_mae:.4f}")
print(f"Test MAE (base pred): {test_mae:.4f}")

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

val_groups = np.array([group_of(i) for i in val_items])
test_groups = np.array([group_of(i) for i in test_items])

# ==================== TUNE ON VAL ====================
print("\n" + "="*70)
print("TUNING BUFFERS ON VAL")
print("="*70)

def flat_loss(buf):
    return cost_fn(y_val, pred_val * buf, val_prices, val_items)
res = minimize_scalar(flat_loss, bounds=(1.0, 10.0), method="bounded")
flat_buf = float(res.x)

groups = ["ultra_fresh","fresh","medium","long_shelf","non_perishable"]
group_buf = {}
for g in groups:
    mask = val_groups == g
    if mask.sum() < 50:
        group_buf[g] = flat_buf
        continue
    def loss(buf):
        return cost_fn(y_val[mask], pred_val[mask] * buf, val_prices[mask], val_items[mask])
    res = minimize_scalar(loss, bounds=(1.0, 10.0), method="bounded")
    group_buf[g] = float(res.x)
    print(f"  {g:18s}: val_buf={res.x:.3f}")

# ==================== EVAL ON TEST ====================
print("\n" + "="*70)
print("FINAL TEST EVALUATION")
print("="*70)

c_140 = cost_fn(y_test, pred_test * 1.40, test_prices, test_items)
c_flat = cost_fn(y_test, pred_test * flat_buf, test_prices, test_items)

pg_pred = pred_test.copy()
for g, b in group_buf.items():
    mask = test_groups == g
    pg_pred[mask] = pred_test[mask] * b
c_group = cost_fn(y_test, pg_pred, test_prices, test_items)

print(f"Baseline (flat 1.40):         {c_140:>14,.0f} DKK")
print(f"Flat tuned ({flat_buf:.2f}):           {c_flat:>14,.0f} DKK  ({(c_flat/c_140-1)*100:+.2f}%)")
print(f"Per-group (val-tuned):        {c_group:>14,.0f} DKK  ({(c_group/c_140-1)*100:+.2f}%)")
print()
print(f"vs CLEAN baseline (5,906,055 DKK without store feats):")
print(f"  delta = {(c_group - 5906055):+,.0f} DKK  ({(c_group/5906055 - 1)*100:+.2f}%)")

# Feature importance
print("\n" + "="*70)
print("FEATURE IMPORTANCE (top 20)")
print("="*70)
importances = pd.DataFrame({"feature": feat, "importance": model.feature_importances_}).sort_values("importance", ascending=False)
for _, r in importances.head(20).iterrows():
    print(f"  {r['feature']:25s}  {r['importance']:.4f}")

# Save
out = {
    "flat_buf": flat_buf,
    "group_buf": group_buf,
    "test_cost_baseline_140": float(c_140),
    "test_cost_flat_tuned": float(c_flat),
    "test_cost_per_group": float(c_group),
    "val_mae_base": val_mae,
    "test_mae_base": test_mae,
    "num_features": len(feat),
    "store_features_added": store_feat_cols,
    "feature_importance": importances.to_dict("records"),
}
with open(RESULTS_DIR / "store_feats_results.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved: {RESULTS_DIR / 'store_feats_results.json'}")
print(f"Total: {time.time()-t0:.1f}s")
