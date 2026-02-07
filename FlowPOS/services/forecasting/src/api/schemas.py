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
