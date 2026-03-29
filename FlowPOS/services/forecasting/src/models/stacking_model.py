"""
Stacking Meta-Learner Ensemble for demand forecasting.

Uses sklearn StackingRegressor with multiple base models and meta-learners.
"""

import numpy as np
from sklearn.ensemble import StackingRegressor, RandomForestRegressor, ExtraTreesRegressor
from sklearn.linear_model import Ridge
import xgboost as xgb


class StackingForecaster:
    """Stacking ensemble forecaster using sklearn StackingRegressor."""

    def __init__(self, base_estimators, meta_learner, cv=3, name="StackingForecaster"):
        self.name = name
        self.model = StackingRegressor(
            estimators=base_estimators,
            final_estimator=meta_learner,
            cv=cv,
            n_jobs=-1,
        )

    def fit(self, X_train, y_train):
        self.model.fit(X_train.fillna(0), y_train)

    def predict(self, X_test):
        return np.clip(self.model.predict(X_test.fillna(0)), 0, None)


def build_stacking_ridge_meta():
    """Full stack: XGB + RF + Ridge, meta-learner = Ridge."""
    base = [
        ("xgb", xgb.XGBRegressor(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            n_jobs=-1, random_state=42, verbosity=0,
        )),
        ("rf", RandomForestRegressor(
            n_estimators=200, n_jobs=-1, random_state=42,
        )),
        ("ridge", Ridge(alpha=1.0)),
    ]
    return StackingForecaster(base, Ridge(alpha=1.0), cv=3, name="Stacking_Ridge_Meta")


def build_stacking_xgb_meta():
    """Tree-only stack: XGB + RF + ET, meta-learner = XGBoost."""
    base = [
        ("xgb", xgb.XGBRegressor(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            n_jobs=-1, random_state=42, verbosity=0,
        )),
        ("rf", RandomForestRegressor(
            n_estimators=200, n_jobs=-1, random_state=42,
        )),
        ("et", ExtraTreesRegressor(
            n_estimators=200, n_jobs=-1, random_state=42,
        )),
    ]
    meta = xgb.XGBRegressor(
        n_estimators=100, max_depth=4, random_state=42, verbosity=0,
    )
    return StackingForecaster(base, meta, cv=3, name="Stacking_XGB_Meta")
