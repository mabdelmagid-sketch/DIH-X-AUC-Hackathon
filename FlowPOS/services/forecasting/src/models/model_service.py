"""
Model Service: loads trained .pkl models and generates predictions.

3-model ensemble: XGBoost Balanced + XGBoost Waste-Optimized + LSTM (RNN).
DeepSeek LLM acts as smart arbitrator via the /prep-recommendation endpoint.
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

# Singleton model caches
_models: dict[str, object] = {}
_rnn_forecaster = None


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


def load_rnn_model():
    """Load the pre-trained LSTM/RNN model (singleton)."""
    global _rnn_forecaster
    if _rnn_forecaster is not None:
        return _rnn_forecaster

    from .rnn_forecaster import RNNForecaster

    rnn = RNNForecaster(sequence_length=60)
    models_dir = settings.trained_models_dir

    # Try rnn_model_1d.pt first (best on 1-day horizon), fallback to rnn_model.pt
    for name in ["rnn_model_1d.pt", "rnn_model.pt"]:
        path = models_dir / name
        if path.exists() and rnn.load(path):
            _rnn_forecaster = rnn
            logger.info(f"LSTM model loaded: {name}")
            return _rnn_forecaster

    logger.warning("No LSTM model found — ensemble will use XGBoost only")
    return None


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
    results = predict_multi_day(daily_sales_df, days_ahead=1, target_date=target_date)
    # Strip the date field to maintain backward compatibility
    for r in results:
        r.pop("date", None)
    return results


def _compute_weekday_factors(daily_sales_df: pd.DataFrame) -> dict[str, dict[int, float]]:
    """Compute per-item weekday demand scaling factors from historical data.

    For each item, calculates what fraction of the overall mean each weekday
    represents. E.g. if Monday averages 80 and the overall mean is 100,
    Monday's factor = 0.80.

    Returns:
        {item_name: {0: mon_factor, 1: tue_factor, ..., 6: sun_factor}}
    """
    df = daily_sales_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["dow"] = df["date"].dt.dayofweek

    item_col = "item_id" if "item_id" in df.columns else "item"
    overall_mean = df.groupby(item_col, observed=True)["quantity_sold"].mean()
    dow_mean = df.groupby([item_col, "dow"], observed=True)["quantity_sold"].mean()

    factors: dict[str, dict[int, float]] = {}
    for item_name in overall_mean.index:
        item_avg = overall_mean[item_name]
        if item_avg <= 0:
            continue
        item_factors = {}
        for dow in range(7):
            if (item_name, dow) in dow_mean.index:
                raw = dow_mean[(item_name, dow)] / item_avg
                # Clamp to [0.5, 1.8] so variation is visible but not extreme
                item_factors[dow] = max(0.5, min(1.8, raw))
            else:
                item_factors[dow] = 0.8  # No data for this weekday → slightly below avg
        factors[str(item_name)] = item_factors

    return factors


def predict_multi_day(
    daily_sales_df: pd.DataFrame,
    days_ahead: int = 7,
    target_date: Optional[date] = None,
) -> list[dict]:
    """Generate per-day ensemble predictions (XGBoost + LSTM majority voting).

    Pipeline:
      1. XGBoost Balanced → base prediction
      2. XGBoost Waste-Optimized → conservative prediction
      3. LSTM (delta-based RNN) → time-series prediction
      4. Ensemble = median of all available models (majority vote)
      5. Weekday scaling applied for day-to-day variation

    DeepSeek LLM acts as a 4th arbitrator via /prep-recommendation,
    seeing all 3 model outputs + weather/holiday context.

    Args:
        daily_sales_df: Raw daily sales with [item, place_id, date, quantity_sold].
        days_ahead: Number of future days to forecast.
        target_date: First date to predict (default: tomorrow).

    Returns:
        List of dicts with per-item, per-day ensemble predictions.
    """
    models = load_trained_models()
    if not models:
        return []

    balanced_model = models.get("balanced")
    waste_model = models.get("waste_optimized")

    if not balanced_model:
        return []

    # Build features from historical data
    feature_df = build_inference_features(daily_sales_df)

    if feature_df.empty:
        return []

    # Get the latest row per item (most recent data point)
    item_col = "item_id" if "item_id" in feature_df.columns else "item"
    group_cols = ["place_id", item_col] if "place_id" in feature_df.columns else [item_col]
    latest = feature_df.sort_values("date").groupby(group_cols, observed=True).last().reset_index()

    if latest.empty:
        return []

    if target_date is None:
        target_date = date.today() + timedelta(days=1)

    # Compute weekday demand patterns from historical data
    weekday_factors = _compute_weekday_factors(daily_sales_df)

    # ── XGBoost predictions ──────────────────────────────────────────
    try:
        balanced_preds = balanced_model.predict(latest, "quantity_sold")
        if waste_model:
            waste_preds = waste_model.predict(latest, "quantity_sold")
        else:
            waste_preds = balanced_preds * 0.85
    except Exception as e:
        logger.error(f"XGBoost prediction failed: {e}", exc_info=True)
        return []

    # ── LSTM predictions ─────────────────────────────────────────────
    rnn = load_rnn_model()
    lstm_preds: dict[str, float] = {}
    if rnn is not None:
        try:
            # LSTM works on item-level aggregated data
            agg_sales = daily_sales_df.groupby(
                ["item", "date"], as_index=False
            )["quantity_sold"].sum()
            lstm_preds = rnn.predict_items(agg_sales)
            logger.info(f"LSTM predicted {len(lstm_preds)} items")
        except Exception as e:
            logger.warning(f"LSTM prediction failed (XGBoost still active): {e}")

    # ── Build per-item metadata + ensemble ───────────────────────────
    items_info = []
    for i, (_, row) in enumerate(latest.iterrows()):
        item_name = str(row.get("item", row.get("item_id", f"item_{i}")))
        avg = float(row.get("quantity_sold", 0))
        std = float(row.get("rolling_std_14d", row.get("rolling_std_7d", 0))) or 0
        cv = std / avg if avg > 0 else 0

        item_lower = item_name.lower()
        perishable_kw = ["salad", "juice", "shake", "fresh", "smoothie",
                         "sandwich", "bowl", "wrap", "sushi", "bread"]

        if cv > 1.0:
            risk = "high"
        elif cv > 0.5:
            risk = "medium"
        else:
            risk = "low"

        base_balanced = float(balanced_preds.iloc[i]) if i < len(balanced_preds) else avg
        base_waste = float(waste_preds.iloc[i]) if i < len(waste_preds) else avg * 0.85
        base_lstm = lstm_preds.get(item_name)  # None if LSTM didn't cover this item

        # Ensemble: median of available models (majority vote)
        votes = [base_balanced, base_waste]
        if base_lstm is not None:
            votes.append(base_lstm)
        ensemble_pred = float(np.median(votes))

        # Determine model source label
        if base_lstm is not None:
            model_src = "ensemble_3model"
        else:
            model_src = "ensemble_2model"

        items_info.append({
            "item": item_name,
            "avg_daily_demand": round(avg, 1),
            "demand_cv": round(cv, 3),
            "demand_risk": risk,
            "is_perishable": any(kw in item_lower for kw in perishable_kw),
            "safety_stock_units": round(1.65 * std, 1),
            "_base_ensemble": ensemble_pred,
            "_base_balanced": base_balanced,
            "_base_waste": base_waste,
            "_base_lstm": base_lstm,
            "_model_source": model_src,
        })

    # ── Generate per-day results with weekday scaling ────────────────
    results = []
    for d in range(days_ahead):
        forecast_date = target_date + timedelta(days=d)
        dow = forecast_date.weekday()

        for info in items_info:
            factor = weekday_factors.get(info["item"], {}).get(dow, 1.0)
            ensemble_pred = max(0.0, info["_base_ensemble"] * factor)
            waste_pred = max(0.0, info["_base_waste"] * factor)
            balanced_pred = max(0.0, info["_base_balanced"] * factor)

            result = {
                "item": info["item"],
                "date": forecast_date.isoformat(),
                "avg_daily_demand": info["avg_daily_demand"],
                "demand_cv": info["demand_cv"],
                "demand_risk": info["demand_risk"],
                "is_perishable": info["is_perishable"],
                "safety_stock_units": info["safety_stock_units"],
                "forecast_balanced": round(ensemble_pred, 1),
                "forecast_waste_optimized": round(waste_pred, 1),
                "forecast_stockout_optimized": round(balanced_pred * 1.20, 1),
                "model_source": info["_model_source"],
            }

            # Include individual model predictions for DeepSeek arbitration
            if info["_base_lstm"] is not None:
                lstm_scaled = max(0.0, info["_base_lstm"] * factor)
                result["forecast_lstm"] = round(lstm_scaled, 1)
                result["forecast_xgboost"] = round(balanced_pred, 1)

            results.append(result)

    return results
