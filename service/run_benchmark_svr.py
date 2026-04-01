"""
SVR Benchmark Runner

Evaluates LinearSVR and SGDRegressor (SVR-equivalent) models for demand forecasting.
LinearSVR and SGDRegressor scale to large datasets unlike standard SVR (O(n^2/n^3)).
"""

import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting")

from benchmark_harness import run_benchmark
from src.models.svr_model import SVRForecaster, SGDSVRForecaster

configs = [
    # LinearSVR: reduced max_iter for scalability at 323K rows
    ("LinearSVR_default", SVRForecaster(C=1.0, max_iter=2000)),
    ("LinearSVR_regularized", SVRForecaster(C=0.1, max_iter=2000)),
    # SGDRegressor: SVR-equivalent via stochastic gradient descent (much faster)
    ("SGD_epsilon_insensitive", SGDSVRForecaster(
        loss="epsilon_insensitive", epsilon=0.1, alpha=0.0001, max_iter=1000
    )),
    ("SGD_huber", SGDSVRForecaster(
        loss="huber", epsilon=0.1, alpha=0.0001, max_iter=1000
    )),
]

results = {}
for name, model in configs:
    result = run_benchmark(model, name)
    results[name] = result

# Summary table
print("\n" + "=" * 80)
print("SVR MODEL COMPARISON SUMMARY")
print("=" * 80)
print(f"{'Model':<30} {'WMAPE':>8} {'MAE':>8} {'Total Cost DKK':>16} {'Train(s)':>10}")
print("-" * 80)
for name, result in results.items():
    m = result["metrics"]
    t = result["timing"]
    print(
        f"{name:<30} {m['wmape']:>7.2f}% {m['mae']:>8.4f} "
        f"{m['total_business_cost_dkk']:>16,.0f} {t['train_s']:>9.1f}s"
    )
print("=" * 80)
print("Baselines: MA7=6,970,000 DKK | NaiveLastWeek=7,310,000 DKK")
