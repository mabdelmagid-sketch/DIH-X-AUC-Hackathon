"""Tests for feature engineering modules."""

import pytest
import pandas as pd
import numpy as np
from datetime import date


def _make_sample_df():
    """Create a small sample DataFrame for testing."""
    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    np.random.seed(42)
    df = pd.DataFrame({
        "date": dates,
        "place_id": 1,
        "item_id": 100,
        "quantity_sold": np.random.poisson(5, size=60).astype(float),
        "revenue": np.random.uniform(50, 200, size=60),
    })
    return df


def test_time_features():
    """Verify time features are correctly added."""
    from src.features.time_features import add_time_features

    df = _make_sample_df()
    result = add_time_features(df, date_col="date")

    assert "day_of_week" in result.columns
    assert "month" in result.columns
    assert "is_weekend" in result.columns
    assert "is_friday" in result.columns
    assert "season" in result.columns
    assert "dow_sin" in result.columns

    # Check ranges
    assert result["day_of_week"].min() >= 0
    assert result["day_of_week"].max() <= 6
    assert result["month"].min() >= 1
    assert result["month"].max() <= 12
    assert set(result["is_weekend"].unique()) <= {0, 1}


def test_lag_features():
    """Verify lag features are computed correctly."""
    from src.features.lag_features import add_lag_features

    df = _make_sample_df()
    result = add_lag_features(df)

    assert "demand_lag_1d" in result.columns
    assert "demand_lag_7d" in result.columns
    assert "demand_lag_14d" in result.columns
    assert "demand_lag_28d" in result.columns

    # Lag-1 should equal the previous day's value
    for i in range(1, len(result)):
        if pd.notna(result.iloc[i]["demand_lag_1d"]):
            assert result.iloc[i]["demand_lag_1d"] == result.iloc[i - 1]["quantity_sold"]


def test_rolling_features():
    """Verify rolling statistics are computed correctly."""
    from src.features.lag_features import add_rolling_features

    df = _make_sample_df()
    result = add_rolling_features(df)

    assert "rolling_mean_7d" in result.columns
    assert "rolling_std_7d" in result.columns
    assert "expanding_mean" in result.columns

    # Rolling mean should be between min and max of data
    valid = result["rolling_mean_7d"].dropna()
    assert valid.min() >= 0
    assert valid.max() <= result["quantity_sold"].max() * 1.1


def test_holiday_detection():
    """Verify Danish holiday detection."""
    from src.features.external_features import get_danish_holidays, add_holiday_features

    holidays_df = get_danish_holidays(2023, 2023)
    assert len(holidays_df) > 5, "Denmark should have multiple holidays per year"

    # Check specific holiday
    christmas = holidays_df[holidays_df["date"] == pd.Timestamp("2023-12-25")]
    assert len(christmas) == 1

    # Test adding to dataframe
    df = _make_sample_df()
    result = add_holiday_features(df, date_col="date")
    assert "is_holiday" in result.columns
    assert "is_day_before_holiday" in result.columns

    # Jan 1 should be a holiday
    jan1 = result[pd.to_datetime(result["date"]).dt.date == date(2023, 1, 1)]
    if len(jan1) > 0:
        assert jan1.iloc[0]["is_holiday"] == 1


def test_feature_shape():
    """Verify the final feature matrix has expected shape and columns."""
    from src.features.time_features import add_time_features
    from src.features.lag_features import add_lag_features, add_rolling_features

    df = _make_sample_df()
    n_original_cols = len(df.columns)

    df = add_time_features(df)
    df = add_lag_features(df)
    df = add_rolling_features(df)

    # Should have significantly more columns
    assert len(df.columns) > n_original_cols + 15
    # Row count should be preserved
    assert len(df) == 60
