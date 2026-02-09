"""
Model/forecasting endpoints for FlowPOS Forecasting API.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, date, timedelta
import json
import logging

import numpy as np
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


async def _forecast_from_supabase(days_ahead: int, item_filter: str | None, top_n: int | None) -> dict:
    """Generate forecasts using real POS data from Supabase."""
    import httpx

    supa_url = settings.supabase_url
    supa_key = settings.supabase_service_key
    if not supa_url or not supa_key:
        raise HTTPException(status_code=400, detail="Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.")

    headers = {"apikey": supa_key, "Authorization": f"Bearer {supa_key}"}
    rest_url = f"{supa_url}/rest/v1"

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Fetch order items with order dates
        oi_resp = await client.get(
            f"{rest_url}/order_items?select=name,quantity,created_at,order_id",
            headers=headers,
        )
        oi_resp.raise_for_status()
        order_items = oi_resp.json()

    if not order_items:
        raise HTTPException(status_code=404, detail="No order data in Supabase.")

    # Build daily sales DataFrame
    rows = []
    for oi in order_items:
        name = (oi.get("name") or "").strip()
        if not name:
            continue
        if item_filter and item_filter.lower() not in name.lower():
            continue
        rows.append({
            "item": name,
            "date": oi["created_at"][:10],
            "quantity_sold": float(oi.get("quantity", 1)),
        })

    if not rows:
        raise HTTPException(status_code=404, detail="No matching sales data found.")

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby(["item", "date"], as_index=False)["quantity_sold"].sum()

    # Per-item stats
    item_stats = daily.groupby("item").agg(
        avg_daily=("quantity_sold", "mean"),
        std_daily=("quantity_sold", "std"),
        active_days=("quantity_sold", "count"),
        total_sold=("quantity_sold", "sum"),
    ).reset_index()
    item_stats["std_daily"] = item_stats["std_daily"].fillna(0)

    # Weekday factors from real sales
    daily["dow"] = daily["date"].dt.dayofweek
    dow_avg = daily.groupby(["item", "dow"])["quantity_sold"].mean()
    overall_avg = daily.groupby("item")["quantity_sold"].mean()

    # Apply top_n filter
    if top_n and top_n > 0:
        item_stats = item_stats.nlargest(top_n, "total_sold")

    # Generate forecasts
    base_date = date.today() + timedelta(days=1)
    forecasts = []

    for _, row in item_stats.iterrows():
        item_name = row["item"]
        avg = float(row["avg_daily"])
        std = float(row["std_daily"])
        cv = std / avg if avg > 0 else 0
        active = int(row["active_days"])

        # Confidence based on data volume
        if active >= 14:
            confidence = "medium"
        elif active >= 5:
            confidence = "low"
        else:
            confidence = "very_low"

        risk = "high" if cv > 1.0 else "medium" if cv > 0.5 else "low"

        item_lower = item_name.lower()
        perishable_kw = ["salad", "juice", "fresh", "smoothie", "sandwich", "bowl", "wrap", "acai", "egg"]
        is_perishable = any(kw in item_lower for kw in perishable_kw)

        for d in range(days_ahead):
            forecast_date = base_date + timedelta(days=d)
            dow = forecast_date.weekday()

            # Weekday scaling from real data
            factor = 1.0
            if (item_name, dow) in dow_avg.index and item_name in overall_avg.index:
                raw_factor = dow_avg[(item_name, dow)] / overall_avg[item_name]
                factor = max(0.5, min(1.8, raw_factor))
            elif dow in (5, 6):
                factor = 0.8
            elif dow == 4:
                factor = 1.1

            pred = max(0.0, avg * factor)

            forecasts.append({
                "item_title": item_name,
                "date": forecast_date.isoformat(),
                "predicted_quantity": round(pred, 1),
                "lower_bound": round(pred * 0.7, 1),
                "upper_bound": round(pred * 1.4, 1),
                "demand_risk": risk,
                "is_perishable": is_perishable,
                "safety_stock": round(1.65 * std, 1),
                "model_source": f"supabase_history ({active}d)",
                "confidence": confidence,
            })

    return {
        "forecasts": forecasts,
        "generated_at": datetime.now().isoformat(),
    }


@router.post("/forecast", response_model=ForecastResponse)
async def generate_forecast(
    request: ForecastRequest,
    forecaster: DemandForecaster = Depends(get_forecaster),
    loader: DataLoader = Depends(get_data_loader)
):
    """Generate demand forecasts using pre-trained models.

    Uses the trained HybridForecaster/WasteOptimizedForecaster .pkl models.
    Falls back to the DemandForecaster if trained models aren't available.
    Pass source="supabase" to use real POS store data instead of demo data.
    """
    # ── Supabase source: use real POS data ───────────────────────────
    if request.source == "supabase":
        result = await _forecast_from_supabase(
            request.days_ahead, request.item_filter, request.top_n
        )
        return ForecastResponse(**result)

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


@router.get("/forecast/ingredients")
async def forecast_ingredients(
    days_ahead: int = 7,
    top_n: int | None = None,
    loader: DataLoader = Depends(get_data_loader),
):
    """Forecast ingredient-level demand by exploding product forecasts through BOM.

    Takes product-level demand forecasts from the 3-model ensemble, maps them
    through SKU links and Bill of Materials to raw ingredient quantities,
    then compares against current stock levels.

    Returns per-ingredient: forecasted demand, current stock, days remaining,
    reorder urgency, and which products drive the demand.
    """
    try:
        loader.load_all_tables()

        # ── 1. Product-level forecasts from ensemble ─────────────────────
        daily_sales = _get_sales_for_forecast(loader, top_n=top_n)
        if daily_sales.empty:
            raise HTTPException(status_code=404, detail="No sales data available.")

        multi_results = predict_multi_day(daily_sales, days_ahead=days_ahead)
        if not multi_results:
            raise HTTPException(status_code=400, detail="Forecast models not available.")

        # Sum forecasts per product across all days
        product_demand: dict[str, float] = {}
        for r in multi_results:
            item = r["item"]
            product_demand[item] = product_demand.get(item, 0) + r["forecast_balanced"]

        # ── 2. Load SKU / BOM / Item mapping tables ──────────────────────
        skus_df = loader.query("SELECT id, item_id, title, quantity, low_stock_threshold, type, unit FROM dim_skus")
        bom_df = loader.query("SELECT parent_sku_id, sku_id, quantity FROM dim_bill_of_materials")

        # Try both dim_items and dim_menu_items for product→SKU mapping
        items_df = loader.query("SELECT id, title FROM dim_items")
        menu_df = loader.query("SELECT id, title FROM dim_menu_items")

        # Merge product tables for broader matching
        all_products = pd.concat([
            items_df[["id", "title"]],
            menu_df[["id", "title"]],
        ]).drop_duplicates(subset="id")

        # ── 3. Build lookup maps ─────────────────────────────────────────
        # product_id → product_title
        prod_id_to_title = dict(zip(all_products["id"], all_products["title"]))
        # product_title (lower) → product_id
        prod_title_to_id = {str(t).lower(): int(pid) for pid, t in zip(all_products["id"], all_products["title"])}

        # SKU map: sku_id → info
        sku_map: dict[int, dict] = {}
        for _, sku in skus_df.iterrows():
            sku_map[int(sku["id"])] = {
                "title": str(sku["title"]),
                "quantity": float(sku["quantity"]) if pd.notna(sku["quantity"]) else 0.0,
                "low_stock_threshold": float(sku["low_stock_threshold"]) if pd.notna(sku["low_stock_threshold"]) else 0.0,
                "type": str(sku["type"]),
                "unit": str(sku["unit"]),
                "item_id": int(sku["item_id"]) if pd.notna(sku["item_id"]) else None,
            }

        # item_id → list of sku_ids
        item_to_skus: dict[int, list[int]] = {}
        for sku_id, info in sku_map.items():
            if info["item_id"] is not None:
                item_to_skus.setdefault(info["item_id"], []).append(sku_id)

        # BOM: parent_sku_id → [(child_sku_id, qty_per_unit)]
        bom_map: dict[int, list[tuple[int, float]]] = {}
        for _, row in bom_df.iterrows():
            parent = int(row["parent_sku_id"])
            bom_map.setdefault(parent, []).append(
                (int(row["sku_id"]), float(row["quantity"]))
            )

        # ── 4. Explode product demand → ingredient demand ────────────────
        ingredient_demand: dict[int, float] = {}       # sku_id → total qty needed
        ingredient_drivers: dict[int, list[str]] = {}  # sku_id → [product names driving demand]
        mapped_products: set[str] = set()

        for product_title, demand in product_demand.items():
            # Find product_id via title matching
            product_id = prod_title_to_id.get(product_title.lower())
            if product_id is None:
                continue

            # Find SKUs linked to this product
            linked_sku_ids = item_to_skus.get(product_id, [])
            if not linked_sku_ids:
                continue

            mapped_products.add(product_title)

            for sku_id in linked_sku_ids:
                sku_info = sku_map.get(sku_id)
                if not sku_info:
                    continue

                if sku_info["type"] == "composite" and sku_id in bom_map:
                    # Explode through BOM → raw ingredients
                    for child_sku_id, bom_qty in bom_map[sku_id]:
                        ingredient_demand[child_sku_id] = ingredient_demand.get(child_sku_id, 0) + demand * bom_qty
                        ingredient_drivers.setdefault(child_sku_id, [])
                        if product_title not in ingredient_drivers[child_sku_id]:
                            ingredient_drivers[child_sku_id].append(product_title)
                else:
                    # Direct ingredient (non-composite SKU)
                    ingredient_demand[sku_id] = ingredient_demand.get(sku_id, 0) + demand
                    ingredient_drivers.setdefault(sku_id, [])
                    if product_title not in ingredient_drivers[sku_id]:
                        ingredient_drivers[sku_id].append(product_title)

        # ── 5. Build response with stock comparison ──────────────────────
        results = []
        for sku_id, info in sku_map.items():
            demand = ingredient_demand.get(sku_id, 0.0)
            daily_rate = demand / days_ahead if demand > 0 else 0.0
            current_stock = info["quantity"]
            days_remaining = current_stock / daily_rate if daily_rate > 0 else 999.0
            needs_reorder = (
                current_stock < info["low_stock_threshold"]
                or (daily_rate > 0 and days_remaining < days_ahead)
            )

            if days_remaining < 2:
                urgency = "critical"
            elif days_remaining < days_ahead:
                urgency = "soon"
            elif current_stock < info["low_stock_threshold"]:
                urgency = "low_stock"
            else:
                urgency = "ok"

            # Suggested reorder qty: enough for days_ahead + 50% buffer
            reorder_qty = max(0.0, (daily_rate * days_ahead * 1.5) - current_stock) if daily_rate > 0 else 0.0

            results.append({
                "ingredient": info["title"],
                "sku_id": sku_id,
                "unit": info["unit"],
                "type": info["type"],
                "current_stock": round(current_stock, 2),
                "forecasted_demand": round(demand, 2),
                "daily_consumption_rate": round(daily_rate, 2),
                "days_of_stock_remaining": round(min(days_remaining, 999.0), 1),
                "low_stock_threshold": info["low_stock_threshold"],
                "needs_reorder": needs_reorder,
                "reorder_urgency": urgency,
                "suggested_reorder_qty": round(reorder_qty, 2),
                "demand_drivers": ingredient_drivers.get(sku_id, []),
            })

        # Sort: critical first, then soon, then low_stock, then ok
        urgency_order = {"critical": 0, "soon": 1, "low_stock": 2, "ok": 3}
        results.sort(key=lambda x: (urgency_order.get(x["reorder_urgency"], 4), -x["forecasted_demand"]))

        unmapped = [p for p in product_demand if p not in mapped_products]

        return {
            "ingredients": results,
            "summary": {
                "days_ahead": days_ahead,
                "total_ingredients": len(results),
                "needs_reorder_count": sum(1 for r in results if r["needs_reorder"]),
                "critical_count": sum(1 for r in results if r["reorder_urgency"] == "critical"),
                "mapped_products": len(mapped_products),
                "unmapped_products": len(unmapped),
                "unmapped_product_names": unmapped[:20],
            },
            "generated_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ingredient forecast failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/forecast/cold-start")
async def cold_start_forecast(
    product_name: str,
    category: str | None = None,
    price: float | None = None,
    description: str | None = None,
    days_ahead: int = 7,
    loader: DataLoader = Depends(get_data_loader),
):
    """Estimate demand for a NEW product with no sales history.

    Uses similar existing products (by category, price range, keywords) as
    demand proxies. Returns a conservative baseline + range that the LLM
    arbitrator can further refine with context signals.
    """
    try:
        loader.load_all_tables()

        # ── 1. Find similar products by multiple signals ─────────────────
        params = []

        # Combine product name words + category as search keywords
        name_words = [w.lower() for w in product_name.split() if len(w) > 2]
        if category:
            name_words.append(category.lower())

        keyword_clauses = []
        for word in name_words[:5]:
            keyword_clauses.append(
                f"LOWER(oi.title) LIKE LOWER('%' || ${len(params) + 1} || '%')"
            )
            params.append(word)

        # Build combined similarity query
        keyword_sql = " OR ".join(keyword_clauses) if keyword_clauses else "1=1"

        sql = f"""
        WITH daily_demand AS (
            SELECT
                oi.title AS item,
                CAST(to_timestamp(o.created)::DATE AS DATE) AS sale_date,
                SUM(oi.quantity) AS qty
            FROM fct_orders o
            JOIN fct_order_items oi ON o.id = oi.order_id
            WHERE o.created IS NOT NULL
              AND ({keyword_sql})
            GROUP BY 1, 2
        ),
        item_stats AS (
            SELECT
                item,
                AVG(qty) AS avg_daily,
                STDDEV(qty) AS std_daily,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY qty) AS p25,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY qty) AS p75,
                COUNT(*) AS active_days,
                MAX(sale_date) AS last_sale
            FROM daily_demand
            GROUP BY item
            HAVING COUNT(*) >= 5
        )
        SELECT * FROM item_stats
        ORDER BY avg_daily DESC
        LIMIT 20
        """
        similar_df = loader.query(sql, params if params else None)

        # Also try exact category match from dim_items if keywords found nothing
        if similar_df.empty and category:
            cat_sql = f"""
            WITH items_in_cat AS (
                SELECT i.title
                FROM dim_items i
                LEFT JOIN dim_taxonomy_terms t ON i.section_id = t.id
                WHERE LOWER(COALESCE(t.title, '')) LIKE LOWER('%' || $1 || '%')
                   OR LOWER(i.title) LIKE LOWER('%' || $1 || '%')
            ),
            daily_demand AS (
                SELECT
                    oi.title AS item,
                    CAST(to_timestamp(o.created)::DATE AS DATE) AS sale_date,
                    SUM(oi.quantity) AS qty
                FROM fct_orders o
                JOIN fct_order_items oi ON o.id = oi.order_id
                WHERE o.created IS NOT NULL
                  AND oi.title IN (SELECT title FROM items_in_cat)
                GROUP BY 1, 2
            )
            SELECT
                item,
                AVG(qty) AS avg_daily,
                STDDEV(qty) AS std_daily,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY qty) AS p25,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY qty) AS p75,
                COUNT(*) AS active_days
            FROM daily_demand
            GROUP BY item
            HAVING COUNT(*) >= 5
            ORDER BY avg_daily DESC
            LIMIT 20
            """
            similar_df = loader.query(cat_sql, [category])

        # ── 2. Compute cold-start estimate from similar products ─────────
        if similar_df.empty:
            # Ultimate fallback: use overall median across ALL products
            fallback_sql = """
            WITH daily_demand AS (
                SELECT
                    oi.title AS item,
                    CAST(to_timestamp(o.created)::DATE AS DATE) AS sale_date,
                    SUM(oi.quantity) AS qty
                FROM fct_orders o
                JOIN fct_order_items oi ON o.id = oi.order_id
                WHERE o.created IS NOT NULL
                GROUP BY 1, 2
            )
            SELECT
                'ALL_PRODUCTS' AS item,
                AVG(avg_d) AS avg_daily,
                STDDEV(avg_d) AS std_daily,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY avg_d) AS p25,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY avg_d) AS p75,
                COUNT(*) AS active_days
            FROM (
                SELECT item, AVG(qty) AS avg_d
                FROM daily_demand
                GROUP BY item
                HAVING COUNT(*) >= 5
            )
            """
            similar_df = loader.query(fallback_sql)
            similarity_method = "global_median"
        else:
            similarity_method = "keyword_match" if keyword_clauses else "category_match"

        # Weighted average (heavier weight on higher-volume similar products)
        avg_vals = similar_df["avg_daily"].astype(float)
        weights = avg_vals / avg_vals.sum() if avg_vals.sum() > 0 else None
        weighted_avg = float(np.average(avg_vals, weights=weights)) if weights is not None else float(avg_vals.mean())

        std_vals = similar_df["std_daily"].fillna(0).astype(float)
        avg_std = float(std_vals.mean())

        # Conservative: new products typically start at 60-80% of similar product demand
        cold_start_factor = 0.7
        estimated_daily = weighted_avg * cold_start_factor

        similar_items = []
        for _, row in similar_df.iterrows():
            similar_items.append({
                "item": str(row["item"]),
                "avg_daily_demand": round(float(row["avg_daily"]), 1),
                "active_days": int(row["active_days"]),
            })

        # ── 3. Generate per-day forecasts ────────────────────────────────
        from datetime import timedelta as td
        base_date = date.today() + td(days=1)

        forecasts = []
        for d in range(days_ahead):
            forecast_date = base_date + td(days=d)
            dow = forecast_date.weekday()
            # Simple weekday adjustment (weekends typically -20%, Fridays +10%)
            if dow in (5, 6):
                day_factor = 0.8
            elif dow == 4:
                day_factor = 1.1
            else:
                day_factor = 1.0

            pred = estimated_daily * day_factor
            forecasts.append({
                "date": forecast_date.isoformat(),
                "predicted_quantity": round(pred, 1),
                "lower_bound": round(pred * 0.6, 1),
                "upper_bound": round(pred * 1.5, 1),
                "confidence": "low",
                "model_source": "cold_start_estimate",
            })

        return {
            "product_name": product_name,
            "estimated_daily_demand": round(estimated_daily, 1),
            "demand_range": {
                "low": round(estimated_daily * 0.6, 1),
                "high": round(estimated_daily * 1.5, 1),
            },
            "confidence": "low",
            "cold_start_factor": cold_start_factor,
            "similarity_method": similarity_method,
            "similar_products_used": len(similar_items),
            "similar_products": similar_items[:10],
            "forecasts": forecasts,
            "recommendation": (
                f"New product with no sales history. Estimated ~{round(estimated_daily, 0):.0f} units/day "
                f"based on {len(similar_items)} similar products. Start conservative and adjust "
                f"after 1-2 weeks of actual sales data."
            ),
            "generated_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cold-start forecast failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
