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
from ..models.model_service import load_trained_models, predict_dual
from ..llm.tools import ToolExecutor
from ..config import settings
from .dependencies import get_forecaster, get_tool_executor, get_data_loader
from .schemas import TrainRequest, TrainResponse, ForecastRequest, ForecastResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["model"])


def _df_to_records(df) -> list:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _get_sales_for_forecast(loader: DataLoader, item_filter: str | None = None) -> pd.DataFrame:
    """Pull daily sales data from loaded DuckDB tables for the trained models."""
    loader.load_all_tables()

    params = []
    item_clause = ""
    if item_filter:
        item_clause = f"AND LOWER(oi.title) LIKE LOWER('%' || ${len(params) + 1} || '%')"
        params.append(item_filter)

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
            daily_sales = _get_sales_for_forecast(loader, request.item_filter)
            if daily_sales.empty:
                raise HTTPException(status_code=404, detail="No sales data found for the given filter.")

            dual_results = predict_dual(daily_sales)

            if dual_results:
                # Convert dual results to the forecast format the frontend expects
                forecasts = []
                target_date = date.today() + timedelta(days=1)
                for r in dual_results:
                    for d in range(request.days_ahead):
                        forecast_date = target_date + timedelta(days=d)
                        forecasts.append({
                            "item_title": r["item"],
                            "date": forecast_date.isoformat(),
                            "predicted_quantity": r["forecast_balanced"],
                            "lower_bound": r["forecast_waste_optimized"],
                            "upper_bound": r["forecast_stockout_optimized"],
                            "demand_risk": r["demand_risk"],
                            "is_perishable": r["is_perishable"],
                            "safety_stock": r["safety_stock_units"],
                            "model_source": r["model_source"],
                        })

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
