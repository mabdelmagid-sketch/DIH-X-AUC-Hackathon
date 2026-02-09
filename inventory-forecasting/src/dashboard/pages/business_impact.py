"""Business Impact page: two cost equations, interactive weight slider, dual-model comparison.

Two models evaluated under two equations:
  - Profit-Oriented Model  + Equation: Total = 1.0 x Waste + 2.0 x Stockout
  - Sustainability Model   + Equation: Total = 2.0 x Waste + 1.0 x Stockout

Users can also set custom weights via sidebar sliders.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from src.models.evaluator import (
    waste_cost_dkk, stockout_cost_dkk, total_business_cost_dkk,
    profit_oriented_cost_dkk, sustainability_cost_dkk,
    wmape, forecast_accuracy, mae,
)
from src.models.baseline import MovingAverageModel


# ── colour palette ──────────────────────────────────────────────────────────
_BASELINE_COLOR  = "#EF5350"   # red   – "no model"
_PROFIT_COLOR    = "#66BB6A"   # green – profit-oriented model
_SUSTAIN_COLOR   = "#AB47BC"   # purple – sustainability model
_WASTE_COLOR     = "#FF7043"   # orange – food waste cost
_STOCKOUT_COLOR  = "#42A5F5"   # blue  – stockout / lost revenue
_SAVINGS_COLOR   = "#26A69A"   # teal  – savings


# ── helpers ─────────────────────────────────────────────────────────────────

def _prices(df):
    if "item_price" in df.columns:
        return df["item_price"].fillna(75).values.astype(float)
    return np.full(len(df), 75.0)


def _baseline_preds(df):
    return MovingAverageModel(window=28).predict(df, "quantity_sold")


def _af(df):
    return 365 / max(pd.to_datetime(df["date"]).nunique(), 1)


def _dkk(v):
    if abs(v) >= 1_000_000:
        return f"{v/1e6:,.1f}M DKK"
    if abs(v) >= 1_000:
        return f"{v/1e3:,.0f}K DKK"
    return f"{v:,.0f} DKK"


def _cost(actual, pred, prices, wm, sm):
    return total_business_cost_dkk(actual, pred, prices,
                                   waste_multiplier=wm, stockout_multiplier=sm)


def _gap():
    st.markdown("<br>", unsafe_allow_html=True)


# ── main render ─────────────────────────────────────────────────────────────

def render(df: pd.DataFrame):
    st.markdown(
        "<h1 style='text-align:center;'>Business Impact of Demand Forecasting</h1>"
        "<p style='text-align:center;color:#757575;font-size:1.1rem;'>"
        "Compare two strategies: maximise profit vs minimise food waste"
        "</p>",
        unsafe_allow_html=True,
    )

    if "predicted" not in df.columns:
        st.warning("Model predictions not available. Run `python scripts/train_and_save.py` first.")
        return

    has_wo = "predicted_waste_opt" in df.columns

    # ── Sidebar: equation controls ───────────────────────────────────────
    with st.sidebar:
        st.subheader("Cost Equation Settings")

        preset = st.radio(
            "Preset",
            ["Profit-Oriented", "Sustainability", "Custom"],
            index=0,
            key="eq_preset",
            help="Choose a preset or set custom weights below.",
        )

        if preset == "Profit-Oriented":
            wm, sm = 1.0, 2.0
        elif preset == "Sustainability":
            wm, sm = 2.0, 1.0
        else:
            wm = st.slider("Waste cost weight", 0.5, 3.0, 1.0, 0.1, key="wm_slider")
            sm = st.slider("Stockout cost weight", 0.5, 3.0, 2.0, 0.1, key="sm_slider")

        st.markdown(f"**Active equation:**")
        st.code(f"Total = {wm}x Waste + {sm}x Stockout", language=None)

    # ── precompute ───────────────────────────────────────────────────────
    actual   = df["quantity_sold"].values.astype(float)
    prof_pred = df["predicted"].values.astype(float)
    prices   = _prices(df)
    bl_pred  = _baseline_preds(df).values.astype(float)

    df = df.copy()
    df["_bl_pred"] = bl_pred

    sust_pred = df["predicted_waste_opt"].values.astype(float) if has_wo else prof_pred

    af = _af(df)

    # Costs under the ACTIVE equation (sidebar selection)
    bl_waste    = waste_cost_dkk(actual, bl_pred, prices)
    bl_stockout = stockout_cost_dkk(actual, bl_pred, prices)
    bl_total    = _cost(actual, bl_pred, prices, wm, sm)

    prof_waste    = waste_cost_dkk(actual, prof_pred, prices)
    prof_stockout = stockout_cost_dkk(actual, prof_pred, prices)
    prof_total    = _cost(actual, prof_pred, prices, wm, sm)

    sust_waste    = waste_cost_dkk(actual, sust_pred, prices)
    sust_stockout = stockout_cost_dkk(actual, sust_pred, prices)
    sust_total    = _cost(actual, sust_pred, prices, wm, sm)

    # Also compute under BOTH preset equations for head-to-head
    prof_total_eq1 = _cost(actual, prof_pred, prices, 1.0, 2.0)
    prof_total_eq2 = _cost(actual, prof_pred, prices, 2.0, 1.0)
    sust_total_eq1 = _cost(actual, sust_pred, prices, 1.0, 2.0)
    sust_total_eq2 = _cost(actual, sust_pred, prices, 2.0, 1.0)
    bl_total_eq1   = _cost(actual, bl_pred, prices, 1.0, 2.0)
    bl_total_eq2   = _cost(actual, bl_pred, prices, 2.0, 1.0)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 0 – The Two Equations (prominent display)
    # ════════════════════════════════════════════════════════════════════════
    st.divider()
    eq1, eq2 = st.columns(2)

    with eq1:
        st.markdown(
            f"<div style='border:2px solid {_PROFIT_COLOR};border-radius:12px;"
            f"padding:20px;text-align:center;'>"
            f"<div style='font-size:1.2rem;font-weight:700;color:{_PROFIT_COLOR};'>"
            f"Profit-Oriented Equation</div>"
            f"<div style='font-size:1.6rem;font-weight:600;margin:10px 0;'>"
            f"Total = 1.0 x Waste + 2.0 x Stockout</div>"
            f"<div style='font-size:0.9rem;color:#757575;'>"
            f"Penalises missed sales 2x &rarr; stocks more &rarr; higher revenue, some waste</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with eq2:
        st.markdown(
            f"<div style='border:2px solid {_SUSTAIN_COLOR};border-radius:12px;"
            f"padding:20px;text-align:center;'>"
            f"<div style='font-size:1.2rem;font-weight:700;color:{_SUSTAIN_COLOR};'>"
            f"Sustainability Equation</div>"
            f"<div style='font-size:1.6rem;font-weight:600;margin:10px 0;'>"
            f"Total = 2.0 x Waste + 1.0 x Stockout</div>"
            f"<div style='font-size:0.9rem;color:#757575;'>"
            f"Penalises food waste 2x &rarr; stocks less &rarr; less waste, some missed sales</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 1 – Hero KPIs (active equation)
    # ════════════════════════════════════════════════════════════════════════
    st.subheader(f"Key Metrics (active: {wm}x waste + {sm}x stockout)")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        prof_sav = (bl_total - prof_total) * af
        st.metric("Profit Model Savings/yr", _dkk(prof_sav),
                  delta=f"{(1 - prof_total/max(bl_total,1))*100:+.1f}%")
    with c2:
        if has_wo:
            sust_sav = (bl_total - sust_total) * af
            st.metric("Sustainability Savings/yr", _dkk(sust_sav),
                      delta=f"{(1 - sust_total/max(bl_total,1))*100:+.1f}%")
        else:
            st.metric("Sustainability Model", "N/A")
    with c3:
        wr = (1 - prof_waste/max(bl_waste,1))*100
        st.metric("Waste Reduction (Profit)", f"{wr:.1f}%")
    with c4:
        if has_wo:
            wr2 = (1 - sust_waste/max(bl_waste,1))*100
            st.metric("Waste Reduction (Sust.)", f"{wr2:.1f}%")
        else:
            st.metric("Waste Reduction (Sust.)", "N/A")
    with c5:
        acc = forecast_accuracy(actual, prof_pred)
        st.metric("Forecast Accuracy", f"{acc:.1f}%",
                  delta=f"+{acc - forecast_accuracy(actual, bl_pred):.1f}pp")

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 2 – Head-to-Head: both models x both equations
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Head-to-Head: Both Models x Both Equations")
    st.caption("Each model evaluated under both cost equations to show the trade-off")

    h2h_data = {
        "Scenario": [
            "No Model (MA28)",
            "Profit-Oriented Model",
        ],
        "Profit Eq (1x W + 2x S)": [
            _dkk(bl_total_eq1),
            _dkk(prof_total_eq1),
        ],
        "Sustainability Eq (2x W + 1x S)": [
            _dkk(bl_total_eq2),
            _dkk(prof_total_eq2),
        ],
        "Waste Cost": [
            _dkk(bl_waste),
            _dkk(prof_waste),
        ],
        "Stockout Cost": [
            _dkk(bl_stockout),
            _dkk(prof_stockout),
        ],
    }
    if has_wo:
        h2h_data["Scenario"].append("Sustainability Model")
        h2h_data["Profit Eq (1x W + 2x S)"].append(_dkk(sust_total_eq1))
        h2h_data["Sustainability Eq (2x W + 1x S)"].append(_dkk(sust_total_eq2))
        h2h_data["Waste Cost"].append(_dkk(sust_waste))
        h2h_data["Stockout Cost"].append(_dkk(sust_stockout))

    st.dataframe(pd.DataFrame(h2h_data), use_container_width=True, hide_index=True)

    if has_wo:
        col_insight1, col_insight2 = st.columns(2)
        with col_insight1:
            prof_vs_sust_waste = (1 - sust_waste / max(prof_waste, 1)) * 100
            st.success(
                f"The Sustainability model produces **{prof_vs_sust_waste:.1f}% less food waste** "
                f"than the Profit model ({_dkk(sust_waste)} vs {_dkk(prof_waste)})."
            )
        with col_insight2:
            sust_vs_prof_stock = (sust_stockout / max(prof_stockout, 1) - 1) * 100
            st.info(
                f"Trade-off: the Sustainability model has **{sust_vs_prof_stock:.1f}% more stockouts** "
                f"({_dkk(sust_stockout)} vs {_dkk(prof_stockout)})."
            )

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 3 – Stacked bar: total cost under active equation
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Total Cost Comparison (Active Equation)")

    col_chart, col_text = st.columns([3, 1])

    with col_chart:
        fig = go.Figure()

        scenarios = [
            ("No Model<br>(Manual Ordering)", bl_waste, bl_stockout, _BASELINE_COLOR),
            ("Profit-Oriented<br>Model", prof_waste, prof_stockout, _PROFIT_COLOR),
        ]
        if has_wo:
            scenarios.append(
                ("Sustainability<br>Model", sust_waste, sust_stockout, _SUSTAIN_COLOR)
            )

        show_leg = True
        for label, wv, sv, _ in scenarios:
            fig.add_trace(go.Bar(
                y=[label], x=[wv * wm], name="Waste Cost (weighted)",
                orientation="h", marker_color=_WASTE_COLOR,
                text=[_dkk(wv * wm)], textposition="inside",
                textfont=dict(color="white", size=12),
                showlegend=show_leg, legendgroup="w",
            ))
            fig.add_trace(go.Bar(
                y=[label], x=[sv * sm], name="Stockout Cost (weighted)",
                orientation="h", marker_color=_STOCKOUT_COLOR,
                text=[_dkk(sv * sm)], textposition="inside",
                textfont=dict(color="white", size=12),
                showlegend=show_leg, legendgroup="s",
            ))
            show_leg = False

        fig.update_layout(
            barmode="stack", template="plotly_white",
            height=320 if has_wo else 260,
            xaxis_title="Total Business Cost (DKK)",
            legend=dict(orientation="h", yanchor="bottom", y=1.05, x=0.25),
            yaxis=dict(tickfont=dict(size=13)),
            margin=dict(l=0, r=20, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_text:
        prof_pct = (1 - prof_total / max(bl_total, 1)) * 100
        html = (
            f"<div style='padding:15px;text-align:center;'>"
            f"<div style='font-size:2rem;font-weight:700;color:{_PROFIT_COLOR};'>"
            f"{prof_pct:.1f}%</div>"
            f"<div style='font-size:0.85rem;color:#757575;'>Profit Model Savings</div>"
        )
        if has_wo:
            sust_pct = (1 - sust_total / max(bl_total, 1)) * 100
            html += (
                f"<br>"
                f"<div style='font-size:2rem;font-weight:700;color:{_SUSTAIN_COLOR};'>"
                f"{sust_pct:.1f}%</div>"
                f"<div style='font-size:0.85rem;color:#757575;'>Sustainability Savings</div>"
            )
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 4 – Donut charts: cost composition per scenario
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Cost Composition by Model")

    def _donut(wv, sv, title, border):
        vals = [wv * wm, sv * sm]
        fig = go.Figure(go.Pie(
            labels=["Food Waste", "Lost Revenue"], values=vals, hole=0.55,
            marker=dict(colors=[_WASTE_COLOR, _STOCKOUT_COLOR],
                        line=dict(color=border, width=2)),
            textinfo="label+percent", textfont=dict(size=11),
        ))
        fig.update_layout(
            title=dict(text=title, x=0.5, font=dict(size=14)),
            height=300, margin=dict(l=10, r=10, t=50, b=10),
            showlegend=False, template="plotly_white",
            annotations=[dict(text=_dkk(sum(vals)), x=0.5, y=0.5,
                              font_size=14, showarrow=False)],
        )
        return fig

    cols = st.columns(3 if has_wo else 2)
    with cols[0]:
        st.plotly_chart(_donut(bl_waste, bl_stockout, "No Model", _BASELINE_COLOR),
                        use_container_width=True)
    with cols[1]:
        st.plotly_chart(_donut(prof_waste, prof_stockout, "Profit-Oriented", _PROFIT_COLOR),
                        use_container_width=True)
    if has_wo:
        with cols[2]:
            st.plotly_chart(_donut(sust_waste, sust_stockout, "Sustainability", _SUSTAIN_COLOR),
                            use_container_width=True)

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 5 – Waterfall: how each model reduces cost
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Savings Waterfall")

    def _waterfall(bl_t, mod_waste, mod_stockout, mod_total, label, color):
        ws = bl_waste * wm - mod_waste * wm
        ss = bl_stockout * sm - mod_stockout * sm
        fig = go.Figure(go.Waterfall(
            x=["Current Cost<br>(No Model)", "Waste<br>Reduction",
               "Stockout<br>Reduction", f"New Cost<br>({label})"],
            y=[bl_t, -ws, -ss, 0],
            measure=["absolute", "relative", "relative", "total"],
            text=[_dkk(bl_t), f"-{_dkk(ws)}", f"-{_dkk(ss)}", _dkk(mod_total)],
            textposition="outside",
            connector=dict(line=dict(color="#E0E0E0", width=2)),
            decreasing=dict(marker_color=_SAVINGS_COLOR),
            increasing=dict(marker_color=_BASELINE_COLOR),
            totals=dict(marker_color=color),
        ))
        fig.update_layout(template="plotly_white", height=380,
                          yaxis_title="Cost (DKK)", yaxis=dict(tickformat=","),
                          margin=dict(l=60, r=20, t=10, b=20))
        return fig

    wf_cols = st.columns(2 if has_wo else 1)
    with wf_cols[0]:
        st.caption("Profit-Oriented Model")
        st.plotly_chart(_waterfall(bl_total, prof_waste, prof_stockout,
                                   prof_total, "Profit", _PROFIT_COLOR),
                        use_container_width=True)
    if has_wo:
        with wf_cols[1]:
            st.caption("Sustainability Model")
            st.plotly_chart(_waterfall(bl_total, sust_waste, sust_stockout,
                                       sust_total, "Sustain.", _SUSTAIN_COLOR),
                            use_container_width=True)

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 6 – Top items breakdown
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Savings by Top Items")

    item_rows = []
    for iid, grp in df.groupby("item_id", observed=True):
        a  = grp["quantity_sold"].values.astype(float)
        bp = grp["_bl_pred"].values.astype(float)
        pp = grp["predicted"].values.astype(float)
        pr = _prices(grp)

        bl_c  = _cost(a, bp, pr, wm, sm)
        prof_c = _cost(a, pp, pr, wm, sm)
        row = {
            "item_name": grp["item_name"].iloc[0] if "item_name" in grp.columns else str(iid),
            "baseline": bl_c, "profit_model": prof_c,
            "savings": bl_c - prof_c, "total_demand": a.sum(),
        }
        if has_wo:
            sp = grp["predicted_waste_opt"].values.astype(float)
            row["sustain_model"] = _cost(a, sp, pr, wm, sm)
        item_rows.append(row)

    items_df = pd.DataFrame(item_rows).sort_values("savings", ascending=False)
    top = items_df.head(15)

    fig_items = go.Figure()
    fig_items.add_trace(go.Bar(y=top["item_name"], x=top["baseline"],
                               name="No Model", orientation="h",
                               marker_color=_BASELINE_COLOR, opacity=0.8))
    fig_items.add_trace(go.Bar(y=top["item_name"], x=top["profit_model"],
                               name="Profit-Oriented", orientation="h",
                               marker_color=_PROFIT_COLOR, opacity=0.8))
    if has_wo:
        fig_items.add_trace(go.Bar(y=top["item_name"], x=top["sustain_model"],
                                   name="Sustainability", orientation="h",
                                   marker_color=_SUSTAIN_COLOR, opacity=0.8))
    fig_items.update_layout(
        barmode="group", template="plotly_white", height=500,
        xaxis_title="Total Cost (DKK)", yaxis=dict(categoryorder="total ascending"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.15),
        margin=dict(l=10, r=20, t=30, b=40),
    )
    st.plotly_chart(fig_items, use_container_width=True)

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 7 – Store savings
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Annual Savings by Store")

    store_rows = []
    for pid, grp in df.groupby("place_id", observed=True):
        a  = grp["quantity_sold"].values.astype(float)
        bp = grp["_bl_pred"].values.astype(float)
        pp = grp["predicted"].values.astype(float)
        pr = _prices(grp)

        bl_c  = _cost(a, bp, pr, wm, sm)
        prof_c = _cost(a, pp, pr, wm, sm)
        row = {
            "store_name": grp["store_name"].iloc[0] if "store_name" in grp.columns else str(pid),
            "profit_savings": (bl_c - prof_c) * af,
        }
        if has_wo:
            sp = grp["predicted_waste_opt"].values.astype(float)
            row["sustain_savings"] = (bl_c - _cost(a, sp, pr, wm, sm)) * af
        store_rows.append(row)

    stores_df = pd.DataFrame(store_rows).sort_values("profit_savings", ascending=False).head(20)

    fig_s = go.Figure()
    fig_s.add_trace(go.Bar(
        y=stores_df["store_name"], x=stores_df["profit_savings"],
        orientation="h", marker_color=_PROFIT_COLOR, name="Profit-Oriented",
        text=[_dkk(v) for v in stores_df["profit_savings"]],
        textposition="outside", textfont=dict(size=10),
    ))
    if has_wo:
        fig_s.add_trace(go.Bar(
            y=stores_df["store_name"], x=stores_df["sustain_savings"],
            orientation="h", marker_color=_SUSTAIN_COLOR, name="Sustainability",
            text=[_dkk(v) for v in stores_df["sustain_savings"]],
            textposition="outside", textfont=dict(size=10),
        ))
    fig_s.update_layout(
        barmode="group", template="plotly_white",
        height=max(350, len(stores_df) * 35),
        xaxis_title="Projected Annual Savings (DKK)",
        yaxis=dict(categoryorder="total ascending"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.2),
        margin=dict(l=10, r=100, t=30, b=40),
    )
    st.plotly_chart(fig_s, use_container_width=True)

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 8 – Day-of-week
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Cost by Day of Week")
    day_map = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}

    if "day_of_week" in df.columns:
        dow_rows = []
        for dow, grp in df.groupby("day_of_week", observed=True):
            a  = grp["quantity_sold"].values.astype(float)
            pp = grp["predicted"].values.astype(float)
            bp = grp["_bl_pred"].values.astype(float)
            pr = _prices(grp)
            row = {"day": day_map.get(dow, str(dow)), "day_num": dow,
                   "baseline": _cost(a, bp, pr, wm, sm),
                   "profit": _cost(a, pp, pr, wm, sm)}
            if has_wo:
                sp = grp["predicted_waste_opt"].values.astype(float)
                row["sustain"] = _cost(a, sp, pr, wm, sm)
            dow_rows.append(row)

        dow_df = pd.DataFrame(dow_rows).sort_values("day_num")

        fig_dow = go.Figure()
        fig_dow.add_trace(go.Bar(x=dow_df["day"], y=dow_df["baseline"],
                                  name="No Model", marker_color=_BASELINE_COLOR))
        fig_dow.add_trace(go.Bar(x=dow_df["day"], y=dow_df["profit"],
                                  name="Profit-Oriented", marker_color=_PROFIT_COLOR))
        if has_wo:
            fig_dow.add_trace(go.Bar(x=dow_df["day"], y=dow_df["sustain"],
                                      name="Sustainability", marker_color=_SUSTAIN_COLOR))
        fig_dow.update_layout(
            barmode="group", template="plotly_white", height=350,
            yaxis_title="Business Cost (DKK)", yaxis=dict(tickformat=","),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.1),
            margin=dict(l=60, r=10, t=30, b=10),
        )
        st.plotly_chart(fig_dow, use_container_width=True)

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 9 – Cumulative savings timeline
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Cumulative Savings Over Time")

    daily = []
    for dt, grp in df.groupby("date"):
        a  = grp["quantity_sold"].values.astype(float)
        pp = grp["predicted"].values.astype(float)
        bp = grp["_bl_pred"].values.astype(float)
        pr = _prices(grp)
        row = {"date": dt,
               "bl": _cost(a, bp, pr, wm, sm),
               "prof": _cost(a, pp, pr, wm, sm)}
        if has_wo:
            sp = grp["predicted_waste_opt"].values.astype(float)
            row["sust"] = _cost(a, sp, pr, wm, sm)
        daily.append(row)

    ddf = pd.DataFrame(daily).sort_values("date")
    ddf["bl_cum"]   = ddf["bl"].cumsum()
    ddf["prof_cum"] = ddf["prof"].cumsum()
    ddf["prof_sav"] = ddf["bl_cum"] - ddf["prof_cum"]

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(x=ddf["date"], y=ddf["bl_cum"],
                                  name="No Model", line=dict(color=_BASELINE_COLOR, width=2.5)))
    fig_cum.add_trace(go.Scatter(x=ddf["date"], y=ddf["prof_cum"],
                                  name="Profit-Oriented", line=dict(color=_PROFIT_COLOR, width=2.5)))
    if has_wo:
        ddf["sust_cum"] = ddf["sust"].cumsum()
        fig_cum.add_trace(go.Scatter(x=ddf["date"], y=ddf["sust_cum"],
                                      name="Sustainability", line=dict(color=_SUSTAIN_COLOR, width=2.5)))
    fig_cum.add_trace(go.Scatter(x=ddf["date"], y=ddf["prof_sav"],
                                  name="Profit Savings", line=dict(color=_SAVINGS_COLOR, width=2, dash="dot"),
                                  fill="tozeroy", fillcolor="rgba(38,166,154,0.12)"))
    fig_cum.update_layout(
        template="plotly_white", height=400,
        yaxis_title="Cumulative Cost (DKK)", yaxis=dict(tickformat=","),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.1),
        margin=dict(l=60, r=20, t=30, b=40), hovermode="x unified",
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    _gap()

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 10 – Full metrics table
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("Detailed Metrics")

    rows = [
        "Waste Cost (raw)",
        "Stockout Cost (raw)",
        f"Total Cost ({wm}x W + {sm}x S)",
        "Cost under Profit Eq (1x W + 2x S)",
        "Cost under Sustain Eq (2x W + 1x S)",
        "Forecast Accuracy",
        "MAE (units)",
        "Overstock Units",
        "Understock Units",
        "Projected Annual Savings",
    ]

    def _col(pred, total, eq1, eq2):
        return [
            _dkk(waste_cost_dkk(actual, pred, prices)),
            _dkk(stockout_cost_dkk(actual, pred, prices)),
            _dkk(total),
            _dkk(eq1),
            _dkk(eq2),
            f"{forecast_accuracy(actual, pred):.1f}%",
            f"{mae(actual, pred):.2f}",
            f"{np.maximum(pred - actual, 0).sum():,.0f}",
            f"{np.maximum(actual - pred, 0).sum():,.0f}",
            _dkk((bl_total - total) * af),
        ]

    data = {
        "Metric": rows,
        "No Model (MA28)": _col(bl_pred, bl_total, bl_total_eq1, bl_total_eq2),
        "Profit-Oriented": _col(prof_pred, prof_total, prof_total_eq1, prof_total_eq2),
    }
    if has_wo:
        data["Sustainability"] = _col(sust_pred, sust_total, sust_total_eq1, sust_total_eq2)

    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    # Download
    st.divider()
    st.download_button("Download Store Savings CSV", stores_df.to_csv(index=False),
                       "store_savings.csv", "text/csv")
    st.download_button("Download Item Savings CSV", items_df.to_csv(index=False),
                       "item_savings.csv", "text/csv")
