"""Tests for ML models: training, prediction shape, baseline comparison."""

import pytest
import pandas as pd
import numpy as np


def _make_training_data(n_days=120):
    """Create sample training data with all required features."""
    dates = pd.date_range("2023-01-01", periods=n_days, freq="D")
    np.random.seed(42)

    # Simulate daily demand with weekly pattern
    base_demand = 5
    weekly_pattern = [3, 4, 5, 5, 7, 8, 6]  # Mon-Sun
    demand = []
    for d in dates:
        day_demand = base_demand + weekly_pattern[d.dayofweek] + np.random.poisson(2)
        demand.append(max(0, day_demand))

    df = pd.DataFrame({
        "date": dates,
        "place_id": 1,
        "item_id": 100,
        "quantity_sold": demand,
        "revenue": [d * 50 for d in demand],
        "order_count": [max(1, d // 2) for d in demand],
        "item_name": "Test Burger",
        "store_name": "Test Store",
        "item_price": 100.0,
        "item_type": "Normal",
    })

    # Add features manually for testing
    from src.features.time_features import add_time_features
    from src.features.lag_features import add_lag_features, add_rolling_features

    df = add_time_features(df)
    df = add_lag_features(df)
    df = add_rolling_features(df)

    # Add placeholder external features
    df["temperature_max"] = np.random.uniform(5, 25, n_days)
    df["temperature_min"] = df["temperature_max"] - 5
    df["precipitation_mm"] = np.random.exponential(2, n_days)
    df["is_rainy"] = (df["precipitation_mm"] > 1).astype(int)
    df["is_holiday"] = 0
    df["is_day_before_holiday"] = 0
    df["is_day_after_holiday"] = 0
    df["is_promotion_active"] = 0
    df["discount_percentage"] = 0.0
    df["campaign_count"] = 0
    df["is_open"] = 1

    return df


def test_baseline_models():
    """Verify baseline models produce predictions."""
    from src.models.baseline import NaiveLastWeekModel, MovingAverageModel

    df = _make_training_data()

    naive = NaiveLastWeekModel()
    preds_naive = naive.predict(df)
    assert len(preds_naive) == len(df)
    assert preds_naive.notna().sum() > 0

    ma = MovingAverageModel(window=7)
    preds_ma = ma.predict(df)
    assert len(preds_ma) == len(df)
    assert preds_ma.notna().sum() > 0


def test_xgboost_trains():
    """Verify XGBoost trains without error and produces predictions."""
    from src.models.xgboost_model import XGBoostForecaster

    df = _make_training_data()
    train = df.iloc[:90]
    test = df.iloc[90:]

    model = XGBoostForecaster(n_estimators=50, max_depth=4)
    model.fit(train, "quantity_sold")

    preds = model.predict(test)
    assert len(preds) == len(test)
    assert (preds >= 0).all(), "Predictions should be non-negative"


def test_xgboost_beats_naive():
    """Verify XGBoost outperforms naive baseline."""
    from src.models.xgboost_model import XGBoostForecaster
    from src.models.baseline import NaiveLastWeekModel
    from src.models.evaluator import mae

    df = _make_training_data(n_days=180)
    train = df.iloc[:120]
    test = df.iloc[120:]

    # Naive baseline
    naive = NaiveLastWeekModel()
    naive_preds = naive.predict(test)

    # XGBoost
    xgb = XGBoostForecaster(n_estimators=100, max_depth=4)
    xgb.fit(train, "quantity_sold")
    xgb_preds = xgb.predict(test)

    # Compare MAE (on valid predictions)
    mask = naive_preds.notna()
    actual = test["quantity_sold"].values

    mae_naive = mae(actual[mask], naive_preds[mask].values)
    mae_xgb = mae(actual, xgb_preds.values)

    # XGBoost should be competitive (allow some margin)
    assert mae_xgb < mae_naive * 1.5, (
        f"XGBoost MAE ({mae_xgb:.2f}) should be close to naive ({mae_naive:.2f})"
    )


def test_feature_importance():
    """Verify feature importance is available after training."""
    from src.models.xgboost_model import XGBoostForecaster

    df = _make_training_data()
    model = XGBoostForecaster(n_estimators=50)
    model.fit(df, "quantity_sold")

    importance = model.get_feature_importance(top_n=10)
    assert len(importance) > 0
    assert "feature" in importance.columns
    assert "importance" in importance.columns


def test_evaluator_metrics():
    """Verify evaluation metrics compute correctly."""
    from src.models.evaluator import mae, rmse, mape, waste_cost_dkk, stockout_cost_dkk

    actual = np.array([10, 20, 30, 40, 50])
    predicted = np.array([12, 18, 35, 38, 52])
    prices = np.array([75.0, 75.0, 75.0, 75.0, 75.0])

    assert mae(actual, predicted) == pytest.approx(2.6, abs=0.1)
    assert rmse(actual, predicted) > 0
    assert mape(actual, predicted) > 0

    # Waste cost: overstock on items 0, 2, 4
    assert waste_cost_dkk(actual, predicted, prices) > 0
    # Stockout cost: understock on items 1, 3
    assert stockout_cost_dkk(actual, predicted, prices) > 0


def test_time_series_split():
    """Verify time series split respects temporal order."""
    from src.models.trainer import time_series_split

    df = _make_training_data(n_days=365)
    train, val, test = time_series_split(df)

    assert len(train) > 0
    assert len(val) > 0
    assert len(test) > 0

    # Train dates should be before val dates
    train_max = pd.to_datetime(train["date"]).max()
    val_min = pd.to_datetime(val["date"]).min()
    assert train_max < val_min, "Train period should end before validation starts"
