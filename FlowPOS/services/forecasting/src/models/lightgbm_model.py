"""
LightGBM demand forecasting model for FlowPOS.

Implements fit/predict interface compatible with the benchmark harness.
"""

import numpy as np
import pandas as pd
import lightgbm as lgb


class LightGBMForecaster:
    """LightGBM-based demand forecaster.

    Designed for sparse restaurant demand data (84.5% zero-demand days).
    Supports multiple hyperparameter configurations via constructor kwargs.
    """

    DEFAULT_PARAMS = {
        "objective": "regression_l1",   # MAE loss — robust to outliers/zeros
        "metric": "mae",
        "n_estimators": 500,
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_child_samples": 10,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "reg_alpha": 0.0,
        "reg_lambda": 1.0,
        "n_jobs": -1,
        "verbose": -1,
        "random_state": 42,
    }

    def __init__(self, **params):
        merged = {**self.DEFAULT_PARAMS, **params}
        self.model = lgb.LGBMRegressor(**merged)
        self.params = merged

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series):
        self.model.fit(X_train, y_train)
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        preds = self.model.predict(X_test)
        return np.clip(preds, 0, None)
