"""
Benchmark runner for Croston's Method variants.

Runs four variants:
  1. Croston Classic (alpha=0.1)
  2. Croston SBA (alpha=0.1, bias-corrected)
  3. Croston Tuned (alpha=0.2, faster adaptation)
  4. Croston Hybrid (Croston SBA for sparse items, MA7 for dense)

Usage:
    cd /home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting
    python run_benchmark_croston.py
"""

import sys
import json
import logging
from pathlib import Path

# Ensure the forecasting service root is on the path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src"))

from benchmark_harness import run_benchmark
from src.models.croston_model import (
    CrostonClassic,
    CrostonSBA,
    CrostonTuned,
    CrostonHybrid,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 70)
    logger.info("CROSTON'S METHOD BENCHMARK - Intermittent Demand Forecasting")
    logger.info("=" * 70)
    logger.info(
        "Dataset is ~84.5% sparse. Croston's method is specifically designed "
        "for intermittent demand like this."
    )

    models = [
        (CrostonClassic(alpha=0.1), "Croston_Classic_a01"),
        (CrostonSBA(alpha=0.1), "Croston_SBA_a01"),
        (CrostonTuned(alpha=0.2), "Croston_Tuned_a02"),
        (CrostonHybrid(alpha=0.1, sparse_threshold=0.5), "Croston_Hybrid"),
    ]

    all_results = {}
    best_model = None
    best_mae = float("inf")

    for model, name in models:
        logger.info(f"\nRunning: {name}")
        result = run_benchmark(model, name, top_n_items=30, test_days=14)
        all_results[name] = result

        mae = result["metrics"]["mae"]
        if mae < best_mae:
            best_mae = mae
            best_model = name

    # Summary table
    logger.info("\n" + "=" * 70)
    logger.info("CROSTON VARIANTS COMPARISON SUMMARY")
    logger.info("=" * 70)
    logger.info(
        f"{'Model':<30} {'MAE':>8} {'RMSE':>8} {'WMAPE%':>8} "
        f"{'Accuracy%':>10} {'BizCost':>12}"
    )
    logger.info("-" * 70)

    for name, result in all_results.items():
        m = result["metrics"]
        logger.info(
            f"{name:<30} {m['mae']:>8.4f} {m['rmse']:>8.4f} "
            f"{m['wmape']:>8.2f} {m['forecast_accuracy_pct']:>10.2f} "
            f"{m['total_business_cost_dkk']:>12,.0f}"
        )

    logger.info("-" * 70)
    logger.info(f"Best model by MAE: {best_model} (MAE={best_mae:.4f})")

    # Save combined summary
    summary_path = BASE_DIR / "benchmark_results" / "croston_summary.json"
    with open(summary_path, "w") as f:
        json.dump(
            {
                "best_model": best_model,
                "best_mae": best_mae,
                "results": {
                    name: res["metrics"] for name, res in all_results.items()
                },
            },
            f,
            indent=2,
        )
    logger.info(f"\nSummary saved to {summary_path}")

    return all_results


if __name__ == "__main__":
    main()
