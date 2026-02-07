"""XGBoost gradient boosting model for demand forecasting."""

import logging
from typing import Optional

import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)

# Feature columns used by the XGBoost model
FEATURE_COLS = [
    # Time features
    "day_of_week", "day_of_month", "month", "quarter", "week_of_year",
    "day_of_year", "year", "is_weekend", "is_friday", "is_monday",
    "season", "dow_sin", "dow_cos", "month_sin", "month_cos",
    # Lag features
    "demand_lag_1d", "demand_lag_7d", "demand_lag_14d", "demand_lag_28d",
    # Rolling features
    "rolling_mean_7d", "rolling_mean_14d", "rolling_mean_30d",
    "rolling_std_7d", "rolling_std_14d",
    "demand_same_weekday_last_week", "demand_same_weekday_avg_4weeks",
    "expanding_mean",
    # External features
    "temperature_max", "temperature_min", "precipitation_mm", "is_rainy",
    # Holiday features
    "is_holiday", "is_day_before_holiday", "is_day_after_holiday",
    # Promotion features
    "is_promotion_active", "discount_percentage", "campaign_count",
    # Store/item flags
    "is_open",
    # Encoded categoricals
    "place_id_encoded", "item_id_encoded",
]


class XGBoostForecaster:
    """XGBoost model for tabular demand forecasting."""

    def __init__(self, **params):
        self.params = {
            "n_estimators": params.get("n_estimators", 500),
            "max_depth": params.get("max_depth", 6),
            "learning_rate": params.get("learning_rate", 0.05),
            "subsample": params.get("subsample", 0.8),
            "colsample_bytree": params.get("colsample_bytree", 0.8),
            "min_child_weight": params.get("min_child_weight", 5),
            "random_state": 42,
            "n_jobs": -1,
        }
        self.model = None
        self.label_encoders = {}
        self.feature_cols = []
        self.name = "xgboost"

    def _encode_categoricals(self, df: pd.DataFrame, fit: bool = False) -> pd.DataFrame:
        """Label-encode categorical columns.

        Args:
            df: DataFrame to encode.
            fit: Whether to fit new encoders (True for training).

        Returns:
            DataFrame with encoded columns.
        """
        df = df.copy()

        for col, encoded_col in [("place_id", "place_id_encoded"),
                                  ("item_id", "item_id_encoded")]:
            if col in df.columns:
                if fit:
                    le = LabelEncoder()
                    df[encoded_col] = le.fit_transform(df[col].astype(str))
                    self.label_encoders[col] = le
                else:
                    le = self.label_encoders.get(col)
                    if le is not None:
                        # Vectorized encoding via dict lookup (fast on 1M+ rows)
                        label_map = {label: idx for idx, label in enumerate(le.classes_)}
                        df[encoded_col] = df[col].astype(str).map(label_map).fillna(-1).astype(int)
                    else:
                        df[encoded_col] = 0

        return df

    def _get_feature_cols(self, df: pd.DataFrame) -> list:
        """Get available feature columns from the DataFrame."""
        return [c for c in FEATURE_COLS if c in df.columns]

    def fit(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> "XGBoostForecaster":
        """Fit XGBoost model.

        Args:
            df: Feature DataFrame (training data).
            target_col: Target column name.

        Returns:
            self
        """
        import xgboost as xgb

        df = self._encode_categoricals(df, fit=True)
        self.feature_cols = self._get_feature_cols(df)

        X = df[self.feature_cols].fillna(0)
        y = df[target_col].fillna(0)

        # Remove rows where all lag features are NaN (first ~28 days)
        lag_cols = [c for c in self.feature_cols if "lag" in c]
        if lag_cols:
            valid_mask = df[lag_cols].notna().any(axis=1)
            X = X[valid_mask]
            y = y[valid_mask]

        self.model = xgb.XGBRegressor(**self.params)
        self.model.fit(
            X, y,
            eval_set=[(X, y)],
            verbose=False,
        )

        logger.info(f"XGBoost fitted on {len(X)} samples with {len(self.feature_cols)} features")
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Generate predictions.

        Args:
            df: Feature DataFrame.

        Returns:
            Series of predictions (clipped to >= 0, NaN/inf replaced with 0).
        """
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        df = self._encode_categoricals(df, fit=False)
        X = df[self.feature_cols].fillna(0)
        predictions = self.model.predict(X)

        # Guard: replace any NaN/inf from XGBoost with 0
        predictions = np.where(np.isfinite(predictions), predictions, 0)

        return pd.Series(np.clip(predictions, 0, None), index=df.index)

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get feature importance ranking.

        Args:
            top_n: Number of top features to return.

        Returns:
            DataFrame with feature names and importance scores.
        """
        if self.model is None:
            return pd.DataFrame()

        importance = pd.DataFrame({
            "feature": self.feature_cols,
            "importance": self.model.feature_importances_,
        }).sort_values("importance", ascending=False)

        return importance.head(top_n)
