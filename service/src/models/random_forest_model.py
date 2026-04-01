"""Random Forest forecasting model for demand prediction."""

import numpy as np
from sklearn.ensemble import RandomForestRegressor


class RFForecaster:
    """Random Forest demand forecaster.

    Args:
        **params: Keyword arguments passed directly to RandomForestRegressor.
                  Defaults: n_estimators=100, random_state=42, n_jobs=-1.
    """

    def __init__(self, **params):
        defaults = {"n_estimators": 100, "random_state": 42, "n_jobs": -1}
        defaults.update(params)
        self.model = RandomForestRegressor(**defaults)
        self.params = defaults

    def fit(self, X_train, y_train):
        self.model.fit(X_train.fillna(0), y_train)

    def predict(self, X_test):
        return np.clip(self.model.predict(X_test.fillna(0)), 0, None)
