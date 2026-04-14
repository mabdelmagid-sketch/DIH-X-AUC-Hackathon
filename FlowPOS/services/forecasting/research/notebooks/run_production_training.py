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
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm.auto import tqdm

from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import (
    RandomForestRegressor,
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    StackingRegressor,
)
from sklearn.linear_model import ElasticNet, Ridge
import lightgbm as lgb
import xgboost as xgb
import catboost as cb

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", "{:.2f}".format)

print("All imports OK")

DB_PATH = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/production.db"

RESULTS_DIR = Path("/home/yahyahammoudeh/Documents/loving loyalty internship/notebooks/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = RESULTS_DIR / "experiment_results.json"

assert os.path.exists(DB_PATH), f"Database not found at {DB_PATH}"
print(f"Database: {DB_PATH} ({os.path.getsize(DB_PATH) / 1e6:.0f} MB)")

def load_production_data(db_path):
    """Load production SQLite data into DataFrames."""
    t0 = time.time()
    conn = sqlite3.connect(db_path)

    print("Loading fct_orders...")
    orders = pd.read_sql("SELECT id, place_id, created, status, total_amount FROM fct_orders", conn)

    print("Loading fct_order_items...")
    items = pd.read_sql("SELECT id, item_id, order_id, quantity, cost, price, title FROM fct_order_items", conn)

    print("Loading dim_menu_items...")
    menu = pd.read_sql("SELECT id, title, price FROM dim_menu_items", conn)

    print("Loading dim_places...")
    places = pd.read_sql("SELECT id, title, active FROM dim_places", conn)

    conn.close()

    # All columns are untyped TEXT in this SQLite dump - convert numerics
    orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
    orders["total_amount"] = pd.to_numeric(orders["total_amount"], errors="coerce")
    items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
    items["cost"] = pd.to_numeric(items["cost"], errors="coerce")
    items["price"] = pd.to_numeric(items["price"], errors="coerce")
    menu["price"] = pd.to_numeric(menu["price"], errors="coerce")

    # Filter to Closed orders only (production uses "Closed", demo used "Settled")
    n_before = len(orders)
    orders = orders[orders["status"] == "Closed"].copy()
    print(f"Filtered orders: {n_before:,} -> {len(orders):,} (Closed only)")

    # Parse timestamps
    orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
    orders = orders.dropna(subset=["created_dt"])
    orders["date"] = orders["created_dt"].dt.normalize()

    print(f"Date range: {orders['date'].min().date()} to {orders['date'].max().date()}")
    print(f"Unique places: {orders['place_id'].nunique()}")
    print(f"Total orders: {len(orders):,}")
    print(f"Total line items: {len(items):,}")
    print(f"Load time: {time.time()-t0:.1f}s")

    return orders, items, menu, places

orders, items, menu, places = load_production_data(DB_PATH)

# ---------- CONSTANTS ----------
TOP_N_ITEMS = 30       # Top items per store by total volume
TEST_DAYS = 14         # Last 14 days for test
WASTE_FRACTION = 0.3   # Waste = 30% of item price * overstock units (flat fallback)
STOCKOUT_MULTIPLIER = 1.5  # Stockout penalty multiplier
MIN_STORE_DAYS = 30    # Minimum days of history to include a store

# ---------- SHELF LIFE LOOKUP ----------
SHELF_LIFE_PATH = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/production_shelf_life_final.csv"
shelf_df = pd.read_csv(SHELF_LIFE_PATH)
# Build lookup: item_id -> (shelf_life_days, avg_gap_days)
SHELF_LOOKUP = {}
for _, row in shelf_df.iterrows():
    iid = str(row["item_id"])
    sl = float(row["shelf_life_days"]) if pd.notna(row["shelf_life_days"]) else 3.0
    ag = float(row["avg_gap_days"]) if pd.notna(row["avg_gap_days"]) else 1.0
    SHELF_LOOKUP[iid] = (sl, ag)
print(f"Shelf life lookup: {len(SHELF_LOOKUP)} items")

def effective_waste_fraction(item_id):
    """Per-item waste fraction based on shelf life.
    Fresh salad (1d shelf) -> 0.3 * 1.0 = 0.30 (full waste)
    Frozen beef (90d shelf, ordered weekly) -> 0.3 * 7/90 = 0.023
    Beer (365d shelf) -> 0.3 * 7/365 = 0.006 (almost no waste)
    """
    sl, ag = SHELF_LOOKUP.get(str(item_id), (3.0, 1.0))
    if sl >= 9999:  # non-food
        return 0.0
    sl = max(sl, 0.5)
    return WASTE_FRACTION * min(1.0, ag / sl)

def prepare_daily_demand(orders, items, menu):
    """Aggregate to daily demand per (place_id, item_id). Vectorized, no loops."""
    t0 = time.time()

    # Merge items with orders to get place_id and date
    merged = items[["item_id", "order_id", "quantity", "cost"]].merge(
        orders[["id", "place_id", "date"]],
        left_on="order_id",
        right_on="id",
        how="inner",
    )
    merged.drop(columns=["id"], inplace=True)
    print(f"Merged line items: {len(merged):,}")

    # Aggregate daily demand
    daily = (
        merged.groupby(["date", "place_id", "item_id"], observed=True)
        .agg(quantity_sold=("quantity", "sum"), revenue=("cost", "sum"))
        .reset_index()
    )
    del merged  # free memory
    print(f"Daily demand rows: {len(daily):,}")

    # Get item prices from dim_menu_items
    item_prices = menu[["id", "price"]].drop_duplicates(subset=["id"]).rename(
        columns={"id": "item_id", "price": "item_price"}
    )
    daily = daily.merge(item_prices, on="item_id", how="left")
    daily["item_price"] = daily["item_price"].fillna(75.0)

    # Filter stores with enough history
    store_date_counts = daily.groupby("place_id")["date"].nunique()
    active_stores = store_date_counts[store_date_counts >= MIN_STORE_DAYS].index
    daily = daily[daily["place_id"].isin(active_stores)].copy()
    print(f"Active stores (>={MIN_STORE_DAYS} days): {len(active_stores)}")

    # Top N items per store by total volume
    top = (
        daily.groupby(["place_id", "item_id"], observed=True)["quantity_sold"]
        .sum()
        .reset_index()
        .sort_values(["place_id", "quantity_sold"], ascending=[True, False])
        .groupby("place_id")
        .head(TOP_N_ITEMS)
    )
    top_keys = top[["place_id", "item_id"]]
    daily = daily.merge(top_keys, on=["place_id", "item_id"], how="inner")
    n_pairs = len(top_keys)
    print(f"After top-{TOP_N_ITEMS} filter: {len(daily):,} rows, {n_pairs} (place,item) pairs")

    # Modal price per (place, item)
    modal_prices = daily.groupby(["place_id", "item_id"], observed=True)["item_price"].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 75.0
    ).reset_index().rename(columns={"item_price": "modal_price"})

    # Build complete date grid using cross-join (vectorized, no loop)
    min_date, max_date = daily["date"].min(), daily["date"].max()
    all_dates = pd.date_range(min_date, max_date, freq="D")
    print(f"Building date grid: {n_pairs} pairs x {len(all_dates)} days...")

    dates_df = pd.DataFrame({"date": all_dates, "_key": 1})
    pairs_df = top_keys.copy()
    pairs_df["_key"] = 1
    full = pairs_df.merge(dates_df, on="_key").drop(columns=["_key"])

    # Merge actual sales and prices
    full = full.merge(
        daily[["date", "place_id", "item_id", "quantity_sold", "revenue"]],
        on=["date", "place_id", "item_id"],
        how="left",
    )
    full = full.merge(modal_prices, on=["place_id", "item_id"], how="left")
    full.rename(columns={"modal_price": "item_price"}, inplace=True)
    full["item_price"] = full["item_price"].fillna(75.0)
    full["quantity_sold"] = full["quantity_sold"].fillna(0)
    full["revenue"] = full["revenue"].fillna(0)
    full = full.sort_values(["place_id", "item_id", "date"]).reset_index(drop=True)

    del daily  # free memory
    print(f"Complete grid: {len(full):,} rows, {len(all_dates)} days")
    print(f"Prep time: {time.time()-t0:.1f}s")
    return full, all_dates

daily_full, all_dates = prepare_daily_demand(orders, items, menu)

# Free raw data from memory
del orders, items, menu, places
import gc; gc.collect()
print(f"Memory freed. Grid shape: {daily_full.shape}")

def engineer_features(df):
    """Full feature engineering pipeline. Vectorized for large datasets."""
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

    # ---- Rolling features (use shift(1) to avoid leakage) ----
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
    print(f"  Trend features done ({time.time()-t0:.0f}s)")

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

    # ---- Danish calendar features (vectorized, no .apply()) ----
    danish_holidays = pd.to_datetime([
        "2025-12-24", "2025-12-25", "2025-12-26", "2025-12-31",
        "2026-01-01", "2026-03-29", "2026-04-02", "2026-04-03",
        "2026-04-05", "2026-04-06",
    ])
    holiday_set = set(danish_holidays.normalize())
    df["is_holiday"] = df["date"].isin(holiday_set).astype(int)

    # Vectorized days_from_holiday: broadcast subtract, take min abs
    dates_arr = df["date"].values.astype("datetime64[D]")
    holidays_arr = danish_holidays.values.astype("datetime64[D]")
    # Compute min distance in chunks to avoid huge memory allocation
    chunk_size = 500_000
    days_from = np.empty(len(df), dtype=np.int32)
    for i in range(0, len(df), chunk_size):
        end = min(i + chunk_size, len(df))
        diffs = np.abs((dates_arr[i:end, None] - holidays_arr[None, :]).astype("timedelta64[D]").astype(int))
        days_from[i:end] = diffs.min(axis=1)
    df["days_from_holiday"] = days_from
    df["near_holiday"] = (df["days_from_holiday"] <= 2).astype(int)

    # School holidays, dark months, christmas (all vectorized)
    m = df["month"]
    d = df["day_of_month"]
    df["is_school_holiday"] = (
        ((m == 12) & (d >= 20)) | ((m == 1) & (d <= 2)) |
        ((m == 2) & (d >= 8) & (d <= 22)) |
        ((m == 3) & (d >= 28)) | ((m == 4) & (d <= 6))
    ).astype(int)
    df["is_dark_months"] = m.isin([11, 12, 1, 2]).astype(int)
    df["is_christmas_period"] = ((m == 12) & (d <= 26)).astype(int)
    print(f"  Calendar features done ({time.time()-t0:.0f}s)")

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
    ]

    print(f"  Total features: {len(feature_cols)}")
    print(f"  Total time: {time.time()-t0:.0f}s")
    return df, feature_cols

df, feature_cols = engineer_features(daily_full)
del daily_full; gc.collect()

# Downcast numeric columns to float32 to save ~50% memory
for col in feature_cols:
    if df[col].dtype == np.float64:
        df[col] = df[col].astype(np.float32)
df["quantity_sold"] = df["quantity_sold"].astype(np.float32)
df["item_price"] = df["item_price"].astype(np.float32)
gc.collect()
print(f"\nFinal dataset: {len(df):,} rows, {len(feature_cols)} features (float32)")

def get_train_test(df, feature_cols, test_days=TEST_DAYS, train_days=None, decay_half_life=None):
    """Split into train/test with optional recency weighting.

    Args:
        train_days: If set, only use last N days for training. None = full history.
        decay_half_life: If set, exponential decay sample weights (days).

    Returns:
        X_train, y_train, X_test, y_test, prices_test, sample_weights (or None)
    """
    max_date = df["date"].max()
    test_cutoff = max_date - pd.Timedelta(days=test_days)

    train = df[df["date"] <= test_cutoff].copy()
    test = df[df["date"] > test_cutoff].copy()

    # Optional: limit training window
    if train_days is not None:
        train_start = test_cutoff - pd.Timedelta(days=train_days)
        train = train[train["date"] > train_start]

    # Drop rows where all lag features are NaN
    lag_cols = [c for c in feature_cols if "lag" in c]
    train = train.dropna(subset=lag_cols, how="all")
    test = test.dropna(subset=lag_cols, how="all")

    X_train = train[feature_cols].fillna(0)
    y_train = train["quantity_sold"].fillna(0)
    X_test = test[feature_cols].fillna(0)
    y_test = test["quantity_sold"].fillna(0)
    prices_test = test["item_price"].values
    item_ids_test = test["item_id"].values  # for shelf-aware evaluation

    # Optional: exponential decay weights
    weights = None
    if decay_half_life is not None:
        days_ago = (test_cutoff - train["date"]).dt.days
        weights = np.exp(-np.log(2) * days_ago / decay_half_life)
        weights = weights / weights.mean()

    return X_train, y_train, X_test, y_test, prices_test, item_ids_test, weights


def evaluate(y_actual, y_predicted, prices, item_ids=None):
    """Business cost metric with shelf-life-aware waste fractions."""
    actual = np.array(y_actual, dtype=float)
    predicted = np.clip(np.array(y_predicted, dtype=float), 0, None)
    prices = np.array(prices, dtype=float)

    mae = np.abs(actual - predicted).mean()
    rmse = np.sqrt(np.mean((actual - predicted) ** 2))
    total_actual = actual.sum()
    wmape = np.sum(np.abs(actual - predicted)) / max(total_actual, 1) * 100

    overstock = np.maximum(predicted - actual, 0)
    understock = np.maximum(actual - predicted, 0)

    # Per-item waste fractions if item_ids provided
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
        "forecast_accuracy_pct": round(max(0, 100 - wmape), 4),
        "overstock_pct": round((predicted > actual).mean() * 100, 2),
        "understock_pct": round((predicted < actual).mean() * 100, 2),
        "n_samples": len(actual),
    }


def run_experiment(model, df, feature_cols, description="",
                   train_days=None, decay_half_life=None):
    """Run a full experiment: split -> train -> predict -> evaluate."""
    t0 = time.time()

    X_train, y_train, X_test, y_test, prices, item_ids, weights = get_train_test(
        df, feature_cols, train_days=train_days, decay_half_life=decay_half_life
    )
    t_data = time.time()

    # Train
    try:
        sig = inspect.signature(model.fit)
        if weights is not None and "sample_weight" in sig.parameters:
            model.fit(X_train, y_train, sample_weight=weights)
        else:
            model.fit(X_train, y_train)
    except Exception as e:
        return {"status": "crash", "error": str(e), "description": description}
    t_train = time.time()

    # Predict
    try:
        predictions = model.predict(X_test)
        predictions = np.clip(np.array(predictions, dtype=float), 0, None)
    except Exception as e:
        return {"status": "crash", "error": str(e), "description": description}
    t_pred = time.time()

    # Evaluate (shelf-life-aware)
    metrics = evaluate(y_test, predictions, prices, item_ids=item_ids)
    metrics["status"] = "ok"
    metrics["description"] = description
    metrics["timing"] = {
        "data_s": round(t_data - t0, 2),
        "train_s": round(t_train - t_data, 2),
        "predict_s": round(t_pred - t_train, 2),
        "total_s": round(t_pred - t0, 2),
    }
    metrics["config"] = {
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "n_features": len(feature_cols),
        "train_days": train_days,
        "decay_half_life": decay_half_life,
    }
    return metrics


def print_results(r):
    """Pretty-print one experiment result."""
    if r.get("status") == "crash":
        print(f"  CRASH: {r.get('error', '?')[:100]}")
        return
    print(f"  Cost: {r['total_business_cost_dkk']:,.0f} DKK "
          f"(waste: {r['waste_cost_dkk']:,.0f}, stockout: {r['stockout_cost_dkk']:,.0f})")
    print(f"  MAE: {r['mae']:.4f}  WMAPE: {r['wmape']:.2f}%  "
          f"Train: {r['timing']['train_s']:.1f}s  Total: {r['timing']['total_s']:.1f}s")

print("Evaluation harness ready")

# =============================================================================
# 5a. LIGHTGBM
# =============================================================================
class LightGBMModel:
    """LightGBM regressor with safety buffer."""
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(
            n_estimators=800, learning_rate=0.03, num_leaves=127,
            min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0, n_jobs=2, random_state=42, verbosity=-1,
        )
        defaults.update(kwargs)
        self.model = lgb.LGBMRegressor(**defaults)

    def fit(self, X, y, sample_weight=None):
        if sample_weight is not None:
            self.model.fit(X, y, sample_weight=sample_weight)
        else:
            self.model.fit(X, y)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)


# =============================================================================
# 5b. XGBOOST
# =============================================================================
class XGBoostModel:
    """XGBoost regressor with safety buffer."""
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(
            n_estimators=800, learning_rate=0.03, max_depth=8,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
            tree_method="hist", n_jobs=2, random_state=42, verbosity=0,
        )
        defaults.update(kwargs)
        self.model = xgb.XGBRegressor(**defaults)

    def fit(self, X, y, sample_weight=None):
        if sample_weight is not None:
            self.model.fit(X, y, sample_weight=sample_weight)
        else:
            self.model.fit(X, y)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)


# =============================================================================
# 5c. CATBOOST
# =============================================================================
class CatBoostModel:
    """CatBoost regressor with safety buffer."""
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(
            iterations=800, learning_rate=0.03, depth=8,
            l2_leaf_reg=3.0, random_seed=42, verbose=0,
            task_type="GPU" if os.environ.get("COLAB_GPU") or os.path.exists("/dev/nvidia0") else "CPU",
        )
        defaults.update(kwargs)
        self.model = cb.CatBoostRegressor(**defaults)

    def fit(self, X, y, sample_weight=None):
        if sample_weight is not None:
            self.model.fit(X, y, sample_weight=sample_weight)
        else:
            self.model.fit(X, y)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)


# =============================================================================
# 5d. RANDOM FOREST
# =============================================================================
class RFModel:
    """Random Forest regressor with safety buffer."""
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(
            n_estimators=300, min_samples_leaf=5, max_depth=20, n_jobs=2, random_state=42,
        )
        defaults.update(kwargs)
        self.model = RandomForestRegressor(**defaults)

    def fit(self, X, y, sample_weight=None):
        if sample_weight is not None:
            self.model.fit(X, y, sample_weight=sample_weight)
        else:
            self.model.fit(X, y)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)


# =============================================================================
# 5e. EXTRA TREES
# =============================================================================
class ETModel:
    """ExtraTrees regressor with safety buffer."""
    def __init__(self, safety_buffer=1.15, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(
            n_estimators=500, max_depth=20, n_jobs=2, random_state=42,
        )
        defaults.update(kwargs)
        self.model = ExtraTreesRegressor(**defaults)

    def fit(self, X, y, sample_weight=None):
        if sample_weight is not None:
            self.model.fit(X, y, sample_weight=sample_weight)
        else:
            self.model.fit(X, y)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)


# =============================================================================
# 5f. ELASTICNET
# =============================================================================
class ElasticNetModel:
    """ElasticNet linear model with safety buffer."""
    def __init__(self, safety_buffer=1.20, **kwargs):
        self.safety_buffer = safety_buffer
        defaults = dict(alpha=0.1, l1_ratio=0.5, max_iter=1000, random_state=42)
        defaults.update(kwargs)
        self.model = ElasticNet(**defaults)

    def fit(self, X, y, sample_weight=None):
        # ElasticNet doesn't support sample_weight
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)

print("Base models defined: LightGBM, XGBoost, CatBoost, RF, ET, ElasticNet")

# =============================================================================
# 5g. SOFTPROB MODEL (current best from demo data)
# LGB classifier gate + RF global + per-store ET local, hierarchical blend
# =============================================================================
class SoftProbModel:
    """
    Soft probability weighting: LightGBM classifier predicts P(demand > 0).
    Final prediction = P^prob_exponent * (global*gw + per-store*sw) * buffer.
    """
    def __init__(self, base_global_weight=0.70, min_store_samples=100,
                 random_state=42, safety_buffer=1.30, prob_exponent=0.25):
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

    def _add_interactions(self, X):
        X_arr = X.values if hasattr(X, "values") else X
        cols = self.feature_cols_
        if cols is None:
            return X_arr
        idx = {c: i for i, c in enumerate(cols)}
        lag7 = X_arr[:, idx["demand_lag_7d"]]
        dow = X_arr[:, idx["day_of_week"]]
        roll7 = X_arr[:, idx["rolling_mean_7d"]]
        is_wknd = X_arr[:, idx["is_weekend"]]
        days_start = X_arr[:, idx["days_since_start"]]
        exp_mean = np.maximum(X_arr[:, idx["expanding_mean"]], 0.01)
        interactions = np.column_stack([
            lag7 * (dow + 1),
            roll7 * is_wknd,
            roll7 * days_start / 45.0,
            lag7 / exp_mean,
        ])
        return np.concatenate([X_arr, interactions], axis=1)

    def fit(self, X, y, sample_weight=None):
        self.feature_cols_ = list(X.columns) if hasattr(X, "columns") else None
        X_arr = X.values if hasattr(X, "values") else X
        X_aug = self._add_interactions(X)
        y_arr = np.array(y)
        y_binary = (y_arr > 0).astype(int)

        self.classifier = lgb.LGBMClassifier(
            n_estimators=500, learning_rate=0.05, num_leaves=63,
            n_jobs=2, random_state=self.random_state, verbosity=-1,
        )
        if sample_weight is not None:
            self.classifier.fit(X_aug, y_binary, sample_weight=sample_weight)
        else:
            self.classifier.fit(X_aug, y_binary)

        self.global_model = RandomForestRegressor(
            n_estimators=300, random_state=self.random_state,
            n_jobs=2, min_samples_leaf=5, max_depth=20,
        )
        if sample_weight is not None:
            self.global_model.fit(X_aug, y_arr, sample_weight=sample_weight)
        else:
            self.global_model.fit(X_aug, y_arr)

        store_col_idx = self.feature_cols_.index("place_id_encoded") if self.feature_cols_ else -3
        store_ids = X_arr[:, store_col_idx]

        for store_id in tqdm(np.unique(store_ids), desc="SoftProb per-store", leave=False):
            mask = store_ids == store_id
            X_store = X_aug[mask]
            y_store = y_arr[mask]
            w_store = sample_weight[mask] if sample_weight is not None else None
            n_store = len(y_store)
            if n_store < 10:
                self.store_weights[store_id] = 1.0
                continue
            store_model = ExtraTreesRegressor(
                n_estimators=200, random_state=self.random_state, n_jobs=1,
                max_depth=15,
            )
            if w_store is not None:
                store_model.fit(X_store, y_store, sample_weight=w_store)
            else:
                store_model.fit(X_store, y_store)
            self.store_models[store_id] = store_model
            frac = min(n_store / self.min_store_samples, 1.0)
            self.store_weights[store_id] = 1.0 - frac * (1.0 - self.base_global_weight)
        return self

    def predict(self, X):
        X_arr = X.values if hasattr(X, "values") else X
        X_aug = self._add_interactions(X)
        proba = self.classifier.predict_proba(X_aug)[:, 1]
        p_weight = np.power(proba, self.prob_exponent)
        global_preds = self.global_model.predict(X_aug)
        result = global_preds.copy()
        store_col_idx = self.feature_cols_.index("place_id_encoded") if self.feature_cols_ else -3
        store_ids = X_arr[:, store_col_idx]
        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            if store_id not in self.store_models:
                continue
            gw = self.store_weights.get(store_id, self.base_global_weight)
            sw = 1.0 - gw
            store_pred = self.store_models[store_id].predict(X_aug[mask])
            result[mask] = sw * store_pred + gw * global_preds[mask]
        result = p_weight * result
        return np.clip(result * self.safety_buffer, 0, None)


# =============================================================================
# 5h. STACKING ENSEMBLE (LGB + XGB + CatBoost meta-learner)
# =============================================================================
class StackingModel:
    """Stacks LGB, XGB, CatBoost with Ridge meta-learner. Safety buffer applied."""
    def __init__(self, safety_buffer=1.15):
        self.safety_buffer = safety_buffer
        self.model = StackingRegressor(
            estimators=[
                ("lgb", lgb.LGBMRegressor(
                    n_estimators=500, learning_rate=0.05, num_leaves=63,
                    n_jobs=-1, random_state=42, verbosity=-1)),
                ("xgb", xgb.XGBRegressor(
                    n_estimators=500, learning_rate=0.05, max_depth=7,
                    tree_method="hist", n_jobs=-1, random_state=42, verbosity=0)),
                ("cb", cb.CatBoostRegressor(
                    iterations=500, learning_rate=0.05, depth=7,
                    random_seed=42, verbose=0)),
            ],
            final_estimator=Ridge(alpha=1.0),
            cv=3,
            n_jobs=-1,
        )

    def fit(self, X, y, sample_weight=None):
        # StackingRegressor doesn't pass sample_weight through cleanly
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return np.clip(self.model.predict(X) * self.safety_buffer, 0, None)


# =============================================================================
# 5i. SIMPLE BLEND (average of LGB + XGB + CatBoost)
# =============================================================================
class BlendModel:
    """Simple average of 3 gradient boosters. Fast, robust."""
    def __init__(self, safety_buffer=1.15):
        self.safety_buffer = safety_buffer
        self.models = [
            lgb.LGBMRegressor(n_estimators=600, learning_rate=0.04, num_leaves=95,
                              n_jobs=2, random_state=42, verbosity=-1),
            xgb.XGBRegressor(n_estimators=600, learning_rate=0.04, max_depth=8,
                             tree_method="hist", n_jobs=2, random_state=42, verbosity=0),
            cb.CatBoostRegressor(iterations=600, learning_rate=0.04, depth=8,
                                 random_seed=42, verbose=0),
        ]

    def fit(self, X, y, sample_weight=None):
        for m in self.models:
            if sample_weight is not None:
                m.fit(X, y, sample_weight=sample_weight)
            else:
                m.fit(X, y)
        return self

    def predict(self, X):
        preds = np.column_stack([m.predict(X) for m in self.models])
        return np.clip(preds.mean(axis=1) * self.safety_buffer, 0, None)


# =============================================================================
# 5j. SOFTPROB V2 (LGB gate + LGB global + per-store LGB local)
# All LightGBM variant - faster than RF+ET combo for 678 stores
# =============================================================================
class SoftProbV2:
    """
    Like SoftProbModel but uses LightGBM for both global and per-store models.
    Much faster for 678 stores. Per-store models use fewer trees.
    """
    def __init__(self, base_global_weight=0.60, min_store_samples=150,
                 random_state=42, safety_buffer=1.25, prob_exponent=0.30):
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

        # Classifier
        self.classifier = lgb.LGBMClassifier(
            n_estimators=500, learning_rate=0.05, num_leaves=63,
            n_jobs=2, random_state=self.random_state, verbosity=-1,
        )
        kw = dict(sample_weight=sample_weight) if sample_weight is not None else {}
        self.classifier.fit(X_arr, y_binary, **kw)

        # Global LGB regressor
        self.global_model = lgb.LGBMRegressor(
            n_estimators=800, learning_rate=0.03, num_leaves=127,
            n_jobs=2, random_state=self.random_state, verbosity=-1,
        )
        self.global_model.fit(X_arr, y_arr, **kw)

        # Per-store LGB regressors (lighter)
        store_col_idx = self.feature_cols_.index("place_id_encoded") if self.feature_cols_ else -3
        store_ids = X_arr[:, store_col_idx]

        for store_id in tqdm(np.unique(store_ids), desc="SoftProbV2 per-store", leave=False):
            mask = store_ids == store_id
            n_store = mask.sum()
            if n_store < 20:
                self.store_weights[store_id] = 1.0
                continue
            store_model = lgb.LGBMRegressor(
                n_estimators=200, learning_rate=0.05, num_leaves=31,
                n_jobs=1, random_state=self.random_state, verbosity=-1,
            )
            w_store = sample_weight[mask] if sample_weight is not None else None
            if w_store is not None:
                store_model.fit(X_arr[mask], y_arr[mask], sample_weight=w_store)
            else:
                store_model.fit(X_arr[mask], y_arr[mask])
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
            if store_id not in self.store_models:
                continue
            gw = self.store_weights.get(store_id, self.base_global_weight)
            sw = 1.0 - gw
            store_pred = self.store_models[store_id].predict(X_arr[mask])
            result[mask] = sw * store_pred + gw * global_preds[mask]
        result = p_weight * result
        return np.clip(result * self.safety_buffer, 0, None)

print("Ensemble models defined: SoftProbModel, SoftProbV2, Stacking, Blend")

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("PyTorch not installed - skipping LSTM model")


print("LSTM model skipped (no GPU locally, tree models only)")

# ---- Phase 1: Recency experiments with LightGBM ----
# Goal: find optimal recency configuration before testing all models

all_results = []

recency_configs = [
    # (train_days, decay_half_life, description)
    (None, None, "LGB full-history no-decay"),
    (None, 6,    "LGB full-history decay=6d"),
    (None, 12,   "LGB full-history decay=12d"),
    (None, 24,   "LGB full-history decay=24d"),
    (60,   None, "LGB window=60d no-decay"),
    (90,   None, "LGB window=90d no-decay"),
    (120,  None, "LGB window=120d no-decay"),
    (90,   12,   "LGB window=90d decay=12d"),
    (120,  12,   "LGB window=120d decay=12d"),
    (120,  24,   "LGB window=120d decay=24d"),
]

print("=" * 70)
print("PHASE 1: RECENCY SWEEP (LightGBM as fixed model)")
print("=" * 70)

for train_days, decay_hl, desc in recency_configs:
    print(f"\n>>> {desc}")
    model = LightGBMModel(safety_buffer=1.15)
    result = run_experiment(model, df, feature_cols, description=desc,
                           train_days=train_days, decay_half_life=decay_hl)
    result["phase"] = "recency"
    all_results.append(result)
    print_results(result)
    del model; gc.collect()

# Find best recency config
phase1_ok = [r for r in all_results if r.get("status") == "ok" and r.get("phase") == "recency"]
best_recency = min(phase1_ok, key=lambda r: r["total_business_cost_dkk"])
print(f"\n{'='*70}")
print(f"BEST RECENCY: {best_recency['description']}")
print(f"  Cost: {best_recency['total_business_cost_dkk']:,.0f} DKK")
BEST_TRAIN_DAYS = best_recency["config"]["train_days"]
BEST_DECAY_HL = best_recency["config"]["decay_half_life"]
print(f"  train_days={BEST_TRAIN_DAYS}, decay_half_life={BEST_DECAY_HL}")
print(f"{'='*70}")

# ---- Phase 2: All models with best recency from Phase 1 ----
# Uses BEST_TRAIN_DAYS and BEST_DECAY_HL from Phase 1

model_configs = [
    ("LightGBM", lambda: LightGBMModel(safety_buffer=1.15)),
    ("XGBoost", lambda: XGBoostModel(safety_buffer=1.15)),
    ("CatBoost", lambda: CatBoostModel(safety_buffer=1.15)),
    # RF/ET/Stacking removed: too slow on 1.4M rows (30+ min each vs ~1min for gradient boosters)
    ("ElasticNet", lambda: ElasticNetModel(safety_buffer=1.20)),
    ("Blend_LGB_XGB_CB", lambda: BlendModel(safety_buffer=1.15)),
    ("SoftProbV2_allLGB", lambda: SoftProbV2(
        base_global_weight=0.60, min_store_samples=150,
        safety_buffer=1.25, prob_exponent=0.30)),
]

print("=" * 70)
print(f"PHASE 2: ALL MODELS (train_days={BEST_TRAIN_DAYS}, decay={BEST_DECAY_HL})")
print("=" * 70)

for name, build_fn in model_configs:
    print(f"\n>>> {name}")
    try:
        model = build_fn()
        desc = f"{name} td={BEST_TRAIN_DAYS} hl={BEST_DECAY_HL}"
        result = run_experiment(model, df, feature_cols, description=desc,
                               train_days=BEST_TRAIN_DAYS, decay_half_life=BEST_DECAY_HL)
        result["phase"] = "model_comparison"
        result["model_name"] = name
        all_results.append(result)
        print_results(result)
    except Exception as e:
        print(f"  FAILED: {e}")
        all_results.append({
            "status": "crash", "error": str(e),
            "description": name, "phase": "model_comparison", "model_name": name
        })
    finally:
        del model; gc.collect()

# Rank models
phase2_ok = [r for r in all_results if r.get("status") == "ok" and r.get("phase") == "model_comparison"]
phase2_ok.sort(key=lambda r: r["total_business_cost_dkk"])

print(f"\n{'='*70}")
print("PHASE 2 RANKING:")
print(f"{'='*70}")
for i, r in enumerate(phase2_ok):
    print(f"  #{i+1}  {r.get('model_name', '?'):25s}  "
          f"Cost: {r['total_business_cost_dkk']:>12,.0f} DKK  "
          f"MAE: {r['mae']:.4f}  Train: {r['timing']['train_s']:.0f}s")

# ---- Phase 3: Safety buffer tuning on top 3 models ----
# The safety buffer trades waste vs stockout. Finding the optimal buffer
# is critical since stockout penalty is 1.5x waste penalty.

top3_names = [r["model_name"] for r in phase2_ok[:3]]
buffer_values = [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40]

# Rebuild model constructors with buffer override
def get_model_with_buffer(name, buffer):
    constructors = {
        "LightGBM": lambda b: LightGBMModel(safety_buffer=b),
        "XGBoost": lambda b: XGBoostModel(safety_buffer=b),
        "CatBoost": lambda b: CatBoostModel(safety_buffer=b),
        "RandomForest": lambda b: RFModel(safety_buffer=b),
        "ExtraTrees": lambda b: ETModel(safety_buffer=b),
        "ElasticNet": lambda b: ElasticNetModel(safety_buffer=b),
        "Blend_LGB_XGB_CB": lambda b: BlendModel(safety_buffer=b),
        "Stacking_LGB_XGB_CB": lambda b: StackingModel(safety_buffer=b),
        "SoftProbModel_v1": lambda b: SoftProbModel(safety_buffer=b),
        "SoftProbV2_allLGB": lambda b: SoftProbV2(safety_buffer=b),
    }
    return constructors[name](buffer)

print("=" * 70)
print("PHASE 3: SAFETY BUFFER SWEEP (top 3 models)")
print("=" * 70)

for name in top3_names:
    print(f"\n--- {name} ---")
    for buf in buffer_values:
        model = get_model_with_buffer(name, buf)
        desc = f"{name} buf={buf:.2f} td={BEST_TRAIN_DAYS} hl={BEST_DECAY_HL}"
        result = run_experiment(model, df, feature_cols, description=desc,
                               train_days=BEST_TRAIN_DAYS, decay_half_life=BEST_DECAY_HL)
        result["phase"] = "buffer_sweep"
        result["model_name"] = name
        result["buffer"] = buf
        all_results.append(result)
        if result.get("status") == "ok":
            print(f"  buf={buf:.2f}  Cost: {result['total_business_cost_dkk']:>12,.0f} DKK  "
                  f"waste: {result['waste_cost_dkk']:>10,.0f}  stockout: {result['stockout_cost_dkk']:>10,.0f}")
        del model; gc.collect()

# Find overall best
phase3_ok = [r for r in all_results if r.get("status") == "ok" and r.get("phase") == "buffer_sweep"]
overall_best = min(phase3_ok, key=lambda r: r["total_business_cost_dkk"])
print(f"\n{'='*70}")
print(f"OVERALL BEST: {overall_best['description']}")
print(f"  Cost: {overall_best['total_business_cost_dkk']:,.0f} DKK")
print(f"  Waste: {overall_best['waste_cost_dkk']:,.0f}  Stockout: {overall_best['stockout_cost_dkk']:,.0f}")
print(f"  MAE: {overall_best['mae']:.4f}  WMAPE: {overall_best['wmape']:.2f}%")
print(f"{'='*70}")

# Save results
with open(RESULTS_FILE, "w") as f:
    json.dump(all_results, f, indent=2, default=str)
print(f"Results saved to {RESULTS_FILE}")

# ---- Visualization: Phase 1 Recency Comparison ----
fig, ax = plt.subplots(figsize=(12, 5))
phase1_data = [r for r in all_results if r.get("status") == "ok" and r.get("phase") == "recency"]
names = [r["description"].replace("LGB ", "") for r in phase1_data]
costs = [r["total_business_cost_dkk"] for r in phase1_data]
colors = ["#2ecc71" if c == min(costs) else "#3498db" for c in costs]
bars = ax.barh(names, costs, color=colors)
ax.set_xlabel("Total Business Cost (DKK)")
ax.set_title("Phase 1: Recency Configuration Comparison")
for bar, cost in zip(bars, costs):
    ax.text(bar.get_width() + max(costs)*0.01, bar.get_y() + bar.get_height()/2,
            f"{cost:,.0f}", va="center", fontsize=9)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "phase1_recency.png", dpi=150)
plt.close('all')

# ---- Visualization: Phase 2 Model Comparison ----
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

phase2_data = sorted(
    [r for r in all_results if r.get("status") == "ok" and r.get("phase") == "model_comparison"],
    key=lambda r: r["total_business_cost_dkk"]
)

# Left: Total cost
names = [r.get("model_name", "?") for r in phase2_data]
costs = [r["total_business_cost_dkk"] for r in phase2_data]
colors = ["#2ecc71" if i == 0 else "#e74c3c" if i == len(costs)-1 else "#3498db" for i in range(len(costs))]
axes[0].barh(names, costs, color=colors)
axes[0].set_xlabel("Total Business Cost (DKK)")
axes[0].set_title("Phase 2: Model Ranking by Business Cost")
for i, (n, c) in enumerate(zip(names, costs)):
    axes[0].text(c + max(costs)*0.01, i, f"{c:,.0f}", va="center", fontsize=8)

# Right: Waste vs Stockout breakdown
waste = [r["waste_cost_dkk"] for r in phase2_data]
stockout = [r["stockout_cost_dkk"] for r in phase2_data]
y = range(len(names))
axes[1].barh(y, waste, label="Waste", color="#f39c12", alpha=0.8)
axes[1].barh(y, [s * STOCKOUT_MULTIPLIER for s in stockout], left=waste,
             label=f"Stockout (x{STOCKOUT_MULTIPLIER})", color="#e74c3c", alpha=0.8)
axes[1].set_yticks(list(y))
axes[1].set_yticklabels(names)
axes[1].set_xlabel("Cost (DKK)")
axes[1].set_title("Waste vs Stockout Breakdown")
axes[1].legend()

plt.tight_layout()
plt.savefig(RESULTS_DIR / "phase2_models.png", dpi=150)
plt.close('all')

# ---- Visualization: Phase 3 Buffer Sweep ----
fig, ax = plt.subplots(figsize=(12, 6))

phase3_data = [r for r in all_results if r.get("status") == "ok" and r.get("phase") == "buffer_sweep"]

for name in top3_names:
    model_data = [r for r in phase3_data if r.get("model_name") == name]
    model_data.sort(key=lambda r: r.get("buffer", 1.0))
    bufs = [r["buffer"] for r in model_data]
    costs = [r["total_business_cost_dkk"] for r in model_data]
    ax.plot(bufs, costs, "o-", label=name, linewidth=2, markersize=6)

ax.set_xlabel("Safety Buffer Multiplier")
ax.set_ylabel("Total Business Cost (DKK)")
ax.set_title("Phase 3: Safety Buffer Optimization")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "phase3_buffer.png", dpi=150)
plt.close('all')

# ---- Retrain best model and evaluate per-store ----
best_name = overall_best.get("model_name", top3_names[0])
best_buffer = overall_best.get("buffer", 1.15)
print(f"Retraining best model: {best_name} (buffer={best_buffer})")

best_model = get_model_with_buffer(best_name, best_buffer)
X_train, y_train, X_test, y_test, prices, item_ids_final, weights = get_train_test(
    df, feature_cols, train_days=BEST_TRAIN_DAYS, decay_half_life=BEST_DECAY_HL
)

sig = inspect.signature(best_model.fit)
if weights is not None and "sample_weight" in sig.parameters:
    best_model.fit(X_train, y_train, sample_weight=weights)
else:
    best_model.fit(X_train, y_train)

preds = best_model.predict(X_test)
preds = np.clip(preds, 0, None)

# Per-store evaluation
test_df = df[df["date"] > df["date"].max() - pd.Timedelta(days=TEST_DAYS)].copy()
lag_cols = [c for c in feature_cols if "lag" in c]
test_df = test_df.dropna(subset=lag_cols, how="all")
test_df["predicted"] = preds
test_df["actual"] = y_test.values

store_metrics = []
for pid in test_df["place_id"].unique():
    mask = test_df["place_id"] == pid
    sub = test_df[mask]
    m = evaluate(sub["actual"], sub["predicted"], sub["item_price"], item_ids=sub["item_id"].values)
    m["place_id"] = pid
    m["n_items"] = sub["item_id"].nunique()
    store_metrics.append(m)

store_df = pd.DataFrame(store_metrics).sort_values("total_business_cost_dkk", ascending=False)

print(f"\nPer-store metrics ({len(store_df)} stores):")
print(f"  Mean cost:   {store_df['total_business_cost_dkk'].mean():,.0f} DKK")
print(f"  Median cost: {store_df['total_business_cost_dkk'].median():,.0f} DKK")
print(f"  Total cost:  {store_df['total_business_cost_dkk'].sum():,.0f} DKK")

print(f"\nTop 10 highest-cost stores:")
print(store_df[["place_id", "total_business_cost_dkk", "waste_cost_dkk", "stockout_cost_dkk", "mae", "n_items"]].head(10).to_string())

print(f"\nTop 10 best-performing stores:")
print(store_df[["place_id", "total_business_cost_dkk", "waste_cost_dkk", "stockout_cost_dkk", "mae", "n_items"]].tail(10).to_string())

# ---- Per-store cost distribution ----
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].hist(store_df["total_business_cost_dkk"], bins=50, color="#3498db", edgecolor="white")
axes[0].axvline(store_df["total_business_cost_dkk"].median(), color="red", linestyle="--", label="Median")
axes[0].set_xlabel("Business Cost per Store (DKK)")
axes[0].set_ylabel("Count")
axes[0].set_title("Distribution of Per-Store Business Cost")
axes[0].legend()

axes[1].scatter(store_df["mae"], store_df["total_business_cost_dkk"],
                alpha=0.5, s=20, c="#e74c3c")
axes[1].set_xlabel("MAE")
axes[1].set_ylabel("Business Cost (DKK)")
axes[1].set_title("MAE vs Business Cost per Store")

plt.tight_layout()
plt.savefig(RESULTS_DIR / "per_store_analysis.png", dpi=150)
plt.close('all')

# ---- Full summary table ----
ok_results = [r for r in all_results if r.get("status") == "ok"]
summary = pd.DataFrame([{
    "phase": r.get("phase", "?"),
    "description": r.get("description", "?"),
    "cost_dkk": r["total_business_cost_dkk"],
    "waste_dkk": r["waste_cost_dkk"],
    "stockout_dkk": r["stockout_cost_dkk"],
    "mae": r["mae"],
    "wmape": r["wmape"],
    "train_s": r["timing"]["train_s"],
    "train_rows": r["config"]["train_rows"],
} for r in ok_results])

summary = summary.sort_values("cost_dkk")
print(f"Total experiments run: {len(all_results)} ({len(ok_results)} successful)")
print(f"\nDemo baseline:     5,133,764 DKK")
print(f"Production best:   {summary['cost_dkk'].min():,.0f} DKK")
improvement = (1 - summary['cost_dkk'].min() / 5_133_764) * 100
print(f"Improvement:       {improvement:.1f}%")
print()
summary