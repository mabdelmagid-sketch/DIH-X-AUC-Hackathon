"""
trainer.py -- Loving Loyalty AI Suite, Pillar 1: Sales Forecasting

Trains the AdaptiveBlendModel and saves three production variants:

  balanced            -- newsvendor buffer fully applied (default)
  waste_optimized     -- buffer x 0.90 (accepts more stockout risk, less waste)
  stockout_optimized  -- buffer x 1.06 (reduces stockout frequency)

Model architecture (from autoresearch best result, cost 5,225,357 DKK):
  - RF(n_estimators=300, min_samples_leaf=2)  -- global model
  - ExtraTrees(n_estimators=800)              -- per-store model
  - 75/25 adaptive blend: weight favours global model until
    min_store_samples=100 training rows are available per store
  - Exponential decay weighting (half_life=12 days)
  - Newsvendor safety buffer per item

Newsvendor buffer:
  critical_ratio = 1.5 / (1.5 + 0.3) = 0.833
  buffer = 1 + z_{0.833} * sigma / mean_demand
  z_{0.833} ≈ 0.967  (standard normal quantile)
  Clamped to [1.0, 2.0].
  Fallback 1.27 for items with < 30 days of history.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor

from .feature_engineer import FeatureEngineer, FEATURE_COLS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CRITICAL_RATIO = 1.5 / (1.5 + 0.3)   # = 0.8333
_Z_CRITICAL = float(norm.ppf(_CRITICAL_RATIO))  # ≈ 0.967
_MIN_HISTORY_FOR_BUFFER = 30
_FALLBACK_BUFFER = 1.27
_BUFFER_CLAMP = (1.0, 2.0)

_DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[3] / "data" / "models"


# ---------------------------------------------------------------------------
# Adaptive blend model
# ---------------------------------------------------------------------------

class AdaptiveBlendModel:
    """RF(300) global + ExtraTrees(800) per-store with adaptive blend.

    The global-to-local blend weight is determined by how many training
    samples the store has.  Until ``min_store_samples`` rows are available
    for a store, the global model dominates (weight=base_global_weight=0.75).
    Once the store has enough data, weight transitions linearly toward
    pure-local (weight=0.0 = 100% local).

    Feature interactions are computed inline via ``_add_interactions``.
    """

    def __init__(
        self,
        base_global_weight: float = 0.75,
        min_store_samples: int = 100,
        random_state: int = 42,
    ) -> None:
        self.base_global_weight = base_global_weight
        self.min_store_samples = min_store_samples
        self.random_state = random_state

        self.global_model_: Optional[RandomForestRegressor] = None
        self.store_models_: dict[int, ExtraTreesRegressor] = {}
        self.store_weights_: dict[int, float] = {}
        self.feature_cols_: Optional[list[str]] = None

    # ------------------------------------------------------------------
    # Feature interactions (replicated from autoresearch/experiment.py)
    # ------------------------------------------------------------------

    def _add_interactions(self, X: np.ndarray) -> np.ndarray:
        if self.feature_cols_ is None:
            return X
        idx = {c: i for i, c in enumerate(self.feature_cols_)}
        try:
            lag7 = X[:, idx["demand_lag_7d"]]
            dow = X[:, idx["day_of_week"]]
            roll7 = X[:, idx["rolling_mean_7d"]]
            is_wknd = X[:, idx["is_weekend"]]
            days_start = X[:, idx["days_since_start"]]
            exp_mean = np.maximum(X[:, idx["expanding_mean"]], 0.01)
        except KeyError:
            return X

        interactions = np.column_stack([
            lag7 * (dow + 1),             # lag x day_of_week
            roll7 * is_wknd,              # rolling_mean x is_weekend
            roll7 * days_start / 45.0,    # trend in rolling_mean (normalised)
            lag7 / exp_mean,              # lag relative to lifetime mean
        ])
        return np.concatenate([X, interactions], axis=1)

    # ------------------------------------------------------------------
    # Fit
    # ------------------------------------------------------------------

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
    ) -> "AdaptiveBlendModel":
        self.feature_cols_ = list(X.columns)
        X_arr = X.values
        X_aug = self._add_interactions(X_arr)
        y_arr = np.array(y, dtype=float)

        logger.info("Training global RF(300) on %d samples, %d augmented features",
                    len(y_arr), X_aug.shape[1])

        self.global_model_ = RandomForestRegressor(
            n_estimators=300,
            min_samples_leaf=2,
            random_state=self.random_state,
            n_jobs=-1,
        )
        if sample_weight is not None:
            self.global_model_.fit(X_aug, y_arr, sample_weight=sample_weight)
        else:
            self.global_model_.fit(X_aug, y_arr)

        # Per-store ExtraTrees models
        store_col_idx = self.feature_cols_.index("place_id_encoded")
        store_ids = X_arr[:, store_col_idx]
        n_stores_trained = 0

        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            n_store = int(mask.sum())
            if n_store < 10:
                self.store_weights_[store_id] = 1.0  # use global entirely
                continue

            et = ExtraTreesRegressor(
                n_estimators=800,
                random_state=self.random_state,
                n_jobs=1,
            )
            w_store = sample_weight[mask] if sample_weight is not None else None
            if w_store is not None:
                et.fit(X_aug[mask], y_arr[mask], sample_weight=w_store)
            else:
                et.fit(X_aug[mask], y_arr[mask])

            self.store_models_[store_id] = et
            frac = min(n_store / self.min_store_samples, 1.0)
            self.store_weights_[store_id] = 1.0 - frac * (1.0 - self.base_global_weight)
            n_stores_trained += 1

        logger.info("Trained %d per-store ET(800) models", n_stores_trained)
        return self

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.global_model_ is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        X_arr = X.values if hasattr(X, "values") else np.array(X)
        X_aug = self._add_interactions(X_arr)
        global_preds = self.global_model_.predict(X_aug)
        result = global_preds.copy()

        store_col_idx = self.feature_cols_.index("place_id_encoded")
        store_ids = X_arr[:, store_col_idx]

        for store_id in np.unique(store_ids):
            mask = store_ids == store_id
            if store_id not in self.store_models_:
                continue
            gw = self.store_weights_.get(store_id, self.base_global_weight)
            sw = 1.0 - gw
            store_pred = self.store_models_[store_id].predict(X_aug[mask])
            result[mask] = sw * store_pred + gw * global_preds[mask]

        return np.clip(result, 0.0, None)

    # ------------------------------------------------------------------
    # Feature importance (from global model)
    # ------------------------------------------------------------------

    def feature_importances(self, top_n: int = 20) -> pd.DataFrame:
        if self.global_model_ is None or self.feature_cols_ is None:
            return pd.DataFrame(columns=["feature", "importance"])
        # Augmented feature names (the 4 interactions appended last)
        aug_names = list(self.feature_cols_) + [
            "interaction_lag7_dow", "interaction_roll7_wknd",
            "interaction_roll7_trend", "interaction_lag7_vs_expanding",
        ]
        importances = self.global_model_.feature_importances_
        n = min(len(aug_names), len(importances))
        df = pd.DataFrame({
            "feature": aug_names[:n],
            "importance": importances[:n],
        }).sort_values("importance", ascending=False).head(top_n)
        return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Newsvendor buffer computation
# ---------------------------------------------------------------------------

def compute_newsvendor_buffers(
    daily_df: pd.DataFrame,
    group_cols: Optional[list[str]] = None,
    target_col: str = "quantity_sold",
) -> dict[tuple, float]:
    """Compute per-item newsvendor safety buffer using rolling_std_14d.

    critical_ratio = 1.5 / (1.5 + 0.3) = 0.833
    z_0.833 = scipy.stats.norm.ppf(0.833) ≈ 0.967
    buffer = 1 + z_0.833 * (rolling_std_14d / mean_demand)  per item
    Clamped to [1.0, 2.0].  Falls back to 1.27 for items with < 30 days
    of history (SRS Task 4).

    The rolling_std_14d is the standard deviation of the 14-day rolling
    window anchored at the last available training date.  Using a
    recent rolling window captures current volatility better than the
    all-history std for fast-moving items.

    Args:
        daily_df: DataFrame with at least date, group_cols, target_col.
        group_cols: Grouping key (default ["place_id", "item_id"]).
        target_col: Demand column.

    Returns:
        Dict mapping group key tuple -> buffer multiplier float.
    """
    group_cols = group_cols or ["place_id", "item_id"]
    buffers: dict[tuple, float] = {}

    for key, grp in daily_df.groupby(group_cols, observed=True):
        demand = grp.sort_values("date")[target_col].dropna()
        n_days = len(demand)
        mean_d = float(demand.mean()) if n_days > 0 else 0.0

        if n_days < _MIN_HISTORY_FOR_BUFFER or mean_d < 0.01:
            buf = _FALLBACK_BUFFER
        else:
            # Use the most-recent 14-day rolling std for demand variability
            # (anchored at end of available history)
            rolling_std_14d = float(demand.rolling(window=14, min_periods=2).std().iloc[-1])
            if np.isnan(rolling_std_14d):
                rolling_std_14d = float(demand.std())

            buf = 1.0 + _Z_CRITICAL * rolling_std_14d / mean_d
            buf = float(np.clip(buf, *_BUFFER_CLAMP))

        key_t = key if isinstance(key, tuple) else (key,)
        buffers[key_t] = buf

    return buffers


# ---------------------------------------------------------------------------
# Main trainer class
# ---------------------------------------------------------------------------

class AdaptiveBlendTrainer:
    """End-to-end training pipeline for the AdaptiveBlendModel.

    Usage::

        from src.forecast.data_loader import DataLoader
        from src.forecast.trainer import AdaptiveBlendTrainer

        loader = DataLoader(source="csv")
        daily_df = loader.load_daily_demand(top_n_items=30)

        trainer = AdaptiveBlendTrainer()
        artifacts = trainer.fit(daily_df)
        # Saves balanced, waste_optimized, stockout_optimized to data/models/
    """

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        decay_half_life: float = 12.0,
        base_global_weight: float = 0.75,
        min_store_samples: int = 100,
        test_days: int = 14,
    ) -> None:
        self.models_dir = models_dir or _DEFAULT_MODELS_DIR
        self.decay_half_life = decay_half_life
        self.base_global_weight = base_global_weight
        self.min_store_samples = min_store_samples
        self.test_days = test_days

        self.feature_engineer_ = FeatureEngineer()
        self.model_: Optional[AdaptiveBlendModel] = None
        self.buffers_: dict[tuple, float] = {}

    def fit(
        self,
        daily_df: pd.DataFrame,
        save: bool = True,
    ) -> dict:
        """Train on ``daily_df`` and optionally save model artifacts.

        Args:
            daily_df: Output of DataLoader.load_daily_demand().
            save: If True, save balanced / waste_optimized / stockout_optimized
                  models to ``models_dir``.

        Returns:
            Dict with training metadata and feature column list.
        """
        daily_df = daily_df.copy()
        daily_df["date"] = pd.to_datetime(daily_df["date"])

        max_date = daily_df["date"].max()
        test_cutoff = max_date - pd.Timedelta(days=self.test_days)
        train_df = daily_df[daily_df["date"] <= test_cutoff].copy()

        logger.info("Feature engineering on training data (%d rows)", len(train_df))
        train_feat = self.feature_engineer_.fit_transform(train_df)

        # Compute newsvendor buffers from training data
        self.buffers_ = compute_newsvendor_buffers(train_df)

        # Prepare X, y
        feature_cols = self.feature_engineer_.get_feature_columns()
        available = [c for c in feature_cols if c in train_feat.columns]
        X_train = train_feat[available].fillna(0.0)
        y_train = train_feat["quantity_sold"].fillna(0.0)

        # Exponential decay sample weights (half-life=12 days)
        days_ago = (test_cutoff - train_feat["date"]).dt.days
        weights = np.exp(-np.log(2) * days_ago / self.decay_half_life)
        weights = weights / weights.mean()

        logger.info("Training AdaptiveBlendModel (%d rows, %d features)", len(X_train), X_train.shape[1])
        self.model_ = AdaptiveBlendModel(
            base_global_weight=self.base_global_weight,
            min_store_samples=self.min_store_samples,
        )
        self.model_.fit(X_train, y_train, sample_weight=weights.values)

        artifacts = {
            "feature_cols": available,
            "train_rows": len(X_train),
            "test_cutoff": str(test_cutoff.date()),
            "n_store_item_pairs": len(self.buffers_),
            "decay_half_life": self.decay_half_life,
        }

        if save:
            self.models_dir.mkdir(parents=True, exist_ok=True)
            self._save_variants(available)
            artifacts["models_saved"] = str(self.models_dir)

        return artifacts

    # ------------------------------------------------------------------
    # Save three output variants
    # ------------------------------------------------------------------

    def _save_variants(self, feature_cols: list[str]) -> None:
        """Save balanced, waste_optimized, stockout_optimized .pkl files."""
        payload_base = {
            "model": self.model_,
            "feature_engineer": self.feature_engineer_,
            "buffers": self.buffers_,
            "feature_cols": feature_cols,
        }

        variants = {
            "balanced_model.pkl": 1.0,
            "waste_optimized_model.pkl": 0.90,
            "stockout_optimized_model.pkl": 1.06,
        }

        for filename, buffer_scale in variants.items():
            payload = {**payload_base, "buffer_scale": buffer_scale}
            path = self.models_dir / filename
            joblib.dump(payload, path, compress=3)
            logger.info("Saved %s (buffer_scale=%.2f)", path, buffer_scale)
