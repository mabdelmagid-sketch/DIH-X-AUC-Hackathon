"""
data_loader.py -- Loving Loyalty AI Suite, Pillar 1: Sales Forecasting

Responsible for loading raw transactional data and producing a complete
daily demand grid per (place_id, item_id) ready for feature engineering.

Supports two data sources, selected via the USE_MYSQL env var or explicit
``source`` argument:
  - "mysql"  : Production MySQL database (requires DB_* env vars)
  - "csv"    : Demo CSV files shipped with the repo (default)

All amounts are in DKK.  Timestamps are UNIX seconds and are converted to
UTC-aware datetimes before extracting the calendar date.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]  # services/forecasting/
_DEMO_DATA_DIR = _REPO_ROOT / "data" / "demo"


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class DataLoader:
    """Load daily demand data from MySQL (real) or CSV (demo).

    Args:
        source: "mysql" or "csv".  Defaults to the USE_MYSQL env var value
                ("1" / "true" => "mysql", anything else => "csv").
        demo_data_dir: Path override for CSV files.  Useful in tests.
        db_dsn: SQLAlchemy DSN string for MySQL.  Falls back to
                ``DB_DSN`` env var, then to building from individual
                DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME vars.
    """

    def __init__(
        self,
        source: Optional[str] = None,
        demo_data_dir: Optional[Path] = None,
        db_dsn: Optional[str] = None,
    ) -> None:
        if source is None:
            source = "mysql" if os.environ.get("USE_MYSQL", "").lower() in ("1", "true", "yes") else "csv"
        self.source = source
        self.demo_data_dir = demo_data_dir or _DEMO_DATA_DIR
        self._db_dsn = db_dsn or self._build_dsn()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load_daily_demand(self, top_n_items: int = 30) -> pd.DataFrame:
        """Return a complete date grid with daily demand per (place_id, item_id).

        The returned DataFrame has columns:
            date            datetime64[ns]   -- calendar day (midnight UTC)
            place_id        int              -- restaurant identifier
            item_id         int/object       -- menu item identifier
            item_title      str              -- human-readable item name
            item_price      float            -- unit price in DKK
            quantity_sold   float            -- units sold that day (0 if none)
            revenue         float            -- revenue that day in DKK

        Zero-filling is applied so every (place_id, item_id) pair has a
        continuous row for every calendar date in the full date range.

        Args:
            top_n_items: Number of highest-volume items per store to include.
                         Limits the output to the most commercially relevant
                         products and keeps memory usage predictable.

        Returns:
            Sorted DataFrame (place_id, item_id, date).
        """
        if self.source == "mysql":
            return self._load_from_mysql(top_n_items)
        return self._load_from_csv(top_n_items)

    # ------------------------------------------------------------------
    # CSV (demo) path
    # ------------------------------------------------------------------

    def _load_from_csv(self, top_n_items: int) -> pd.DataFrame:
        logger.info("Loading daily demand from CSV demo data at %s", self.demo_data_dir)

        orders = pd.read_csv(self.demo_data_dir / "fct_orders.csv", low_memory=False)
        order_items = pd.read_csv(self.demo_data_dir / "fct_order_items.csv", low_memory=False)
        dim_items = pd.read_csv(self.demo_data_dir / "dim_items.csv", low_memory=False)

        # Convert UNIX timestamp (seconds) to date
        orders["created_dt"] = pd.to_datetime(orders["created"], unit="s", errors="coerce")
        orders = orders.dropna(subset=["created_dt"])
        orders["date"] = orders["created_dt"].dt.normalize()

        # Filter: only Settled payments (status field if present)
        if "status" in orders.columns:
            orders = orders[orders["status"].str.lower() == "settled"].copy()

        # Join order items with orders
        merged = order_items.merge(
            orders[["id", "place_id", "date"]],
            left_on="order_id",
            right_on="id",
            how="inner",
            suffixes=("", "_order"),
        )

        # Aggregate daily demand per (place_id, item_id)
        daily = merged.groupby(["date", "place_id", "item_id"]).agg(
            quantity_sold=("quantity", "sum"),
            revenue=("cost", "sum"),
        ).reset_index()

        # Attach item metadata
        item_meta = (
            dim_items[["id", "title", "price"]]
            .drop_duplicates(subset=["id"])
            .rename(columns={"id": "item_id", "title": "item_title", "price": "item_price"})
        )
        daily = daily.merge(item_meta, on="item_id", how="left")
        daily["item_price"] = daily["item_price"].fillna(75.0)
        daily["item_title"] = daily["item_title"].fillna(daily["item_id"].astype(str))

        return self._build_complete_grid(daily, top_n_items)

    # ------------------------------------------------------------------
    # MySQL (production) path
    # ------------------------------------------------------------------

    def _load_from_mysql(self, top_n_items: int) -> pd.DataFrame:
        """Load from production MySQL database.

        Requires sqlalchemy + PyMySQL installed.
        The query mirrors the CSV logic: joins fct_orders (status=Settled)
        with fct_order_items and dim_items, then aggregates to daily demand.
        """
        try:
            from sqlalchemy import create_engine, text
        except ImportError as exc:
            raise ImportError("sqlalchemy is required for MySQL loading") from exc

        logger.info("Loading daily demand from MySQL (%s)", self._db_dsn.split("@")[-1])
        engine = create_engine(self._db_dsn)

        sql = text("""
            SELECT
                DATE(FROM_UNIXTIME(o.created))  AS date,
                o.place_id                       AS place_id,
                oi.item_id                       AS item_id,
                di.title                         AS item_title,
                COALESCE(di.price, 75.0)         AS item_price,
                SUM(oi.quantity)                 AS quantity_sold,
                SUM(oi.cost)                     AS revenue
            FROM fct_orders o
            JOIN fct_order_items oi ON oi.order_id = o.id
            LEFT JOIN dim_items di ON di.id = oi.item_id
            WHERE o.status = 'Settled'
              AND o.created IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5
            ORDER BY 1, 2, 3
        """)
        with engine.connect() as conn:
            daily = pd.read_sql(sql, conn, parse_dates=["date"])

        return self._build_complete_grid(daily, top_n_items)

    # ------------------------------------------------------------------
    # Shared helper: build complete date grid with zero-filling
    # ------------------------------------------------------------------

    def _build_complete_grid(self, daily: pd.DataFrame, top_n_items: int) -> pd.DataFrame:
        """Select top-N items per store, build complete date x (place, item) grid."""
        daily["date"] = pd.to_datetime(daily["date"])

        # Keep top_n_items per store by total volume
        top = (
            daily.groupby(["place_id", "item_id"])["quantity_sold"]
            .sum()
            .reset_index()
            .sort_values(["place_id", "quantity_sold"], ascending=[True, False])
            .groupby("place_id")
            .head(top_n_items)
        )
        top_pairs = set(zip(top["place_id"], top["item_id"]))

        daily = daily[
            daily.apply(lambda r: (r["place_id"], r["item_id"]) in top_pairs, axis=1)
        ].copy()

        min_date = daily["date"].min()
        max_date = daily["date"].max()
        all_dates = pd.date_range(min_date, max_date, freq="D")

        # Build empty grid
        grids = []
        for (pid, iid) in top_pairs:
            sub = daily[(daily["place_id"] == pid) & (daily["item_id"] == iid)]
            price = sub["item_price"].mode()
            price = float(price.iloc[0]) if len(price) > 0 else 75.0
            title = sub["item_title"].mode()
            title = str(title.iloc[0]) if len(title) > 0 else str(iid)
            grids.append(pd.DataFrame({
                "date": all_dates,
                "place_id": pid,
                "item_id": iid,
                "item_title": title,
                "item_price": price,
            }))

        full = pd.concat(grids, ignore_index=True)
        full = full.merge(
            daily[["date", "place_id", "item_id", "quantity_sold", "revenue"]],
            on=["date", "place_id", "item_id"],
            how="left",
        )
        full["quantity_sold"] = full["quantity_sold"].fillna(0.0)
        full["revenue"] = full["revenue"].fillna(0.0)

        full = full.sort_values(["place_id", "item_id", "date"]).reset_index(drop=True)
        logger.info(
            "Daily demand grid: %d rows, %d store-item pairs, %d days",
            len(full), len(top_pairs), len(all_dates),
        )
        return full

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build_dsn() -> str:
        dsn = os.environ.get("DB_DSN", "")
        if dsn:
            return dsn
        host = os.environ.get("DB_HOST", "localhost")
        port = os.environ.get("DB_PORT", "3306")
        user = os.environ.get("DB_USER", "root")
        password = os.environ.get("DB_PASSWORD", "")
        name = os.environ.get("DB_NAME", "flowpos")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"
