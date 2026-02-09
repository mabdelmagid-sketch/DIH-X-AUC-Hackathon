"""Offline training script: builds features, trains both models, saves predictions + model files.

Run this ONCE before launching the dashboard:
    cd inventory-forecasting
    python scripts/train_and_save.py

The dashboard will then load the saved predictions and model files instantly
instead of retraining on every cold start.
"""

import sys
import time
import logging
import joblib
from pathlib import Path

# Add project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = ROOT / "data" / "predictions"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS_DIR = ROOT / "data" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

PREDICTIONS_PATH = OUTPUT_DIR / "dashboard_predictions.csv"
BALANCED_MODEL_PATH = MODELS_DIR / "balanced_model.pkl"
WASTE_OPT_MODEL_PATH = MODELS_DIR / "waste_optimized_model.pkl"


def main():
    t0 = time.time()

    # ── 1. Load & clean ────────────────────────────────────────────────────
    logger.info("Step 1/6: Loading and cleaning data...")
    from src.data.loader import load_key_tables, load_config
    from src.data.cleaner import clean_all

    config = load_config()
    tables = load_key_tables(config)
    tables = clean_all(tables)

    # Filter to main stores (1000+ orders)
    order_counts = tables["fct_orders"].groupby("place_id").size()
    main_stores = order_counts[order_counts >= 1000].index.tolist()
    logger.info(f"  Main stores: {len(main_stores)}")

    tables["fct_orders"] = tables["fct_orders"][
        tables["fct_orders"]["place_id"].isin(main_stores)
    ].copy()
    tables["fct_order_items"] = tables["fct_order_items"][
        tables["fct_order_items"]["order_id"].isin(tables["fct_orders"]["id"])
    ].copy()

    logger.info(f"  Elapsed: {time.time() - t0:.0f}s")

    # ── 2. Build features ──────────────────────────────────────────────────
    logger.info("Step 2/6: Building features (top 20 items per store)...")
    from src.features.builder import build_features

    features_df = build_features(tables, top_n_items=20)
    logger.info(f"  Feature matrix: {features_df.shape}")
    logger.info(f"  Elapsed: {time.time() - t0:.0f}s")

    # ── 3. Train balanced hybrid model ─────────────────────────────────────
    logger.info("Step 3/6: Training Profit-Oriented model (30% XGB + 70% MA7)...")
    from src.models.ensemble import HybridForecaster, WasteOptimizedForecaster
    from src.models.trainer import time_series_split

    train, val, test = time_series_split(features_df)
    logger.info(f"  Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

    xgb_params = {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05}

    balanced = HybridForecaster(
        xgb_weight=0.3, ma_window=7, round_predictions=True,
        xgb_params=xgb_params,
    )
    balanced.fit(train, "quantity_sold")
    logger.info(f"  Balanced model fitted. Elapsed: {time.time() - t0:.0f}s")

    logger.info("  Generating balanced predictions...")
    features_df["predicted"] = balanced.predict(features_df, "quantity_sold").values

    # Confidence intervals
    if "rolling_std_14d" in features_df.columns:
        std = features_df["rolling_std_14d"].fillna(features_df["quantity_sold"].std())
    else:
        std = features_df["quantity_sold"].std()
    features_df["predicted_lower"] = (features_df["predicted"] - 1.96 * std).clip(lower=0)
    features_df["predicted_upper"] = features_df["predicted"] + 1.96 * std

    logger.info(f"  Balanced predictions done. Elapsed: {time.time() - t0:.0f}s")

    # ── 4. Train waste-optimized model ─────────────────────────────────────
    logger.info("Step 4/6: Training Sustainability model (85% of profit-oriented)...")
    waste_opt = WasteOptimizedForecaster(
        shrink=0.85, xgb_weight=0.3, ma_window=7, xgb_params=xgb_params,
    )
    waste_opt.fit(train, "quantity_sold")

    features_df["predicted_waste_opt"] = waste_opt.predict(features_df, "quantity_sold").values
    logger.info(f"  Waste-optimized predictions done. Elapsed: {time.time() - t0:.0f}s")

    # ── 5. Save models + predictions to disk ────────────────────────────
    logger.info("Step 5/6: Saving trained models...")
    joblib.dump(balanced, BALANCED_MODEL_PATH)
    joblib.dump(waste_opt, WASTE_OPT_MODEL_PATH)
    bal_size = BALANCED_MODEL_PATH.stat().st_size / (1024 * 1024)
    wo_size = WASTE_OPT_MODEL_PATH.stat().st_size / (1024 * 1024)
    logger.info(f"  Balanced model: {bal_size:.1f} MB -> {BALANCED_MODEL_PATH}")
    logger.info(f"  Waste-opt model: {wo_size:.1f} MB -> {WASTE_OPT_MODEL_PATH}")

    logger.info(f"Step 6/6: Saving predictions to {PREDICTIONS_PATH}...")
    features_df.to_csv(PREDICTIONS_PATH, index=False)

    size_mb = PREDICTIONS_PATH.stat().st_size / (1024 * 1024)
    total_time = time.time() - t0
    logger.info(f"  Saved: {size_mb:.1f} MB, {features_df.shape[0]:,} rows x {features_df.shape[1]} cols")
    logger.info(f"  Total time: {total_time:.0f}s")
    logger.info("")
    logger.info("Done! You can now run the dashboard instantly:")
    logger.info("  streamlit run src/dashboard/app.py")


if __name__ == "__main__":
    main()
