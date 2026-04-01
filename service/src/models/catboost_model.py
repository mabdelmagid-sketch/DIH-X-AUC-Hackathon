"""CatBoost gradient boosting model for demand forecasting.

CatBoost natively handles categorical features without preprocessing,
making it well-suited for store-item demand forecasting where place_id
and item_id are high-cardinality categoricals.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Indices of categorical features within the feature list used by the harness
# These are the last two columns: place_id_encoded, item_id_encoded
# CatBoost accepts integer-encoded categoricals directly when cat_features indices are given
CAT_FEATURE_NAMES = ["place_id_encoded", "item_id_encoded"]


class CatBoostForecaster:
    """CatBoost model for tabular demand forecasting.

    Leverages CatBoost's native categorical feature handling for
    place_id_encoded and item_id_encoded, which avoids information loss
    from treating integer-encoded IDs as continuous numeric values.
    """

    def __init__(self, **params):
        self.params = {
            "iterations": params.get("iterations", 600),
            "depth": params.get("depth", 6),
            "learning_rate": params.get("learning_rate", 0.05),
            "loss_function": "RMSE",
            "eval_metric": "RMSE",
            "random_seed": 42,
            "thread_count": -1,
            "verbose": False,
            "allow_writing_files": False,
        }
        # Override defaults with any extra user-supplied params
        for k, v in params.items():
            if k not in ("iterations", "depth", "learning_rate"):
                self.params[k] = v

        self.model = None
        self.cat_feature_indices = []
        self.feature_cols = []

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "CatBoostForecaster":
        """Fit CatBoost model.

        Args:
            X_train: Feature DataFrame (from benchmark harness).
            y_train: Target series (quantity_sold).

        Returns:
            self
        """
        from catboost import CatBoostRegressor, Pool

        self.feature_cols = list(X_train.columns)

        # Identify categorical feature indices
        self.cat_feature_indices = [
            i for i, col in enumerate(self.feature_cols)
            if col in CAT_FEATURE_NAMES
        ]

        X = X_train.fillna(0)
        y = y_train.fillna(0).values

        # CatBoost Pool with categorical feature indices
        train_pool = Pool(
            data=X,
            label=y,
            cat_features=self.cat_feature_indices,
        )

        self.model = CatBoostRegressor(**self.params)
        self.model.fit(train_pool)

        logger.info(
            f"CatBoost fitted on {len(X)} samples, "
            f"{len(self.feature_cols)} features, "
            f"{len(self.cat_feature_indices)} cat features"
        )
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        """Generate predictions.

        Args:
            X_test: Feature DataFrame.

        Returns:
            Array of predictions clipped to >= 0.
        """
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        from catboost import Pool

        X = X_test[self.feature_cols].fillna(0)
        test_pool = Pool(data=X, cat_features=self.cat_feature_indices)
        predictions = self.model.predict(test_pool)
        return np.clip(predictions, 0, None)

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get feature importance ranking."""
        if self.model is None:
            return pd.DataFrame()

        importance = pd.DataFrame({
            "feature": self.feature_cols,
            "importance": self.model.get_feature_importance(),
        }).sort_values("importance", ascending=False)

        return importance.head(top_n)
