"""
Shared benchmark harness for evaluating forecasting models.

Each team member should:
1. Import this module
2. Implement their model with fit(X_train, y_train) and predict(X_test) interface
3. Call run_benchmark(model, model_name) to get standardized results

The harness loads data, engineers features, splits train/test, and evaluates
using both standard metrics (MAE, RMSE, WMAPE) and business-impact metrics (DKK).
"""

import sys
import time
import json
import logging
import warnings
from pathlib import Path

import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "demo"
RESULTS_DIR = BASE_DIR / "benchmark_results"
RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Data loading & feature engineering
# ---------------------------------------------------------------------------

def load_and_prepare_data(top_n_items: int = 30):
    """Load CSVs, aggregate daily demand, create features.

    Returns:
        df: Full feature DataFrame with columns including 'quantity_sold',
            'place_id', 'item_id', 'date', 'item_price', and all features.
        feature_cols: List of feature column names for modeling.
    """
    logger.info("Loading data...")
    orders = pd.read_csv(DATA_DIR / "fct_orders.csv", low_memory=False)
    items = pd.read_csv(DATA_DIR / "fct_order_items.csv", low_memory=False)
    dim_items = pd.read_csv(DATA_DIR / "dim_items.csv", low_memory=False)

    # Convert timestamps
    orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
    orders = orders.dropna(subset=["created_dt"])
    orders["date"] = orders["created_dt"].dt.normalize()

    # Join order items with orders
    merged = items.merge(
        orders[["id", "place_id", "date"]],
        left_on="order_id", right_on="id",
        how="inner", suffixes=("", "_order"),
    )

    # Aggregate daily demand per (place, item)
    daily = merged.groupby(["date", "place_id", "item_id"]).agg(
        quantity_sold=("quantity", "sum"),
        revenue=("cost", "sum"),
    ).reset_index()

    # Get item prices
    item_prices = dim_items[["id", "price"]].drop_duplicates(subset=["id"]).rename(
        columns={"id": "item_id", "price": "item_price"}
    )
    daily = daily.merge(item_prices, on="item_id", how="left")
    daily["item_price"] = daily["item_price"].fillna(75.0)

    # Focus on top N items per store (by total volume)
    top = (
        daily.groupby(["place_id", "item_id"])["quantity_sold"]
        .sum().reset_index()
        .sort_values(["place_id", "quantity_sold"], ascending=[True, False])
        .groupby("place_id").head(top_n_items)
    )
    top_pairs = set(zip(top["place_id"], top["item_id"]))
    daily = daily[daily.apply(lambda r: (r["place_id"], r["item_id"]) in top_pairs, axis=1)].copy()

    # Create complete date grid (fill missing days with 0)
    min_date, max_date = daily["date"].min(), daily["date"].max()
    all_dates = pd.date_range(min_date, max_date, freq="D")

    grids = []
    for (pid, iid) in top_pairs:
        price = daily[(daily["place_id"] == pid) & (daily["item_id"] == iid)]["item_price"].mode()
        price = price.iloc[0] if len(price) > 0 else 75.0
        grid = pd.DataFrame({
            "date": all_dates, "place_id": pid, "item_id": iid, "item_price": price,
        })
        grids.append(grid)

    full = pd.concat(grids, ignore_index=True)
    full = full.merge(daily[["date", "place_id", "item_id", "quantity_sold", "revenue"]],
                      on=["date", "place_id", "item_id"], how="left")
    full["quantity_sold"] = full["quantity_sold"].fillna(0)
    full["revenue"] = full["revenue"].fillna(0)
    full = full.sort_values(["place_id", "item_id", "date"]).reset_index(drop=True)

    logger.info(f"Data: {len(full):,} rows, {len(top_pairs)} store-item pairs, "
                f"{len(all_dates)} days ({min_date.date()} to {max_date.date()})")

    # --- Feature Engineering ---
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

    # Lag features (per place-item group)
    grp = ["place_id", "item_id"]
    for lag in [1, 7, 14, 28]:
        df[f"demand_lag_{lag}d"] = df.groupby(grp, observed=True)["quantity_sold"].shift(lag)

    df["demand_same_weekday_last_week"] = df.groupby(grp, observed=True)["quantity_sold"].shift(7)

    # Rolling features
    for window in [7, 14, 30]:
        shifted = df.groupby(grp, observed=True)["quantity_sold"].shift(1)
        col = f"rolling_mean_{window}d"
        df[col] = shifted.groupby([df["place_id"], df["item_id"]], observed=True).transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )

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

    # Encode categoricals
    le_place = LabelEncoder()
    le_item = LabelEncoder()
    df["place_id_encoded"] = le_place.fit_transform(df["place_id"].astype(str))
    df["item_id_encoded"] = le_item.fit_transform(df["item_id"].astype(str))

    # Stub features for weather/holiday/promotion (0 = unknown)
    for col in ["temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
                 "is_holiday", "is_day_before_holiday", "is_day_after_holiday",
                 "is_promotion_active", "discount_percentage", "campaign_count", "is_open"]:
        if col not in df.columns:
            df[col] = 0
    df["is_open"] = 1

    # Feature columns
    feature_cols = [
        "day_of_week", "day_of_month", "month", "quarter", "week_of_year",
        "day_of_year", "year", "is_weekend", "is_friday", "is_monday",
        "season", "dow_sin", "dow_cos", "month_sin", "month_cos",
        "demand_lag_1d", "demand_lag_7d", "demand_lag_14d", "demand_lag_28d",
        "rolling_mean_7d", "rolling_mean_14d", "rolling_mean_30d",
        "rolling_std_7d", "rolling_std_14d",
        "demand_same_weekday_last_week", "demand_same_weekday_avg_4weeks",
        "expanding_mean",
        "temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
        "is_holiday", "is_day_before_holiday", "is_day_after_holiday",
        "is_promotion_active", "discount_percentage", "campaign_count",
        "is_open",
        "place_id_encoded", "item_id_encoded",
    ]

    return df, feature_cols


def train_test_split_temporal(df, feature_cols, test_days=14):
    """Split data temporally: last `test_days` days as test set.

    Returns:
        X_train, y_train, X_test, y_test, test_df (full test DataFrame for evaluation)
    """
    max_date = df["date"].max()
    cutoff = max_date - pd.Timedelta(days=test_days)

    train = df[df["date"] <= cutoff].copy()
    test = df[df["date"] > cutoff].copy()

    # Drop rows where lag features are all NaN (early days)
    lag_cols = [c for c in feature_cols if "lag" in c]
    if lag_cols:
        train = train.dropna(subset=lag_cols, how="all")
        test = test.dropna(subset=lag_cols, how="all")

    X_train = train[feature_cols].fillna(0)
    y_train = train["quantity_sold"].fillna(0)
    X_test = test[feature_cols].fillna(0)
    y_test = test["quantity_sold"].fillna(0)

    logger.info(f"Train: {len(X_train):,} rows (up to {cutoff.date()}), "
                f"Test: {len(X_test):,} rows ({test_days} days)")

    return X_train, y_train, X_test, y_test, test


# ---------------------------------------------------------------------------
# Evaluation metrics
# ---------------------------------------------------------------------------

def evaluate(y_actual, y_predicted, prices=None):
    """Compute standard + business metrics.

    Returns dict with MAE, RMSE, WMAPE, forecast accuracy, waste cost, stockout cost, total cost.
    """
    actual = np.array(y_actual, dtype=float)
    predicted = np.clip(np.array(y_predicted, dtype=float), 0, None)

    if prices is None:
        prices = np.full(len(actual), 75.0)
    else:
        prices = np.array(prices, dtype=float)

    mae = np.abs(actual - predicted).mean()
    rmse = np.sqrt(np.mean((actual - predicted) ** 2))

    total_actual = actual.sum()
    wmape = np.sum(np.abs(actual - predicted)) / max(total_actual, 1) * 100
    forecast_accuracy = max(0, 100 - wmape)

    # Business costs
    overstock = np.maximum(predicted - actual, 0)
    understock = np.maximum(actual - predicted, 0)
    waste_cost = (overstock * prices * 0.3).sum()
    stockout_cost = (understock * prices).sum()
    total_cost = waste_cost + 1.5 * stockout_cost

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wmape": round(wmape, 2),
        "forecast_accuracy_pct": round(forecast_accuracy, 2),
        "waste_cost_dkk": round(waste_cost, 0),
        "stockout_cost_dkk": round(stockout_cost, 0),
        "total_business_cost_dkk": round(total_cost, 0),
        "overstock_units": round(overstock.sum(), 0),
        "understock_units": round(understock.sum(), 0),
        "overstock_days_pct": round((predicted > actual).mean() * 100, 1),
        "understock_days_pct": round((predicted < actual).mean() * 100, 1),
        "n_samples": len(actual),
    }


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(model, model_name: str, top_n_items: int = 30, test_days: int = 14):
    """Run a complete benchmark for a model.

    The model must implement:
        model.fit(X_train: pd.DataFrame, y_train: pd.Series)
        model.predict(X_test: pd.DataFrame) -> array-like

    Args:
        model: Model instance with fit/predict interface.
        model_name: Human-readable name for results.
        top_n_items: Top N items per store to include.
        test_days: Number of days for test set.

    Returns:
        Dict with metrics and timing info.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"BENCHMARKING: {model_name}")
    logger.info(f"{'='*60}")

    # Load data
    t0 = time.time()
    df, feature_cols = load_and_prepare_data(top_n_items)
    data_time = time.time() - t0

    # Split
    X_train, y_train, X_test, y_test, test_df = train_test_split_temporal(df, feature_cols, test_days)

    # Train
    t1 = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - t1
    logger.info(f"Training time: {train_time:.1f}s")

    # Predict
    t2 = time.time()
    predictions = model.predict(X_test)
    predict_time = time.time() - t2
    predictions = np.clip(np.array(predictions, dtype=float), 0, None)

    # Evaluate
    prices = test_df["item_price"].values if "item_price" in test_df.columns else None
    metrics = evaluate(y_test, predictions, prices)

    result = {
        "model_name": model_name,
        "metrics": metrics,
        "timing": {
            "data_prep_s": round(data_time, 1),
            "train_s": round(train_time, 1),
            "predict_s": round(predict_time, 3),
        },
        "config": {
            "top_n_items": top_n_items,
            "test_days": test_days,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "n_features": len(feature_cols),
        },
    }

    # Print results
    m = metrics
    logger.info(f"\n--- Results: {model_name} ---")
    logger.info(f"  MAE:              {m['mae']:.4f}")
    logger.info(f"  RMSE:             {m['rmse']:.4f}")
    logger.info(f"  WMAPE:            {m['wmape']:.2f}%")
    logger.info(f"  Forecast Accuracy:{m['forecast_accuracy_pct']:.2f}%")
    logger.info(f"  Waste Cost:       {m['waste_cost_dkk']:,.0f} DKK")
    logger.info(f"  Stockout Cost:    {m['stockout_cost_dkk']:,.0f} DKK")
    logger.info(f"  Total Biz Cost:   {m['total_business_cost_dkk']:,.0f} DKK")
    logger.info(f"  Train time:       {train_time:.1f}s")

    # Save results
    results_file = RESULTS_DIR / f"{model_name.replace(' ', '_').lower()}.json"
    with open(results_file, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"Results saved to {results_file}")

    return result


# ---------------------------------------------------------------------------
# Baselines (for comparison)
# ---------------------------------------------------------------------------

class MA7Baseline:
    """Moving Average 7-day baseline."""
    def __init__(self):
        self.name = "MA7"

    def fit(self, X_train, y_train):
        pass  # No fitting needed

    def predict(self, X_test):
        # Use rolling_mean_7d feature
        if "rolling_mean_7d" in X_test.columns:
            return X_test["rolling_mean_7d"].fillna(0).values
        return np.zeros(len(X_test))


class NaiveLastWeekBaseline:
    """Naive last-week-same-day baseline."""
    def __init__(self):
        self.name = "NaiveLastWeek"

    def fit(self, X_train, y_train):
        pass

    def predict(self, X_test):
        if "demand_lag_7d" in X_test.columns:
            return X_test["demand_lag_7d"].fillna(0).values
        return np.zeros(len(X_test))


class ZeroBaseline:
    """Always predict 0 (worst case)."""
    def __init__(self):
        self.name = "Zero"

    def fit(self, X_train, y_train):
        pass

    def predict(self, X_test):
        return np.zeros(len(X_test))


def run_all_baselines():
    """Run baselines and save for comparison."""
    baselines = [MA7Baseline(), NaiveLastWeekBaseline(), ZeroBaseline()]
    results = {}
    for bl in baselines:
        r = run_benchmark(bl, bl.name)
        results[bl.name] = r
    return results


if __name__ == "__main__":
    # When run directly, compute baselines
    run_all_baselines()
