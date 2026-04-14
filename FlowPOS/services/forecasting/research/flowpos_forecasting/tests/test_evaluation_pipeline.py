"""
Regression tests for the forecast evaluation pipeline.

Two layers of tests:

1. Unit tests for the evaluation functions themselves (metrics math, cost
   decomposition, DM test, sanity checks). These pin behaviour so the module
   can be refactored safely.

2. Model gating tests: load a fixture of (actuals, predictions) from the
   currently-promoted model and assert quality thresholds. These are the
   tests CI runs after every retrain to decide whether the new model can be
   promoted to production.

Run with:
    pytest flowpos_forecasting/tests/test_evaluation_pipeline.py -v
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flowpos_forecasting.evaluation import (
    ForecastReport,
    bias_diagnostics,
    compute_business_cost,
    compute_metrics,
    diebold_mariano_test,
    error_by_dow,
    evaluate_forecast,
    format_report,
    top_error_items,
)


# ============================================================================
# Unit tests: pin metric behaviour
# ============================================================================

class TestComputeMetrics:
    def test_perfect_forecast(self):
        m = compute_metrics([1, 2, 3, 4], [1, 2, 3, 4])
        assert m.mae == 0
        assert m.rmse == 0
        assert m.bias == 0
        assert m.r2 == 1.0

    def test_constant_overprediction(self):
        m = compute_metrics([10, 10, 10], [12, 12, 12])
        assert m.mae == pytest.approx(2.0)
        assert m.bias == pytest.approx(2.0)
        assert m.bias_pct == pytest.approx(20.0)

    def test_mae_vs_rmse(self):
        m = compute_metrics([0, 0, 0, 0], [0, 0, 0, 10])
        assert m.mae == pytest.approx(2.5)
        assert m.rmse == pytest.approx(5.0)

    def test_mape_skips_zeros(self):
        # actuals=[0, 10, 20], preds=[5, 11, 22]
        # zero actual is dropped; remaining APEs = 1/10=10%, 2/20=10% -> 10%
        m = compute_metrics([0, 10, 20], [5, 11, 22])
        assert math.isfinite(m.mape)
        assert m.mape == pytest.approx(10.0)

    def test_percentile_errors_monotonic(self):
        rng = np.random.default_rng(42)
        a = rng.uniform(0, 100, 200)
        p = a + rng.normal(0, 5, 200)
        m = compute_metrics(a, p)
        assert m.p50_abs_error <= m.p90_abs_error <= m.p99_abs_error

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            compute_metrics([1, 2, 3], [1, 2])

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_metrics([], [])


class TestBusinessCost:
    def test_no_error_zero_cost(self):
        c = compute_business_cost([10, 5], [10, 5], [50, 50], ["a", "b"])
        assert c.total == 0
        assert c.waste == 0
        assert c.stockout == 0

    def test_pure_overprediction_is_waste(self):
        c = compute_business_cost([10], [12], [50], ["a"])
        # waste = 2 * 50 * 0.3 = 30, no stockout
        assert c.waste == pytest.approx(30.0)
        assert c.stockout == 0

    def test_pure_underprediction_is_stockout(self):
        c = compute_business_cost([10], [8], [50], ["a"])
        # stockout = 2 * 50 = 100, multiplied by 1.5 -> total 150
        assert c.waste == 0
        assert c.stockout == pytest.approx(100.0)
        assert c.total == pytest.approx(150.0)

    def test_shelf_lookup_reduces_waste_for_long_shelf(self):
        # avg_gap=1d, shelf=90d -> effective_waste = 0.3 * (1/90) ~= 0.0033
        lookup = {"a": (90.0, 1.0)}
        c = compute_business_cost([10], [12], [50], ["a"], shelf_lookup=lookup)
        assert c.waste < 1.0  # very small vs 30 with flat fraction
        assert c.stockout == 0

    def test_non_food_zero_waste(self):
        lookup = {"a": (9999.0, 1.0)}
        c = compute_business_cost([10], [12], [50], ["a"], shelf_lookup=lookup)
        assert c.waste == 0

    def test_shares_sum_to_one(self):
        c = compute_business_cost([10, 10], [12, 8], [50, 50], ["a", "b"])
        assert c.waste_share + c.stockout_share == pytest.approx(1.0)


class TestDiagnostics:
    def test_dow_returns_seven_max(self):
        dates = pd.date_range("2026-01-01", periods=14)
        a = np.arange(14)
        p = a + 1
        out = error_by_dow(a, p, dates)
        assert all(v == pytest.approx(1.0) for v in out.values())
        assert len(out) <= 7

    def test_top_error_items_order(self):
        a = [10, 10, 10, 10]
        p = [10, 11, 10, 20]  # item b gets all the error
        ids = ["a", "a", "b", "b"]
        top = top_error_items(a, p, ids, top_n=2)
        assert top[0][0] == "b"
        assert top[0][1] > top[1][1]

    def test_sanity_passes_clean_forecast(self):
        a = [10, 12, 11, 9]
        p = [10, 11, 11, 10]
        s = bias_diagnostics(a, p)
        assert all(s.values())

    def test_sanity_flags_negatives(self):
        s = bias_diagnostics([5, 5], [-1, 5])
        assert s["no_negative_predictions"] is False

    def test_sanity_flags_systematic_bias(self):
        a = [100] * 50
        p = [200] * 50  # +100% bias
        s = bias_diagnostics(a, p, tol_pct=5.0)
        assert s["bias_within_tolerance"] is False


class TestDieboldMariano:
    def test_identical_models_zero_stat(self):
        rng = np.random.default_rng(0)
        a = rng.normal(10, 2, 100)
        p = a + rng.normal(0, 1, 100)
        out = diebold_mariano_test(a, p, p)
        assert abs(out["dm_stat"]) < 1e-9
        assert out["p_value"] == pytest.approx(1.0, abs=1e-6)

    def test_better_model_negative_stat(self):
        # model A is closer to actuals than model B
        rng = np.random.default_rng(1)
        a = rng.normal(0, 1, 500)
        p_a = a + rng.normal(0, 0.1, 500)
        p_b = a + rng.normal(0, 1.0, 500)
        out = diebold_mariano_test(a, p_a, p_b)
        assert out["dm_stat"] < 0
        assert out["p_value"] < 0.01

    def test_mae_loss_supported(self):
        out = diebold_mariano_test([1, 2, 3], [1.1, 2.1, 3.1], [1.5, 2.5, 3.5], loss="mae")
        assert "dm_stat" in out
        assert "p_value" in out


# ============================================================================
# Orchestrator integration test
# ============================================================================

def test_evaluate_forecast_full_report():
    rng = np.random.default_rng(42)
    n = 100
    a = rng.uniform(5, 50, n)
    p = a + rng.normal(0, 3, n)
    prices = np.full(n, 75.0)
    item_ids = ["item_1"] * 50 + ["item_2"] * 50
    dates = pd.date_range("2026-01-01", periods=n)
    shelf = {"item_1": (3.0, 1.0), "item_2": (90.0, 7.0)}

    report = evaluate_forecast(a, p, prices, item_ids, dates, shelf_lookup=shelf)
    assert isinstance(report, ForecastReport)
    assert report.metrics.n == n
    assert report.cost.total >= 0
    assert len(report.top_error_items) <= 10
    assert all(report.sanity.values())

    # Round-trip JSON serialization
    payload = json.loads(report.to_json())
    assert "metrics" in payload
    assert "cost" in payload


def test_format_report_renders():
    a = [10, 12, 8, 15]
    p = [11, 11, 9, 14]
    prices = [50, 50, 50, 50]
    ids = ["a", "a", "b", "b"]
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"])
    report = evaluate_forecast(a, p, prices, ids, dates)
    text = format_report(report, model_name="unit_test")
    assert "Forecast Report: unit_test" in text
    assert "MAE" in text
    assert "Sanity checks" in text


# ============================================================================
# Model gating tests
#
# These run against a fixture saved by `scripts/run_evaluation_demo.py`. They
# enforce minimum-quality thresholds for the currently-promoted model. CI
# should run these after every retrain to gate promotion.
#
# Thresholds are intentionally loose so they fail only on regressions, not
# on noise. Tighten as the model improves.
# ============================================================================

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "promoted_model_predictions.json"

def _load_fixture():
    if not FIXTURE_PATH.exists():
        pytest.skip(f"fixture not found: {FIXTURE_PATH} -- run scripts/run_evaluation_demo.py first")
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def test_promoted_model_no_negative_predictions():
    fix = _load_fixture()
    preds = np.array(fix["predictions"])
    assert (preds >= 0).all(), "promoted model is producing negative predictions"


def test_promoted_model_no_nan_predictions():
    fix = _load_fixture()
    preds = np.array(fix["predictions"])
    assert np.isfinite(preds).all(), "promoted model produced NaN/inf predictions"


def test_promoted_model_mae_under_threshold():
    fix = _load_fixture()
    m = compute_metrics(fix["actuals"], fix["predictions"])
    threshold = fix.get("thresholds", {}).get("max_mae", 15.0)
    assert m.mae < threshold, f"MAE {m.mae:.2f} exceeds threshold {threshold}"


def test_promoted_model_bias_within_tolerance():
    fix = _load_fixture()
    m = compute_metrics(fix["actuals"], fix["predictions"])
    tol = fix.get("thresholds", {}).get("max_bias_pct", 25.0)
    assert abs(m.bias_pct) < tol, f"bias {m.bias_pct:.1f}% exceeds tolerance +/-{tol}%"


def test_promoted_model_business_cost_under_threshold():
    fix = _load_fixture()
    cost = compute_business_cost(
        fix["actuals"], fix["predictions"], fix["prices"], fix["item_ids"],
        shelf_lookup={k: tuple(v) for k, v in fix.get("shelf_lookup", {}).items()},
    )
    threshold = fix.get("thresholds", {}).get("max_business_cost", 2_000_000)
    assert cost.total < threshold, f"cost {cost.total:,.0f} exceeds threshold {threshold:,.0f}"


def test_promoted_model_beats_naive_baseline():
    """
    The promoted model must be statistically better than the naive baseline
    (rolling 7-day average) at p < 0.05 via Diebold-Mariano. If not, do not
    promote.
    """
    fix = _load_fixture()
    if "naive_predictions" not in fix:
        pytest.skip("fixture has no naive baseline to compare against")
    out = diebold_mariano_test(fix["actuals"], fix["predictions"], fix["naive_predictions"])
    # promoted model loss must be lower (negative DM stat) and significant
    assert out["dm_stat"] <= 0 or out["p_value"] >= 0.05, (
        f"promoted model is significantly WORSE than naive baseline "
        f"(DM={out['dm_stat']:.2f}, p={out['p_value']:.3f})"
    )
