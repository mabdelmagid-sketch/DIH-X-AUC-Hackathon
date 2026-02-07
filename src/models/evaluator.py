"""Model evaluation: standard metrics + business-impact metrics in DKK."""

import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standard forecasting metrics
# ---------------------------------------------------------------------------

def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Error."""
    return np.abs(actual - predicted).mean()


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Root Mean Squared Error."""
    return np.sqrt(np.mean((actual - predicted) ** 2))


def mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Percentage Error (excludes zero actuals)."""
    mask = actual > 0
    if mask.sum() == 0:
        return 0.0
    return np.abs((actual[mask] - predicted[mask]) / actual[mask]).mean() * 100


def wmape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Weighted Mean Absolute Percentage Error.

    WMAPE = sum(|actual - predicted|) / sum(actual)
    More robust than MAPE for sparse data - weights by volume.
    """
    total_actual = np.sum(actual)
    if total_actual == 0:
        return 0.0
    return np.sum(np.abs(actual - predicted)) / total_actual * 100


# ---------------------------------------------------------------------------
# Business-impact metrics (DKK-denominated)
# ---------------------------------------------------------------------------

def waste_cost_dkk(actual: np.ndarray, predicted: np.ndarray,
                   prices: np.ndarray, waste_fraction: float = 0.3) -> float:
    """Estimated waste cost in DKK from over-forecasting.

    When we prep more than demand, the excess is wasted.
    Cost = sum( (predicted - actual) * price * waste_fraction ) where predicted > actual

    waste_fraction = 0.3 means 30% of ingredient cost is lost (some can be reused next day).

    Args:
        actual: Actual demand quantities.
        predicted: Forecasted/prepped quantities.
        prices: Unit price per item (DKK).
        waste_fraction: Fraction of item cost lost when wasted (0-1).

    Returns:
        Total waste cost in DKK.
    """
    overstock = np.maximum(predicted - actual, 0)
    return (overstock * prices * waste_fraction).sum()


def stockout_cost_dkk(actual: np.ndarray, predicted: np.ndarray,
                      prices: np.ndarray) -> float:
    """Estimated lost revenue in DKK from under-forecasting.

    When demand exceeds prep, we lose the sale.
    Cost = sum( (actual - predicted) * price ) where actual > predicted

    Args:
        actual: Actual demand quantities.
        predicted: Forecasted/prepped quantities.
        prices: Unit selling price per item (DKK).

    Returns:
        Total lost revenue in DKK.
    """
    understock = np.maximum(actual - predicted, 0)
    return (understock * prices).sum()


def total_business_cost_dkk(actual: np.ndarray, predicted: np.ndarray,
                            prices: np.ndarray, waste_fraction: float = 0.3,
                            waste_multiplier: float = 1.0,
                            stockout_multiplier: float = 1.5) -> float:
    """Total business cost combining waste + stockout in DKK.

    Args:
        waste_multiplier: Weight for waste cost (default 1.0).
        stockout_multiplier: Weight for stockout cost (default 1.5).
    """
    wc = waste_cost_dkk(actual, predicted, prices, waste_fraction)
    sc = stockout_cost_dkk(actual, predicted, prices)
    return waste_multiplier * wc + stockout_multiplier * sc


def profit_oriented_cost_dkk(actual: np.ndarray, predicted: np.ndarray,
                              prices: np.ndarray, waste_fraction: float = 0.3) -> float:
    """Profit-oriented cost: penalise stockouts 2x (missed sales hurt revenue).

    Formula: Total = 1.0 x Waste Cost + 2.0 x Stockout Cost
    """
    return total_business_cost_dkk(actual, predicted, prices, waste_fraction,
                                   waste_multiplier=1.0, stockout_multiplier=2.0)


def sustainability_cost_dkk(actual: np.ndarray, predicted: np.ndarray,
                             prices: np.ndarray, waste_fraction: float = 0.3) -> float:
    """Sustainability-oriented cost: penalise waste 2x (food waste hurts planet).

    Formula: Total = 2.0 x Waste Cost + 1.0 x Stockout Cost
    """
    return total_business_cost_dkk(actual, predicted, prices, waste_fraction,
                                   waste_multiplier=2.0, stockout_multiplier=1.0)


def forecast_accuracy(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Forecast accuracy percentage = 1 - WMAPE/100.

    E.g. WMAPE=25% means 75% forecast accuracy.
    """
    return max(0, 100 - wmape(actual, predicted))


# ---------------------------------------------------------------------------
# Comprehensive evaluation
# ---------------------------------------------------------------------------

def evaluate_predictions(df: pd.DataFrame, actual_col: str = "quantity_sold",
                         pred_col: str = "predicted",
                         price_col: str = "item_price",
                         group_cols: list = None) -> dict:
    """Comprehensive evaluation with standard + business metrics.

    Args:
        df: DataFrame with actual, predicted, and price columns.
        actual_col: Actual values column.
        pred_col: Prediction column.
        price_col: Item price column (DKK).
        group_cols: Optional grouping columns.

    Returns:
        Dict with overall and per-group metrics.
    """
    actual = df[actual_col].values.astype(float)
    predicted = df[pred_col].values.astype(float)

    # Use real prices if available, else default 75 DKK (avg restaurant item)
    if price_col in df.columns:
        prices = df[price_col].fillna(75).values.astype(float)
    else:
        prices = np.full(len(df), 75.0)

    overall = {
        # Standard metrics
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "mape": mape(actual, predicted),
        "wmape": wmape(actual, predicted),
        "forecast_accuracy_pct": forecast_accuracy(actual, predicted),
        # Business metrics (DKK)
        "waste_cost_dkk": waste_cost_dkk(actual, predicted, prices),
        "stockout_cost_dkk": stockout_cost_dkk(actual, predicted, prices),
        "total_business_cost_dkk": total_business_cost_dkk(actual, predicted, prices),
        # Volume stats
        "total_actual_demand": actual.sum(),
        "total_predicted": predicted.sum(),
        "overstock_units": np.maximum(predicted - actual, 0).sum(),
        "understock_units": np.maximum(actual - predicted, 0).sum(),
        "overstock_days_pct": (predicted > actual).mean() * 100,
        "understock_days_pct": (predicted < actual).mean() * 100,
        "n_samples": len(df),
    }

    logger.info(f"Overall: MAE={overall['mae']:.2f}, WMAPE={overall['wmape']:.1f}%, "
                f"Accuracy={overall['forecast_accuracy_pct']:.1f}%, "
                f"Waste={overall['waste_cost_dkk']:,.0f} DKK, "
                f"Stockout={overall['stockout_cost_dkk']:,.0f} DKK")

    result = {"overall": overall}

    if group_cols:
        group_metrics = {}
        for name, group in df.groupby(group_cols, observed=True):
            a = group[actual_col].values.astype(float)
            p = group[pred_col].values.astype(float)
            pr = group[price_col].fillna(75).values.astype(float) if price_col in group.columns else np.full(len(group), 75.0)
            group_metrics[name] = {
                "mae": mae(a, p),
                "wmape": wmape(a, p),
                "forecast_accuracy_pct": forecast_accuracy(a, p),
                "waste_cost_dkk": waste_cost_dkk(a, p, pr),
                "stockout_cost_dkk": stockout_cost_dkk(a, p, pr),
                "n_samples": len(group),
            }
        result["by_group"] = group_metrics

    return result


def compare_models_business_impact(df: pd.DataFrame,
                                   model_predictions: dict,
                                   actual_col: str = "quantity_sold",
                                   price_col: str = "item_price") -> pd.DataFrame:
    """Compare multiple models on business impact metrics.

    Args:
        df: DataFrame with actuals and prices.
        model_predictions: Dict of model_name -> prediction Series/array.
        actual_col: Actual values column.
        price_col: Price column.

    Returns:
        Comparison DataFrame with one row per model, sorted by total cost.
    """
    actual = df[actual_col].values.astype(float)
    prices = df[price_col].fillna(75).values.astype(float) if price_col in df.columns else np.full(len(df), 75.0)

    rows = []
    for name, preds in model_predictions.items():
        preds = np.array(preds, dtype=float)
        wc = waste_cost_dkk(actual, preds, prices)
        sc = stockout_cost_dkk(actual, preds, prices)
        tc = wc + 1.5 * sc

        rows.append({
            "model": name,
            "mae": mae(actual, preds),
            "wmape": wmape(actual, preds),
            "forecast_accuracy_pct": forecast_accuracy(actual, preds),
            "waste_cost_dkk": wc,
            "stockout_cost_dkk": sc,
            "total_cost_dkk": tc,
            "overstock_units": np.maximum(preds - actual, 0).sum(),
            "understock_units": np.maximum(actual - preds, 0).sum(),
        })

    result = pd.DataFrame(rows).sort_values("total_cost_dkk")

    # Add savings vs worst model
    worst_cost = result["total_cost_dkk"].max()
    result["savings_vs_worst_dkk"] = worst_cost - result["total_cost_dkk"]
    result["savings_vs_worst_pct"] = result["savings_vs_worst_dkk"] / worst_cost * 100

    return result


def evaluate_by_store(df: pd.DataFrame, actual_col: str = "quantity_sold",
                      pred_col: str = "predicted",
                      price_col: str = "item_price") -> pd.DataFrame:
    """Evaluate predictions broken down by store with business metrics.

    Returns:
        DataFrame with one row per store.
    """
    rows = []
    for pid, group in df.groupby("place_id", observed=True):
        a = group[actual_col].values.astype(float)
        p = group[pred_col].values.astype(float)
        pr = group[price_col].fillna(75).values.astype(float) if price_col in group.columns else np.full(len(group), 75.0)

        rows.append({
            "place_id": pid,
            "store_name": group["store_name"].iloc[0] if "store_name" in group.columns else "",
            "mae": mae(a, p),
            "wmape": wmape(a, p),
            "forecast_accuracy_pct": forecast_accuracy(a, p),
            "waste_cost_dkk": waste_cost_dkk(a, p, pr),
            "stockout_cost_dkk": stockout_cost_dkk(a, p, pr),
            "total_cost_dkk": total_business_cost_dkk(a, p, pr),
            "total_demand": a.sum(),
            "n_samples": len(group),
        })
    return pd.DataFrame(rows).sort_values("total_cost_dkk", ascending=False)


def evaluate_by_day_of_week(df: pd.DataFrame, actual_col: str = "quantity_sold",
                            pred_col: str = "predicted",
                            price_col: str = "item_price") -> pd.DataFrame:
    """Evaluate predictions broken down by day of week."""
    day_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
                 4: "Friday", 5: "Saturday", 6: "Sunday"}
    rows = []
    for dow, group in df.groupby("day_of_week", observed=True):
        a = group[actual_col].values.astype(float)
        p = group[pred_col].values.astype(float)
        pr = group[price_col].fillna(75).values.astype(float) if price_col in group.columns else np.full(len(group), 75.0)

        rows.append({
            "day_of_week": dow,
            "day_name": day_names.get(dow, str(dow)),
            "mae": mae(a, p),
            "wmape": wmape(a, p),
            "forecast_accuracy_pct": forecast_accuracy(a, p),
            "waste_cost_dkk": waste_cost_dkk(a, p, pr),
            "stockout_cost_dkk": stockout_cost_dkk(a, p, pr),
        })
    return pd.DataFrame(rows).sort_values("day_of_week")


def generate_business_summary(df: pd.DataFrame, model_predictions: dict,
                              actual_col: str = "quantity_sold",
                              price_col: str = "item_price",
                              test_days: int = 90) -> dict:
    """Generate a business-focused summary for hackathon presentation.

    Args:
        df: Test DataFrame.
        model_predictions: Dict of model_name -> predictions.
        actual_col: Actual demand column.
        price_col: Price column.
        test_days: Number of test days (for annualization).

    Returns:
        Dict with presentation-ready business metrics.
    """
    comparison = compare_models_business_impact(df, model_predictions, actual_col, price_col)

    best_model = comparison.iloc[0]
    worst_model = comparison.iloc[-1]

    # Annualize from test period
    annual_factor = 365 / max(test_days, 1)

    summary = {
        "best_model": best_model["model"],
        "best_forecast_accuracy": f"{best_model['forecast_accuracy_pct']:.1f}%",
        "best_wmape": f"{best_model['wmape']:.1f}%",
        # Annualized savings
        "annual_waste_reduction_dkk": (worst_model["waste_cost_dkk"] - best_model["waste_cost_dkk"]) * annual_factor,
        "annual_stockout_reduction_dkk": (worst_model["stockout_cost_dkk"] - best_model["stockout_cost_dkk"]) * annual_factor,
        "annual_total_savings_dkk": (worst_model["total_cost_dkk"] - best_model["total_cost_dkk"]) * annual_factor,
        # Percentage improvements
        "waste_reduction_pct": (1 - best_model["waste_cost_dkk"] / max(worst_model["waste_cost_dkk"], 1)) * 100,
        "stockout_reduction_pct": (1 - best_model["stockout_cost_dkk"] / max(worst_model["stockout_cost_dkk"], 1)) * 100,
        # Per-store averages
        "model_comparison": comparison,
    }

    return summary
