"""Inventory recommendations page: prep quantities, alerts, safety stock."""

import streamlit as st
import pandas as pd

from src.dashboard.components.charts import alert_table
from src.dashboard.components.filters import store_selector


def render(df: pd.DataFrame, recommendations: pd.DataFrame = None):
    """Render the Inventory Recommendations page.

    Args:
        df: Feature DataFrame.
        recommendations: Pre-computed prep recommendations DataFrame.
    """
    st.header("Inventory Recommendations")

    if recommendations is None or recommendations.empty:
        st.info("No recommendations available. Run the forecasting pipeline first "
                "to generate prep quantity recommendations.")
        _show_demand_summary(df)
        return

    # Sidebar filter
    with st.sidebar:
        st.subheader("Inventory Filters")
        stores = recommendations["store_name"].unique().tolist()
        selected_stores = st.multiselect(
            "Filter by Store", options=stores, default=stores,
            key="inv_store_filter",
        )

        alert_filter = st.multiselect(
            "Alert Level",
            options=["red", "yellow", "green"],
            default=["red", "yellow", "green"],
            key="inv_alert_filter",
        )

    filtered_recs = recommendations[
        (recommendations["store_name"].isin(selected_stores)) &
        (recommendations["alert_level"].isin(alert_filter))
    ]

    # KPI summary
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        n_red = len(filtered_recs[filtered_recs["alert_level"] == "red"])
        st.metric("High Risk Items", n_red)
    with col2:
        n_yellow = len(filtered_recs[filtered_recs["alert_level"] == "yellow"])
        st.metric("Moderate Risk", n_yellow)
    with col3:
        n_green = len(filtered_recs[filtered_recs["alert_level"] == "green"])
        st.metric("Low Risk", n_green)
    with col4:
        total_prep = filtered_recs["recommended_prep_qty"].sum()
        st.metric("Total Prep Units", f"{total_prep:,.0f}")

    st.divider()

    # Alert table
    st.subheader("Prep Quantity Recommendations")

    # Color-coded dataframe
    def color_alert(val):
        colors = {"red": "background-color: #FFCDD2",
                  "yellow": "background-color: #FFF9C4",
                  "green": "background-color: #C8E6C9"}
        return colors.get(val, "")

    display_cols = ["store_name", "item_name", "forecast_demand", "safety_stock",
                    "recommended_prep_qty", "avg_daily_demand", "alert_level"]
    st.dataframe(filtered_recs[display_cols], use_container_width=True)

    # Safety stock details
    st.subheader("Safety Stock & Reorder Points")
    detail_cols = ["store_name", "item_name", "avg_daily_demand", "demand_std",
                   "safety_stock", "reorder_point"]
    available_cols = [c for c in detail_cols if c in filtered_recs.columns]
    st.dataframe(filtered_recs[available_cols], use_container_width=True)

    # Download
    csv = filtered_recs.to_csv(index=False)
    st.download_button(
        label="Download Recommendations CSV",
        data=csv,
        file_name="inventory_recommendations.csv",
        mime="text/csv",
    )


def _show_demand_summary(df: pd.DataFrame):
    """Show basic demand summary when no recommendations are available."""
    st.subheader("Demand Summary (Historical)")

    if df.empty:
        return

    summary = (
        df.groupby(["store_name", "item_name"])
        .agg(
            avg_daily=("quantity_sold", "mean"),
            std_daily=("quantity_sold", "std"),
            total=("quantity_sold", "sum"),
        )
        .reset_index()
        .sort_values("total", ascending=False)
        .head(30)
    )

    summary["avg_daily"] = summary["avg_daily"].round(1)
    summary["std_daily"] = summary["std_daily"].round(1)

    st.dataframe(summary, use_container_width=True)
