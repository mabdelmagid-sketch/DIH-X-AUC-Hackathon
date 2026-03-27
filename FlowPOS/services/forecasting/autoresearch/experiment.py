"""
Experiment file for autoresearch. THIS FILE IS MODIFIED BY THE AGENT.

Current best: 5,228,622 DKK (feature interactions + RF(300,min_leaf=2) global + ET(800) per-store 75/25 + decay hl=12d + 27% buffer).

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

    def _add_interactions(self, X):
        """Add multiplicative interaction features."""
        X_arr = X.values if hasattr(X, 'values') else X
        cols = self.feature_cols_
        if cols is None:
            return X_arr

        idx = {c: i for i, c in enumerate(cols)}

        # Key interactions for zero-inflated demand forecasting
        lag7 = X_arr[:, idx['demand_lag_7d']]
        dow = X_arr[:, idx['day_of_week']]
        roll7 = X_arr[:, idx['rolling_mean_7d']]
        is_wknd = X_arr[:, idx['is_weekend']]
        days_start = X_arr[:, idx['days_since_start']]
        exp_mean = np.maximum(X_arr[:, idx['expanding_mean']], 0.01)

        interactions = np.column_stack([
            lag7 * (dow + 1),            # lag * day_of_week
            roll7 * is_wknd,             # rolling_mean * weekend
            roll7 * days_start / 45.0,   # trend in rolling_mean (normalized)
            lag7 / exp_mean,             # lag relative to expanding mean
        ])

        return np.concatenate([X_arr, interactions], axis=1)

    def fit(self, X, y, sample_weight=None):
        self.feature_cols_ = list(X.columns) if hasattr(X, 'columns') else None
        X_arr = X.values if hasattr(X, 'values') else X
        X_aug = self._add_interactions(X)
        y_arr = np.array(y)

        self.global_model = RandomForestRegressor(
            n_estimators=300,
            random_state=self.random_state,
            n_jobs=-1,
            min_samples_leaf=2,
        )
        if sample_weight is not None:
            self.global_model.fit(X_aug, y_arr, sample_weight=sample_weight)
        else:
            self.global_model.fit(X_aug, y_arr)

        if self.feature_cols_ is not None:
            store_col_idx = self.feature_cols_.index('place_id_encoded')
        else:
            store_col_idx = -3

        store_ids = X_arr[:, store_col_idx]

        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            X_store = X_aug[mask]
            y_store = y_arr[mask]
            w_store = sample_weight[mask] if sample_weight is not None else None
            n_store = len(y_store)

            if n_store < 10:
                self.store_weights[store_id] = 1.0
                continue

            store_model = ExtraTreesRegressor(
                n_estimators=800,
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
        X_aug = self._add_interactions(X)

        global_preds = self.global_model.predict(X_aug)
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
            store_pred = self.store_models[store_id].predict(X_aug[mask])
            result[mask] = sw * store_pred + gw * global_preds[mask]

        return np.clip(result * self.safety_buffer, 0, None)


def build_model():
    """Return a model instance with fit() and predict() methods."""
    return AdaptiveBlendModel(
        base_global_weight=0.75,
        min_store_samples=200,
        random_state=42,
        safety_buffer=1.25,
    )


# =============================================================================
# TRAINING CONFIG (agent modifies this)
# =============================================================================

TRAIN_DAYS = None
DECAY_HALF_LIFE = 12


# =============================================================================
# ENTRY POINT (do not modify the interface, only the contents above)
# =============================================================================

if __name__ == "__main__":
    from evaluate import run_experiment, print_results

    results = run_experiment(
        build_model_fn=build_model,
        description="Feature interactions + adaptive blend RF(300) global + ET(800) per-store 75/25 + decay hl=12d + 25% buffer",
        train_days=TRAIN_DAYS,
        decay_half_life=DECAY_HALF_LIFE,
    )
    print_results(results)
