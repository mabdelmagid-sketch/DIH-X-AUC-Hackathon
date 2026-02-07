"""Inventory optimization: safety stock, reorder points, prep recommendations."""

import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def calculate_safety_stock(forecast_std: float, lead_time_days: int = 1,
                           z_score: float = 1.65) -> float:
    """Calculate safety stock for a given service level.

    safety_stock = z_score * forecast_std * sqrt(lead_time)

    Args:
        forecast_std: Standard deviation of forecast errors or demand.
        lead_time_days: Lead time in days (default 1 for daily prep).
        z_score: Z-score for service level (1.65 = 95%).

    Returns:
        Safety stock quantity.
    """
    return z_score * forecast_std * np.sqrt(lead_time_days)


def calculate_reorder_point(avg_daily_demand: float, lead_time_days: int = 1,
                            safety_stock: float = 0) -> float:
    """Calculate reorder point.

    reorder_point = avg_daily_demand * lead_time + safety_stock

    Args:
        avg_daily_demand: Average daily demand.
        lead_time_days: Lead time in days.
        safety_stock: Calculated safety stock.

    Returns:
        Reorder point quantity.
    """
    return avg_daily_demand * lead_time_days + safety_stock


def generate_prep_recommendations(df: pd.DataFrame,
                                  forecast_col: str = "predicted",
                                  actual_col: str = "quantity_sold",
                                  z_score: float = 1.65,
                                  lead_time_days: int = 1) -> pd.DataFrame:
    """Generate daily prep quantity recommendations per (store, item).

    Args:
        df: DataFrame with forecast predictions and historical data.
        forecast_col: Column with forecast values.
        actual_col: Column with actual demand.
        z_score: Z-score for safety stock (1.65 = 95% service level).
        lead_time_days: Lead time in days.

    Returns:
        DataFrame with recommended prep quantities and alerts.
    """
    recommendations = []

    for (pid, iid), group in df.groupby(["place_id", "item_id"], observed=True):
        group = group.sort_values("date")

        # Calculate forecast error std from recent history
        if actual_col in group.columns and forecast_col in group.columns:
            errors = group[actual_col] - group[forecast_col]
            forecast_std = errors.std() if len(errors) > 7 else group[actual_col].std()
        else:
            forecast_std = group[actual_col].std() if actual_col in group.columns else 0

        forecast_std = max(forecast_std, 0.1)  # Minimum std

        avg_demand = group[actual_col].mean() if actual_col in group.columns else 0
        safety = calculate_safety_stock(forecast_std, lead_time_days, z_score)
        reorder = calculate_reorder_point(avg_demand, lead_time_days, safety)

        # Last row forecast for next-day recommendation
        last_row = group.iloc[-1]
        forecast_demand = last_row.get(forecast_col, avg_demand)
        recommended_qty = max(0, np.ceil(forecast_demand + safety))

        # Determine alert level
        cv = forecast_std / max(avg_demand, 0.1)  # Coefficient of variation
        if cv > 0.8:
            alert = "red"  # High variability = stockout risk
        elif cv > 0.4:
            alert = "yellow"  # Moderate variability
        else:
            alert = "green"  # Low variability = adequate

        recommendations.append({
            "place_id": pid,
            "item_id": iid,
            "item_name": last_row.get("item_name", ""),
            "store_name": last_row.get("store_name", ""),
            "forecast_demand": round(forecast_demand, 1),
            "safety_stock": round(safety, 1),
            "recommended_prep_qty": int(recommended_qty),
            "reorder_point": round(reorder, 1),
            "avg_daily_demand": round(avg_demand, 1),
            "demand_std": round(forecast_std, 1),
            "alert_level": alert,
            "date": last_row.get("date", ""),
        })

    result = pd.DataFrame(recommendations)
    logger.info(f"Generated {len(result)} prep recommendations")
    return result


def generate_daily_schedule(df: pd.DataFrame,
                            forecast_col: str = "predicted",
                            z_score: float = 1.65) -> pd.DataFrame:
    """Generate a full daily prep schedule from forecasts.

    For each date x store x item, outputs the recommended prep quantity.

    Args:
        df: Feature DataFrame with predictions.
        forecast_col: Forecast column name.
        z_score: Z-score for safety stock.

    Returns:
        DataFrame with date, store, item, recommended quantity.
    """
    records = []

    for (pid, iid), group in df.groupby(["place_id", "item_id"], observed=True):
        group = group.sort_values("date")
        demand_std = group["quantity_sold"].rolling(14, min_periods=3).std().fillna(
            group["quantity_sold"].std()
        )

        for idx, row in group.iterrows():
            forecast = row.get(forecast_col, 0)
            std = demand_std.get(idx, 1)
            safety = calculate_safety_stock(max(std, 0.1), z_score=z_score)
            qty = max(0, np.ceil(forecast + safety))

            records.append({
                "date": row["date"],
                "place_id": pid,
                "item_id": iid,
                "item_name": row.get("item_name", ""),
                "store_name": row.get("store_name", ""),
                "forecast": round(forecast, 1),
                "safety_stock": round(safety, 1),
                "recommended_qty": int(qty),
            })

    return pd.DataFrame(records)
