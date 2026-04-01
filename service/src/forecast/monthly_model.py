"""
monthly_model.py -- Loving Loyalty AI Suite, Pillar 1: Sales Forecasting

Lag-Free Monthly Revenue Model (SRS Section 5).

Used ONLY for month-long revenue projections beyond 14 days.
NEVER used for item-level or operational decisions.

Key constraint: uses ONLY trend and seasonality features.
No lag features, no rolling window features — these would be invalid
for predictions 14+ days out because future lags are unavailable.

Features used:
  - month, quarter, week_of_year, day_of_week, is_weekend
  - Fourier terms (weekly + annual, order 2)
  - expanding_mean  (frozen historical average — not a lag)
  - wow_growth      (computed from history, not future lags)

Returns predictions with reduced confidence (normal_confidence * 0.6)
to reflect the inherent uncertainty of lag-free long-horizon forecasting.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

logger = logging.getLogger(__name__)

# Features allowed for the monthly model (no lags, no rolling windows)
_MONTHLY_FEATURE_COLS: list[str] = [
    "month",
    "quarter",
    "week_of_year",
    "day_of_week",
    "is_weekend",
    # Fourier terms for weekly and annual seasonality
    "fourier_week_sin_1",
    "fourier_week_cos_1",
    "fourier_week_sin_2",
    "fourier_week_cos_2",
    "fourier_annual_sin_1",
    "fourier_annual_cos_1",
    "fourier_annual_sin_2",
    "fourier_annual_cos_2",
    # Trend features derived from history (not future-leaking)
    "expanding_mean",
    "wow_growth",
]

# Confidence penalty for long-horizon lag-free forecasting (SRS Section 5)
_CONFIDENCE_SCALE = 0.6

_FALLBACK_BUFFER = 1.27


class MonthlyRevenueModel:
    """Lag-free model for month-long revenue projections.

    Trains a Random Forest using only trend and seasonality features,
    deliberately excluding all lag and rolling window features that would
    be invalid for forecasts beyond 14 days.

    Args:
        n_estimators: Number of trees in the Random Forest.
        random_state: Reproducibility seed.
    """

    def __init__(
        self,
        n_estimators: int = 300,
        random_state: int = 42,
    ) -> None:
        self.n_estimators = n_estimators
        self.random_state = random_state
        self._model: Optional[RandomForestRegressor] = None
        self._feature_cols: list[str] = []
        self._expanding_means: dict[tuple, float] = {}
        self._wow_growth_by_group: dict[tuple, float] = {}

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def fit(self, daily_df: pd.DataFrame, target_col: str = "quantity_sold") -> "MonthlyRevenueModel":
        """Fit the lag-free model on historical daily demand.

        Args:
            daily_df: Historical daily demand DataFrame with at least:
                      date, place_id, item_id (or item), quantity_sold.
            target_col: Name of the demand column.

        Returns:
            Self (for chaining).
        """
        df = daily_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        group_cols = self._infer_group_cols(df)

        # Compute features
        df = self._add_time_features(df)
        df = self._add_fourier_features(df)
        df = self._freeze_expanding_means(df, group_cols, target_col)
        df = self._add_wow_growth(df, group_cols, target_col)

        # Determine which feature columns are actually present
        self._feature_cols = [c for c in _MONTHLY_FEATURE_COLS if c in df.columns]

        X = df[self._feature_cols].fillna(0.0)
        y = df[target_col].fillna(0.0)

        if len(X) == 0:
            logger.warning("MonthlyRevenueModel: no training data; model will return zeros")
            return self

        self._model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            min_samples_leaf=2,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self._model.fit(X.values, y.values)
        logger.info(
            "MonthlyRevenueModel: fitted on %d rows, %d features",
            len(X),
            len(self._feature_cols),
        )
        return self

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(
        self,
        start_date: date,
        end_date: date,
        place_id: Optional[int] = None,
        item_id: Optional[object] = None,
        item_title: str = "",
        base_confidence: float = 0.75,
    ) -> list[dict]:
        """Generate daily revenue-level predictions for a date range.

        Args:
            start_date: First date (inclusive).
            end_date: Last date (inclusive).
            place_id: Restaurant identifier (used in output only).
            item_id: Item identifier (used in output only).
            item_title: Human-readable item title.
            base_confidence: Confidence that would be assigned by the
                             operational model; this is scaled by
                             _CONFIDENCE_SCALE = 0.6 before output.

        Returns:
            List of prediction dicts compatible with ForecastPredictor output,
            with an extra ``model_type`` key set to ``"monthly_lag_free"``.
        """
        if self._model is None:
            logger.error("MonthlyRevenueModel.predict() called before fit()")
            return []

        # Build a synthetic DataFrame for the forecast horizon
        dates = pd.date_range(start=start_date, end=end_date, freq="D")
        rows = []
        for d in dates:
            row: dict = {"date": d}
            rows.append(row)

        feat_df = pd.DataFrame(rows)
        feat_df = self._add_time_features(feat_df)
        feat_df = self._add_fourier_features(feat_df)

        # Use frozen expanding_mean for the group if available
        group_key = (place_id, item_id)
        frozen_mean = self._expanding_means.get(group_key, 0.0)
        feat_df["expanding_mean"] = frozen_mean

        # Use frozen wow_growth for the group if available
        frozen_wow = self._wow_growth_by_group.get(group_key, 0.0)
        feat_df["wow_growth"] = frozen_wow

        available_cols = [c for c in self._feature_cols if c in feat_df.columns]
        X = feat_df[available_cols].fillna(0.0)

        if X.shape[1] != len(self._feature_cols):
            # Pad missing columns with zeros to match training shape
            for col in self._feature_cols:
                if col not in X.columns:
                    X[col] = 0.0
            X = X[self._feature_cols]

        raw_preds = self._model.predict(X.values)
        raw_preds = np.clip(raw_preds, 0.0, None)

        # Confidence is reduced to reflect the long-horizon, lag-free nature
        confidence = round(float(base_confidence) * _CONFIDENCE_SCALE, 3)
        confidence = max(0.0, min(1.0, confidence))

        results: list[dict] = []
        for i, d in enumerate(dates):
            raw = float(raw_preds[i])
            # Apply conservative newsvendor buffer (fallback value for new items)
            group_key_lookup = (place_id, item_id)
            # No per-item rolling_std available for lag-free model; use fallback
            buffered = raw * _FALLBACK_BUFFER
            predicted_units = int(round(buffered))
            lower_bound = int(round(max(0.0, buffered * 0.75)))
            upper_bound = int(round(buffered * 1.30))

            results.append({
                "item_id": item_id,
                "item_title": item_title,
                "place_id": place_id or 0,
                "date": d.date().isoformat(),
                "predicted_units": predicted_units,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "confidence": confidence,
                "forecast_drivers": [
                    "Long-horizon monthly projection (lag-free)",
                    "Seasonal and trend pattern applied",
                    "Historical average demand used",
                ],
                "model_type": "monthly_lag_free",
                "buffer_multiplier": _FALLBACK_BUFFER,
            })

        return results

    # ------------------------------------------------------------------
    # Feature helpers (no lags, no rolling windows)
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_group_cols(df: pd.DataFrame) -> list[str]:
        cols = []
        if "place_id" in df.columns:
            cols.append("place_id")
        for candidate in ("item_id", "item"):
            if candidate in df.columns:
                cols.append(candidate)
                break
        return cols or ["item_id"]

    @staticmethod
    def _add_time_features(df: pd.DataFrame) -> pd.DataFrame:
        df["day_of_week"] = df["date"].dt.dayofweek
        df["day_of_year"] = df["date"].dt.dayofyear
        df["month"] = df["date"].dt.month
        df["quarter"] = df["date"].dt.quarter
        df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
        df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
        return df

    @staticmethod
    def _add_fourier_features(df: pd.DataFrame) -> pd.DataFrame:
        for k in [1, 2]:
            df[f"fourier_week_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_week"] / 7)
            df[f"fourier_week_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_week"] / 7)
            df[f"fourier_annual_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_year"] / 365.25)
            df[f"fourier_annual_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_year"] / 365.25)
        return df

    def _freeze_expanding_means(
        self,
        df: pd.DataFrame,
        group_cols: list[str],
        target_col: str,
    ) -> pd.DataFrame:
        """Compute and freeze the expanding mean per group for inference."""
        if target_col not in df.columns:
            df["expanding_mean"] = 0.0
            return df

        def _group_expanding_mean(g: pd.DataFrame) -> pd.Series:
            return g[target_col].expanding().mean()

        df["expanding_mean"] = df.groupby(group_cols, observed=True, group_keys=False)[target_col].apply(
            lambda s: s.expanding().mean()
        )

        # Freeze last value per group for future inference
        last_means = (
            df.dropna(subset=["expanding_mean"])
            .sort_values("date")
            .groupby(group_cols, observed=True)["expanding_mean"]
            .last()
        )
        for key, val in last_means.items():
            k = key if isinstance(key, tuple) else (key,)
            self._expanding_means[k] = float(val)

        return df

    def _add_wow_growth(
        self,
        df: pd.DataFrame,
        group_cols: list[str],
        target_col: str,
    ) -> pd.DataFrame:
        """Compute week-over-week growth from history (not future lags)."""
        if target_col not in df.columns:
            df["wow_growth"] = 0.0
            return df

        # wow_growth = (demand_t - demand_{t-7}) / demand_{t-7}.clip(1)
        df = df.sort_values(["date"])
        df["_lag7"] = df.groupby(group_cols, observed=True)[target_col].shift(7)
        df["wow_growth"] = (df[target_col] - df["_lag7"]) / df["_lag7"].clip(lower=0.01)
        df["wow_growth"] = df["wow_growth"].fillna(0.0).clip(-1.0, 5.0)
        df.drop(columns=["_lag7"], inplace=True)

        # Freeze last wow_growth per group
        last_wow = (
            df.dropna(subset=["wow_growth"])
            .sort_values("date")
            .groupby(group_cols, observed=True)["wow_growth"]
            .last()
        )
        for key, val in last_wow.items():
            k = key if isinstance(key, tuple) else (key,)
            self._wow_growth_by_group[k] = float(val)

        return df
