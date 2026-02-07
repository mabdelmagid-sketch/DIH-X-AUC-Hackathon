"""Column type definitions and validation for all CSV tables."""

import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Expected columns for key tables (subset of important ones for type casting)
SCHEMAS = {
    "fct_orders": {
        "id": "int64",
        "user_id": "Int64",
        "created": "int64",
        "updated": "int64",
        "cash_amount": "float64",
        "demo_mode": "Int64",
        "discount_amount": "float64",
        "items_amount": "float64",
        "place_id": "Int64",
        "total_amount": "float64",
        "vat_amount": "float64",
        "status": "str",
        "type": "str",
        "channel": "str",
        "source": "str",
        "payment_method": "str",
    },
    "fct_order_items": {
        "id": "int64",
        "user_id": "Int64",
        "created": "int64",
        "updated": "int64",
        "title": "str",
        "cost": "float64",
        "discount_amount": "float64",
        "item_id": "Int64",
        "order_id": "Int64",
        "price": "float64",
        "quantity": "Int64",
        "status": "str",
        "vat_amount": "float64",
        "campaign_id": "Int64",
        "commission_amount": "float64",
    },
    "dim_items": {
        "id": "int64",
        "user_id": "Int64",
        "created": "int64",
        "updated": "int64",
        "title": "str",
        "description": "str",
        "price": "float64",
        "status": "str",
        "type": "str",
        "section_id": "Int64",
        "vat": "float64",
        "deleted": "Int64",
        "demo_mode": "Int64",
    },
    "dim_places": {
        "id": "int64",
        "user_id": "Int64",
        "created": "int64",
        "updated": "int64",
        "title": "str",
        "country": "str",
        "currency": "str",
        "timezone": "str",
        "latitude": "float64",
        "longitude": "float64",
        "opening_hours": "str",
        "street_address": "str",
    },
    "fct_campaigns": {
        "id": "int64",
        "user_id": "Int64",
        "created": "int64",
        "updated": "int64",
        "title": "str",
        "discount": "float64",
        "discount_type": "str",
        "start_date_time": "Int64",
        "end_date_time": "Int64",
        "place_id": "Int64",
        "status": "str",
        "type": "str",
        "item_ids": "str",
        "redemptions": "Int64",
        "used_redemptions": "Int64",
    },
    "most_ordered": {
        "place_id": "Int64",
        "item_id": "Int64",
        "item_name": "str",
        "order_count": "Int64",
    },
    "dim_skus": {
        "id": "int64",
        "user_id": "Int64",
        "created": "int64",
        "updated": "int64",
        "stock_category_id": "Int64",
        "item_id": "Int64",
        "title": "str",
        "quantity": "float64",
        "low_stock_threshold": "float64",
        "type": "str",
        "unit": "str",
    },
}

# Columns that contain UNIX timestamps (seconds since epoch)
UNIX_TIMESTAMP_COLS = ["created", "updated", "start_date_time", "end_date_time"]


def validate_table(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """Validate and cast column types for a given table.

    Args:
        df: Raw DataFrame loaded from CSV.
        table_name: Name of the table (must be in SCHEMAS).

    Returns:
        DataFrame with validated/casted types.

    Raises:
        ValueError: If the DataFrame is empty after loading.
    """
    if df.empty:
        raise ValueError(f"Table '{table_name}' is empty — aborting to prevent silent errors")

    if table_name not in SCHEMAS:
        logger.warning(f"No schema defined for '{table_name}', returning as-is")
        return df

    schema = SCHEMAS[table_name]
    for col, dtype in schema.items():
        if col not in df.columns:
            continue
        try:
            if dtype == "str":
                df[col] = df[col].astype(str).replace("nan", pd.NA)
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype(dtype)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not cast {table_name}.{col} to {dtype}: {e}")

    # Check for expected columns
    missing = set(schema.keys()) - set(df.columns)
    if missing:
        logger.warning(f"Table '{table_name}' missing columns: {missing}")

    # Warn on high null percentage in key ID column
    if "id" in df.columns:
        null_pct = df["id"].isna().mean() * 100
        if null_pct > 5:
            logger.warning(f"Table '{table_name}' has {null_pct:.1f}% null IDs")

    return df
