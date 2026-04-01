"""
Croston's Method for Intermittent Demand Forecasting.

Croston's method decomposes intermittent demand into:
  - z: size of non-zero demands (smoothed)
  - p: inter-arrival times between non-zero demands (smoothed)
  Forecast = z_hat / p_hat

The SBA (Syntetos-Boylan Approximation) variant applies a bias correction:
  Forecast = z_hat / p_hat * (1 - alpha/2)

Since the benchmark harness provides pre-engineered tabular features (not raw
time series), this implementation adapts Croston's logic to the feature space:
  - Uses lag/rolling features to estimate demand size (z_hat)
  - Uses zero-fraction features to estimate inter-arrival time (p_hat)
  - Applies SBA bias correction optionally

Variants implemented:
  - CrostonClassic: alpha=0.1, no bias correction
  - CrostonSBA: alpha=0.1, with SBA bias correction
  - CrostonTuned: alpha=0.2, no bias correction
  - CrostonHybrid: Croston for sparse series, MA7 for dense series
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _estimate_zero_fraction(X: pd.DataFrame) -> np.ndarray:
    """Estimate fraction of zero-demand days from rolling features.

    Uses the ratio of rolling_std to rolling_mean as a proxy for intermittency.
    When mean is low and std is low, demand is consistently near zero.
    Falls back to a heuristic using demand_lag_1d.
    """
    zero_frac = np.zeros(len(X))

    if "rolling_mean_7d" in X.columns and "rolling_std_7d" in X.columns:
        mean7 = X["rolling_mean_7d"].fillna(0).values
        std7 = X["rolling_std_7d"].fillna(0).values

        # Items with very low mean are mostly zero
        # Approximate zero fraction using coefficient of variation heuristic
        # If mean is near 0, almost all days are zero
        with np.errstate(divide="ignore", invalid="ignore"):
            cv = np.where(mean7 > 0, std7 / mean7, 1.0)

        # Map CV to zero fraction: high CV -> more intermittent
        # zero_frac in [0, 1]: 0 = always demand, 1 = always zero
        # Empirically: for Poisson-like data, cv ~ 1/sqrt(mean) when mean << 1
        # We use the clipped mean as a proxy
        max_mean = mean7.max() if mean7.max() > 0 else 1.0
        zero_frac = np.clip(1.0 - mean7 / (mean7 + 0.5), 0.0, 1.0)

    elif "demand_lag_1d" in X.columns:
        lag1 = X["demand_lag_1d"].fillna(0).values
        zero_frac = (lag1 == 0).astype(float)

    return zero_frac


def _croston_predict(
    X: pd.DataFrame,
    alpha: float = 0.1,
    sba_correction: bool = False,
    fitted_z: Optional[float] = None,
    fitted_p: Optional[float] = None,
) -> np.ndarray:
    """Core Croston prediction logic adapted for tabular feature data.

    Parameters
    ----------
    X : pd.DataFrame
        Test feature matrix with pre-engineered demand features.
    alpha : float
        Exponential smoothing parameter (0 < alpha < 1).
    sba_correction : bool
        Apply Syntetos-Boylan bias correction: multiply by (1 - alpha/2).
    fitted_z : float or None
        Pre-fitted demand size estimate (from training set).
    fitted_p : float or None
        Pre-fitted inter-arrival estimate (from training set).

    Returns
    -------
    np.ndarray
        Predicted demand values, clipped to >= 0.
    """
    # Estimate demand size (z_hat) from rolling/lag features
    if "rolling_mean_7d" in X.columns:
        raw_demand = X["rolling_mean_7d"].fillna(0).values
    elif "demand_lag_7d" in X.columns:
        raw_demand = X["demand_lag_7d"].fillna(0).values
    else:
        raw_demand = np.zeros(len(X))

    # Use expanding_mean as a secondary signal for non-zero demand size
    if "expanding_mean" in X.columns:
        exp_mean = X["expanding_mean"].fillna(0).values
        # Blend: weight rolling more heavily for recency
        raw_demand = 0.7 * raw_demand + 0.3 * exp_mean

    # Estimate inter-arrival time (p_hat) from zero fraction
    zero_frac = _estimate_zero_fraction(X)
    # p_hat: avg days between non-zero demands = 1 / (1 - zero_frac)
    # Clamp to avoid division by zero: min non-zero rate = 0.01
    non_zero_rate = np.clip(1.0 - zero_frac, 0.01, 1.0)
    p_hat = 1.0 / non_zero_rate

    # z_hat: conditional demand size (demand given a non-zero day)
    # = rolling_mean / non_zero_rate  (reverses the averaging over zero days)
    z_hat = np.where(non_zero_rate > 0, raw_demand / non_zero_rate, raw_demand)

    # Apply exponential smoothing update: blend fitted values with current estimates
    if fitted_z is not None:
        z_hat = alpha * z_hat + (1 - alpha) * fitted_z
    if fitted_p is not None:
        p_hat = alpha * p_hat + (1 - alpha) * fitted_p

    # Croston forecast: z_hat / p_hat = conditional demand * non-zero rate
    forecast = z_hat / np.maximum(p_hat, 1e-6)

    # SBA bias correction
    if sba_correction:
        forecast = forecast * (1.0 - alpha / 2.0)

    return np.clip(forecast, 0.0, None)


class CrostonClassic:
    """Croston's classic method (alpha=0.1, no bias correction)."""

    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self.name = "croston_classic"
        self._fitted_z: Optional[float] = None
        self._fitted_p: Optional[float] = None

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "CrostonClassic":
        """Fit by computing training-set z and p estimates.

        Args:
            X_train: Feature matrix (training).
            y_train: Target demand values (training).

        Returns:
            self
        """
        y = y_train.fillna(0).values

        # Estimate global z (mean of non-zero demands)
        non_zero_mask = y > 0
        if non_zero_mask.any():
            self._fitted_z = y[non_zero_mask].mean()
        else:
            self._fitted_z = 0.0

        # Estimate global p (average inter-arrival time)
        zero_frac = (y == 0).mean()
        non_zero_rate = max(1.0 - zero_frac, 0.01)
        self._fitted_p = 1.0 / non_zero_rate

        logger.info(
            f"[{self.name}] Fitted: z_hat={self._fitted_z:.4f}, "
            f"p_hat={self._fitted_p:.4f}, zero_frac={zero_frac:.3f}"
        )
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        """Generate Croston demand forecasts.

        Args:
            X_test: Feature matrix (test).

        Returns:
            Array of predicted demand values.
        """
        return _croston_predict(
            X_test,
            alpha=self.alpha,
            sba_correction=False,
            fitted_z=self._fitted_z,
            fitted_p=self._fitted_p,
        )


class CrostonSBA:
    """Croston SBA variant (Syntetos-Boylan Approximation, alpha=0.1).

    Applies bias correction: forecast *= (1 - alpha/2).
    Shown to be less biased than classic Croston for most intermittent series.
    """

    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self.name = "croston_sba"
        self._fitted_z: Optional[float] = None
        self._fitted_p: Optional[float] = None

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "CrostonSBA":
        y = y_train.fillna(0).values

        non_zero_mask = y > 0
        if non_zero_mask.any():
            self._fitted_z = y[non_zero_mask].mean()
        else:
            self._fitted_z = 0.0

        zero_frac = (y == 0).mean()
        non_zero_rate = max(1.0 - zero_frac, 0.01)
        self._fitted_p = 1.0 / non_zero_rate

        logger.info(
            f"[{self.name}] Fitted: z_hat={self._fitted_z:.4f}, "
            f"p_hat={self._fitted_p:.4f}, zero_frac={zero_frac:.3f}"
        )
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        return _croston_predict(
            X_test,
            alpha=self.alpha,
            sba_correction=True,
            fitted_z=self._fitted_z,
            fitted_p=self._fitted_p,
        )


class CrostonTuned:
    """Croston with higher smoothing (alpha=0.2) for faster adaptation."""

    def __init__(self, alpha: float = 0.2):
        self.alpha = alpha
        self.name = "croston_tuned"
        self._fitted_z: Optional[float] = None
        self._fitted_p: Optional[float] = None

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "CrostonTuned":
        y = y_train.fillna(0).values

        non_zero_mask = y > 0
        if non_zero_mask.any():
            self._fitted_z = y[non_zero_mask].mean()
        else:
            self._fitted_z = 0.0

        zero_frac = (y == 0).mean()
        non_zero_rate = max(1.0 - zero_frac, 0.01)
        self._fitted_p = 1.0 / non_zero_rate

        logger.info(
            f"[{self.name}] Fitted: z_hat={self._fitted_z:.4f}, "
            f"p_hat={self._fitted_p:.4f}, zero_frac={zero_frac:.3f}"
        )
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        return _croston_predict(
            X_test,
            alpha=self.alpha,
            sba_correction=False,
            fitted_z=self._fitted_z,
            fitted_p=self._fitted_p,
        )


class CrostonHybrid:
    """Hybrid: Croston SBA for sparse items, MA7 for dense items.

    Classifies each test row by the sparsity of its store-item pair (estimated
    from rolling_mean_7d and rolling_std_7d). Items with >50% zero days use
    Croston SBA; others use a 7-day moving average.

    The sparsity threshold can be adjusted via `sparse_threshold`.
    """

    def __init__(self, alpha: float = 0.1, sparse_threshold: float = 0.5):
        self.alpha = alpha
        self.sparse_threshold = sparse_threshold
        self.name = "croston_hybrid"
        self._fitted_z: Optional[float] = None
        self._fitted_p: Optional[float] = None
        self._train_zero_frac: float = 0.0

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "CrostonHybrid":
        y = y_train.fillna(0).values

        non_zero_mask = y > 0
        if non_zero_mask.any():
            self._fitted_z = y[non_zero_mask].mean()
        else:
            self._fitted_z = 0.0

        self._train_zero_frac = (y == 0).mean()
        non_zero_rate = max(1.0 - self._train_zero_frac, 0.01)
        self._fitted_p = 1.0 / non_zero_rate

        logger.info(
            f"[{self.name}] Fitted: z_hat={self._fitted_z:.4f}, "
            f"p_hat={self._fitted_p:.4f}, zero_frac={self._train_zero_frac:.3f}, "
            f"sparse_threshold={self.sparse_threshold}"
        )
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        """Hybrid prediction: Croston SBA for sparse rows, MA7 for dense rows.

        Args:
            X_test: Feature matrix (test).

        Returns:
            Array of predicted demand values.
        """
        # Determine sparsity per row
        zero_frac = _estimate_zero_fraction(X_test)
        is_sparse = zero_frac >= self.sparse_threshold

        # Croston SBA predictions for all rows
        croston_preds = _croston_predict(
            X_test,
            alpha=self.alpha,
            sba_correction=True,
            fitted_z=self._fitted_z,
            fitted_p=self._fitted_p,
        )

        # MA7 predictions for dense rows
        if "rolling_mean_7d" in X_test.columns:
            ma7_preds = X_test["rolling_mean_7d"].fillna(0).values
        else:
            ma7_preds = np.zeros(len(X_test))

        # Combine: Croston for sparse, MA7 for dense
        predictions = np.where(is_sparse, croston_preds, ma7_preds)
        return np.clip(predictions, 0.0, None)
