"""Promotion recommendation engine for slow-moving and high-waste items."""

import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def identify_slow_movers(df: pd.DataFrame, actual_col: str = "quantity_sold",
                         threshold_percentile: float = 25) -> pd.DataFrame:
    """Identify slow-moving items that may benefit from promotions.

    Args:
        df: Feature DataFrame with demand data.
        actual_col: Actual demand column.
        threshold_percentile: Items below this percentile are 'slow-moving'.

    Returns:
        DataFrame of slow-moving items with statistics.
    """
    item_stats = (
        df.groupby(["place_id", "item_id"], observed=True)
        .agg(
            avg_daily_demand=(actual_col, "mean"),
            total_demand=(actual_col, "sum"),
            days_with_sales=(actual_col, lambda x: (x > 0).sum()),
            total_days=(actual_col, "count"),
            item_name=("item_name", "first") if "item_name" in df.columns else (actual_col, "count"),
            store_name=("store_name", "first") if "store_name" in df.columns else (actual_col, "count"),
        )
        .reset_index()
    )

    # Fix column names if item_name/store_name weren't available
    if "item_name" not in df.columns:
        item_stats = item_stats.rename(columns={item_stats.columns[-2]: "item_name"})
    if "store_name" not in df.columns:
        item_stats = item_stats.rename(columns={item_stats.columns[-1]: "store_name"})

    item_stats["sell_through_rate"] = item_stats["days_with_sales"] / item_stats["total_days"]

    threshold = item_stats["avg_daily_demand"].quantile(threshold_percentile / 100)
    slow = item_stats[item_stats["avg_daily_demand"] <= threshold].copy()

    logger.info(f"Identified {len(slow)} slow-moving items (below {threshold:.2f} units/day)")
    return slow.sort_values("avg_daily_demand")


def analyze_campaign_effectiveness(df: pd.DataFrame, campaigns_df: pd.DataFrame,
                                   actual_col: str = "quantity_sold") -> pd.DataFrame:
    """Analyze historical campaign effectiveness.

    Compare demand during promotion vs non-promotion periods.

    Args:
        df: Feature DataFrame with promotion flags.
        campaigns_df: Raw fct_campaigns data.
        actual_col: Actual demand column.

    Returns:
        DataFrame with campaign impact analysis.
    """
    if "is_promotion_active" not in df.columns:
        logger.warning("No promotion features found in data")
        return pd.DataFrame()

    promo = df[df["is_promotion_active"] == 1]
    no_promo = df[df["is_promotion_active"] == 0]

    results = []
    for pid in df["place_id"].unique():
        promo_store = promo[promo["place_id"] == pid]
        no_promo_store = no_promo[no_promo["place_id"] == pid]

        if len(promo_store) == 0 or len(no_promo_store) == 0:
            continue

        avg_promo = promo_store[actual_col].mean()
        avg_no_promo = no_promo_store[actual_col].mean()
        lift = (avg_promo - avg_no_promo) / max(avg_no_promo, 0.01) * 100

        results.append({
            "place_id": pid,
            "store_name": promo_store["store_name"].iloc[0] if "store_name" in promo_store.columns else "",
            "avg_demand_with_promo": round(avg_promo, 2),
            "avg_demand_without_promo": round(avg_no_promo, 2),
            "demand_lift_pct": round(lift, 1),
            "promo_days": len(promo_store),
            "non_promo_days": len(no_promo_store),
        })

    return pd.DataFrame(results)


def suggest_promotions(slow_movers: pd.DataFrame, waste_risk: pd.DataFrame,
                       campaign_effectiveness: pd.DataFrame) -> pd.DataFrame:
    """Generate promotion recommendations.

    Combines slow-moving status, waste risk, and historical campaign data
    to suggest which items should be promoted and with what discount.

    Args:
        slow_movers: DataFrame of slow-moving items.
        waste_risk: DataFrame with waste risk classifications.
        campaign_effectiveness: DataFrame with campaign impact data.

    Returns:
        DataFrame with promotion recommendations.
    """
    # Merge slow movers with waste risk
    recs = slow_movers.merge(
        waste_risk[["place_id", "item_id", "waste_risk", "cv"]],
        on=["place_id", "item_id"],
        how="left",
    )

    # Suggest discount based on urgency
    def suggest_discount(row):
        if row.get("waste_risk") == "high":
            return 25.0  # Aggressive discount for high waste risk
        elif row.get("waste_risk") == "medium":
            return 15.0
        elif row["sell_through_rate"] < 0.2:
            return 20.0  # Low sell-through => needs bigger discount
        else:
            return 10.0

    recs["suggested_discount_pct"] = recs.apply(suggest_discount, axis=1)

    # Suggest timing: promote on low-demand days (Mon/Tue typically)
    recs["suggested_days"] = "Monday-Tuesday"
    recs["priority"] = recs["waste_risk"].map(
        {"high": 1, "medium": 2, "low": 3, None: 3}
    ).fillna(3).astype(int)

    recs = recs.sort_values("priority")
    logger.info(f"Generated {len(recs)} promotion recommendations")
    return recs
