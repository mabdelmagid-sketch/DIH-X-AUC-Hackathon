"""
Function-calling tool definitions and executor for FlowPOS LLM.

Defines the tools the LLM can call to query real data, and provides
an executor that maps tool names to actual data queries.
"""
import asyncio
import json
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# Tool definitions in OpenAI function-calling format
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_inventory",
            "description": "Get current stock levels for inventory items. Can filter by place (location) or category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "place_id": {
                        "type": "integer",
                        "description": "Filter by place/location ID"
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by stock category name"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max rows to return (default 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_history",
            "description": "Get historical daily sales data for a specific item or all items. Returns date, quantity sold, and revenue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Item name to filter (partial match supported)"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of recent days to include (default 30)",
                        "default": 30
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": "Get demand forecast predictions for items. Requires a trained model.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Specific item to forecast (optional, forecasts all if omitted)"
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days to forecast ahead (default 7)",
                        "default": 7
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock",
            "description": "Get items that are below their reorder threshold. Returns items sorted by urgency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "place_id": {
                        "type": "integer",
                        "description": "Filter by place/location ID"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_sellers",
            "description": "Get the best-selling items by quantity or revenue over a time period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of recent days to analyze (default 30)",
                        "default": 30
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of top items to return (default 10)",
                        "default": 10
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["quantity", "revenue"],
                        "description": "Sort by total quantity or revenue (default quantity)",
                        "default": "quantity"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_bom",
            "description": "Get the bill of materials (recipe/ingredients) for a menu item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "menu_item": {
                        "type": "string",
                        "description": "Menu item name to look up (partial match supported)"
                    }
                },
                "required": ["menu_item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Run a custom SQL query against the loaded data tables. Available tables: dim_items, dim_menu_items, dim_bill_of_materials, dim_places, dim_stock_categories, dim_skus, dim_users, dim_campaigns, dim_add_ons, dim_menu_item_add_ons, dim_taxonomy_terms, dim_bonus_codes, dim_inventory_reports, fct_orders, fct_order_items, fct_cash_balances, fct_campaigns, fct_invoice_items, fct_bonus_codes, most_ordered. All timestamps are UNIX integers (use to_timestamp to convert). Currency is DKK.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL query to execute (DuckDB SQL syntax)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_expiring_items",
            "description": "Get items that are approaching expiry based on shelf life estimates. Sorted by days remaining.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Show items expiring within this many days (default 7)",
                        "default": 7
                    },
                    "place_id": {
                        "type": "integer",
                        "description": "Filter by place/location ID"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_context_signals",
            "description": "Get real-time environmental context (weather forecast, holidays, daylight, Danish retail calendar, payday proximity, severe weather alerts) for Copenhagen. Use this BEFORE deciding inventory strategy to understand external factors affecting demand. Returns a recommendation_bias suggesting whether to prioritize waste reduction or stockout prevention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Target date in YYYY-MM-DD format. Defaults to today."
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days to look ahead for weather outlook (default 3, max 16)",
                        "default": 3
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_new_product",
            "description": "Estimate demand for a NEW product with NO sales history (cold-start). Finds similar existing products by keywords and category, then returns a conservative demand estimate. Use this when asked about new menu items, seasonal specials, or items that haven't been sold before.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "Name of the new product"
                    },
                    "category": {
                        "type": "string",
                        "description": "Product category (e.g. 'burger', 'drink', 'dessert')"
                    },
                    "price": {
                        "type": "number",
                        "description": "Product price (helps find similar-priced items)"
                    }
                },
                "required": ["product_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_dual_forecast",
            "description": "Get demand forecasts from the 3-model ensemble: XGBoost Balanced, XGBoost Waste-Optimized, and LSTM (RNN). Returns all model predictions side by side. The ensemble_prediction is the median (majority vote). Use context_signals and item characteristics to decide the final recommendation per item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Item name filter (partial match). Omit for all items."
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Days to forecast (default 7)",
                        "default": 7
                    },
                    "place_id": {
                        "type": "integer",
                        "description": "Filter by store/place ID"
                    }
                },
                "required": []
            }
        }
    }
]


class ToolExecutor:
    """Executes tool calls against the data layer."""

    def __init__(self, data_loader, forecaster=None):
        self.loader = data_loader
        self.forecaster = forecaster
        self._tables_loaded = False

    def _ensure_tables(self):
        """Lazy-load tables once."""
        if not self._tables_loaded:
            self.loader.load_all_tables()
            self._tables_loaded = True

    def execute(self, tool_name: str, arguments: dict) -> str:
        """Execute a sync tool call and return the result as a string."""
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
            return handler(**arguments)
        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_name}")
            return json.dumps({"error": str(e)})

    async def execute_async(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call, awaiting async handlers if needed."""
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

            result = handler(**arguments)

            # Await if the handler returned a coroutine
            if asyncio.iscoroutine(result):
                result = await result

            return result
        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_name}")
            return json.dumps({"error": str(e)})

    def _tool_query_inventory(
        self,
        place_id: Optional[int] = None,
        category: Optional[str] = None,
        limit: int = 50
    ) -> str:
        self._ensure_tables()
        where_clauses = []
        params = []

        if place_id is not None:
            where_clauses.append(f"i.place_id = ${len(params) + 1}")
            params.append(place_id)
        if category:
            where_clauses.append(f"LOWER(sc.title) LIKE LOWER('%' || ${len(params) + 1} || '%')")
            params.append(category)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
        SELECT
            i.title, sk.quantity, sk.unit, sk.low_stock_threshold as threshold,
            sc.title as category
        FROM dim_items i
        LEFT JOIN dim_skus sk ON sk.item_id = i.id
        LEFT JOIN dim_stock_categories sc ON sk.stock_category_id = sc.id
        {where_sql}
        ORDER BY i.title
        LIMIT {int(limit)}
        """
        df = self.loader.query(sql, params if params else None)
        return df.to_json(orient="records", date_format="iso")

    def _tool_get_sales_history(
        self,
        item_name: Optional[str] = None,
        days: int = 30
    ) -> str:
        self._ensure_tables()
        params = []
        item_filter = ""

        if item_name:
            item_filter = f"AND LOWER(oi.title) LIKE LOWER('%' || ${len(params) + 1} || '%')"
            params.append(item_name)

        sql = f"""
        SELECT
            DATE_TRUNC('day', to_timestamp(o.created)) as date,
            oi.title as item,
            SUM(oi.quantity) as qty_sold,
            ROUND(SUM(oi.quantity * oi.price), 2) as revenue
        FROM fct_orders o
        JOIN fct_order_items oi ON o.id = oi.order_id
        WHERE o.created IS NOT NULL
          AND to_timestamp(o.created) >= CURRENT_DATE - INTERVAL '{int(days)}' DAY
          {item_filter}
        GROUP BY 1, 2
        ORDER BY 1 DESC
        LIMIT 200
        """
        df = self.loader.query(sql, params if params else None)
        return df.to_json(orient="records", date_format="iso")

    def _tool_get_forecast(
        self,
        item_name: Optional[str] = None,
        days_ahead: int = 7
    ) -> str:
        if self.forecaster is None or self.forecaster.model is None:
            return json.dumps({"error": "No trained model available. Train the model first via /api/train."})

        from ..models.trainer import ModelTrainer
        trainer = ModelTrainer()
        try:
            forecasts = trainer.generate_forecasts(
                days_ahead=days_ahead,
                item_filter=item_name
            )
            return forecasts.head(50).to_json(orient="records", date_format="iso")
        except Exception as e:
            return json.dumps({"error": f"Forecast failed: {str(e)}"})

    def _tool_get_low_stock(self, place_id: Optional[int] = None) -> str:
        self._ensure_tables()
        params = []
        place_filter = ""

        if place_id is not None:
            place_filter = f"AND i.place_id = ${len(params) + 1}"
            params.append(place_id)

        sql = f"""
        SELECT
            i.title, sk.quantity, sk.low_stock_threshold as threshold, sk.unit,
            sc.title as category,
            CASE
                WHEN sk.low_stock_threshold > 0 THEN ROUND(sk.quantity / sk.low_stock_threshold, 2)
                ELSE NULL
            END as stock_ratio
        FROM dim_items i
        JOIN dim_skus sk ON sk.item_id = i.id
        LEFT JOIN dim_stock_categories sc ON sk.stock_category_id = sc.id
        WHERE sk.low_stock_threshold > 0 AND sk.quantity <= sk.low_stock_threshold
          {place_filter}
        ORDER BY stock_ratio ASC
        LIMIT 50
        """
        df = self.loader.query(sql, params if params else None)
        return df.to_json(orient="records", date_format="iso")

    def _tool_get_top_sellers(
        self,
        days: int = 30,
        limit: int = 10,
        sort_by: str = "quantity"
    ) -> str:
        self._ensure_tables()
        order_col = "total_qty" if sort_by == "quantity" else "total_revenue"

        sql = f"""
        SELECT
            oi.title as item,
            SUM(oi.quantity) as total_qty,
            ROUND(SUM(oi.quantity * oi.price), 2) as total_revenue,
            COUNT(DISTINCT o.id) as order_count
        FROM fct_orders o
        JOIN fct_order_items oi ON o.id = oi.order_id
        WHERE o.created IS NOT NULL
          AND to_timestamp(o.created) >= CURRENT_DATE - INTERVAL '{int(days)}' DAY
        GROUP BY oi.title
        ORDER BY {order_col} DESC
        LIMIT {int(limit)}
        """
        df = self.loader.query(sql)
        return df.to_json(orient="records", date_format="iso")

    def _tool_get_bom(self, menu_item: str) -> str:
        self._ensure_tables()
        sql = """
        SELECT
            COALESCE(pi.title, parent_sk.title) as menu_item,
            pi.price as menu_price,
            child_sk.title as ingredient,
            b.quantity as ingredient_qty,
            child_sk.unit,
            child_sk.quantity as stock_on_hand,
            child_sk.low_stock_threshold as threshold
        FROM dim_bill_of_materials b
        JOIN dim_skus parent_sk ON b.parent_sku_id = parent_sk.id
        JOIN dim_skus child_sk ON b.sku_id = child_sk.id
        LEFT JOIN dim_items pi ON parent_sk.item_id = pi.id
        WHERE LOWER(COALESCE(pi.title, parent_sk.title)) LIKE LOWER('%' || $1 || '%')
        ORDER BY parent_sk.title, child_sk.title
        """
        df = self.loader.query(sql, [menu_item])
        if df.empty:
            return json.dumps({"message": f"No bill of materials found for '{menu_item}'. BOM data may be sparse."})
        return df.to_json(orient="records", date_format="iso")

    def _tool_run_sql(self, query: str) -> str:
        self._ensure_tables()

        # Basic safety: block destructive operations
        query_upper = query.strip().upper()
        blocked = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE"]
        for kw in blocked:
            if query_upper.startswith(kw):
                return json.dumps({"error": f"Destructive SQL operations ({kw}) are not allowed."})

        df = self.loader.query(query)
        # Limit large results
        if len(df) > 100:
            return df.head(100).to_json(orient="records", date_format="iso") + \
                f'\n[Showing 100 of {len(df)} rows]'
        return df.to_json(orient="records", date_format="iso")

    def _tool_get_expiring_items(
        self,
        days: int = 7,
        place_id: Optional[int] = None
    ) -> str:
        self._ensure_tables()
        params = []
        place_filter = ""

        if place_id is not None:
            place_filter = f"AND i.place_id = ${len(params) + 1}"
            params.append(place_id)

        sql = f"""
        WITH daily_sales AS (
            SELECT
                oi.title,
                SUM(oi.quantity) / COUNT(DISTINCT DATE_TRUNC('day', to_timestamp(o.created))) as avg_daily_sales
            FROM fct_orders o
            JOIN fct_order_items oi ON o.id = oi.order_id
            WHERE o.created IS NOT NULL
            GROUP BY oi.title
        )
        SELECT
            i.title,
            sk.quantity as stock,
            sk.unit,
            sc.title as category,
            ds.avg_daily_sales,
            CASE
                WHEN ds.avg_daily_sales > 0 THEN ROUND(sk.quantity / ds.avg_daily_sales, 1)
                ELSE NULL
            END as days_of_stock
        FROM dim_items i
        JOIN dim_skus sk ON sk.item_id = i.id
        LEFT JOIN dim_stock_categories sc ON sk.stock_category_id = sc.id
        LEFT JOIN daily_sales ds ON LOWER(i.title) = LOWER(ds.title)
        WHERE sk.quantity > 0
          AND ds.avg_daily_sales > 0
          {place_filter}
        ORDER BY days_of_stock ASC
        LIMIT 30
        """
        df = self.loader.query(sql, params if params else None)
        return df.to_json(orient="records", date_format="iso")

    # ------------------------------------------------------------------
    # Cold-start estimation for new products
    # ------------------------------------------------------------------

    def _tool_estimate_new_product(
        self,
        product_name: str,
        category: Optional[str] = None,
        price: Optional[float] = None,
    ) -> str:
        """Find similar products and estimate demand for a new item with no history."""
        self._ensure_tables()
        import numpy as np

        # Find similar products by keywords from the product name
        name_words = [w.lower() for w in product_name.split() if len(w) > 2]
        params = []
        keyword_clauses = []
        for word in name_words[:5]:
            keyword_clauses.append(
                f"LOWER(oi.title) LIKE LOWER('%' || ${len(params) + 1} || '%')"
            )
            params.append(word)

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
        )
        SELECT
            item,
            ROUND(AVG(qty), 1) AS avg_daily,
            ROUND(STDDEV(qty), 1) AS std_daily,
            COUNT(*) AS active_days
        FROM daily_demand
        GROUP BY item
        HAVING COUNT(*) >= 5
        ORDER BY avg_daily DESC
        LIMIT 15
        """
        similar_df = self.loader.query(sql, params if params else None)

        if similar_df.empty:
            # Fallback: global median
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
                item,
                ROUND(AVG(qty), 1) AS avg_daily,
                COUNT(*) AS active_days
            FROM daily_demand
            GROUP BY item
            HAVING COUNT(*) >= 10
            ORDER BY avg_daily DESC
            LIMIT 10
            """
            similar_df = self.loader.query(fallback_sql)
            method = "global_top_products"
        else:
            method = "keyword_similarity"

        similar_items = []
        for _, row in similar_df.iterrows():
            similar_items.append({
                "item": str(row["item"]),
                "avg_daily_demand": float(row["avg_daily"]),
                "active_days": int(row["active_days"]),
            })

        avg_demand = float(similar_df["avg_daily"].mean()) if not similar_df.empty else 5.0
        estimated = round(avg_demand * 0.7, 1)  # 70% conservative factor

        result = {
            "new_product": product_name,
            "estimated_daily_demand": estimated,
            "demand_range": {"low": round(estimated * 0.6, 1), "high": round(estimated * 1.5, 1)},
            "confidence": "low",
            "method": method,
            "similar_products": similar_items[:10],
            "note": (
                f"Cold-start estimate based on {len(similar_items)} similar products. "
                f"New products typically achieve 60-80% of similar item demand initially. "
                f"Recommend ordering conservatively for first 1-2 weeks."
            ),
        }
        return json.dumps(result, default=str)

    # ------------------------------------------------------------------
    # Context-aware tools for dual-model arbitration
    # ------------------------------------------------------------------

    async def _tool_get_context_signals(
        self,
        date: Optional[str] = None,
        days_ahead: int = 3,
    ) -> str:
        """Fetch real-time environmental context for LLM arbitration."""
        from .context_signals import get_all_context_signals
        from datetime import date as date_type

        target = date_type.fromisoformat(date) if date else date_type.today()
        days_ahead = min(max(days_ahead, 1), 16)

        signals = await get_all_context_signals(target, days_ahead)
        return json.dumps(signals, default=str)

    def _tool_get_dual_forecast(
        self,
        item_name: Optional[str] = None,
        days_ahead: int = 7,
        place_id: Optional[int] = None,
    ) -> str:
        """Get forecasts from both models for comparison.

        Tries trained HybridForecaster/WasteOptimizedForecaster first.
        Falls back to SQL-based averages with shrink/buffer multipliers.
        """
        self._ensure_tables()

        # ── Try trained models first ──────────────────────────────────
        try:
            model_results = self._dual_forecast_trained_models(
                item_name, days_ahead, place_id
            )
            if model_results:
                return json.dumps(model_results, default=str)
        except Exception as e:
            logger.warning(f"Trained model prediction failed, using SQL fallback: {e}")

        # ── SQL-based fallback ────────────────────────────────────────
        return self._dual_forecast_sql_fallback(item_name, days_ahead, place_id)

    def _dual_forecast_trained_models(
        self,
        item_name: Optional[str] = None,
        days_ahead: int = 7,
        place_id: Optional[int] = None,
    ) -> list[dict]:
        """Use 3-model ensemble (XGBoost + LSTM) for predictions."""
        from ..models.model_service import load_trained_models, build_inference_features, load_rnn_model
        import numpy as np

        models = load_trained_models()
        if not models:
            return []

        # Fetch raw daily sales from DuckDB
        params = []
        filters = []
        if item_name:
            filters.append(f"LOWER(oi.title) LIKE LOWER('%' || ${len(params) + 1} || '%')")
            params.append(item_name)
        if place_id is not None:
            filters.append(f"o.place_id = ${len(params) + 1}")
            params.append(place_id)
        where = f"AND {' AND '.join(filters)}" if filters else ""

        sql = f"""
        SELECT
            oi.title as item,
            o.place_id as place_id,
            oi.title as item_id,
            DATE_TRUNC('day', to_timestamp(o.created))::DATE as date,
            SUM(oi.quantity) as quantity_sold
        FROM fct_orders o
        JOIN fct_order_items oi ON o.id = oi.order_id
        WHERE o.created IS NOT NULL
          AND to_timestamp(o.created) >= CURRENT_DATE - INTERVAL '90' DAY
          {where}
        GROUP BY 1, 2, 3, 4
        ORDER BY item, date
        """
        raw_df = self.loader.query(sql, params if params else None)
        if raw_df.empty:
            return []

        # Build features and predict
        import pandas as pd
        feature_df = build_inference_features(raw_df)
        if feature_df.empty:
            return []

        balanced_model = models.get("balanced")
        waste_model = models.get("waste_optimized")
        if not balanced_model:
            return []

        latest = feature_df.sort_values("date").groupby("item", observed=True).last().reset_index()

        try:
            balanced_preds = balanced_model.predict(latest, "quantity_sold")
            waste_preds = waste_model.predict(latest, "quantity_sold") if waste_model else balanced_preds * 0.85
        except Exception as e:
            logger.warning(f"Model predict() failed: {e}")
            return []

        # LSTM predictions
        rnn = load_rnn_model()
        lstm_preds: dict[str, float] = {}
        if rnn is not None:
            try:
                agg_sales = raw_df.groupby(["item", "date"], as_index=False)["quantity_sold"].sum()
                lstm_preds = rnn.predict_items(agg_sales)
            except Exception as e:
                logger.warning(f"LSTM prediction failed: {e}")

        results = []
        for i, (_, row) in enumerate(latest.iterrows()):
            item = str(row.get("item", ""))
            avg = float(row.get("rolling_mean_7d", row.get("quantity_sold", 0)))
            std = float(row.get("rolling_std_14d", row.get("rolling_std_7d", 0))) or 0
            cv = std / avg if avg > 0 else 0

            bp = float(balanced_preds.iloc[i]) if i < len(balanced_preds) else avg
            wp = float(waste_preds.iloc[i]) if i < len(waste_preds) else avg * 0.85
            lp = lstm_preds.get(item)
            safety = round(1.65 * std, 1)

            # Ensemble: median of available models
            votes = [bp, wp]
            if lp is not None:
                votes.append(lp)
            ensemble = float(np.median(votes))

            item_lower = item.lower()
            perishable_kw = ["salad", "juice", "shake", "fresh", "smoothie",
                             "sandwich", "bowl", "wrap", "sushi", "bread"]

            if cv > 1.0:
                risk = "high"
            elif cv > 0.5:
                risk = "medium"
            else:
                risk = "low"

            r = {
                "item": item,
                "avg_daily_demand": round(avg, 1),
                "demand_cv": round(cv, 3),
                "demand_risk": risk,
                "is_perishable": any(kw in item_lower for kw in perishable_kw),
                "forecast_xgboost_balanced": round(bp, 1),
                "forecast_waste_optimized": round(wp, 1),
                "forecast_stockout_optimized": round(bp * 1.20, 1),
                "ensemble_prediction": round(ensemble, 1),
                "safety_stock_units": safety,
                "model_source": "ensemble_3model" if lp is not None else "ensemble_2model",
            }
            if lp is not None:
                r["forecast_lstm"] = round(lp, 1)

            results.append(r)

        return results

    def _dual_forecast_sql_fallback(
        self,
        item_name: Optional[str] = None,
        days_ahead: int = 7,
        place_id: Optional[int] = None,
    ) -> str:
        """SQL-based average fallback when trained models aren't available."""
        params = []
        filters = []

        if item_name:
            filters.append(
                f"LOWER(oi.title) LIKE LOWER('%' || ${len(params) + 1} || '%')"
            )
            params.append(item_name)
        if place_id is not None:
            filters.append(f"o.place_id = ${len(params) + 1}")
            params.append(place_id)

        where = f"AND {' AND '.join(filters)}" if filters else ""

        sql = f"""
        WITH daily AS (
            SELECT
                oi.title as item,
                DATE_TRUNC('day', to_timestamp(o.created))::DATE as sale_date,
                SUM(oi.quantity) as qty
            FROM fct_orders o
            JOIN fct_order_items oi ON o.id = oi.order_id
            WHERE o.created IS NOT NULL
              AND to_timestamp(o.created) >= CURRENT_DATE - INTERVAL '60' DAY
              {where}
            GROUP BY 1, 2
        ),
        stats AS (
            SELECT
                item,
                AVG(qty) as avg_daily,
                STDDEV(qty) as std_daily,
                MAX(qty) as max_daily,
                MIN(qty) as min_daily,
                COUNT(*) as active_days,
                CASE WHEN AVG(qty) > 0
                     THEN STDDEV(qty) / AVG(qty)
                     ELSE 0
                END as cv
            FROM daily
            GROUP BY item
        )
        SELECT * FROM stats
        ORDER BY avg_daily DESC
        LIMIT 30
        """
        df = self.loader.query(sql, params if params else None)

        if df.empty:
            return json.dumps({"error": "No sales data found for the given filters."})

        results = []
        for _, row in df.iterrows():
            avg = float(row.get("avg_daily", 0))
            std = float(row.get("std_daily", 0))
            cv = float(row.get("cv", 0))

            safety_stock = round(1.65 * std, 1)

            item_lower = str(row.get("item", "")).lower()
            perishable_kw = ["salad", "juice", "shake", "fresh", "smoothie",
                             "sandwich", "bowl", "wrap", "sushi", "bread"]

            if cv > 1.0:
                risk = "high"
            elif cv > 0.5:
                risk = "medium"
            else:
                risk = "low"

            results.append({
                "item": row.get("item"),
                "avg_daily_demand": round(avg, 1),
                "demand_cv": round(cv, 3),
                "demand_risk": risk,
                "is_perishable": any(kw in item_lower for kw in perishable_kw),
                "forecast_waste_optimized": round(avg * 0.85, 1),
                "forecast_stockout_optimized": round(avg * 1.20, 1),
                "forecast_balanced": round(avg, 1),
                "safety_stock_units": safety_stock,
                "active_days_last_60": int(row.get("active_days", 0)),
                "model_source": "sql_average_fallback",
            })

        return json.dumps(results, default=str)
