"""
Walk-forward validation for a single restaurant.
Retrain every 3 days, predict next 3 days.
Test different window sizes and recency weights.
"""

import sys
import time
import json
import sqlite3
import gc
import warnings
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder
import lightgbm as lgb

warnings.filterwarnings("ignore")

DB_PATH = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/production.db"
STORE_ID = "5995723"  # Zeynos
TOP_N_ITEMS = 30
WASTE_FRACTION = 0.3
STOCKOUT_MULT = 1.5
RETRAIN_EVERY = 3  # days

# Load shelf life
SHELF_PATH = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/production_shelf_life_final.csv"
shelf_df = pd.read_csv(SHELF_PATH)
SHELF_LOOKUP = {}
for _, row in shelf_df.iterrows():
    iid = str(row["item_id"])
    sl = float(row["shelf_life_days"]) if pd.notna(row["shelf_life_days"]) else 3.0
    ag = float(row["avg_gap_days"]) if pd.notna(row["avg_gap_days"]) else 1.0
    SHELF_LOOKUP[iid] = (sl, ag)

def effective_waste_fraction(item_id):
    sl, ag = SHELF_LOOKUP.get(str(item_id), (3.0, 1.0))
    if sl >= 9999: return 0.0
    sl = max(sl, 0.5)
    return WASTE_FRACTION * min(1.0, ag / sl)


def load_store_data():
    conn = sqlite3.connect(DB_PATH)
    orders = pd.read_sql("SELECT id, place_id, created, status FROM fct_orders", conn)
    items = pd.read_sql("SELECT item_id, order_id, quantity, cost, title FROM fct_order_items", conn)
    menu = pd.read_sql("SELECT id, price FROM dim_menu_items", conn)
    conn.close()

    orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
    orders["total_amount"] = 0
    items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
    items["cost"] = pd.to_numeric(items["cost"], errors="coerce")
    menu["price"] = pd.to_numeric(menu["price"], errors="coerce")
    orders = orders[orders["status"] == "Closed"]
    orders["date"] = pd.to_datetime(orders["created"], unit="s", errors="coerce").dt.normalize()

    # Single store
    orders = orders[orders["place_id"] == STORE_ID]
    merged = items.merge(orders[["id", "place_id", "date"]], left_on="order_id", right_on="id", how="inner")

    daily = merged.groupby(["date", "place_id", "item_id"]).agg(
        quantity_sold=("quantity", "sum"), revenue=("cost", "sum")
    ).reset_index()

    # Top N items
    top = daily.groupby("item_id")["quantity_sold"].sum().reset_index().sort_values("quantity_sold", ascending=False).head(TOP_N_ITEMS)
    daily = daily[daily["item_id"].isin(top["item_id"])]

    # Item prices from menu
    item_prices = menu.rename(columns={"id": "item_id", "price": "item_price"})
    daily = daily.merge(item_prices, on="item_id", how="left")
    daily["item_price"] = daily["item_price"].fillna(75.0)

    # Modal price per item
    modal = daily.groupby("item_id")["item_price"].agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 75.0).reset_index()
    modal.columns = ["item_id", "modal_price"]

    # Complete date grid
    all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    items_list = daily["item_id"].unique()
    grid = pd.MultiIndex.from_product([items_list, all_dates], names=["item_id", "date"]).to_frame(index=False)
    grid["place_id"] = STORE_ID
    grid = grid.merge(daily[["date", "item_id", "quantity_sold", "revenue"]], on=["date", "item_id"], how="left")
    grid = grid.merge(modal, on="item_id", how="left")
    grid.rename(columns={"modal_price": "item_price"}, inplace=True)
    grid["item_price"] = grid["item_price"].fillna(75.0)
    grid["quantity_sold"] = grid["quantity_sold"].fillna(0)
    grid["revenue"] = grid["revenue"].fillna(0)
    grid = grid.sort_values(["item_id", "date"]).reset_index(drop=True)

    print(f"Store {STORE_ID}: {len(items_list)} items, {len(all_dates)} days, {len(grid)} rows")
    return grid, all_dates


def engineer_features(df):
    """Lightweight features for single-store model."""
    df = df.copy()
    grp = ["item_id"]

    # Time
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_of_month"] = df["date"].dt.day
    df["month"] = df["date"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["is_friday"] = (df["day_of_week"] == 4).astype(int)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

    # Lags
    for lag in [1, 3, 7, 14]:
        df[f"lag_{lag}d"] = df.groupby(grp)["quantity_sold"].shift(lag)

    # Same weekday last week
    df["same_dow_1w"] = df.groupby(grp)["quantity_sold"].shift(7)
    df["same_dow_2w"] = df.groupby(grp)["quantity_sold"].shift(14)

    # Rolling
    shifted = df.groupby(grp)["quantity_sold"].shift(1)
    for w in [3, 7, 14]:
        df[f"roll_mean_{w}d"] = shifted.groupby(df["item_id"]).transform(
            lambda x: x.rolling(w, min_periods=1).mean()
        )
    df[f"roll_std_7d"] = shifted.groupby(df["item_id"]).transform(
        lambda x: x.rolling(7, min_periods=2).std()
    )

    # Expanding mean
    df["expanding_mean"] = df.groupby(grp)["quantity_sold"].expanding().mean().reset_index(level=0, drop=True)

    # Trend
    df["days_since_start"] = (df["date"] - df["date"].min()).dt.days
    df["recent_vs_expand"] = (df["roll_mean_7d"] / df["expanding_mean"].clip(lower=0.01)).clip(0, 10).fillna(1)

    # Item encoding
    le = LabelEncoder()
    df["item_encoded"] = le.fit_transform(df["item_id"].astype(str))

    feature_cols = [
        "day_of_week", "day_of_month", "month", "is_weekend", "is_friday",
        "dow_sin", "dow_cos",
        "lag_1d", "lag_3d", "lag_7d", "lag_14d",
        "same_dow_1w", "same_dow_2w",
        "roll_mean_3d", "roll_mean_7d", "roll_mean_14d", "roll_std_7d",
        "expanding_mean", "days_since_start", "recent_vs_expand",
        "item_encoded",
    ]
    return df, feature_cols


def evaluate_predictions(actuals, predictions, prices, item_ids):
    a = np.array(actuals, dtype=float)
    p = np.clip(np.array(predictions, dtype=float), 0, None)
    pr = np.array(prices, dtype=float)

    mae = np.abs(a - p).mean()
    overstock = np.maximum(p - a, 0)
    understock = np.maximum(a - p, 0)
    waste_fracs = np.array([effective_waste_fraction(iid) for iid in item_ids])
    waste = (overstock * pr * waste_fracs).sum()
    stockout = (understock * pr).sum()
    cost = waste + STOCKOUT_MULT * stockout
    return mae, cost, waste, stockout


def walk_forward(df, feature_cols, window_days, decay_hl, safety_buffer, min_train_days=30):
    """Walk-forward: retrain every RETRAIN_EVERY days, predict next RETRAIN_EVERY days."""
    all_dates = sorted(df["date"].unique())
    start_idx = min_train_days  # need at least this many days to start

    all_preds = []
    all_actuals = []
    all_prices = []
    all_item_ids = []
    n_retrains = 0

    for pred_start in range(start_idx, len(all_dates), RETRAIN_EVERY):
        pred_end = min(pred_start + RETRAIN_EVERY, len(all_dates))
        if pred_start >= len(all_dates):
            break

        # Training data
        train_end_date = all_dates[pred_start - 1]
        if window_days is not None:
            train_start_date = train_end_date - pd.Timedelta(days=window_days)
            train = df[(df["date"] > train_start_date) & (df["date"] <= train_end_date)]
        else:
            train = df[df["date"] <= train_end_date]

        # Test data
        test_dates = all_dates[pred_start:pred_end]
        test = df[df["date"].isin(test_dates)]

        if len(train) < 50 or len(test) == 0:
            continue

        # Drop rows with all NaN lags
        lag_cols = [c for c in feature_cols if "lag" in c]
        train = train.dropna(subset=lag_cols, how="all")
        test = test.dropna(subset=lag_cols, how="all")
        if len(test) == 0:
            continue

        X_train = train[feature_cols].fillna(0).astype(np.float32)
        y_train = train["quantity_sold"].fillna(0).astype(np.float32)
        X_test = test[feature_cols].fillna(0).astype(np.float32)
        y_test = test["quantity_sold"].fillna(0)

        # Decay weights
        weights = None
        if decay_hl is not None:
            days_ago = (train_end_date - train["date"]).dt.days
            weights = np.exp(-np.log(2) * days_ago / decay_hl).astype(np.float32)
            weights = weights / weights.mean()

        # Train LightGBM
        model = lgb.LGBMRegressor(
            n_estimators=200, learning_rate=0.05, num_leaves=31,
            min_child_samples=5, n_jobs=2, random_state=42, verbosity=-1,
        )
        if weights is not None:
            model.fit(X_train, y_train, sample_weight=weights)
        else:
            model.fit(X_train, y_train)

        preds = np.clip(model.predict(X_test) * safety_buffer, 0, None)
        n_retrains += 1

        all_preds.extend(preds)
        all_actuals.extend(y_test.values)
        all_prices.extend(test["item_price"].values)
        all_item_ids.extend(test["item_id"].values)

        del model; gc.collect()

    if len(all_actuals) == 0:
        return None

    mae, cost, waste, stockout = evaluate_predictions(all_actuals, all_preds, all_prices, all_item_ids)
    return {
        "mae": round(mae, 4),
        "cost": round(cost, 2),
        "waste": round(waste, 2),
        "stockout": round(stockout, 2),
        "n_predictions": len(all_actuals),
        "n_retrains": n_retrains,
    }


# ---- Main ----
print("Loading data...")
grid, all_dates = load_store_data()
print("Engineering features...")
df, feature_cols = engineer_features(grid)
del grid; gc.collect()
print(f"Features: {len(feature_cols)}, rows: {len(df)}")

# Configs to test
configs = [
    # (window_days, decay_half_life, safety_buffer, description)
    # Window sizes
    (14,   3,   1.15, "14d window, 3d decay"),
    (14,   7,   1.15, "14d window, 7d decay"),
    (21,   3,   1.15, "21d window, 3d decay"),
    (21,   7,   1.15, "21d window, 7d decay"),
    (30,   3,   1.15, "30d window, 3d decay"),
    (30,   7,   1.15, "30d window, 7d decay"),
    (30,   14,  1.15, "30d window, 14d decay"),
    (45,   7,   1.15, "45d window, 7d decay"),
    (45,   14,  1.15, "45d window, 14d decay"),
    (60,   7,   1.15, "60d window, 7d decay"),
    (60,   14,  1.15, "60d window, 14d decay"),
    (90,   7,   1.15, "90d window, 7d decay"),
    (90,   14,  1.15, "90d window, 14d decay"),
    (None, 3,   1.15, "full history, 3d decay"),
    (None, 7,   1.15, "full history, 7d decay"),
    (None, 14,  1.15, "full history, 14d decay"),
    (None, None,1.15, "full history, no decay"),
    # No decay baselines
    (14,   None,1.15, "14d window, no decay"),
    (30,   None,1.15, "30d window, no decay"),
    (60,   None,1.15, "60d window, no decay"),
]

print(f"\n{'='*70}")
print(f"WALK-FORWARD VALIDATION: retrain every {RETRAIN_EVERY} days")
print(f"Store: Zeynos ({STORE_ID}), {TOP_N_ITEMS} items")
print(f"Configs: {len(configs)}")
print(f"{'='*70}\n")

results = []
for win, decay, buf, desc in configs:
    t0 = time.time()
    r = walk_forward(df, feature_cols, win, decay, buf)
    elapsed = time.time() - t0
    if r is None:
        print(f"  {desc:35s}  SKIP (no data)")
        continue
    r["description"] = desc
    r["window_days"] = win
    r["decay_hl"] = decay
    r["buffer"] = buf
    r["time_s"] = round(elapsed, 1)
    results.append(r)
    print(f"  {desc:35s}  Cost: {r['cost']:>10,.0f} DKK  MAE: {r['mae']:.3f}  "
          f"Retrains: {r['n_retrains']:>3}  Time: {elapsed:.1f}s")

# Rank
results.sort(key=lambda r: r["cost"])
print(f"\n{'='*70}")
print("RANKING BY BUSINESS COST:")
print(f"{'='*70}")
for i, r in enumerate(results):
    print(f"  #{i+1:2d}  {r['description']:35s}  Cost: {r['cost']:>10,.0f} DKK  "
          f"MAE: {r['mae']:.3f}  waste: {r['waste']:>8,.0f}  stockout: {r['stockout']:>8,.0f}")

# Now test buffer sweep on the best config
best = results[0]
print(f"\n{'='*70}")
print(f"BUFFER SWEEP on best config: {best['description']}")
print(f"{'='*70}")
for buf in [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40]:
    r = walk_forward(df, feature_cols, best["window_days"], best["decay_hl"], buf)
    if r:
        print(f"  buf={buf:.2f}  Cost: {r['cost']:>10,.0f} DKK  "
              f"waste: {r['waste']:>8,.0f}  stockout: {r['stockout']:>8,.0f}  MAE: {r['mae']:.3f}")

# Save
with open("/home/yahyahammoudeh/Documents/loving loyalty internship/notebooks/results/single_store_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nResults saved.")
