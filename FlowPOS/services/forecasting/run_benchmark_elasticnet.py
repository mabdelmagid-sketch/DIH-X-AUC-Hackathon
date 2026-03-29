"""
Benchmark runner for linear regularized models: Ridge, Lasso, ElasticNet.
"""
import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting")

from benchmark_harness import run_benchmark
from sklearn.linear_model import ElasticNet, Ridge, Lasso
from src.models.elasticnet_model import LinearForecaster

configs = [
    ("Ridge", Ridge, {"alpha": 1.0}),
    ("Lasso", Lasso, {"alpha": 0.1}),
    ("ElasticNet_default", ElasticNet, {"alpha": 0.1, "l1_ratio": 0.5}),
    ("ElasticNet_tuned", ElasticNet, {"alpha": 0.01, "l1_ratio": 0.7}),
]

results = {}
for name, cls, params in configs:
    model = LinearForecaster(cls, **params)
    result = run_benchmark(model, name)
    results[name] = result

print("\n=== Summary ===")
print(f"{'Model':<25} {'WMAPE':>8} {'Acc%':>8} {'Total DKK':>14}")
print("-" * 58)
for name, r in results.items():
    m = r["metrics"]
    print(f"{name:<25} {m['wmape']:>8.2f} {m['forecast_accuracy_pct']:>8.2f} {m['total_business_cost_dkk']:>14,.0f}")
