"""
Data endpoints for FlowPOS Forecasting API.
"""
from fastapi import APIRouter, HTTPException, Depends
import pandas as pd
import json

from ..data.loader import DataLoader
from .dependencies import get_data_loader

router = APIRouter(tags=["data"])


def _df_to_records(df: pd.DataFrame) -> list:
    """Convert DataFrame to list of dicts, handling NaN -> null safely."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


@router.get("/data/tables")
async def list_tables(loader: DataLoader = Depends(get_data_loader)):
    """List available data tables."""
    try:
        loader.load_all_tables()
        loaded = loader.list_tables()
        return {
            "tables": [
                {"name": name, "rows": loader.get_table_info(name)["row_count"]}
                for name in loaded
            ],
            "count": len(loaded)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/inventory")
async def get_inventory_status(
    limit: int = 200,
    loader: DataLoader = Depends(get_data_loader)
):
    """Get current inventory status."""
    try:
        loader.load_all_tables()
        inventory = loader.get_inventory_status()

        low_stock_count = 0
        if "quantity" in inventory.columns and "threshold" in inventory.columns:
            mask = inventory["quantity"].notnull() & inventory["threshold"].notnull()
            filtered = inventory[mask]
            low_stock_count = int((filtered["quantity"] < filtered["threshold"]).sum())

        return {
            "items": _df_to_records(inventory.head(limit)),
            "total_items": len(inventory),
            "low_stock_count": low_stock_count,
            "expiring_soon_count": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/sales")
async def get_daily_sales(
    limit: int = 1000,
    loader: DataLoader = Depends(get_data_loader)
):
    """Get daily sales data."""
    try:
        loader.load_all_tables()
        sales = loader.get_daily_sales()

        return {
            "sales": _df_to_records(sales.head(limit)),
            "total_records": len(sales),
            "date_range": {
                "min": str(sales["date"].min()) if len(sales) > 0 else None,
                "max": str(sales["date"].max()) if len(sales) > 0 else None
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/menu")
async def get_menu_items(
    limit: int = 100,
    loader: DataLoader = Depends(get_data_loader)
):
    """Get menu items with ingredients."""
    try:
        loader.load_all_tables()
        menu = loader.get_menu_with_ingredients()

        return {
            "items": _df_to_records(menu.head(limit)),
            "total": len(menu)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/places")
async def list_places(loader: DataLoader = Depends(get_data_loader)):
    """List restaurants/places that have order data, sorted by order count."""
    try:
        loader.load_all_tables()
        sql = """
        SELECT p.id, p.title, COUNT(DISTINCT o.id) AS order_count
        FROM dim_places p
        JOIN fct_orders o ON o.place_id = p.id
        GROUP BY p.id, p.title
        ORDER BY order_count DESC
        """
        df = loader.query(sql)
        return {
            "places": _df_to_records(df),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/query")
async def run_query(
    sql: str,
    limit: int = 100,
    loader: DataLoader = Depends(get_data_loader)
):
    """Run an arbitrary SQL query (read-only)."""
    try:
        loader.load_all_tables()

        # Block destructive operations
        sql_upper = sql.strip().upper()
        blocked = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE"]
        for kw in blocked:
            if sql_upper.startswith(kw):
                raise HTTPException(status_code=400, detail=f"Destructive SQL ({kw}) not allowed")

        df = loader.query(sql)

        return {
            "data": _df_to_records(df.head(limit)),
            "total_rows": len(df),
            "columns": list(df.columns)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
