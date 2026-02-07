"""
Demand Forecasting Model using XGBoost
"""
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

from ..config import settings


class DemandForecaster:
    """XGBoost-based demand forecasting model"""

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or settings.model_path
        self.model: Optional[xgb.XGBRegressor] = None
        self.feature_columns: list[str] = []
        self.item_models: dict[str, xgb.XGBRegressor] = {}
        self.metrics: dict = {}

    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        item_column: Optional[str] = None,
        item_data: Optional[pd.DataFrame] = None,
        **xgb_params
    ) -> dict:
        """Train the forecasting model"""
        default_params = {
            "n_estimators": 100,
            "max_depth": 6,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
            "n_jobs": -1
        }
        default_params.update(xgb_params)

        self.feature_columns = list(X.columns)

        # Train global model
        self.model = xgb.XGBRegressor(**default_params)
        self.model.fit(X, y)

        # Evaluate with time series cross-validation
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = []

        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            temp_model = xgb.XGBRegressor(**default_params)
            temp_model.fit(X_train, y_train)
            y_pred = temp_model.predict(X_val)

            cv_scores.append({
                "mae": mean_absolute_error(y_val, y_pred),
                "rmse": np.sqrt(mean_squared_error(y_val, y_pred)),
                "r2": r2_score(y_val, y_pred)
            })

        # Average metrics
        self.metrics = {
            "mae": np.mean([s["mae"] for s in cv_scores]),
            "rmse": np.mean([s["rmse"] for s in cv_scores]),
            "r2": np.mean([s["r2"] for s in cv_scores]),
            "cv_scores": cv_scores
        }

        return self.metrics

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Generate predictions"""
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")

        # Ensure columns match
        X = X[self.feature_columns]
        return self.model.predict(X)

    def predict_with_confidence(
        self,
        X: pd.DataFrame,
        confidence: float = 0.9
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate predictions with confidence intervals"""
        predictions = self.predict(X)

        # Estimate uncertainty (simplified)
        std_estimate = self.metrics.get("rmse", predictions.std())
        z_score = 1.645 if confidence == 0.9 else 1.96

        lower = predictions - z_score * std_estimate
        upper = predictions + z_score * std_estimate

        # Ensure non-negative
        lower = np.maximum(lower, 0)

        return predictions, lower, upper

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get feature importance ranking"""
        if self.model is None:
            raise ValueError("Model not trained")

        importance = pd.DataFrame({
            "feature": self.feature_columns,
            "importance": self.model.feature_importances_
        }).sort_values("importance", ascending=False)

        return importance.head(top_n)

    def save(self, filename: str = "demand_forecaster.joblib"):
        """Save model to disk"""
        self.model_path.mkdir(parents=True, exist_ok=True)

        model_data = {
            "model": self.model,
            "feature_columns": self.feature_columns,
            "metrics": self.metrics,
            "saved_at": datetime.now().isoformat()
        }

        filepath = self.model_path / filename
        joblib.dump(model_data, filepath)
        return filepath

    def load(self, filename: str = "demand_forecaster.joblib"):
        """Load model from disk"""
        filepath = self.model_path / filename

        if not filepath.exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")

        model_data = joblib.load(filepath)
        self.model = model_data["model"]
        self.feature_columns = model_data["feature_columns"]
        self.metrics = model_data["metrics"]

        return self

    def forecast_future(
        self,
        historical_df: pd.DataFrame,
        feature_engineer,
        days_ahead: int = 7,
        item_filter: Optional[str] = None
    ) -> pd.DataFrame:
        """Generate future forecasts"""
        # Get the last date in historical data
        last_date = historical_df["date"].max()

        # Generate future dates
        future_dates = pd.date_range(
            start=last_date + timedelta(days=1),
            periods=days_ahead,
            freq="D"
        )

        forecasts = []

        # Get unique items
        items = historical_df["item_title"].unique()
        if item_filter:
            items = [item_filter]

        for item in items:
            item_hist = historical_df[historical_df["item_title"] == item].copy()

            if len(item_hist) < 7:  # Need minimum history
                continue

            for future_date in future_dates:
                future_row = self._create_future_row(
                    item_hist, future_date, item, feature_engineer
                )

                if future_row is not None:
                    pred, lower, upper = self.predict_with_confidence(
                        future_row[self.feature_columns].to_frame().T
                    )

                    forecasts.append({
                        "date": future_date,
                        "item_title": item,
                        "predicted_quantity": pred[0],
                        "lower_bound": lower[0],
                        "upper_bound": upper[0]
                    })

                    # Update history for next iteration
                    new_row = future_row.copy()
                    new_row["total_quantity"] = pred[0]
                    item_hist = pd.concat([item_hist, new_row.to_frame().T], ignore_index=True)

        return pd.DataFrame(forecasts)

    def _create_future_row(
        self,
        history: pd.DataFrame,
        future_date: datetime,
        item: str,
        feature_engineer
    ) -> Optional[pd.Series]:
        """Create feature row for a future date"""
        recent = history.tail(30).copy()

        if len(recent) == 0:
            return None

        row = pd.Series({
            "date": future_date,
            "item_title": item,
            "total_quantity": 0,
        })

        # Time features
        row["day_of_week"] = future_date.dayofweek
        row["day_of_month"] = future_date.day
        row["month"] = future_date.month
        row["week_of_year"] = future_date.isocalendar()[1]
        row["is_weekend"] = 1 if future_date.dayofweek in [5, 6] else 0
        row["is_month_start"] = 1 if future_date.day == 1 else 0
        row["is_month_end"] = 1 if (future_date + timedelta(days=1)).day == 1 else 0
        row["quarter"] = (future_date.month - 1) // 3 + 1

        # Cyclical
        row["day_of_week_sin"] = np.sin(2 * np.pi * row["day_of_week"] / 7)
        row["day_of_week_cos"] = np.cos(2 * np.pi * row["day_of_week"] / 7)
        row["month_sin"] = np.sin(2 * np.pi * row["month"] / 12)
        row["month_cos"] = np.cos(2 * np.pi * row["month"] / 12)

        # Lag features (from actual history)
        qty = recent["total_quantity"]
        row["total_quantity_lag_1"] = qty.iloc[-1] if len(qty) >= 1 else 0
        row["total_quantity_lag_7"] = qty.iloc[-7] if len(qty) >= 7 else qty.mean()
        row["total_quantity_lag_14"] = qty.iloc[-14] if len(qty) >= 14 else qty.mean()
        row["total_quantity_lag_28"] = qty.iloc[-28] if len(qty) >= 28 else qty.mean()

        # Rolling features
        for window in [7, 14, 30]:
            vals = qty.tail(window)
            row[f"total_quantity_rolling_mean_{window}"] = vals.mean()
            row[f"total_quantity_rolling_std_{window}"] = vals.std() if len(vals) > 1 else 0
            row[f"total_quantity_rolling_max_{window}"] = vals.max()
            row[f"total_quantity_rolling_min_{window}"] = vals.min()

        # EWM features
        for span in [7, 14]:
            row[f"total_quantity_ewm_{span}"] = qty.ewm(span=span).mean().iloc[-1]

        return row
