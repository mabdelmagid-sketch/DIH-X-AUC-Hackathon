"""Overview page: KPIs, demand trends, store comparison."""

import streamlit as st
import pandas as pd

from src.dashboard.components.charts import (
    demand_time_series, store_comparison_bar, top_items_chart, heatmap_day_hour,
)
from src.dashboard.components.filters import (
    store_selector, date_range_selector, apply_filters,
)


def render(df: pd.DataFrame):
    """Render the Overview page.

    Args:
        df: Feature DataFrame with all data.
    """
    st.header("Overview")

    # Filters in sidebar
    with st.sidebar:
        st.subheader("Filters")
        selected_stores = store_selector(df, key="overview_stores")
        start_date, end_date = date_range_selector(df, key="overview_dates")

    filtered = apply_filters(df, place_ids=selected_stores,
                              start_date=start_date, end_date=end_date)

    if filtered.empty:
        st.warning("No data for the selected filters.")
        return

    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)

    total_orders = filtered["order_count"].sum()
    total_revenue = filtered["revenue"].sum()
    avg_daily_demand = filtered.groupby("date")["quantity_sold"].sum().mean()
    n_stores = filtered["place_id"].nunique()

    with col1:
        st.metric("Total Orders", f"{total_orders:,.0f}")
    with col2:
        st.metric("Total Revenue", f"{total_revenue:,.0f} DKK")
    with col3:
        st.metric("Avg Daily Demand", f"{avg_daily_demand:,.1f} units")
    with col4:
        st.metric("Active Stores", n_stores)

    st.divider()

    # Demand trend
    st.subheader("Demand Trend Over Time")
    fig_trend = demand_time_series(filtered, title="Daily Total Demand Across Stores")
    st.plotly_chart(fig_trend, use_container_width=True)

    # Two-column layout
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Demand by Store")
        fig_stores = store_comparison_bar(filtered)
        st.plotly_chart(fig_stores, use_container_width=True)

    with col_right:
        st.subheader("Top 10 Items")
        fig_items = top_items_chart(filtered, n=10)
        st.plotly_chart(fig_items, use_container_width=True)

    # Heatmap
    if "day_of_week" in filtered.columns and "month" in filtered.columns:
        st.subheader("Demand Patterns: Day of Week x Month")
        fig_heat = heatmap_day_hour(filtered)
        st.plotly_chart(fig_heat, use_container_width=True)
