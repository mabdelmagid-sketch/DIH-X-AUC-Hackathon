"""Business Impact page: client-facing visualizations of forecasting value.

Compares three scenarios:
  1. "No Model" baseline  – 28-day moving average (proxy for manual ordering)
  2. "Balanced Model"     – 30% XGB + 70% MA7 hybrid (optimised for overall cost)
  3. "Waste-Optimized"    – Balanced * 0.85 shrink (prioritises reducing food waste)

Stockout multiplier: 1.5x (stockout cost weighted 50% higher than face value).
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from src.models.evaluator import (
    waste_cost_dkk, stockout_cost_dkk, total_business_cost_dkk,
    wmape, forecast_accuracy, mae,
)
from src.models.baseline import MovingAverageModel


# ── colour palette ──────────────────────────────────────────────────────────
_BASELINE_COLOR   = "#EF5350"   # red-ish  – "no model"
_BALANCED_COLOR   = "#66BB6A"   # green    – balanced model
_WASTEOPT_COLOR   = "#AB47BC"   # purple   – waste-optimized model
_WASTE_COLOR      = "#FF7043"   # deep orange – food waste
_STOCKOUT_COLOR   = "#42A5F5"   # blue – lost revenue / stockouts
_SAVINGS_COLOR    = "#26A69A"   # teal – savings
_NEUTRAL          = "#BDBDBD"   # grey

STOCKOUT_MULT = 1.5  # stockout cost multiplier used in business cost formula


# ── helpers ─────────────────────────────────────────────────────────────────

def _get_prices(df: pd.DataFrame) -> np.ndarray:
    if "item_price" in df.columns:
        return df["item_price"].fillna(75).values.astype(float)
    return np.full(len(df), 75.0)


def _compute_baseline_preds(df: pd.DataFrame) -> pd.Series:
    """Generate 28-day moving average predictions (proxy for manual ordering)."""
    ma28 = MovingAverageModel(window=28)
    return ma28.predict(df, "quantity_sold")


def _annual_factor(df: pd.DataFrame) -> float:
    n_days = pd.to_datetime(df["date"]).nunique()
    return 365 / max(n_days, 1)


def _fmt_dkk(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:,.1f}M DKK"
    if abs(v) >= 1_000:
        return f"{v/1_000:,.0f}K DKK"
    return f"{v:,.0f} DKK"


def _section_gap():
    st.markdown("<br>", unsafe_allow_html=True)


def _has_waste_opt(df: pd.DataFrame) -> bool:
    return "predicted_waste_opt" in df.columns


# ── main render ─────────────────────────────────────────────────────────────

def render(df: pd.DataFrame):
    """Render the Business Impact page."""

    st.markdown(
        "<h1 style='text-align:center;'>Business Impact of Demand Forecasting</h1>"
        "<p style='text-align:center;color:#757575;font-size:1.1rem;'>"
        "Quantified monetary savings from replacing manual ordering with ML-powered forecasting"
        "</p>",
        unsafe_allow_html=True,
    )

    if "predicted" not in df.columns:
        st.warning("Model predictions are not available. Train the model first.")
        return

    has_wo = _has_waste_opt(df)

    # ── compute all scenarios ────────────────────────────────────────────────
    actual     = df["quantity_sold"].values.astype(float)
    bal_pred   = df["predicted"].values.astype(float)
    prices     = _get_prices(df)
    bl_pred    = _compute_baseline_preds(df).values.astype(float)

    df = df.copy()
    df["_bl_pred"] = bl_pred

    if has_wo:
        wo_pred = df["predicted_waste_opt"].values.astype(float)

    # costs – baseline ("no model")
    bl_waste    = waste_cost_dkk(actual, bl_pred, prices)
    bl_stockout = stockout_cost_dkk(actual, bl_pred, prices)
    bl_total    = total_business_cost_dkk(actual, bl_pred, prices)

    # costs – balanced model
    bal_waste    = waste_cost_dkk(actual, bal_pred, prices)
    bal_stockout = stockout_cost_dkk(actual, bal_pred, prices)
    bal_total    = total_business_cost_dkk(actual, bal_pred, prices)

    # costs – waste-optimized model
    if has_wo:
        wo_waste    = waste_cost_dkk(actual, wo_pred, prices)
        wo_stockout = stockout_cost_dkk(actual, wo_pred, prices)
        wo_total    = total_business_cost_dkk(actual, wo_pred, prices)

    af = _annual_factor(df)
    bal_savings     = (bl_total - bal_total) * af
    bal_savings_pct = (1 - bal_total / max(bl_total, 1)) * 100

    if has_wo:
        wo_savings     = (bl_total - wo_total) * af
        wo_savings_pct = (1 - wo_total / max(bl_total, 1)) * 100

    # ════════════════════════════════════════════════════════════════════════
    # MODEL SELECTOR
    # ════════════════════════════════════════════════════════════════════════
    if has_wo:
        st.info("Two ML models are available: **Balanced** (overall cost reduction) "
                "and **Waste-Optimized** (prioritises food waste reduction at the "
                "cost of slightly more stockouts).")

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 1 – Hero KPIs
    # ════════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("Key Performance Indicators")

    if has_wo:
        c1, c2, c3, c4, c5 = st.columns(5)
    else:
        c1, c2, c3, c4 = st.columns(4)
        c5 = None

    with c1:
        st.metric(
            "Annual Savings (Balanced)",
            _fmt_dkk(bal_savings),
            delta=f"{bal_savings_pct:+.1f}% cost reduction",
            delta_color="normal",
        )
    with c2:
        waste_red_bal = (1 - bal_waste / max(bl_waste, 1)) * 100
        st.metric(
            "Food Waste Reduction",
            f"{waste_red_bal:.1f}%",
            delta=_fmt_dkk((bl_waste - bal_waste) * af) + "/yr",
            delta_color="normal",
        )
    with c3:
        stock_red_bal = (1 - bal_stockout / max(bl_stockout, 1)) * 100
        st.metric(
            "Stockout Reduction",
            f"{stock_red_bal:.1f}%",
            delta=_fmt_dkk((bl_stockout - bal_stockout) * af) + "/yr",
            delta_color="normal",
        )
    with c4:
        acc_bal = forecast_accuracy(actual, bal_pred)
        acc_bl  = forecast_accuracy(actual, bl_pred)
        st.metric(
            "Forecast Accuracy",
            f"{acc_bal:.1f}%",
            delta=f"+{acc_bal - acc_bl:.1f}pp vs baseline",
            delta_color="normal",
        )
    if c5 and has_wo:
        with c5:
            waste_red_wo = (1 - wo_waste / max(bl_waste, 1)) * 100
            st.metric(
                "Waste-Opt Waste Cut",
                f"{waste_red_wo:.1f}%",
                delta=_fmt_dkk((bl_waste - wo_waste) * af) + "/yr",
                delta_color="normal",
            )

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 2 – Before / After total cost comparison (horizontal bar)
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Total Cost Comparison: All Scenarios")
    col_chart, col_text = st.columns([3, 1])

    with col_chart:
        fig_compare = go.Figure()

        scenarios = [
            ("No Model<br>(Manual Ordering)", bl_waste, bl_stockout, _BASELINE_COLOR),
            ("Balanced Model<br>(30% XGB + 70% MA7)", bal_waste, bal_stockout, _BALANCED_COLOR),
        ]
        if has_wo:
            scenarios.append(
                ("Waste-Optimized<br>(85% of Balanced)", wo_waste, wo_stockout, _WASTEOPT_COLOR),
            )

        show_legend = True
        for label, waste_v, stock_v, _ in scenarios:
            fig_compare.add_trace(go.Bar(
                y=[label], x=[waste_v], name="Food Waste Cost",
                orientation="h", marker_color=_WASTE_COLOR,
                text=[_fmt_dkk(waste_v)], textposition="inside",
                textfont=dict(color="white", size=12),
                showlegend=show_legend, legendgroup="waste",
            ))
            fig_compare.add_trace(go.Bar(
                y=[label], x=[stock_v * STOCKOUT_MULT],
                name=f"Stockout Cost ({STOCKOUT_MULT}x weighted)",
                orientation="h", marker_color=_STOCKOUT_COLOR,
                text=[_fmt_dkk(stock_v * STOCKOUT_MULT)], textposition="inside",
                textfont=dict(color="white", size=12),
                showlegend=show_legend, legendgroup="stockout",
            ))
            show_legend = False

        bar_height = 320 if has_wo else 260
        fig_compare.update_layout(
            barmode="stack", template="plotly_white",
            height=bar_height, margin=dict(l=0, r=20, t=10, b=10),
            xaxis_title="Total Business Cost (DKK)",
            legend=dict(orientation="h", yanchor="bottom", y=1.05, x=0.3),
            yaxis=dict(tickfont=dict(size=13)),
        )
        st.plotly_chart(fig_compare, use_container_width=True)

    with col_text:
        lines = (
            f"<div style='padding:15px 10px;text-align:center;'>"
            f"<div style='font-size:2.2rem;font-weight:700;color:{_BALANCED_COLOR};'>"
            f"{bal_savings_pct:.1f}%</div>"
            f"<div style='font-size:0.9rem;color:#757575;'>Balanced Model Savings</div>"
            f"<br>"
            f"<div style='font-size:1.3rem;font-weight:600;color:{_BALANCED_COLOR};'>"
            f"{_fmt_dkk(bal_savings)}/yr</div>"
        )
        if has_wo:
            lines += (
                f"<br><br>"
                f"<div style='font-size:2.2rem;font-weight:700;color:{_WASTEOPT_COLOR};'>"
                f"{wo_savings_pct:.1f}%</div>"
                f"<div style='font-size:0.9rem;color:#757575;'>Waste-Optimized Savings</div>"
                f"<br>"
                f"<div style='font-size:1.3rem;font-weight:600;color:{_WASTEOPT_COLOR};'>"
                f"{_fmt_dkk(wo_savings)}/yr</div>"
            )
        lines += "</div>"
        st.markdown(lines, unsafe_allow_html=True)

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 3 – Waste type breakdown (donut charts)
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Cost Breakdown by Waste Type")

    def _donut(waste_val, stockout_val, title, border_color):
        labels = ["Food Waste<br>(Overstock)", "Lost Revenue<br>(Stockout)"]
        values = [waste_val, stockout_val * STOCKOUT_MULT]
        colors = [_WASTE_COLOR, _STOCKOUT_COLOR]
        fig = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.55,
            marker=dict(colors=colors, line=dict(color=border_color, width=2)),
            textinfo="label+percent", textfont=dict(size=11),
            hovertemplate="%{label}: %{value:,.0f} DKK<extra></extra>",
        ))
        fig.update_layout(
            title=dict(text=title, x=0.5, font=dict(size=14)),
            template="plotly_white", height=310,
            margin=dict(l=15, r=15, t=50, b=15),
            showlegend=False,
            annotations=[dict(
                text=_fmt_dkk(waste_val + stockout_val * STOCKOUT_MULT),
                x=0.5, y=0.5, font_size=14, showarrow=False, font_color="#424242",
            )],
        )
        return fig

    if has_wo:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.plotly_chart(_donut(bl_waste, bl_stockout,
                                   "No Model", _BASELINE_COLOR), use_container_width=True)
        with col_b:
            st.plotly_chart(_donut(bal_waste, bal_stockout,
                                   "Balanced Model", _BALANCED_COLOR), use_container_width=True)
        with col_c:
            st.plotly_chart(_donut(wo_waste, wo_stockout,
                                   "Waste-Optimized", _WASTEOPT_COLOR), use_container_width=True)
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(_donut(bl_waste, bl_stockout,
                                   "No Model", _BASELINE_COLOR), use_container_width=True)
        with col_b:
            st.plotly_chart(_donut(bal_waste, bal_stockout,
                                   "With ML Model", _BALANCED_COLOR), use_container_width=True)

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 4 – Savings waterfall
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Savings Waterfall: How Each Model Reduces Costs")

    # Balanced waterfall
    bal_waste_saving  = bl_waste - bal_waste
    bal_stock_saving  = (bl_stockout - bal_stockout) * STOCKOUT_MULT

    fig_wf = go.Figure(go.Waterfall(
        orientation="v",
        x=["Current Cost<br>(No Model)", "Waste<br>Reduction",
           "Stockout<br>Reduction", "New Cost<br>(Balanced)"],
        y=[bl_total, -bal_waste_saving, -bal_stock_saving, 0],
        measure=["absolute", "relative", "relative", "total"],
        text=[_fmt_dkk(bl_total), f"-{_fmt_dkk(bal_waste_saving)}",
              f"-{_fmt_dkk(bal_stock_saving)}", _fmt_dkk(bal_total)],
        textposition="outside",
        connector=dict(line=dict(color="#E0E0E0", width=2)),
        decreasing=dict(marker_color=_SAVINGS_COLOR),
        increasing=dict(marker_color=_BASELINE_COLOR),
        totals=dict(marker_color=_BALANCED_COLOR),
        name="Balanced",
    ))
    fig_wf.update_layout(
        template="plotly_white", height=420,
        yaxis_title="Business Cost (DKK)",
        margin=dict(l=60, r=20, t=20, b=20),
        yaxis=dict(tickformat=","),
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    if has_wo:
        st.caption("Waste-Optimized Model Waterfall:")
        wo_waste_saving  = bl_waste - wo_waste
        wo_stock_saving  = (bl_stockout - wo_stockout) * STOCKOUT_MULT

        fig_wf2 = go.Figure(go.Waterfall(
            orientation="v",
            x=["Current Cost<br>(No Model)", "Waste<br>Reduction",
               "Stockout<br>Reduction", "New Cost<br>(Waste-Opt)"],
            y=[bl_total, -wo_waste_saving, -wo_stock_saving, 0],
            measure=["absolute", "relative", "relative", "total"],
            text=[_fmt_dkk(bl_total), f"-{_fmt_dkk(wo_waste_saving)}",
                  f"-{_fmt_dkk(wo_stock_saving)}", _fmt_dkk(wo_total)],
            textposition="outside",
            connector=dict(line=dict(color="#E0E0E0", width=2)),
            decreasing=dict(marker_color=_SAVINGS_COLOR),
            increasing=dict(marker_color=_BASELINE_COLOR),
            totals=dict(marker_color=_WASTEOPT_COLOR),
            name="Waste-Optimized",
        ))
        fig_wf2.update_layout(
            template="plotly_white", height=420,
            yaxis_title="Business Cost (DKK)",
            margin=dict(l=60, r=20, t=20, b=20),
            yaxis=dict(tickformat=","),
        )
        st.plotly_chart(fig_wf2, use_container_width=True)

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 5 – Head-to-head model comparison table
    # ════════════════════════════════════════════════════════════════════════
    if has_wo:
        st.subheader("Balanced vs Waste-Optimized: Head-to-Head")

        comp_data = {
            "Metric": [
                "Food Waste Cost",
                "Stockout Cost",
                f"Total Business Cost (waste + {STOCKOUT_MULT}x stockout)",
                "Forecast Accuracy",
                "Overstock Units",
                "Understock Units",
                "Projected Annual Savings vs No Model",
            ],
            "No Model (MA28)": [
                _fmt_dkk(bl_waste),
                _fmt_dkk(bl_stockout),
                _fmt_dkk(bl_total),
                f"{forecast_accuracy(actual, bl_pred):.1f}%",
                f"{np.maximum(bl_pred - actual, 0).sum():,.0f}",
                f"{np.maximum(actual - bl_pred, 0).sum():,.0f}",
                "---",
            ],
            "Balanced Model": [
                _fmt_dkk(bal_waste),
                _fmt_dkk(bal_stockout),
                _fmt_dkk(bal_total),
                f"{forecast_accuracy(actual, bal_pred):.1f}%",
                f"{np.maximum(bal_pred - actual, 0).sum():,.0f}",
                f"{np.maximum(actual - bal_pred, 0).sum():,.0f}",
                _fmt_dkk(bal_savings),
            ],
            "Waste-Optimized": [
                _fmt_dkk(wo_waste),
                _fmt_dkk(wo_stockout),
                _fmt_dkk(wo_total),
                f"{forecast_accuracy(actual, wo_pred):.1f}%",
                f"{np.maximum(wo_pred - actual, 0).sum():,.0f}",
                f"{np.maximum(actual - wo_pred, 0).sum():,.0f}",
                _fmt_dkk(wo_savings),
            ],
        }
        comp_df = pd.DataFrame(comp_data)
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

        # Highlight the trade-off
        wo_waste_vs_bal = (1 - wo_waste / max(bal_waste, 1)) * 100
        wo_stock_vs_bal = (wo_stockout / max(bal_stockout, 1) - 1) * 100
        st.markdown(
            f"**Trade-off:** The Waste-Optimized model reduces food waste by "
            f"an additional **{wo_waste_vs_bal:.1f}%** compared to the Balanced model, "
            f"but increases stockout costs by **{wo_stock_vs_bal:.1f}%**. "
            f"Choose based on your priority: overall cost vs sustainability."
        )

        _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 6 – Impact by item category (top items)
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Waste Reduction by Top Items")
    st.caption("Comparing total business cost per item across models")

    item_rows = []
    for iid, grp in df.groupby("item_id", observed=True):
        a  = grp["quantity_sold"].values.astype(float)
        bp = grp["_bl_pred"].values.astype(float)
        mp = grp["predicted"].values.astype(float)
        pr = _get_prices(grp)

        bl_c  = total_business_cost_dkk(a, bp, pr)
        bal_c = total_business_cost_dkk(a, mp, pr)

        row = {
            "item_name": grp["item_name"].iloc[0] if "item_name" in grp.columns else str(iid),
            "baseline_cost": bl_c,
            "balanced_cost": bal_c,
            "savings": bl_c - bal_c,
            "savings_pct": (1 - bal_c / max(bl_c, 1)) * 100,
            "total_demand": a.sum(),
            "baseline_waste": waste_cost_dkk(a, bp, pr),
            "balanced_waste": waste_cost_dkk(a, mp, pr),
        }
        if has_wo:
            wp = grp["predicted_waste_opt"].values.astype(float)
            wo_c = total_business_cost_dkk(a, wp, pr)
            row["waste_opt_cost"] = wo_c
            row["waste_opt_waste"] = waste_cost_dkk(a, wp, pr)
            row["wo_savings"] = bl_c - wo_c

        item_rows.append(row)

    items_df = pd.DataFrame(item_rows).sort_values("savings", ascending=False)
    top_items = items_df.head(15)

    fig_items = go.Figure()
    fig_items.add_trace(go.Bar(
        y=top_items["item_name"], x=top_items["baseline_cost"],
        name="No Model", orientation="h",
        marker_color=_BASELINE_COLOR, opacity=0.8,
    ))
    fig_items.add_trace(go.Bar(
        y=top_items["item_name"], x=top_items["balanced_cost"],
        name="Balanced Model", orientation="h",
        marker_color=_BALANCED_COLOR, opacity=0.8,
    ))
    if has_wo:
        fig_items.add_trace(go.Bar(
            y=top_items["item_name"], x=top_items["waste_opt_cost"],
            name="Waste-Optimized", orientation="h",
            marker_color=_WASTEOPT_COLOR, opacity=0.8,
        ))
    fig_items.update_layout(
        barmode="group", template="plotly_white", height=500,
        xaxis_title="Total Business Cost (DKK)", yaxis_title="",
        yaxis=dict(categoryorder="total ascending", tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.15),
        margin=dict(l=10, r=20, t=30, b=40),
    )
    st.plotly_chart(fig_items, use_container_width=True)

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 7 – Impact by store
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Savings by Store Location")
    st.caption("Annual projected savings per store from ML forecasting")

    store_rows = []
    for pid, grp in df.groupby("place_id", observed=True):
        a  = grp["quantity_sold"].values.astype(float)
        bp = grp["_bl_pred"].values.astype(float)
        mp = grp["predicted"].values.astype(float)
        pr = _get_prices(grp)

        bl_c  = total_business_cost_dkk(a, bp, pr)
        bal_c = total_business_cost_dkk(a, mp, pr)

        row = {
            "store_name": grp["store_name"].iloc[0] if "store_name" in grp.columns else str(pid),
            "baseline_cost": bl_c * af,
            "balanced_savings": (bl_c - bal_c) * af,
            "balanced_waste": waste_cost_dkk(a, mp, pr) * af,
            "baseline_waste": waste_cost_dkk(a, bp, pr) * af,
        }
        if has_wo:
            wp = grp["predicted_waste_opt"].values.astype(float)
            wo_c = total_business_cost_dkk(a, wp, pr)
            row["wo_savings"] = (bl_c - wo_c) * af
            row["wo_waste"] = waste_cost_dkk(a, wp, pr) * af

        store_rows.append(row)

    stores_df = pd.DataFrame(store_rows).sort_values("balanced_savings", ascending=False)
    top_stores = stores_df.head(20)

    fig_stores = go.Figure()
    fig_stores.add_trace(go.Bar(
        y=top_stores["store_name"], x=top_stores["balanced_savings"],
        orientation="h", marker_color=_BALANCED_COLOR, name="Balanced Model",
        text=[_fmt_dkk(v) for v in top_stores["balanced_savings"]],
        textposition="outside", textfont=dict(size=10),
    ))
    if has_wo:
        fig_stores.add_trace(go.Bar(
            y=top_stores["store_name"], x=top_stores["wo_savings"],
            orientation="h", marker_color=_WASTEOPT_COLOR, name="Waste-Optimized",
            text=[_fmt_dkk(v) for v in top_stores["wo_savings"]],
            textposition="outside", textfont=dict(size=10),
        ))
    fig_stores.update_layout(
        barmode="group", template="plotly_white",
        height=max(350, len(top_stores) * 35),
        xaxis_title="Projected Annual Savings (DKK)",
        yaxis=dict(categoryorder="total ascending", tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.2),
        margin=dict(l=10, r=100, t=30, b=40),
    )
    st.plotly_chart(fig_stores, use_container_width=True)

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 8 – Impact by day of week
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Cost Savings by Day of Week")
    st.caption("Which days benefit most from ML forecasting?")

    day_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
                 4: "Friday", 5: "Saturday", 6: "Sunday"}

    dow_rows = []
    if "day_of_week" in df.columns:
        for dow, grp in df.groupby("day_of_week", observed=True):
            a  = grp["quantity_sold"].values.astype(float)
            mp = grp["predicted"].values.astype(float)
            bp = grp["_bl_pred"].values.astype(float)
            pr = _get_prices(grp)

            bl_c  = total_business_cost_dkk(a, bp, pr)
            bal_c = total_business_cost_dkk(a, mp, pr)

            row = {
                "day": day_names.get(dow, str(dow)),
                "day_num": dow,
                "baseline_cost": bl_c,
                "balanced_cost": bal_c,
                "savings": bl_c - bal_c,
                "waste_baseline": waste_cost_dkk(a, bp, pr),
                "waste_balanced": waste_cost_dkk(a, mp, pr),
                "stockout_baseline": stockout_cost_dkk(a, bp, pr),
                "stockout_balanced": stockout_cost_dkk(a, mp, pr),
            }
            if has_wo:
                wp = grp["predicted_waste_opt"].values.astype(float)
                row["wo_cost"] = total_business_cost_dkk(a, wp, pr)
            dow_rows.append(row)

    if dow_rows:
        dow_df = pd.DataFrame(dow_rows).sort_values("day_num")

        col_dow1, col_dow2 = st.columns(2)

        with col_dow1:
            fig_dow = go.Figure()
            fig_dow.add_trace(go.Bar(
                x=dow_df["day"], y=dow_df["baseline_cost"],
                name="No Model", marker_color=_BASELINE_COLOR, opacity=0.8,
            ))
            fig_dow.add_trace(go.Bar(
                x=dow_df["day"], y=dow_df["balanced_cost"],
                name="Balanced", marker_color=_BALANCED_COLOR, opacity=0.8,
            ))
            if has_wo:
                fig_dow.add_trace(go.Bar(
                    x=dow_df["day"], y=dow_df["wo_cost"],
                    name="Waste-Opt", marker_color=_WASTEOPT_COLOR, opacity=0.8,
                ))
            fig_dow.update_layout(
                barmode="group", template="plotly_white", height=350,
                yaxis_title="Business Cost (DKK)", yaxis=dict(tickformat=","),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.1),
                margin=dict(l=60, r=10, t=30, b=10),
                title=dict(text="Total Cost by Day", font=dict(size=14)),
            )
            st.plotly_chart(fig_dow, use_container_width=True)

        with col_dow2:
            fig_dow_s = go.Figure()
            fig_dow_s.add_trace(go.Bar(
                x=dow_df["day"],
                y=dow_df["waste_baseline"] - dow_df["waste_balanced"],
                name="Waste Reduction", marker_color=_WASTE_COLOR, opacity=0.85,
            ))
            fig_dow_s.add_trace(go.Bar(
                x=dow_df["day"],
                y=(dow_df["stockout_baseline"] - dow_df["stockout_balanced"]) * STOCKOUT_MULT,
                name=f"Stockout Reduction ({STOCKOUT_MULT}x)",
                marker_color=_STOCKOUT_COLOR, opacity=0.85,
            ))
            fig_dow_s.update_layout(
                barmode="stack", template="plotly_white", height=350,
                yaxis_title="Savings (DKK)", yaxis=dict(tickformat=","),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.1),
                margin=dict(l=60, r=10, t=30, b=10),
                title=dict(text="Savings Breakdown by Day", font=dict(size=14)),
            )
            st.plotly_chart(fig_dow_s, use_container_width=True)

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 9 – Cumulative savings timeline
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Cumulative Savings Over Time")
    st.caption("Running total of cost savings as each model operates day by day")

    df_time = df.copy()
    df_time["date"] = pd.to_datetime(df_time["date"])

    daily_costs = []
    for dt, grp in df_time.groupby("date"):
        a  = grp["quantity_sold"].values.astype(float)
        mp = grp["predicted"].values.astype(float)
        bp = grp["_bl_pred"].values.astype(float)
        pr = _get_prices(grp)

        row = {
            "date": dt,
            "bl_cost": total_business_cost_dkk(a, bp, pr),
            "bal_cost": total_business_cost_dkk(a, mp, pr),
        }
        if has_wo:
            wp = grp["predicted_waste_opt"].values.astype(float)
            row["wo_cost"] = total_business_cost_dkk(a, wp, pr)
        daily_costs.append(row)

    daily_df = pd.DataFrame(daily_costs).sort_values("date")
    daily_df["bl_cum"]  = daily_df["bl_cost"].cumsum()
    daily_df["bal_cum"] = daily_df["bal_cost"].cumsum()
    daily_df["bal_savings_cum"] = daily_df["bl_cum"] - daily_df["bal_cum"]

    if has_wo:
        daily_df["wo_cum"] = daily_df["wo_cost"].cumsum()
        daily_df["wo_savings_cum"] = daily_df["bl_cum"] - daily_df["wo_cum"]

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=daily_df["date"], y=daily_df["bl_cum"],
        name="No Model", mode="lines",
        line=dict(color=_BASELINE_COLOR, width=2.5),
    ))
    fig_cum.add_trace(go.Scatter(
        x=daily_df["date"], y=daily_df["bal_cum"],
        name="Balanced Model", mode="lines",
        line=dict(color=_BALANCED_COLOR, width=2.5),
    ))
    if has_wo:
        fig_cum.add_trace(go.Scatter(
            x=daily_df["date"], y=daily_df["wo_cum"],
            name="Waste-Optimized", mode="lines",
            line=dict(color=_WASTEOPT_COLOR, width=2.5),
        ))
    fig_cum.add_trace(go.Scatter(
        x=daily_df["date"], y=daily_df["bal_savings_cum"],
        name="Balanced Savings", mode="lines",
        line=dict(color=_SAVINGS_COLOR, width=2, dash="dot"),
        fill="tozeroy", fillcolor="rgba(38,166,154,0.12)",
    ))
    fig_cum.update_layout(
        template="plotly_white", height=400,
        yaxis_title="Cumulative Cost (DKK)", yaxis=dict(tickformat=","),
        xaxis_title="Date",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.1),
        margin=dict(l=60, r=20, t=30, b=40),
        hovermode="x unified",
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 10 – Item scatter: baseline cost vs model cost
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Item-Level Forecast Performance")
    st.caption("Each dot is one item. Items below the diagonal line are improved by the model.")

    scatter_df = items_df.copy()
    scatter_df["demand_size"] = np.clip(scatter_df["total_demand"], 10, None)

    fig_scatter = px.scatter(
        scatter_df.head(60),
        x="baseline_cost", y="balanced_cost",
        size="demand_size", color="savings_pct",
        hover_name="item_name",
        color_continuous_scale="RdYlGn",
        range_color=[-10, 50],
        labels={
            "baseline_cost": "Cost Without Model (DKK)",
            "balanced_cost": "Cost With Balanced Model (DKK)",
            "savings_pct": "Savings %",
        },
    )
    max_val = max(scatter_df.head(60)["baseline_cost"].max(),
                  scatter_df.head(60)["balanced_cost"].max()) * 1.05
    fig_scatter.add_trace(go.Scatter(
        x=[0, max_val], y=[0, max_val],
        mode="lines", line=dict(color="#E0E0E0", dash="dash", width=1),
        showlegend=False, hoverinfo="skip",
    ))
    fig_scatter.update_layout(
        template="plotly_white", height=450,
        margin=dict(l=60, r=20, t=20, b=40),
    )
    st.plotly_chart(fig_scatter, use_container_width=True)
    st.caption("Dots below the dashed line = model outperforms baseline. "
               "Greener = larger improvement. Size = demand volume.")

    _section_gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 11 – Full metrics table
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Detailed Metrics Comparison")

    metrics_rows = [
        "Total Business Cost",
        "Food Waste Cost (Overstock)",
        "Lost Revenue Cost (Stockout)",
        "Forecast Accuracy (WMAPE)",
        "Mean Absolute Error",
        "Overstock Units (total)",
        "Understock Units (total)",
        "Projected Annual Savings",
    ]

    no_model_vals = [
        _fmt_dkk(bl_total),
        _fmt_dkk(bl_waste),
        _fmt_dkk(bl_stockout),
        f"{forecast_accuracy(actual, bl_pred):.1f}%",
        f"{mae(actual, bl_pred):.2f} units",
        f"{np.maximum(bl_pred - actual, 0).sum():,.0f}",
        f"{np.maximum(actual - bl_pred, 0).sum():,.0f}",
        "---",
    ]

    balanced_vals = [
        _fmt_dkk(bal_total),
        _fmt_dkk(bal_waste),
        _fmt_dkk(bal_stockout),
        f"{forecast_accuracy(actual, bal_pred):.1f}%",
        f"{mae(actual, bal_pred):.2f} units",
        f"{np.maximum(bal_pred - actual, 0).sum():,.0f}",
        f"{np.maximum(actual - bal_pred, 0).sum():,.0f}",
        _fmt_dkk(bal_savings),
    ]

    metrics_data = {
        "Metric": metrics_rows,
        "No Model (MA28)": no_model_vals,
        "Balanced Model": balanced_vals,
    }

    if has_wo:
        metrics_data["Waste-Optimized"] = [
            _fmt_dkk(wo_total),
            _fmt_dkk(wo_waste),
            _fmt_dkk(wo_stockout),
            f"{forecast_accuracy(actual, wo_pred):.1f}%",
            f"{mae(actual, wo_pred):.2f} units",
            f"{np.maximum(wo_pred - actual, 0).sum():,.0f}",
            f"{np.maximum(actual - wo_pred, 0).sum():,.0f}",
            _fmt_dkk(wo_savings),
        ]

    metrics_df = pd.DataFrame(metrics_data)
    st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    # Download buttons
    st.divider()
    csv_stores = stores_df.to_csv(index=False)
    st.download_button(
        label="Download Store-Level Savings (CSV)",
        data=csv_stores,
        file_name="store_savings_breakdown.csv",
        mime="text/csv",
    )
    csv_items = items_df.to_csv(index=False)
    st.download_button(
        label="Download Item-Level Savings (CSV)",
        data=csv_items,
        file_name="item_savings_breakdown.csv",
        mime="text/csv",
    )
