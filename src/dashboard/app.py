"""Streamlit main app entry point for Fresh Flow Markets Demand Forecasting Dashboard."""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Fresh Flow Markets - Demand Forecasting",
    page_icon="\U0001f957",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Pre-computed predictions file (created by scripts/train_and_save.py)
PREDICTIONS_PATH = PROJECT_ROOT / "data" / "predictions" / "dashboard_predictions.csv"


@st.cache_data(ttl=3600)
def load_saved_predictions():
    """Load pre-computed predictions from CSV (fast, ~10 seconds)."""
    logger.info(f"Loading saved predictions from {PREDICTIONS_PATH}")
    df = pd.read_csv(PREDICTIONS_PATH, low_memory=False)

    if df.empty:
        raise ValueError("Predictions CSV is empty — re-run scripts/train_and_save.py")

    df["date"] = pd.to_datetime(df["date"])

    # Validate critical columns exist
    required = ["date", "quantity_sold", "predicted", "place_id"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Predictions CSV missing required columns: {missing}")

    # Replace any NaN predictions with 0 to prevent downstream errors
    for col in ["predicted", "predicted_waste_opt"]:
        if col in df.columns:
            nan_count = df[col].isna().sum()
            if nan_count > 0:
                logger.warning(f"{nan_count} NaN values in '{col}' replaced with 0")
                df[col] = df[col].fillna(0)

    logger.info(f"Loaded {df.shape[0]:,} rows x {df.shape[1]} cols")
    return df


@st.cache_data(ttl=3600)
def load_data_and_train():
    """Fallback: load raw data, build features, train model live."""
    from src.data.loader import load_key_tables, load_config
    from src.data.cleaner import clean_all
    from src.features.builder import build_features
    from src.models.ensemble import HybridForecaster, WasteOptimizedForecaster
    from src.models.trainer import time_series_split

    config = load_config()
    tables = load_key_tables(config)
    tables = clean_all(tables)

    order_counts = tables["fct_orders"].groupby("place_id").size()
    main_stores = order_counts[order_counts >= 1000].index.tolist()

    tables["fct_orders"] = tables["fct_orders"][
        tables["fct_orders"]["place_id"].isin(main_stores)
    ].copy()
    tables["fct_order_items"] = tables["fct_order_items"][
        tables["fct_order_items"]["order_id"].isin(tables["fct_orders"]["id"])
    ].copy()

    features_df = build_features(tables, top_n_items=20)

    train, val, test = time_series_split(features_df)
    xgb_params = {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05}

    # Balanced model
    model = HybridForecaster(
        xgb_weight=0.3, ma_window=7, round_predictions=True,
        xgb_params=xgb_params,
    )
    model.fit(train, "quantity_sold")
    features_df["predicted"] = model.predict(features_df, "quantity_sold").values

    # Waste-optimized model
    waste_opt = WasteOptimizedForecaster(
        shrink=0.85, xgb_weight=0.3, ma_window=7, xgb_params=xgb_params,
    )
    waste_opt.fit(train, "quantity_sold")
    features_df["predicted_waste_opt"] = waste_opt.predict(features_df, "quantity_sold").values

    if "rolling_std_14d" in features_df.columns:
        std = features_df["rolling_std_14d"].fillna(features_df["quantity_sold"].std())
    else:
        std = features_df["quantity_sold"].std()

    features_df["predicted_lower"] = (features_df["predicted"] - 1.96 * std).clip(lower=0)
    features_df["predicted_upper"] = features_df["predicted"] + 1.96 * std

    return features_df, tables


@st.cache_data(ttl=3600)
def generate_recommendations(_df_with_preds):
    """Generate inventory recommendations."""
    from src.inventory.optimizer import generate_prep_recommendations
    return generate_prep_recommendations(_df_with_preds, forecast_col="predicted")


@st.cache_data(ttl=3600)
def generate_promo_analysis(_df_with_preds, _tables):
    """Generate promotion analysis."""
    from src.inventory.waste_analyzer import classify_waste_risk
    from src.inventory.promotion_engine import (
        identify_slow_movers, analyze_campaign_effectiveness, suggest_promotions,
    )

    waste_risk = classify_waste_risk(_df_with_preds)
    slow_movers = identify_slow_movers(_df_with_preds)
    campaign_impact = analyze_campaign_effectiveness(
        _df_with_preds, _tables.get("fct_campaigns", pd.DataFrame())
    )
    promo_recs = suggest_promotions(slow_movers, waste_risk, campaign_impact)
    return promo_recs, campaign_impact


def main():
    # Sidebar navigation
    st.sidebar.title("Fresh Flow Markets")
    st.sidebar.markdown("*Demand Forecasting System*")

    page = st.sidebar.radio(
        "Navigation",
        ["Business Impact", "Overview", "Forecasts", "Inventory", "Promotions"],
        key="nav",
    )

    # ── Load data ───────────────────────────────────────────────────────────
    tables = None

    if PREDICTIONS_PATH.exists():
        # Fast path: load pre-computed predictions from disk
        with st.spinner("Loading predictions..."):
            try:
                df_with_preds = load_saved_predictions()
            except Exception as e:
                st.error(f"Failed to load saved predictions: {e}")
                logger.exception("Saved predictions load failed")
                return
    else:
        # Slow path: train live (first time, or if parquet missing)
        st.info(
            "No pre-computed predictions found. Training model live "
            "(this takes several minutes on first run). "
            "To speed this up, run: `python scripts/train_and_save.py`"
        )
        with st.spinner("Loading data, building features, and training model..."):
            try:
                df_with_preds, tables = load_data_and_train()
            except Exception as e:
                st.error(f"Failed to load data / train model: {e}")
                logger.exception("Live training failed")
                return

    # ── Route to page ───────────────────────────────────────────────────────
    if page == "Business Impact":
        from src.dashboard.pages.business_impact import render
        render(df_with_preds)

    elif page == "Overview":
        from src.dashboard.pages.overview import render
        render(df_with_preds)

    elif page == "Forecasts":
        from src.dashboard.pages.forecasts import render
        render(df_with_preds)

    elif page == "Inventory":
        from src.dashboard.pages.inventory import render
        try:
            recommendations = generate_recommendations(df_with_preds)
        except Exception:
            recommendations = None
        render(df_with_preds, recommendations)

    elif page == "Promotions":
        from src.dashboard.pages.promotions import render
        # If we didn't load tables (fast path), load them now for promo analysis
        if tables is None:
            try:
                from src.data.loader import load_key_tables, load_config
                from src.data.cleaner import clean_all
                config = load_config()
                tables = load_key_tables(config)
                tables = clean_all(tables)
            except Exception:
                tables = {}
        try:
            promo_recs, campaign_impact = generate_promo_analysis(df_with_preds, tables)
        except Exception:
            promo_recs, campaign_impact = None, None
        render(df_with_preds, promo_recs, campaign_impact)


if __name__ == "__main__":
    main()
