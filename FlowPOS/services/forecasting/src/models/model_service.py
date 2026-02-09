"""
Model Service: loads trained .pkl models and generates predictions.

Bridges the trained HybridForecaster/WasteOptimizedForecaster from
inventory-forecasting with the FlowPOS forecasting API.
"""
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

from ..config import settings

logger = logging.getLogger(__name__)

# Singleton model cache
_models: dict[str, object] = {}


def load_trained_models() -> dict:
    """Load pre-trained .pkl models from disk.

    Returns dict with 'balanced' and 'waste_optimized' keys,
    or empty dict if files not found.
    """
    global _models
    if _models:
        return _models

    models_dir = settings.trained_models_dir
    balanced_path = models_dir / "balanced_model.pkl"
    waste_opt_path = models_dir / "waste_optimized_model.pkl"

    if balanced_path.exists():
        try:
            _models["balanced"] = joblib.load(balanced_path)
            logger.info(f"Loaded balanced model from {balanced_path}")
        except Exception as e:
            logger.error(f"Failed to load balanced model: {e}")

    if waste_opt_path.exists():
        try:
            _models["waste_optimized"] = joblib.load(waste_opt_path)
            logger.info(f"Loaded waste-optimized model from {waste_opt_path}")
        except Exception as e:
            logger.error(f"Failed to load waste-optimized model: {e}")

    return _models


def build_inference_features(daily_sales_df: pd.DataFrame) -> pd.DataFrame:
    """Build feature DataFrame from daily sales data for model inference.

    Args:
        daily_sales_df: DataFrame with columns [item, place_id, date, quantity_sold].
                        Must be sorted by (item, date).

    Returns:
        Feature DataFrame ready for model prediction.
    """
    df = daily_sales_df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # --- Time features ---
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_of_month"] = df["date"].dt.day
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["day_of_year"] = df["date"].dt.dayofyear
    df["year"] = df["date"].dt.year
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["is_friday"] = (df["day_of_week"] == 4).astype(int)
    df["is_monday"] = (df["day_of_week"] == 0).astype(int)

    # Seasons: 0=Winter, 1=Spring, 2=Summer, 3=Fall
    df["season"] = df["month"].map(
        {12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3}
    )

    # Cyclical encodings
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # --- Lag features (per item) ---
    # Determine grouping columns based on what's available
    item_col = "item_id" if "item_id" in df.columns else "item"
    group = ["place_id", item_col] if "place_id" in df.columns else [item_col]
    target = "quantity_sold"

    for lag in [1, 7, 14, 28]:
        df[f"demand_lag_{lag}d"] = df.groupby(group, observed=True)[target].shift(lag)

    # Same weekday last week
    df["demand_same_weekday_last_week"] = df.groupby(group, observed=True)[target].shift(7)

    # --- Rolling features ---
    for window in [7, 14, 30]:
        shifted = df.groupby(group, observed=True)[target].shift(1)
        col_name = f"rolling_mean_{window}d" if window != 30 else "rolling_mean_30d"
        df[col_name] = shifted.groupby(
            [df[g] for g in group], observed=True
        ).transform(lambda x: x.rolling(window, min_periods=1).mean())

    for window in [7, 14]:
        shifted = df.groupby(group, observed=True)[target].shift(1)
        df[f"rolling_std_{window}d"] = shifted.groupby(
            [df[g] for g in group], observed=True
        ).transform(lambda x: x.rolling(window, min_periods=2).std())

    # 4-week same-weekday average
    df["demand_same_weekday_avg_4weeks"] = df.groupby(group, observed=True)[target].transform(
        lambda x: x.shift(7).rolling(4, min_periods=1).mean()
    )

    # Expanding mean
    df["expanding_mean"] = df.groupby(group, observed=True)[target].expanding().mean().reset_index(level=list(range(len(group))), drop=True)

    # --- Stub features for columns the model might expect ---
    # Weather (will be 0 if not available — model handles via fillna)
    for col in ["temperature_max", "temperature_min", "precipitation_mm", "is_rainy"]:
        if col not in df.columns:
            df[col] = 0

    # Holiday
    for col in ["is_holiday", "is_day_before_holiday", "is_day_after_holiday"]:
        if col not in df.columns:
            df[col] = 0

    # Promotions
    for col in ["is_promotion_active", "discount_percentage", "campaign_count"]:
        if col not in df.columns:
            df[col] = 0

    # Store open
    if "is_open" not in df.columns:
        df["is_open"] = 1

    # Encoded categoricals (will be re-encoded by the model)
    if "place_id_encoded" not in df.columns:
        df["place_id_encoded"] = 0
    if "item_id_encoded" not in df.columns:
        df["item_id_encoded"] = 0

    return df


def predict_dual(
    daily_sales_df: pd.DataFrame,
    target_date: Optional[date] = None,
) -> list[dict]:
    """Generate dual predictions (balanced + waste-optimized) using trained models.

    Args:
        daily_sales_df: Raw daily sales with [item, place_id, date, quantity_sold].
        target_date: Date to predict for (default: tomorrow).

    Returns:
        List of dicts with per-item dual predictions, or empty list if models unavailable.
    """
    models = load_trained_models()
    if not models:
        return []

    balanced_model = models.get("balanced")
    waste_model = models.get("waste_optimized")

    if not balanced_model:
        return []

    # Build features
    feature_df = build_inference_features(daily_sales_df)

    if feature_df.empty:
        return []

    # Get the latest row per item (most recent data point)
    # This is what we use for "predict next day"
    item_col = "item_id" if "item_id" in feature_df.columns else "item"
    group_cols = ["place_id", item_col] if "place_id" in feature_df.columns else [item_col]
    latest = feature_df.sort_values("date").groupby(group_cols, observed=True).last().reset_index()

    if latest.empty:
        return []

    results = []
    try:
        # Balanced (stockout-optimized) prediction
        balanced_preds = balanced_model.predict(latest, "quantity_sold")

        # Waste-optimized prediction
        if waste_model:
            waste_preds = waste_model.predict(latest, "quantity_sold")
        else:
            waste_preds = balanced_preds * 0.85

        for i, (_, row) in enumerate(latest.iterrows()):
            item_name = row.get("item", row.get("item_id", f"item_{i}"))
            avg = float(row.get("quantity_sold", 0))
            std = float(row.get("rolling_std_14d", row.get("rolling_std_7d", 0))) or 0
            cv = std / avg if avg > 0 else 0

            balanced_pred = float(balanced_preds.iloc[i]) if i < len(balanced_preds) else avg
            waste_pred = float(waste_preds.iloc[i]) if i < len(waste_preds) else avg * 0.85

            # Safety stock at 95% service level
            safety_stock = round(1.65 * std, 1)

            # Perishability heuristic
            item_lower = str(item_name).lower()
            perishable_kw = ["salad", "juice", "shake", "fresh", "smoothie",
                             "sandwich", "bowl", "wrap", "sushi", "bread"]
            is_perishable = any(kw in item_lower for kw in perishable_kw)

            # Risk classification
            if cv > 1.0:
                risk = "high"
            elif cv > 0.5:
                risk = "medium"
            else:
                risk = "low"

            results.append({
                "item": str(item_name),
                "avg_daily_demand": round(avg, 1),
                "demand_cv": round(cv, 3),
                "demand_risk": risk,
                "is_perishable": is_perishable,
                "forecast_waste_optimized": round(waste_pred, 1),
                "forecast_stockout_optimized": round(balanced_pred * 1.20, 1),
                "forecast_balanced": round(balanced_pred, 1),
                "safety_stock_units": safety_stock,
                "model_source": "trained_hybrid",
            })

    except Exception as e:
        logger.error(f"Model prediction failed: {e}", exc_info=True)
        return []

    return results
