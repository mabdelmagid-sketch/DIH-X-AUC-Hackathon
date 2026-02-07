"""CSV ingestion, UNIX timestamp conversion, DKK handling."""

import os
import json
import logging
from pathlib import Path

import pandas as pd
import yaml

from src.data.schema import validate_table, UNIX_TIMESTAMP_COLS

logger = logging.getLogger(__name__)

# Base directory for the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "settings.yaml"


def load_config() -> dict:
    """Load configuration from settings.yaml."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_data_dir(config: dict) -> Path:
    """Resolve the raw data directory from config."""
    raw_dir = config["data"]["raw_dir"]
    # Try relative to BASE_DIR first
    path = BASE_DIR / raw_dir
    if path.exists():
        return path
    # Try as absolute
    path = Path(raw_dir)
    if path.exists():
        return path
    raise FileNotFoundError(f"Data directory not found: {raw_dir}")


def convert_unix_timestamps(df: pd.DataFrame, timezone: str = "Europe/Copenhagen") -> pd.DataFrame:
    """Convert UNIX timestamp columns to timezone-aware datetime.

    Args:
        df: DataFrame with potential UNIX timestamp columns.
        timezone: Target timezone for conversion.

    Returns:
        DataFrame with converted datetime columns.
    """
    for col in UNIX_TIMESTAMP_COLS:
        if col in df.columns:
            # Only convert numeric values
            numeric_vals = pd.to_numeric(df[col], errors="coerce")
            mask = numeric_vals.notna() & (numeric_vals > 0)
            if mask.any():
                dt_col = col + "_dt"
                # Build the full datetime series at once to avoid dtype conflicts
                dt_series = pd.to_datetime(
                    numeric_vals.where(mask), unit="s", utc=True
                ).dt.tz_convert(timezone)
                df[dt_col] = dt_series
    return df


def parse_opening_hours(hours_str: str) -> dict:
    """Parse the opening_hours JSON string from dim_places.

    Args:
        hours_str: JSON string like '{"monday":{"from":"12.00","to":"20.30"},...}'

    Returns:
        Dict mapping day names to (open_time, close_time) or None if closed.
    """
    if pd.isna(hours_str) or not hours_str:
        return {}
    try:
        hours = json.loads(hours_str)
        parsed = {}
        for day, times in hours.items():
            if times.get("from") == "closed":
                parsed[day] = None
            else:
                parsed[day] = (times.get("from", ""), times.get("to", ""))
        return parsed
    except (json.JSONDecodeError, AttributeError):
        return {}


def load_table(table_name: str, config: dict = None) -> pd.DataFrame:
    """Load a single CSV table by name.

    Args:
        table_name: Key from config tables (e.g., 'fct_orders').
        config: Configuration dict. Loaded from file if None.

    Returns:
        Loaded and validated DataFrame.
    """
    if config is None:
        config = load_config()

    data_dir = _resolve_data_dir(config)
    filename = config["tables"].get(table_name)
    if filename is None:
        raise ValueError(f"Unknown table: {table_name}")

    filepath = data_dir / filename
    logger.info(f"Loading {table_name} from {filepath}")

    df = pd.read_csv(filepath, low_memory=False)
    logger.info(f"  Loaded {len(df)} rows, {len(df.columns)} columns")

    # Validate schema
    df = validate_table(df, table_name)

    # Convert timestamps
    tz = config["data"]["timezone"]
    df = convert_unix_timestamps(df, timezone=tz)

    return df


def load_all_tables(config: dict = None) -> dict:
    """Load all configured CSV tables.

    Args:
        config: Configuration dict. Loaded from file if None.

    Returns:
        Dict mapping table names to DataFrames.
    """
    if config is None:
        config = load_config()

    tables = {}
    for table_name in config["tables"]:
        try:
            tables[table_name] = load_table(table_name, config)
        except Exception as e:
            logger.error(f"Failed to load {table_name}: {e}")

    logger.info(f"Loaded {len(tables)} tables successfully")
    return tables


def load_key_tables(config: dict = None) -> dict:
    """Load only the key tables needed for forecasting.

    Returns dict with keys: orders, order_items, items, places, campaigns, most_ordered
    """
    if config is None:
        config = load_config()

    key_tables = [
        "fct_orders",
        "fct_order_items",
        "dim_items",
        "dim_places",
        "fct_campaigns",
        "most_ordered",
        "dim_skus",
    ]

    tables = {}
    for name in key_tables:
        try:
            tables[name] = load_table(name, config)
        except Exception as e:
            logger.error(f"Failed to load {name}: {e}")

    return tables


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    tables = load_key_tables(config)
    for name, df in tables.items():
        print(f"{name}: {df.shape}")
