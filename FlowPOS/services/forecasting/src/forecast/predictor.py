"""
predictor.py -- Loving Loyalty AI Suite, Pillar 1: Sales Forecasting

Load trained model artifacts and generate item-level forecasts for a date
range, with:
  - Per-item newsvendor safety buffers
  - Confidence scores based on data history depth (SRS Table 25)
  - Forecast drivers from global model feature importance
  - Lower / upper bounds on each daily prediction

Confidence score rules (SRS Table 25):
  90+ days history  ->  0.75 – 0.95
  30–89 days        ->  0.50 – 0.74
  <30 days          ->  0.20 – 0.49
  0 orders          ->  0.10 – 0.25

Drivers are based on the top features from the RF global model, filtered to
the features that contributed most to this specific item's predictions.  At
least 3 drivers are always returned (falling back to generic labels when
necessary).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

from .feature_engineer import FeatureEngineer

logger = logging.getLogger(__name__)

_DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[3] / "data" / "models"

# Human-readable labels for the top feature drivers
_FEATURE_LABELS: dict[str, str] = {
    "demand_lag_7d": "same day last week",
    "demand_lag_1d": "yesterday's demand",
    "demand_lag_14d": "demand 2 weeks ago",
    "demand_lag_28d": "demand 4 weeks ago",
    "demand_same_weekday_last_week": "same weekday last week",
    "demand_same_weekday_avg_4weeks": "4-week same-weekday average",
    "rolling_mean_7d": "7-day rolling average",
    "rolling_mean_14d": "14-day rolling average",
    "rolling_mean_30d": "30-day rolling average",
    "rolling_std_7d": "7-day demand variability",
    "rolling_std_14d": "14-day demand variability",
    "expanding_mean": "historical average demand",
    "wow_growth": "week-over-week growth trend",
    "recent_vs_expanding": "recent vs. historical demand ratio",
    "is_weekend": "weekend effect",
    "is_friday": "Friday peak",
    "is_monday": "Monday pattern",
    "day_of_week": "day of week",
    "month": "seasonal month pattern",
    "is_holiday": "Danish public holiday",
    "near_holiday": "proximity to public holiday",
    "days_from_holiday": "distance from next/last holiday",
    "fourier_week_sin_1": "weekly seasonality",
    "fourier_annual_sin_1": "annual seasonality",
    "interaction_lag7d_dow": "weekday-adjusted last-week demand",
    "interaction_rolling7_weekend": "weekend rolling demand pattern",
    "is_promotion_active": "active promotion",
}


class ForecastPredictor:
    """Load trained artifacts and generate forecasts for a place and date range.

    Args:
        models_dir: Directory containing balanced_model.pkl (and variants).
        variant: One of "balanced", "waste_optimized", "stockout_optimized".
    """

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        variant: str = "balanced",
    ) -> None:
        self.models_dir = models_dir or _DEFAULT_MODELS_DIR
        self.variant = variant
        self._payload: Optional[dict] = None

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> "ForecastPredictor":
        """Load model artifacts from disk."""
        filename_map = {
            "balanced": "balanced_model.pkl",
            "waste_optimized": "waste_optimized_model.pkl",
            "stockout_optimized": "stockout_optimized_model.pkl",
        }
        filename = filename_map.get(self.variant, "balanced_model.pkl")
        path = self.models_dir / filename

        if not path.exists():
            # Fallback: try the balanced model if variant-specific file is absent
            path = self.models_dir / "balanced_model.pkl"
            if not path.exists():
                raise FileNotFoundError(
                    f"No trained model found at {self.models_dir}. "
                    "Run AdaptiveBlendTrainer.fit() first."
                )
            logger.warning("Variant '%s' not found; falling back to balanced model", self.variant)

        self._payload = joblib.load(path)
        logger.info("Loaded model artifact from %s", path)
        return self

    def _ensure_loaded(self) -> None:
        if self._payload is None:
            self.load()

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(
        self,
        daily_df: pd.DataFrame,
        start_date: date,
        end_date: date,
        place_id: Optional[int] = None,
    ) -> list[dict]:
        """Generate item-level forecasts for a date range.

        Args:
            daily_df: Historical daily demand (output of DataLoader.load_daily_demand()).
                      Should contain all available history up to (not including)
                      start_date.
            start_date: First forecast date (inclusive).
            end_date: Last forecast date (inclusive).
            place_id: If specified, filter to a single restaurant.

        Returns:
            List of dicts, one per (item_id, date), with keys:
              item_id, item_title, place_id, date,
              predicted_units (int), lower_bound (int), upper_bound (int),
              confidence (float), forecast_drivers (list[str])
        """
        self._ensure_loaded()
        model = self._payload["model"]
        feature_engineer: FeatureEngineer = self._payload["feature_engineer"]
        buffers: dict[tuple, float] = self._payload["buffers"]
        feature_cols: list[str] = self._payload["feature_cols"]
        buffer_scale: float = self._payload.get("buffer_scale", 1.0)

        daily_df = daily_df.copy()
        daily_df["date"] = pd.to_datetime(daily_df["date"])

        if place_id is not None:
            daily_df = daily_df[daily_df["place_id"] == place_id].copy()

        if daily_df.empty:
            logger.warning("No data for place_id=%s", place_id)
            return []

        # Build features on historical data (transform only — no fit)
        feat_df = feature_engineer.transform(daily_df)

        # Keep only columns the model was trained on
        available = [c for c in feature_cols if c in feat_df.columns]
        X_hist = feat_df[available].fillna(0.0)

        # Get the most recent row per (place_id, item_id) as the basis for
        # multi-day prediction (features are updated per day in the loop below)
        group_cols = ["place_id", "item_id"] if "place_id" in feat_df.columns else ["item_id"]
        latest = feat_df.sort_values("date").groupby(group_cols, observed=True).last().reset_index()

        if latest.empty:
            return []

        # Compute per-item history depth for confidence scoring
        history_days = (
            daily_df.groupby(group_cols, observed=True)
            .apply(lambda g: (g["quantity_sold"] > 0).sum())
            .reset_index(name="active_days")
        )

        # Feature importance from global model (for driver labels)
        top_features = self._get_top_features(model, available)

        # Date loop
        results: list[dict] = []
        forecast_dates = pd.date_range(start=start_date, end=end_date, freq="D")

        for forecast_date in forecast_dates:
            # Update time-sensitive features for this date
            latest_copy = latest.copy()
            latest_copy["date"] = forecast_date

            # Re-apply time features for the new date
            latest_copy["day_of_week"] = forecast_date.dayofweek
            latest_copy["day_of_month"] = forecast_date.day
            latest_copy["month"] = forecast_date.month
            latest_copy["quarter"] = forecast_date.quarter
            latest_copy["week_of_year"] = forecast_date.isocalendar()[1]
            latest_copy["day_of_year"] = forecast_date.timetuple().tm_yday
            latest_copy["year"] = forecast_date.year
            latest_copy["is_weekend"] = int(forecast_date.weekday() in (5, 6))
            latest_copy["is_friday"] = int(forecast_date.weekday() == 4)
            latest_copy["is_monday"] = int(forecast_date.weekday() == 0)
            latest_copy["dow_sin"] = float(np.sin(2 * np.pi * forecast_date.weekday() / 7))
            latest_copy["dow_cos"] = float(np.cos(2 * np.pi * forecast_date.weekday() / 7))

            # Rebuild Fourier and interaction features for this date
            doy = forecast_date.timetuple().tm_yday
            for k in [1, 2]:
                latest_copy[f"fourier_week_sin_{k}"] = np.sin(2 * np.pi * k * forecast_date.weekday() / 7)
                latest_copy[f"fourier_week_cos_{k}"] = np.cos(2 * np.pi * k * forecast_date.weekday() / 7)
                latest_copy[f"fourier_annual_sin_{k}"] = np.sin(2 * np.pi * k * doy / 365.25)
                latest_copy[f"fourier_annual_cos_{k}"] = np.cos(2 * np.pi * k * doy / 365.25)

            # Rebuild interaction features
            lag7 = latest_copy.get("demand_lag_7d", pd.Series(0, index=latest_copy.index)).fillna(0)
            roll7 = latest_copy.get("rolling_mean_7d", pd.Series(0, index=latest_copy.index)).fillna(0)
            latest_copy["interaction_lag7d_dow"] = lag7 * (latest_copy["day_of_week"] + 1)
            latest_copy["interaction_rolling7_weekend"] = roll7 * latest_copy["is_weekend"]

            # Holiday features for this date
            date_str = forecast_date.strftime("%Y-%m-%d")
            from .feature_engineer import _DANISH_HOLIDAYS
            holiday_ts = [pd.Timestamp(h) for h in _DANISH_HOLIDAYS]
            is_holiday = int(date_str in _DANISH_HOLIDAYS)
            days_from_holiday = min(abs((forecast_date - h).days) for h in holiday_ts)
            near_holiday = int(days_from_holiday <= 2)
            latest_copy["is_holiday"] = is_holiday
            latest_copy["days_from_holiday"] = days_from_holiday
            latest_copy["near_holiday"] = near_holiday

            X_pred = latest_copy[available].fillna(0.0)
            raw_preds = model.predict(X_pred)

            for i, row in latest_copy.iterrows():
                item_id = row.get("item_id", row.get("item", i))
                p_id = row.get("place_id", place_id or 0)
                item_title = row.get("item_title", str(item_id))

                key = (p_id, item_id) if "place_id" in group_cols else (item_id,)
                buffer = buffers.get(key, 1.27) * buffer_scale
                buffer = float(np.clip(buffer, 1.0, 2.0))

                raw = float(raw_preds[i]) if i < len(raw_preds) else 0.0
                buffered = max(0.0, raw * buffer)
                predicted_units = int(round(buffered))
                lower_bound = int(round(max(0.0, buffered * 0.75)))
                upper_bound = int(round(buffered * 1.30))

                # Confidence score (SRS Table 25)
                active_days_row = history_days[
                    history_days.apply(
                        lambda r: all(r[c] == row[c] for c in group_cols if c in r.index),
                        axis=1,
                    )
                ]
                active_days = int(active_days_row["active_days"].iloc[0]) if len(active_days_row) > 0 else 0
                confidence = self._confidence_score(active_days)

                # Forecast drivers
                drivers = self._forecast_drivers(row, top_features, active_days)

                results.append({
                    "item_id": item_id,
                    "item_title": item_title,
                    "place_id": p_id,
                    "date": forecast_date.date().isoformat(),
                    "predicted_units": predicted_units,
                    "lower_bound": lower_bound,
                    "upper_bound": upper_bound,
                    "confidence": round(confidence, 3),
                    "forecast_drivers": drivers,
                })

        return results

    # ------------------------------------------------------------------
    # Confidence scoring (SRS Table 25)
    # ------------------------------------------------------------------

    @staticmethod
    def _confidence_score(active_days: int) -> float:
        """Map history depth to a confidence float per SRS Table 25."""
        if active_days == 0:
            return 0.175   # midpoint of 0.10–0.25
        if active_days < 30:
            # Linear interpolation within 0.20–0.49
            frac = active_days / 30.0
            return round(0.20 + frac * (0.49 - 0.20), 3)
        if active_days < 90:
            # Linear interpolation within 0.50–0.74
            frac = (active_days - 30) / 60.0
            return round(0.50 + frac * (0.74 - 0.50), 3)
        # 90+ days: linear interpolation within 0.75–0.95
        frac = min((active_days - 90) / 180.0, 1.0)  # saturate at ~270 days
        return round(0.75 + frac * (0.95 - 0.75), 3)

    # ------------------------------------------------------------------
    # Forecast drivers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_top_features(model, feature_cols: list[str], top_n: int = 10) -> list[str]:
        """Extract top feature names from the global RF model."""
        try:
            # AdaptiveBlendModel exposes global_model_ directly
            gm = getattr(model, "global_model_", None)
            if gm is None:
                return feature_cols[:top_n]
            importances = gm.feature_importances_
            aug_names = list(feature_cols) + [
                "interaction_lag7_dow", "interaction_roll7_wknd",
                "interaction_roll7_trend", "interaction_lag7_vs_expanding",
            ]
            n = min(len(aug_names), len(importances))
            paired = sorted(zip(aug_names[:n], importances[:n]), key=lambda x: -x[1])
            return [name for name, _ in paired[:top_n]]
        except Exception:
            return feature_cols[:top_n]

    @staticmethod
    def _forecast_drivers(
        row: pd.Series,
        top_features: list[str],
        active_days: int,
    ) -> list[str]:
        """Build human-readable forecast driver strings.

        Always returns at least 3 non-empty strings.
        """
        drivers: list[str] = []

        for feat in top_features:
            label = _FEATURE_LABELS.get(feat)
            if label is None:
                continue
            val = row.get(feat)
            if val is None:
                continue

            # Format value into a useful natural-language driver
            if feat == "demand_lag_7d" and pd.notna(val):
                drivers.append(f"{label}: {int(round(float(val)))} units")
            elif feat == "rolling_mean_7d" and pd.notna(val):
                drivers.append(f"{label}: {float(val):.1f} units/day avg")
            elif feat == "is_weekend" and int(val) == 1:
                drivers.append("Weekend demand pattern")
            elif feat == "is_friday" and int(val) == 1:
                drivers.append("Friday peak demand")
            elif feat == "is_holiday" and int(val) == 1:
                drivers.append("Danish public holiday effect")
            elif feat == "near_holiday" and int(val) == 1:
                drivers.append("Near public holiday boost")
            elif feat == "wow_growth" and pd.notna(val):
                direction = "up" if float(val) > 0 else "down"
                drivers.append(f"Demand trending {direction} week-over-week")
            elif feat == "recent_vs_expanding" and pd.notna(val):
                ratio = float(val)
                if ratio > 1.1:
                    drivers.append("Recent demand above historical average")
                elif ratio < 0.9:
                    drivers.append("Recent demand below historical average")

            if len(drivers) >= 5:
                break

        # Guarantee at least 3 drivers
        if len(drivers) < 3:
            fallbacks = [
                f"Based on {active_days} days of sales history",
                "Weekday demand pattern applied",
                "Seasonal adjustment applied",
                "Historical mean demand used",
                "Rolling demand window applied",
            ]
            for fb in fallbacks:
                if fb not in drivers:
                    drivers.append(fb)
                if len(drivers) >= 3:
                    break

        return drivers[:5]  # cap at 5 to keep response size reasonable
