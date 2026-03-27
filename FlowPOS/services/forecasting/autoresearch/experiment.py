"""
Experiment file for autoresearch. THIS FILE IS MODIFIED BY THE AGENT.

Current best: 5,393,255 DKK (40/60 blend + 22% safety buffer, all data).

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

class StoreGlobalBlendModel:
    """
    Blends a global RF model with per-store ExtraTrees models.
    ExtraTrees is faster and can capture different patterns.
    """

    def __init__(self, global_weight=0.6, n_estimators=100, random_state=42, safety_buffer=1.22):
        self.global_weight = global_weight
        self.store_weight = 1.0 - global_weight
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.safety_buffer = safety_buffer
        self.global_model = None
        self.store_models = {}
        self.feature_cols_ = None

    def fit(self, X, y, sample_weight=None):
        self.feature_cols_ = list(X.columns) if hasattr(X, 'columns') else None

        # Global RF model
        self.global_model = RandomForestRegressor(
            n_estimators=200,   # more trees for better global model
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

            if len(y_store) < 10:
                continue

            # ExtraTrees per-store: faster, different random splits
            store_model = ExtraTreesRegressor(
                n_estimators=50,
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

        global_preds = self.global_model.predict(X_arr)
        store_preds = global_preds.copy()

        if self.feature_cols_ is not None:
            store_col_idx = self.feature_cols_.index('place_id_encoded')
        else:
            store_col_idx = -3

        store_ids = X_arr[:, store_col_idx]

        for store_id in np.unique(store_ids):
            if store_id not in self.store_models:
                continue
            mask = store_ids == store_id
            store_preds[mask] = self.store_models[store_id].predict(X_arr[mask])

        blended = self.store_weight * store_preds + self.global_weight * global_preds
        return np.clip(blended * self.safety_buffer, 0, None)


def build_model():
    """Return a model instance with fit() and predict() methods."""
    return StoreGlobalBlendModel(
        global_weight=0.6,
        n_estimators=200,   # 200 trees global RF + ET per-store
        random_state=42,
        safety_buffer=1.22,
    )


# =============================================================================
# TRAINING CONFIG (agent modifies this)
# =============================================================================

TRAIN_DAYS = None
DECAY_HALF_LIFE = None


# =============================================================================
# ENTRY POINT (do not modify the interface, only the contents above)
# =============================================================================

if __name__ == "__main__":
    from evaluate import run_experiment, print_results

    results = run_experiment(
        build_model_fn=build_model,
        description="RF(200,min_leaf=2) global + ExtraTrees per-store 60/40 + 22% buffer",
        train_days=TRAIN_DAYS,
        decay_half_life=DECAY_HALF_LIFE,
    )
    print_results(results)
