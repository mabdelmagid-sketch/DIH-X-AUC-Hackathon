"""
FastAPI Routes for FlowCast
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import pandas as pd
import json

def _df_to_records(df: pd.DataFrame) -> list:
    """Convert DataFrame to list of dicts, handling NaN -> null safely"""
    return json.loads(df.to_json(orient="records", date_format="iso"))

from ..data.loader import DataLoader
from ..data.features import FeatureEngineer
from ..models.forecaster import DemandForecaster
from ..models.trainer import ModelTrainer
from ..llm.client import LLMClient
from ..llm.tools import ToolExecutor
from ..llm.simulator import ScenarioSimulator

try:
    from ..llm.rag import RAGEngine
except ImportError:
    RAGEngine = None
from ..config import settings

router = APIRouter()

# Global instances (initialized on startup)
data_loader: Optional[DataLoader] = None
forecaster: Optional[DemandForecaster] = None
llm_client: Optional[LLMClient] = None
rag_engine: Optional[RAGEngine] = None
tool_executor: Optional[ToolExecutor] = None
simulator: Optional[ScenarioSimulator] = None


# === Request/Response Models ===

class ChatRequest(BaseModel):
    message: str
    include_context: bool = True

class ChatResponse(BaseModel):
    response: str
    context_used: bool = False

class ForecastRequest(BaseModel):
    days_ahead: int = 7
    item_filter: Optional[str] = None

class ForecastResponse(BaseModel):
    forecasts: list[dict]
    generated_at: str

class TrainRequest(BaseModel):
    force_retrain: bool = False

class TrainResponse(BaseModel):
    status: str
    metrics: Optional[dict] = None
    message: str

class InsightRequest(BaseModel):
    query: Optional[str] = None

class InsightResponse(BaseModel):
    insight: str
    generated_at: str

class InventoryStatusResponse(BaseModel):
    items: list[dict]
    total_items: int
    low_stock_count: int
    expiring_soon_count: int

class DailySalesResponse(BaseModel):
    sales: list[dict]
    total_records: int
    date_range: dict

class SimulateRequest(BaseModel):
    scenario: str


# === Startup/Shutdown ===

@router.on_event("startup")
async def startup():
    """Initialize services on startup"""
    global data_loader, forecaster, llm_client, rag_engine, tool_executor, simulator

    print("Starting FlowCast API...")

    # Initialize data loader
    data_loader = DataLoader()
    print(f"Data path: {settings.data_path}")

    # Initialize LLM client
    try:
        llm_client = LLMClient()
        print("LLM client initialized")
    except Exception as e:
        print(f"LLM client failed: {e}")

    # Initialize RAG engine (optional - requires sentence-transformers)
    if RAGEngine is not None:
        try:
            rag_engine = RAGEngine()
            rag_engine.seed_default_rules()
            print("RAG engine initialized")
        except Exception as e:
            print(f"RAG engine failed: {e}")
    else:
        print("RAG engine skipped (sentence-transformers not installed)")

    # Load forecaster if model exists
    forecaster = DemandForecaster()
    try:
        forecaster.load()
        print("Forecaster model loaded")
    except FileNotFoundError:
        print("No trained model found - train via /api/train")

    # Initialize tool executor and wire it into LLM client
    tool_executor = ToolExecutor(data_loader, forecaster)
    if llm_client:
        llm_client.set_tool_executor(tool_executor)

    # Initialize simulator
    if llm_client:
        simulator = ScenarioSimulator(llm_client, tool_executor)

    print("FlowCast API ready!")


# === Health ===

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model_loaded": forecaster.model is not None if forecaster else False,
        "llm_available": llm_client is not None,
        "tools_available": tool_executor is not None
    }


# === Data Endpoints ===

@router.get("/data/tables")
async def list_tables():
    """List available data tables"""
    try:
        tables = data_loader.load_all_tables()
        loaded = data_loader.list_tables()
        return {
            "tables": [
                {"name": name, "rows": data_loader.get_table_info(name)["row_count"]}
                for name in loaded
            ],
            "count": len(loaded)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/inventory")
async def get_inventory_status(limit: int = 200):
    """Get current inventory status"""
    try:
        data_loader.load_all_tables()
        inventory = data_loader.get_inventory_status()

        low_stock_count = 0
        if "quantity" in inventory.columns and "threshold" in inventory.columns:
            mask = inventory["quantity"].notnull() & inventory["threshold"].notnull()
            filtered = inventory[mask]
            low_stock_count = int((filtered["quantity"] < filtered["threshold"]).sum())

        return {
            "items": inventory.head(limit).pipe(lambda d: _df_to_records(d)),
            "total_items": len(inventory),
            "low_stock_count": low_stock_count,
            "expiring_soon_count": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/sales")
async def get_daily_sales(limit: int = 1000):
    """Get daily sales data"""
    try:
        data_loader.load_all_tables()
        sales = data_loader.get_daily_sales()

        return {
            "sales": sales.head(limit).pipe(lambda d: _df_to_records(d)),
            "total_records": len(sales),
            "date_range": {
                "min": str(sales["date"].min()) if len(sales) > 0 else None,
                "max": str(sales["date"].max()) if len(sales) > 0 else None
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/menu")
async def get_menu_items(limit: int = 100):
    """Get menu items with ingredients"""
    try:
        data_loader.load_all_tables()
        menu = data_loader.get_menu_with_ingredients()


        return {
            "items": menu.head(limit).pipe(lambda d: _df_to_records(d)),
            "total": len(menu)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/query")
async def run_query(sql: str, limit: int = 100):
    """Run an arbitrary SQL query (read-only)"""
    try:
        data_loader.load_all_tables()

        # Block destructive operations
        sql_upper = sql.strip().upper()
        blocked = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE"]
        for kw in blocked:
            if sql_upper.startswith(kw):
                raise HTTPException(status_code=400, detail=f"Destructive SQL ({kw}) not allowed")

        df = data_loader.query(sql)

        return {
            "data": df.head(limit).pipe(lambda d: _df_to_records(d)),
            "total_rows": len(df),
            "columns": list(df.columns)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Model Endpoints ===

@router.post("/train", response_model=TrainResponse)
async def train_model(request: TrainRequest, background_tasks: BackgroundTasks):
    """Train or retrain the forecasting model"""
    global forecaster, tool_executor

    if not request.force_retrain and forecaster and forecaster.model is not None:
        return TrainResponse(
            status="skipped",
            metrics=forecaster.metrics,
            message="Model already trained. Use force_retrain=true to retrain."
        )

    try:
        trainer = ModelTrainer()
        results = trainer.run_training_pipeline(verbose=True)

        # Reload forecaster with new model
        forecaster = DemandForecaster()
        forecaster.load()

        # Update tool executor with new forecaster
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
async def generate_forecast(request: ForecastRequest):
    """Generate demand forecasts"""
    if forecaster is None or forecaster.model is None:
        raise HTTPException(status_code=400, detail="Model not trained. Call /train first.")

    try:
        trainer = ModelTrainer()
        forecasts = trainer.generate_forecasts(
            days_ahead=request.days_ahead,
            item_filter=request.item_filter
        )

        return ForecastResponse(
            forecasts=forecasts.pipe(lambda d: _df_to_records(d)),
            generated_at=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model/features")
async def get_feature_importance(top_n: int = 20):
    """Get feature importance from trained model"""
    if forecaster is None or forecaster.model is None:
        raise HTTPException(status_code=400, detail="Model not trained")

    importance = forecaster.get_feature_importance(top_n)
    return {
        "features": importance.pipe(lambda d: _df_to_records(d)),
        "model_metrics": forecaster.metrics
    }


# === LLM/Chat Endpoints ===

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat with the AI assistant (with function-calling)"""
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    try:
        # Use function-calling chat if tool executor is available
        if tool_executor:
            response = await llm_client.chat_with_tools(request.message)
        else:
            # Fallback to basic chat with context
            context = {}
            if request.include_context and rag_engine:
                rag_context = rag_engine.get_context_for_query(request.message)
                context["business_rules"] = rag_context
            response = await llm_client.generate_insights(context, query=request.message)

        return ChatResponse(
            response=response,
            context_used=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Chat with SSE streaming and function-calling"""
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    async def event_generator():
        try:
            async for event in llm_client.chat_with_tools_stream(request.message):
                yield event
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/insights", response_model=InsightResponse)
async def generate_insights(request: InsightRequest):
    """Generate inventory insights"""
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    try:
        context = {}
        data_loader.load_all_tables()

        # Current stock
        inventory = data_loader.get_inventory_status()
        context["current_stock"] = inventory.head(20).to_string()

        # Recent sales
        sales = data_loader.get_daily_sales()
        context["recent_sales"] = sales.tail(50).to_string()

        # Forecasts if available
        if forecaster and forecaster.model is not None:
            try:
                trainer = ModelTrainer()
                forecasts = trainer.generate_forecasts(days_ahead=7)
                context["forecasts"] = forecasts.head(20).to_string()
            except Exception:
                pass

        # RAG context
        if rag_engine and request.query:
            context["business_rules"] = rag_engine.get_context_for_query(request.query)

        response = await llm_client.generate_insights(context, query=request.query)

        return InsightResponse(
            insight=response,
            generated_at=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/explain-anomaly")
async def explain_anomaly(
    item: str,
    expected: float,
    actual: float,
    day_of_week: Optional[str] = None,
    weather: Optional[str] = None
):
    """Explain why sales differed from forecast"""
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    try:
        context = {
            "day_of_week": day_of_week or "Unknown",
            "weather": weather or "Unknown",
            "promotions": "None",
            "events": "None"
        }

        explanation = await llm_client.explain_anomaly(item, expected, actual, context)

        return {
            "item": item,
            "expected": expected,
            "actual": actual,
            "explanation": explanation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggest-promotion")
async def suggest_promotion(
    item: str,
    current_stock: float,
    days_to_expiry: int,
    avg_daily_sales: float,
    cost: float,
    price: float
):
    """Get promotion suggestions for expiring inventory"""
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    try:
        suggestion = await llm_client.suggest_promotion(
            item, current_stock, days_to_expiry, avg_daily_sales, cost, price
        )

        return {
            "item": item,
            "suggestion": suggestion
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Simulator ===

@router.post("/simulate")
async def run_simulation(request: SimulateRequest):
    """Run a what-if scenario simulation"""
    if simulator is None:
        raise HTTPException(status_code=503, detail="Simulator not available (requires LLM)")

    try:
        result = await simulator.simulate(request.scenario)
        return {
            "scenario": request.scenario,
            "analysis": result,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
