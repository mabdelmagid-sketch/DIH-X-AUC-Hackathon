"""
Test TFT, N-HiTS, DeepAR via the `darts` library.
These are the remaining models we promised to try but didn't.

TFT: uses exogenous features (static + time-varying); most likely to compete with XGB
N-HiTS: specialized neural time-series architecture, strong on M4/M5
DeepAR: probabilistic RNN, gives distributional forecasts
"""
import os, json, sqlite3, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import torch
warnings.filterwarnings("ignore")

# Install darts if needed
try:
    import darts
except ImportError:
    os.system("pip install -q darts 2>&1 | tail -2")
    import darts

from darts import TimeSeries
from darts.models import TFTModel, NHiTSModel, RNNModel
from darts.dataprocessing.transformers import Scaler

DB_PATH = "data/raw/production.db"
SHELF_LIFE_PATH = "data/raw/production_shelf_life_final.csv"
LOCAL_BASE = "/home/yahyahammoudeh/Documents/loving loyalty internship"
if os.path.exists(os.path.join(LOCAL_BASE, DB_PATH)):
    DB_PATH = os.path.join(LOCAL_BASE, DB_PATH)
    SHELF_LIFE_PATH = os.path.join(LOCAL_BASE, SHELF_LIFE_PATH)

RESULTS_DIR = Path("results_darts")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30; TEST_DAYS = 14; VAL_DAYS = 14
WASTE_FRACTION = 0.3; STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30; SEED = 42; NON_FOOD_SHELF_LIFE = 9999.0
CONTEXT_LEN = 64
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Limit to top pairs to keep runtime reasonable (darts is per-series)
MAX_SERIES = 1500  # out of 12k total pairs; sample biggest-selling

print("="*70 + f"\nDARTS MODELS (TFT / N-HiTS / DeepAR)  device={DEVICE}\n" + "="*70)
t0 = time.time()

# Load
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

# Build per-pair series
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
print(f"Data loaded: {len(df):,} rows, {len(pairs)} pairs, {time.time()-t0:.1f}s")

# Pick top MAX_SERIES by total sales
pair_totals = daily.groupby(["place_id","item_id"], observed=True)["quantity_sold"].sum().sort_values(ascending=False)
selected_pairs = pair_totals.head(MAX_SERIES).index.tolist()
selected_set = set(selected_pairs)
df_sub = df[df.apply(lambda r: (r["place_id"], r["item_id"]) in selected_set, axis=1)].copy()
print(f"Subsampled to {len(selected_pairs)} high-volume series ({len(df_sub):,} rows)")

# Build TimeSeries objects
t_ts = time.time()
series_list = []
series_meta = []
for (pid, iid), g in df_sub.groupby(["place_id","item_id"], observed=True, sort=False):
    g = g.sort_values("date")
    if len(g) < CONTEXT_LEN + TEST_DAYS + VAL_DAYS + 7:
        continue
    ts = TimeSeries.from_times_and_values(g["date"], g["quantity_sold"].astype(np.float32).values)
    series_list.append(ts)
    series_meta.append({
        "place_id": pid, "item_id": iid,
        "price": float(g["item_price"].iloc[0]),
        "shelf_days": SHELF_LOOKUP.get(str(iid), (3.0, 1.0))[0],
    })
print(f"Built {len(series_list)} TimeSeries in {time.time()-t_ts:.1f}s")

# Train/val/test split at the series level
max_date = df_sub["date"].max()
test_start = max_date - pd.Timedelta(days=TEST_DAYS - 1)
val_start = test_start - pd.Timedelta(days=VAL_DAYS)

train_series = [s.drop_after(pd.Timestamp(val_start)) for s in series_list]
val_series = [s.slice(pd.Timestamp(val_start), pd.Timestamp(test_start) - pd.Timedelta(days=1)) for s in series_list]
test_series = [s.slice(pd.Timestamp(test_start), pd.Timestamp(max_date)) for s in series_list]

# Scale (fit on train, apply to all)
scaler = Scaler()
train_scaled = scaler.fit_transform(train_series)
val_scaled = scaler.transform(val_series)
test_scaled = scaler.transform(test_series)

print(f"Split: train={len(train_scaled[0])}d, val={len(val_scaled[0])}d, test={len(test_scaled[0])}d")

# ==================== COST FUNCTION ====================
def cost_fn(actual, pred, prices, shelf_days):
    a = np.asarray(actual, dtype=float); p = np.asarray(pred, dtype=float)
    pr = np.asarray(prices, dtype=float)
    wf = np.array([
        (0.0 if sd >= NON_FOOD_SHELF_LIFE else WASTE_FRACTION * min(1.0, 1.0 / max(sd, 0.5)))
        for sd in shelf_days])
    over = np.maximum(p - a, 0); under = np.maximum(a - p, 0)
    return (over * pr * wf).sum() + STOCKOUT_MULTIPLIER * (under * pr).sum()

# ==================== COMMON TRAINING CONFIG ====================
def make_trainer_kwargs():
    return {
        "accelerator": "gpu" if DEVICE == "cuda" else "cpu",
        "enable_progress_bar": False, "enable_model_summary": False,
    }

results = {}

# ==================== TFT ====================
print("\n" + "="*70 + "\nTFT (Temporal Fusion Transformer)\n" + "="*70)
try:
    t_tft = time.time()
    tft = TFTModel(
        input_chunk_length=CONTEXT_LEN, output_chunk_length=TEST_DAYS,
        hidden_size=32, lstm_layers=1, num_attention_heads=4,
        dropout=0.1, batch_size=256, n_epochs=10,
        random_state=SEED, pl_trainer_kwargs=make_trainer_kwargs(),
        add_relative_index=True,
    )
    tft.fit(train_scaled, verbose=False)
    print(f"  TFT trained: {time.time()-t_tft:.1f}s")

    t_pred = time.time()
    preds_scaled = tft.predict(n=TEST_DAYS, series=train_scaled, verbose=False)
    preds = scaler.inverse_transform(preds_scaled)
    print(f"  TFT predict: {time.time()-t_pred:.1f}s")

    all_actual, all_pred, all_price, all_shelf = [], [], [], []
    for i, pred in enumerate(preds):
        actual = test_series[i].values().flatten()
        p = np.clip(pred.values().flatten(), 0, None)
        m = min(len(actual), len(p))
        all_actual.extend(actual[:m]); all_pred.extend(p[:m])
        all_price.extend([series_meta[i]["price"]] * m)
        all_shelf.extend([series_meta[i]["shelf_days"]] * m)
    all_actual = np.array(all_actual); all_pred = np.array(all_pred)
    all_price = np.array(all_price); all_shelf = np.array(all_shelf)
    mae = float(np.mean(np.abs(all_pred - all_actual)))

    buf_results = {}
    for buf in [1.0, 1.4, 2.0, 2.5, 3.0, 4.0]:
        c = cost_fn(all_actual, all_pred * buf, all_price, all_shelf)
        buf_results[f"buf_{buf:.1f}"] = float(c)
        print(f"  buf={buf:.1f}  cost={c:,.0f}")
    results["TFT"] = {"mae": mae, "buffer_sweep": buf_results, "train_seconds": time.time()-t_tft}
except Exception as e:
    print(f"  TFT failed: {type(e).__name__}: {e}")
    results["TFT"] = {"error": str(e)}

# ==================== N-HiTS ====================
print("\n" + "="*70 + "\nN-HiTS\n" + "="*70)
try:
    t_nh = time.time()
    nhits = NHiTSModel(
        input_chunk_length=CONTEXT_LEN, output_chunk_length=TEST_DAYS,
        num_stacks=3, num_blocks=1, num_layers=2, layer_widths=256,
        batch_size=256, n_epochs=10,
        random_state=SEED, pl_trainer_kwargs=make_trainer_kwargs(),
    )
    nhits.fit(train_scaled, verbose=False)
    print(f"  N-HiTS trained: {time.time()-t_nh:.1f}s")

    preds_scaled = nhits.predict(n=TEST_DAYS, series=train_scaled, verbose=False)
    preds = scaler.inverse_transform(preds_scaled)
    all_actual, all_pred, all_price, all_shelf = [], [], [], []
    for i, pred in enumerate(preds):
        actual = test_series[i].values().flatten()
        p = np.clip(pred.values().flatten(), 0, None)
        m = min(len(actual), len(p))
        all_actual.extend(actual[:m]); all_pred.extend(p[:m])
        all_price.extend([series_meta[i]["price"]] * m)
        all_shelf.extend([series_meta[i]["shelf_days"]] * m)
    all_actual = np.array(all_actual); all_pred = np.array(all_pred)
    all_price = np.array(all_price); all_shelf = np.array(all_shelf)
    mae = float(np.mean(np.abs(all_pred - all_actual)))

    buf_results = {}
    for buf in [1.0, 1.4, 2.0, 2.5, 3.0, 4.0]:
        c = cost_fn(all_actual, all_pred * buf, all_price, all_shelf)
        buf_results[f"buf_{buf:.1f}"] = float(c)
        print(f"  buf={buf:.1f}  cost={c:,.0f}")
    results["NHiTS"] = {"mae": mae, "buffer_sweep": buf_results, "train_seconds": time.time()-t_nh}
except Exception as e:
    print(f"  N-HiTS failed: {type(e).__name__}: {e}")
    results["NHiTS"] = {"error": str(e)}

# ==================== DeepAR (RNNModel with DeepAR style) ====================
print("\n" + "="*70 + "\nDeepAR (RNN)\n" + "="*70)
try:
    t_dar = time.time()
    deepar = RNNModel(
        input_chunk_length=CONTEXT_LEN, model="LSTM",
        hidden_dim=64, n_rnn_layers=2, dropout=0.1,
        batch_size=256, n_epochs=10, training_length=CONTEXT_LEN + TEST_DAYS,
        random_state=SEED, pl_trainer_kwargs=make_trainer_kwargs(),
    )
    deepar.fit(train_scaled, verbose=False)
    print(f"  DeepAR trained: {time.time()-t_dar:.1f}s")

    preds_scaled = deepar.predict(n=TEST_DAYS, series=train_scaled, verbose=False)
    preds = scaler.inverse_transform(preds_scaled)
    all_actual, all_pred, all_price, all_shelf = [], [], [], []
    for i, pred in enumerate(preds):
        actual = test_series[i].values().flatten()
        p = np.clip(pred.values().flatten(), 0, None)
        m = min(len(actual), len(p))
        all_actual.extend(actual[:m]); all_pred.extend(p[:m])
        all_price.extend([series_meta[i]["price"]] * m)
        all_shelf.extend([series_meta[i]["shelf_days"]] * m)
    all_actual = np.array(all_actual); all_pred = np.array(all_pred)
    all_price = np.array(all_price); all_shelf = np.array(all_shelf)
    mae = float(np.mean(np.abs(all_pred - all_actual)))

    buf_results = {}
    for buf in [1.0, 1.4, 2.0, 2.5, 3.0, 4.0]:
        c = cost_fn(all_actual, all_pred * buf, all_price, all_shelf)
        buf_results[f"buf_{buf:.1f}"] = float(c)
        print(f"  buf={buf:.1f}  cost={c:,.0f}")
    results["DeepAR"] = {"mae": mae, "buffer_sweep": buf_results, "train_seconds": time.time()-t_dar}
except Exception as e:
    print(f"  DeepAR failed: {type(e).__name__}: {e}")
    results["DeepAR"] = {"error": str(e)}

print("\n" + "="*70 + "\nSUMMARY\n" + "="*70)
print(f"{'Model':<10}  {'MAE':>6}  {'Best cost':>14}  {'Best buf':>8}  {'Train(s)':>8}")
for name, r in results.items():
    if "error" in r:
        print(f"{name:<10}  ERROR: {r['error'][:50]}")
        continue
    best = min(r["buffer_sweep"].items(), key=lambda kv: kv[1])
    print(f"{name:<10}  {r['mae']:>6.3f}  {best[1]:>14,.0f}  {best[0]:>8}  {r['train_seconds']:>8.1f}")

# Note: these are on MAX_SERIES=1500 subset, so costs not directly comparable
# Scale up: cost_full ≈ cost_sub × (12348 / 1500)
print(f"\nNote: costs are on {MAX_SERIES}-series subset. Full-dataset estimate ≈ cost × {12348/MAX_SERIES:.1f}")

out = {"results": results, "max_series": MAX_SERIES, "scale_factor": 12348/MAX_SERIES}
with open(RESULTS_DIR / "darts_results.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved. Total: {time.time()-t0:.1f}s")
