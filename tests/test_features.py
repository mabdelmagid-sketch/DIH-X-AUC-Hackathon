"""Tests for the FeatureEngineer module."""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from src.data.features import FeatureEngineer


@pytest.fixture
def sample_daily_sales():
    """Create a small daily sales DataFrame for testing."""
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    items = ["Coffee", "Tea"]
    rows = []
    for item in items:
        for d in dates:
            rows.append({
                "date": d,
                "item_title": item,
                "total_quantity": np.random.randint(5, 50),
                "total_revenue": np.random.uniform(50, 500),
                "order_count": np.random.randint(1, 20),
            })
    return pd.DataFrame(rows)


class TestTimeFeatures:
    def test_creates_time_columns(self, sample_daily_sales):
        fe = FeatureEngineer()
        result = fe.create_time_features(sample_daily_sales, "date")

        expected_cols = [
            "day_of_week", "day_of_month", "month", "week_of_year",
            "is_weekend", "is_month_start", "is_month_end", "quarter",
            "day_of_week_sin", "day_of_week_cos", "month_sin", "month_cos"
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_is_weekend_values(self, sample_daily_sales):
        fe = FeatureEngineer()
        result = fe.create_time_features(sample_daily_sales, "date")
        assert set(result["is_weekend"].unique()).issubset({0, 1})


class TestLagFeatures:
    def test_creates_lag_columns(self, sample_daily_sales):
        fe = FeatureEngineer()
        result = fe.create_lag_features(
            sample_daily_sales, "total_quantity", "item_title", lags=[1, 7]
        )
        assert "total_quantity_lag_1" in result.columns
        assert "total_quantity_lag_7" in result.columns

    def test_lag_values_are_shifted(self):
        fe = FeatureEngineer()
        df = pd.DataFrame({
            "val": [10, 20, 30, 40, 50]
        })
        result = fe.create_lag_features(df, "val", lags=[1, 2])
        assert pd.isna(result["val_lag_1"].iloc[0])
        assert result["val_lag_1"].iloc[1] == 10
        assert result["val_lag_2"].iloc[2] == 10


class TestRollingFeatures:
    def test_creates_rolling_columns(self, sample_daily_sales):
        fe = FeatureEngineer()
        result = fe.create_rolling_features(
            sample_daily_sales, "total_quantity", windows=[7]
        )
        assert "total_quantity_rolling_mean_7" in result.columns
        assert "total_quantity_rolling_std_7" in result.columns
        assert "total_quantity_rolling_max_7" in result.columns
        assert "total_quantity_rolling_min_7" in result.columns


class TestBuildForecastFeatures:
    def test_full_pipeline(self, sample_daily_sales):
        fe = FeatureEngineer()
        result = fe.build_forecast_features(sample_daily_sales)

        assert len(fe.feature_columns) > 10
        assert "total_quantity" not in fe.feature_columns
        assert "date" not in fe.feature_columns
        assert "item_title" not in fe.feature_columns

    def test_prepare_training_data(self, sample_daily_sales):
        fe = FeatureEngineer()
        featured = fe.build_forecast_features(sample_daily_sales)
        X, y = fe.prepare_training_data(featured)

        assert len(X) > 0
        assert len(X) == len(y)
        assert X.shape[1] == len(fe.feature_columns)
        assert not X.isnull().any().any()
