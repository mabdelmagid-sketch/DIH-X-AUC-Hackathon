"""
Experiment file for autoresearch. THIS FILE IS MODIFIED BY THE AGENT.

Current best: 5,260,180 DKK (RF(300,min_leaf=2) global + ET(100) per-store 75/25 + decay hl=14d + 22% buffer).

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
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor


# =============================================================================
# MODEL DEFINITION (agent modifies this)
# =============================================================================

class AdaptiveBlendModel:
    """
    Blends global RF with per-store ExtraTrees.
    Adaptive blend ratio: stores with more data get more weight on their own model.
    """

    def __init__(self, base_global_weight=0.75, min_store_samples=200,
                 random_state=42, safety_buffer=1.22):
        self.base_global_weight = base_global_weight
        self.min_store_samples = min_store_samples
        self.random_state = random_state
        self.safety_buffer = safety_buffer
        self.global_model = None
        self.store_models = {}
        self.store_weights = {}
        self.feature_cols_ = None

    def fit(self, X, y, sample_weight=None):
        self.feature_cols_ = list(X.columns) if hasattr(X, 'columns') else None

        self.global_model = RandomForestRegressor(
            n_estimators=300,
            random_state=self.random_state,
            n_jobs=-1,
            min_samples_leaf=2,
        )
        if sample_weight is not None:
            self.global_model.fit(X, y, sample_weight=sample_weight)
        else:
            self.global_model.fit(X, y)

        X_arr = X.values if hasattr(X, 'values') else X
        y_arr = np.array(y)

        if self.feature_cols_ is not None:
            store_col_idx = self.feature_cols_.index('place_id_encoded')
        else:
            store_col_idx = -3

        store_ids = X_arr[:, store_col_idx]

        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            X_store = X_arr[mask]
            y_store = y_arr[mask]
            w_store = sample_weight[mask] if sample_weight is not None else None
            n_store = len(y_store)

            if n_store < 10:
                self.store_weights[store_id] = 1.0
                continue

            store_model = ExtraTreesRegressor(
                n_estimators=100,
                random_state=self.random_state,
                n_jobs=1,
            )
            if w_store is not None:
                store_model.fit(X_store, y_store, sample_weight=w_store)
            else:
                store_model.fit(X_store, y_store)

            self.store_models[store_id] = store_model

            frac = min(n_store / self.min_store_samples, 1.0)
            self.store_weights[store_id] = 1.0 - frac * (1.0 - self.base_global_weight)

        return self

    def predict(self, X):
        X_arr = X.values if hasattr(X, 'values') else X

        global_preds = self.global_model.predict(X_arr)
        result = global_preds.copy()

        if self.feature_cols_ is not None:
            store_col_idx = self.feature_cols_.index('place_id_encoded')
        else:
            store_col_idx = -3

        store_ids = X_arr[:, store_col_idx]

        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            if store_id not in self.store_models:
                continue
            gw = self.store_weights.get(store_id, self.base_global_weight)
            sw = 1.0 - gw
            store_pred = self.store_models[store_id].predict(X_arr[mask])
            result[mask] = sw * store_pred + gw * global_preds[mask]

        return np.clip(result * self.safety_buffer, 0, None)


def build_model():
    """Return a model instance with fit() and predict() methods."""
    return AdaptiveBlendModel(
        base_global_weight=0.75,
        min_store_samples=200,
        random_state=42,
        safety_buffer=1.22,
    )


# =============================================================================
# TRAINING CONFIG (agent modifies this)
# =============================================================================

TRAIN_DAYS = None
DECAY_HALF_LIFE = 10


# =============================================================================
# ENTRY POINT (do not modify the interface, only the contents above)
# =============================================================================

if __name__ == "__main__":
    from evaluate import run_experiment, print_results

    results = run_experiment(
        build_model_fn=build_model,
        description="Adaptive blend RF(300) global + ET(100) per-store 75/25 + decay hl=10d + 22% buffer",
        train_days=TRAIN_DAYS,
        decay_half_life=DECAY_HALF_LIFE,
    )
    print_results(results)
