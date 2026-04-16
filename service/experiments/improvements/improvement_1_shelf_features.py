"""
Improvement 1: Add shelf-life as MODEL FEATURES.

Currently shelf-life data is only used in the cost function (evaluation).
The model itself has no idea which items are perishable vs long-shelf.
This script adds shelf_life_days, avg_gap_days, perishability, storage_type,
and effective_waste_fraction as input features.

Usage: Run cells in order in Colab (or as a script).
       Requires production.db and production_shelf_life_final.csv in data/raw/.
"""

import os
import sys
import time
import json
import sqlite3
import pickle
import warnings
import inspect
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from sklearn.preprocessing import LabelEncoder
import lightgbm as lgb

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", "{:.2f}".format)

import gc

print("All imports OK")

# ============================================================================
# CONFIG — adjust paths if running on Colab
# ============================================================================
# If on Colab, upload your data or mount Drive and change these paths
DB_PATH = "data/raw/production.db"
SHELF_LIFE_PATH = "data/raw/production_shelf_life_final.csv"

# Auto-detect: if local paths exist, use them; otherwise assume Colab upload
LOCAL_BASE = "/home/yahyahammoudeh/Documents/loving loyalty internship"
if os.path.exists(os.path.join(LOCAL_BASE, DB_PATH)):
    DB_PATH = os.path.join(LOCAL_BASE, DB_PATH)
    SHELF_LIFE_PATH = os.path.join(LOCAL_BASE, SHELF_LIFE_PATH)

RESULTS_DIR = Path("results_shelf_features")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

assert os.path.exists(DB_PATH), f"Database not found at {DB_PATH}"
print(f"Database: {DB_PATH} ({os.path.getsize(DB_PATH) / 1e6:.0f} MB)")

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
# LOAD DATA (same as production training)
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

    n_before = len(orders)
    orders = orders[orders["status"] == "Closed"].copy()
    print(f"Filtered orders: {n_before:,} -> {len(orders):,} (Closed only)")

    orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
    orders = orders.dropna(subset=["created_dt"])
    orders["date"] = orders["created_dt"].dt.normalize()

    print(f"Date range: {orders['date'].min().date()} to {orders['date'].max().date()}")
    print(f"Unique places: {orders['place_id'].nunique()}")
    print(f"Load time: {time.time()-t0:.1f}s")
    return orders, items, menu, places

orders, items, menu, places = load_production_data(DB_PATH)

# ============================================================================
# SHELF LIFE LOOKUP
# ============================================================================
shelf_df = pd.read_csv(SHELF_LIFE_PATH)
SHELF_LOOKUP = {}
for _, row in shelf_df.iterrows():
    iid = str(row["item_id"])
    sl = float(row["shelf_life_days"]) if pd.notna(row["shelf_life_days"]) else 3.0
    ag = float(row["avg_gap_days"]) if pd.notna(row["avg_gap_days"]) else 1.0
    SHELF_LOOKUP[iid] = (sl, ag)
print(f"Shelf life lookup: {len(SHELF_LOOKUP)} items")

# Build extended shelf lookup with all columns for features
SHELF_FEATURES = {}
perishability_map = {"high": 2, "medium": 1, "low": 0}
storage_map = {"refrigerated": 2, "frozen": 1, "ambient": 0, "dry": 0}
for _, row in shelf_df.iterrows():
    iid = str(row["item_id"])
    sl = float(row["shelf_life_days"]) if pd.notna(row["shelf_life_days"]) else 3.0
    ag = float(row["avg_gap_days"]) if pd.notna(row["avg_gap_days"]) else 1.0
    perish = perishability_map.get(str(row.get("perishability", "low")), 0)
    storage = storage_map.get(str(row.get("storage_type", "dry")), 0)

    # Effective waste fraction (same formula as evaluate)
    if sl >= 9999:
        ewf = 0.0
    else:
        ewf = WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))

    SHELF_FEATURES[iid] = {
        "shelf_life_days": sl,
        "avg_gap_days": ag,
        "perishability": perish,
        "storage_type": storage,
        "effective_waste_frac": ewf,
        "log_shelf_life": np.log1p(sl),
        "turnover_ratio": min(ag / max(sl, 0.5), 5.0),  # how fast it turns over relative to shelf life
    }

print(f"Shelf features built for {len(SHELF_FEATURES)} items")

def effective_waste_fraction(item_id):
    sl, ag = SHELF_LOOKUP.get(str(item_id), (3.0, 1.0))
    if sl >= 9999:
        return 0.0
    return WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))

# ============================================================================
# PREPARE DAILY DEMAND (same as production)
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
    n_pairs = len(top_keys)

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
    print(f"Complete grid: {len(full):,} rows, {len(all_dates)} days, {n_pairs} pairs")
    print(f"Prep time: {time.time()-t0:.1f}s")
    return full, all_dates

daily_full, all_dates = prepare_daily_demand(orders, items, menu)
del orders, items, menu, places; gc.collect()

# ============================================================================
# FEATURE ENGINEERING — WITH SHELF-LIFE FEATURES (the new part)
# ============================================================================
def engineer_features(df):
    t0 = time.time()
    df = df.copy()
    grp = ["place_id", "item_id"]

    # ---- Time features ----
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
    print(f"  Time features done ({time.time()-t0:.0f}s)")

    # ---- Lag features ----
    t1 = time.time()
    for lag in [1, 7, 14, 28]:
        df[f"demand_lag_{lag}d"] = df.groupby(grp, observed=True)["quantity_sold"].shift(lag)
    df["demand_same_weekday_last_week"] = df.groupby(grp, observed=True)["quantity_sold"].shift(7)
    print(f"  Lag features done ({time.time()-t1:.0f}s)")

    # ---- Rolling features ----
    t1 = time.time()
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
    print(f"  Rolling features done ({time.time()-t1:.0f}s)")

    # ---- Trend features ----
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

    # ---- Demand residual feedback ----
    t1 = time.time()
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
    print(f"  Residual features done ({time.time()-t1:.0f}s)")

    # ---- Fourier harmonics ----
    for k in [1, 2, 3]:
        df[f"fourier_week_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_week"] / 7)
        df[f"fourier_week_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_week"] / 7)
    for k in [1, 2]:
        df[f"fourier_year_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_year"] / 365.25)
        df[f"fourier_year_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_year"] / 365.25)

    # ---- Danish calendar features ----
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

    # ---- Categorical encoding ----
    le_place = LabelEncoder()
    le_item = LabelEncoder()
    df["place_id_encoded"] = le_place.fit_transform(df["place_id"].astype(str))
    df["item_id_encoded"] = le_item.fit_transform(df["item_id"].astype(str))
    df["store_dow_interaction"] = df["place_id_encoded"] * 10 + df["day_of_week"]

    # ---- Store-cluster features ----
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

    # ---- Stub features ----
    for col in ["temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
                "is_promotion_active", "discount_percentage", "campaign_count"]:
        df[col] = 0
    df["is_open"] = 1

    # ==================================================================
    # NEW: SHELF-LIFE FEATURES
    # ==================================================================
    t1 = time.time()
    item_ids_str = df["item_id"].astype(str)

    # Default values for items not in shelf lookup
    defaults = {
        "shelf_life_days": 3.0,
        "avg_gap_days": 1.0,
        "perishability": 1,       # medium
        "storage_type": 0,        # dry/ambient
        "effective_waste_frac": 0.3,
        "log_shelf_life": np.log1p(3.0),
        "turnover_ratio": 1.0 / 3.0,
    }

    for feat_name, default_val in defaults.items():
        df[feat_name] = item_ids_str.map(
            lambda iid, fn=feat_name, dv=default_val: SHELF_FEATURES.get(iid, defaults).get(fn, dv)
        )

    # Interaction features: shelf-life x demand patterns
    df["shelf_x_rolling7"] = df["log_shelf_life"] * df["rolling_mean_7d"].fillna(0)
    df["perishable_x_weekend"] = df["perishability"] * df["is_weekend"]
    df["perishable_x_monday"] = df["perishability"] * df["is_monday"]
    df["turnover_x_lag1"] = df["turnover_ratio"] * df["demand_lag_1d"].fillna(0)

    print(f"  Shelf-life features done ({time.time()-t1:.0f}s)")
    # ==================================================================

    # ---- FEATURE LIST (original + shelf-life features) ----
    feature_cols = [
        # Original features
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
        # NEW shelf-life features
        "shelf_life_days", "avg_gap_days", "perishability", "storage_type",
        "effective_waste_frac", "log_shelf_life", "turnover_ratio",
        "shelf_x_rolling7", "perishable_x_weekend", "perishable_x_monday",
        "turnover_x_lag1",
    ]

    print(f"  Total features: {len(feature_cols)} (was 60, now +11 shelf features)")
    print(f"  Total time: {time.time()-t0:.0f}s")
    return df, feature_cols

df, feature_cols = engineer_features(daily_full)
del daily_full; gc.collect()

# Downcast to float32
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
def get_train_test(df, feature_cols, test_days=TEST_DAYS, train_days=None, decay_half_life=None):
    max_date = df["date"].max()
    test_cutoff = max_date - pd.Timedelta(days=test_days)

    train = df[df["date"] <= test_cutoff].copy()
    test = df[df["date"] > test_cutoff].copy()

    if train_days is not None:
        train_start = test_cutoff - pd.Timedelta(days=train_days)
        train = train[train["date"] > train_start]

    lag_cols = [c for c in feature_cols if "lag" in c]
    train = train.dropna(subset=lag_cols, how="all")
    test = test.dropna(subset=lag_cols, how="all")

    X_train = train[feature_cols].fillna(0)
    y_train = train["quantity_sold"].fillna(0)
    X_test = test[feature_cols].fillna(0)
    y_test = test["quantity_sold"].fillna(0)
    prices_test = test["item_price"].values
    item_ids_test = test["item_id"].values

    weights = None
    if decay_half_life is not None:
        days_ago = (test_cutoff - train["date"]).dt.days
        weights = np.exp(-np.log(2) * days_ago / decay_half_life)
        weights = weights / weights.mean()

    return X_train, y_train, X_test, y_test, prices_test, item_ids_test, weights

# ============================================================================
# EVALUATE
# ============================================================================
def evaluate(y_actual, y_predicted, prices, item_ids=None):
    actual = np.array(y_actual, dtype=float)
    predicted = np.clip(np.array(y_predicted, dtype=float), 0, None)
    prices = np.array(prices, dtype=float)

    mae = np.abs(actual - predicted).mean()
    rmse = np.sqrt(np.mean((actual - predicted) ** 2))
    total_actual = actual.sum()
    wmape = np.sum(np.abs(actual - predicted)) / max(total_actual, 1) * 100

    overstock = np.maximum(predicted - actual, 0)
    understock = np.maximum(actual - predicted, 0)

    if item_ids is not None:
        waste_fracs = np.array([effective_waste_fraction(iid) for iid in item_ids])
    else:
        waste_fracs = np.full(len(actual), WASTE_FRACTION)

    waste_cost = (overstock * prices * waste_fracs).sum()
    stockout_cost = (understock * prices).sum()
    total_cost = waste_cost + STOCKOUT_MULTIPLIER * stockout_cost

    return {
        "total_business_cost_dkk": round(total_cost, 2),
        "waste_cost_dkk": round(waste_cost, 2),
        "stockout_cost_dkk": round(stockout_cost, 2),
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "wmape": round(wmape, 4),
        "n_samples": len(actual),
    }

# ============================================================================
# EXPERIMENT: COMPARE BASELINE vs SHELF-LIFE FEATURES
# ============================================================================
# Best config from production training: full history, decay=6d, buf=1.40
BEST_DECAY_HL = 6
BEST_BUFFER = 1.40

# Baseline feature list (without shelf-life features)
baseline_features = [c for c in feature_cols if c not in [
    "shelf_life_days", "avg_gap_days", "perishability", "storage_type",
    "effective_waste_frac", "log_shelf_life", "turnover_ratio",
    "shelf_x_rolling7", "perishable_x_weekend", "perishable_x_monday",
    "turnover_x_lag1",
]]

print(f"\nBaseline features: {len(baseline_features)}")
print(f"With shelf features: {len(feature_cols)}")
print(f"New features: {len(feature_cols) - len(baseline_features)}")

results = []

# ============================================================================
# ALL MODEL DEFINITIONS (Colab has plenty of RAM — include RF + ET too)
# ============================================================================
import xgboost as xgb
import catboost as cb
from sklearn.ensemble import (
    RandomForestRegressor, ExtraTreesRegressor, StackingRegressor,
)
from sklearn.linear_model import Ridge

class LightGBMModel:
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(
            n_estimators=800, learning_rate=0.03, num_leaves=127,
            min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0, n_jobs=-1, random_state=SEED, verbosity=-1,
        )
        defaults.update(kwargs)
        self.model = lgb.LGBMRegressor(**defaults)
    def fit(self, X, y, sample_weight=None):
        self.model.fit(X, y, sample_weight=sample_weight) if sample_weight is not None else self.model.fit(X, y)
        return self
    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)
    def predict_raw(self, X):
        return self.model.predict(X)

class XGBoostModel:
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(
            n_estimators=800, learning_rate=0.03, max_depth=8,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
            tree_method="hist", n_jobs=-1, random_state=SEED, verbosity=0,
        )
        defaults.update(kwargs)
        self.model = xgb.XGBRegressor(**defaults)
    def fit(self, X, y, sample_weight=None):
        self.model.fit(X, y, sample_weight=sample_weight) if sample_weight is not None else self.model.fit(X, y)
        return self
    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)
    def predict_raw(self, X):
        return self.model.predict(X)

class CatBoostModel:
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(
            iterations=800, learning_rate=0.03, depth=8,
            l2_leaf_reg=3.0, random_seed=SEED, verbose=0,
            task_type="GPU" if os.environ.get("COLAB_GPU") or os.path.exists("/dev/nvidia0") else "CPU",
        )
        defaults.update(kwargs)
        self.model = cb.CatBoostRegressor(**defaults)
    def fit(self, X, y, sample_weight=None):
        self.model.fit(X, y, sample_weight=sample_weight) if sample_weight is not None else self.model.fit(X, y)
        return self
    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)
    def predict_raw(self, X):
        return self.model.predict(X)

class RFModel:
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(n_estimators=500, min_samples_leaf=5, max_depth=20, n_jobs=-1, random_state=SEED)
        defaults.update(kwargs)
        self.model = RandomForestRegressor(**defaults)
    def fit(self, X, y, sample_weight=None):
        self.model.fit(X, y, sample_weight=sample_weight) if sample_weight is not None else self.model.fit(X, y)
        return self
    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)
    def predict_raw(self, X):
        return self.model.predict(X)

class ETModel:
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(n_estimators=500, max_depth=20, n_jobs=-1, random_state=SEED)
        defaults.update(kwargs)
        self.model = ExtraTreesRegressor(**defaults)
    def fit(self, X, y, sample_weight=None):
        self.model.fit(X, y, sample_weight=sample_weight) if sample_weight is not None else self.model.fit(X, y)
        return self
    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)
    def predict_raw(self, X):
        return self.model.predict(X)

class BlendModel:
    def __init__(self, safety_buffer=1.15):
        self.safety_buffer = safety_buffer
        self.models = [
            lgb.LGBMRegressor(n_estimators=600, learning_rate=0.04, num_leaves=95,
                              n_jobs=-1, random_state=SEED, verbosity=-1),
            xgb.XGBRegressor(n_estimators=600, learning_rate=0.04, max_depth=8,
                             tree_method="hist", n_jobs=-1, random_state=SEED, verbosity=0),
            cb.CatBoostRegressor(iterations=600, learning_rate=0.04, depth=8,
                                 random_seed=SEED, verbose=0,
                                 task_type="GPU" if os.environ.get("COLAB_GPU") or os.path.exists("/dev/nvidia0") else "CPU"),
        ]
    def fit(self, X, y, sample_weight=None):
        for m in self.models:
            m.fit(X, y, sample_weight=sample_weight) if sample_weight is not None else m.fit(X, y)
        return self
    def predict(self, X):
        preds = np.column_stack([m.predict(X) for m in self.models])
        return np.clip(preds.mean(axis=1) * self.safety_buffer, 0, None)
    def predict_raw(self, X):
        preds = np.column_stack([m.predict(X) for m in self.models])
        return preds.mean(axis=1)

class SoftProbV2:
    def __init__(self, base_global_weight=0.60, min_store_samples=150,
                 random_state=SEED, safety_buffer=1.25, prob_exponent=0.30):
        self.base_global_weight = base_global_weight
        self.min_store_samples = min_store_samples
        self.random_state = random_state
        self.safety_buffer = safety_buffer
        self.prob_exponent = prob_exponent
        self.global_model = None
        self.classifier = None
        self.store_models = {}
        self.store_weights = {}
        self.feature_cols_ = None
    def fit(self, X, y, sample_weight=None):
        self.feature_cols_ = list(X.columns) if hasattr(X, "columns") else None
        X_arr = X.values if hasattr(X, "values") else X
        y_arr = np.array(y)
        y_binary = (y_arr > 0).astype(int)
        self.classifier = lgb.LGBMClassifier(
            n_estimators=500, learning_rate=0.05, num_leaves=63,
            n_jobs=-1, random_state=self.random_state, verbosity=-1)
        kw = dict(sample_weight=sample_weight) if sample_weight is not None else {}
        self.classifier.fit(X_arr, y_binary, **kw)
        self.global_model = lgb.LGBMRegressor(
            n_estimators=800, learning_rate=0.03, num_leaves=127,
            n_jobs=-1, random_state=self.random_state, verbosity=-1)
        self.global_model.fit(X_arr, y_arr, **kw)
        store_col_idx = self.feature_cols_.index("place_id_encoded") if self.feature_cols_ else -3
        store_ids = X_arr[:, store_col_idx]
        for store_id in tqdm(np.unique(store_ids), desc="SoftProbV2 per-store", leave=False):
            mask = store_ids == store_id
            n_store = mask.sum()
            if n_store < 20:
                self.store_weights[store_id] = 1.0; continue
            store_model = lgb.LGBMRegressor(
                n_estimators=200, learning_rate=0.05, num_leaves=31,
                n_jobs=1, random_state=self.random_state, verbosity=-1)
            w_store = sample_weight[mask] if sample_weight is not None else None
            store_model.fit(X_arr[mask], y_arr[mask], sample_weight=w_store) if w_store is not None else store_model.fit(X_arr[mask], y_arr[mask])
            self.store_models[store_id] = store_model
            frac = min(n_store / self.min_store_samples, 1.0)
            self.store_weights[store_id] = 1.0 - frac * (1.0 - self.base_global_weight)
        return self
    def predict(self, X):
        X_arr = X.values if hasattr(X, "values") else X
        proba = self.classifier.predict_proba(X_arr)[:, 1]
        p_weight = np.power(proba, self.prob_exponent)
        global_preds = self.global_model.predict(X_arr)
        result = global_preds.copy()
        store_col_idx = self.feature_cols_.index("place_id_encoded") if self.feature_cols_ else -3
        store_ids = X_arr[:, store_col_idx]
        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            if store_id not in self.store_models: continue
            gw = self.store_weights.get(store_id, self.base_global_weight)
            sw = 1.0 - gw
            store_pred = self.store_models[store_id].predict(X_arr[mask])
            result[mask] = sw * store_pred + gw * global_preds[mask]
        result = p_weight * result
        return np.clip(result * self.safety_buffer, 0, None)
    def predict_raw(self, X):
        # Same as predict but without buffer
        X_arr = X.values if hasattr(X, "values") else X
        proba = self.classifier.predict_proba(X_arr)[:, 1]
        p_weight = np.power(proba, self.prob_exponent)
        global_preds = self.global_model.predict(X_arr)
        result = global_preds.copy()
        store_col_idx = self.feature_cols_.index("place_id_encoded") if self.feature_cols_ else -3
        store_ids = X_arr[:, store_col_idx]
        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            if store_id not in self.store_models: continue
            gw = self.store_weights.get(store_id, self.base_global_weight)
            sw = 1.0 - gw
            store_pred = self.store_models[store_id].predict(X_arr[mask])
            result[mask] = sw * store_pred + gw * global_preds[mask]
        return p_weight * result

print("All models defined: LGB, XGB, CatBoost, RF, ET, Blend, SoftProbV2")

# ============================================================================
# MODEL CONFIGS — all models, with Colab-friendly n_jobs=-1
# ============================================================================
ALL_MODELS = {
    "LightGBM":        lambda buf: LightGBMModel(safety_buffer=buf),
    "XGBoost":         lambda buf: XGBoostModel(safety_buffer=buf),
    "CatBoost":        lambda buf: CatBoostModel(safety_buffer=buf),
    # RF/ET skipped: 500 trees on 2.2M rows takes 60+ min on Colab's 2 CPU cores
    # "RandomForest":    lambda buf: RFModel(safety_buffer=buf),
    # "ExtraTrees":      lambda buf: ETModel(safety_buffer=buf),
    "Blend_LGB_XGB_CB": lambda buf: BlendModel(safety_buffer=buf),
    "SoftProbV2":      lambda buf: SoftProbV2(safety_buffer=buf),
}

def run_one_model(name, build_fn, X_train, y_train, X_test, y_test, prices, item_ids, weights, buf):
    t0 = time.time()
    model = build_fn(buf)
    if weights is not None and hasattr(model, 'fit'):
        model.fit(X_train, y_train, sample_weight=weights)
    else:
        model.fit(X_train, y_train)
    preds = model.predict(X_test)
    m = evaluate(y_test, preds, prices, item_ids=item_ids)
    m["model"] = name
    m["time_s"] = round(time.time() - t0, 1)
    del model; gc.collect()
    return m

# ============================================================================
# PHASE 1: ALL MODELS — BASELINE (no shelf features) vs WITH SHELF FEATURES
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 1: ALL MODELS — BASELINE vs SHELF FEATURES (buf=1.40, decay=6d)")
print("=" * 70)

for feat_set_name, feat_list in [("baseline", baseline_features), ("shelf", feature_cols)]:
    print(f"\n--- Feature set: {feat_set_name} ({len(feat_list)} features) ---")
    X_train, y_train, X_test, y_test, prices, item_ids, weights = get_train_test(
        df, feat_list, decay_half_life=BEST_DECAY_HL
    )
    for name, build_fn in ALL_MODELS.items():
        print(f"\n  >>> {name} ({feat_set_name})")
        try:
            m = run_one_model(name, build_fn, X_train, y_train, X_test, y_test,
                              prices, item_ids, weights, BEST_BUFFER)
            m["feature_set"] = feat_set_name
            m["n_features"] = len(feat_list)
            m["description"] = f"{name} {feat_set_name} buf={BEST_BUFFER}"
            results.append(m)
            print(f"    Cost: {m['total_business_cost_dkk']:>12,.0f} DKK  "
                  f"MAE: {m['mae']:.4f}  Time: {m['time_s']}s")
        except Exception as e:
            print(f"    FAILED: {e}")
            results.append({"model": name, "feature_set": feat_set_name, "status": "crash", "error": str(e)})

# ============================================================================
# PHASE 2: COMPARISON TABLE
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 1 RESULTS: BASELINE vs SHELF FEATURES")
print("=" * 70)
print(f"\n  {'Model':25s} {'Baseline Cost':>14s} {'Shelf Cost':>14s} {'Delta':>12s} {'%':>8s}")
print(f"  {'-'*25} {'-'*14} {'-'*14} {'-'*12} {'-'*8}")

for name in ALL_MODELS:
    base_r = [r for r in results if r.get("model") == name and r.get("feature_set") == "baseline" and "total_business_cost_dkk" in r]
    shelf_r = [r for r in results if r.get("model") == name and r.get("feature_set") == "shelf" and "total_business_cost_dkk" in r]
    if base_r and shelf_r:
        bc = base_r[0]["total_business_cost_dkk"]
        sc = shelf_r[0]["total_business_cost_dkk"]
        delta = sc - bc
        pct = delta / bc * 100
        print(f"  {name:25s} {bc:>14,.0f} {sc:>14,.0f} {delta:>+12,.0f} {pct:>+7.2f}%")

# ============================================================================
# PHASE 3: BUFFER SWEEP — TOP 3 MODELS WITH SHELF FEATURES
# ============================================================================
shelf_results = [r for r in results if r.get("feature_set") == "shelf" and "total_business_cost_dkk" in r]
shelf_results.sort(key=lambda r: r["total_business_cost_dkk"])
top3 = [r["model"] for r in shelf_results[:3]]

print(f"\n{'='*70}")
print(f"PHASE 2: BUFFER SWEEP — top 3 models with shelf features: {top3}")
print(f"{'='*70}")

buffer_values = [1.00, 1.10, 1.20, 1.30, 1.35, 1.40, 1.45, 1.50, 1.60]

X_train, y_train, X_test, y_test, prices, item_ids, weights = get_train_test(
    df, feature_cols, decay_half_life=BEST_DECAY_HL
)

for name in top3:
    print(f"\n--- {name} ---")
    for buf in buffer_values:
        m = run_one_model(name, ALL_MODELS[name], X_train, y_train, X_test, y_test,
                          prices, item_ids, weights, buf)
        m["feature_set"] = "shelf"
        m["buffer"] = buf
        m["description"] = f"{name} shelf buf={buf:.2f}"
        results.append(m)
        print(f"  buf={buf:.2f}  Cost: {m['total_business_cost_dkk']:>12,.0f} DKK  "
              f"waste: {m['waste_cost_dkk']:>10,.0f}  stockout: {m['stockout_cost_dkk']:>10,.0f}")

# Overall best
buf_results = [r for r in results if "buffer" in r and "total_business_cost_dkk" in r]
if buf_results:
    overall_best = min(buf_results, key=lambda r: r["total_business_cost_dkk"])
    print(f"\n{'='*70}")
    print(f"OVERALL BEST: {overall_best.get('model', '?')} buf={overall_best['buffer']:.2f}")
    print(f"  Cost: {overall_best['total_business_cost_dkk']:,.0f} DKK")
    print(f"{'='*70}")

# ============================================================================
# FEATURE IMPORTANCE (LightGBM with shelf features)
# ============================================================================
print("\n" + "=" * 70)
print("FEATURE IMPORTANCE (LightGBM with shelf features)")
print("=" * 70)

# Train one LGB to get importances
model_for_imp = lgb.LGBMRegressor(
    n_estimators=800, learning_rate=0.03, num_leaves=127,
    min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
    reg_alpha=0.1, reg_lambda=1.0, n_jobs=-1, random_state=SEED, verbosity=-1,
)
model_for_imp.fit(X_train, y_train, sample_weight=weights)
importances = model_for_imp.feature_importances_
feat_imp = sorted(zip(feature_cols, importances), key=lambda x: -x[1])

shelf_feat_names = [
    "shelf_life_days", "avg_gap_days", "perishability", "storage_type",
    "effective_waste_frac", "log_shelf_life", "turnover_ratio",
    "shelf_x_rolling7", "perishable_x_weekend", "perishable_x_monday",
    "turnover_x_lag1",
]

print("\nTop 20 features overall:")
for fname, imp in feat_imp[:20]:
    marker = " <<<" if fname in shelf_feat_names else ""
    print(f"  {fname:40s}  {imp:6d}{marker}")

print("\nShelf-life feature ranks:")
for fname, imp in feat_imp:
    if fname in shelf_feat_names:
        rank = [f for f, _ in feat_imp].index(fname) + 1
        print(f"  #{rank:3d}  {fname:40s}  importance={imp}")

del model_for_imp; gc.collect()

# Save results
with open(RESULTS_DIR / "shelf_features_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nResults saved to {RESULTS_DIR / 'shelf_features_results.json'}")
print("\nDONE.")
