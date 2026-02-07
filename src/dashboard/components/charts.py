"""Reusable Plotly chart components."""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np


def demand_time_series(df: pd.DataFrame, date_col: str = "date",
                       value_col: str = "quantity_sold",
                       title: str = "Daily Demand") -> go.Figure:
    """Line chart of demand over time.

    Args:
        df: DataFrame with date and value columns.
        date_col: Date column name.
        value_col: Value column name.
        title: Chart title.

    Returns:
        Plotly Figure.
    """
    daily = df.groupby(date_col)[value_col].sum().reset_index()
    fig = px.line(daily, x=date_col, y=value_col, title=title)
    fig.update_layout(xaxis_title="Date", yaxis_title="Quantity",
                      template="plotly_white")
    return fig


def forecast_chart(df: pd.DataFrame, actual_col: str = "quantity_sold",
                   forecast_col: str = "predicted",
                   date_col: str = "date",
                   lower_col: str = None, upper_col: str = None,
                   title: str = "Forecast vs Actual") -> go.Figure:
    """Interactive chart showing historical demand + forecast with confidence interval.

    Args:
        df: DataFrame with actual and forecast columns.
        actual_col: Actual values column.
        forecast_col: Forecast values column.
        date_col: Date column.
        lower_col: Lower confidence bound column.
        upper_col: Upper confidence bound column.
        title: Chart title.

    Returns:
        Plotly Figure.
    """
    fig = go.Figure()

    # Actual demand
    fig.add_trace(go.Scatter(
        x=df[date_col], y=df[actual_col],
        name="Actual", mode="lines",
        line=dict(color="#2196F3", width=1.5),
    ))

    # Forecast
    fig.add_trace(go.Scatter(
        x=df[date_col], y=df[forecast_col],
        name="Forecast", mode="lines",
        line=dict(color="#FF5722", width=2, dash="dash"),
    ))

    # Confidence interval
    if lower_col and upper_col and lower_col in df.columns and upper_col in df.columns:
        fig.add_trace(go.Scatter(
            x=pd.concat([df[date_col], df[date_col][::-1]]),
            y=pd.concat([df[upper_col], df[lower_col][::-1]]),
            fill="toself", fillcolor="rgba(255,87,34,0.1)",
            line=dict(width=0), name="95% CI",
        ))

    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Quantity",
                      template="plotly_white", hovermode="x unified")
    return fig


def store_comparison_bar(df: pd.DataFrame, value_col: str = "quantity_sold",
                         title: str = "Demand by Store") -> go.Figure:
    """Bar chart comparing stores."""
    store_totals = (
        df.groupby("store_name")[value_col]
        .sum()
        .reset_index()
        .sort_values(value_col, ascending=True)
    )

    fig = px.bar(store_totals, x=value_col, y="store_name",
                 orientation="h", title=title,
                 color=value_col, color_continuous_scale="Viridis")
    fig.update_layout(template="plotly_white", yaxis_title="",
                      xaxis_title="Total Quantity Sold")
    return fig


def top_items_chart(df: pd.DataFrame, n: int = 10,
                    value_col: str = "quantity_sold",
                    title: str = "Top Items") -> go.Figure:
    """Horizontal bar chart of top items."""
    top = (
        df.groupby("item_name")[value_col]
        .sum()
        .nlargest(n)
        .reset_index()
        .sort_values(value_col, ascending=True)
    )

    fig = px.bar(top, x=value_col, y="item_name",
                 orientation="h", title=title,
                 color=value_col, color_continuous_scale="Turbo")
    fig.update_layout(template="plotly_white", yaxis_title="",
                      xaxis_title="Total Quantity")
    return fig


def heatmap_day_hour(df: pd.DataFrame, value_col: str = "quantity_sold",
                     title: str = "Demand by Day of Week") -> go.Figure:
    """Heatmap of demand by day of week and month."""
    day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu",
                 4: "Fri", 5: "Sat", 6: "Sun"}

    pivot = df.groupby(["day_of_week", "month"])[value_col].mean().reset_index()
    pivot["day_name"] = pivot["day_of_week"].map(day_names)

    matrix = pivot.pivot_table(index="day_name", columns="month",
                                values=value_col, aggfunc="mean")

    # Reorder days
    day_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    matrix = matrix.reindex([d for d in day_order if d in matrix.index])

    fig = px.imshow(matrix, title=title, aspect="auto",
                    color_continuous_scale="YlOrRd",
                    labels=dict(x="Month", y="Day of Week", color="Avg Demand"))
    fig.update_layout(template="plotly_white")
    return fig


def kpi_card(label: str, value, delta=None, delta_color: str = "normal"):
    """Display a KPI metric card using Streamlit.

    Args:
        label: Metric label.
        value: Metric value.
        delta: Change from previous period.
        delta_color: Color of delta ("normal", "inverse", "off").
    """
    import streamlit as st
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def alert_table(recommendations: pd.DataFrame) -> go.Figure:
    """Color-coded recommendation table."""
    color_map = {"red": "#FFCDD2", "yellow": "#FFF9C4", "green": "#C8E6C9"}

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=["Store", "Item", "Forecast", "Safety Stock", "Rec. Qty", "Alert"],
            fill_color="#424242",
            font=dict(color="white", size=12),
            align="left",
        ),
        cells=dict(
            values=[
                recommendations["store_name"],
                recommendations["item_name"],
                recommendations["forecast_demand"],
                recommendations["safety_stock"],
                recommendations["recommended_prep_qty"],
                recommendations["alert_level"],
            ],
            fill_color=[
                [color_map.get(a, "white") for a in recommendations["alert_level"]]
            ] * 6,
            align="left",
        )
    )])

    fig.update_layout(title="Inventory Recommendations", template="plotly_white")
    return fig
