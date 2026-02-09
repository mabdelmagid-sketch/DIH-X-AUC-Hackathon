"""Baseline models: naive last-week and moving average."""

import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class NaiveLastWeekModel:
    """Predict same weekday last week's value."""

    def __init__(self):
        self.name = "naive_last_week"

    def predict(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> pd.Series:
        """Predict using last week's same-day value."""
        # Use pre-computed feature if available
        if "demand_lag_7d" in df.columns:
            return df["demand_lag_7d"].fillna(0)
        predictions = df.groupby(["place_id", "item_id"], observed=True)[target_col].shift(7)
        return predictions.fillna(0)


class MovingAverageModel:
    """Predict using a rolling average."""

    # Map window sizes to pre-computed feature column names
    _FEATURE_MAP = {
        7: "rolling_mean_7d",
        14: "rolling_mean_14d",
        28: "rolling_mean_30d",   # closest available (30d)
        30: "rolling_mean_30d",
    }

    def __init__(self, window: int = 7):
        self.window = window
        self.name = f"moving_avg_{window}d"

    def predict(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> pd.Series:
        """Predict using rolling mean (shifted by 1 to avoid leakage).

        Uses pre-computed rolling_mean columns from feature engineering when
        available (instant). Falls back to computing on the fly.
        """
        # Fast path: use pre-computed feature column if present
        feat_col = self._FEATURE_MAP.get(self.window)
        if feat_col and feat_col in df.columns:
            return df[feat_col].fillna(0)

        # Slow path: compute from scratch (for small DataFrames or missing features)
        shifted = df.groupby(["place_id", "item_id"], observed=True)[target_col].shift(1)
        predictions = shifted.groupby(
            [df["place_id"], df["item_id"]], observed=True
        ).transform(
            lambda x: x.rolling(self.window, min_periods=1).mean()
        )
        return predictions.fillna(0)


def evaluate_baselines(df: pd.DataFrame, target_col: str = "quantity_sold") -> dict:
    """Evaluate all baseline models."""
    models = [
        NaiveLastWeekModel(),
        MovingAverageModel(window=7),
        MovingAverageModel(window=28),
    ]

    results = {}
    actuals = df[target_col]

    for model in models:
        preds = model.predict(df, target_col)
        mask = preds.notna() & actuals.notna()
        mae = np.abs(actuals[mask] - preds[mask]).mean()
        results[model.name] = {"mae": mae, "predictions": preds}
        logger.info(f"Baseline {model.name}: MAE = {mae:.4f}")

    return results
