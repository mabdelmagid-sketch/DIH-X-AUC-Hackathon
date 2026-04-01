from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore")

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False


@dataclass
class ModelResult:
    model_name: str
    item_id: int
    item_name: str
    mae: float
    rmse: float
    mape: float
    r2: float
    stockout_rate: float
    overstock_rate: float
    shortage_units: float
    waste_units: float
    train_days: int
    valid_days: int


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
        if "item_id" not in chunk.columns or "quantity" not in chunk.columns:
            continue
        
        # Join with orders to get dates
        chunk = chunk.merge(orders_df, on="order_id", how="inner")
        
        # Aggregate quantities by item and day
        daily = chunk.groupby(["item_id", "day"])["quantity"].sum().reset_index()
        daily.rename(columns={"quantity": "demand"}, inplace=True)
        demand_data.append(daily)
    
    if not demand_data:
        return pd.DataFrame()
    
    demand_df = pd.concat(demand_data, ignore_index=True)
    demand_df = demand_df.groupby(["item_id", "day"], as_index=False)["demand"].sum()
    
    # Join with item names
    demand_df = demand_df.merge(items_df, on="item_id", how="left")
    demand_df["item_name"] = demand_df["item_name"].fillna("Unknown Item")
    
    demand_df = demand_df.sort_values(["item_id", "day"])
    
    return demand_df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day"] = pd.to_datetime(df["day"])
    df["dow"] = df["day"].dt.weekday
    df["month"] = df["day"].dt.month
    df["weekofyear"] = df["day"].dt.isocalendar().week.astype(int)
    df["day_of_month"] = df["day"].dt.day
    df["quarter"] = df["day"].dt.quarter
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df["is_month_start"] = (df["day_of_month"] <= 3).astype(int)
    df["is_month_end"] = (df["day_of_month"] >= 28).astype(int)
    return df


def add_lag_features(df: pd.DataFrame, lags: list[int]) -> pd.DataFrame:
    df = df.copy()
    for lag in lags:
        df[f"demand_lag_{lag}"] = df.groupby("item_id")["demand"].shift(lag)
    return df


def add_rolling_features(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    df = df.copy()
    for window in windows:
        df[f"demand_roll_mean_{window}"] = (
            df.groupby("item_id")["demand"].shift(1).rolling(window).mean()
        )
        df[f"demand_roll_std_{window}"] = (
            df.groupby("item_id")["demand"].shift(1).rolling(window).std()
        )
        df[f"demand_roll_max_{window}"] = (
            df.groupby("item_id")["demand"].shift(1).rolling(window).max()
        )
    return df


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """
    Calculate metrics including inventory-specific business metrics.
    
    Business Metrics:
    - Stockout Rate: % of days where prediction < actual (ran out of stock)
    - Overstock Rate: % of days where prediction > actual (excess inventory)
    - Waste Units: Total excess units predicted (overstock cost)
    - Shortage Units: Total shortage units (lost sales cost)
    """
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    
    mask = y_true != 0
    if mask.sum() > 0:
        mape = np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
    else:
        mape = np.nan
    
    r2 = r2_score(y_true, y_pred)
    
    # Business-specific metrics
    stockout_rate = (y_pred < y_true).sum() / len(y_true) * 100  # % days with stockout
    overstock_rate = (y_pred > y_true).sum() / len(y_true) * 100  # % days with excess
    
    shortage_units = np.maximum(y_true - y_pred, 0).sum()  # Total units short
    waste_units = np.maximum(y_pred - y_true, 0).sum()  # Total units excess
    
    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "mape": float(mape) if np.isfinite(mape) else np.nan,
        "r2": float(r2),
        "stockout_rate": float(stockout_rate),
        "overstock_rate": float(overstock_rate),
        "shortage_units": float(shortage_units),
        "waste_units": float(waste_units),
    }


def get_models() -> dict:
    """
    Get models with business-relevant loss functions for inventory management.
    
    Business Context:
    - Stockouts (underestimating demand) are MORE costly than overstocking
    - We use quantile regression to predict higher than median (safety stock)
    - 75th percentile = order enough to meet demand 75% of the time
    - 90th percentile = more conservative, less stockouts but more inventory
    """
    models = {}
    
    if LIGHTGBM_AVAILABLE:
        # MAE - Standard prediction (50th percentile)
        models["LightGBM_MAE"] = lgb.LGBMRegressor(
            objective="mae",
            n_estimators=200,
            max_depth=10,
            learning_rate=0.05,
            num_leaves=31,
            random_state=42,
            verbose=-1,
        )
        
        # Quantile 0.75 - Predict 75th percentile (built-in safety stock)
        models["LightGBM_Q75"] = lgb.LGBMRegressor(
            objective="quantile",
            alpha=0.75,  # 75th percentile
            n_estimators=200,
            max_depth=10,
            learning_rate=0.05,
            num_leaves=31,
            random_state=42,
            verbose=-1,
        )
        
        # Quantile 0.90 - Conservative (90th percentile)
        models["LightGBM_Q90"] = lgb.LGBMRegressor(
            objective="quantile",
            alpha=0.90,  # 90th percentile
            n_estimators=200,
            max_depth=10,
            learning_rate=0.05,
            num_leaves=31,
            random_state=42,
            verbose=-1,
        )
    
    if XGBOOST_AVAILABLE:
        # MAE - Standard
        models["XGBoost_MAE"] = xgb.XGBRegressor(
            objective="reg:absoluteerror",
            n_estimators=200,
            max_depth=10,
            learning_rate=0.05,
            random_state=42,
            verbosity=0,
        )
        
        # Quantile 0.75
        models["XGBoost_Q75"] = xgb.XGBRegressor(
            objective="reg:quantileerror",
            quantile_alpha=0.75,
            n_estimators=200,
            max_depth=10,
            learning_rate=0.05,
            random_state=42,
            verbosity=0,
        )
    
    return models


def evaluate_item_forecast(
    item_df: pd.DataFrame,
    features: list[str],
    horizon: int = 30,
) -> list[ModelResult]:
    """Evaluate forecasting models for a single item"""
    
    item_df = item_df.sort_values("day").copy()
    item_id = int(item_df["item_id"].iloc[0])
    item_name = str(item_df["item_name"].iloc[0])
    
    # Split train/test
    split_idx = len(item_df) - horizon
    train_df = item_df.iloc[:split_idx]
    test_df = item_df.iloc[split_idx:]
    
    if len(train_df) < 60 or len(test_df) == 0:
        return []
    
    results = []
    models = get_models()
    
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
            preds = np.maximum(preds, 0)  # Demand can't be negative
            
            # Evaluate
            metrics = calculate_metrics(test_clean["demand"].values, preds)
            
            results.append(
                ModelResult(
                    model_name=model_name,
                    item_id=item_id,
                    item_name=item_name,
                    train_days=len(train_df),
                    valid_days=len(test_df),
                    **metrics,
                )
            )
        
        except Exception as e:
            continue
    
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory demand forecasting")
    parser.add_argument("--order-items-path", default="data/Inventory Management/fct_order_items.csv")
    parser.add_argument("--orders-path", default="data/Inventory Management/fct_orders.csv")
    parser.add_argument("--items-path", default="data/Inventory Management/dim_items.csv")
    parser.add_argument("--output-dir", default="docs/forecast")
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--min-history", type=int, default=60)
    parser.add_argument("--top-items", type=int, default=None, help="Number of top items (None = all items with min history)")
    parser.add_argument("--min-demand", type=int, default=20, help="Minimum total demand to include item")
    parser.add_argument("--chunk-size", type=int, default=100_000)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*80)
    print("INVENTORY DEMAND FORECASTING")
    print("="*80)
    print("\nObjective: Predict daily quantity needed for each item")
    print("-"*80)

    print("\n1. Building daily item demand data...")
    demand_df = build_item_demand_data(
        Path(args.order_items_path),
        Path(args.orders_path),
        Path(args.items_path),
        args.chunk_size,
    )
    
    if demand_df.empty:
        print("No demand data generated.")
        return
    
    print(f"   ✓ Loaded {len(demand_df)} demand records")
    print(f"   ✓ {demand_df['item_id'].nunique()} unique items")
    print(f"   ✓ Date range: {demand_df['day'].min()} to {demand_df['day'].max()}")
    
    print("\n2. Engineering features...")
    demand_df = add_time_features(demand_df)
    demand_df = add_lag_features(demand_df, [1, 2, 3, 7, 14, 21, 28])
    demand_df = add_rolling_features(demand_df, [7, 14, 28])
    
    # Select items based on criteria
    item_stats = demand_df.groupby("item_id").agg({
        "demand": ["sum", "count"]
    })
    item_stats.columns = ["total_demand", "num_days"]
    
    # Filter by minimum demand and minimum history
    eligible_items = item_stats[
        (item_stats["total_demand"] >= args.min_demand) &
        (item_stats["num_days"] >= args.min_history)
    ].sort_values("total_demand", ascending=False)
    
    # Optionally limit to top N items
    if args.top_items is not None:
        eligible_items = eligible_items.head(args.top_items)
    
    selected_items = eligible_items.index
    demand_df = demand_df[demand_df["item_id"].isin(selected_items)]
    
    features = [
        col for col in demand_df.columns
        if col not in ["item_id", "item_name", "day", "demand"]
    ]
    
    print(f"   ✓ {len(features)} features engineered")
    print(f"   ✓ Evaluating on {len(selected_items)} items (min demand: {args.min_demand}, min history: {args.min_history} days)")
    print(f"   ✓ Total eligible items: {len(eligible_items)}")
    
    print("\n3. Training and evaluating models...")
    print("-"*80)
    
    all_results = []
    total_items = len(selected_items)
    
    for i, (item_id, item_df) in enumerate(demand_df.groupby("item_id"), 1):
        if len(item_df) < args.min_history:
            continue
        
        item_name = item_df["item_name"].iloc[0]
        total_demand = item_df["demand"].sum()
        
        if i % 10 == 0 or i <= 20:
            print(f"  Item {i}/{total_items}: {item_name[:40]} (Total: {total_demand:.0f} units)")
        elif i % 50 == 0:
            print(f"  ... processed {i}/{total_items} items ...")
        
        results = evaluate_item_forecast(item_df, features, args.horizon)
        all_results.extend(results)
    
    if not all_results:
        print("\nNo results generated.")
        return
    
    # Save results
    results_df = pd.DataFrame([r.__dict__ for r in all_results])
    results_df.to_csv(output_dir / "inventory_forecast_results.csv", index=False)
    
    # Summary
    summary = results_df.groupby("model_name")[["mae", "rmse", "mape", "stockout_rate", "overstock_rate"]].agg(["mean", "std"])
    summary.to_csv(output_dir / "inventory_forecast_summary.csv")
    
    print("\n" + "="*80)
    print("INVENTORY FORECAST PERFORMANCE:")
    print("="*80)
    print(summary.round(2))
    
    # Business impact summary
    print("\n" + "="*80)
    print("BUSINESS IMPACT ANALYSIS:")
    print("="*80)
    
    for model_name in results_df["model_name"].unique():
        model_results = results_df[results_df["model_name"] == model_name]
        print(f"\n{model_name}:")
        print(f"  Stockout Days: {model_results['stockout_rate'].mean():.1f}% (days running out)")
        print(f"  Overstock Days: {model_results['overstock_rate'].mean():.1f}% (days with excess)")
        print(f"  Avg Shortage: {model_results['shortage_units'].mean():.1f} units (lost sales)")
        print(f"  Avg Waste: {model_results['waste_units'].mean():.1f} units (excess inventory)")
    
    # Additional statistics
    print("\n" + "-"*80)
    print(f"TRAINING SUMMARY:")
    print("-"*80)
    print(f"  Total items trained: {results_df['item_id'].nunique()}")
    print(f"  Total predictions: {len(results_df)}")
    print(f"  Items with MAE < 5 units: {(results_df['mae'] < 5).sum() / len(results_df) * 100:.1f}%")
    print(f"  Items with MAE < 10 units: {(results_df['mae'] < 10).sum() / len(results_df) * 100:.1f}%")
    print(f"  Items with stockout < 30%: {(results_df['stockout_rate'] < 30).sum() / len(results_df) * 100:.1f}%")
    
    # Top items with best forecast accuracy
    print("\n" + "-"*80)
    print("TOP 10 ITEMS WITH LOWEST STOCKOUT RATE:")
    print("-"*80)
    
    best_items = results_df.sort_values("stockout_rate").head(10)[["item_name", "model_name", "mae", "stockout_rate", "overstock_rate"]]
    print(best_items.to_string(index=False))
    
    # Worst items for review
    print("\n" + "-"*80)
    print("TOP 10 ITEMS WITH HIGHEST STOCKOUT RATE (needs attention):")
    print("-"*80)
    
    worst_items = results_df.sort_values("stockout_rate", ascending=False).head(10)[["item_name", "model_name", "mae", "stockout_rate", "shortage_units"]]
    print(worst_items.to_string(index=False))
    
    print(f"\nResults saved to {output_dir}")
    
    # Model recommendation
    print("\n" + "="*80)
    print("BUSINESS RECOMMENDATION:")
    print("="*80)
    
    # Find model with lowest stockout rate
    best_model = results_df.groupby("model_name")["stockout_rate"].mean().sort_values().index[0]
    best_stats = results_df[results_df["model_name"] == best_model]
    
    print(f"\n🎯 RECOMMENDED MODEL: {best_model}")
    print(f"   → Stockout Rate: {best_stats['stockout_rate'].mean():.1f}% (minimize lost sales)")
    print(f"   → MAE: {best_stats['mae'].mean():.2f} units")
    print(f"   → Use for: Production ordering system")
    print(f"\n💡 INTERPRETATION:")
    
    if "Q75" in best_model or "Q90" in best_model:
        print("   Quantile models predict HIGHER than average to build safety stock")
        print("   → Reduces stockouts but increases holding costs")
    else:
        print("   MAE models predict median demand")
        print("   → Balanced approach between stockouts and overstocking")
    print("="*80)


if __name__ == "__main__":
    main()
