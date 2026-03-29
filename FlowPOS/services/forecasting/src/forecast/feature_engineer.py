"""
feature_engineer.py -- Loving Loyalty AI Suite, Pillar 1: Sales Forecasting

All feature engineering in a single, testable module.

Feature groups produced:
  - Time features    : day_of_week, is_weekend, month, quarter, …
  - Lag features     : demand_lag_{1,7,14,28}d — shifted to avoid leakage
  - Rolling stats    : rolling_mean / rolling_std over 7d, 14d windows
  - Trend features   : wow_growth, recent_vs_expanding_mean
  - Seasonality      : Fourier harmonics (order 2) for weekly and annual cycles
  - Interaction feat : lag7d x day_of_week, rolling_mean7d x is_weekend
  - Holiday features : Danish public holidays (static + computed set)
  - expanding_mean   : ONLY computed on training data (Report B, Section 4 fix)

Usage:

    fe = FeatureEngineer()
    # During training — passes training partition so expanding_mean is safe:
    train_df = fe.fit_transform(train_df)
    # During inference — uses expanding stats frozen at training cutoff:
    test_df  = fe.transform(test_df)

The ``fit`` step memorises the per-(place_id, item_id) expanding mean at the
last training date.  ``transform`` then uses those frozen values for any date
beyond the training window, preventing leakage.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Danish public holidays (static + extended)
# Used for is_holiday, days_from_holiday, near_holiday features.
# Extend this set for years beyond 2024 if retraining on newer data.
# ---------------------------------------------------------------------------
_DANISH_HOLIDAYS: frozenset[str] = frozenset({
    # 2023
    "2023-01-01",  # Nytarsdag
    "2023-04-06",  # Skaertorsdag
    "2023-04-07",  # Langfredag
    "2023-04-09",  # Paaske 1
    "2023-04-10",  # Paaske 2
    "2023-05-05",  # Store Bededag
    "2023-05-18",  # Kristi Himmelfartsdag
    "2023-05-28",  # Pinse 1
    "2023-05-29",  # Pinse 2
    "2023-06-05",  # Grundlovsdag
    "2023-12-24",  # Juleaftensdag
    "2023-12-25",  # 1. juledag
    "2023-12-26",  # 2. juledag
    "2023-12-31",  # Nytaarsaften
    # 2024
    "2024-01-01",  # Nytarsdag
    "2024-03-28",  # Skaertorsdag
    "2024-03-29",  # Langfredag
    "2024-03-31",  # Paaske 1
    "2024-04-01",  # Paaske 2
    "2024-04-26",  # Store Bededag
    "2024-05-09",  # Kristi Himmelfartsdag
    "2024-05-19",  # Pinse 1
    "2024-05-20",  # Pinse 2
    "2024-06-05",  # Grundlovsdag
    "2024-12-24",  # Juleaftensdag
    "2024-12-25",  # 1. juledag
    "2024-12-26",  # 2. juledag
    "2024-12-31",  # Nytaarsaften
    # 2025
    "2025-01-01",
    "2025-04-17",
    "2025-04-18",
    "2025-04-20",
    "2025-04-21",
    "2025-05-16",
    "2025-05-29",
    "2025-06-08",
    "2025-06-09",
    "2025-06-05",
    "2025-12-24",
    "2025-12-25",
    "2025-12-26",
    "2025-12-31",
})

# The canonical ordered list of feature columns produced by this module.
# Models trained with this module expect exactly these columns, in this order.
FEATURE_COLS: list[str] = [
    # Time
    "day_of_week", "day_of_month", "month", "quarter", "week_of_year",
    "day_of_year", "year", "is_weekend", "is_friday", "is_monday",
    "season", "dow_sin", "dow_cos", "month_sin", "month_cos",
    # Lag
    "demand_lag_1d", "demand_lag_7d", "demand_lag_14d", "demand_lag_28d",
    "demand_same_weekday_last_week", "demand_same_weekday_avg_4weeks",
    # Rolling
    "rolling_mean_7d", "rolling_mean_14d", "rolling_mean_30d",
    "rolling_std_7d", "rolling_std_14d",
    # Expanding (leakage-safe)
    "expanding_mean",
    # Trend
    "days_since_start", "wow_growth", "recent_vs_expanding",
    # Seasonality (Fourier order 2)
    "fourier_week_sin_1", "fourier_week_cos_1",
    "fourier_week_sin_2", "fourier_week_cos_2",
    "fourier_annual_sin_1", "fourier_annual_cos_1",
    "fourier_annual_sin_2", "fourier_annual_cos_2",
    # Interactions
    "interaction_lag7d_dow", "interaction_rolling7_weekend",
    # Holiday
    "is_holiday", "days_from_holiday", "near_holiday",
    # External stubs (filled 0 when data unavailable)
    "temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
    "is_promotion_active", "discount_percentage", "campaign_count",
    "is_open",
    # Categorical encodings
    "place_id_encoded", "item_id_encoded", "store_dow_interaction",
]


class FeatureEngineer:
    """Build the complete feature matrix for the AdaptiveBlend model.

    Scikit-learn style fit / transform / fit_transform interface.

    After ``fit``, the engineer remembers:
      - ``expanding_mean_at_cutoff_``  : dict (place_id, item_id) -> float
          The per-pair expanding mean computed through the training window.
          Applied to test/inference rows so they never see future demand.
      - ``date_min_``                  : earliest date seen during fit
          Used to compute ``days_since_start`` consistently at inference time.
      - ``label_encoders_``            : dict str -> LabelEncoder
          Fitted label encoders for place_id and item_id.
    """

    def __init__(self) -> None:
        self.expanding_mean_at_cutoff_: dict[tuple, float] = {}
        self.date_min_: Optional[pd.Timestamp] = None
        self.label_encoders_: dict[str, "LabelEncoder"] = {}
        self._is_fitted = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit_transform(self, df: pd.DataFrame,
                      target_col: str = "quantity_sold",
                      group_cols: Optional[list[str]] = None) -> pd.DataFrame:
        """Fit on ``df`` and return the featurised training DataFrame.

        expanding_mean is computed only on rows present in ``df``.
        Call this once with the training partition; then call ``transform``
        on the test / inference partition.
        """
        group_cols = group_cols or ["place_id", "item_id"]
        df = df.copy().sort_values(group_cols + ["date"]).reset_index(drop=True)
        df["date"] = pd.to_datetime(df["date"])

        # Fit label encoders
        self._fit_label_encoders(df)
        # Capture global date_min for stable days_since_start
        self.date_min_ = df["date"].min()

        # Add all features (expanding_mean computed here, safe within training)
        df = self._add_all_features(df, target_col, group_cols, mode="fit")

        self._is_fitted = True
        return df

    def transform(self, df: pd.DataFrame,
                  target_col: str = "quantity_sold",
                  group_cols: Optional[list[str]] = None) -> pd.DataFrame:
        """Apply fitted feature engineering to new (test/inference) data.

        For rows belonging to (place_id, item_id) pairs seen during fit,
        the expanding_mean is frozen at the training-cutoff value so that
        no future demand leaks into the feature.  Unseen pairs fall back to
        a global mean of 0.

        Report B, Section 4: this is the explicit fix for the expanding_mean
        leakage issue found in the independent audit.
        """
        if not self._is_fitted:
            raise RuntimeError("Call fit_transform before transform")
        group_cols = group_cols or ["place_id", "item_id"]
        df = df.copy().sort_values(group_cols + ["date"]).reset_index(drop=True)
        df["date"] = pd.to_datetime(df["date"])

        df = self._add_all_features(df, target_col, group_cols, mode="transform")
        return df

    def get_feature_columns(self) -> list[str]:
        """Return the canonical ordered list of model feature columns."""
        return list(FEATURE_COLS)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fit_label_encoders(self, df: pd.DataFrame) -> None:
        from sklearn.preprocessing import LabelEncoder
        for col in ["place_id", "item_id"]:
            if col in df.columns:
                le = LabelEncoder()
                le.fit(df[col].astype(str))
                self.label_encoders_[col] = le

    def _encode_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in ["place_id", "item_id"]:
            enc_col = f"{col}_encoded"
            if col in df.columns and col in self.label_encoders_:
                le = self.label_encoders_[col]
                series = df[col].astype(str)
                # Handle unseen labels gracefully: map to 0
                known = set(le.classes_)
                safe = series.where(series.isin(known), le.classes_[0])
                df[enc_col] = le.transform(safe)
            else:
                df[enc_col] = 0
        return df

    def _add_all_features(self, df: pd.DataFrame, target_col: str,
                          group_cols: list[str], mode: str) -> pd.DataFrame:
        df = self._add_time_features(df)
        df = self._add_lag_features(df, target_col, group_cols)
        df = self._add_rolling_features(df, target_col, group_cols)
        df = self._add_expanding_mean(df, target_col, group_cols, mode)
        df = self._add_trend_features(df)
        df = self._add_seasonality(df)
        df = self._add_interaction_features(df)
        df = self._add_holiday_features(df)
        df = self._add_stub_features(df)
        df = self._encode_labels(df)
        df["store_dow_interaction"] = df["place_id_encoded"] * 10 + df["day_of_week"]
        return df

    # ---------- Time ----------

    @staticmethod
    def _add_time_features(df: pd.DataFrame) -> pd.DataFrame:
        d = df["date"]
        df["day_of_week"] = d.dt.dayofweek
        df["day_of_month"] = d.dt.day
        df["month"] = d.dt.month
        df["quarter"] = d.dt.quarter
        df["week_of_year"] = d.dt.isocalendar().week.astype(int)
        df["day_of_year"] = d.dt.dayofyear
        df["year"] = d.dt.year
        df["is_weekend"] = d.dt.dayofweek.isin([5, 6]).astype(int)
        df["is_friday"] = (d.dt.dayofweek == 4).astype(int)
        df["is_monday"] = (d.dt.dayofweek == 0).astype(int)
        df["season"] = df["month"].map(
            {12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3}
        )
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
        return df

    # ---------- Lags ----------

    @staticmethod
    def _add_lag_features(df: pd.DataFrame, target_col: str,
                          group_cols: list[str]) -> pd.DataFrame:
        grp = df.groupby(group_cols, observed=True)[target_col]
        for lag in [1, 7, 14, 28]:
            df[f"demand_lag_{lag}d"] = grp.shift(lag)
        df["demand_same_weekday_last_week"] = grp.shift(7)
        df["demand_same_weekday_avg_4weeks"] = grp.transform(
            lambda x: x.shift(7).rolling(4, min_periods=1).mean()
        )
        return df

    # ---------- Rolling ----------

    @staticmethod
    def _add_rolling_features(df: pd.DataFrame, target_col: str,
                               group_cols: list[str]) -> pd.DataFrame:
        grp = df.groupby(group_cols, observed=True)[target_col]
        for window in [7, 14, 30]:
            df[f"rolling_mean_{window}d"] = grp.transform(
                lambda x, w=window: x.shift(1).rolling(window=w, min_periods=1).mean()
            )
        for window in [7, 14]:
            df[f"rolling_std_{window}d"] = grp.transform(
                lambda x, w=window: x.shift(1).rolling(window=w, min_periods=2).std()
            )
        return df

    # ---------- Expanding mean (leakage fix — Report B Section 4) ----------

    def _add_expanding_mean(self, df: pd.DataFrame, target_col: str,
                            group_cols: list[str], mode: str) -> pd.DataFrame:
        """Compute expanding_mean safely with respect to the train/test boundary.

        Fix (Report B, Section 4): During training (mode='fit'), the expanding
        mean is computed with a one-day shift so each training row sees only
        historical values.  The per-pair value at the last training date is
        then saved in ``expanding_mean_at_cutoff_``.

        During inference / testing (mode='transform'), the expanding mean for
        every row of a given (place_id, item_id) pair is set to the frozen
        training-cutoff value, ensuring no future demand data leaks into the
        feature.
        """
        if mode == "fit":
            grp = df.groupby(group_cols, observed=True)[target_col]
            df["expanding_mean"] = grp.transform(
                lambda x: x.shift(1).expanding(min_periods=1).mean()
            )
            # Memorise the last non-NaN expanding_mean per pair for inference
            last_rows = (
                df.dropna(subset=["expanding_mean"])
                .sort_values("date")
                .groupby(group_cols, observed=True)["expanding_mean"]
                .last()
            )
            self.expanding_mean_at_cutoff_ = {
                (k if isinstance(k, tuple) else (k,)): float(v)
                for k, v in last_rows.items()
            }
        else:
            # Inference mode: freeze expanding_mean at training-cutoff value
            # Build a lookup Series indexed by the group key columns
            def _frozen_value(row: pd.Series) -> float:
                key = tuple(row[col] for col in group_cols)
                return self.expanding_mean_at_cutoff_.get(key, 0.0)

            df["expanding_mean"] = df.apply(_frozen_value, axis=1)

        return df

    # ---------- Trend ----------

    def _add_trend_features(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.date_min_ is not None:
            df["days_since_start"] = (df["date"] - self.date_min_).dt.days
        else:
            df["days_since_start"] = 0
        # wow_growth: week-over-week demand growth
        df["wow_growth"] = (
            (df["demand_lag_7d"] - df["demand_lag_14d"])
            / df["demand_lag_14d"].clip(lower=0.1)
        ).clip(-5, 5).fillna(0)
        # recent_vs_expanding: ratio of recent rolling mean to lifetime mean
        df["recent_vs_expanding"] = (
            df["rolling_mean_7d"] / df["expanding_mean"].clip(lower=0.01)
        ).clip(0, 10).fillna(1)
        return df

    # ---------- Seasonality (Fourier) ----------

    @staticmethod
    def _add_seasonality(df: pd.DataFrame) -> pd.DataFrame:
        # Weekly Fourier harmonics (order 2 as per SRS)
        for k in [1, 2]:
            df[f"fourier_week_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_week"] / 7)
            df[f"fourier_week_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_week"] / 7)
        # Annual Fourier harmonics (order 2)
        for k in [1, 2]:
            df[f"fourier_annual_sin_{k}"] = np.sin(2 * np.pi * k * df["day_of_year"] / 365.25)
            df[f"fourier_annual_cos_{k}"] = np.cos(2 * np.pi * k * df["day_of_year"] / 365.25)
        return df

    # ---------- Interaction features ----------

    @staticmethod
    def _add_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
        df["interaction_lag7d_dow"] = df["demand_lag_7d"].fillna(0) * (df["day_of_week"] + 1)
        df["interaction_rolling7_weekend"] = df["rolling_mean_7d"].fillna(0) * df["is_weekend"]
        return df

    # ---------- Holiday ----------

    @staticmethod
    def _add_holiday_features(df: pd.DataFrame) -> pd.DataFrame:
        date_strs = df["date"].dt.strftime("%Y-%m-%d")
        df["is_holiday"] = date_strs.isin(_DANISH_HOLIDAYS).astype(int)

        holiday_ts = [pd.Timestamp(h) for h in _DANISH_HOLIDAYS]

        def _days_from_holiday(d: pd.Timestamp) -> int:
            return min(abs((d - h).days) for h in holiday_ts)

        df["days_from_holiday"] = df["date"].apply(_days_from_holiday)
        df["near_holiday"] = (df["days_from_holiday"] <= 2).astype(int)
        return df

    # ---------- External stubs ----------

    @staticmethod
    def _add_stub_features(df: pd.DataFrame) -> pd.DataFrame:
        for col in ["temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
                    "is_promotion_active", "discount_percentage", "campaign_count"]:
            if col not in df.columns:
                df[col] = 0
        if "is_open" not in df.columns:
            df["is_open"] = 1
        return df
