"""Facebook Prophet model for trend + seasonality detection."""

import logging
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class ProphetForecaster:
    """Prophet model wrapper for demand forecasting."""

    def __init__(self, changepoint_prior_scale: float = 0.05,
                 seasonality_prior_scale: float = 10.0,
                 yearly_seasonality: bool = True,
                 weekly_seasonality: bool = True):
        self.changepoint_prior_scale = changepoint_prior_scale
        self.seasonality_prior_scale = seasonality_prior_scale
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.models = {}  # (place_id, item_id) -> fitted model
        self.name = "prophet"

    def _prepare_prophet_df(self, df: pd.DataFrame,
                            target_col: str = "quantity_sold") -> pd.DataFrame:
        """Prepare data in Prophet format (ds, y)."""
        prophet_df = pd.DataFrame({
            "ds": pd.to_datetime(df["date"]),
            "y": df[target_col].values,
        })

        # Add regressors if available
        regressor_cols = ["temperature_max", "is_rainy", "is_holiday",
                          "is_promotion_active", "is_weekend"]
        for col in regressor_cols:
            if col in df.columns:
                prophet_df[col] = df[col].fillna(0).values

        return prophet_df

    def fit(self, df: pd.DataFrame, target_col: str = "quantity_sold",
            top_n: int = 10) -> "ProphetForecaster":
        """Fit Prophet models per (place_id, item_id) pair.

        Only fits for top N items per store to manage computation time.

        Args:
            df: Feature DataFrame.
            target_col: Target column.
            top_n: Max items per store to model.

        Returns:
            self
        """
        try:
            from prophet import Prophet
        except ImportError:
            logger.error("Prophet not installed. Run: pip install prophet")
            return self

        # Get top items per store
        top_items = (
            df.groupby(["place_id", "item_id"])[target_col]
            .sum()
            .reset_index()
            .sort_values([target_col], ascending=False)
            .groupby("place_id")
            .head(top_n)
        )
        pairs = list(zip(top_items["place_id"], top_items["item_id"]))

        for place_id, item_id in pairs:
            mask = (df["place_id"] == place_id) & (df["item_id"] == item_id)
            subset = df[mask].copy()

            if len(subset) < 30:
                continue

            prophet_df = self._prepare_prophet_df(subset, target_col)

            model = Prophet(
                changepoint_prior_scale=self.changepoint_prior_scale,
                seasonality_prior_scale=self.seasonality_prior_scale,
                yearly_seasonality=self.yearly_seasonality,
                weekly_seasonality=self.weekly_seasonality,
                daily_seasonality=False,
            )

            # Add Danish holidays
            try:
                model.add_country_holidays(country_name="DK")
            except Exception:
                pass

            # Add regressors
            for col in ["temperature_max", "is_rainy", "is_holiday",
                        "is_promotion_active", "is_weekend"]:
                if col in prophet_df.columns:
                    model.add_regressor(col)

            try:
                model.fit(prophet_df)
                self.models[(place_id, item_id)] = model
            except Exception as e:
                logger.warning(f"Prophet fit failed for ({place_id}, {item_id}): {e}")

        logger.info(f"Fitted Prophet models for {len(self.models)} store-item pairs")
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Generate predictions for all rows.

        Args:
            df: DataFrame with same structure as training data.

        Returns:
            Series of predictions.
        """
        predictions = pd.Series(0.0, index=df.index)

        for (place_id, item_id), model in self.models.items():
            mask = (df["place_id"] == place_id) & (df["item_id"] == item_id)
            subset = df[mask].copy()

            if len(subset) == 0:
                continue

            future = self._prepare_prophet_df(subset)
            future = future.drop(columns=["y"], errors="ignore")

            try:
                forecast = model.predict(future)
                preds = forecast["yhat"].clip(lower=0).values
                predictions.loc[mask] = preds
            except Exception as e:
                logger.warning(f"Prophet predict failed for ({place_id}, {item_id}): {e}")

        return predictions

    def predict_future(self, place_id: int, item_id: int,
                       periods: int = 30,
                       regressors_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Generate future forecast for a specific store-item pair.

        Args:
            place_id: Store ID.
            item_id: Item ID.
            periods: Number of days to forecast.
            regressors_df: DataFrame with future regressor values.

        Returns:
            DataFrame with ds, yhat, yhat_lower, yhat_upper columns.
        """
        key = (place_id, item_id)
        if key not in self.models:
            return pd.DataFrame()

        model = self.models[key]
        future = model.make_future_dataframe(periods=periods)

        if regressors_df is not None:
            for col in regressors_df.columns:
                if col != "ds" and col in future.columns:
                    future = future.merge(regressors_df[["ds", col]], on="ds", how="left")
                    future[col] = future[col].fillna(0)

        # Fill regressor columns with 0 where missing
        for col in ["temperature_max", "is_rainy", "is_holiday",
                     "is_promotion_active", "is_weekend"]:
            if col in future.columns:
                future[col] = future[col].fillna(0)

        forecast = model.predict(future)
        forecast["yhat"] = forecast["yhat"].clip(lower=0)
        forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0)

        return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods)
