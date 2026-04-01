"""
Bayesian Ridge Regression and ARD Regression forecasting models.

Variants:
- BayesianRidge (default sklearn settings)
- BayesianRidge (tuned alpha_1/lambda_1)
- ARDRegression (Automatic Relevance Determination)
- BayesianRidge with polynomial features on top lag features
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import BayesianRidge, ARDRegression
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.pipeline import Pipeline


class BayesianForecaster:
    """Bayesian forecaster wrapping sklearn Bayesian linear models."""

    def __init__(self, model_cls=BayesianRidge, **params):
        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", model_cls(**params)),
        ])

    def fit(self, X_train, y_train):
        self.pipeline.fit(X_train.fillna(0), y_train)

    def predict(self, X_test):
        return np.clip(self.pipeline.predict(X_test.fillna(0)), 0, None)


class BayesianRidgePolyForecaster:
    """BayesianRidge with degree-2 polynomial features on top lag columns only."""

    # Top lag/rolling features most correlated with demand
    LAG_COLS = [
        "demand_lag_1d",
        "demand_lag_7d",
        "rolling_mean_7d",
        "demand_same_weekday_last_week",
        "demand_same_weekday_avg_4weeks",
    ]

    def __init__(self, **params):
        self.params = params
        self.scaler = StandardScaler()
        self.poly = PolynomialFeatures(degree=2, include_bias=False)
        self.model = BayesianRidge(**params)
        self._lag_cols_present = []
        self._other_cols = []

    def _split_features(self, X):
        lag_present = [c for c in self.LAG_COLS if c in X.columns]
        other = [c for c in X.columns if c not in lag_present]
        return X[lag_present].fillna(0), X[other].fillna(0), lag_present, other

    def fit(self, X_train, y_train):
        X_lag, X_other, lag_cols, other_cols = self._split_features(X_train)
        self._lag_cols_present = lag_cols
        self._other_cols = other_cols

        X_poly = self.poly.fit_transform(X_lag)
        X_combined = np.hstack([X_poly, X_other.values])
        X_scaled = self.scaler.fit_transform(X_combined)
        self.model.fit(X_scaled, y_train)

    def predict(self, X_test):
        X_lag = X_test[self._lag_cols_present].fillna(0)
        X_other = X_test[self._other_cols].fillna(0)
        X_poly = self.poly.transform(X_lag)
        X_combined = np.hstack([X_poly, X_other.values])
        X_scaled = self.scaler.transform(X_combined)
        return np.clip(self.model.predict(X_scaled), 0, None)
