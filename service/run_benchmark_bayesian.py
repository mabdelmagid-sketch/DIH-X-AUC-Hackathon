"""
Benchmark runner for Bayesian Ridge and ARD Regression models.
"""

import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting")

from benchmark_harness import run_benchmark
from sklearn.linear_model import BayesianRidge, ARDRegression
from src.models.bayesian_ridge_model import BayesianForecaster, BayesianRidgePolyForecaster

configs = [
    ("BayesianRidge_default", BayesianForecaster, {"model_cls": BayesianRidge}),
    ("BayesianRidge_tuned", BayesianForecaster, {"model_cls": BayesianRidge, "alpha_1": 1e-5, "lambda_1": 1e-5}),
    ("ARD_Regression", BayesianForecaster, {"model_cls": ARDRegression, "max_iter": 300}),
]

results = {}
for name, cls, params in configs:
    model = cls(**params)
    result = run_benchmark(model, name)
    results[name] = result

# Polynomial variant (separate instantiation)
poly_model = BayesianRidgePolyForecaster()
poly_result = run_benchmark(poly_model, "BayesianRidge_poly_lag_features")
results["BayesianRidge_poly_lag_features"] = poly_result

# Summary table
print("\n" + "=" * 80)
print("BAYESIAN MODELS SUMMARY")
print("=" * 80)
header = f"{'Model':<40} {'WMAPE':>8} {'Accuracy':>10} {'Total DKK':>14} {'Train(s)':>10}"
print(header)
print("-" * 80)
for name, r in results.items():
    m = r["metrics"]
    t = r["timing"]
    print(
        f"{name:<40} {m['wmape']:>7.2f}% {m['forecast_accuracy_pct']:>9.2f}%"
        f" {m['total_business_cost_dkk']:>14,.0f} {t['train_s']:>9.1f}s"
    )
print("=" * 80)
print("Baselines: MA7=6,970,000 DKK  NaiveLastWeek=7,310,000 DKK")
