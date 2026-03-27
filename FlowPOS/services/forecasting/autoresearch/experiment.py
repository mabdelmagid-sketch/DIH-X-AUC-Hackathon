"""
Experiment file for autoresearch. THIS FILE IS MODIFIED BY THE AGENT.

Current best: 40/60 per-store/global blend ~5,645K DKK.

The agent modifies this file to try different:
- Model architectures (RF, XGBoost, LightGBM, CatBoost, ensembles, blends)
- Hyperparameters (n_estimators, max_depth, learning_rate, etc.)
- Feature subsets (drop features, add interactions, select top-k)
- Training strategies (recency windows, decay weighting)
- Ensemble methods (blending, stacking, voting)
- Post-processing (rounding, clipping, safety buffers)

Everything below is fair game. The only constraint is that build_model()
returns an object with fit(X, y, sample_weight=None) and predict(X) methods.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor


# =============================================================================
# MODEL DEFINITION (agent modifies this)
# =============================================================================

class StoreGlobalBlendModel:
    """
    Blends a global RF model with per-store RF models.
    global_weight: fraction from global model (e.g. 0.6 means 60% global).
    store_weight = 1 - global_weight (e.g. 0.4 per-store).
    Known best: global_weight=0.6 (40% per-store, 60% global).
    """

    def __init__(self, global_weight=0.6, n_estimators=100, random_state=42):
        self.global_weight = global_weight
        self.store_weight = 1.0 - global_weight
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.global_model = None
        self.store_models = {}
        self.feature_cols_ = None

    def fit(self, X, y, sample_weight=None):
        self.feature_cols_ = list(X.columns) if hasattr(X, 'columns') else None

        # Train global model on all data
        self.global_model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
        )
        if sample_weight is not None:
            self.global_model.fit(X, y, sample_weight=sample_weight)
        else:
            self.global_model.fit(X, y)

        # Train per-store models
        X_arr = X.values if hasattr(X, 'values') else X
        y_arr = np.array(y)

        # Get place_id_encoded column index
        if self.feature_cols_ is not None:
            store_col_idx = self.feature_cols_.index('place_id_encoded')
        else:
            store_col_idx = -3  # fallback

        store_ids = X_arr[:, store_col_idx]
        unique_stores = np.unique(store_ids)

        for store_id in unique_stores:
            mask = store_ids == store_id
            X_store = X_arr[mask]
            y_store = y_arr[mask]
            w_store = sample_weight[mask] if sample_weight is not None else None

            # Only train per-store model if enough data
            if len(y_store) < 10:
                continue

            store_model = RandomForestRegressor(
                n_estimators=50,  # smaller for speed
                random_state=self.random_state,
                n_jobs=1,
            )
            if w_store is not None:
                store_model.fit(X_store, y_store, sample_weight=w_store)
            else:
                store_model.fit(X_store, y_store)

            self.store_models[store_id] = store_model

        return self

    def predict(self, X):
        X_arr = X.values if hasattr(X, 'values') else X

        # Global predictions
        global_preds = self.global_model.predict(X_arr)

        # Per-store predictions
        store_preds = global_preds.copy()  # fallback to global

        if self.feature_cols_ is not None:
            store_col_idx = self.feature_cols_.index('place_id_encoded')
        else:
            store_col_idx = -3

        store_ids = X_arr[:, store_col_idx]
        unique_stores = np.unique(store_ids)

        for store_id in unique_stores:
            if store_id not in self.store_models:
                continue
            mask = store_ids == store_id
            store_preds[mask] = self.store_models[store_id].predict(X_arr[mask])

        # Blend: store_weight * per-store + global_weight * global
        blended = self.store_weight * store_preds + self.global_weight * global_preds
        return np.clip(blended, 0, None)


def build_model():
    """Return a model instance with fit() and predict() methods."""
    return StoreGlobalBlendModel(
        global_weight=0.6,   # 60% global, 40% per-store
        n_estimators=100,
        random_state=42,
    )


# =============================================================================
# TRAINING CONFIG (agent modifies this)
# =============================================================================

# How many days of training data to use. None = all available (~47 days).
TRAIN_DAYS = None

# Exponential decay half-life in days. None = no decay (equal weights).
DECAY_HALF_LIFE = None


# =============================================================================
# ENTRY POINT (do not modify the interface, only the contents above)
# =============================================================================

if __name__ == "__main__":
    from evaluate import run_experiment, print_results

    results = run_experiment(
        build_model_fn=build_model,
        description="40% per-store + 60% global RF blend",
        train_days=TRAIN_DAYS,
        decay_half_life=DECAY_HALF_LIFE,
    )
    print_results(results)
