"""
Data Loader for FlowCast
Loads and cleans the hackathon CSV data
"""
import pandas as pd
import duckdb
from pathlib import Path
from typing import Optional
from datetime import datetime

from ..config import settings


class DataLoader:
    """Load and manage hackathon datasets"""

    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or settings.data_path
        self.conn = duckdb.connect(":memory:")
        self._tables_loaded = set()

    def load_csv(self, filename: str, table_name: Optional[str] = None) -> pd.DataFrame:
        """Load a CSV file and register it in DuckDB"""
        filepath = self.data_path / filename
        if not filepath.exists():
            # Try with .csv extension
            filepath = self.data_path / f"{filename}.csv"

        if not filepath.exists():
            raise FileNotFoundError(f"Could not find {filename} in {self.data_path}")

        df = pd.read_csv(filepath)

        # Register in DuckDB
        tbl_name = table_name or filepath.stem
        self.conn.register(tbl_name, df)
        self._tables_loaded.add(tbl_name)

        return df

    def load_all_tables(self) -> dict[str, pd.DataFrame]:
        """Load all CSV files in the data directory"""
        if self._tables_loaded:
            return {}  # Already loaded

        tables = {}

        for csv_file in self.data_path.glob("*.csv"):
            table_name = csv_file.stem
            try:
                tables[table_name] = self.load_csv(csv_file.name)
                print(f"  Loaded {table_name}: {len(tables[table_name]):,} rows")
            except Exception as e:
                print(f"  Failed to load {table_name}: {e}")

        return tables

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        """Run SQL query against loaded tables, with optional parameterized args."""
        if params:
            return self.conn.execute(sql, params).fetchdf()
        return self.conn.execute(sql).fetchdf()

    def convert_unix_timestamp(self, df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        """Convert UNIX timestamp columns to datetime"""
        df = df.copy()
        for col in columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], unit='s', errors='coerce')
        return df

    def get_orders_with_items(self) -> pd.DataFrame:
        """Join orders with order items for analysis"""
        sql = """
        SELECT
            o.*,
            oi.title as item_title,
            oi.quantity,
            oi.price as item_price,
            oi.cost as item_cost
        FROM fct_orders o
        LEFT JOIN fct_order_items oi ON o.id = oi.order_id
        """
        return self.query(sql)

    def get_inventory_status(self) -> pd.DataFrame:
        """Get current inventory with stock levels and thresholds"""
        sql = """
        SELECT
            i.id, i.title, i.price, i.status,
            sk.quantity, sk.low_stock_threshold as threshold, sk.unit,
            sc.title as category_name
        FROM dim_items i
        LEFT JOIN dim_skus sk ON sk.item_id = i.id
        LEFT JOIN dim_stock_categories sc ON sk.stock_category_id = sc.id
        """
        return self.query(sql)

    def get_menu_with_ingredients(self) -> pd.DataFrame:
        """Get composite SKUs with their bill of materials (ingredients)"""
        sql = """
        SELECT
            parent_sk.id as parent_sku_id,
            parent_sk.title as parent_title,
            pi.title as parent_item_title,
            pi.price as parent_price,
            child_sk.title as ingredient_title,
            b.quantity as ingredient_quantity,
            child_sk.quantity as stock_quantity,
            child_sk.unit,
            child_sk.low_stock_threshold as threshold
        FROM dim_bill_of_materials b
        JOIN dim_skus parent_sk ON b.parent_sku_id = parent_sk.id
        JOIN dim_skus child_sk ON b.sku_id = child_sk.id
        LEFT JOIN dim_items pi ON parent_sk.item_id = pi.id
        """
        return self.query(sql)

    def get_daily_sales(self) -> pd.DataFrame:
        """Aggregate sales by day for forecasting"""
        sql = """
        SELECT
            DATE_TRUNC('day', to_timestamp(o.created)) as date,
            oi.title as item_title,
            SUM(oi.quantity) as total_quantity,
            SUM(oi.quantity * oi.price) as total_revenue,
            COUNT(DISTINCT o.id) as order_count
        FROM fct_orders o
        JOIN fct_order_items oi ON o.id = oi.order_id
        WHERE o.created IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
        return self.query(sql)

    def get_table_info(self, table_name: str) -> dict:
        """Get schema info for a table"""
        if table_name not in self._tables_loaded:
            raise ValueError(f"Table {table_name} not loaded")

        df = self.conn.execute(f"DESCRIBE {table_name}").fetchdf()
        return {
            "columns": df.to_dict(orient="records"),
            "row_count": self.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        }

    def list_tables(self) -> list[str]:
        """List all loaded tables"""
        return list(self._tables_loaded)
