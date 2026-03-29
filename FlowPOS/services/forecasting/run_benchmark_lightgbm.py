"""
LightGBM benchmark runner — evaluates three hyperparameter configs.

Baselines for reference:
  MA7             = 6.97M DKK total business cost
  NaiveLastWeek   = 7.31M DKK total business cost
"""

import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting")
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/src/models")

from benchmark_harness import run_benchmark
from lightgbm_model import LightGBMForecaster

configs = [
    # 1. Default — balanced starting point
    (
        "LightGBM_default",
        {},
    ),
    # 2. Tuned for accuracy — more estimators, lower learning rate, more leaves
    (
        "LightGBM_tuned",
        {
            "n_estimators": 800,
            "num_leaves": 31,
            "learning_rate": 0.03,
            "min_child_samples": 5,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.9,
            "reg_lambda": 0.5,
        },
    ),
    # 3. Tuned for sparse data — penalise complexity, higher min_child_samples
    #    to avoid fitting sparse zero-demand noise
    (
        "LightGBM_sparse",
        {
            "n_estimators": 500,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "min_child_samples": 20,
            "reg_alpha": 0.1,
            "reg_lambda": 2.0,
            "feature_fraction": 0.7,
            "bagging_fraction": 0.7,
        },
    ),
]

results = {}
for name, params in configs:
    model = LightGBMForecaster(**params)
    result = run_benchmark(model, name)
    results[name] = result

# Summary table
print("\n" + "=" * 70)
print(f"{'Model':<25} {'WMAPE':>7} {'Acc%':>7} {'TotalCost DKK':>16}")
print("-" * 70)
baselines = {"MA7": 6_970_000, "NaiveLastWeek": 7_310_000}
for bl, cost in baselines.items():
    print(f"  {bl:<23} {'—':>7} {'—':>7} {cost:>16,.0f}")
for name, r in results.items():
    m = r["metrics"]
    print(
        f"  {name:<23} {m['wmape']:>6.2f}% {m['forecast_accuracy_pct']:>6.2f}%"
        f" {m['total_business_cost_dkk']:>16,.0f}"
    )
print("=" * 70)
