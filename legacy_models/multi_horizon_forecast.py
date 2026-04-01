"""
Multi-Horizon Inventory Forecasting
Predicts menu item demand for 1 day, 7 days, and 30 days ahead
"""
from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    print("⚠️  LightGBM not available")

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("⚠️  XGBoost not available")


@dataclass
class ForecastResult:
    item_id: int
    item_name: str
    horizon: int  # 1, 7, or 30 days
    model_name: str
    mae: float
    rmse: float
    mape: float
    stockout_rate: float
    overstock_rate: float
    shortage_units: float
    waste_units: float
    predictions: list[float]
    actuals: list[float]


def parse_datetime(series: pd.Series) -> pd.Series:
    """Robust datetime parsing"""
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


def build_item_demand_data(
    order_items_path: Path,
    orders_path: Path,
    items_path: Path,
    chunk_size: int = 100_000,
) -> pd.DataFrame:
    """Build daily item demand from order items"""
    
    print("  Loading items catalog...")
    items_df = pd.read_csv(items_path, low_memory=False)
    items_df = items_df[["id", "title"]].rename(columns={"id": "item_id", "title": "item_name"})
    
    print("  Loading order timestamps...")
    orders_data = []
    for chunk in pd.read_csv(orders_path, chunksize=chunk_size, low_memory=False, usecols=["id", "created"]):
        created = parse_datetime(chunk["created"])
        chunk["created_dt"] = created
        chunk["day"] = created.dt.date
        orders_data.append(chunk[["id", "day"]].rename(columns={"id": "order_id"}))
    
    orders_df = pd.concat(orders_data, ignore_index=True)
    orders_df = orders_df.dropna(subset=["day"])
    
    print("  Processing order items to get daily demand...")
    demand_data = []
    for chunk in pd.read_csv(order_items_path, chunksize=chunk_size, low_memory=False):
        chunk = chunk[["order_id", "item_id", "quantity"]].copy()
        chunk = chunk.merge(orders_df, on="order_id", how="inner")
        chunk = chunk.groupby(["day", "item_id"])["quantity"].sum().reset_index()
        chunk.rename(columns={"quantity": "demand"}, inplace=True)
        demand_data.append(chunk)
    
    demand_df = pd.concat(demand_data, ignore_index=True)
    demand_df = demand_df.groupby(["day", "item_id"])["demand"].sum().reset_index()
    demand_df = demand_df.merge(items_df, on="item_id", how="left")
    demand_df["day"] = pd.to_datetime(demand_df["day"])
    
    print(f"   ✓ Loaded {len(demand_df):,} demand records")
    print(f"   ✓ {demand_df['item_id'].nunique():,} unique items")
    print(f"   ✓ Date range: {demand_df['day'].min().date()} to {demand_df['day'].max().date()}")
    
    return demand_df


def engineer_features(demand_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Engineer time-based features for forecasting"""
    
    df = demand_df.copy()
    df = df.sort_values(["item_id", "day"])
    
    # Time features
    df["dow"] = df["day"].dt.dayofweek
    df["dom"] = df["day"].dt.day
    df["month"] = df["day"].dt.month
    df["quarter"] = df["day"].dt.quarter
    df["week_of_year"] = df["day"].dt.isocalendar().week
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df["is_month_start"] = (df["dom"] <= 7).astype(int)
    df["is_month_end"] = (df["dom"] >= 24).astype(int)
    
    # Lag features (per item)
    for lag in [1, 2, 3, 7, 14, 21, 28]:
        df[f"demand_lag_{lag}"] = df.groupby("item_id")["demand"].shift(lag)
    
    # Rolling features (per item)
    for window in [7, 14, 28]:
        df[f"demand_rolling_mean_{window}"] = (
            df.groupby("item_id")["demand"]
            .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
        )
        df[f"demand_rolling_std_{window}"] = (
            df.groupby("item_id")["demand"]
            .transform(lambda x: x.shift(1).rolling(window, min_periods=1).std())
        )
    
    features = [
        "dow", "dom", "month", "quarter", "week_of_year",
        "is_weekend", "is_month_start", "is_month_end",
    ] + [col for col in df.columns if "lag_" in col or "rolling_" in col]
    
    return df, features


def get_models(objective: Literal["mae", "q75", "q90"] = "q90") -> dict:
    """Get forecasting models based on objective"""
    models = {}
    
    if LIGHTGBM_AVAILABLE:
        if objective == "mae":
            models["LightGBM"] = lgb.LGBMRegressor(
                objective="mae",
                n_estimators=200,
                max_depth=10,
                learning_rate=0.05,
                num_leaves=31,
                random_state=42,
                verbose=-1,
            )
        elif objective == "q75":
            models["LightGBM"] = lgb.LGBMRegressor(
                objective="quantile",
                alpha=0.75,
                n_estimators=200,
                max_depth=10,
                learning_rate=0.05,
                num_leaves=31,
                random_state=42,
                verbose=-1,
            )
        elif objective == "q90":
            models["LightGBM"] = lgb.LGBMRegressor(
                objective="quantile",
                alpha=0.90,
                n_estimators=200,
                max_depth=10,
                learning_rate=0.05,
                num_leaves=31,
                random_state=42,
                verbose=-1,
            )
    
    if XGBOOST_AVAILABLE:
        if objective == "mae":
            models["XGBoost"] = xgb.XGBRegressor(
                objective="reg:absoluteerror",
                n_estimators=200,
                max_depth=10,
                learning_rate=0.05,
                random_state=42,
                verbosity=0,
            )
        elif objective == "q75":
            models["XGBoost"] = xgb.XGBRegressor(
                objective="reg:quantileerror",
                quantile_alpha=0.75,
                n_estimators=200,
                max_depth=10,
                learning_rate=0.05,
                random_state=42,
                verbosity=0,
            )
        elif objective == "q90":
            models["XGBoost"] = xgb.XGBRegressor(
                objective="reg:quantileerror",
                quantile_alpha=0.90,
                n_estimators=200,
                max_depth=10,
                learning_rate=0.05,
                random_state=42,
                verbosity=0,
            )
    
    return models


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Calculate forecasting metrics including business metrics"""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    
    # MAPE (avoid division by zero)
    mape = np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 1))) * 100
    
    # Business metrics
    stockout_rate = (y_pred < y_true).sum() / len(y_true) * 100
    overstock_rate = (y_pred > y_true).sum() / len(y_true) * 100
    shortage_units = np.maximum(y_true - y_pred, 0).sum()
    waste_units = np.maximum(y_pred - y_true, 0).sum()
    
    return {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "stockout_rate": stockout_rate,
        "overstock_rate": overstock_rate,
        "shortage_units": shortage_units,
        "waste_units": waste_units,
    }


def forecast_item_multi_horizon(
    item_df: pd.DataFrame,
    features: list[str],
    horizons: list[int] = [1, 7, 30],
    objective: Literal["mae", "q75", "q90"] = "q90",
) -> list[ForecastResult]:
    """Forecast item demand for multiple horizons (1, 7, 30 days)"""
    
    item_df = item_df.sort_values("day").copy()
    item_id = int(item_df["item_id"].iloc[0])
    item_name = str(item_df["item_name"].iloc[0])
    
    results = []
    models = get_models(objective)
    
    for horizon in horizons:
        # Split train/test
        split_idx = len(item_df) - horizon
        train_df = item_df.iloc[:split_idx]
        test_df = item_df.iloc[split_idx:]
        
        if len(train_df) < 60 or len(test_df) < horizon:
            continue
        
        for model_name, model in models.items():
            try:
                # Prepare data
                train_clean = train_df.dropna(subset=features + ["demand"])
                test_clean = test_df.dropna(subset=features + ["demand"])
                
                if len(train_clean) < 30 or len(test_clean) == 0:
                    continue
                
                # Train
                model.fit(train_clean[features], train_clean["demand"])
                
                # Predict
                preds = model.predict(test_clean[features])
                preds = np.maximum(preds, 0)  # Non-negative
                
                # Calculate metrics
                metrics = calculate_metrics(test_clean["demand"].values, preds)
                
                results.append(ForecastResult(
                    item_id=item_id,
                    item_name=item_name,
                    horizon=horizon,
                    model_name=model_name,
                    predictions=preds.tolist(),
                    actuals=test_clean["demand"].tolist(),
                    **metrics,
                ))
            except Exception as e:
                continue
    
    return results


def main(
    min_demand: int = 50,
    min_history: int = 90,
    max_items: int | None = None,
    objective: Literal["mae", "q75", "q90"] = "q90",
):
    """Run multi-horizon forecasting for menu items"""
    
    root = Path(__file__).parent.parent.parent
    data_dir = root / "data" / "Inventory Management"
    output_dir = root / "docs" / "forecast"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("MULTI-HORIZON MENU ITEM FORECASTING")
    print("=" * 80)
    print(f"\nObjective: Predict daily menu item demand for 1, 7, and 30 days ahead")
    print(f"Model Type: {objective.upper()} (Q90 = Conservative, minimizes stockouts)")
    print("-" * 80)
    
    # Build demand data
    print("\n1. Building daily item demand data...")
    demand_df = build_item_demand_data(
        order_items_path=data_dir / "fct_order_items.csv",
        orders_path=data_dir / "fct_orders.csv",
        items_path=data_dir / "dim_items.csv",
    )
    
    # Engineer features
    print("\n2. Engineering features...")
    df, features = engineer_features(demand_df)
    print(f"   ✓ {len(features)} features engineered")
    
    # Filter items
    item_stats = df.groupby("item_id").agg({
        "demand": ["sum", "count"],
        "item_name": "first"
    }).reset_index()
    item_stats.columns = ["item_id", "total_demand", "days", "item_name"]
    
    eligible_items = item_stats[
        (item_stats["total_demand"] >= min_demand) &
        (item_stats["days"] >= min_history)
    ].sort_values("total_demand", ascending=False)
    
    if max_items:
        eligible_items = eligible_items.head(max_items)
    
    print(f"   ✓ Evaluating on {len(eligible_items)} items (min demand: {min_demand}, min history: {min_history} days)")
    
    # Forecast for each item
    print(f"\n3. Forecasting for horizons: 1-day, 7-day, 30-day...")
    print("-" * 80)
    
    all_results = []
    for idx, row in enumerate(eligible_items.itertuples(), 1):
        item_df = df[df["item_id"] == row.item_id].copy()
        
        if idx % 10 == 0 or idx <= 20:
            print(f"  Item {idx}/{len(eligible_items)}: {row.item_name} (Total: {int(row.total_demand)} units)")
        
        results = forecast_item_multi_horizon(
            item_df=item_df,
            features=features,
            horizons=[1, 7, 30],
            objective=objective,
        )
        all_results.extend(results)
    
    if not all_results:
        print("\n⚠️  No valid forecasts generated. Adjust min_demand or min_history.")
        return
    
    # Convert to DataFrame
    results_df = pd.DataFrame([
        {
            "item_id": r.item_id,
            "item_name": r.item_name,
            "horizon_days": r.horizon,
            "model_name": r.model_name,
            "mae": r.mae,
            "rmse": r.rmse,
            "mape": r.mape,
            "stockout_rate": r.stockout_rate,
            "overstock_rate": r.overstock_rate,
            "shortage_units": r.shortage_units,
            "waste_units": r.waste_units,
        }
        for r in all_results
    ])
    
    # Summary by horizon
    print("\n" + "=" * 80)
    print("FORECAST PERFORMANCE BY HORIZON:")
    print("=" * 80)
    
    summary = results_df.groupby(["horizon_days", "model_name"]).agg({
        "mae": ["mean", "std"],
        "stockout_rate": ["mean", "std"],
        "overstock_rate": ["mean", "std"],
        "shortage_units": ["mean"],
        "waste_units": ["mean"],
    }).round(2)
    
    print(summary)
    
    # Detailed analysis
    print("\n" + "=" * 80)
    print("BUSINESS IMPACT BY HORIZON:")
    print("=" * 80)
    
    for horizon in [1, 7, 30]:
        horizon_data = results_df[results_df["horizon_days"] == horizon]
        if len(horizon_data) == 0:
            continue
        
        print(f"\n📅 {horizon}-DAY FORECAST:")
        for model in horizon_data["model_name"].unique():
            model_data = horizon_data[horizon_data["model_name"] == model]
            print(f"\n  {model}:")
            print(f"    Stockout Rate: {model_data['stockout_rate'].mean():.1f}%")
            print(f"    Overstock Rate: {model_data['overstock_rate'].mean():.1f}%")
            print(f"    Avg Shortage: {model_data['shortage_units'].mean():.1f} units")
            print(f"    Avg Waste: {model_data['waste_units'].mean():.1f} units")
            print(f"    MAE: {model_data['mae'].mean():.2f} units")
    
    # Save results
    results_path = output_dir / "menu_forecast_multi_horizon.csv"
    results_df.to_csv(results_path, index=False)
    
    summary_path = output_dir / "menu_forecast_summary.csv"
    summary.to_csv(summary_path)
    
    print("\n" + "-" * 80)
    print(f"Results saved to {output_dir.relative_to(root)}/")
    print(f"  - menu_forecast_multi_horizon.csv (detailed predictions)")
    print(f"  - menu_forecast_summary.csv (summary by horizon)")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION:")
    print("=" * 80)
    print(f"🎯 Using {objective.upper()} objective for business-relevant forecasting")
    print(f"   → 1-day: Daily ordering decisions")
    print(f"   → 7-day: Weekly inventory planning")
    print(f"   → 30-day: Monthly procurement & budgeting")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-horizon menu item forecasting")
    parser.add_argument("--min-demand", type=int, default=50, help="Minimum total demand")
    parser.add_argument("--min-history", type=int, default=90, help="Minimum days of history")
    parser.add_argument("--max-items", type=int, default=None, help="Max items to forecast")
    parser.add_argument("--objective", type=str, default="q90", choices=["mae", "q75", "q90"], help="Model objective")
    
    args = parser.parse_args()
    
    main(
        min_demand=args.min_demand,
        min_history=args.min_history,
        max_items=args.max_items,
        objective=args.objective,
    )
