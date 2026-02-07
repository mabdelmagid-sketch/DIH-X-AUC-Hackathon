"""Training pipeline: time-series split, cross-validation, hyperparameter tuning."""

import logging
from typing import Optional

import pandas as pd
import numpy as np

from src.models.baseline import NaiveLastWeekModel, MovingAverageModel
from src.models.xgboost_model import XGBoostForecaster
from src.models.prophet_model import ProphetForecaster
from src.models.ensemble import HybridForecaster, BufferedMAForecaster
from src.models.evaluator import evaluate_predictions

logger = logging.getLogger(__name__)


def time_series_split(df: pd.DataFrame, train_months: int = 30,
                      val_months: int = 3, test_months: int = 3) -> tuple:
    """Split data chronologically into train/validation/test sets.

    Args:
        df: Feature DataFrame with 'date' column.
        train_months: Number of months for training.
        val_months: Number of months for validation.
        test_months: Number of months for test.

    Returns:
        Tuple of (train_df, val_df, test_df).
    """
    df = df.sort_values("date").copy()
    dates = pd.to_datetime(df["date"])
    min_date = dates.min()

    train_end = min_date + pd.DateOffset(months=train_months)
    val_end = train_end + pd.DateOffset(months=val_months)
    test_end = val_end + pd.DateOffset(months=test_months)

    train = df[dates < train_end]
    val = df[(dates >= train_end) & (dates < val_end)]
    test = df[(dates >= val_end) & (dates < test_end)]

    # If there's not enough data, use ratio-based split
    if len(val) == 0 or len(test) == 0:
        n = len(df)
        train_idx = int(n * 0.7)
        val_idx = int(n * 0.85)
        train = df.iloc[:train_idx]
        val = df.iloc[train_idx:val_idx]
        test = df.iloc[val_idx:]

    logger.info(f"Split: train={len(train)}, val={len(val)}, test={len(test)}")
    return train, val, test


def walk_forward_validation(df: pd.DataFrame, model_class,
                            model_params: dict = None,
                            n_splits: int = 3,
                            train_window_months: int = 24,
                            test_window_months: int = 1,
                            target_col: str = "quantity_sold") -> list:
    """Walk-forward cross-validation with expanding window.

    Args:
        df: Feature DataFrame sorted by date.
        model_class: Model class to instantiate.
        model_params: Parameters for model constructor.
        n_splits: Number of CV splits.
        train_window_months: Minimum training window in months.
        test_window_months: Test window size in months.
        target_col: Target column name.

    Returns:
        List of metric dicts per split.
    """
    if model_params is None:
        model_params = {}

    df = df.sort_values("date").copy()
    dates = pd.to_datetime(df["date"])
    min_date = dates.min()
    max_date = dates.max()

    total_months = (max_date.year - min_date.year) * 12 + (max_date.month - min_date.month)
    test_total = n_splits * test_window_months
    train_start_months = total_months - test_total

    results = []
    for i in range(n_splits):
        train_end = min_date + pd.DateOffset(months=train_start_months + i * test_window_months)
        test_end = train_end + pd.DateOffset(months=test_window_months)

        train = df[dates < train_end]
        test = df[(dates >= train_end) & (dates < test_end)]

        if len(train) < 100 or len(test) < 10:
            continue

        model = model_class(**model_params)
        model.fit(train, target_col)
        preds = model.predict(test)

        test = test.copy()
        test["predicted"] = preds.values
        metrics = evaluate_predictions(test, target_col, "predicted")
        metrics["split"] = i
        results.append(metrics)

        logger.info(f"CV split {i}: train={len(train)}, test={len(test)}, "
                    f"MAE={metrics['overall']['mae']:.4f}")

    return results


def train_all_models(df: pd.DataFrame, config: dict = None,
                     target_col: str = "quantity_sold") -> dict:
    """Train and evaluate all models.

    Args:
        df: Complete feature DataFrame.
        config: Configuration dict with model params.
        target_col: Target column.

    Returns:
        Dict with trained models and evaluation results.
    """
    if config is None:
        config = {}

    # Split data
    train, val, test = time_series_split(df)

    results = {}

    # Baselines
    logger.info("=== Evaluating Baselines ===")
    for model in [NaiveLastWeekModel(), MovingAverageModel(7), MovingAverageModel(28)]:
        preds = model.predict(test, target_col)
        test_eval = test.copy()
        test_eval["predicted"] = preds.values
        metrics = evaluate_predictions(test_eval, target_col, "predicted")
        results[model.name] = {"model": model, "metrics": metrics}

    # XGBoost
    logger.info("=== Training XGBoost ===")
    xgb_params = config.get("model", {}).get("xgboost", {})
    xgb = XGBoostForecaster(**xgb_params)
    xgb.fit(train, target_col)
    xgb_preds = xgb.predict(test)
    test_eval = test.copy()
    test_eval["predicted"] = xgb_preds.values
    xgb_metrics = evaluate_predictions(test_eval, target_col, "predicted")
    results["xgboost"] = {"model": xgb, "metrics": xgb_metrics}

    # Prophet (optional - slower)
    logger.info("=== Training Prophet ===")
    try:
        prophet_params = config.get("model", {}).get("prophet", {})
        prophet = ProphetForecaster(**prophet_params)
        prophet.fit(train, target_col, top_n=10)
        prophet_preds = prophet.predict(test)
        test_eval = test.copy()
        test_eval["predicted"] = prophet_preds.values
        prophet_metrics = evaluate_predictions(test_eval, target_col, "predicted")
        results["prophet"] = {"model": prophet, "metrics": prophet_metrics}
    except Exception as e:
        logger.warning(f"Prophet training failed: {e}")

    # Hybrid: 30% XGBoost + 70% MA7 (best ML-based model)
    logger.info("=== Training Hybrid (30% XGB + 70% MA7) ===")
    hybrid = HybridForecaster(xgb_weight=0.3, ma_window=7,
                              round_predictions=True, xgb_params=xgb_params)
    hybrid.fit(train, target_col)
    hybrid_preds = hybrid.predict(test, target_col)
    test_eval = test.copy()
    test_eval["predicted"] = hybrid_preds.values
    hybrid_metrics = evaluate_predictions(test_eval, target_col, "predicted")
    results["hybrid_xgb30_ma7"] = {"model": hybrid, "metrics": hybrid_metrics}

    # Buffered MA7 (best overall model on business cost)
    logger.info("=== Evaluating Buffered MA7 (+20%) ===")
    buffered = BufferedMAForecaster(window=7, buffer_pct=0.20)
    buffered_preds = buffered.predict(test, target_col)
    test_eval = test.copy()
    test_eval["predicted"] = buffered_preds.values
    buffered_metrics = evaluate_predictions(test_eval, target_col, "predicted")
    results["ma7_buffer20pct"] = {"model": buffered, "metrics": buffered_metrics}

    # Summary
    logger.info("\n=== Model Comparison ===")
    for name, res in results.items():
        m = res["metrics"]["overall"]
        logger.info(f"{name:20s}: MAE={m['mae']:.4f}, RMSE={m['rmse']:.4f}, MAPE={m['mape']:.1f}%")

    return results


def hyperparameter_search(df: pd.DataFrame, target_col: str = "quantity_sold") -> dict:
    """Grid search for XGBoost hyperparameters.

    Args:
        df: Feature DataFrame.
        target_col: Target column.

    Returns:
        Dict with best params and score.
    """
    train, val, _ = time_series_split(df)

    param_grid = {
        "n_estimators": [300, 500],
        "max_depth": [4, 6, 8],
        "learning_rate": [0.03, 0.05, 0.1],
    }

    best_mae = float("inf")
    best_params = {}

    for n_est in param_grid["n_estimators"]:
        for depth in param_grid["max_depth"]:
            for lr in param_grid["learning_rate"]:
                params = {
                    "n_estimators": n_est,
                    "max_depth": depth,
                    "learning_rate": lr,
                }
                model = XGBoostForecaster(**params)
                model.fit(train, target_col)
                preds = model.predict(val)

                val_copy = val.copy()
                val_copy["predicted"] = preds.values
                metrics = evaluate_predictions(val_copy, target_col, "predicted")
                current_mae = metrics["overall"]["mae"]

                if current_mae < best_mae:
                    best_mae = current_mae
                    best_params = params

    logger.info(f"Best params: {best_params}, MAE: {best_mae:.4f}")
    return {"best_params": best_params, "best_mae": best_mae}
