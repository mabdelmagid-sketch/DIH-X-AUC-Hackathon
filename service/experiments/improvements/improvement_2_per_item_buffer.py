"""
Improvement 2: Per-item buffer optimization.

Instead of a flat safety_buffer=1.40 for all items, assign different buffers
based on item characteristics. The key insight:

  - Short-shelf perishable items (salad, 1d): stockout is 1.5x worse than waste,
    but waste fraction is HIGH (0.30). A moderate buffer is optimal.
  - Long-shelf items (beer, 365d): waste fraction is near-zero (0.006).
    A HIGHER buffer costs almost nothing extra but prevents stockouts.
  - Medium-shelf items (cheese, 14d): intermediate behavior.

This script:
1. Trains LightGBM with shelf features (from improvement 1)
2. Gets raw predictions
3. Optimizes buffer PER shelf-life group to minimize total business cost
4. Compares flat buffer vs per-group buffer

Usage: Run cells in order in Colab. Requires production.db + shelf life CSV.
"""

import os
import sys
import time
import json
import sqlite3
import warnings
import inspect
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
from tqdm.auto import tqdm
from scipy.optimize import minimize_scalar

from sklearn.preprocessing import LabelEncoder
import lightgbm as lgb

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", "{:.2f}".format)

import gc

print("All imports OK")

# ============================================================================
# CONFIG
# ============================================================================
DB_PATH = "data/raw/production.db"
SHELF_LIFE_PATH = "data/raw/production_shelf_life_final.csv"

LOCAL_BASE = "/home/yahyahammoudeh/Documents/loving loyalty internship"
if os.path.exists(os.path.join(LOCAL_BASE, DB_PATH)):
    DB_PATH = os.path.join(LOCAL_BASE, DB_PATH)
    SHELF_LIFE_PATH = os.path.join(LOCAL_BASE, SHELF_LIFE_PATH)

RESULTS_DIR = Path("results_per_item_buffer")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

assert os.path.exists(DB_PATH), f"Database not found at {DB_PATH}"
print(f"Database: {DB_PATH}")

# ============================================================================
# CONSTANTS
# ============================================================================
TOP_N_ITEMS = 30
TEST_DAYS = 14
WASTE_FRACTION = 0.3
STOCKOUT_MULTIPLIER = 1.5
MIN_STORE_DAYS = 30
SEED = 42

# ============================================================================
# LOAD DATA
# ============================================================================
def load_production_data(db_path):
    t0 = time.time()
    conn = sqlite3.connect(db_path)
    orders = pd.read_sql("SELECT id, place_id, created, status, total_amount FROM fct_orders", conn)
    items = pd.read_sql("SELECT id, item_id, order_id, quantity, cost, price, title FROM fct_order_items", conn)
    menu = pd.read_sql("SELECT id, title, price FROM dim_menu_items", conn)
    places = pd.read_sql("SELECT id, title, active FROM dim_places", conn)
    conn.close()

    orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
    orders["total_amount"] = pd.to_numeric(orders["total_amount"], errors="coerce")
    items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
    items["cost"] = pd.to_numeric(items["cost"], errors="coerce")
    items["price"] = pd.to_numeric(items["price"], errors="coerce")
    menu["price"] = pd.to_numeric(menu["price"], errors="coerce")

    orders = orders[orders["status"] == "Closed"].copy()
    orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
    orders = orders.dropna(subset=["created_dt"])
    orders["date"] = orders["created_dt"].dt.normalize()

    print(f"Date range: {orders['date'].min().date()} to {orders['date'].max().date()}")
    print(f"Load time: {time.time()-t0:.1f}s")
    return orders, items, menu, places

orders, items, menu, places = load_production_data(DB_PATH)

# ============================================================================
# SHELF LIFE
# ============================================================================
shelf_df = pd.read_csv(SHELF_LIFE_PATH)
SHELF_LOOKUP = {}
for _, row in shelf_df.iterrows():
    iid = str(row["item_id"])
    sl = float(row["shelf_life_days"]) if pd.notna(row["shelf_life_days"]) else 3.0
    ag = float(row["avg_gap_days"]) if pd.notna(row["avg_gap_days"]) else 1.0
    SHELF_LOOKUP[iid] = (sl, ag)

perishability_map = {"high": 2, "medium": 1, "low": 0}
storage_map = {"refrigerated": 2, "frozen": 1, "ambient": 0, "dry": 0}
SHELF_FEATURES = {}
for _, row in shelf_df.iterrows():
    iid = str(row["item_id"])
    sl = float(row["shelf_life_days"]) if pd.notna(row["shelf_life_days"]) else 3.0
    ag = float(row["avg_gap_days"]) if pd.notna(row["avg_gap_days"]) else 1.0
    perish = perishability_map.get(str(row.get("perishability", "low")), 0)
    storage = storage_map.get(str(row.get("storage_type", "dry")), 0)
    if sl >= 9999:
        ewf = 0.0
    else:
        ewf = WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))
    SHELF_FEATURES[iid] = {
        "shelf_life_days": sl, "avg_gap_days": ag, "perishability": perish,
        "storage_type": storage, "effective_waste_frac": ewf,
        "log_shelf_life": np.log1p(sl), "turnover_ratio": min(ag / max(sl, 0.5), 5.0),
    }

# Assign shelf-life GROUP for buffer optimization
# Groups: ultra-fresh (<=3d), fresh (4-14d), medium (15-90d), long (91-365d), non-perishable (>365d)
def get_shelf_group(item_id):
    sl, _ = SHELF_LOOKUP.get(str(item_id), (3.0, 1.0))
    if sl <= 3:
        return "ultra_fresh"
    elif sl <= 14:
        return "fresh"
    elif sl <= 90:
        return "medium"
    elif sl <= 365:
        return "long_shelf"
    else:
        return "non_perishable"

def effective_waste_fraction(item_id):
    sl, ag = SHELF_LOOKUP.get(str(item_id), (3.0, 1.0))
    if sl >= 9999:
        return 0.0
    return WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))

print(f"Shelf life lookup: {len(SHELF_LOOKUP)} items")

# ============================================================================
# PREPARE DAILY DEMAND
# ============================================================================
def prepare_daily_demand(orders, items, menu):
    t0 = time.time()
    merged = items[["item_id", "order_id", "quantity", "cost"]].merge(
        orders[["id", "place_id", "date"]],
        left_on="order_id", right_on="id", how="inner",
    )
    merged.drop(columns=["id"], inplace=True)

    daily = (
        merged.groupby(["date", "place_id", "item_id"], observed=True)
        .agg(quantity_sold=("quantity", "sum"), revenue=("cost", "sum"))
        .reset_index()
    )
    del merged

    item_prices = menu[["id", "price"]].drop_duplicates(subset=["id"]).rename(
        columns={"id": "item_id", "price": "item_price"}
    )
    daily = daily.merge(item_prices, on="item_id", how="left")
    daily["item_price"] = daily["item_price"].fillna(75.0)

    store_date_counts = daily.groupby("place_id")["date"].nunique()
    active_stores = store_date_counts[store_date_counts >= MIN_STORE_DAYS].index
    daily = daily[daily["place_id"].isin(active_stores)].copy()

    top = (
        daily.groupby(["place_id", "item_id"], observed=True)["quantity_sold"]
        .sum().reset_index()
        .sort_values(["place_id", "quantity_sold"], ascending=[True, False])
        .groupby("place_id").head(TOP_N_ITEMS)
    )
    top_keys = top[["place_id", "item_id"]]
    daily = daily.merge(top_keys, on=["place_id", "item_id"], how="inner")

    modal_prices = daily.groupby(["place_id", "item_id"], observed=True)["item_price"].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 75.0
    ).reset_index().rename(columns={"item_price": "modal_price"})

    min_date, max_date = daily["date"].min(), daily["date"].max()
    all_dates = pd.date_range(min_date, max_date, freq="D")

    dates_df = pd.DataFrame({"date": all_dates, "_key": 1})
    pairs_df = top_keys.copy()
    pairs_df["_key"] = 1
    full = pairs_df.merge(dates_df, on="_key").drop(columns=["_key"])

    full = full.merge(
        daily[["date", "place_id", "item_id", "quantity_sold", "revenue"]],
        on=["date", "place_id", "item_id"], how="left",
    )
    full = full.merge(modal_prices, on=["place_id", "item_id"], how="left")
    full.rename(columns={"modal_price": "item_price"}, inplace=True)
    full["item_price"] = full["item_price"].fillna(75.0)
    full["quantity_sold"] = full["quantity_sold"].fillna(0)
    full["revenue"] = full["revenue"].fillna(0)
    full = full.sort_values(["place_id", "item_id", "date"]).reset_index(drop=True)

    del daily
    print(f"Complete grid: {len(full):,} rows, {len(all_dates)} days")
    print(f"Prep time: {time.time()-t0:.1f}s")
    return full, all_dates

daily_full, all_dates = prepare_daily_demand(orders, items, menu)
del orders, items, menu, places; gc.collect()

# ============================================================================
# FEATURE ENGINEERING (with shelf features from improvement 1)
# ============================================================================
def engineer_features(df):
    t0 = time.time()
    df = df.copy()
    grp = ["place_id", "item_id"]

    # Time features
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_of_month"] = df["date"].dt.day
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["day_of_year"] = df["date"].dt.dayofyear
    df["year"] = df["date"].dt.year
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["is_friday"] = (df["day_of_week"] == 4).astype(int)
    df["is_monday"] = (df["day_of_week"] == 0).astype(int)
    df["season"] = df["month"].map(
        {12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3}
    )
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Lag features
    for lag in [1, 7, 14, 28]:
        df[f"demand_lag_{lag}d"] = df.groupby(grp, observed=True)["quantity_sold"].shift(lag)
    df["demand_same_weekday_last_week"] = df.groupby(grp, observed=True)["quantity_sold"].shift(7)

    # Rolling features
    shifted = df.groupby(grp, observed=True)["quantity_sold"].shift(1)
    for window in [7, 14, 30]:
        df[f"rolling_mean_{window}d"] = shifted.groupby(
            [df["place_id"], df["item_id"]], observed=True
        ).transform(lambda x: x.rolling(window, min_periods=1).mean())
    for window in [7, 14]:
        df[f"rolling_std_{window}d"] = shifted.groupby(
            [df["place_id"], df["item_id"]], observed=True
        ).transform(lambda x: x.rolling(window, min_periods=2).std())

    df["demand_same_weekday_avg_4weeks"] = df.groupby(grp, observed=True)[
        "quantity_sold"
    ].transform(lambda x: x.shift(7).rolling(4, min_periods=1).mean())

    df["expanding_mean"] = (
        df.groupby(grp, observed=True)["quantity_sold"]
        .expanding().mean()
        .reset_index(level=[0, 1], drop=True)
    )

    # Trend features
    df["days_since_start"] = (df["date"] - df["date"].min()).dt.days
    df["demand_1w_ago"] = df.groupby(grp, observed=True)["quantity_sold"].shift(7)
    df["demand_2w_ago"] = df.groupby(grp, observed=True)["quantity_sold"].shift(14)
    df["wow_growth"] = (
        ((df["demand_1w_ago"] - df["demand_2w_ago"]) / df["demand_2w_ago"].clip(lower=0.1))
        .clip(-5, 5).fillna(0)
    )
    df["recent_vs_expanding"] = (
        (df["rolling_mean_7d"] / df["expanding_mean"].clip(lower=0.01))
        .clip(0, 10).fillna(1)
    )

    # Demand residual feedback
    exp_mean_shifted = df.groupby(grp, observed=True)["quantity_sold"].transform(
        lambda x: x.shift(2).expanding(min_periods=1).mean()
    )
    df["demand_residual_lag_1d"] = (
        df.groupby(grp, observed=True)["quantity_sold"].shift(1) - exp_mean_shifted
    )
    for lag in [7, 14, 28]:
        df[f"demand_residual_lag_{lag}d"] = df.groupby(grp, observed=True)[
            "demand_residual_lag_1d"
        ].shift(lag - 1)

    resid_grp = df.groupby(grp, observed=True)["demand_residual_lag_1d"]
    df["residual_rolling_mean_7d"] = resid_grp.transform(
        lambda x: x.shift(1).rolling(7, min_periods=2).mean()
    )
    df["residual_rolling_mean_14d"] = resid_grp.transform(
        lambda x: x.shift(1).rolling(14, min_periods=3).mean()
    )
    df["residual_rolling_std_7d"] = resid_grp.transform(
        lambda x: x.shift(1).rolling(7, min_periods=3).std()
    )
    df["residual_dow_mean"] = df.groupby(
        grp + ["day_of_week"], observed=True
    )["demand_residual_lag_1d"].transform(
        lambda x: x.shift(7).expanding(min_periods=1).mean()
    )

    # Fourier harmonics
    for k in [1, 2, 3]:
        df[f"fourier_week_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_week"] / 7)
        df[f"fourier_week_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_week"] / 7)
    for k in [1, 2]:
        df[f"fourier_year_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_year"] / 365.25)
        df[f"fourier_year_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_year"] / 365.25)

    # Danish calendar
    danish_holidays = pd.to_datetime([
        "2025-12-24", "2025-12-25", "2025-12-26", "2025-12-31",
        "2026-01-01", "2026-03-29", "2026-04-02", "2026-04-03",
        "2026-04-05", "2026-04-06",
    ])
    holiday_set = set(danish_holidays.normalize())
    df["is_holiday"] = df["date"].isin(holiday_set).astype(int)

    dates_arr = df["date"].values.astype("datetime64[D]")
    holidays_arr = danish_holidays.values.astype("datetime64[D]")
    chunk_size = 500_000
    days_from = np.empty(len(df), dtype=np.int32)
    for i in range(0, len(df), chunk_size):
        end = min(i + chunk_size, len(df))
        diffs = np.abs((dates_arr[i:end, None] - holidays_arr[None, :]).astype("timedelta64[D]").astype(int))
        days_from[i:end] = diffs.min(axis=1)
    df["days_from_holiday"] = days_from
    df["near_holiday"] = (df["days_from_holiday"] <= 2).astype(int)

    m = df["month"]
    d = df["day_of_month"]
    df["is_school_holiday"] = (
        ((m == 12) & (d >= 20)) | ((m == 1) & (d <= 2)) |
        ((m == 2) & (d >= 8) & (d <= 22)) |
        ((m == 3) & (d >= 28)) | ((m == 4) & (d <= 6))
    ).astype(int)
    df["is_dark_months"] = m.isin([11, 12, 1, 2]).astype(int)
    df["is_christmas_period"] = ((m == 12) & (d <= 26)).astype(int)

    # Categorical encoding
    le_place = LabelEncoder()
    le_item = LabelEncoder()
    df["place_id_encoded"] = le_place.fit_transform(df["place_id"].astype(str))
    df["item_id_encoded"] = le_item.fit_transform(df["item_id"].astype(str))
    df["store_dow_interaction"] = df["place_id_encoded"] * 10 + df["day_of_week"]

    # Store-cluster features
    store_stats = df.groupby("place_id", observed=True).agg(
        store_avg_daily_demand=("quantity_sold", "mean"),
        store_total_volume=("quantity_sold", "sum"),
    ).reset_index()
    store_stats["volume_tier"] = pd.qcut(
        store_stats["store_total_volume"], q=4, labels=[0, 1, 2, 3]
    ).astype(int)

    weekend_ratio = df.groupby(["place_id", "is_weekend"], observed=True)["quantity_sold"].mean().unstack(fill_value=0)
    if 0 in weekend_ratio.columns and 1 in weekend_ratio.columns:
        weekend_ratio["weekend_ratio"] = weekend_ratio[1] / weekend_ratio[0].clip(lower=0.1)
    else:
        weekend_ratio["weekend_ratio"] = 1.0
    weekend_ratio = weekend_ratio[["weekend_ratio"]].reset_index()

    df = df.merge(store_stats[["place_id", "store_avg_daily_demand", "volume_tier"]], on="place_id", how="left")
    df = df.merge(weekend_ratio, on="place_id", how="left")

    # Stub features
    for col in ["temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
                "is_promotion_active", "discount_percentage", "campaign_count"]:
        df[col] = 0
    df["is_open"] = 1

    # Shelf-life features
    item_ids_str = df["item_id"].astype(str)
    defaults = {
        "shelf_life_days": 3.0, "avg_gap_days": 1.0, "perishability": 1,
        "storage_type": 0, "effective_waste_frac": 0.3,
        "log_shelf_life": np.log1p(3.0), "turnover_ratio": 1.0 / 3.0,
    }
    for feat_name, default_val in defaults.items():
        df[feat_name] = item_ids_str.map(
            lambda iid, fn=feat_name, dv=default_val: SHELF_FEATURES.get(iid, defaults).get(fn, dv)
        )
    df["shelf_x_rolling7"] = df["log_shelf_life"] * df["rolling_mean_7d"].fillna(0)
    df["perishable_x_weekend"] = df["perishability"] * df["is_weekend"]
    df["perishable_x_monday"] = df["perishability"] * df["is_monday"]
    df["turnover_x_lag1"] = df["turnover_ratio"] * df["demand_lag_1d"].fillna(0)

    # Shelf group (for per-group buffer optimization)
    df["shelf_group"] = item_ids_str.map(get_shelf_group)

    feature_cols = [
        "day_of_week", "day_of_month", "month", "quarter", "week_of_year",
        "day_of_year", "year", "is_weekend", "is_friday", "is_monday", "season",
        "dow_sin", "dow_cos", "month_sin", "month_cos",
        "demand_lag_1d", "demand_lag_7d", "demand_lag_14d", "demand_lag_28d",
        "demand_same_weekday_last_week", "demand_same_weekday_avg_4weeks",
        "rolling_mean_7d", "rolling_mean_14d", "rolling_mean_30d",
        "rolling_std_7d", "rolling_std_14d", "expanding_mean",
        "demand_residual_lag_1d", "demand_residual_lag_7d",
        "demand_residual_lag_14d", "demand_residual_lag_28d",
        "residual_rolling_mean_7d", "residual_rolling_mean_14d",
        "residual_rolling_std_7d", "residual_dow_mean",
        "days_since_start", "wow_growth", "recent_vs_expanding",
        "fourier_week_sin_1", "fourier_week_cos_1",
        "fourier_week_sin_2", "fourier_week_cos_2",
        "fourier_week_sin_3", "fourier_week_cos_3",
        "fourier_year_sin_1", "fourier_year_cos_1",
        "fourier_year_sin_2", "fourier_year_cos_2",
        "is_holiday", "days_from_holiday", "near_holiday",
        "is_school_holiday", "is_dark_months", "is_christmas_period",
        "temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
        "is_promotion_active", "discount_percentage", "campaign_count", "is_open",
        "place_id_encoded", "item_id_encoded", "store_dow_interaction",
        "store_avg_daily_demand", "volume_tier", "weekend_ratio",
        "shelf_life_days", "avg_gap_days", "perishability", "storage_type",
        "effective_waste_frac", "log_shelf_life", "turnover_ratio",
        "shelf_x_rolling7", "perishable_x_weekend", "perishable_x_monday",
        "turnover_x_lag1",
    ]

    print(f"  Total features: {len(feature_cols)}")
    print(f"  Total time: {time.time()-t0:.0f}s")
    return df, feature_cols

df, feature_cols = engineer_features(daily_full)
del daily_full; gc.collect()

for col in feature_cols:
    if df[col].dtype == np.float64:
        df[col] = df[col].astype(np.float32)
df["quantity_sold"] = df["quantity_sold"].astype(np.float32)
df["item_price"] = df["item_price"].astype(np.float32)
gc.collect()
print(f"\nFinal dataset: {len(df):,} rows, {len(feature_cols)} features")

# ============================================================================
# TRAIN/TEST SPLIT
# ============================================================================
max_date = df["date"].max()
test_cutoff = max_date - pd.Timedelta(days=TEST_DAYS)
BEST_DECAY_HL = 6

train = df[df["date"] <= test_cutoff].copy()
test = df[df["date"] > test_cutoff].copy()

lag_cols = [c for c in feature_cols if "lag" in c]
train = train.dropna(subset=lag_cols, how="all")
test = test.dropna(subset=lag_cols, how="all")

X_train = train[feature_cols].fillna(0)
y_train = train["quantity_sold"].fillna(0)
X_test = test[feature_cols].fillna(0)
y_test = test["quantity_sold"].fillna(0).values
prices_test = test["item_price"].values
item_ids_test = test["item_id"].values
shelf_groups_test = test["shelf_group"].values

# Decay weights
days_ago = (test_cutoff - train["date"]).dt.days
weights = np.exp(-np.log(2) * days_ago / BEST_DECAY_HL)
weights = weights / weights.mean()

print(f"Train: {len(X_train):,}  Test: {len(X_test):,}")
print(f"\nShelf group distribution in test set:")
for g in sorted(test["shelf_group"].unique()):
    n = (shelf_groups_test == g).sum()
    print(f"  {g:20s}: {n:>8,} samples ({n/len(test)*100:.1f}%)")

# ============================================================================
# ALL MODEL DEFINITIONS (Colab has plenty of RAM)
# ============================================================================
import xgboost as xgb
import catboost as cb
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor

def build_model(name):
    if name == "LightGBM":
        return lgb.LGBMRegressor(
            n_estimators=800, learning_rate=0.03, num_leaves=127,
            min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0, n_jobs=-1, random_state=SEED, verbosity=-1)
    elif name == "XGBoost":
        return xgb.XGBRegressor(
            n_estimators=800, learning_rate=0.03, max_depth=8,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
            tree_method="hist", n_jobs=-1, random_state=SEED, verbosity=0)
    elif name == "CatBoost":
        return cb.CatBoostRegressor(
            iterations=800, learning_rate=0.03, depth=8, l2_leaf_reg=3.0,
            random_seed=SEED, verbose=0,
            task_type="GPU" if os.environ.get("COLAB_GPU") or os.path.exists("/dev/nvidia0") else "CPU")
    elif name == "RandomForest":
        return RandomForestRegressor(
            n_estimators=500, min_samples_leaf=5, max_depth=20, n_jobs=-1, random_state=SEED)
    elif name == "ExtraTrees":
        return ExtraTreesRegressor(
            n_estimators=500, max_depth=20, n_jobs=-1, random_state=SEED)
    else:
        raise ValueError(f"Unknown model: {name}")

# RF/ET skipped: too slow on Colab's 2 CPU cores (60+ min each on 2.2M rows)
MODEL_NAMES = ["LightGBM", "XGBoost", "CatBoost"]

# ============================================================================
# TRAIN ALL MODELS
# ============================================================================
print("\nTraining all models with shelf features...")
trained_models = {}
raw_predictions = {}

for name in MODEL_NAMES:
    t0 = time.time()
    print(f"  Training {name}...", end=" ", flush=True)
    model = build_model(name)
    if name in ("RandomForest", "ExtraTrees"):
        model.fit(X_train, y_train, sample_weight=weights)
    else:
        model.fit(X_train, y_train, sample_weight=weights)
    raw_predictions[name] = model.predict(X_test)
    trained_models[name] = model
    print(f"done in {time.time()-t0:.1f}s")

print("All models trained.")

# ============================================================================
# EVALUATE FUNCTION (works on subsets)
# ============================================================================
def compute_cost(actual, predicted, prices, item_ids):
    actual = np.array(actual, dtype=float)
    predicted = np.clip(np.array(predicted, dtype=float), 0, None)
    prices = np.array(prices, dtype=float)

    overstock = np.maximum(predicted - actual, 0)
    understock = np.maximum(actual - predicted, 0)

    waste_fracs = np.array([effective_waste_fraction(iid) for iid in item_ids])
    waste_cost = (overstock * prices * waste_fracs).sum()
    stockout_cost = (understock * prices).sum()
    total_cost = waste_cost + STOCKOUT_MULTIPLIER * stockout_cost
    return total_cost, waste_cost, stockout_cost

# ============================================================================
# PER-MODEL BUFFER OPTIMIZATION
# ============================================================================
groups = sorted(test["shelf_group"].unique())
all_model_results = {}

def optimize_group_buffer(raw_preds, group_mask, group_actual, group_prices, group_ids):
    """Find optimal buffer for one group given raw predictions."""
    def cost_fn(buf):
        preds = np.clip(raw_preds[group_mask] * buf, 0, None)
        total, _, _ = compute_cost(group_actual, preds, group_prices, group_ids)
        return total
    best_buf, best_cost = 1.0, float("inf")
    for buf in np.arange(0.80, 2.01, 0.05):
        c = cost_fn(buf)
        if c < best_cost:
            best_cost = c; best_buf = buf
    result = minimize_scalar(cost_fn, bounds=(max(0.5, best_buf-0.1), min(2.5, best_buf+0.1)), method="bounded")
    if result.success and result.fun < best_cost:
        best_buf = result.x; best_cost = result.fun
    return round(best_buf, 3), best_cost

for model_name in MODEL_NAMES:
    raw_preds = raw_predictions[model_name]

    print(f"\n{'='*70}")
    print(f"MODEL: {model_name}")
    print(f"{'='*70}")

    # Flat buffer baseline
    flat_preds = np.clip(raw_preds * 1.40, 0, None)
    flat_cost, flat_waste, flat_stockout = compute_cost(y_test, flat_preds, prices_test, item_ids_test)
    print(f"  Flat buf=1.40: {flat_cost:>12,.0f} DKK (waste: {flat_waste:,.0f}, stockout: {flat_stockout:,.0f})")

    # Optimize per-group buffer
    optimal_buffers = {}
    for group in groups:
        mask = shelf_groups_test == group
        opt_buf, opt_cost = optimize_group_buffer(
            raw_preds, mask, y_test[mask], prices_test[mask], item_ids_test[mask])
        optimal_buffers[group] = opt_buf
        flat_g = compute_cost(y_test[mask], np.clip(raw_preds[mask]*1.40, 0, None), prices_test[mask], item_ids_test[mask])[0]
        savings = flat_g - opt_cost
        print(f"    {group:20s}: buf={opt_buf:.3f}  saves {savings:>+10,.0f} DKK")

    # Apply per-group
    pergroup_preds = np.zeros_like(raw_preds)
    for group in groups:
        mask = shelf_groups_test == group
        pergroup_preds[mask] = np.clip(raw_preds[mask] * optimal_buffers[group], 0, None)
    pergroup_cost, pergroup_waste, pergroup_stockout = compute_cost(
        y_test, pergroup_preds, prices_test, item_ids_test)

    # Per-item optimization for top 50 error items
    abs_errors = np.abs(pergroup_preds - y_test)
    error_df = pd.DataFrame({"item_id": item_ids_test, "abs_error": abs_errors, "price": prices_test})
    item_errors = error_df.groupby("item_id").agg(total_error=("abs_error", "sum")).sort_values("total_error", ascending=False)
    top_items = item_errors.head(50).index.tolist()
    per_item_buffers = {}

    for item_id in top_items:
        mask = item_ids_test == item_id
        if mask.sum() < 5: continue
        item_raw = raw_preds[mask]
        item_actual = y_test[mask]
        item_prices_loc = prices_test[mask]
        item_ids_loc = item_ids_test[mask]

        best_buf, best_cost = 1.0, float("inf")
        for buf in np.arange(0.50, 3.01, 0.05):
            preds = np.clip(item_raw * buf, 0, None)
            c, _, _ = compute_cost(item_actual, preds, item_prices_loc, item_ids_loc)
            if c < best_cost: best_cost = c; best_buf = buf
        result = minimize_scalar(lambda b: compute_cost(item_actual, np.clip(item_raw*b, 0, None), item_prices_loc, item_ids_loc)[0],
                                 bounds=(max(0.3, best_buf-0.1), min(4.0, best_buf+0.1)), method="bounded")
        if result.success and result.fun < best_cost: best_buf = result.x
        per_item_buffers[str(item_id)] = round(best_buf, 3)

    # Apply hybrid (per-group + per-item)
    hybrid_preds = np.zeros_like(raw_preds)
    for i in range(len(raw_preds)):
        iid = str(item_ids_test[i])
        if iid in per_item_buffers:
            buf = per_item_buffers[iid]
        else:
            group = get_shelf_group(iid)
            buf = optimal_buffers.get(group, 1.40)
        hybrid_preds[i] = max(raw_preds[i] * buf, 0)
    hybrid_cost, hybrid_waste, hybrid_stockout = compute_cost(y_test, hybrid_preds, prices_test, item_ids_test)

    print(f"\n  {'Method':30s} {'Total Cost':>14s} {'Waste':>14s} {'Stockout':>14s}")
    print(f"  {'-'*30} {'-'*14} {'-'*14} {'-'*14}")
    print(f"  {'Flat buf=1.40':30s} {flat_cost:>14,.0f} {flat_waste:>14,.0f} {flat_stockout:>14,.0f}")
    print(f"  {'Per-group buffer':30s} {pergroup_cost:>14,.0f} {pergroup_waste:>14,.0f} {pergroup_stockout:>14,.0f}")
    print(f"  {'Hybrid (group+top50)':30s} {hybrid_cost:>14,.0f} {hybrid_waste:>14,.0f} {hybrid_stockout:>14,.0f}")
    delta = hybrid_cost - flat_cost
    pct = delta / flat_cost * 100
    print(f"  vs flat: {delta:+,.0f} DKK ({pct:+.2f}%)")

    all_model_results[model_name] = {
        "flat_cost": flat_cost, "pergroup_cost": pergroup_cost, "hybrid_cost": hybrid_cost,
        "improvement_pct": round(-pct, 2),
        "group_buffers": optimal_buffers,
        "per_item_buffers": per_item_buffers,
    }

# ============================================================================
# FINAL RANKING
# ============================================================================
print(f"\n{'='*70}")
print("FINAL RANKING: ALL MODELS WITH OPTIMIZED BUFFERS")
print(f"{'='*70}")
print(f"\n  {'Model':20s} {'Flat 1.40':>14s} {'Per-group':>14s} {'Hybrid':>14s} {'Improve':>8s}")
print(f"  {'-'*20} {'-'*14} {'-'*14} {'-'*14} {'-'*8}")
ranked = sorted(all_model_results.items(), key=lambda x: x[1]["hybrid_cost"])
for name, r in ranked:
    print(f"  {name:20s} {r['flat_cost']:>14,.0f} {r['pergroup_cost']:>14,.0f} "
          f"{r['hybrid_cost']:>14,.0f} {r['improvement_pct']:>+7.2f}%")

best_model = ranked[0][0]
best_cost = ranked[0][1]["hybrid_cost"]
print(f"\n  BEST: {best_model} with hybrid buffer -> {best_cost:,.0f} DKK")

# ============================================================================
# SAVE RESULTS
# ============================================================================
output = {
    "all_model_results": {k: {kk: vv for kk, vv in v.items() if kk != "per_item_buffers"} for k, v in all_model_results.items()},
    "best_model": best_model,
    "best_cost": best_cost,
    "group_distribution": {g: int((shelf_groups_test == g).sum()) for g in groups},
}

with open(RESULTS_DIR / "per_item_buffer_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)

# Save best model's buffer lookup for production
best_buffers = all_model_results[best_model]
buffer_lookup = {}
for group, buf in best_buffers["group_buffers"].items():
    buffer_lookup[f"group:{group}"] = buf
for item_id, buf in best_buffers["per_item_buffers"].items():
    buffer_lookup[f"item:{item_id}"] = buf

with open(RESULTS_DIR / "buffer_lookup.json", "w") as f:
    json.dump(buffer_lookup, f, indent=2)
print(f"\nResults saved to {RESULTS_DIR}/")

print("\nDONE.")
