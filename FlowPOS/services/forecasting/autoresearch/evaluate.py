"""
Fixed evaluation harness for autoresearch. DO NOT MODIFY.

Loads data once, caches to disk, evaluates any model that implements
fit(X_train, y_train) and predict(X_test) -> array.

Metric: total_business_cost_dkk (lower is better)
  = waste_cost + 1.5 * stockout_cost

Usage:
    from evaluate import run_experiment
    # In experiment.py, define build_model() -> model with fit/predict
"""

import os
import sys
import time
import json
import pickle
import hashlib
import warnings
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "demo"
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_FILE = CACHE_DIR / "prepared_data.pkl"

# Fixed constants
TOP_N_ITEMS = 30
TEST_DAYS = 14
WASTE_FRACTION = 0.3
STOCKOUT_MULTIPLIER = 1.5


def _load_and_prepare():
    """Load CSVs, aggregate, feature engineer. Cached to disk."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "rb") as f:
            return pickle.load(f)

    logger.info("Preparing data (first run, will be cached)...")

    orders = pd.read_csv(DATA_DIR / "fct_orders.csv", low_memory=False)
    items = pd.read_csv(DATA_DIR / "fct_order_items.csv", low_memory=False)
    dim_items = pd.read_csv(DATA_DIR / "dim_items.csv", low_memory=False)

    orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
    orders = orders.dropna(subset=["created_dt"])
    orders["date"] = orders["created_dt"].dt.normalize()

    merged = items.merge(
        orders[["id", "place_id", "date"]],
        left_on="order_id", right_on="id",
        how="inner", suffixes=("", "_order"),
    )

    daily = merged.groupby(["date", "place_id", "item_id"]).agg(
        quantity_sold=("quantity", "sum"),
        revenue=("cost", "sum"),
    ).reset_index()

    item_prices = dim_items[["id", "price"]].drop_duplicates(subset=["id"]).rename(
        columns={"id": "item_id", "price": "item_price"}
    )
    daily = daily.merge(item_prices, on="item_id", how="left")
    daily["item_price"] = daily["item_price"].fillna(75.0)

    top = (
        daily.groupby(["place_id", "item_id"])["quantity_sold"]
        .sum().reset_index()
        .sort_values(["place_id", "quantity_sold"], ascending=[True, False])
        .groupby("place_id").head(TOP_N_ITEMS)
    )
    top_pairs = set(zip(top["place_id"], top["item_id"]))
    daily = daily[daily.apply(lambda r: (r["place_id"], r["item_id"]) in top_pairs, axis=1)].copy()

    min_date, max_date = daily["date"].min(), daily["date"].max()
    all_dates = pd.date_range(min_date, max_date, freq="D")

    grids = []
    for (pid, iid) in top_pairs:
        price = daily[(daily["place_id"] == pid) & (daily["item_id"] == iid)]["item_price"].mode()
        price = price.iloc[0] if len(price) > 0 else 75.0
        grids.append(pd.DataFrame({
            "date": all_dates, "place_id": pid, "item_id": iid, "item_price": price,
        }))

    full = pd.concat(grids, ignore_index=True)
    full = full.merge(daily[["date", "place_id", "item_id", "quantity_sold", "revenue"]],
                      on=["date", "place_id", "item_id"], how="left")
    full["quantity_sold"] = full["quantity_sold"].fillna(0)
    full["revenue"] = full["revenue"].fillna(0)
    full = full.sort_values(["place_id", "item_id", "date"]).reset_index(drop=True)

    df = full.copy()

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
    df["season"] = df["month"].map({12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1,
                                     6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3})
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Lag features
    grp = ["place_id", "item_id"]
    for lag in [1, 7, 14, 28]:
        df[f"demand_lag_{lag}d"] = df.groupby(grp, observed=True)["quantity_sold"].shift(lag)

    df["demand_same_weekday_last_week"] = df.groupby(grp, observed=True)["quantity_sold"].shift(7)

    # Rolling features
    for window in [7, 14, 30]:
        shifted = df.groupby(grp, observed=True)["quantity_sold"].shift(1)
        df[f"rolling_mean_{window}d"] = shifted.groupby(
            [df["place_id"], df["item_id"]], observed=True
        ).transform(lambda x: x.rolling(window, min_periods=1).mean())

    for window in [7, 14]:
        shifted = df.groupby(grp, observed=True)["quantity_sold"].shift(1)
        df[f"rolling_std_{window}d"] = shifted.groupby(
            [df["place_id"], df["item_id"]], observed=True
        ).transform(lambda x: x.rolling(window, min_periods=2).std())

    df["demand_same_weekday_avg_4weeks"] = df.groupby(grp, observed=True)["quantity_sold"].transform(
        lambda x: x.shift(7).rolling(4, min_periods=1).mean()
    )

    df["expanding_mean"] = df.groupby(grp, observed=True)["quantity_sold"].expanding().mean().reset_index(
        level=[0, 1], drop=True
    )

    # Trend features
    df["days_since_start"] = (df["date"] - df["date"].min()).dt.days
    df["demand_1w_ago"] = df.groupby(grp, observed=True)["quantity_sold"].shift(7)
    df["demand_2w_ago"] = df.groupby(grp, observed=True)["quantity_sold"].shift(14)
    df["wow_growth"] = ((df["demand_1w_ago"] - df["demand_2w_ago"]) / df["demand_2w_ago"].clip(lower=0.1)).clip(-5, 5).fillna(0)
    df["recent_vs_expanding"] = (df["rolling_mean_7d"] / df["expanding_mean"].clip(lower=0.01)).clip(0, 10).fillna(1)

    # Holiday features (Danish holidays in this date range)
    danish_holidays = {'2023-12-24', '2023-12-25', '2023-12-26', '2023-12-31', '2024-01-01'}
    df["is_holiday"] = df["date"].dt.strftime("%Y-%m-%d").isin(danish_holidays).astype(int)
    df["days_from_holiday"] = df["date"].apply(
        lambda d: min(abs((d - pd.Timestamp(h)).days) for h in danish_holidays)
    )
    df["near_holiday"] = (df["days_from_holiday"] <= 2).astype(int)

    # Fourier weekly harmonics
    for k in [1, 2, 3]:
        df[f"fourier_week_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_week"] / 7)
        df[f"fourier_week_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_week"] / 7)

    # Categorical encoding
    le_place = LabelEncoder()
    le_item = LabelEncoder()
    df["place_id_encoded"] = le_place.fit_transform(df["place_id"].astype(str))
    df["item_id_encoded"] = le_item.fit_transform(df["item_id"].astype(str))
    df["store_dow_interaction"] = df["place_id_encoded"] * 10 + df["day_of_week"]

    # Stub features
    for col in ["temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
                 "is_promotion_active", "discount_percentage", "campaign_count"]:
        if col not in df.columns:
            df[col] = 0
    df["is_open"] = 1

    # Feature columns (the full set available to the agent)
    feature_cols = [
        # Time
        "day_of_week", "day_of_month", "month", "quarter", "week_of_year",
        "day_of_year", "year", "is_weekend", "is_friday", "is_monday",
        "season", "dow_sin", "dow_cos", "month_sin", "month_cos",
        # Lag
        "demand_lag_1d", "demand_lag_7d", "demand_lag_14d", "demand_lag_28d",
        "demand_same_weekday_last_week", "demand_same_weekday_avg_4weeks",
        # Rolling
        "rolling_mean_7d", "rolling_mean_14d", "rolling_mean_30d",
        "rolling_std_7d", "rolling_std_14d", "expanding_mean",
        # Trend
        "days_since_start", "wow_growth", "recent_vs_expanding",
        # Seasonality
        "fourier_week_sin_1", "fourier_week_cos_1",
        "fourier_week_sin_2", "fourier_week_cos_2",
        "fourier_week_sin_3", "fourier_week_cos_3",
        # External
        "is_holiday", "days_from_holiday", "near_holiday",
        "temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
        "is_promotion_active", "discount_percentage", "campaign_count",
        "is_open",
        # Categorical
        "place_id_encoded", "item_id_encoded", "store_dow_interaction",
    ]

    data = {
        "df": df,
        "feature_cols": feature_cols,
        "n_store_item_pairs": len(top_pairs),
        "n_days": len(all_dates),
        "date_range": (min_date, max_date),
    }

    with open(CACHE_FILE, "wb") as f:
        pickle.dump(data, f)

    logger.info(f"Data cached: {len(df):,} rows, {len(top_pairs)} pairs, {len(all_dates)} days")
    return data


def get_data():
    """Return the prepared data dict. Loads from cache if available."""
    return _load_and_prepare()


def get_train_test(data, test_days=TEST_DAYS, train_days=None, decay_half_life=None):
    """Split data into train/test with optional recency controls.

    Args:
        data: Output of get_data().
        test_days: Number of days for test set.
        train_days: If set, only use the last N days for training. None = use all.
        decay_half_life: If set, compute exponential decay sample weights.

    Returns:
        X_train, y_train, X_test, y_test, prices_test, sample_weights (or None)
    """
    df = data["df"]
    feature_cols = data["feature_cols"]

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

    # Optional: exponential decay weights
    weights = None
    if decay_half_life is not None:
        days_ago = (test_cutoff - train["date"]).dt.days
        weights = np.exp(-np.log(2) * days_ago / decay_half_life)
        weights = weights / weights.mean()

    return X_train, y_train, X_test, y_test, prices_test, weights


def evaluate(y_actual, y_predicted, prices):
    """Compute the business cost metric. Returns dict."""
    actual = np.array(y_actual, dtype=float)
    predicted = np.clip(np.array(y_predicted, dtype=float), 0, None)
    prices = np.array(prices, dtype=float)

    mae = np.abs(actual - predicted).mean()
    rmse = np.sqrt(np.mean((actual - predicted) ** 2))
    total_actual = actual.sum()
    wmape = np.sum(np.abs(actual - predicted)) / max(total_actual, 1) * 100

    overstock = np.maximum(predicted - actual, 0)
    understock = np.maximum(actual - predicted, 0)
    waste_cost = (overstock * prices * WASTE_FRACTION).sum()
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
        "overstock_days_pct": round((predicted > actual).mean() * 100, 2),
        "understock_days_pct": round((predicted < actual).mean() * 100, 2),
        "n_samples": len(actual),
    }


def run_experiment(build_model_fn, description="", train_days=None, decay_half_life=None):
    """Run a single experiment end-to-end.

    Args:
        build_model_fn: Callable that returns a model with fit(X, y, sample_weight=None)
                        and predict(X) -> array interface.
        description: Short text describing this experiment.
        train_days: Optional training window (days). None = full history.
        decay_half_life: Optional exponential decay half-life (days).

    Returns:
        Dict with all metrics + timing.
    """
    t_start = time.time()

    data = get_data()
    X_train, y_train, X_test, y_test, prices, weights = get_train_test(
        data, train_days=train_days, decay_half_life=decay_half_life
    )

    t_data = time.time()

    model = build_model_fn()

    t_build = time.time()

    # Train
    try:
        if weights is not None and hasattr(model, 'fit'):
            import inspect
            sig = inspect.signature(model.fit)
            if 'sample_weight' in sig.parameters:
                model.fit(X_train, y_train, sample_weight=weights)
            else:
                model.fit(X_train, y_train)
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

    t_predict = time.time()

    # Evaluate
    metrics = evaluate(y_test, predictions, prices)
    metrics["status"] = "ok"
    metrics["description"] = description
    metrics["timing"] = {
        "data_s": round(t_data - t_start, 2),
        "build_s": round(t_build - t_data, 2),
        "train_s": round(t_train - t_build, 2),
        "predict_s": round(t_predict - t_train, 2),
        "total_s": round(t_predict - t_start, 2),
    }
    metrics["config"] = {
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "n_features": len(data["feature_cols"]),
        "train_days": train_days,
        "decay_half_life": decay_half_life,
    }

    return metrics


def print_results(results):
    """Pretty-print experiment results."""
    if results.get("status") == "crash":
        print(f"CRASH: {results.get('error', 'unknown')}")
        return

    print("---")
    print(f"total_business_cost_dkk: {results['total_business_cost_dkk']:.2f}")
    print(f"waste_cost_dkk:          {results['waste_cost_dkk']:.2f}")
    print(f"stockout_cost_dkk:       {results['stockout_cost_dkk']:.2f}")
    print(f"mae:                     {results['mae']:.6f}")
    print(f"wmape:                   {results['wmape']:.4f}")
    print(f"forecast_accuracy_pct:   {results['forecast_accuracy_pct']:.4f}")
    print(f"train_seconds:           {results['timing']['train_s']:.1f}")
    print(f"total_seconds:           {results['timing']['total_s']:.1f}")
    print(f"train_rows:              {results['config']['train_rows']}")
    print(f"test_rows:               {results['config']['test_rows']}")
    print(f"description:             {results.get('description', '')}")


if __name__ == "__main__":
    # Quick test: just load data and verify cache works
    data = get_data()
    print(f"Data loaded: {len(data['df']):,} rows, {len(data['feature_cols'])} features")
