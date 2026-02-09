"""Time-based features extracted from order timestamps."""

import pandas as pd
import numpy as np
import json
import logging

logger = logging.getLogger(__name__)


def add_time_features(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    """Add calendar and time-based features.

    Args:
        df: DataFrame with a date column.
        date_col: Name of the date column (datetime or date type).

    Returns:
        DataFrame with added time feature columns.
    """
    dt = pd.to_datetime(df[date_col])

    df["day_of_week"] = dt.dt.dayofweek  # 0=Mon, 6=Sun
    df["day_of_month"] = dt.dt.day
    df["month"] = dt.dt.month
    df["quarter"] = dt.dt.quarter
    df["week_of_year"] = dt.dt.isocalendar().week.astype(int)
    df["day_of_year"] = dt.dt.dayofyear
    df["year"] = dt.dt.year

    # Binary flags
    df["is_weekend"] = (dt.dt.dayofweek >= 5).astype(int)
    df["is_friday"] = (dt.dt.dayofweek == 4).astype(int)
    df["is_monday"] = (dt.dt.dayofweek == 0).astype(int)

    # Season (meteorological for Denmark)
    df["season"] = dt.dt.month.map({
        12: 0, 1: 0, 2: 0,   # Winter
        3: 1, 4: 1, 5: 1,    # Spring
        6: 2, 7: 2, 8: 2,    # Summer
        9: 3, 10: 3, 11: 3,  # Autumn
    })

    # Cyclical encoding for day_of_week and month
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * (df["month"] - 1) / 12)
    df["month_cos"] = np.cos(2 * np.pi * (df["month"] - 1) / 12)

    logger.info(f"Added {14} time features")
    return df


def add_is_open_flag(df: pd.DataFrame, places_df: pd.DataFrame,
                     date_col: str = "date", place_col: str = "place_id") -> pd.DataFrame:
    """Add is_open flag based on store opening hours.

    Args:
        df: DataFrame with date and place_id columns.
        places_df: dim_places DataFrame with opening_hours JSON.
        date_col: Date column name.
        place_col: Place ID column name.

    Returns:
        DataFrame with 'is_open' column added.
    """
    day_names = {0: "monday", 1: "tuesday", 2: "wednesday",
                 3: "thursday", 4: "friday", 5: "saturday", 6: "sunday"}

    # Parse opening hours for each place
    place_hours = {}
    for _, row in places_df.iterrows():
        try:
            hours = json.loads(row.get("opening_hours", "{}"))
            place_hours[row["id"]] = hours
        except (json.JSONDecodeError, TypeError):
            place_hours[row["id"]] = {}

    dt = pd.to_datetime(df[date_col])
    dow = dt.dt.dayofweek

    is_open = []
    for i in range(len(df)):
        pid = df[place_col].iloc[i]
        day_name = day_names.get(dow.iloc[i], "monday")
        hours = place_hours.get(pid, {})
        day_hours = hours.get(day_name, {})

        if isinstance(day_hours, dict) and day_hours.get("from") == "closed":
            is_open.append(0)
        elif isinstance(day_hours, dict) and day_hours.get("from"):
            is_open.append(1)
        else:
            is_open.append(1)  # Default to open if no info

    df["is_open"] = is_open
    logger.info("Added is_open flag")
    return df
