"""Benchmark runner for CatBoost demand forecasting model.

Evaluates three configurations against the standard benchmark harness:
  - CatBoost_default: balanced iterations/depth/lr
  - CatBoost_deep:    deeper trees, more iterations, lower lr (more accurate)
  - CatBoost_shallow: shallower trees, fewer iterations, higher lr (faster)
"""

import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting")

from benchmark_harness import run_benchmark
from src.models.catboost_model import CatBoostForecaster

configs = [
    ("CatBoost_default", {}),
    ("CatBoost_deep", {"depth": 8, "iterations": 800, "learning_rate": 0.03}),
    ("CatBoost_shallow", {"depth": 4, "iterations": 500, "learning_rate": 0.1}),
]

results = {}
for name, params in configs:
    model = CatBoostForecaster(**params)
    result = run_benchmark(model, name)
    results[name] = result

# Summary table
print("\n" + "=" * 70)
print(f"{'Model':<25} {'WMAPE':>7} {'Accuracy':>9} {'Total DKK':>14}")
print("=" * 70)
for name, r in results.items():
    m = r["metrics"]
    print(
        f"{name:<25} {m['wmape']:>6.2f}% {m['forecast_accuracy_pct']:>8.2f}% "
        f"{m['total_business_cost_dkk']:>14,.0f}"
    )
print("=" * 70)
print("Baselines: MA7 = 6,970,000 DKK | NaiveLastWeek = 7,310,000 DKK")
