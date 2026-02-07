"""Lag and rolling window features for time series forecasting."""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def add_lag_features(df: pd.DataFrame, target_col: str = "quantity_sold",
                     group_cols: list = None) -> pd.DataFrame:
    """Add lag features per (store, item) group.

    Args:
        df: DataFrame sorted by date within each group.
        target_col: Column to create lags from.
        group_cols: Columns defining the group (default: ['place_id', 'item_id']).

    Returns:
        DataFrame with lag feature columns added.
    """
    if group_cols is None:
        group_cols = ["place_id", "item_id"]

    # Ensure sorted by date within groups
    df = df.sort_values(group_cols + ["date"]).copy()
    grouped = df.groupby(group_cols, observed=True)[target_col]

    # Simple lags
    for lag in [1, 7, 14, 28]:
        col_name = f"demand_lag_{lag}d"
        df[col_name] = grouped.shift(lag)

    logger.info("Added lag features (1, 7, 14, 28 days)")
    return df


def add_rolling_features(df: pd.DataFrame, target_col: str = "quantity_sold",
                         group_cols: list = None) -> pd.DataFrame:
    """Add rolling window statistics per (store, item) group.

    Args:
        df: DataFrame sorted by date within each group.
        target_col: Column to compute rolling stats from.
        group_cols: Columns defining the group.

    Returns:
        DataFrame with rolling feature columns added.
    """
    if group_cols is None:
        group_cols = ["place_id", "item_id"]

    df = df.sort_values(group_cols + ["date"]).copy()
    grouped = df.groupby(group_cols, observed=True)[target_col]

    # Rolling means (shifted by 1 to avoid data leakage)
    for window in [7, 14, 30]:
        col_name = f"rolling_mean_{window}d"
        df[col_name] = grouped.transform(
            lambda x: x.shift(1).rolling(window=window, min_periods=1).mean()
        )

    # Rolling standard deviations
    for window in [7, 14]:
        col_name = f"rolling_std_{window}d"
        df[col_name] = grouped.transform(
            lambda x: x.shift(1).rolling(window=window, min_periods=2).std()
        )

    # Same weekday last week
    df["demand_same_weekday_last_week"] = grouped.shift(7)

    # Average of same weekday over last 4 weeks
    df["demand_same_weekday_avg_4weeks"] = grouped.transform(
        lambda x: (x.shift(7) + x.shift(14) + x.shift(21) + x.shift(28)) / 4
    )

    # Expanding mean (lifetime average up to that point)
    df["expanding_mean"] = grouped.transform(
        lambda x: x.shift(1).expanding(min_periods=1).mean()
    )

    logger.info("Added rolling features (mean, std, weekday avg, expanding)")
    return df
