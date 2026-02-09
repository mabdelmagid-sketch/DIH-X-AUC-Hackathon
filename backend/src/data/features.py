"""
Feature Engineering for Demand Forecasting
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional


class FeatureEngineer:
    """Build features for demand forecasting"""

    def __init__(self):
        self.feature_columns = []

    def create_time_features(self, df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
        """Extract time-based features from date column"""
        df = df.copy()

        # Ensure datetime
        if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
            df[date_col] = pd.to_datetime(df[date_col])

        # Time features
        df["day_of_week"] = df[date_col].dt.dayofweek  # 0=Monday
        df["day_of_month"] = df[date_col].dt.day
        df["month"] = df[date_col].dt.month
        df["week_of_year"] = df[date_col].dt.isocalendar().week.astype(int)
        df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
        df["is_month_start"] = df[date_col].dt.is_month_start.astype(int)
        df["is_month_end"] = df[date_col].dt.is_month_end.astype(int)

        # Quarter
        df["quarter"] = df[date_col].dt.quarter

        # Cyclical encoding for day of week and month
        df["day_of_week_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["day_of_week_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

        return df

    def create_lag_features(
        self,
        df: pd.DataFrame,
        target_col: str,
        group_col: Optional[str] = None,
        lags: list[int] = [1, 7, 14, 28]
    ) -> pd.DataFrame:
        """Create lagged features for time series"""
        df = df.copy()

        for lag in lags:
            col_name = f"{target_col}_lag_{lag}"
            if group_col:
                df[col_name] = df.groupby(group_col)[target_col].shift(lag)
            else:
                df[col_name] = df[target_col].shift(lag)

        return df

    def create_rolling_features(
        self,
        df: pd.DataFrame,
        target_col: str,
        group_col: Optional[str] = None,
        windows: list[int] = [7, 14, 30]
    ) -> pd.DataFrame:
        """Create rolling window statistics"""
        df = df.copy()

        for window in windows:
            if group_col:
                grouped = df.groupby(group_col)[target_col]
                df[f"{target_col}_rolling_mean_{window}"] = grouped.transform(
                    lambda x: x.shift(1).rolling(window, min_periods=1).mean()
                )
                df[f"{target_col}_rolling_std_{window}"] = grouped.transform(
                    lambda x: x.shift(1).rolling(window, min_periods=1).std()
                )
                df[f"{target_col}_rolling_max_{window}"] = grouped.transform(
                    lambda x: x.shift(1).rolling(window, min_periods=1).max()
                )
                df[f"{target_col}_rolling_min_{window}"] = grouped.transform(
                    lambda x: x.shift(1).rolling(window, min_periods=1).min()
                )
            else:
                shifted = df[target_col].shift(1)
                df[f"{target_col}_rolling_mean_{window}"] = shifted.rolling(window, min_periods=1).mean()
                df[f"{target_col}_rolling_std_{window}"] = shifted.rolling(window, min_periods=1).std()
                df[f"{target_col}_rolling_max_{window}"] = shifted.rolling(window, min_periods=1).max()
                df[f"{target_col}_rolling_min_{window}"] = shifted.rolling(window, min_periods=1).min()

        return df

    def create_ewm_features(
        self,
        df: pd.DataFrame,
        target_col: str,
        group_col: Optional[str] = None,
        spans: list[int] = [7, 14, 30]
    ) -> pd.DataFrame:
        """Create exponentially weighted moving average features"""
        df = df.copy()

        for span in spans:
            col_name = f"{target_col}_ewm_{span}"
            if group_col:
                df[col_name] = df.groupby(group_col)[target_col].transform(
                    lambda x: x.shift(1).ewm(span=span, min_periods=1).mean()
                )
            else:
                df[col_name] = df[target_col].shift(1).ewm(span=span, min_periods=1).mean()

        return df

    def build_forecast_features(
        self,
        daily_sales: pd.DataFrame,
        target_col: str = "total_quantity",
        group_col: str = "item_title",
        date_col: str = "date"
    ) -> pd.DataFrame:
        """Build complete feature set for forecasting"""

        # Sort by group and date
        df = daily_sales.sort_values([group_col, date_col]).copy()

        # Time features
        df = self.create_time_features(df, date_col)

        # Lag features
        df = self.create_lag_features(df, target_col, group_col, lags=[1, 7, 14, 28])

        # Rolling features
        df = self.create_rolling_features(df, target_col, group_col, windows=[7, 14, 30])

        # EWM features
        df = self.create_ewm_features(df, target_col, group_col, spans=[7, 14])

        # Store feature columns (excluding target, date, and group)
        exclude_cols = {target_col, date_col, group_col, "total_revenue", "order_count"}
        self.feature_columns = [c for c in df.columns if c not in exclude_cols]

        return df

    def get_feature_columns(self) -> list[str]:
        """Return list of feature column names"""
        return self.feature_columns

    def prepare_training_data(
        self,
        df: pd.DataFrame,
        target_col: str = "total_quantity",
        dropna: bool = True
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Prepare X and y for model training"""
        if not self.feature_columns:
            raise ValueError("Run build_forecast_features first")

        if dropna:
            df = df.dropna(subset=self.feature_columns + [target_col])

        X = df[self.feature_columns].copy()
        y = df[target_col].copy()

        # Fill any remaining NaN with 0
        X = X.fillna(0)

        return X, y
