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
    """List restaurants/places that have tracked order data, sorted by total tracked orders."""
    try:
        loader.load_all_tables()
        sql = """
        SELECT p.id, p.title, SUM(m.order_count) AS order_count
        FROM dim_places p
        JOIN most_ordered m ON m.place_id = p.id
        GROUP BY p.id, p.title
        ORDER BY order_count DESC
        """
        df = loader.query(sql)
        return {
            "places": _df_to_records(df),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/products")
async def get_products_for_place(
    place_id: int,
    limit: int = 200,
    loader: DataLoader = Depends(get_data_loader),
):
    """Get products for a specific restaurant, ordered by popularity."""
    try:
        loader.load_all_tables()
        sql = """
        SELECT m.item_id AS id, m.item_name AS title,
               i.price, i.image, m.order_count
        FROM most_ordered m
        LEFT JOIN dim_items i ON m.item_id = i.id
        WHERE m.place_id = $1
          AND (i.status = 'Active' OR i.status IS NULL)
        ORDER BY m.order_count DESC
        LIMIT $2
        """
        df = loader.query(sql, [place_id, limit])
        return {"products": _df_to_records(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/orders")
async def get_orders(
    place_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    loader: DataLoader = Depends(get_data_loader),
):
    """Get orders with their items from the dataset."""
    try:
        loader.load_all_tables()

        # Build WHERE clauses
        conditions = []
        params = []
        idx = 1
        if place_id is not None:
            conditions.append(f"o.place_id = ${idx}")
            params.append(place_id)
            idx += 1
        if status is not None:
            conditions.append(f"o.status = ${idx}")
            params.append(status)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # Count total
        count_sql = f"SELECT COUNT(*) as cnt FROM fct_orders o {where}"
        total = int(loader.query(count_sql, params if params else None).iloc[0]["cnt"])

        # Fetch orders page
        params_page = params.copy()
        params_page.append(limit)
        params_page.append(offset)
        orders_sql = f"""
        SELECT o.id, o.code, o.status, o.type,
               o.total_amount, o.items_amount, o.discount_amount,
               o.payment_method, o.place_id, o.customer_name,
               o.created, o.channel,
               p.title as place_name
        FROM fct_orders o
        LEFT JOIN dim_places p ON o.place_id = p.id
        {where}
        ORDER BY o.created DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """
        orders_df = loader.query(orders_sql, params_page)

        if orders_df.empty:
            return {"orders": [], "total": total}

        # Fetch items for these orders
        order_ids = orders_df["id"].tolist()
        placeholders = ", ".join(str(int(oid)) for oid in order_ids)
        items_sql = f"""
        SELECT oi.order_id, oi.title, oi.quantity, oi.price
        FROM fct_order_items oi
        WHERE oi.order_id IN ({placeholders})
        """
        items_df = loader.query(items_sql)

        # Group items by order_id
        items_by_order: dict[int, list] = {}
        for _, row in items_df.iterrows():
            oid = int(row["order_id"])
            items_by_order.setdefault(oid, []).append({
                "title": row["title"],
                "quantity": int(row["quantity"]) if pd.notnull(row["quantity"]) else 1,
                "price": float(row["price"]) if pd.notnull(row["price"]) else 0,
            })

        # Build response
        orders_out = []
        for _, o in orders_df.iterrows():
            oid = int(o["id"])
            orders_out.append({
                "id": oid,
                "code": o["code"] if pd.notnull(o.get("code")) else None,
                "status": o["status"] if pd.notnull(o.get("status")) else "Unknown",
                "type": o["type"] if pd.notnull(o.get("type")) else None,
                "total_amount": float(o["total_amount"]) if pd.notnull(o.get("total_amount")) else 0,
                "items_amount": float(o["items_amount"]) if pd.notnull(o.get("items_amount")) else 0,
                "discount_amount": float(o["discount_amount"]) if pd.notnull(o.get("discount_amount")) else 0,
                "payment_method": o["payment_method"] if pd.notnull(o.get("payment_method")) else None,
                "customer_name": o["customer_name"] if pd.notnull(o.get("customer_name")) else None,
                "channel": o["channel"] if pd.notnull(o.get("channel")) else None,
                "place_name": o["place_name"] if pd.notnull(o.get("place_name")) else None,
                "created": int(o["created"]) if pd.notnull(o.get("created")) else None,
                "items": items_by_order.get(oid, []),
            })

        return {"orders": orders_out, "total": total}
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
