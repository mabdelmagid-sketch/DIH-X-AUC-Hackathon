"""Forecasts page: interactive forecast charts with confidence intervals."""

import streamlit as st
import pandas as pd
import numpy as np

from src.dashboard.components.charts import forecast_chart
from src.dashboard.components.filters import (
    store_selector, item_selector, date_range_selector,
    granularity_selector, apply_filters,
)


def _aggregate_by_granularity(df: pd.DataFrame, granularity: str) -> pd.DataFrame:
    """Aggregate data to the selected time granularity."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    if granularity == "Weekly":
        df["period"] = df["date"].dt.to_period("W").dt.start_time
    elif granularity == "Monthly":
        df["period"] = df["date"].dt.to_period("M").dt.start_time
    else:
        df["period"] = df["date"]

    agg_cols = {"quantity_sold": "sum", "revenue": "sum"}
    if "predicted" in df.columns:
        agg_cols["predicted"] = "sum"
    if "predicted_lower" in df.columns:
        agg_cols["predicted_lower"] = "sum"
    if "predicted_upper" in df.columns:
        agg_cols["predicted_upper"] = "sum"

    agg = df.groupby("period").agg(agg_cols).reset_index()
    agg = agg.rename(columns={"period": "date"})
    return agg


def render(df: pd.DataFrame):
    """Render the Forecasts page.

    Args:
        df: Feature DataFrame with predictions.
    """
    st.header("Demand Forecasts")

    has_predictions = "predicted" in df.columns

    # Sidebar filters
    with st.sidebar:
        st.subheader("Forecast Filters")
        selected_stores = store_selector(df, key="forecast_stores")
        selected_items = item_selector(df, place_ids=selected_stores,
                                        key="forecast_items")
        start_date, end_date = date_range_selector(df, key="forecast_dates")
        granularity = granularity_selector(key="forecast_gran")

    filtered = apply_filters(df, place_ids=selected_stores,
                              item_ids=selected_items,
                              start_date=start_date, end_date=end_date)

    if filtered.empty:
        st.warning("No data for the selected filters. Try adjusting your selections.")
        return

    # Aggregate by granularity
    agg = _aggregate_by_granularity(filtered, granularity)

    if has_predictions:
        # Generate confidence interval if not present
        if "predicted_lower" not in agg.columns:
            std = agg["quantity_sold"].std() * 0.5
            agg["predicted_lower"] = (agg["predicted"] - 1.96 * std).clip(lower=0)
            agg["predicted_upper"] = agg["predicted"] + 1.96 * std

        # Forecast chart
        st.subheader(f"{granularity} Forecast vs Actual")
        fig = forecast_chart(
            agg,
            actual_col="quantity_sold",
            forecast_col="predicted",
            lower_col="predicted_lower",
            upper_col="predicted_upper",
            title=f"{granularity} Demand: Actual vs Forecast",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Metrics
        from src.models.evaluator import mae, rmse, mape as mape_fn
        actual = agg["quantity_sold"].values
        predicted = agg["predicted"].values

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("MAE", f"{mae(actual, predicted):.2f}")
        with col2:
            st.metric("RMSE", f"{rmse(actual, predicted):.2f}")
        with col3:
            st.metric("MAPE", f"{mape_fn(actual, predicted):.1f}%")
    else:
        # Just show historical data
        st.subheader(f"{granularity} Historical Demand")
        fig = forecast_chart(
            agg,
            actual_col="quantity_sold",
            forecast_col="quantity_sold",
            title=f"{granularity} Historical Demand",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.info("No forecast predictions available yet. Train a model to see forecasts.")

    # Data table with download
    st.subheader("Forecast Data")
    display_cols = ["date", "quantity_sold"]
    if has_predictions:
        display_cols.extend(["predicted"])
    st.dataframe(agg[display_cols], use_container_width=True)

    csv = agg[display_cols].to_csv(index=False)
    st.download_button(
        label="Download Forecast CSV",
        data=csv,
        file_name="forecast_data.csv",
        mime="text/csv",
    )
