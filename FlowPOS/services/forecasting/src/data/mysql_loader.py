"""
MySQL data loader for the Loving Loyalty production database.

This module connects to the real Loving Loyalty MySQL database and loads:
  - fct_orders        (WHERE status = 'Settled')
  - fct_order_items   (joined with fct_orders)
  - fct_payments      (joined with fct_orders)

Connection parameters are read exclusively from environment variables;
no credentials are ever hardcoded.

When the MySQL host is unreachable (e.g. during local development or CI),
the loader falls back to the CSV demo dataset located at data/demo/.

Environment variables required for live MySQL mode:
  MYSQL_HOST     — hostname or IP of the MySQL server
  MYSQL_PORT     — port (default: 3306)
  MYSQL_DB       — database name (e.g. "loving_loyalty")
  MYSQL_USER     — database user
  MYSQL_PASSWORD — database password

Optional:
  MYSQL_SSL_CA   — path to CA certificate file for TLS connections
  MYSQL_TIMEOUT  — connect/read timeout in seconds (default: 10)
  DEMO_DATA_PATH — override path to CSV demo directory (default: ./data/demo)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_REPO_ROOT   = Path(__file__).parent.parent.parent          # …/forecasting/
_DEMO_DIR    = _REPO_ROOT / "data" / "demo"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

# Only settled (paid) orders are used for demand forecasting.
# The WHERE status = 'Settled' filter matches the Loving Loyalty POS status enum.
_SQL_ORDERS = """
SELECT
    id,
    place_id,
    status,
    created,                                   -- UNIX timestamp (seconds)
    FROM_UNIXTIME(created) AS created_at,      -- human-readable datetime
    DATE(FROM_UNIXTIME(created))  AS sale_date, -- date only for daily aggregation
    total,
    tip,
    discount,
    tax
FROM fct_orders
WHERE status = 'Settled'
  AND created IS NOT NULL
ORDER BY created ASC
"""

# Order items joined to orders so we only get items for settled orders.
# UNIX timestamp comes from fct_orders.created (fct_order_items has no own timestamp).
_SQL_ORDER_ITEMS = """
SELECT
    oi.id             AS order_item_id,
    oi.order_id,
    oi.item_id,
    oi.title          AS item_title,
    oi.quantity,
    oi.price,
    oi.cost,
    oi.discount       AS item_discount,
    o.place_id,
    o.created         AS order_created_unix,       -- UNIX timestamp (seconds)
    FROM_UNIXTIME(o.created) AS order_created_at,  -- datetime
    DATE(FROM_UNIXTIME(o.created)) AS sale_date     -- date for daily aggregation
FROM fct_order_items oi
INNER JOIN fct_orders o ON o.id = oi.order_id
WHERE o.status = 'Settled'
  AND o.created IS NOT NULL
  AND oi.quantity > 0
ORDER BY o.created ASC, oi.id ASC
"""

# Payments joined to settled orders.
_SQL_PAYMENTS = """
SELECT
    p.id              AS payment_id,
    p.order_id,
    p.method,
    p.amount,
    p.tip,
    p.created         AS payment_created_unix,     -- UNIX timestamp (seconds)
    FROM_UNIXTIME(p.created) AS payment_created_at,
    o.place_id,
    o.status          AS order_status
FROM fct_payments p
INNER JOIN fct_orders o ON o.id = p.order_id
WHERE o.status = 'Settled'
  AND o.created IS NOT NULL
ORDER BY p.created ASC
"""


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def _build_connection():
    """Build a mysql-connector-python or PyMySQL connection from env vars.

    Tries mysql.connector first (preferred), falls back to pymysql.
    Raises ImportError if neither is available (install via requirements).
    Raises EnvironmentError if MYSQL_HOST is not set.
    """
    host     = os.environ.get("MYSQL_HOST", "")
    port     = int(os.environ.get("MYSQL_PORT", "3306"))
    database = os.environ.get("MYSQL_DB", "")
    user     = os.environ.get("MYSQL_USER", "")
    password = os.environ.get("MYSQL_PASSWORD", "")
    ssl_ca   = os.environ.get("MYSQL_SSL_CA", "")
    timeout  = int(os.environ.get("MYSQL_TIMEOUT", "10"))

    if not host:
        raise EnvironmentError(
            "MYSQL_HOST environment variable is not set. "
            "Set MYSQL_HOST, MYSQL_PORT, MYSQL_DB, MYSQL_USER, MYSQL_PASSWORD "
            "to connect to the Loving Loyalty production database. "
            "Leave unset to use CSV demo data fallback."
        )

    connect_kwargs: dict = {
        "host":             host,
        "port":             port,
        "database":         database,
        "user":             user,
        "password":         password,
        "connect_timeout":  timeout,
    }

    if ssl_ca:
        connect_kwargs["ssl_ca"] = ssl_ca
        connect_kwargs["ssl_verify_cert"] = True

    # Try mysql-connector-python first
    try:
        import mysql.connector  # type: ignore
        logger.info(f"Connecting to MySQL at {host}:{port}/{database} via mysql-connector-python")
        return mysql.connector.connect(**connect_kwargs)
    except ImportError:
        pass

    # Fallback to PyMySQL
    try:
        import pymysql  # type: ignore
        logger.info(f"Connecting to MySQL at {host}:{port}/{database} via PyMySQL")
        return pymysql.connect(**connect_kwargs)
    except ImportError:
        pass

    raise ImportError(
        "No MySQL driver found. Install one of: "
        "mysql-connector-python, PyMySQL"
    )


# ---------------------------------------------------------------------------
# Public loader class
# ---------------------------------------------------------------------------

class MySQLLoader:
    """Load Loving Loyalty production data from MySQL with CSV demo fallback.

    Usage
    -----
    loader = MySQLLoader()

    # Full order history (settled only)
    orders_df = loader.load_orders()

    # Order items joined with orders
    items_df = loader.load_order_items()

    # Payments
    payments_df = loader.load_payments()

    # Pre-aggregated daily demand ready for the forecasting model
    daily_df = loader.load_daily_demand()

    All UNIX timestamps are converted to pandas datetime columns automatically.
    """

    def __init__(self, demo_data_path: Optional[Path] = None):
        """Initialise the loader.

        Args:
            demo_data_path: Path to the CSV demo directory.
                            Defaults to DEMO_DATA_PATH env var or data/demo/.
        """
        env_path = os.environ.get("DEMO_DATA_PATH", "")
        self.demo_dir = (
            Path(demo_data_path)
            if demo_data_path
            else (Path(env_path) if env_path else _DEMO_DIR)
        )
        self._mysql_available: Optional[bool] = None  # lazy-checked on first query

    # ------------------------------------------------------------------
    # Connectivity check
    # ------------------------------------------------------------------

    def is_mysql_available(self) -> bool:
        """Return True if MySQL is reachable, False otherwise (cached after first call)."""
        if self._mysql_available is not None:
            return self._mysql_available

        try:
            conn = _build_connection()
            conn.close()
            self._mysql_available = True
            logger.info("MySQL connection test: OK")
        except (EnvironmentError, ImportError, Exception) as e:
            logger.warning(f"MySQL not available ({type(e).__name__}: {e}); will use CSV demo data")
            self._mysql_available = False

        return self._mysql_available

    # ------------------------------------------------------------------
    # Internal: execute SQL
    # ------------------------------------------------------------------

    def _query_mysql(self, sql: str) -> pd.DataFrame:
        """Run a SQL query against the Loving Loyalty MySQL database.

        Opens a new connection per call (stateless; safe for async workloads
        when called inside asyncio.to_thread).
        """
        conn = _build_connection()
        try:
            df = pd.read_sql(sql, conn)
        finally:
            conn.close()
        return df

    # ------------------------------------------------------------------
    # Internal: UNIX timestamp conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_unix_columns(df: pd.DataFrame, unix_cols: list[str]) -> pd.DataFrame:
        """Convert UNIX-second integer columns to pandas Timestamps in-place.

        The Loving Loyalty database stores all timestamps as UNIX epoch seconds
        (INTEGER). This matches the pattern in fct_orders.created.
        """
        df = df.copy()
        for col in unix_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], unit="s", errors="coerce")
                # Drop rows where conversion yielded NaT (corrupt timestamp)
                df = df.dropna(subset=[col])
        return df

    # ------------------------------------------------------------------
    # Public: load orders
    # ------------------------------------------------------------------

    def load_orders(self) -> pd.DataFrame:
        """Load settled orders from MySQL, or from CSV demo on failure.

        Returns
        -------
        DataFrame with columns:
            id, place_id, status, created (UNIX int), created_at (datetime),
            sale_date (date string), total, tip, discount, tax
        """
        if self.is_mysql_available():
            logger.info("Loading fct_orders from MySQL (status='Settled')")
            try:
                df = self._query_mysql(_SQL_ORDERS)
                # MySQL FROM_UNIXTIME returns strings via JDBC; parse them
                for dt_col in ["created_at", "sale_date"]:
                    if dt_col in df.columns:
                        df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
                logger.info(f"Loaded {len(df):,} settled orders from MySQL")
                return df
            except Exception as e:
                logger.error(f"MySQL orders load failed: {e}; falling back to CSV demo")

        return self._load_orders_from_csv()

    def _load_orders_from_csv(self) -> pd.DataFrame:
        """Load orders from the CSV demo dataset."""
        path = self.demo_dir / "fct_orders.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"Demo CSV not found at {path}. "
                f"Set DEMO_DATA_PATH or ensure data/demo/ is populated."
            )
        logger.info(f"Loading fct_orders from CSV demo: {path}")
        df = pd.read_csv(path, low_memory=False)
        df = self._convert_unix_columns(df, ["created"])
        df = df.rename(columns={"created": "created_at"})
        df["sale_date"] = df["created_at"].dt.normalize()
        # Demo data may not have a status column; treat all rows as Settled
        if "status" not in df.columns:
            df["status"] = "Settled"
        else:
            df = df[df["status"] == "Settled"].copy()
        logger.info(f"Loaded {len(df):,} orders from CSV demo")
        return df

    # ------------------------------------------------------------------
    # Public: load order items
    # ------------------------------------------------------------------

    def load_order_items(self) -> pd.DataFrame:
        """Load order items joined with settled orders.

        Returns
        -------
        DataFrame with columns:
            order_item_id, order_id, item_id, item_title, quantity, price,
            cost, item_discount, place_id, order_created_unix (int),
            order_created_at (datetime), sale_date (datetime)
        """
        if self.is_mysql_available():
            logger.info("Loading fct_order_items from MySQL (settled orders only)")
            try:
                df = self._query_mysql(_SQL_ORDER_ITEMS)
                for dt_col in ["order_created_at", "sale_date"]:
                    if dt_col in df.columns:
                        df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
                logger.info(f"Loaded {len(df):,} order items from MySQL")
                return df
            except Exception as e:
                logger.error(f"MySQL order_items load failed: {e}; falling back to CSV demo")

        return self._load_order_items_from_csv()

    def _load_order_items_from_csv(self) -> pd.DataFrame:
        """Load order items and join with settled orders from CSV demo."""
        items_path  = self.demo_dir / "fct_order_items.csv"
        orders_path = self.demo_dir / "fct_orders.csv"

        if not items_path.exists():
            raise FileNotFoundError(f"Demo CSV not found: {items_path}")

        items_df = pd.read_csv(items_path, low_memory=False)

        if orders_path.exists():
            orders_df = pd.read_csv(orders_path, low_memory=False)
            # Convert UNIX timestamp
            orders_df = self._convert_unix_columns(orders_df, ["created"])
            orders_df = orders_df.rename(columns={"created": "order_created_at"})
            orders_df["sale_date"] = orders_df["order_created_at"].dt.normalize()
            if "status" not in orders_df.columns:
                orders_df["status"] = "Settled"
            settled = orders_df[orders_df["status"] == "Settled"][
                ["id", "place_id", "order_created_at", "sale_date"]
            ]
            df = items_df.merge(settled, left_on="order_id", right_on="id", how="inner")
        else:
            df = items_df.copy()
            df["order_created_at"] = pd.NaT
            df["sale_date"] = pd.NaT

        # Normalise column names
        if "title" in df.columns and "item_title" not in df.columns:
            df = df.rename(columns={"title": "item_title"})

        df = df[df["quantity"] > 0].copy() if "quantity" in df.columns else df

        logger.info(f"Loaded {len(df):,} order items from CSV demo")
        return df

    # ------------------------------------------------------------------
    # Public: load payments
    # ------------------------------------------------------------------

    def load_payments(self) -> pd.DataFrame:
        """Load payments joined with settled orders.

        Returns
        -------
        DataFrame with columns:
            payment_id, order_id, method, amount, tip,
            payment_created_unix (int), payment_created_at (datetime),
            place_id, order_status
        """
        if self.is_mysql_available():
            logger.info("Loading fct_payments from MySQL (settled orders only)")
            try:
                df = self._query_mysql(_SQL_PAYMENTS)
                for dt_col in ["payment_created_at"]:
                    if dt_col in df.columns:
                        df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
                logger.info(f"Loaded {len(df):,} payments from MySQL")
                return df
            except Exception as e:
                logger.error(f"MySQL payments load failed: {e}; falling back to CSV demo")

        return self._load_payments_from_csv()

    def _load_payments_from_csv(self) -> pd.DataFrame:
        """Load payments from CSV demo dataset."""
        # The demo dataset may not include fct_payments; return an empty frame if absent
        path = self.demo_dir / "fct_payments.csv"
        if not path.exists():
            logger.warning(f"fct_payments.csv not found at {path}; returning empty DataFrame")
            return pd.DataFrame(columns=[
                "payment_id", "order_id", "method", "amount", "tip",
                "payment_created_unix", "payment_created_at", "place_id", "order_status",
            ])
        df = pd.read_csv(path, low_memory=False)
        if "created" in df.columns:
            df = self._convert_unix_columns(df, ["created"])
            df = df.rename(columns={"created": "payment_created_at"})
        logger.info(f"Loaded {len(df):,} payments from CSV demo")
        return df

    # ------------------------------------------------------------------
    # Public: pre-aggregated daily demand (ready for the forecasting model)
    # ------------------------------------------------------------------

    def load_daily_demand(
        self,
        top_n: Optional[int] = None,
        place_id: Optional[int] = None,
    ) -> pd.DataFrame:
        """Return daily demand aggregated by (date, place_id, item_title).

        This is the primary input expected by `predict_multi_day()` and the
        autoresearch `evaluate.run_experiment()` pipeline.

        Args:
            top_n: If set, restrict to the top N items by total volume.
            place_id: If set, restrict to a single place.

        Returns
        -------
        DataFrame with columns: date, place_id, item, quantity_sold
        Sorted by (item, date).
        """
        items_df = self.load_order_items()

        if items_df.empty:
            return pd.DataFrame(columns=["date", "place_id", "item", "quantity_sold"])

        # Determine the item name column
        title_col = "item_title" if "item_title" in items_df.columns else (
            "title" if "title" in items_df.columns else None
        )
        if title_col is None:
            raise ValueError("Order items DataFrame has no 'item_title' or 'title' column")

        # Determine the date column
        date_col = None
        for candidate in ["sale_date", "order_created_at", "created_at"]:
            if candidate in items_df.columns:
                date_col = candidate
                break
        if date_col is None:
            raise ValueError("Order items DataFrame has no date column")

        items_df["_date"] = pd.to_datetime(items_df[date_col], errors="coerce").dt.normalize()
        items_df = items_df.dropna(subset=["_date"])
        items_df = items_df.rename(columns={title_col: "item"})

        qty_col = "quantity" if "quantity" in items_df.columns else "quantity_sold"

        group_cols = ["_date", "item"]
        if "place_id" in items_df.columns:
            group_cols = ["_date", "place_id", "item"]

        daily = (
            items_df.groupby(group_cols, observed=True)[qty_col]
            .sum()
            .reset_index()
            .rename(columns={"_date": "date", qty_col: "quantity_sold"})
        )

        if "place_id" not in daily.columns:
            daily["place_id"] = 0

        # Optional place filter
        if place_id is not None:
            daily = daily[daily["place_id"] == place_id].copy()

        # Optional top-N filter
        if top_n and top_n > 0:
            top_items = (
                daily.groupby("item", observed=True)["quantity_sold"]
                .sum()
                .nlargest(top_n)
                .index
            )
            daily = daily[daily["item"].isin(top_items)].copy()

        daily = daily.sort_values(["item", "date"]).reset_index(drop=True)

        logger.info(
            f"Daily demand: {len(daily):,} rows, "
            f"{daily['item'].nunique()} items, "
            f"{daily['place_id'].nunique()} places"
        )
        return daily

    # ------------------------------------------------------------------
    # Utility: data source status string (for health endpoint)
    # ------------------------------------------------------------------

    def data_source_status(self) -> str:
        """Return 'mysql_live', 'csv_demo', or 'unavailable'."""
        if self.is_mysql_available():
            return "mysql_live"
        if self.demo_dir.exists() and any(self.demo_dir.glob("*.csv")):
            return "csv_demo"
        return "unavailable"
