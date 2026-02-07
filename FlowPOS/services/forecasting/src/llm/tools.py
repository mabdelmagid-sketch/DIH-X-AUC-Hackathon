"""
Function-calling tool definitions and executor for FlowPOS LLM.

Defines the tools the LLM can call to query real data, and provides
an executor that maps tool names to actual data queries.
"""
import json
from typing import Optional

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
        """Execute a tool call and return the result as a string."""
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
            result = handler(**arguments)
            return result
        except Exception as e:
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
