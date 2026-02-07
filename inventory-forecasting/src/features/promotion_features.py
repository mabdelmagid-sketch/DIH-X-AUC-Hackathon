"""Promotion features derived from fct_campaigns."""

import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def build_promotion_calendar(campaigns_df: pd.DataFrame,
                             timezone: str = "Europe/Copenhagen") -> pd.DataFrame:
    """Build a daily promotion calendar from campaigns data.

    Args:
        campaigns_df: fct_campaigns DataFrame with start_date_time, end_date_time as UNIX timestamps.
        timezone: Timezone for date conversion.

    Returns:
        DataFrame with columns: date, place_id, is_promotion_active, discount_percentage,
        promotion_type, campaign_count
    """
    records = []

    for _, row in campaigns_df.iterrows():
        try:
            start_ts = row.get("start_date_time")
            end_ts = row.get("end_date_time")
            if pd.isna(start_ts) or pd.isna(end_ts):
                continue

            start = pd.Timestamp(int(start_ts), unit="s", tz="UTC").tz_convert(timezone)
            end = pd.Timestamp(int(end_ts), unit="s", tz="UTC").tz_convert(timezone)

            place_id = row.get("place_id")
            discount = row.get("discount", 0) or 0
            promo_type = row.get("type", "unknown")

            # Generate one record per day the campaign was active
            dates = pd.date_range(start.normalize(), end.normalize(), freq="D")
            for date in dates:
                records.append({
                    "date": date.date(),
                    "place_id": place_id,
                    "discount_percentage": float(discount),
                    "promotion_type": str(promo_type),
                })
        except (ValueError, TypeError):
            continue

    if not records:
        return pd.DataFrame(columns=["date", "place_id", "is_promotion_active",
                                      "discount_percentage", "promotion_type", "campaign_count"])

    promo_df = pd.DataFrame(records)
    promo_df["date"] = pd.to_datetime(promo_df["date"])

    # Aggregate per (date, place_id)
    agg = promo_df.groupby(["date", "place_id"]).agg(
        campaign_count=("discount_percentage", "count"),
        discount_percentage=("discount_percentage", "max"),
        promotion_type=("promotion_type", "first"),
    ).reset_index()

    agg["is_promotion_active"] = 1
    return agg


def add_promotion_features(df: pd.DataFrame, campaigns_df: pd.DataFrame,
                           date_col: str = "date",
                           place_col: str = "place_id") -> pd.DataFrame:
    """Add promotion features to the main DataFrame.

    Args:
        df: Main DataFrame with date and place_id columns.
        campaigns_df: fct_campaigns DataFrame.
        date_col: Date column name.
        place_col: Place ID column name.

    Returns:
        DataFrame with promotion features added.
    """
    promo_cal = build_promotion_calendar(campaigns_df)

    if promo_cal.empty:
        df["is_promotion_active"] = 0
        df["discount_percentage"] = 0.0
        df["promotion_type"] = ""
        df["campaign_count"] = 0
        df["days_since_last_promotion"] = -1
        df["days_until_next_promotion"] = -1
        return df

    df["_merge_date"] = pd.to_datetime(df[date_col]).dt.normalize()
    promo_cal["date"] = pd.to_datetime(promo_cal["date"]).dt.normalize()

    df = df.merge(
        promo_cal,
        left_on=["_merge_date", place_col],
        right_on=["date", "place_id"],
        how="left",
        suffixes=("", "_promo"),
    )

    # Fill NaN for non-promotion days
    df["is_promotion_active"] = df["is_promotion_active"].fillna(0).astype(int)
    df["discount_percentage"] = df["discount_percentage"].fillna(0.0)
    df["promotion_type"] = df["promotion_type"].fillna("")
    df["campaign_count"] = df["campaign_count"].fillna(0).astype(int)

    # Calculate days since last / until next promotion per place
    df = df.sort_values([place_col, date_col]).copy()
    for pid in df[place_col].unique():
        mask = df[place_col] == pid
        promo_dates = df.loc[mask & (df["is_promotion_active"] == 1), "_merge_date"]

        if promo_dates.empty:
            df.loc[mask, "days_since_last_promotion"] = -1
            df.loc[mask, "days_until_next_promotion"] = -1
            continue

        for idx in df[mask].index:
            current_date = df.loc[idx, "_merge_date"]
            past = promo_dates[promo_dates < current_date]
            future = promo_dates[promo_dates > current_date]

            df.loc[idx, "days_since_last_promotion"] = (
                (current_date - past.max()).days if not past.empty else -1
            )
            df.loc[idx, "days_until_next_promotion"] = (
                (future.min() - current_date).days if not future.empty else -1
            )

    # Clean up merge columns
    df = df.drop(columns=["_merge_date", "date_promo", "place_id_promo"], errors="ignore")

    logger.info("Added promotion features")
    return df
