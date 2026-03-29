"""
Benchmark runner for Holt-Winters Exponential Smoothing models.

Usage:
    cd /home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting
    python run_benchmark_ets.py
"""

import sys
import json
from pathlib import Path

# Ensure the forecasting service root is on the path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src" / "models"))

from benchmark_harness import run_benchmark
from exponential_smoothing_model import (
    SESModel,
    WeightedETSModel,
    AdaptiveETSModel,
    DampedTrendETSModel,
)


def main():
    models = [
        ("SES alpha=0.3", SESModel(alpha=0.3)),
        ("WeightedETS alpha=0.2", WeightedETSModel(alpha=0.2)),
        ("AdaptiveETS", AdaptiveETSModel()),
        ("DampedTrend ETS", DampedTrendETSModel(alpha=0.3, phi=0.1)),
    ]

    all_results = {}

    for name, model in models:
        result = run_benchmark(model, name)
        all_results[name] = result

    # Summary table
    print("\n" + "=" * 70)
    print("ETS MODEL COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Model':<25} {'MAE':>8} {'WMAPE':>8} {'Accuracy':>10} {'TotalCost(DKK)':>16}")
    print("-" * 70)

    baselines = {
        "MA7 Baseline":       6_970_000,
        "NaiveLW Baseline":   7_310_000,
    }
    for bname, bcost in baselines.items():
        print(f"{bname:<25} {'N/A':>8} {'N/A':>8} {'N/A':>10} {bcost:>16,.0f}")

    print("-" * 70)
    for name, result in all_results.items():
        m = result["metrics"]
        print(
            f"{name:<25} {m['mae']:>8.4f} {m['wmape']:>7.2f}% "
            f"{m['forecast_accuracy_pct']:>9.2f}% {m['total_business_cost_dkk']:>16,.0f}"
        )

    print("=" * 70)

    # Save combined results
    out_path = Path(__file__).parent / "benchmark_results" / "ets_all_results.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nAll results saved to {out_path}")

    return all_results


if __name__ == "__main__":
    main()
