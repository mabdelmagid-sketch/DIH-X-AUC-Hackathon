"""
Benchmark runner for Stacking Meta-Learner Ensemble models.

Runs two stacking configurations:
  1. Stacking_Ridge_Meta: XGB + RF + Ridge base, Ridge meta-learner
  2. Stacking_XGB_Meta: XGB + RF + ExtraTrees base, XGBoost meta-learner
"""

import sys
sys.path.insert(0, "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting")

from benchmark_harness import run_benchmark
from src.models.stacking_model import build_stacking_ridge_meta, build_stacking_xgb_meta

if __name__ == "__main__":
    results = {}

    # Config 1: Full stack with Ridge meta-learner
    print("\n" + "="*60)
    print("Config 1: Stacking with Ridge Meta-Learner")
    print("  Base: XGBoost + RandomForest + Ridge")
    print("="*60)
    model1 = build_stacking_ridge_meta()
    r1 = run_benchmark(model1, "Stacking_Ridge_Meta")
    results["Stacking_Ridge_Meta"] = r1

    # Config 2: Tree-only stack with XGBoost meta-learner
    print("\n" + "="*60)
    print("Config 2: Stacking with XGBoost Meta-Learner (tree-only base)")
    print("  Base: XGBoost + RandomForest + ExtraTrees")
    print("="*60)
    model2 = build_stacking_xgb_meta()
    r2 = run_benchmark(model2, "Stacking_XGB_Meta")
    results["Stacking_XGB_Meta"] = r2

    # Summary comparison
    print("\n" + "="*60)
    print("SUMMARY: Stacking Ensemble Results")
    print("="*60)
    baselines = {"MA7": 6_970_000, "NaiveLastWeek": 7_310_000}
    print(f"{'Model':<25} {'WMAPE':>8} {'Accuracy':>10} {'Total Cost DKK':>16} {'vs MA7':>10}")
    print("-"*75)
    for name, r in results.items():
        m = r["metrics"]
        cost = m["total_business_cost_dkk"]
        vs_ma7 = (cost - baselines["MA7"]) / baselines["MA7"] * 100
        sign = "+" if vs_ma7 > 0 else ""
        print(f"{name:<25} {m['wmape']:>7.2f}% {m['forecast_accuracy_pct']:>9.2f}% "
              f"{cost:>16,.0f} {sign}{vs_ma7:>8.1f}%")
    print("-"*75)
    print(f"{'MA7 Baseline':<25} {'':>8} {'':>10} {baselines['MA7']:>16,.0f} {'0.0%':>10}")
    print(f"{'NaiveLastWeek':<25} {'':>8} {'':>10} {baselines['NaiveLastWeek']:>16,.0f} {'+4.9%':>10}")
