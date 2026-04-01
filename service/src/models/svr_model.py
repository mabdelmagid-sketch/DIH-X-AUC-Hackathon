"""
SVR (Support Vector Regression) forecasting models.

Uses LinearSVR and SGDRegressor with epsilon-insensitive loss for scalability.
Standard SVR is O(n^2/n^3) and cannot scale to 300k+ rows.
"""

import numpy as np
from sklearn.svm import LinearSVR
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline


class SVRForecaster:
    """LinearSVR-based forecaster with StandardScaler pipeline."""

    def __init__(self, C=1.0, max_iter=10000, **kwargs):
        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", LinearSVR(C=C, max_iter=max_iter, **kwargs)),
        ])

    def fit(self, X_train, y_train):
        self.pipeline.fit(X_train.fillna(0), y_train)

    def predict(self, X_test):
        return np.clip(self.pipeline.predict(X_test.fillna(0)), 0, None)


class SGDSVRForecaster:
    """SGDRegressor with epsilon_insensitive loss (SVR-equivalent, very fast)."""

    def __init__(self, loss="epsilon_insensitive", epsilon=0.1, alpha=0.0001,
                 max_iter=1000, **kwargs):
        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", SGDRegressor(
                loss=loss,
                epsilon=epsilon,
                alpha=alpha,
                max_iter=max_iter,
                random_state=42,
                **kwargs,
            )),
        ])

    def fit(self, X_train, y_train):
        self.pipeline.fit(X_train.fillna(0), y_train)

    def predict(self, X_test):
        return np.clip(self.pipeline.predict(X_test.fillna(0)), 0, None)
