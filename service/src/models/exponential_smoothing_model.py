"""
Holt-Winters Exponential Smoothing models for demand forecasting.

Since the benchmark harness provides tabular feature data (not raw time series),
we implement exponential smoothing as feature-based models that combine lag and
rolling features using exponential decay weighting schemes.

Models implemented:
1. SES (Simple Exponential Smoothing) - alpha * lag_1d + (1-alpha) * rolling_mean_7d
2. WeightedETS - exponential decay combination of lag_1d, lag_7d, rolling_mean_7d
3. AdaptiveETS - learns optimal alpha from training data via linear regression
4. DampedTrend - adds trend component using lag differences
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


class SESModel:
    """
    Simple Exponential Smoothing using pre-computed lag/rolling features.

    Prediction = alpha * lag_1d + (1 - alpha) * rolling_mean_7d
    """

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.name = f"SES(alpha={alpha})"

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series):
        # No training needed - uses fixed alpha
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        lag_1d = X_test["demand_lag_1d"].fillna(0).values
        rolling_7d = X_test["rolling_mean_7d"].fillna(0).values
        return self.alpha * lag_1d + (1 - self.alpha) * rolling_7d


class WeightedETSModel:
    """
    Weighted ETS combining lag_1d, lag_7d, and rolling_mean_7d with
    exponential decay weights.

    Weights: w1 = alpha, w2 = (1-alpha)*alpha, w3 = (1-alpha)^2
    Normalized so they sum to 1.
    """

    def __init__(self, alpha: float = 0.2):
        self.alpha = alpha
        self.name = f"WeightedETS(alpha={alpha})"

        # Exponential decay weights
        w1 = alpha
        w2 = (1 - alpha) * alpha
        w3 = (1 - alpha) ** 2
        total = w1 + w2 + w3
        self.w1 = w1 / total
        self.w2 = w2 / total
        self.w3 = w3 / total

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series):
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        lag_1d = X_test["demand_lag_1d"].fillna(0).values
        lag_7d = X_test["demand_lag_7d"].fillna(0).values
        rolling_7d = X_test["rolling_mean_7d"].fillna(0).values
        return self.w1 * lag_1d + self.w2 * lag_7d + self.w3 * rolling_7d


class AdaptiveETSModel:
    """
    Adaptive ETS that learns optimal combination weights from training data
    via constrained linear regression on the lag and rolling features.
    """

    def __init__(self):
        self.name = "AdaptiveETS"
        self.lr = LinearRegression(fit_intercept=True, positive=True)
        self._feature_cols = [
            "demand_lag_1d",
            "demand_lag_7d",
            "rolling_mean_7d",
            "rolling_mean_14d",
            "demand_same_weekday_last_week",
        ]

    def _get_features(self, X: pd.DataFrame) -> np.ndarray:
        cols = [c for c in self._feature_cols if c in X.columns]
        return X[cols].fillna(0).values

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series):
        Xf = self._get_features(X_train)
        y = y_train.fillna(0).values
        self.lr.fit(Xf, y)
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        Xf = self._get_features(X_test)
        preds = self.lr.predict(Xf)
        return np.clip(preds, 0, None)


class DampedTrendETSModel:
    """
    Damped Trend ETS that adds a trend component computed from lag differences.

    trend = lag_1d - lag_7d (change over 6 days, scaled)
    prediction = alpha * lag_1d + (1-alpha) * rolling_mean_7d + phi * trend
    """

    def __init__(self, alpha: float = 0.3, phi: float = 0.1):
        self.alpha = alpha
        self.phi = phi  # damping factor for trend
        self.name = f"DampedTrendETS(alpha={alpha},phi={phi})"

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series):
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        lag_1d = X_test["demand_lag_1d"].fillna(0).values
        lag_7d = X_test["demand_lag_7d"].fillna(0).values
        rolling_7d = X_test["rolling_mean_7d"].fillna(0).values

        # Short-term trend: difference between most recent and week-ago demand
        trend = (lag_1d - lag_7d) / 7.0  # daily trend estimate

        level = self.alpha * lag_1d + (1 - self.alpha) * rolling_7d
        preds = level + self.phi * trend
        return np.clip(preds, 0, None)
