"""Promotions page: recommendations, campaign impact, revenue simulation."""

import streamlit as st
import pandas as pd
import plotly.express as px


def render(df: pd.DataFrame, promo_recs: pd.DataFrame = None,
           campaign_impact: pd.DataFrame = None):
    """Render the Promotions page.

    Args:
        df: Feature DataFrame.
        promo_recs: Promotion recommendations DataFrame.
        campaign_impact: Campaign effectiveness analysis DataFrame.
    """
    st.header("Promotion Intelligence")

    tab1, tab2, tab3 = st.tabs(["Recommendations", "Campaign History", "Revenue Impact"])

    with tab1:
        _render_recommendations(promo_recs)

    with tab2:
        _render_campaign_history(df, campaign_impact)

    with tab3:
        _render_revenue_impact(df, promo_recs)


def _render_recommendations(promo_recs: pd.DataFrame):
    """Render promotion recommendation table."""
    st.subheader("Items Recommended for Promotion")

    if promo_recs is None or promo_recs.empty:
        st.info("No promotion recommendations available. "
                "Run the analysis pipeline to generate recommendations.")
        return

    # Priority badges
    priority_map = {1: "HIGH", 2: "MEDIUM", 3: "LOW"}

    display = promo_recs.copy()
    if "priority" in display.columns:
        display["priority_label"] = display["priority"].map(priority_map)
    if "avg_daily_demand" in display.columns:
        display["avg_daily_demand"] = display["avg_daily_demand"].round(1)

    cols = ["store_name", "item_name", "avg_daily_demand", "waste_risk",
            "suggested_discount_pct", "suggested_days"]
    available = [c for c in cols if c in display.columns]

    if "priority_label" in display.columns:
        available.insert(0, "priority_label")

    st.dataframe(display[available].head(20), use_container_width=True)

    # Summary stats
    if "suggested_discount_pct" in display.columns:
        avg_discount = display["suggested_discount_pct"].mean()
        st.info(f"Average suggested discount: {avg_discount:.0f}%  |  "
                f"Total items flagged: {len(display)}")


def _render_campaign_history(df: pd.DataFrame, campaign_impact: pd.DataFrame):
    """Render historical campaign effectiveness analysis."""
    st.subheader("Historical Campaign Effectiveness")

    if campaign_impact is not None and not campaign_impact.empty:
        fig = px.bar(
            campaign_impact,
            x="store_name",
            y="demand_lift_pct",
            title="Demand Lift During Promotions (%)",
            color="demand_lift_pct",
            color_continuous_scale="RdYlGn",
        )
        fig.update_layout(template="plotly_white", yaxis_title="Demand Lift (%)")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(campaign_impact, use_container_width=True)
    else:
        # Fallback: show promo vs non-promo comparison from the data
        if "is_promotion_active" in df.columns:
            promo_summary = df.groupby("is_promotion_active")["quantity_sold"].agg(
                ["mean", "std", "count"]
            ).reset_index()
            promo_summary["is_promotion_active"] = promo_summary["is_promotion_active"].map(
                {0: "No Promotion", 1: "With Promotion"}
            )
            st.dataframe(promo_summary, use_container_width=True)
        else:
            st.info("No promotion data available for analysis.")


def _render_revenue_impact(df: pd.DataFrame, promo_recs: pd.DataFrame):
    """Render revenue impact simulation."""
    st.subheader("Revenue Impact Simulation")

    if promo_recs is None or promo_recs.empty:
        st.info("No promotion recommendations to simulate.")
        return

    # Simple simulation
    st.markdown("**Estimated impact of applying recommended promotions:**")

    if "avg_daily_demand" in promo_recs.columns and "suggested_discount_pct" in promo_recs.columns:
        # Assume 30% demand lift from promotions (based on typical restaurant data)
        assumed_lift = st.slider("Assumed Demand Lift (%)", 10, 50, 30,
                                 key="promo_lift_slider")

        sim = promo_recs.copy()
        sim["current_daily_revenue"] = sim["avg_daily_demand"] * 100  # ~100 DKK avg
        sim["boosted_demand"] = sim["avg_daily_demand"] * (1 + assumed_lift / 100)
        sim["discounted_price"] = 100 * (1 - sim["suggested_discount_pct"] / 100)
        sim["new_daily_revenue"] = sim["boosted_demand"] * sim["discounted_price"]
        sim["daily_revenue_change"] = sim["new_daily_revenue"] - sim["current_daily_revenue"]

        total_change = sim["daily_revenue_change"].sum()
        monthly_change = total_change * 30

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Est. Daily Revenue Change",
                      f"{total_change:+,.0f} DKK")
        with col2:
            st.metric("Est. Monthly Revenue Change",
                      f"{monthly_change:+,.0f} DKK")

        # Show top impact items
        sim_display = sim.nlargest(10, "daily_revenue_change")
        fig = px.bar(
            sim_display,
            x="item_name",
            y="daily_revenue_change",
            title="Top 10 Items by Revenue Impact",
            color="daily_revenue_change",
            color_continuous_scale="RdYlGn",
        )
        fig.update_layout(template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)
