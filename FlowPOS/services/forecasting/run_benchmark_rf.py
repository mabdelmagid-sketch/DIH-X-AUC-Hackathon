"""Benchmark runner for Random Forest forecasting models."""

import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting")

from benchmark_harness import run_benchmark
from src.models.random_forest_model import RFForecaster

configs = [
    ("RF_default", {}),
    ("RF_large", {"n_estimators": 500, "max_depth": 12}),
    ("RF_tuned", {"n_estimators": 300, "min_samples_leaf": 10, "max_features": "sqrt"}),
]

results = {}
for name, params in configs:
    model = RFForecaster(**params)
    result = run_benchmark(model, name)
    results[name] = result

print("\n" + "=" * 70)
print("RANDOM FOREST BENCHMARK SUMMARY")
print("=" * 70)
print(f"{'Model':<20} {'WMAPE%':>8} {'Accuracy%':>10} {'Total Cost DKK':>16} {'Train(s)':>9}")
print("-" * 70)
for name, r in results.items():
    m = r["metrics"]
    t = r["timing"]
    print(
        f"{name:<20} {m['wmape']:>8.2f} {m['forecast_accuracy_pct']:>10.2f} "
        f"{m['total_business_cost_dkk']:>16,.0f} {t['train_s']:>9.1f}"
    )
print("=" * 70)
