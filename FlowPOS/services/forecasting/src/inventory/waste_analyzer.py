"""Waste analysis: estimate overstocking and cost savings."""

import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def estimate_waste(df: pd.DataFrame, forecast_col: str = "predicted",
                   actual_col: str = "quantity_sold",
                   cost_col: str = "item_price") -> pd.DataFrame:
    """Estimate waste from over-forecasting vs actual demand.

    Args:
        df: DataFrame with forecast and actual columns.
        forecast_col: Predicted demand column.
        actual_col: Actual demand column.
        cost_col: Unit cost/price column (for monetary waste).

    Returns:
        DataFrame with waste estimates per (store, item).
    """
    df = df.copy()
    df["overstock"] = np.maximum(df[forecast_col] - df[actual_col], 0)
    df["understock"] = np.maximum(df[actual_col] - df[forecast_col], 0)

    unit_cost = df[cost_col].fillna(50)  # Default 50 DKK

    results = []
    for (pid, iid), group in df.groupby(["place_id", "item_id"], observed=True):
        avg_cost = group[cost_col].mean() if cost_col in group.columns else 50

        total_overstock = group["overstock"].sum()
        total_understock = group["understock"].sum()
        total_demand = group[actual_col].sum()

        results.append({
            "place_id": pid,
            "item_id": iid,
            "item_name": group["item_name"].iloc[0] if "item_name" in group.columns else "",
            "store_name": group["store_name"].iloc[0] if "store_name" in group.columns else "",
            "total_demand": total_demand,
            "total_overstock_units": total_overstock,
            "total_understock_units": total_understock,
            "waste_rate": total_overstock / max(total_demand, 1),
            "stockout_rate": total_understock / max(total_demand, 1),
            "waste_cost_dkk": total_overstock * avg_cost * 0.3,  # 30% of cost wasted
            "lost_revenue_dkk": total_understock * avg_cost,
        })

    result = pd.DataFrame(results)
    logger.info(f"Waste analysis: {len(result)} items analyzed")
    return result


def classify_waste_risk(df: pd.DataFrame, actual_col: str = "quantity_sold") -> pd.DataFrame:
    """Classify items by waste risk based on demand variability.

    High variance items => high waste risk because harder to forecast.

    Args:
        df: Feature DataFrame with demand data.
        actual_col: Actual demand column.

    Returns:
        DataFrame with waste risk classification per item.
    """
    risk = []

    for (pid, iid), group in df.groupby(["place_id", "item_id"], observed=True):
        demand = group[actual_col]
        avg = demand.mean()
        std = demand.std()
        cv = std / max(avg, 0.1)  # Coefficient of variation

        # Classify based on CV
        if cv > 1.0:
            risk_level = "high"
        elif cv > 0.5:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Perishability heuristic based on item type
        item_name = group["item_name"].iloc[0] if "item_name" in group.columns else ""
        item_type = group["item_type"].iloc[0] if "item_type" in group.columns else ""

        perishable_keywords = ["salad", "juice", "shake", "fresh", "smoothie",
                               "sandwich", "bowl", "wrap"]
        is_perishable = any(kw in str(item_name).lower() for kw in perishable_keywords)

        risk.append({
            "place_id": pid,
            "item_id": iid,
            "item_name": item_name,
            "store_name": group["store_name"].iloc[0] if "store_name" in group.columns else "",
            "avg_daily_demand": round(avg, 2),
            "demand_std": round(std, 2),
            "cv": round(cv, 3),
            "waste_risk": risk_level,
            "is_perishable": is_perishable,
        })

    return pd.DataFrame(risk).sort_values("cv", ascending=False)


def calculate_savings_from_forecasting(naive_waste: pd.DataFrame,
                                       ml_waste: pd.DataFrame) -> pd.DataFrame:
    """Calculate cost savings from ML forecasting vs naive approach.

    Args:
        naive_waste: Waste estimates using naive/baseline forecast.
        ml_waste: Waste estimates using ML model forecast.

    Returns:
        DataFrame with savings per item.
    """
    merged = naive_waste.merge(
        ml_waste,
        on=["place_id", "item_id"],
        suffixes=("_naive", "_ml"),
    )

    merged["waste_savings_dkk"] = (
        merged["waste_cost_dkk_naive"] - merged["waste_cost_dkk_ml"]
    )
    merged["revenue_recovery_dkk"] = (
        merged["lost_revenue_dkk_naive"] - merged["lost_revenue_dkk_ml"]
    )
    merged["total_savings_dkk"] = merged["waste_savings_dkk"] + merged["revenue_recovery_dkk"]

    logger.info(f"Total estimated savings: {merged['total_savings_dkk'].sum():,.0f} DKK")
    return merged
