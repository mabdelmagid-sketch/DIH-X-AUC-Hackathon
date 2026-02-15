"""
Pydantic request/response models for FlowPOS Forecasting API.
"""
from pydantic import BaseModel
from typing import Optional


# === Chat ===

class ChatRequest(BaseModel):
    message: str
    include_context: bool = True


class ChatResponse(BaseModel):
    response: str
    context_used: bool = False


# === Forecasting ===

class ForecastRequest(BaseModel):
    days_ahead: int = 7
    item_filter: Optional[str] = None
    top_n: Optional[int] = None  # Limit to top N items by predicted volume
    source: Optional[str] = None  # "supabase" to use real POS data
    place_id: Optional[int] = None  # Filter to a specific restaurant/place


class ForecastResponse(BaseModel):
    forecasts: list[dict]
    generated_at: str


# === Training ===

class TrainRequest(BaseModel):
    force_retrain: bool = False


class TrainResponse(BaseModel):
    status: str
    metrics: Optional[dict] = None
    message: str


# === Insights ===

class InsightRequest(BaseModel):
    query: Optional[str] = None
    store_context: Optional[str] = None  # Override context with store-specific info


class InsightResponse(BaseModel):
    insight: str
    generated_at: str


# === Data ===

class InventoryStatusResponse(BaseModel):
    items: list[dict]
    total_items: int
    low_stock_count: int
    expiring_soon_count: int


class DailySalesResponse(BaseModel):
    sales: list[dict]
    total_records: int
    date_range: dict


# === Simulator ===

class SimulateRequest(BaseModel):
    scenario: str


# === Prep Recommendation ===

class PrepRecommendationRequest(BaseModel):
    item_name: Optional[str] = None
    place_id: Optional[int] = None
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today
