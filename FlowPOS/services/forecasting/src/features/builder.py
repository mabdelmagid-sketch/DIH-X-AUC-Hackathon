"""Orchestrates all feature engineering into a single analysis-ready DataFrame."""

import logging

import pandas as pd
import numpy as np

from src.features.time_features import add_time_features, add_is_open_flag
from src.features.lag_features import add_lag_features, add_rolling_features
from src.features.external_features import add_weather_features, add_holiday_features
from src.features.promotion_features import add_promotion_features

logger = logging.getLogger(__name__)


def aggregate_daily_demand(orders_df: pd.DataFrame,
                           order_items_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fct_order_items to daily demand per (place_id, item_id).

    Joins order_items with orders to get place_id and date, then aggregates.

    Args:
        orders_df: Cleaned fct_orders with 'created_dt' datetime column.
        order_items_df: Cleaned fct_order_items.

    Returns:
        DataFrame with columns: date, place_id, item_id, quantity_sold, revenue
    """
    # Join order items with orders to get place_id and date
    items_with_orders = order_items_df.merge(
        orders_df[["id", "place_id", "created_dt"]],
        left_on="order_id",
        right_on="id",
        how="inner",
        suffixes=("", "_order"),
    )

    # Extract date from order timestamp
    items_with_orders["date"] = items_with_orders["created_dt"].dt.date

    # Aggregate daily demand
    daily = items_with_orders.groupby(["date", "place_id", "item_id"]).agg(
        quantity_sold=("quantity", "sum"),
        revenue=("cost", "sum"),
        order_count=("order_id", "nunique"),
    ).reset_index()

    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values(["place_id", "item_id", "date"]).reset_index(drop=True)

    logger.info(f"Aggregated daily demand: {len(daily)} rows, "
                f"{daily['place_id'].nunique()} stores, {daily['item_id'].nunique()} items")
    return daily


def create_complete_date_grid(daily_df: pd.DataFrame,
                              top_n_items: int = 50) -> pd.DataFrame:
    """Create a complete date grid filling missing dates with 0 demand.

    Focuses on top N items per store to keep the dataset manageable.

    Args:
        daily_df: Aggregated daily demand DataFrame.
        top_n_items: Number of top items per store to include.

    Returns:
        DataFrame with complete date coverage for each (store, item) pair.
    """
    # Identify top items per store by total quantity
    top_items = (
        daily_df.groupby(["place_id", "item_id"])["quantity_sold"]
        .sum()
        .reset_index()
        .sort_values(["place_id", "quantity_sold"], ascending=[True, False])
        .groupby("place_id")
        .head(top_n_items)
    )
    top_pairs = set(zip(top_items["place_id"], top_items["item_id"]))

    # Filter to top items
    daily_filtered = daily_df[
        daily_df.apply(lambda r: (r["place_id"], r["item_id"]) in top_pairs, axis=1)
    ].copy()

    # Create full date range
    min_date = daily_filtered["date"].min()
    max_date = daily_filtered["date"].max()
    all_dates = pd.date_range(min_date, max_date, freq="D")

    # Create complete grid
    grids = []
    for (pid, iid) in top_pairs:
        grid = pd.DataFrame({
            "date": all_dates,
            "place_id": pid,
            "item_id": iid,
        })
        grids.append(grid)

    full_grid = pd.concat(grids, ignore_index=True)

    # Merge with actual demand (left join fills missing with NaN)
    result = full_grid.merge(
        daily_filtered,
        on=["date", "place_id", "item_id"],
        how="left",
    )

    # Fill missing demand with 0
    result["quantity_sold"] = result["quantity_sold"].fillna(0)
    result["revenue"] = result["revenue"].fillna(0)
    result["order_count"] = result["order_count"].fillna(0)

    logger.info(f"Complete date grid: {len(result)} rows "
                f"({len(top_pairs)} store-item pairs x {len(all_dates)} days)")
    return result.sort_values(["place_id", "item_id", "date"]).reset_index(drop=True)


def build_features(tables: dict, top_n_items: int = 50) -> pd.DataFrame:
    """Build the complete feature matrix from cleaned tables.

    This is the main orchestration function that:
    1. Aggregates daily demand
    2. Creates complete date grid
    3. Joins dimension tables
    4. Adds all feature groups (time, lag, weather, holidays, promotions)

    Args:
        tables: Dict with cleaned DataFrames (fct_orders, fct_order_items,
                dim_items, dim_places, fct_campaigns).
        top_n_items: Number of top items per store to model.

    Returns:
        Complete feature matrix ready for modeling.
    """
    logger.info("Building feature matrix...")

    # Step 1: Aggregate daily demand
    daily = aggregate_daily_demand(tables["fct_orders"], tables["fct_order_items"])

    # Step 2: Create complete date grid with top items
    df = create_complete_date_grid(daily, top_n_items=top_n_items)

    # Step 3: Join item names and store info
    items = tables["dim_items"][["id", "title", "price", "type", "section_id"]].rename(
        columns={"id": "item_id", "title": "item_name", "price": "item_price",
                 "type": "item_type"}
    )
    df = df.merge(items.drop_duplicates(subset=["item_id"]),
                  on="item_id", how="left")

    places = tables["dim_places"][["id", "title"]].rename(
        columns={"id": "place_id", "title": "store_name"}
    )
    df = df.merge(places.drop_duplicates(subset=["place_id"]),
                  on="place_id", how="left")

    # Step 4: Add time features
    df = add_time_features(df, date_col="date")

    # Step 5: Add is_open flag
    df = add_is_open_flag(df, tables["dim_places"],
                          date_col="date", place_col="place_id")

    # Step 6: Add holiday features
    df = add_holiday_features(df, date_col="date")

    # Step 7: Add weather features
    try:
        df = add_weather_features(df, date_col="date")
    except Exception as e:
        logger.warning(f"Weather feature fetch failed: {e}. Skipping weather.")
        df["temperature_max"] = np.nan
        df["temperature_min"] = np.nan
        df["precipitation_mm"] = np.nan
        df["is_rainy"] = 0

    # Step 8: Add promotion features
    df = add_promotion_features(df, tables["fct_campaigns"],
                                date_col="date", place_col="place_id")

    # Step 9: Add lag and rolling features (must be after complete grid)
    df = add_lag_features(df)
    df = add_rolling_features(df)

    logger.info(f"Feature matrix complete: {df.shape}")
    return df


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    from src.data.loader import load_key_tables
    from src.data.cleaner import clean_all

    tables = load_key_tables()
    tables = clean_all(tables)
    features = build_features(tables, top_n_items=30)
    print(f"Feature matrix shape: {features.shape}")
    print(f"Columns: {list(features.columns)}")
