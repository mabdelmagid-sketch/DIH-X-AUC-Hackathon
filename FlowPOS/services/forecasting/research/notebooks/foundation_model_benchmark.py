"""
Benchmark time series foundation models vs LightGBM on Zeynos walk-forward.
Models: Chronos-Bolt (small), Chronos-Bolt (mini), LightGBM baseline.
Same setup: 60d window, retrain/predict every 3 days, 30 items.
"""

import sys
import time
import json
import sqlite3
import gc
import warnings
import numpy as np
import pandas as pd
import torch
from chronos import BaseChronosPipeline

warnings.filterwarnings("ignore")

DB_PATH = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/production.db"
STORE_ID = "5995723"  # Zeynos
TOP_N_ITEMS = 30
WASTE_FRACTION = 0.3
STOCKOUT_MULT = 1.5
PREDICT_EVERY = 3
WINDOW_DAYS = 60

# Shelf life lookup
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
    return WASTE_FRACTION * min(1.0, ag / max(sl, 0.5))


def load_store_data():
    conn = sqlite3.connect(DB_PATH)
    orders = pd.read_sql("SELECT id, place_id, created, status FROM fct_orders", conn)
    items = pd.read_sql("SELECT item_id, order_id, quantity, title FROM fct_order_items", conn)
    menu = pd.read_sql("SELECT id, price FROM dim_menu_items", conn)
    conn.close()

    orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
    items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
    menu["price"] = pd.to_numeric(menu["price"], errors="coerce")
    orders = orders[orders["status"] == "Closed"]
    orders["date"] = pd.to_datetime(orders["created"], unit="s", errors="coerce").dt.normalize()
    orders = orders[orders["place_id"] == STORE_ID]

    merged = items.merge(orders[["id", "place_id", "date"]], left_on="order_id", right_on="id", how="inner")
    daily = merged.groupby(["date", "item_id"]).agg(
        quantity_sold=("quantity", "sum")
    ).reset_index()

    # Top N items
    top = daily.groupby("item_id")["quantity_sold"].sum().reset_index().sort_values("quantity_sold", ascending=False).head(TOP_N_ITEMS)
    top_items = top["item_id"].values
    daily = daily[daily["item_id"].isin(top_items)]

    # Item prices
    item_prices = menu.rename(columns={"id": "item_id", "price": "item_price"})
    item_prices["item_price"] = pd.to_numeric(item_prices["item_price"], errors="coerce").fillna(75.0)
    modal = daily.merge(item_prices, on="item_id", how="left").groupby("item_id")["item_price"].agg(
        lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 75.0
    ).reset_index()
    modal.columns = ["item_id", "item_price"]

    # Complete date grid per item
    all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    frames = []
    for iid in top_items:
        item_daily = pd.DataFrame({"date": all_dates, "item_id": iid})
        item_sales = daily[daily["item_id"] == iid][["date", "quantity_sold"]]
        item_daily = item_daily.merge(item_sales, on="date", how="left")
        item_daily["quantity_sold"] = item_daily["quantity_sold"].fillna(0)
        price = modal[modal["item_id"] == iid]["item_price"].values
        item_daily["item_price"] = price[0] if len(price) > 0 else 75.0
        frames.append(item_daily)

    grid = pd.concat(frames, ignore_index=True).sort_values(["item_id", "date"]).reset_index(drop=True)
    print(f"Store data: {len(top_items)} items, {len(all_dates)} days, {len(grid)} rows")
    return grid, all_dates, top_items


def evaluate_all(actuals, preds, prices, item_ids):
    a = np.array(actuals, dtype=float)
    p = np.clip(np.array(preds, dtype=float), 0, None)
    pr = np.array(prices, dtype=float)
    mae = np.abs(a - p).mean()
    wf = np.array([effective_waste_fraction(iid) for iid in item_ids])
    over = np.maximum(p - a, 0)
    under = np.maximum(a - p, 0)
    waste = (over * pr * wf).sum()
    stockout = (under * pr).sum()
    cost = waste + STOCKOUT_MULT * stockout
    return mae, cost, waste, stockout


def chronos_walk_forward(grid, all_dates, top_items, model_name, safety_buffer=1.15):
    """Walk-forward using Chronos foundation model."""
    print(f"\nLoading {model_name}...")
    t_load = time.time()
    pipeline = BaseChronosPipeline.from_pretrained(
        model_name,
        device_map="cpu",
        torch_dtype=torch.float32,
    )
    print(f"  Loaded in {time.time()-t_load:.1f}s")

    all_preds = []
    all_actuals = []
    all_prices = []
    all_item_ids = []
    n_rounds = 0
    min_start = 30  # need 30 days before first prediction

    t0 = time.time()
    for pred_start_idx in range(min_start, len(all_dates), PREDICT_EVERY):
        pred_end_idx = min(pred_start_idx + PREDICT_EVERY, len(all_dates))
        if pred_start_idx >= len(all_dates):
            break

        # Window
        train_end = all_dates[pred_start_idx - 1]
        train_start = train_end - pd.Timedelta(days=WINDOW_DAYS)
        pred_dates = all_dates[pred_start_idx:pred_end_idx]
        n_pred = len(pred_dates)

        for iid in top_items:
            item_data = grid[grid["item_id"] == iid].set_index("date").sort_index()
            history = item_data.loc[train_start:train_end]["quantity_sold"].values
            actuals = item_data.loc[pred_dates[0]:pred_dates[-1]]["quantity_sold"].values
            price = item_data["item_price"].iloc[0]

            if len(history) < 14 or len(actuals) == 0:
                continue

            # Chronos prediction
            context = torch.tensor(history, dtype=torch.float32).unsqueeze(0)
            forecast = pipeline.predict(context, prediction_length=n_pred)
            # forecast shape: (1, num_samples, pred_len) — take median
            preds = np.median(forecast[0].numpy(), axis=0)
            preds = np.clip(preds * safety_buffer, 0, None)

            for i in range(min(len(preds), len(actuals))):
                all_preds.append(preds[i])
                all_actuals.append(actuals[i])
                all_prices.append(price)
                all_item_ids.append(iid)

        n_rounds += 1
        if n_rounds % 10 == 0:
            elapsed = time.time() - t0
            print(f"  Round {n_rounds}, {len(all_preds)} predictions, {elapsed:.0f}s")

    elapsed = time.time() - t0
    mae, cost, waste, stockout = evaluate_all(all_preds, all_actuals, all_prices, all_item_ids)
    print(f"  Done: {n_rounds} rounds, {len(all_preds)} predictions, {elapsed:.0f}s")

    del pipeline; gc.collect()
    torch.cuda.empty_cache() if torch.cuda.is_available() else None

    return {
        "model": model_name.split("/")[-1],
        "mae": round(mae, 4),
        "cost": round(cost, 2),
        "waste": round(waste, 2),
        "stockout": round(stockout, 2),
        "n_predictions": len(all_preds),
        "n_rounds": n_rounds,
        "time_s": round(elapsed, 1),
        "buffer": safety_buffer,
    }


def lgb_walk_forward(grid, all_dates, top_items, safety_buffer=1.15):
    """LightGBM baseline for comparison."""
    import lightgbm as lgb
    from sklearn.preprocessing import LabelEncoder

    # Quick feature engineering
    df = grid.copy()
    df["day_of_week"] = df["date"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

    grp = ["item_id"]
    for lag in [1, 3, 7, 14]:
        df[f"lag_{lag}"] = df.groupby(grp)["quantity_sold"].shift(lag)
    shifted = df.groupby(grp)["quantity_sold"].shift(1)
    for w in [3, 7, 14]:
        df[f"roll_{w}"] = shifted.groupby(df["item_id"]).transform(
            lambda x: x.rolling(w, min_periods=1).mean()
        )
    df["roll_std_7"] = shifted.groupby(df["item_id"]).transform(
        lambda x: x.rolling(7, min_periods=2).std()
    )

    le = LabelEncoder()
    df["item_enc"] = le.fit_transform(df["item_id"].astype(str))

    feat_cols = ["day_of_week", "is_weekend", "dow_sin", "dow_cos",
                 "lag_1", "lag_3", "lag_7", "lag_14",
                 "roll_3", "roll_7", "roll_14", "roll_std_7", "item_enc"]

    all_preds, all_actuals, all_prices, all_item_ids = [], [], [], []
    n_rounds = 0
    t0 = time.time()

    for pred_start_idx in range(30, len(all_dates), PREDICT_EVERY):
        pred_end_idx = min(pred_start_idx + PREDICT_EVERY, len(all_dates))
        train_end = all_dates[pred_start_idx - 1]
        train_start = train_end - pd.Timedelta(days=WINDOW_DAYS)
        pred_dates = all_dates[pred_start_idx:pred_end_idx]

        train = df[(df["date"] > train_start) & (df["date"] <= train_end)]
        test = df[df["date"].isin(pred_dates)]

        lag_cols = [c for c in feat_cols if "lag" in c]
        train = train.dropna(subset=lag_cols, how="all")
        test = test.dropna(subset=lag_cols, how="all")
        if len(train) < 50 or len(test) == 0:
            continue

        X_tr = train[feat_cols].fillna(0).astype(np.float32)
        y_tr = train["quantity_sold"].astype(np.float32)
        X_te = test[feat_cols].fillna(0).astype(np.float32)

        model = lgb.LGBMRegressor(
            n_estimators=200, learning_rate=0.05, num_leaves=31,
            min_child_samples=5, n_jobs=2, random_state=42, verbosity=-1,
        )
        model.fit(X_tr, y_tr)
        preds = np.clip(model.predict(X_te) * safety_buffer, 0, None)

        all_preds.extend(preds)
        all_actuals.extend(test["quantity_sold"].values)
        all_prices.extend(test["item_price"].values)
        all_item_ids.extend(test["item_id"].values)
        n_rounds += 1
        del model

    elapsed = time.time() - t0
    mae, cost, waste, stockout = evaluate_all(all_preds, all_actuals, all_prices, all_item_ids)
    return {
        "model": "LightGBM-200",
        "mae": round(mae, 4),
        "cost": round(cost, 2),
        "waste": round(waste, 2),
        "stockout": round(stockout, 2),
        "n_predictions": len(all_preds),
        "n_rounds": n_rounds,
        "time_s": round(elapsed, 1),
        "buffer": safety_buffer,
    }


# ---- Main ----
print("Loading store data...")
grid, all_dates, top_items = load_store_data()

results = []

# LightGBM baseline
print("\n" + "="*60)
print("LightGBM BASELINE (60d window, retrain/3d)")
print("="*60)
r = lgb_walk_forward(grid, all_dates, top_items, safety_buffer=1.40)
results.append(r)
print(f"  MAE: {r['mae']:.3f}  Cost: {r['cost']:,.0f} DKK  Time: {r['time_s']:.0f}s")

# Chronos models (small to large)
chronos_models = [
    "amazon/chronos-bolt-tiny",    # 8M params
    "amazon/chronos-bolt-mini",    # 20M params
    "amazon/chronos-bolt-small",   # 48M params
]

for model_name in chronos_models:
    print(f"\n{'='*60}")
    print(f"CHRONOS: {model_name}")
    print(f"{'='*60}")
    try:
        r = chronos_walk_forward(grid, all_dates, top_items, model_name, safety_buffer=1.40)
        results.append(r)
        print(f"  MAE: {r['mae']:.3f}  Cost: {r['cost']:,.0f} DKK  Time: {r['time_s']:.0f}s")
    except Exception as e:
        print(f"  FAILED: {e}")

# Summary
print(f"\n{'='*60}")
print("FINAL COMPARISON (buf=1.40, 60d window, retrain/3d)")
print(f"{'='*60}")
print(f"{'Model':<25} {'MAE':>8} {'Cost (DKK)':>12} {'Waste':>10} {'Stockout':>10} {'Time':>8}")
print("-" * 75)
for r in sorted(results, key=lambda x: x["cost"]):
    print(f"{r['model']:<25} {r['mae']:>8.3f} {r['cost']:>12,.0f} {r['waste']:>10,.0f} {r['stockout']:>10,.0f} {r['time_s']:>7.0f}s")

# Save
with open("/home/yahyahammoudeh/Documents/loving loyalty internship/notebooks/results/foundation_model_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print("\nResults saved.")
