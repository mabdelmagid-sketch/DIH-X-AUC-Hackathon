"""
Chat/LLM endpoints for FlowPOS Forecasting API.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime
import json

from ..data.loader import DataLoader
from ..models.forecaster import DemandForecaster
from ..models.trainer import ModelTrainer
from ..llm.client import LLMClient
from ..llm.tools import ToolExecutor
from ..llm.simulator import ScenarioSimulator
from .dependencies import (
    get_data_loader, get_forecaster, get_llm_client,
    get_tool_executor, get_rag_engine, get_simulator
)
from .schemas import (
    ChatRequest, ChatResponse,
    InsightRequest, InsightResponse,
    SimulateRequest, PrepRecommendationRequest
)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    llm_client: Optional[LLMClient] = Depends(get_llm_client),
    tool_executor: Optional[ToolExecutor] = Depends(get_tool_executor),
    rag_engine=Depends(get_rag_engine)
):
    """Chat with the AI assistant (with function-calling)."""
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    try:
        if tool_executor:
            response = await llm_client.chat_with_tools(request.message)
        else:
            context = {}
            if request.include_context and rag_engine:
                rag_context = rag_engine.get_context_for_query(request.message)
                context["business_rules"] = rag_context
            response = await llm_client.generate_insights(context, query=request.message)

        return ChatResponse(response=response, context_used=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    llm_client: Optional[LLMClient] = Depends(get_llm_client)
):
    """Chat with SSE streaming and function-calling."""
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
async def generate_insights(
    request: InsightRequest,
    llm_client: Optional[LLMClient] = Depends(get_llm_client),
    loader: DataLoader = Depends(get_data_loader),
    forecaster: DemandForecaster = Depends(get_forecaster),
    rag_engine=Depends(get_rag_engine)
):
    """Generate inventory insights."""
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    try:
        context = {}
        loader.load_all_tables()

        if request.store_context:
            # When store context is provided, use it as primary data source
            # and filter raw data to only include relevant items
            context["store_info"] = request.store_context

            # Try to get sales data filtered to store items
            try:
                sales = loader.get_daily_sales()
                if not sales.empty:
                    context["recent_sales"] = sales.tail(30).to_string()
            except Exception:
                pass
        else:
            # Default: use all DuckDB data
            inventory = loader.get_inventory_status()
            context["current_stock"] = inventory.head(20).to_string()

            sales = loader.get_daily_sales()
            context["recent_sales"] = sales.tail(50).to_string()

        if forecaster.model is not None:
            try:
                trainer = ModelTrainer()
                forecasts = trainer.generate_forecasts(days_ahead=7)
                context["forecasts"] = forecasts.head(20).to_string()
            except Exception:
                pass

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
    weather: Optional[str] = None,
    llm_client: Optional[LLMClient] = Depends(get_llm_client)
):
    """Explain why sales differed from forecast."""
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
    price: float,
    llm_client: Optional[LLMClient] = Depends(get_llm_client)
):
    """Get promotion suggestions for expiring inventory."""
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


@router.post("/simulate")
async def run_simulation(
    request: SimulateRequest,
    simulator: Optional[ScenarioSimulator] = Depends(get_simulator)
):
    """Run a what-if scenario simulation."""
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


@router.post("/prep-recommendation")
async def prep_recommendation(
    request: PrepRecommendationRequest,
    llm_client: Optional[LLMClient] = Depends(get_llm_client),
):
    """Get AI-powered prep/order recommendations using dual-model arbitration.

    The LLM calls get_context_signals (weather, holidays, etc.) and
    get_dual_forecast (both models), then decides per item which
    forecast to use based on context + item characteristics.
    """
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    from ..llm.prompts import SYSTEM_PROMPTS

    # Build the user message
    parts = ["Generate today's prep/order recommendations."]
    if request.item_name:
        parts.append(f"Focus on items matching: {request.item_name}")
    if request.place_id:
        parts.append(f"For store/place ID: {request.place_id}")
    if request.date:
        parts.append(f"Target date: {request.date}")
    else:
        parts.append(f"Target date: {datetime.now().strftime('%Y-%m-%d')}")

    user_message = " ".join(parts)

    try:
        response = await llm_client.chat_with_tools(
            user_message=user_message,
            system_prompt=SYSTEM_PROMPTS["inventory_advisor"],
            temperature=0.3,
            max_tokens=4096,
        )

        return {
            "recommendation": response,
            "generated_at": datetime.now().isoformat(),
            "model": "inventory_advisor",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prep-recommendation/stream")
async def prep_recommendation_stream(
    request: PrepRecommendationRequest,
    llm_client: Optional[LLMClient] = Depends(get_llm_client),
):
    """Streaming version of prep recommendations via SSE."""
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not available")

    from ..llm.prompts import SYSTEM_PROMPTS

    parts = ["Generate today's prep/order recommendations."]
    if request.item_name:
        parts.append(f"Focus on items matching: {request.item_name}")
    if request.place_id:
        parts.append(f"For store/place ID: {request.place_id}")
    if request.date:
        parts.append(f"Target date: {request.date}")
    else:
        parts.append(f"Target date: {datetime.now().strftime('%Y-%m-%d')}")

    user_message = " ".join(parts)

    async def event_generator():
        try:
            async for event in llm_client.chat_with_tools_stream(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPTS["inventory_advisor"],
                temperature=0.3,
                max_tokens=4096,
            ):
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
