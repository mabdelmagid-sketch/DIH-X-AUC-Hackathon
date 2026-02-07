"""Tests for inventory optimization: safety stock, prep quantities, reorder points."""

import pytest
import pandas as pd
import numpy as np


def test_safety_stock_calculation():
    """Verify safety stock formula is correct."""
    from src.inventory.optimizer import calculate_safety_stock

    # Known values
    result = calculate_safety_stock(forecast_std=10, lead_time_days=1, z_score=1.65)
    expected = 1.65 * 10 * np.sqrt(1)
    assert result == pytest.approx(expected)

    # Higher lead time increases safety stock
    result_lt2 = calculate_safety_stock(forecast_std=10, lead_time_days=4, z_score=1.65)
    assert result_lt2 > result, "Safety stock should increase with lead time"

    # Zero std should give zero safety stock
    assert calculate_safety_stock(0, 1, 1.65) == 0


def test_reorder_point():
    """Verify reorder point formula."""
    from src.inventory.optimizer import calculate_reorder_point

    result = calculate_reorder_point(avg_daily_demand=10, lead_time_days=2, safety_stock=5)
    expected = 10 * 2 + 5
    assert result == expected


def test_prep_recommendations_positive():
    """Verify recommended prep quantities are always non-negative."""
    from src.inventory.optimizer import generate_prep_recommendations

    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    np.random.seed(42)
    df = pd.DataFrame({
        "date": dates,
        "place_id": 1,
        "item_id": 100,
        "quantity_sold": np.random.poisson(5, size=60).astype(float),
        "predicted": np.random.poisson(5, size=60).astype(float),
        "item_name": "Test Burger",
        "store_name": "Test Store",
    })

    recs = generate_prep_recommendations(df)

    assert len(recs) > 0
    assert (recs["recommended_prep_qty"] >= 0).all(), "Prep quantities must be non-negative"
    assert (recs["safety_stock"] >= 0).all(), "Safety stock must be non-negative"


def test_prep_recommendations_with_high_variance():
    """Items with high demand variance should get red alerts."""
    from src.inventory.optimizer import generate_prep_recommendations

    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    np.random.seed(42)

    # High variance item
    df = pd.DataFrame({
        "date": dates,
        "place_id": 1,
        "item_id": 100,
        "quantity_sold": np.random.choice([0, 0, 0, 20, 30], size=60).astype(float),
        "predicted": np.full(60, 5.0),
        "item_name": "Volatile Item",
        "store_name": "Test Store",
    })

    recs = generate_prep_recommendations(df)
    assert recs.iloc[0]["alert_level"] in ["red", "yellow"]


def test_reorder_point_logic():
    """Verify reorder point is greater than average demand."""
    from src.inventory.optimizer import calculate_reorder_point, calculate_safety_stock

    avg_demand = 10
    safety = calculate_safety_stock(forecast_std=3, lead_time_days=1)
    reorder = calculate_reorder_point(avg_demand, lead_time_days=1, safety_stock=safety)

    assert reorder >= avg_demand, "Reorder point should be >= average demand"
