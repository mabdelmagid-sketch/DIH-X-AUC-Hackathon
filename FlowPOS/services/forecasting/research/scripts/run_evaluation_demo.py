"""
Demo runner for the post-training forecast evaluation pipeline.

What it does
------------
1. Loads Zeynos store data the same way the foundation model benchmark does.
2. Runs two models on the same walk-forward harness:
     - Rolling 7-day average  (the current "promoted" baseline)
     - Same-weekday average   (the naive challenger)
3. Feeds both prediction sets through `flowpos_forecasting.evaluation`.
4. Prints a full forecast report for each model.
5. Runs a Diebold-Mariano test between them.
6. Saves a fixture so `pytest flowpos_forecasting/tests/` can run model
   gating tests against today's promoted model.

Run with:
    python scripts/run_evaluation_demo.py
"""

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flowpos_forecasting.evaluation import (
    compute_business_cost,
    diebold_mariano_test,
    evaluate_forecast,
    format_report,
)

DB_PATH = ROOT / "data" / "raw" / "production.db"
SHELF_PATH = ROOT / "data" / "raw" / "production_shelf_life_final.csv"
STORE_ID = "5995723"
TOP_N_ITEMS = 30
PREDICT_EVERY = 3
WINDOW_DAYS = 60

FIXTURE_DIR = ROOT / "flowpos_forecasting" / "tests" / "fixtures"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
FIXTURE_PATH = FIXTURE_DIR / "promoted_model_predictions.json"


def load_shelf_lookup():
    df = pd.read_csv(SHELF_PATH)
    out = {}
    for _, row in df.iterrows():
        sl = float(row["shelf_life_days"]) if pd.notna(row["shelf_life_days"]) else 3.0
        ag = float(row["avg_gap_days"]) if pd.notna(row["avg_gap_days"]) else 1.0
        out[str(row["item_id"])] = (sl, ag)
    return out


def load_store_grid():
    conn = sqlite3.connect(DB_PATH)
    orders = pd.read_sql("SELECT id, place_id, created, status FROM fct_orders", conn)
    items = pd.read_sql("SELECT item_id, order_id, quantity FROM fct_order_items", conn)
    menu = pd.read_sql("SELECT id, price FROM dim_menu_items", conn)
    conn.close()

    orders["created"] = pd.to_numeric(orders["created"], errors="coerce")
    items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
    menu["price"] = pd.to_numeric(menu["price"], errors="coerce")
    orders = orders[(orders["status"] == "Closed") & (orders["place_id"] == STORE_ID)]
    orders["date"] = pd.to_datetime(orders["created"], unit="s", errors="coerce").dt.normalize()

    merged = items.merge(orders[["id", "date"]], left_on="order_id", right_on="id", how="inner")
    daily = merged.groupby(["date", "item_id"])["quantity"].sum().reset_index(name="quantity_sold")
    top = (
        daily.groupby("item_id")["quantity_sold"]
        .sum()
        .reset_index()
        .sort_values("quantity_sold", ascending=False)
        .head(TOP_N_ITEMS)
    )
    top_items = top["item_id"].values
    daily = daily[daily["item_id"].isin(top_items)]

    ip = menu.rename(columns={"id": "item_id", "price": "item_price"})
    modal = (
        daily.merge(ip, on="item_id", how="left")
        .groupby("item_id")["item_price"]
        .agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 75.0)
        .reset_index()
    )
    modal.columns = ["item_id", "item_price"]

    all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    frames = []
    for iid in top_items:
        f = pd.DataFrame({"date": all_dates, "item_id": iid})
        s = daily[daily["item_id"] == iid][["date", "quantity_sold"]]
        f = f.merge(s, on="date", how="left")
        f["quantity_sold"] = f["quantity_sold"].fillna(0)
        p = modal[modal["item_id"] == iid]["item_price"].values
        f["item_price"] = p[0] if len(p) > 0 else 75.0
        frames.append(f)

    grid = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["item_id", "date"])
        .reset_index(drop=True)
    )
    return grid, all_dates, top_items


def walk_forward_predict(grid, all_dates, top_items, method, buffer=1.40):
    """
    Two methods:
      - "rolling_7d"   : mean of last 7 days (the promoted baseline)
      - "same_dow_avg" : mean of same weekday in window (naive challenger)
    """
    preds, actuals, prices, item_ids, dates = [], [], [], [], []
    for ps in range(30, len(all_dates), PREDICT_EVERY):
        pe = min(ps + PREDICT_EVERY, len(all_dates))
        te = all_dates[ps - 1]
        ts = te - pd.Timedelta(days=WINDOW_DAYS)
        pred_dates = all_dates[ps:pe]
        for iid in top_items:
            item = grid[grid["item_id"] == iid].set_index("date").sort_index()
            hist = item.loc[ts:te]["quantity_sold"]
            acts = item.loc[pred_dates[0]:pred_dates[-1]]["quantity_sold"].values
            price = item["item_price"].iloc[0]
            if len(hist) < 14 or len(acts) == 0:
                continue
            if method == "rolling_7d":
                pred_value = float(hist.values[-7:].mean())
                for i, d in enumerate(pred_dates):
                    if i >= len(acts):
                        break
                    preds.append(pred_value * buffer)
                    actuals.append(float(acts[i]))
                    prices.append(float(price))
                    item_ids.append(str(iid))
                    dates.append(d)
            elif method == "same_dow_avg":
                for i, d in enumerate(pred_dates):
                    if i >= len(acts):
                        break
                    same = hist[hist.index.dayofweek == d.dayofweek].values
                    pv = float(same.mean()) if len(same) > 0 else float(hist.values[-7:].mean())
                    preds.append(pv * buffer)
                    actuals.append(float(acts[i]))
                    prices.append(float(price))
                    item_ids.append(str(iid))
                    dates.append(d)
    return (
        np.array(actuals),
        np.clip(np.array(preds), 0, None),
        np.array(prices),
        item_ids,
        pd.to_datetime(dates),
    )


def main():
    print("Loading Zeynos data...")
    grid, all_dates, top_items = load_store_grid()
    shelf_lookup = load_shelf_lookup()
    print(f"  {len(top_items)} items, {len(all_dates)} days")

    print("\nRunning rolling_7d (promoted baseline)...")
    a, p, pr, ids, dts = walk_forward_predict(grid, all_dates, top_items, "rolling_7d", buffer=1.40)

    print("Running same_dow_avg (challenger)...")
    a2, p2, _, _, _ = walk_forward_predict(grid, all_dates, top_items, "same_dow_avg", buffer=1.40)

    # Both walks produce identical (a, ids, dts) sequences; sanity check
    assert len(a) == len(a2), "challenger walk produced different number of predictions"

    # Promoted-model report
    promoted_report = evaluate_forecast(a, p, pr, ids, dts, shelf_lookup=shelf_lookup)
    print("\n" + format_report(promoted_report, model_name="rolling_7d_buf1.40"))

    # Challenger report
    challenger_report = evaluate_forecast(a2, p2, pr, ids, dts, shelf_lookup=shelf_lookup)
    print("\n" + format_report(challenger_report, model_name="same_dow_avg_buf1.40"))

    # Statistical comparison
    dm = diebold_mariano_test(a, p, p2)
    print("\n=== Diebold-Mariano test (promoted vs challenger) ===")
    print(f"  DM stat       : {dm['dm_stat']:+.3f}")
    print(f"  p-value       : {dm['p_value']:.4f}")
    print(f"  mean loss diff: {dm['mean_loss_diff']:+.3f}")
    if dm["dm_stat"] < 0 and dm["p_value"] < 0.05:
        verdict = "promoted is significantly BETTER"
    elif dm["dm_stat"] > 0 and dm["p_value"] < 0.05:
        verdict = "promoted is significantly WORSE"
    else:
        verdict = "no significant difference"
    print(f"  verdict       : {verdict}")

    # Save fixture for CI gating tests
    fixture = {
        "model_name": "rolling_7d_buf1.40",
        "actuals": a.tolist(),
        "predictions": p.tolist(),
        "prices": pr.tolist(),
        "item_ids": list(ids),
        "naive_predictions": p2.tolist(),
        "shelf_lookup": {k: list(v) for k, v in shelf_lookup.items() if k in set(ids)},
        "thresholds": {
            # Loose thresholds: tighten as the model improves.
            # max_bias_pct is generous because buffer multipliers deliberately
            # introduce positive bias to trade waste for stockout reduction.
            "max_mae": float(promoted_report.metrics.mae * 1.10),
            "max_bias_pct": 60.0,
            "max_business_cost": float(promoted_report.cost.total * 1.10),
        },
    }
    with open(FIXTURE_PATH, "w") as f:
        json.dump(fixture, f, indent=2)
    print(f"\nFixture saved -> {FIXTURE_PATH}")
    print("Run regression tests with:")
    print("  pytest flowpos_forecasting/tests/test_evaluation_pipeline.py -v")


if __name__ == "__main__":
    main()
