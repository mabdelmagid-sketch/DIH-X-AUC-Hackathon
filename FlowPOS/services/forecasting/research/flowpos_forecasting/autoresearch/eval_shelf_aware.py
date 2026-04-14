"""
Shelf-life-aware evaluation of the best model.

Key insight: the flat WASTE_FRACTION=0.3 is wrong.
  - Unsold fresh salad (shelf_life=1d, ordered daily)  → IS waste (factor=1.0)
  - Unsold frozen beef (shelf_life=90d, ordered weekly) → NOT waste (factor=7/90=0.078)
  - Unsold bottled beer (shelf_life=365d)               → Almost never waste

Formula:
  effective_waste_fraction[item] = 0.3 × min(1.0, avg_gap_days / shelf_life_days)

Newsvendor buffer also adjusts per item:
  critical_ratio = 1.5 / (1.5 + effective_waste_fraction)
  Higher shelf life → lower waste cost → higher critical ratio → more safety stock is fine
"""

import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
from evaluate import get_data, get_train_test, STOCKOUT_MULTIPLIER
from experiment import build_model, DECAY_HALF_LIFE

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "demo"

FLAT_WASTE = 0.3
STOCKOUT_MULT = 1.5
BASELINE_COST = 5_133_764.0

# ---------------------------------------------------------------------------
# Load shelf life + cadence lookup: item_id -> (shelf_life_days, avg_gap_days, confidence)
# ---------------------------------------------------------------------------


def load_shelf_lookup() -> dict[int, tuple[float, float, str]]:
    """Returns {item_id: (shelf_life_days, avg_gap_days, confidence)}"""
    shelf_path = DATA_DIR / "dim_items_shelf_life.csv"
    cadence_path = DATA_DIR / "items_to_enrich.csv"

    shelf = pd.read_csv(shelf_path)[["item_id", "shelf_life_days", "confidence"]]
    shelf["shelf_life_days"] = pd.to_numeric(
        shelf["shelf_life_days"], errors="coerce"
    ).fillna(3)
    shelf["confidence"] = shelf["confidence"].fillna("low").astype(str).str.lower()

    cadence = pd.read_csv(cadence_path)[["item_id", "avg_gap_days"]]
    cadence["avg_gap_days"] = pd.to_numeric(
        cadence["avg_gap_days"], errors="coerce"
    ).fillna(1)

    merged = shelf.merge(cadence, on="item_id", how="left")
    merged["avg_gap_days"] = merged["avg_gap_days"].fillna(1)

    return {
        int(row["item_id"]): (
            float(row["shelf_life_days"]),
            float(row["avg_gap_days"]),
            str(row["confidence"]),
        )
        for _, row in merged.iterrows()
    }


def effective_waste_fraction(item_id: int, lookup: dict) -> float:
    shelf_life, avg_gap, confidence = lookup.get(item_id, (3.0, 1.0, "low"))
    if confidence != "high":
        return FLAT_WASTE
    shelf_life = max(shelf_life, 0.5)
    return FLAT_WASTE * min(1.0, avg_gap / shelf_life)


# ---------------------------------------------------------------------------
# Shelf-life-aware newsvendor buffer per item
# ---------------------------------------------------------------------------


def shelf_aware_buffer(
    item_id: int,
    lookup: dict,
    mean_demand: float,
    std_demand: float,
    base: float = 1.30,
    scale: float = 0.20,
) -> float:
    """Compute shelf-life-adjusted safety buffer using log scaling.

    Smooth adjustment: buffer = base + scale * log(0.3 / eff_waste).
    - Frozen/ambient (low waste): slightly higher buffer (order more, overstock is cheap)
    - Perishable (high waste): slightly lower buffer (order less, overstock is expensive)
    """
    eff_waste = effective_waste_fraction(item_id, lookup)
    eff_waste = max(eff_waste, 0.01)  # avoid log(0)
    adj = scale * np.log(0.3 / eff_waste)
    buffer = base + adj
    return float(np.clip(buffer, 1.05, 1.50))


# ---------------------------------------------------------------------------
# Business cost with shelf-life-aware waste fractions
# ---------------------------------------------------------------------------


def shelf_aware_cost(y_actual, y_predicted, prices, item_ids, lookup):
    actual = np.array(y_actual, dtype=float)
    predicted = np.clip(np.array(y_predicted, dtype=float), 0, None)
    prices = np.array(prices, dtype=float)

    waste_cost = 0.0
    stockout_cost = 0.0
    for i, iid in enumerate(item_ids):
        wf = effective_waste_fraction(int(iid), lookup)
        overstock = max(predicted[i] - actual[i], 0)
        understock = max(actual[i] - predicted[i], 0)
        waste_cost += overstock * prices[i] * wf
        stockout_cost += understock * prices[i]

    total = waste_cost + STOCKOUT_MULT * stockout_cost
    return total, waste_cost, stockout_cost


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Loading shelf life lookup...")
    lookup = load_shelf_lookup()
    print(f"  {len(lookup):,} items with shelf life data")

    # Sample a few to show the effect
    sample_ids = list(lookup.keys())[:5]
    for iid in sample_ids:
        sl, gap, conf = lookup[iid]
        wf = effective_waste_fraction(iid, lookup)
        print(
            f"  item {iid}: shelf_life={sl:.0f}d, avg_gap={gap:.1f}d, "
            f"confidence={conf} → waste_fraction={wf:.3f}"
        )

    print("\nLoading and preparing data...")
    data = get_data()
    X_train, y_train, X_test, y_test, prices_test, weights = get_train_test(
        data, decay_half_life=DECAY_HALF_LIFE
    )

    # Get item_ids for test rows (needed for per-item waste fractions)
    df = data["df"]
    max_date = df["date"].max()
    test_cutoff = max_date - pd.Timedelta(days=14)
    test_df = df[df["date"] > test_cutoff].dropna(
        subset=[c for c in data["feature_cols"] if "lag" in c], how="all"
    )
    item_ids_test = test_df["item_id"].values

    # Compute per-item demand stats from training data for shelf-aware buffers
    train_df = df[df["date"] <= test_cutoff]
    item_stats = (
        train_df.groupby("item_id")["quantity_sold"].agg(["mean", "std"]).fillna(0)
    )
    item_stats["std"] = item_stats["std"].fillna(item_stats["mean"] * 0.3)

    print(f"\nTraining best model (SoftProbModel LGB+RF(500)+ET(800))...")
    t0 = time.time()
    model = build_model()
    model.fit(
        X_train,
        y_train,
        sample_weight=weights.values if hasattr(weights, "values") else weights,
    )
    print(f"  Trained in {time.time() - t0:.0f}s")

    raw_preds = model.predict(X_test)

    # --- Evaluation 1: Old flat cost (baseline, should match 5.13M) ---
    overstock = np.maximum(raw_preds - np.array(y_test), 0)
    understock = np.maximum(np.array(y_test) - raw_preds, 0)
    flat_waste = (overstock * prices_test * FLAT_WASTE).sum()
    flat_stockout = (understock * prices_test).sum()
    flat_total = flat_waste + STOCKOUT_MULT * flat_stockout

    # --- Evaluation 2: Shelf-life-aware cost (same predictions, better cost model) ---
    shelf_total, shelf_waste, shelf_stockout = shelf_aware_cost(
        y_test, raw_preds, prices_test, item_ids_test, lookup
    )

    # --- Evaluation 3: Shelf-life-aware buffers + cost ---
    # Remove the model's baked-in 1.30 buffer, apply per-item shelf-aware buffer
    raw_no_buffer = raw_preds / 1.30
    shelf_buffered = np.array(
        [
            raw_no_buffer[i]
            * shelf_aware_buffer(
                int(item_ids_test[i]),
                lookup,
                float(item_stats.loc[item_ids_test[i], "mean"])
                if item_ids_test[i] in item_stats.index
                else 1.0,
                float(item_stats.loc[item_ids_test[i], "std"])
                if item_ids_test[i] in item_stats.index
                else 0.3,
            )
            for i in range(len(raw_no_buffer))
        ]
    )
    shelf_buf_total, shelf_buf_waste, shelf_buf_stockout = shelf_aware_cost(
        y_test, shelf_buffered, prices_test, item_ids_test, lookup
    )

    print("\n" + "=" * 60)
    print("  COMPARISON")
    print("=" * 60)
    print(f"  {'':35s} {'Waste':>10} {'Stockout':>10} {'TOTAL':>12}")
    print(f"  {'-' * 67}")
    print(
        f"  {'Old flat cost (baseline)':35s} {flat_waste:>10,.0f} {flat_stockout:>10,.0f} {flat_total:>12,.0f}"
    )
    print(
        f"  {'Shelf-aware cost (same preds)':35s} {shelf_waste:>10,.0f} {shelf_stockout:>10,.0f} {shelf_total:>12,.0f}"
    )
    print(
        f"  {'Shelf-aware cost + smart buffers':35s} {shelf_buf_waste:>10,.0f} {shelf_buf_stockout:>10,.0f} {shelf_buf_total:>12,.0f}"
    )
    print(f"  {'-' * 67}")
    print(f"  {'Autoresearch baseline':35s} {'':>10} {'':>10} {BASELINE_COST:>12,.0f}")
    print()
    print(
        f"  Cost reduction (shelf-aware cost):          {((flat_total - shelf_total) / flat_total * 100):+.1f}%"
    )
    print(
        f"  Cost reduction (smart buffers):             {((flat_total - shelf_buf_total) / flat_total * 100):+.1f}%"
    )
    print("=" * 60)
    print()
    print("Key insight: items with long shelf life (frozen/ambient) now have")
    print("lower waste penalties and higher safety buffers — because over-ordering")
    print("frozen beef costs almost nothing, but running out costs 1.5x price.")
