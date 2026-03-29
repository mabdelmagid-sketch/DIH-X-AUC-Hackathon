"""
src/forecast - Production forecasting pipeline for Loving Loyalty AI Suite, Pillar 1.

Modules:
    data_loader     -- Load raw data from MySQL (real) or CSV (demo) and build daily demand grid
    feature_engineer -- All feature engineering in one place (time, lag, rolling, trend, seasonality)
    trainer         -- Train the AdaptiveBlendModel (RF global + ExtraTrees per-store)
    predictor       -- Load trained models and generate item-level forecasts with confidence scores
"""

from .data_loader import DataLoader
from .feature_engineer import FeatureEngineer
from .trainer import AdaptiveBlendTrainer
from .predictor import ForecastPredictor

__all__ = [
    "DataLoader",
    "FeatureEngineer",
    "AdaptiveBlendTrainer",
    "ForecastPredictor",
]
