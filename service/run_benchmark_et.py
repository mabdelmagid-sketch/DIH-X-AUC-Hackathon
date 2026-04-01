"""
Benchmark runner for Extra Trees forecasting models.
Run from the forecasting service directory.
"""

import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting")

from benchmark_harness import run_benchmark
from src.models.extra_trees_model import ETForecaster

configs = [
    ("ET_default", {}),
    ("ET_large", {"n_estimators": 500, "max_depth": 15}),
    ("ET_tuned", {"n_estimators": 300, "min_samples_leaf": 5, "max_features": 0.7}),
]

results = {}
for name, params in configs:
    model = ETForecaster(**params)
    result = run_benchmark(model, name)
    results[name] = result

print("\n" + "=" * 60)
print("EXTRA TREES BENCHMARK SUMMARY")
print("=" * 60)
print(f"{'Model':<20} {'WMAPE':>8} {'Acc%':>8} {'TotalCost DKK':>16} {'Train(s)':>10}")
print("-" * 62)
for name, r in results.items():
    m = r["metrics"]
    t = r["timing"]
    print(f"{name:<20} {m['wmape']:>7.2f}% {m['forecast_accuracy_pct']:>7.2f}% "
          f"{m['total_business_cost_dkk']:>16,.0f} {t['train_s']:>9.1f}s")
print("=" * 60)
print("Baselines for reference:")
print("  MA7:           total_business_cost = 6,970,000 DKK")
print("  NaiveLastWeek: total_business_cost = 7,310,000 DKK")
