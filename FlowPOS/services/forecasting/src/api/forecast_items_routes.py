"""
forecast_items_routes.py -- Loving Loyalty AI Suite, Pillar 1: Sales Forecasting

POST /ai/forecast/items

Generates per-item daily demand forecasts for a restaurant (place) over a
requested date range.  Uses the AdaptiveBlendModel (RF global + ExtraTrees
per-store) trained by AdaptiveBlendTrainer, loaded via ForecastPredictor.

Request body:
    placeId     int               Restaurant identifier
    startDate   str  YYYY-MM-DD   First forecast date (inclusive)
    endDate     str  YYYY-MM-DD   Last forecast date (inclusive)
    granularity str               "daily" only (future: "weekly")
    variant     str  optional     "balanced" | "waste_optimized" |
                                  "stockout_optimized"  (default: "balanced")
    topN        int  optional     Limit to top N items by predicted volume

Response body:
    placeId       int
    startDate     str
    endDate       str
    granularity   str
    variant       str
    generatedAt   str  ISO-8601
    itemForecasts list[ItemForecast]

ItemForecast:
    itemId      int | str
    itemTitle   str
    predictions list[DailyPrediction]

DailyPrediction:
    date            str YYYY-MM-DD
    predictedUnits  int   (buffer-adjusted, rounded)
    lowerBound      int
    upperBound      int
    confidence      float  (0–1)
    forecastDrivers list[str]
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator

from .response_wrapper import wrap_response, wrap_error

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-forecast"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ForecastItemsRequest(BaseModel):
    placeId: int = Field(..., description="Restaurant / place identifier")
    startDate: str = Field(..., description="First forecast date (YYYY-MM-DD, inclusive)")
    endDate: str = Field(..., description="Last forecast date (YYYY-MM-DD, inclusive)")
    granularity: str = Field("daily", description="Forecast granularity (only 'daily' supported)")
    variant: str = Field(
        "balanced",
        description="Output variant: 'balanced' | 'waste_optimized' | 'stockout_optimized'",
    )
    topN: Optional[int] = Field(None, description="Limit to top N items by predicted volume")

    @validator("startDate", "endDate")
    def _validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date must be YYYY-MM-DD, got: {v!r}")
        return v

    @validator("granularity")
    def _validate_granularity(cls, v: str) -> str:
        if v not in ("daily",):
            raise ValueError(f"Unsupported granularity '{v}'. Only 'daily' is supported.")
        return v

    @validator("variant")
    def _validate_variant(cls, v: str) -> str:
        allowed = {"balanced", "waste_optimized", "stockout_optimized"}
        if v not in allowed:
            raise ValueError(f"variant must be one of {allowed}, got: {v!r}")
        return v


class DailyPrediction(BaseModel):
    date: str
    predictedUnits: int
    lowerBound: int
    upperBound: int
    confidence: float
    forecastDrivers: list[str]


class ItemForecast(BaseModel):
    itemId: object  # int or str depending on the dataset
    itemTitle: str
    predictions: list[DailyPrediction]


class ForecastItemsResponse(BaseModel):
    placeId: int
    startDate: str
    endDate: str
    granularity: str
    variant: str
    generatedAt: str
    itemForecasts: list[ItemForecast]


# ---------------------------------------------------------------------------
# Lazy-loaded predictor (singleton per variant)
# ---------------------------------------------------------------------------

_predictor_cache: dict[str, object] = {}


def _get_predictor(variant: str):
    """Return a loaded ForecastPredictor for the given variant (cached)."""
    if variant in _predictor_cache:
        return _predictor_cache[variant]

    from ..forecast.predictor import ForecastPredictor

    predictor = ForecastPredictor(variant=variant)
    try:
        predictor.load()
        _predictor_cache[variant] = predictor
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Forecast model for variant '{variant}' is not available. "
                "Please retrain the model first via POST /api/train or the CLI."
            ),
        ) from exc
    return predictor


def _get_data_loader():
    """Return a DataLoader instance (uses CSV demo by default)."""
    from ..forecast.data_loader import DataLoader
    return DataLoader()


# ---------------------------------------------------------------------------
# Background sync helper
# ---------------------------------------------------------------------------

def _run_forecast_sync(
    variant: str,
    place_id: int,
    start_date: date,
    end_date: date,
    top_n: Optional[int],
) -> list[dict]:
    """CPU-bound forecast work, runs in a thread pool."""
    predictor = _get_predictor(variant)
    loader = _get_data_loader()

    daily_df = loader.load_daily_demand(top_n_items=top_n or 30)

    raw_results = predictor.predict(
        daily_df=daily_df,
        start_date=start_date,
        end_date=end_date,
        place_id=place_id,
    )
    return raw_results


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/ai/forecast/items")
async def forecast_items(request: ForecastItemsRequest) -> dict:
    """Generate daily per-item demand forecasts for a restaurant.

    Uses the AdaptiveBlendModel (RF(300) global + ExtraTrees(800) per-store,
    75/25 adaptive blend, newsvendor safety buffer) trained by the autoresearch
    pipeline.

    The ``variant`` field selects the output buffer scaling:
      - balanced            : newsvendor buffer fully applied (default)
      - waste_optimized     : buffer x 0.90 — reduces overstocking
      - stockout_optimized  : buffer x 1.06 — reduces stockouts

    Confidence scores follow SRS Table 25:
      90+ days history -> 0.75–0.95
      30–89 days       -> 0.50–0.74
      <30 days         -> 0.20–0.49
      0 orders         -> 0.10–0.25
    """
    try:
        start_date = date.fromisoformat(request.startDate)
        end_date = date.fromisoformat(request.endDate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if end_date < start_date:
        raise wrap_error(
            422,
            "INVALID_DATE_RANGE",
            f"endDate ({request.endDate}) must be >= startDate ({request.startDate})",
        )

    max_days = 90
    delta = (end_date - start_date).days + 1
    if delta > max_days:
        raise wrap_error(
            422,
            "INVALID_DATE_RANGE",
            f"Requested {delta} days exceeds the maximum of {max_days}.",
        )

    try:
        raw_results: list[dict] = await asyncio.to_thread(
            _run_forecast_sync,
            request.variant,
            request.placeId,
            start_date,
            end_date,
            request.topN,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Forecast failed for placeId=%s: %s", request.placeId, exc, exc_info=True)
        raise wrap_error(500, "FORECAST_FAILED", str(exc)) from exc

    # Group predictions by item
    from collections import defaultdict
    item_map: dict[object, dict] = defaultdict(lambda: {"item_title": "", "predictions": []})

    for r in raw_results:
        item_id = r["item_id"]
        item_map[item_id]["item_title"] = r.get("item_title", str(item_id))
        item_map[item_id]["predictions"].append(
            DailyPrediction(
                date=r["date"],
                predictedUnits=int(r["predicted_units"]),
                lowerBound=int(r.get("lower_bound", 0)),
                upperBound=int(r.get("upper_bound", 0)),
                confidence=float(r.get("confidence", 0.5)),
                forecastDrivers=r.get("forecast_drivers", ["Historical demand pattern"]),
            )
        )

    # Apply topN filter on item total predicted units
    if request.topN is not None:
        item_totals = {
            iid: sum(p.predictedUnits for p in info["predictions"])
            for iid, info in item_map.items()
        }
        top_ids = set(
            sorted(item_totals, key=item_totals.get, reverse=True)[: request.topN]
        )
        item_map = {k: v for k, v in item_map.items() if k in top_ids}

    item_forecasts = [
        ItemForecast(
            itemId=item_id,
            itemTitle=info["item_title"],
            predictions=sorted(info["predictions"], key=lambda p: p.date),
        )
        for item_id, info in item_map.items()
    ]

    # Sort items by total predicted volume descending for easy scanning
    item_forecasts.sort(
        key=lambda it: sum(p.predictedUnits for p in it.predictions),
        reverse=True,
    )

    return wrap_response(ForecastItemsResponse(
        placeId=request.placeId,
        startDate=request.startDate,
        endDate=request.endDate,
        granularity=request.granularity,
        variant=request.variant,
        generatedAt=datetime.utcnow().isoformat() + "Z",
        itemForecasts=item_forecasts,
    ))
