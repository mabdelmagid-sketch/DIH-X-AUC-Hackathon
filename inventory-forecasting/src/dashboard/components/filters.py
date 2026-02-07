"""Reusable Streamlit filter/selector widgets."""

import streamlit as st
import pandas as pd


def store_selector(df: pd.DataFrame, key: str = "store_select") -> list:
    """Multi-select widget for stores.

    Args:
        df: DataFrame with place_id and store_name columns.
        key: Unique key for the widget.

    Returns:
        List of selected place_ids.
    """
    stores = df[["place_id", "store_name"]].drop_duplicates().sort_values("store_name")
    store_map = dict(zip(stores["store_name"], stores["place_id"]))

    selected_names = st.multiselect(
        "Select Stores",
        options=list(store_map.keys()),
        default=list(store_map.keys()),
        key=key,
    )

    return [store_map[n] for n in selected_names]


def item_selector(df: pd.DataFrame, place_ids: list = None,
                  key: str = "item_select", max_items: int = 20) -> list:
    """Selector for items, optionally filtered by store.

    Args:
        df: DataFrame with item_id and item_name columns.
        place_ids: Optional list of place_ids to filter by.
        key: Unique key for the widget.
        max_items: Max number of items to show.

    Returns:
        List of selected item_ids.
    """
    filtered = df.copy()
    if place_ids:
        filtered = filtered[filtered["place_id"].isin(place_ids)]

    # Get top items by total demand
    top_items = (
        filtered.groupby(["item_id", "item_name"])["quantity_sold"]
        .sum()
        .reset_index()
        .sort_values("quantity_sold", ascending=False)
        .head(max_items)
    )

    item_map = dict(zip(top_items["item_name"], top_items["item_id"]))

    if not item_map:
        st.warning("No items found for the selected filters.")
        return []

    selected_names = st.multiselect(
        "Select Items",
        options=list(item_map.keys()),
        default=list(item_map.keys())[:5],
        key=key,
    )

    return [item_map[n] for n in selected_names]


def date_range_selector(df: pd.DataFrame,
                        key: str = "date_range") -> tuple:
    """Date range picker.

    Args:
        df: DataFrame with 'date' column.
        key: Unique key for the widget.

    Returns:
        Tuple of (start_date, end_date).
    """
    dates = pd.to_datetime(df["date"])
    min_date = dates.min().date()
    max_date = dates.max().date()

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start Date", value=min_date, min_value=min_date,
                               max_value=max_date, key=f"{key}_start")
    with col2:
        end = st.date_input("End Date", value=max_date, min_value=min_date,
                             max_value=max_date, key=f"{key}_end")

    return start, end


def granularity_selector(key: str = "granularity") -> str:
    """Selector for time granularity (daily/weekly/monthly).

    Returns:
        Selected granularity string.
    """
    return st.radio(
        "Time Granularity",
        options=["Daily", "Weekly", "Monthly"],
        horizontal=True,
        key=key,
    )


def apply_filters(df: pd.DataFrame, place_ids: list = None,
                  item_ids: list = None, start_date=None,
                  end_date=None) -> pd.DataFrame:
    """Apply all selected filters to a DataFrame.

    Args:
        df: DataFrame to filter.
        place_ids: Selected store IDs.
        item_ids: Selected item IDs.
        start_date: Start date filter.
        end_date: End date filter.

    Returns:
        Filtered DataFrame.
    """
    filtered = df.copy()

    if place_ids:
        filtered = filtered[filtered["place_id"].isin(place_ids)]
    if item_ids:
        filtered = filtered[filtered["item_id"].isin(item_ids)]
    if start_date:
        filtered = filtered[pd.to_datetime(filtered["date"]).dt.date >= start_date]
    if end_date:
        filtered = filtered[pd.to_datetime(filtered["date"]).dt.date <= end_date]

    return filtered
