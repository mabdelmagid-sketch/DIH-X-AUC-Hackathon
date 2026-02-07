"""Tests for data loading, timestamp conversion, schema validation."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path


def test_config_loads():
    """Verify settings.yaml loads correctly."""
    from src.data.loader import load_config
    config = load_config()
    assert "data" in config
    assert "tables" in config
    assert config["data"]["timezone"] == "Europe/Copenhagen"


def test_key_tables_load():
    """Verify all key CSV tables load with correct row counts."""
    from src.data.loader import load_key_tables
    tables = load_key_tables()

    assert "fct_orders" in tables
    assert "fct_order_items" in tables
    assert "dim_items" in tables
    assert "dim_places" in tables

    # Check minimum expected rows
    assert len(tables["fct_orders"]) > 100000, "Expected 400K+ orders"
    assert len(tables["fct_order_items"]) > 500000, "Expected 2M+ order items"
    assert len(tables["dim_places"]) >= 5, "Expected ~10 places"


def test_timestamp_conversion():
    """Verify UNIX timestamps are converted to datetime."""
    from src.data.loader import load_table
    orders = load_table("fct_orders")

    assert "created_dt" in orders.columns, "created_dt column should exist"
    # Check that timestamps are in reasonable range
    valid_dates = orders["created_dt"].dropna()
    assert len(valid_dates) > 0
    min_date = valid_dates.min()
    assert min_date.year >= 2021, f"Min date should be >= 2021, got {min_date}"


def test_schema_validation():
    """Verify schema validation works correctly."""
    from src.data.schema import validate_table

    df = pd.DataFrame({
        "id": [1, 2, 3],
        "user_id": [10, 20, None],
        "created": [1613139429, 1613144783, 1613149610],
        "status": ["Closed", "Open", "Closed"],
        "total_amount": ["50.0", "100.0", "150.0"],
    })

    validated = validate_table(df, "fct_orders")
    assert validated["total_amount"].dtype == float


def test_opening_hours_parsing():
    """Verify opening hours JSON parsing."""
    from src.data.loader import parse_opening_hours

    hours_str = '{"monday":{"from":"12.00","to":"20.30"},"tuesday":{"from":"closed","to":"00.00"}}'
    parsed = parse_opening_hours(hours_str)

    assert "monday" in parsed
    assert parsed["monday"] == ("12.00", "20.30")
    assert parsed["tuesday"] is None  # Closed

    # Edge cases
    assert parse_opening_hours("") == {}
    assert parse_opening_hours(None) == {}
