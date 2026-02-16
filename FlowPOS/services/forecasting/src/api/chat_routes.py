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

        # Always include store context if provided
        if request.store_context:
            context["store_info"] = request.store_context

        # Fetch data from the Fresh Foods dataset (DuckDB)
        try:
            import pandas as pd

            loader.load_all_tables()

            # 1) Top menu items from actual order data (so LLM knows real product names)
            try:
                top_items_df = loader.query("""
                    SELECT oi.title, COUNT(*) as order_count,
                           SUM(oi.quantity) as total_qty,
                           ROUND(AVG(oi.price), 2) as avg_price
                    FROM fct_order_items oi
                    GROUP BY oi.title
                    ORDER BY total_qty DESC
                    LIMIT 40
                """)
                if not top_items_df.empty:
                    item_lines = []
                    for _, row in top_items_df.iterrows():
                        item_lines.append(
                            f"  {row['title']}: {row['total_qty']:.0f} sold, avg price {row['avg_price']:.0f} DKK"
                        )
                    context["menu_items"] = (
                        f"Top {len(top_items_df)} menu items by total sales volume:\n"
                        + "\n".join(item_lines)
                    )
            except Exception:
                pass

            # 2) Current inventory status
            inventory = loader.get_inventory_status()
            if not inventory.empty:
                # Only include items that have actual quantity data
                tracked = inventory[inventory["quantity"].notnull()]
                low_stock = tracked[
                    tracked["threshold"].notnull()
                    & (tracked["quantity"] <= tracked["threshold"])
                ]
                if not tracked.empty:
                    lines = []
                    for _, row in tracked.head(30).iterrows():
                        qty = row.get("quantity")
                        thresh = row.get("threshold")
                        unit = row.get("unit", "")
                        status = "LOW" if (pd.notnull(thresh) and qty <= thresh) else "OK"
                        lines.append(
                            f"  {row['title']}: {qty} {unit} (threshold: {thresh}) [{status}]"
                        )
                    context["current_stock"] = (
                        f"{len(tracked)} items with inventory tracking, {len(low_stock)} below threshold.\n"
                        + "\n".join(lines)
                    )
                else:
                    context["current_stock"] = (
                        f"Inventory tracking is not configured — no quantity data available for {len(inventory)} catalog items. "
                        f"Analysis is based on sales and forecast data only."
                    )

            # 3) Recent sales from fct_orders + fct_order_items
            sales = loader.get_daily_sales()
            if not sales.empty:
                sales["date"] = pd.to_datetime(sales["date"], errors="coerce")
                max_date = sales["date"].max()

                # Last 30 days of sales
                cutoff_30d = max_date - pd.Timedelta(days=30)
                recent_30d = sales[sales["date"] >= cutoff_30d]

                if not recent_30d.empty:
                    daily_totals = recent_30d.groupby("date")["total_quantity"].sum()
                    avg_daily = daily_totals.mean()
                    context["recent_sales"] = (
                        f"Last 30 days of data (up to {max_date.strftime('%Y-%m-%d')}): "
                        f"avg {avg_daily:.0f} items/day, "
                        f"total {daily_totals.sum():.0f} items across {len(daily_totals)} days.\n"
                        f"Top sellers (30d):\n"
                    )
                    top = recent_30d.groupby("item_title")["total_quantity"].sum().sort_values(ascending=False).head(15)
                    for name, qty in top.items():
                        context["recent_sales"] += f"  {name}: {qty:.0f} sold\n"

                # Week-over-week trends
                cutoff_7d = max_date - pd.Timedelta(days=7)
                cutoff_14d = max_date - pd.Timedelta(days=14)
                this_week = sales[sales["date"] >= cutoff_7d].groupby("item_title")["total_quantity"].sum()
                last_week = sales[(sales["date"] >= cutoff_14d) & (sales["date"] < cutoff_7d)].groupby("item_title")["total_quantity"].sum()

                trending_up = []
                trending_down = []
                for item in last_week.index:
                    prev = last_week[item]
                    curr = this_week.get(item, 0)
                    if prev > 5:
                        pct = ((curr - prev) / prev) * 100
                        if pct > 30:
                            trending_up.append(f"  {item}: {prev:.0f} → {curr:.0f} ({pct:+.0f}%)")
                        elif pct < -30:
                            trending_down.append(f"  {item}: {prev:.0f} → {curr:.0f} ({pct:+.0f}%)")

                if trending_up:
                    context["trending_up"] = "Items with rising demand (week-over-week):\n" + "\n".join(trending_up[:10])
                if trending_down:
                    context["trending_down"] = "Items with declining demand (week-over-week):\n" + "\n".join(trending_down[:10])

            # 4) Forecast data from trained models or SQL fallback
            try:
                from ..llm.tools import ToolExecutor
                tool_exec = ToolExecutor(loader, forecaster)
                forecast_json = tool_exec._tool_get_dual_forecast(days_ahead=7)
                forecast_data = json.loads(forecast_json) if isinstance(forecast_json, str) else forecast_json

                if isinstance(forecast_data, list) and forecast_data:
                    lines = []
                    for f in forecast_data[:20]:
                        item = f.get("item", "")
                        avg = f.get("avg_daily_demand", 0)
                        risk = f.get("demand_risk", "unknown")
                        perishable = "Yes" if f.get("is_perishable") else "No"
                        safety = f.get("safety_stock_units", 0)
                        source = f.get("model_source", "unknown")
                        balanced = f.get("forecast_xgboost_balanced") or f.get("forecast_balanced", avg)
                        waste = f.get("forecast_waste_optimized", avg * 0.85)
                        lines.append(
                            f"  {item}: avg {avg:.1f}/day, balanced={balanced:.1f}, waste_opt={waste:.1f}, "
                            f"risk={risk}, perishable={perishable}, safety_stock={safety:.1f} [{source}]"
                        )
                    context["forecasts"] = "\n".join(lines)
            except Exception:
                pass  # Forecasts are optional context

        except Exception:
            pass  # If DuckDB loading fails, continue without data context

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
    simulator: Optional[ScenarioSimulator] = Depends(get_simulator),
    loader: DataLoader = Depends(get_data_loader),
):
    """Run a what-if scenario simulation. Uses LLM if available, otherwise data-driven fallback."""
    # Try LLM-powered simulation first
    if simulator is not None:
        try:
            result = await simulator.simulate(request.scenario)
            return {
                "scenario": request.scenario,
                "analysis": result,
                "generated_at": datetime.now().isoformat()
            }
        except Exception:
            pass  # Fall through to data-driven fallback

    # Data-driven fallback (no LLM required)
    try:
        analysis = _simulate_from_data(request.scenario, loader)
        return {
            "scenario": request.scenario,
            "analysis": analysis,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _simulate_from_data(scenario: str, loader: DataLoader) -> str:
    """Generate a data-driven simulation analysis without LLM."""
    import pandas as pd
    import re

    loader.load_all_tables()
    scenario_lower = scenario.lower()

    # --- Parse scenario parameters ---
    # Extract percentage
    pct_match = re.search(r'(\d+)\s*%', scenario)
    pct = int(pct_match.group(1)) if pct_match else 20

    # Extract number of days
    days_match = re.search(r'(\d+)\s*days?', scenario_lower)
    sim_days = int(days_match.group(1)) if days_match else 7

    # Extract price
    price_match = re.search(r'(\d+)\s*(?:dkk|kr)', scenario_lower)
    target_price = int(price_match.group(1)) if price_match else None

    # --- Get baseline data ---
    sales_df = loader.get_daily_sales()
    sales_df["date"] = pd.to_datetime(sales_df["date"], errors="coerce")
    max_date = sales_df["date"].max()
    cutoff = max_date - pd.Timedelta(days=30)
    recent = sales_df[sales_df["date"] >= cutoff]

    if recent.empty:
        return "Not enough sales data to simulate this scenario."

    # Top items by revenue
    item_stats = recent.groupby("item_title").agg(
        total_qty=("total_quantity", "sum"),
        total_rev=("total_revenue", "sum"),
        order_count=("order_count", "sum"),
        active_days=("total_quantity", "count"),
    ).reset_index()
    item_stats["avg_daily_qty"] = item_stats["total_qty"] / item_stats["active_days"]
    item_stats["avg_price"] = item_stats["total_rev"] / item_stats["total_qty"].replace(0, 1)
    item_stats = item_stats.sort_values("total_rev", ascending=False)

    daily_revenue = recent.groupby("date")["total_revenue"].sum()
    avg_daily_revenue = daily_revenue.mean()
    daily_qty = recent.groupby("date")["total_quantity"].sum()
    avg_daily_qty = daily_qty.mean()

    # --- Identify scenario type and compute impact ---
    lines = []
    lines.append(f"## Scenario Analysis: {scenario}\n")
    lines.append(f"**Baseline (last 30 days):**")
    lines.append(f"- Average daily revenue: {avg_daily_revenue:,.0f} DKK")
    lines.append(f"- Average daily items sold: {avg_daily_qty:,.0f}")
    lines.append(f"- Top products: {', '.join(item_stats.head(5)['item_title'].tolist())}")
    lines.append("")

    # Detect scenario keywords
    is_discount = any(w in scenario_lower for w in ["discount", "off", "sale", "promotion", "promo", "reduce price"])
    is_price_increase = any(w in scenario_lower for w in ["increase price", "raise price", "price increase"])
    is_new_item = any(w in scenario_lower for w in ["new", "add", "launch", "introduce"])
    is_stop = any(w in scenario_lower for w in ["stop", "remove", "discontinue", "cut"])
    is_demand_change = any(w in scenario_lower for w in ["demand increase", "demand decrease", "more customers", "less customers", "increase by", "decrease by"])
    is_supply = any(w in scenario_lower for w in ["supplier", "delivery", "delay", "shortage", "supply"])
    is_combo = any(w in scenario_lower for w in ["combo", "bundle", "meal deal", "deal"])

    # Find matching items from the scenario text
    matched_items = []
    for _, row in item_stats.iterrows():
        item_words = row["item_title"].lower().split()
        if any(w in scenario_lower for w in item_words if len(w) > 3):
            matched_items.append(row)
    matched_df = pd.DataFrame(matched_items) if matched_items else item_stats.head(10)

    if is_discount:
        # Price elasticity simulation: ~1.5x elasticity for food
        elasticity = 1.5
        demand_boost = (pct / 100) * elasticity
        lines.append(f"### Discount Impact ({pct}% off)")
        lines.append(f"Using price elasticity of {elasticity} for food/beverage:\n")

        total_rev_change = 0
        total_qty_change = 0
        lines.append("| Item | Current Avg/Day | Projected Avg/Day | Daily Rev Change |")
        lines.append("|------|----------------|-------------------|-----------------|")
        for _, row in matched_df.head(8).iterrows():
            old_qty = row["avg_daily_qty"]
            new_qty = old_qty * (1 + demand_boost)
            old_rev = old_qty * row["avg_price"]
            new_rev = new_qty * row["avg_price"] * (1 - pct / 100)
            rev_change = new_rev - old_rev
            total_rev_change += rev_change
            total_qty_change += new_qty - old_qty
            lines.append(f"| {row['item_title'][:30]} | {old_qty:.1f} | {new_qty:.1f} | {rev_change:+,.0f} DKK |")

        lines.append(f"\n**Projected daily impact:**")
        lines.append(f"- Volume increase: +{total_qty_change:.0f} items/day ({demand_boost*100:.0f}%)")
        lines.append(f"- Revenue change: {total_rev_change:+,.0f} DKK/day")
        lines.append(f"- Over {sim_days} days: {total_rev_change * sim_days:+,.0f} DKK")
        lines.append(f"\n**Recommendation:** {'Proceed with caution - margin compression likely.' if total_rev_change < 0 else 'Looks viable - volume gains offset the discount.'}")

    elif is_demand_change:
        change = pct / 100 if "increase" in scenario_lower else -(pct / 100)
        direction = "increase" if change > 0 else "decrease"
        lines.append(f"### Demand {direction.title()} ({abs(change)*100:.0f}%)")
        new_daily_rev = avg_daily_revenue * (1 + change)
        new_daily_qty = avg_daily_qty * (1 + change)
        lines.append(f"\n| Metric | Current | Projected |")
        lines.append(f"|--------|---------|-----------|")
        lines.append(f"| Daily Revenue | {avg_daily_revenue:,.0f} DKK | {new_daily_rev:,.0f} DKK |")
        lines.append(f"| Daily Items | {avg_daily_qty:,.0f} | {new_daily_qty:,.0f} |")
        lines.append(f"| Monthly Revenue | {avg_daily_revenue*30:,.0f} DKK | {new_daily_rev*30:,.0f} DKK |")
        lines.append(f"\n**Supply implications:**")
        for _, row in item_stats.head(5).iterrows():
            new_qty = row["avg_daily_qty"] * (1 + change)
            lines.append(f"- {row['item_title']}: {row['avg_daily_qty']:.1f} → {new_qty:.1f}/day")

    elif is_stop:
        lines.append(f"### Impact of Removing Items")
        if matched_items:
            lost_rev = sum(r["total_rev"] / 30 for _, r in matched_df.iterrows())
            lost_qty = sum(r["avg_daily_qty"] for _, r in matched_df.iterrows())
            lines.append(f"\nItems affected: {', '.join(matched_df['item_title'].tolist())}")
            lines.append(f"- Daily revenue lost: {lost_rev:,.0f} DKK")
            lines.append(f"- Daily items lost: {lost_qty:.0f}")
            lines.append(f"- Monthly revenue impact: {lost_rev * 30:,.0f} DKK")
            lines.append(f"\n**Recommendation:** Consider substitution with similar items to retain customers.")
        else:
            lines.append(f"Could not identify specific items from the scenario. Total menu has {len(item_stats)} active items.")

    elif is_supply:
        delay_days = sim_days
        lines.append(f"### Supply Disruption Impact ({delay_days}-day delay)")
        lines.append(f"\nDuring a {delay_days}-day supply disruption:")
        lines.append(f"- Revenue at risk: {avg_daily_revenue * delay_days:,.0f} DKK")
        lines.append(f"- Items affected: ~{len(item_stats)} products")
        lines.append(f"\n**Most vulnerable items** (highest daily demand):")
        for _, row in item_stats.head(8).iterrows():
            lines.append(f"- {row['item_title']}: {row['avg_daily_qty']:.1f}/day × {delay_days}d = {row['avg_daily_qty']*delay_days:.0f} units needed")
        lines.append(f"\n**Recommendation:** Build {delay_days+2}-day buffer stock for top sellers. Prioritize non-perishable alternatives.")

    elif is_new_item or is_combo:
        lines.append(f"### New Item / Combo Analysis")
        # Find similar items to estimate demand
        avg_item_demand = item_stats["avg_daily_qty"].median()
        avg_item_price = item_stats["avg_price"].median()
        est_price = target_price or avg_item_price
        conservative_demand = avg_item_demand * 0.6
        optimistic_demand = avg_item_demand * 1.0

        lines.append(f"\nBased on {len(item_stats)} existing menu items:")
        lines.append(f"- Median item sells: {avg_item_demand:.1f}/day at ~{avg_item_price:.0f} DKK")
        lines.append(f"- Estimated price point: {est_price:.0f} DKK")
        lines.append(f"\n**Demand estimate:**")
        lines.append(f"- Conservative: {conservative_demand:.1f} units/day ({conservative_demand * est_price:.0f} DKK/day)")
        lines.append(f"- Optimistic: {optimistic_demand:.1f} units/day ({optimistic_demand * est_price:.0f} DKK/day)")
        lines.append(f"- Monthly revenue range: {conservative_demand * est_price * 30:,.0f} - {optimistic_demand * est_price * 30:,.0f} DKK")
        lines.append(f"\n**Recommendation:** Start with conservative prep ({conservative_demand:.0f}/day) for the first 1-2 weeks, then adjust based on actual sales.")

    else:
        # Generic analysis
        lines.append(f"### General Impact Analysis")
        lines.append(f"\n**Current business metrics (30-day baseline):**")
        lines.append(f"- Total revenue: {daily_revenue.sum():,.0f} DKK")
        lines.append(f"- Avg daily revenue: {avg_daily_revenue:,.0f} DKK")
        lines.append(f"- Active products: {len(item_stats)}")
        lines.append(f"- Avg items sold/day: {avg_daily_qty:,.0f}")
        lines.append(f"\n**Top 10 products by revenue:**")
        for _, row in item_stats.head(10).iterrows():
            lines.append(f"- {row['item_title']}: {row['avg_daily_qty']:.1f}/day, {row['total_rev']/30:,.0f} DKK/day")
        lines.append(f"\nApply the scenario assumptions to these baselines to estimate impact.")

    # Inventory context
    try:
        inv = loader.get_inventory_status()
        low_stock = inv[
            inv["quantity"].notnull()
            & inv["threshold"].notnull()
            & (inv["quantity"] <= inv["threshold"])
        ]
        if not low_stock.empty:
            lines.append(f"\n**Current inventory alerts:** {len(low_stock)} items below reorder threshold")
    except Exception:
        pass

    return "\n".join(lines)


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
