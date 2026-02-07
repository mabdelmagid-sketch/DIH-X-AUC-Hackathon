"""
Model/forecasting endpoints for FlowPOS Forecasting API.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import json

from ..models.forecaster import DemandForecaster
from ..models.trainer import ModelTrainer
from ..llm.tools import ToolExecutor
from .dependencies import get_forecaster, get_tool_executor
from .schemas import TrainRequest, TrainResponse, ForecastRequest, ForecastResponse

router = APIRouter(tags=["model"])


def _df_to_records(df) -> list:
    return json.loads(df.to_json(orient="records", date_format="iso"))


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
    forecaster: DemandForecaster = Depends(get_forecaster)
):
    """Generate demand forecasts."""
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
