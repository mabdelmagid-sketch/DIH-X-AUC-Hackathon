from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error


def parse_datetime(series: pd.Series) -> pd.Series:
    if series.dtype == "datetime64[ns, UTC]":
        return series
    if series.dtype == object or pd.api.types.is_string_dtype(series):
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
        if parsed.notna().mean() >= 0.6:
            return parsed
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() < 0.6:
        return pd.Series(pd.NaT, index=series.index)
    max_value = numeric.dropna().max()
    if max_value > 1e12:
        return pd.to_datetime(numeric, unit="ms", errors="coerce", utc=True)
    return pd.to_datetime(numeric, unit="s", errors="coerce", utc=True)


def iqr_bounds(values: pd.Series, multiplier: float = 3.0) -> tuple[float, float]:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return (np.nan, np.nan)
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    return (q1 - multiplier * iqr, q3 + multiplier * iqr)


def sample_numeric_from_csv(
    path: Path,
    column: str,
    chunk_size: int,
    sample_per_chunk: int = 2000,
) -> pd.Series:
    samples = []
    for chunk in pd.read_csv(path, chunksize=chunk_size, low_memory=False):
        if column not in chunk.columns:
            continue
        col = pd.to_numeric(chunk[column], errors="coerce").dropna()
        if col.empty:
            continue
        if len(col) > sample_per_chunk:
            col = col.sample(n=sample_per_chunk, random_state=42)
        samples.append(col)
    if not samples:
        return pd.Series(dtype="float64")
    return pd.concat(samples, ignore_index=True)


@dataclass
class ModelConfig:
    chunk_size: int = 200_000
    horizon: int = 30
    min_history_days: int = 120
    top_places: int | None = None
    outlier_iqr_multiplier: float = 3.0


@dataclass
class PlaceMetrics:
    place_id: int
    mae: float
    mape: float
    baseline_mae: float
    baseline_mape: float
    train_days: int
    valid_days: int


def build_daily_place_aggregates(
    orders_path: Path,
    chunk_size: int,
    outlier_bounds: tuple[float, float],
) -> pd.DataFrame:
    daily_rows = []
    low, high = outlier_bounds

    for chunk in pd.read_csv(orders_path, chunksize=chunk_size, low_memory=False):
        if "place_id" not in chunk.columns:
            continue

        created = None
        if "created_dt" in chunk.columns:
            created = parse_datetime(chunk["created_dt"])
        elif "created" in chunk.columns:
            created = parse_datetime(chunk["created"])
        if created is None:
            continue

        chunk = chunk.copy()
        chunk["created_dt"] = created
        chunk["total_amount"] = pd.to_numeric(chunk.get("total_amount"), errors="coerce")

        if np.isfinite(low) and np.isfinite(high):
            chunk = chunk[chunk["total_amount"].between(low, high)]

        chunk["day"] = chunk["created_dt"].dt.date
        grouped = chunk.groupby(["place_id", "day"]).agg(
            revenue=("total_amount", "sum"),
            order_count=("id", "count"),
        )
        if not grouped.empty:
            grouped = grouped.reset_index()
            daily_rows.append(grouped)

    if not daily_rows:
        return pd.DataFrame(columns=["place_id", "day", "revenue", "order_count"])

    daily_df = pd.concat(daily_rows, ignore_index=True)
    daily_df = (
        daily_df.groupby(["place_id", "day"], as_index=False)
        .agg(revenue=("revenue", "sum"), order_count=("order_count", "sum"))
        .sort_values(["place_id", "day"])
    )
    return daily_df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day"] = pd.to_datetime(df["day"])
    df["dow"] = df["day"].dt.weekday
    df["month"] = df["day"].dt.month
    df["weekofyear"] = df["day"].dt.isocalendar().week.astype(int)
    return df


def add_lag_features(df: pd.DataFrame, lags: list[int]) -> pd.DataFrame:
    df = df.copy()
    for lag in lags:
        df[f"revenue_lag_{lag}"] = df.groupby("place_id")["revenue"].shift(lag)
        df[f"orders_lag_{lag}"] = df.groupby("place_id")["order_count"].shift(lag)
    return df


def add_rolling_features(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    df = df.copy()
    for window in windows:
        df[f"revenue_roll_{window}"] = (
            df.groupby("place_id")["revenue"].shift(1).rolling(window).mean()
        )
        df[f"orders_roll_{window}"] = (
            df.groupby("place_id")["order_count"].shift(1).rolling(window).mean()
        )
    return df


def train_place_model(place_df: pd.DataFrame) -> tuple[Ridge | None, pd.DataFrame]:
    features = [
        "dow",
        "month",
        "weekofyear",
        "revenue_lag_1",
        "revenue_lag_7",
        "revenue_lag_14",
        "revenue_lag_28",
        "orders_lag_1",
        "orders_lag_7",
        "orders_roll_7",
        "orders_roll_28",
        "revenue_roll_7",
        "revenue_roll_28",
    ]

    model_df = place_df.dropna(subset=features + ["revenue"]).copy()
    if model_df.empty:
        return None, model_df

    model = Ridge(alpha=1.0, random_state=42)
    model.fit(model_df[features], model_df["revenue"])
    return model, model_df


def baseline_forecast(series: pd.Series, horizon: int) -> np.ndarray:
    if series.empty:
        return np.zeros(horizon)
    last_week = series.tail(7)
    if len(last_week) < 7:
        return np.repeat(series.iloc[-1], horizon)
    return np.tile(last_week.to_numpy(), int(np.ceil(horizon / 7)))[:horizon]


def evaluate_place(place_df: pd.DataFrame, horizon: int) -> tuple[PlaceMetrics | None, pd.DataFrame]:
    place_df = place_df.sort_values("day").copy()
    if len(place_df) <= horizon + 30:
        return None, place_df

    split_point = place_df["day"].max() - pd.Timedelta(days=horizon)
    train_df = place_df[place_df["day"] <= split_point]
    valid_df = place_df[place_df["day"] > split_point]

    model, model_df = train_place_model(train_df)
    if model is None or model_df.empty:
        return None, place_df

    features = [
        "dow",
        "month",
        "weekofyear",
        "revenue_lag_1",
        "revenue_lag_7",
        "revenue_lag_14",
        "revenue_lag_28",
        "orders_lag_1",
        "orders_lag_7",
        "orders_roll_7",
        "orders_roll_28",
        "revenue_roll_7",
        "revenue_roll_28",
    ]

    valid_df = valid_df.dropna(subset=features + ["revenue"]).copy()
    if valid_df.empty:
        return None, place_df

    preds = model.predict(valid_df[features])
    mae = mean_absolute_error(valid_df["revenue"], preds)
    denom = valid_df["revenue"].replace(0, np.nan)
    mape = np.nanmean(np.abs((valid_df["revenue"] - preds) / denom))

    baseline_preds = baseline_forecast(train_df["revenue"], len(valid_df))
    baseline_mae = mean_absolute_error(valid_df["revenue"], baseline_preds)
    baseline_mape = np.nanmean(
        np.abs((valid_df["revenue"].to_numpy() - baseline_preds) / denom)
    )

    metrics = PlaceMetrics(
        place_id=int(place_df["place_id"].iloc[0]),
        mae=float(mae),
        mape=float(mape) if np.isfinite(mape) else np.nan,
        baseline_mae=float(baseline_mae),
        baseline_mape=float(baseline_mape) if np.isfinite(baseline_mape) else np.nan,
        train_days=len(train_df),
        valid_days=len(valid_df),
    )

    return metrics, place_df


def forecast_place(
    place_df: pd.DataFrame,
    model: Ridge | None,
    horizon: int,
) -> pd.DataFrame:
    place_df = place_df.sort_values("day").copy()
    last_day = place_df["day"].max()
    future_days = [last_day + pd.Timedelta(days=i) for i in range(1, horizon + 1)]

    history = place_df.copy()

    for day in future_days:
        new_row = {
            "place_id": place_df["place_id"].iloc[0],
            "day": day,
            "revenue": np.nan,
            "order_count": np.nan,
        }
        history = pd.concat([history, pd.DataFrame([new_row])], ignore_index=True)

        history = add_time_features(history)
        history = add_lag_features(history, [1, 7, 14, 28])
        history = add_rolling_features(history, [7, 28])

        current = history[history["day"] == day].copy()
        features = [
            "dow",
            "month",
            "weekofyear",
            "revenue_lag_1",
            "revenue_lag_7",
            "revenue_lag_14",
            "revenue_lag_28",
            "orders_lag_1",
            "orders_lag_7",
            "orders_roll_7",
            "orders_roll_28",
            "revenue_roll_7",
            "revenue_roll_28",
        ]

        if model is None or current[features].isna().any(axis=None):
            pred = baseline_forecast(place_df["revenue"], horizon=1)[0]
        else:
            pred = float(model.predict(current[features])[0])

        history.loc[history["day"] == day, "revenue"] = pred
        history.loc[history["day"] == day, "order_count"] = history.loc[
            history["day"] == day, "orders_lag_1"
        ]

    return history[history["day"].isin(future_days)][["place_id", "day", "revenue"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Train per-place revenue forecast model")
    parser.add_argument(
        "--orders-path",
        default="data/processed/clean/fct_orders.csv",
    )
    parser.add_argument("--output-dir", default="docs/forecast")
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--min-history", type=int, default=120)
    parser.add_argument("--top-places", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=200_000)
    args = parser.parse_args()

    config = ModelConfig(
        chunk_size=args.chunk_size,
        horizon=args.horizon,
        min_history_days=args.min_history,
        top_places=args.top_places or None,
    )

    orders_path = Path(args.orders_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sample = sample_numeric_from_csv(orders_path, "total_amount", config.chunk_size)
    bounds = iqr_bounds(sample, config.outlier_iqr_multiplier)

    daily_df = build_daily_place_aggregates(orders_path, config.chunk_size, bounds)
    daily_df = add_time_features(daily_df)
    daily_df = add_lag_features(daily_df, [1, 7, 14, 28])
    daily_df = add_rolling_features(daily_df, [7, 28])

    place_sizes = daily_df.groupby("place_id").size().sort_values(ascending=False)
    if config.top_places is not None:
        selected_places = set(place_sizes.head(config.top_places).index)
        daily_df = daily_df[daily_df["place_id"].isin(selected_places)]

    metrics = []
    forecasts = []

    for place_id, place_df in daily_df.groupby("place_id"):
        if len(place_df) < config.min_history_days:
            continue

        metric, _ = evaluate_place(place_df, config.horizon)
        if metric:
            metrics.append(metric.__dict__)

        model, _ = train_place_model(place_df)
        forecasts.append(forecast_place(place_df, model, config.horizon))

    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(output_dir / "place_metrics.csv", index=False)

    if forecasts:
        forecast_df = pd.concat(forecasts, ignore_index=True)
        forecast_df.to_csv(output_dir / "place_forecasts.csv", index=False)


if __name__ == "__main__":
    main()
