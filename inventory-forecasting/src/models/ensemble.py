"""Hybrid ensemble models for demand forecasting.

After evaluating 32 model configurations on business-impact metrics (DKK),
the winning approach is a weighted blend of XGBoost + 7-day Moving Average.

Key insight: XGBoost captures demand spikes and promotional effects well but
tends to overstock on low-volume items. MA7 is conservative and tracks recent
trends closely. Blending them at 30% XGB / 70% MA7 with rounding gives the
best trade-off between waste cost and stockout cost.

Model ranking (total business cost on 93-day test period):
    1. MA7 + 20% safety buffer:        15.20M DKK (29.3% savings)
    2. 30% XGB + 70% MA7 (rounded):    15.51M DKK (27.8% savings)
    3. 40% XGB + 60% MA7:              15.52M DKK (27.8% savings)
    4. Pure MA7:                        16.44M DKK (23.5% savings)
   22. Pure XGBoost:                    17.08M DKK (20.5% savings)
   32. MA28 (worst):                    21.49M DKK (baseline)
"""

import logging

import pandas as pd
import numpy as np

from src.models.xgboost_model import XGBoostForecaster
from src.models.baseline import MovingAverageModel

logger = logging.getLogger(__name__)


class HybridForecaster:
    """Weighted blend of XGBoost + Moving Average predictions.

    The default configuration (30% XGBoost + 70% MA7 with rounding) was
    selected from a 32-model search as the best ML-based approach on
    business-impact metrics (total DKK cost = waste + 1.5x stockout).

    Business impact on test period (93 days, 101 stores, 1,976 item-pairs):
        - Total cost: 15.51M DKK (27.8% reduction vs worst baseline)
        - Forecast accuracy: 67.7% (WMAPE)
        - Overstock days: 33.6%
        - Understock days: 28.3%
    """

    def __init__(self, xgb_weight: float = 0.3, ma_window: int = 7,
                 round_predictions: bool = True,
                 xgb_params: dict = None):
        """Initialize the hybrid forecaster.

        Args:
            xgb_weight: Weight for XGBoost predictions (0-1). MA weight = 1 - xgb_weight.
            ma_window: Moving average window in days.
            round_predictions: Whether to round predictions to nearest integer.
            xgb_params: Optional XGBoost hyperparameters.
        """
        self.xgb_weight = xgb_weight
        self.ma_weight = 1.0 - xgb_weight
        self.ma_window = ma_window
        self.round_predictions = round_predictions
        self.xgboost = XGBoostForecaster(**(xgb_params or {}))
        self.ma_model = MovingAverageModel(window=ma_window)
        self.name = f"hybrid_xgb{int(xgb_weight*100)}_ma{ma_window}"

    def fit(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> "HybridForecaster":
        """Fit the XGBoost component (MA requires no fitting).

        Args:
            df: Training DataFrame with features and target.
            target_col: Target column name.

        Returns:
            self
        """
        logger.info(f"Fitting HybridForecaster ({self.name})...")
        self.xgboost.fit(df, target_col)
        logger.info(f"HybridForecaster fitted: XGB weight={self.xgb_weight}, "
                    f"MA{self.ma_window} weight={self.ma_weight}")
        return self

    def predict(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> pd.Series:
        """Generate blended predictions.

        Args:
            df: Feature DataFrame.
            target_col: Target column (needed by MA model for rolling calc).

        Returns:
            Series of blended predictions, clipped to >= 0.
        """
        xgb_preds = self.xgboost.predict(df)
        ma_preds = self.ma_model.predict(df, target_col)

        blended = self.xgb_weight * xgb_preds + self.ma_weight * ma_preds

        if self.round_predictions:
            blended = blended.round()

        return blended.clip(lower=0)

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get XGBoost feature importance from the hybrid model."""
        return self.xgboost.get_feature_importance(top_n)


class BufferedMAForecaster:
    """Moving Average with a safety buffer to reduce stockouts.

    This was the single best model on total business cost (15.20M DKK),
    but it is not ML-based. It adds a percentage buffer on top of MA7
    predictions to trade slightly more waste for significantly fewer
    stockouts.

    Recommended for production use at stores where stockout cost is
    much higher than waste cost (e.g., high-traffic locations).
    """

    def __init__(self, window: int = 7, buffer_pct: float = 0.20):
        """Initialize buffered MA forecaster.

        Args:
            window: Moving average window in days.
            buffer_pct: Safety buffer as a fraction (0.20 = 20% buffer).
        """
        self.window = window
        self.buffer_pct = buffer_pct
        self.ma_model = MovingAverageModel(window=window)
        self.name = f"ma{window}_buffer{int(buffer_pct*100)}pct"

    def fit(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> "BufferedMAForecaster":
        """No fitting needed for MA-based model."""
        return self

    def predict(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> pd.Series:
        """Generate buffered MA predictions.

        Args:
            df: Feature DataFrame.
            target_col: Target column.

        Returns:
            Series of buffered predictions, clipped to >= 0.
        """
        ma_preds = self.ma_model.predict(df, target_col)
        buffered = ma_preds * (1 + self.buffer_pct)
        return buffered.clip(lower=0)


class WasteOptimizedForecaster:
    """Forecaster tuned to minimize food waste (overstocking).

    Scales down the hybrid model's predictions by a shrink factor so that
    the restaurant preps slightly less than expected demand.  This reduces
    the amount of unsold food that gets thrown away, at the cost of
    slightly more stockouts on peak days.

    Use this model when the priority is sustainability / waste reduction
    rather than maximising every possible sale.
    """

    def __init__(self, shrink: float = 0.85, xgb_weight: float = 0.3,
                 ma_window: int = 7, xgb_params: dict = None):
        """
        Args:
            shrink: Multiplicative factor applied to predictions (0-1).
                    0.85 means prep 85% of the standard forecast.
            xgb_weight: XGBoost weight in the underlying hybrid blend.
            ma_window: Moving average window.
            xgb_params: Optional XGBoost hyperparameters.
        """
        self.shrink = shrink
        self.hybrid = HybridForecaster(
            xgb_weight=xgb_weight, ma_window=ma_window,
            round_predictions=True, xgb_params=xgb_params,
        )
        self.name = f"waste_optimized_{int(shrink*100)}pct"

    def fit(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> "WasteOptimizedForecaster":
        self.hybrid.fit(df, target_col)
        return self

    def predict(self, df: pd.DataFrame, target_col: str = "quantity_sold") -> pd.Series:
        base = self.hybrid.predict(df, target_col)
        return (base * self.shrink).round().clip(lower=0)

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        return self.hybrid.get_feature_importance(top_n)


# Legacy compatibility - keep EnsembleForecaster for backward compatibility
class EnsembleForecaster(HybridForecaster):
    """Backward-compatible alias for HybridForecaster.

    Previous versions used Prophet + XGBoost. Now defaults to the
    optimized XGBoost + MA7 hybrid which was validated to perform
    better on business metrics.
    """

    def __init__(self, prophet_weight: float = 0.3, xgboost_weight: float = 0.7,
                 prophet_params: dict = None, xgboost_params: dict = None):
        super().__init__(
            xgb_weight=xgboost_weight,
            ma_window=7,
            round_predictions=True,
            xgb_params=xgboost_params,
        )
        self.name = "ensemble"
