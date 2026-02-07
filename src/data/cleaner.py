"""Data cleaning: deduplication, null handling, status filtering."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the fct_orders table.

    - Filter to status == 'Closed' (completed orders only)
    - Remove demo_mode == 1 records
    - Deduplicate on id
    - Remove rows with missing place_id
    """
    initial_rows = len(df)

    # Filter to closed orders only
    if "status" in df.columns:
        df = df[df["status"] == "Closed"].copy()
        logger.info(f"  Filtered to Closed orders: {initial_rows} -> {len(df)}")

    # Remove demo mode records
    if "demo_mode" in df.columns:
        df = df[df["demo_mode"] != 1].copy()
        logger.info(f"  Removed demo_mode: {len(df)} rows remain")

    # Deduplicate
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["id"], keep="first")
    if before_dedup != len(df):
        logger.info(f"  Deduplicated: {before_dedup} -> {len(df)}")

    # Remove rows missing place_id
    df = df.dropna(subset=["place_id"])

    logger.info(f"  Orders cleaned: {initial_rows} -> {len(df)} rows")
    return df.reset_index(drop=True)


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the fct_order_items table.

    - Remove rows with null item_id
    - Deduplicate on id
    - Ensure quantity is positive
    """
    initial_rows = len(df)

    # Remove null item_id
    df = df.dropna(subset=["item_id"]).copy()
    logger.info(f"  Removed null item_id: {initial_rows} -> {len(df)}")

    # Deduplicate
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["id"], keep="first")
    if before_dedup != len(df):
        logger.info(f"  Deduplicated: {before_dedup} -> {len(df)}")

    # Ensure quantity is positive
    if "quantity" in df.columns:
        df = df[df["quantity"] > 0]

    logger.info(f"  Order items cleaned: {initial_rows} -> {len(df)} rows")
    return df.reset_index(drop=True)


def clean_items(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the dim_items table.

    - Remove deleted items
    - Remove demo_mode items
    - Deduplicate on id
    """
    initial_rows = len(df)

    if "deleted" in df.columns:
        df = df[df["deleted"] != 1].copy()

    if "demo_mode" in df.columns:
        df = df[df["demo_mode"] != 1].copy()

    df = df.drop_duplicates(subset=["id"], keep="first")

    logger.info(f"  Items cleaned: {initial_rows} -> {len(df)} rows")
    return df.reset_index(drop=True)


def clean_campaigns(df: pd.DataFrame) -> pd.DataFrame:
    """Clean fct_campaigns table.

    - Deduplicate on id
    - Ensure start_date_time and end_date_time are present
    """
    initial_rows = len(df)
    df = df.drop_duplicates(subset=["id"], keep="first")
    df = df.dropna(subset=["start_date_time", "end_date_time"]).copy()
    logger.info(f"  Campaigns cleaned: {initial_rows} -> {len(df)} rows")
    return df.reset_index(drop=True)


def clean_all(tables: dict) -> dict:
    """Apply cleaning to all key tables.

    Args:
        tables: Dict of table_name -> DataFrame.

    Returns:
        Dict with cleaned DataFrames.
    """
    cleaned = {}

    for name, df in tables.items():
        if name == "fct_orders":
            cleaned[name] = clean_orders(df)
        elif name == "fct_order_items":
            cleaned[name] = clean_order_items(df)
        elif name == "dim_items":
            cleaned[name] = clean_items(df)
        elif name == "fct_campaigns":
            cleaned[name] = clean_campaigns(df)
        else:
            # Basic dedup for other tables
            if "id" in df.columns:
                df = df.drop_duplicates(subset=["id"], keep="first")
            cleaned[name] = df

    return cleaned
