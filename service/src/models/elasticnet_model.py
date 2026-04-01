"""
ElasticNet / Ridge / Lasso forecasting models using sklearn Pipelines with StandardScaler.
"""
import numpy as np
from sklearn.linear_model import ElasticNet, Ridge, Lasso
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline


class LinearForecaster:
    """Generic linear forecaster wrapping any sklearn linear model with StandardScaler."""

    def __init__(self, model_cls, **params):
        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", model_cls(**params)),
        ])

    def fit(self, X_train, y_train):
        self.pipeline.fit(X_train.fillna(0), y_train)

    def predict(self, X_test):
        return np.clip(self.pipeline.predict(X_test.fillna(0)), 0, None)
