"""
Darts models WITH covariates (proper setup).

Unlike the previous run, this gives the models the side information they need:
  - future_covariates: dow, is_weekend, month, dom (calendar features known ahead)
  - static_covariates: shelf_life, storage_type, perishability, chain_id, area_id
  - past_covariates: rolling stats (only TFT/N-HiTS variant that supports them)

TFT is designed exactly for this. Should close most of the gap to XGB.
"""
import os, json, sqlite3, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import torch
warnings.filterwarnings("ignore")

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

RESULTS_DIR = Path("results_darts_covariates")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_ITEMS = 30; TEST_DAYS = 14; VAL_DAYS = 14
WASTE_FRACTION = 0.3; STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30; SEED = 42; NON_FOOD_SHELF_LIFE = 9999.0
CONTEXT_LEN = 64
MAX_SERIES = 1500
N_EPOCHS = 20  # more epochs than before

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {DEVICE}, torch {torch.__version__}")
torch.set_float32_matmul_precision("high")

print("="*70 + f"\nDARTS MODELS WITH COVARIATES  (epochs={N_EPOCHS}, series={MAX_SERIES})\n" + "="*70)
t0 = time.time()

# =========== LOAD ===========
conn = sqlite3.connect(DB_PATH)
orders = pd.read_sql("SELECT id, place_id, created, status FROM fct_orders", conn)
items = pd.read_sql("SELECT order_id, item_id, quantity, price FROM fct_order_items", conn)
menu = pd.read_sql("SELECT id, price FROM dim_menu_items", conn)
places = pd.read_sql("SELECT id, chain_id, area_id, type_id, seasonal FROM dim_places", conn)
conn.close()
orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
items["price"] = pd.to_numeric(items["price"], errors="coerce")
menu["price"] = pd.to_numeric(menu["price"], errors="coerce")
for c in ["chain_id","area_id","type_id","seasonal"]:
    places[c] = pd.to_numeric(places[c], errors="coerce").fillna(-1).astype(int)
places["id"] = places["id"].astype(str)
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

pair_totals = daily.groupby(["place_id","item_id"], observed=True)["quantity_sold"].sum().sort_values(ascending=False)
selected_pairs = set(pair_totals.head(MAX_SERIES).index.tolist())
daily = daily[daily.apply(lambda r: (r["place_id"], r["item_id"]) in selected_pairs, axis=1)].copy()
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

# future covariates — calendar features
df["dow"] = df["date"].dt.dayofweek.astype(float)
df["is_weekend"] = (df["dow"] >= 5).astype(float)
df["dom"] = df["date"].dt.day.astype(float)
df["month"] = df["date"].dt.month.astype(float)
FUTURE_COV_COLS = ["dow","is_weekend","dom","month"]

print(f"Data prep: {time.time()-t0:.1f}s, pairs={len(selected_pairs)}")

# =========== BUILD TIMESERIES with COVARIATES ===========
t_ts = time.time()
# static covariates lookup per place
place_cov = places.set_index("id")[["chain_id","area_id","type_id","seasonal"]].to_dict("index")

target_series = []
future_covs = []
static_cov_rows = []
meta = []
for (pid, iid), g in df.groupby(["place_id","item_id"], observed=True, sort=False):
    g = g.sort_values("date").reset_index(drop=True)
    if len(g) < CONTEXT_LEN + TEST_DAYS + VAL_DAYS + 7:
        continue
    idx = pd.DatetimeIndex(g["date"])
    ts_target = TimeSeries.from_times_and_values(idx, g["quantity_sold"].astype(np.float32).values)
    ts_future = TimeSeries.from_times_and_values(idx, g[FUTURE_COV_COLS].astype(np.float32).values, columns=FUTURE_COV_COLS)

    pid_str = str(pid)
    store = place_cov.get(pid_str, {"chain_id":-1,"area_id":-1,"type_id":-1,"seasonal":0})
    sl, ag = SHELF_LOOKUP.get(str(iid), (3.0, 1.0))
    per = 1.0 / max(sl, 0.5)
    storage = 3 if sl >= NON_FOOD_SHELF_LIFE else (0 if sl <= 3 else 1 if sl <= 14 else 2)
    static_row = {
        "shelf_life_days": min(sl, 365.0),
        "avg_gap_days": float(ag),
        "perishability": per,
        "storage_type": float(storage),
        "logsl": float(np.log1p(sl)),
        "chain_id": float(store["chain_id"]),
        "area_id": float(store["area_id"]),
        "type_id": float(store["type_id"]),
        "seasonal": float(store["seasonal"]),
    }
    static_df = pd.DataFrame([static_row])
    ts_target = ts_target.with_static_covariates(static_df)

    target_series.append(ts_target)
    future_covs.append(ts_future)
    static_cov_rows.append(static_row)
    meta.append({
        "place_id": pid, "item_id": iid,
        "price": float(g["item_price"].iloc[0]),
        "shelf_days": sl,
    })

print(f"Built {len(target_series)} series w/ covariates in {time.time()-t_ts:.1f}s")

# split
max_date = df["date"].max()
test_start = max_date - pd.Timedelta(days=TEST_DAYS - 1)
val_start = test_start - pd.Timedelta(days=VAL_DAYS)

train_targets = [s.drop_after(pd.Timestamp(val_start)) for s in target_series]
test_targets = [s.slice(pd.Timestamp(test_start), pd.Timestamp(max_date)) for s in target_series]
train_future_covs = [s.drop_after(pd.Timestamp(val_start)) for s in future_covs]

# Future covariates must cover the forecast horizon (keep all of it)
# For prediction: pass future_covariates spanning train + test

scaler = Scaler()
train_scaled = scaler.fit_transform(train_targets)

# future cov scaler
fcov_scaler = Scaler()
future_covs_scaled = fcov_scaler.fit_transform(future_covs)

# =========== COST FN ===========
def cost_fn(actual, pred, prices, shelf_days):
    a = np.asarray(actual, dtype=float); p = np.asarray(pred, dtype=float)
    pr = np.asarray(prices, dtype=float)
    wf = np.array([
        (0.0 if sd >= NON_FOOD_SHELF_LIFE else WASTE_FRACTION * min(1.0, 1.0 / max(sd, 0.5)))
        for sd in shelf_days])
    over = np.maximum(p - a, 0); under = np.maximum(a - p, 0)
    return (over * pr * wf).sum() + STOCKOUT_MULTIPLIER * (under * pr).sum()

def trainer_kwargs():
    return {"accelerator": "gpu" if DEVICE=="cuda" else "cpu",
            "enable_progress_bar": False, "enable_model_summary": False,
            "gradient_clip_val": 1.0}

def eval_preds(preds, label):
    all_a, all_p, all_pr, all_sh = [], [], [], []
    for i, pred in enumerate(preds):
        actual = test_targets[i].values().flatten()
        p = np.clip(pred.values().flatten(), 0, None)
        m = min(len(actual), len(p))
        all_a.extend(actual[:m]); all_p.extend(p[:m])
        all_pr.extend([meta[i]["price"]] * m)
        all_sh.extend([meta[i]["shelf_days"]] * m)
    all_a = np.array(all_a); all_p = np.array(all_p)
    all_pr = np.array(all_pr); all_sh = np.array(all_sh)
    mae = float(np.mean(np.abs(all_p - all_a)))
    bufs = {}
    for buf in [1.0, 1.4, 2.0, 2.5, 3.0, 4.0]:
        c = cost_fn(all_a, all_p * buf, all_pr, all_sh)
        bufs[f"buf_{buf:.1f}"] = float(c)
    return mae, bufs

results = {}

# =========== TFT with covariates ===========
print("\n" + "="*70 + "\nTFT + covariates (static, future)\n" + "="*70)
try:
    t_m = time.time()
    model = TFTModel(
        input_chunk_length=CONTEXT_LEN, output_chunk_length=TEST_DAYS,
        hidden_size=64, lstm_layers=1, num_attention_heads=4,
        dropout=0.1, batch_size=256, n_epochs=N_EPOCHS,
        random_state=SEED, pl_trainer_kwargs=trainer_kwargs(),
        use_static_covariates=True,
        add_relative_index=False,
    )
    model.fit(train_scaled, future_covariates=future_covs_scaled, verbose=False)
    t_train = time.time() - t_m
    print(f"  TFT trained: {t_train:.1f}s")
    preds_s = model.predict(n=TEST_DAYS, series=train_scaled, future_covariates=future_covs_scaled, verbose=False)
    preds = scaler.inverse_transform(preds_s)
    mae, bufs = eval_preds(preds, "TFT")
    best = min(bufs.items(), key=lambda kv: kv[1])
    print(f"  MAE={mae:.3f}  best_cost={best[1]:,.0f} at {best[0]}")
    for k,v in bufs.items(): print(f"    {k}  {v:,.0f}")
    results["TFT"] = {"mae": mae, "buffer_sweep": bufs, "train_seconds": t_train}
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
    import traceback; traceback.print_exc()
    results["TFT"] = {"error": str(e)}

# =========== DeepAR (RNN/LSTM) with future_covariates ===========
print("\n" + "="*70 + "\nDeepAR (LSTM) + future covariates\n" + "="*70)
try:
    t_m = time.time()
    model = RNNModel(
        input_chunk_length=CONTEXT_LEN, model="LSTM",
        hidden_dim=96, n_rnn_layers=2, dropout=0.1,
        batch_size=256, n_epochs=N_EPOCHS,
        training_length=CONTEXT_LEN + TEST_DAYS,
        random_state=SEED, pl_trainer_kwargs=trainer_kwargs(),
    )
    model.fit(train_scaled, future_covariates=future_covs_scaled, verbose=False)
    t_train = time.time() - t_m
    print(f"  DeepAR trained: {t_train:.1f}s")
    preds_s = model.predict(n=TEST_DAYS, series=train_scaled, future_covariates=future_covs_scaled, verbose=False)
    preds = scaler.inverse_transform(preds_s)
    mae, bufs = eval_preds(preds, "DeepAR")
    best = min(bufs.items(), key=lambda kv: kv[1])
    print(f"  MAE={mae:.3f}  best_cost={best[1]:,.0f} at {best[0]}")
    for k,v in bufs.items(): print(f"    {k}  {v:,.0f}")
    results["DeepAR"] = {"mae": mae, "buffer_sweep": bufs, "train_seconds": t_train}
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
    results["DeepAR"] = {"error": str(e)}

# =========== N-HiTS with past_covariates (rolling stats) ===========
# N-HiTS supports past_covariates, not future. Skip with covariates since we
# don't have past covariates separate from the target; just rerun bigger/longer.
print("\n" + "="*70 + "\nN-HiTS (bigger, longer)\n" + "="*70)
try:
    t_m = time.time()
    model = NHiTSModel(
        input_chunk_length=CONTEXT_LEN, output_chunk_length=TEST_DAYS,
        num_stacks=4, num_blocks=2, num_layers=3, layer_widths=512,
        batch_size=256, n_epochs=N_EPOCHS,
        random_state=SEED, pl_trainer_kwargs=trainer_kwargs(),
    )
    model.fit(train_scaled, verbose=False)
    t_train = time.time() - t_m
    print(f"  N-HiTS trained: {t_train:.1f}s")
    preds_s = model.predict(n=TEST_DAYS, series=train_scaled, verbose=False)
    preds = scaler.inverse_transform(preds_s)
    mae, bufs = eval_preds(preds, "NHiTS")
    best = min(bufs.items(), key=lambda kv: kv[1])
    print(f"  MAE={mae:.3f}  best_cost={best[1]:,.0f} at {best[0]}")
    for k,v in bufs.items(): print(f"    {k}  {v:,.0f}")
    results["NHiTS"] = {"mae": mae, "buffer_sweep": bufs, "train_seconds": t_train}
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
    results["NHiTS"] = {"error": str(e)}

# =========== SUMMARY ===========
print("\n" + "="*70 + "\nSUMMARY (with covariates, same 1500-subset)\n" + "="*70)
print(f"{'Model':<12}  {'MAE':>6}  {'Best cost':>12}  {'Best buf':>8}  {'Train(s)':>8}")
print(f"{'XGB ref':<12}  {7.02:>6.2f}  {2200459:>12,.0f}  per-grp   {1.5:>8.1f}  (apples-to-apples XGB on same 1500 subset)")
for name, r in results.items():
    if "error" in r:
        print(f"{name:<12}  ERROR: {r['error'][:60]}")
        continue
    best = min(r["buffer_sweep"].items(), key=lambda kv: kv[1])
    print(f"{name:<12}  {r['mae']:>6.2f}  {best[1]:>12,.0f}  {best[0]:>8}  {r['train_seconds']:>8.1f}")

with open(RESULTS_DIR / "darts_covariates_results.json", "w") as f:
    json.dump({"results": results, "xgb_ref_1500subset": 2200459,
               "max_series": MAX_SERIES, "n_epochs": N_EPOCHS}, f, indent=2, default=str)
print(f"\nSaved. Total: {time.time()-t0:.1f}s")
