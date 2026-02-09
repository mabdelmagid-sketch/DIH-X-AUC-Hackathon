"""
Model/forecasting endpoints for FlowPOS Forecasting API.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, date, timedelta
import json
import logging

import pandas as pd

from ..data.loader import DataLoader
from ..models.forecaster import DemandForecaster
from ..models.trainer import ModelTrainer
from ..models.model_service import load_trained_models, predict_dual, predict_multi_day
from ..llm.tools import ToolExecutor
from ..config import settings
from .dependencies import get_forecaster, get_tool_executor, get_data_loader
from .schemas import TrainRequest, TrainResponse, ForecastRequest, ForecastResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["model"])


def _df_to_records(df) -> list:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _get_sales_for_forecast(loader: DataLoader, item_filter: str | None = None, top_n: int | None = None) -> pd.DataFrame:
    """Pull daily sales data from loaded DuckDB tables for the trained models."""
    loader.load_all_tables()

    params = []
    item_clause = ""
    if item_filter:
        item_clause = f"AND LOWER(oi.title) LIKE LOWER('%' || ${len(params) + 1} || '%')"
        params.append(item_filter)

    # If top_n specified, pre-filter to only top-selling items for performance
    top_items_clause = ""
    if top_n and top_n > 0 and not item_filter:
        top_items_clause = f"""AND oi.title IN (
            SELECT title FROM (
                SELECT oi2.title, SUM(oi2.quantity) AS total_qty
                FROM fct_order_items oi2
                GROUP BY oi2.title
                ORDER BY total_qty DESC
                LIMIT {int(top_n)}
            )
        )"""

    sql = f"""
    SELECT
        oi.title AS item,
        o.place_id AS place_id,
        CAST(to_timestamp(o.created)::DATE AS DATE) AS date,
        SUM(oi.quantity) AS quantity_sold
    FROM fct_orders o
    JOIN fct_order_items oi ON o.id = oi.order_id
    WHERE o.created IS NOT NULL
      {item_clause}
      {top_items_clause}
    GROUP BY oi.title, o.place_id, CAST(to_timestamp(o.created)::DATE AS DATE)
    ORDER BY oi.title, CAST(to_timestamp(o.created)::DATE AS DATE)
    """

    return loader.query(sql, params if params else None)


@router.post("/train", response_model=TrainResponse)
async def train_model(
    request: TrainRequest,
    forecaster: DemandForecaster = Depends(get_forecaster),
    tool_executor: ToolExecutor = Depends(get_tool_executor)
):
    """Train or retrain the forecasting model."""
    if not request.force_retrain and forecaster.model is not None:
        return TrainResponse(
            status="skipped",
            metrics=forecaster.metrics,
            message="Model already trained. Use force_retrain=true to retrain."
        )

    try:
        trainer = ModelTrainer()
        results = trainer.run_training_pipeline(verbose=True)

        # Reload model into the existing singleton
        forecaster.load()

        # Update tool executor reference
        if tool_executor:
            tool_executor.forecaster = forecaster

        return TrainResponse(
            status=results.get("status", "unknown"),
            metrics=results.get("metrics"),
            message="Model trained successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/forecast", response_model=ForecastResponse)
async def generate_forecast(
    request: ForecastRequest,
    forecaster: DemandForecaster = Depends(get_forecaster),
    loader: DataLoader = Depends(get_data_loader)
):
    """Generate demand forecasts using pre-trained models.

    Uses the trained HybridForecaster/WasteOptimizedForecaster .pkl models.
    Falls back to the DemandForecaster if trained models aren't available.
    """
    # Try trained .pkl models first
    trained = load_trained_models()
    if trained:
        try:
            daily_sales = _get_sales_for_forecast(loader, request.item_filter, request.top_n)
            if daily_sales.empty:
                raise HTTPException(status_code=404, detail="No sales data found for the given filter.")

            # Use multi-day prediction so each future day gets distinct
            # time features (day_of_week, is_weekend, etc.) → different predictions
            multi_results = predict_multi_day(daily_sales, days_ahead=request.days_ahead)

            if multi_results:
                forecasts = []
                for r in multi_results:
                    entry = {
                        "item_title": r["item"],
                        "date": r["date"],
                        "predicted_quantity": r["forecast_balanced"],
                        "lower_bound": r["forecast_waste_optimized"],
                        "upper_bound": r["forecast_stockout_optimized"],
                        "demand_risk": r["demand_risk"],
                        "is_perishable": r["is_perishable"],
                        "safety_stock": r["safety_stock_units"],
                        "model_source": r["model_source"],
                    }
                    # Include individual model predictions when available
                    if "forecast_lstm" in r:
                        entry["forecast_lstm"] = r["forecast_lstm"]
                    if "forecast_xgboost" in r:
                        entry["forecast_xgboost"] = r["forecast_xgboost"]
                    forecasts.append(entry)

                # Apply top_n filter if specified
                if request.top_n and request.top_n > 0:
                    item_totals = {}
                    for f in forecasts:
                        item = f["item_title"]
                        item_totals[item] = item_totals.get(item, 0) + abs(f["predicted_quantity"])
                    top_items = set(sorted(item_totals, key=item_totals.get, reverse=True)[:request.top_n])
                    forecasts = [f for f in forecasts if f["item_title"] in top_items]

                return ForecastResponse(
                    forecasts=forecasts,
                    generated_at=datetime.now().isoformat()
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Trained model forecast failed, trying fallback: {e}")

    # Fallback: old DemandForecaster (requires /train)
    if forecaster.model is None:
        raise HTTPException(status_code=400, detail="Model not trained. Call /train first.")

    try:
        trainer = ModelTrainer()
        forecasts = trainer.generate_forecasts(
            days_ahead=request.days_ahead,
            item_filter=request.item_filter
        )

        return ForecastResponse(
            forecasts=_df_to_records(forecasts),
            generated_at=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model/features")
async def get_feature_importance(
    top_n: int = 20,
    forecaster: DemandForecaster = Depends(get_forecaster)
):
    """Get feature importance from trained model."""
    if forecaster.model is None:
        raise HTTPException(status_code=400, detail="Model not trained")

    importance = forecaster.get_feature_importance(top_n)
    return {
        "features": _df_to_records(importance),
        "model_metrics": forecaster.metrics
    }
