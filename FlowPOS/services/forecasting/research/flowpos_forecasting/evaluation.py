"""
Post-training forecast evaluation pipeline.

A reusable module for evaluating any demand-forecasting model after training.
Designed to be plugged into CI / regression tests, batch jobs, or notebooks.

The pipeline answers four questions a forecasting team should ask after every
training run:

  1. How accurate is it?              -> compute_metrics
  2. How costly are its errors?        -> compute_business_cost (shelf-aware)
  3. Where does it fail?               -> error_by_dow, top_error_items, bias_diagnostics
  4. Is it actually better than what we already had?  -> diebold_mariano_test

Plus a high-level orchestrator (`evaluate_forecast`) that runs everything and
returns a structured `ForecastReport` ready for assertion-based regression
tests.

Example
-------
>>> import numpy as np
>>> from flowpos_forecasting.evaluation import evaluate_forecast
>>> report = evaluate_forecast(
...     actuals=np.array([10, 12, 8, 15]),
...     predictions=np.array([11, 11, 9, 14]),
...     prices=np.array([50, 50, 50, 50]),
...     item_ids=["a", "a", "b", "b"],
...     dates=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
...     shelf_lookup={"a": (3.0, 1.0), "b": (90.0, 7.0)},
... )
>>> assert report.metrics.mae < 2.0
>>> assert report.business_cost < 1000
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence, Tuple

import json
import math
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Constants used by the shelf-aware business cost.
# These match the values used across the project's evaluation harnesses so
# numbers in this module are directly comparable to other reports.
# ----------------------------------------------------------------------------
DEFAULT_WASTE_FRACTION = 0.3
DEFAULT_STOCKOUT_MULTIPLIER = 1.5
NON_FOOD_SHELF_LIFE = 9999.0


# ============================================================================
# Data containers
# ============================================================================

@dataclass
class ForecastMetrics:
    """Standard accuracy metrics for a single forecast set."""
    n: int
    mae: float
    rmse: float
    mape: float            # ignores zero-actual rows
    smape: float
    bias: float            # mean(pred - actual); >0 = systematic over-prediction
    bias_pct: float        # bias / mean(actual)
    r2: float
    p50_abs_error: float
    p90_abs_error: float
    p99_abs_error: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CostBreakdown:
    """Shelf-aware business cost decomposition."""
    total: float
    waste: float
    stockout: float
    waste_share: float
    stockout_share: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ForecastReport:
    """Full post-training evaluation result."""
    metrics: ForecastMetrics
    cost: CostBreakdown
    dow_errors: Dict[str, float]
    top_error_items: List[Tuple[str, float]]
    sanity: Dict[str, bool]

    def to_dict(self) -> Dict:
        return {
            "metrics": self.metrics.to_dict(),
            "cost": self.cost.to_dict(),
            "dow_errors": self.dow_errors,
            "top_error_items": [{"item_id": str(i), "abs_error_sum": float(e)} for i, e in self.top_error_items],
            "sanity": self.sanity,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ============================================================================
# Core metric functions
# ============================================================================

def _to_arrays(actuals, predictions) -> Tuple[np.ndarray, np.ndarray]:
    a = np.asarray(actuals, dtype=float)
    p = np.asarray(predictions, dtype=float)
    if a.shape != p.shape:
        raise ValueError(f"actuals shape {a.shape} != predictions shape {p.shape}")
    if a.size == 0:
        raise ValueError("empty actuals/predictions")
    return a, p


def compute_metrics(actuals, predictions) -> ForecastMetrics:
    """Standard accuracy metrics with no business assumptions baked in."""
    a, p = _to_arrays(actuals, predictions)
    err = p - a
    abs_err = np.abs(err)

    mae = float(abs_err.mean())
    rmse = float(np.sqrt((err ** 2).mean()))

    nz = a != 0
    mape = float((abs_err[nz] / np.abs(a[nz])).mean() * 100) if nz.any() else float("nan")

    denom = (np.abs(a) + np.abs(p))
    nz_smape = denom != 0
    smape = float((2 * abs_err[nz_smape] / denom[nz_smape]).mean() * 100) if nz_smape.any() else float("nan")

    bias = float(err.mean())
    mean_a = float(a.mean())
    bias_pct = float(bias / mean_a * 100) if mean_a != 0 else float("nan")

    ss_res = float(((a - p) ** 2).sum())
    ss_tot = float(((a - mean_a) ** 2).sum())
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    return ForecastMetrics(
        n=int(a.size),
        mae=mae,
        rmse=rmse,
        mape=mape,
        smape=smape,
        bias=bias,
        bias_pct=bias_pct,
        r2=r2,
        p50_abs_error=float(np.percentile(abs_err, 50)),
        p90_abs_error=float(np.percentile(abs_err, 90)),
        p99_abs_error=float(np.percentile(abs_err, 99)),
    )


def compute_business_cost(
    actuals,
    predictions,
    prices,
    item_ids: Sequence,
    shelf_lookup: Optional[Dict[str, Tuple[float, float]]] = None,
    waste_fraction: float = DEFAULT_WASTE_FRACTION,
    stockout_multiplier: float = DEFAULT_STOCKOUT_MULTIPLIER,
) -> CostBreakdown:
    """
    Shelf-aware business cost decomposition.

    cost = waste + stockout_multiplier * stockout
    waste     = sum_i max(pred_i - actual_i, 0) * price_i * effective_waste_i
    stockout  = sum_i max(actual_i - pred_i, 0) * price_i

    `shelf_lookup`: optional {item_id -> (shelf_life_days, avg_gap_days)}.
    Items with shelf_life >= NON_FOOD_SHELF_LIFE get a waste fraction of zero.
    If `shelf_lookup` is None, every item uses the flat `waste_fraction`.
    """
    a, p = _to_arrays(actuals, predictions)
    pr = np.asarray(prices, dtype=float)
    if pr.shape != a.shape:
        raise ValueError(f"prices shape {pr.shape} != actuals shape {a.shape}")
    if len(item_ids) != a.size:
        raise ValueError(f"item_ids len {len(item_ids)} != actuals size {a.size}")

    if shelf_lookup is None:
        wf = np.full(a.size, waste_fraction)
    else:
        wf = np.empty(a.size)
        for i, iid in enumerate(item_ids):
            sl, ag = shelf_lookup.get(str(iid), (3.0, 1.0))
            if sl >= NON_FOOD_SHELF_LIFE:
                wf[i] = 0.0
            else:
                wf[i] = waste_fraction * min(1.0, ag / max(sl, 0.5))

    p_clip = np.clip(p, 0, None)
    over = np.maximum(p_clip - a, 0)
    under = np.maximum(a - p_clip, 0)
    waste = float((over * pr * wf).sum())
    stockout = float((under * pr).sum())
    total = waste + stockout_multiplier * stockout
    waste_share = waste / total if total > 0 else 0.0
    stockout_share = (stockout_multiplier * stockout) / total if total > 0 else 0.0

    return CostBreakdown(
        total=total,
        waste=waste,
        stockout=stockout,
        waste_share=waste_share,
        stockout_share=stockout_share,
    )


# ============================================================================
# Diagnostic functions
# ============================================================================

def error_by_dow(actuals, predictions, dates) -> Dict[str, float]:
    """
    Mean absolute error broken down by day of week.
    Useful to spot weekday-specific bias (e.g. systematically under-predicting
    Saturdays).
    """
    a, p = _to_arrays(actuals, predictions)
    d = pd.to_datetime(dates)
    if len(d) != a.size:
        raise ValueError(f"dates len {len(d)} != actuals size {a.size}")
    abs_err = np.abs(p - a)
    df = pd.DataFrame({"abs_err": abs_err, "dow": d.dayofweek})
    out = df.groupby("dow")["abs_err"].mean().to_dict()
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return {names[k]: float(v) for k, v in out.items()}


def top_error_items(
    actuals, predictions, item_ids: Sequence, top_n: int = 10
) -> List[Tuple[str, float]]:
    """
    Items contributing the most absolute error in total. Use this to identify
    which items the model fails on most badly so they can be investigated
    individually.
    """
    a, p = _to_arrays(actuals, predictions)
    abs_err = np.abs(p - a)
    df = pd.DataFrame({"item_id": [str(i) for i in item_ids], "abs_err": abs_err})
    g = df.groupby("item_id")["abs_err"].sum().sort_values(ascending=False)
    return [(iid, float(v)) for iid, v in g.head(top_n).items()]


def bias_diagnostics(actuals, predictions, tol_pct: float = 5.0) -> Dict[str, bool]:
    """
    Quick checks that should pass for any reasonable forecast.
    Returns a dict of named booleans, all of which should be True.
    """
    a, p = _to_arrays(actuals, predictions)
    p_clip = np.clip(p, 0, None)
    metrics = compute_metrics(a, p_clip)

    return {
        "no_negative_predictions": bool((p >= 0).all()),
        "no_nan_predictions": bool(np.isfinite(p).all()),
        "bias_within_tolerance": bool(abs(metrics.bias_pct) < tol_pct),
        "mae_below_actual_mean": bool(metrics.mae < float(a.mean()) if a.mean() > 0 else True),
        "predictions_have_variance": bool(p.std() > 0),
    }


# ============================================================================
# Statistical model comparison
# ============================================================================

def diebold_mariano_test(
    actuals,
    preds_a,
    preds_b,
    h: int = 1,
    loss: str = "mse",
) -> Dict[str, float]:
    """
    Diebold-Mariano test for equal forecast accuracy between two models.

    Null hypothesis: both forecasts have equal expected loss.
    A negative DM stat with small p-value means model A is significantly
    BETTER than model B (its loss is lower).

    Parameters
    ----------
    actuals : array-like
    preds_a : array-like   first model's predictions
    preds_b : array-like   second model's predictions
    h       : int          forecast horizon (1 for one-step-ahead)
    loss    : "mse" or "mae"

    Returns
    -------
    {"dm_stat": float, "p_value": float, "n": int, "mean_loss_diff": float}
    """
    a = np.asarray(actuals, dtype=float)
    pa = np.asarray(preds_a, dtype=float)
    pb = np.asarray(preds_b, dtype=float)
    if not (a.shape == pa.shape == pb.shape):
        raise ValueError("shape mismatch in DM test")

    if loss == "mse":
        e_a = (a - pa) ** 2
        e_b = (a - pb) ** 2
    elif loss == "mae":
        e_a = np.abs(a - pa)
        e_b = np.abs(a - pb)
    else:
        raise ValueError(f"unknown loss {loss}")

    d = e_a - e_b
    n = d.size
    mean_d = float(d.mean())

    # Long-run variance with Newey-West correction up to lag h-1
    var_d = float(d.var(ddof=1))
    for lag in range(1, h):
        cov = float(np.cov(d[:-lag], d[lag:], bias=True)[0, 1])
        var_d += 2 * cov
    var_d = max(var_d, 1e-12)

    dm_stat = mean_d / math.sqrt(var_d / n)
    # Two-sided p-value via standard normal approximation
    p_value = 2 * (1 - _norm_cdf(abs(dm_stat)))

    return {
        "dm_stat": float(dm_stat),
        "p_value": float(p_value),
        "n": int(n),
        "mean_loss_diff": mean_d,
    }


def _norm_cdf(x: float) -> float:
    """Standard normal CDF without scipy dependency."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ============================================================================
# Orchestrator
# ============================================================================

def evaluate_forecast(
    actuals,
    predictions,
    prices,
    item_ids: Sequence,
    dates,
    shelf_lookup: Optional[Dict[str, Tuple[float, float]]] = None,
    top_n_error_items: int = 10,
) -> ForecastReport:
    """
    Run the full post-training evaluation pipeline and return a structured
    report. This is the function regression tests should call.
    """
    metrics = compute_metrics(actuals, predictions)
    cost = compute_business_cost(actuals, predictions, prices, item_ids, shelf_lookup)
    dow = error_by_dow(actuals, predictions, dates)
    top_items = top_error_items(actuals, predictions, item_ids, top_n=top_n_error_items)
    sanity = bias_diagnostics(actuals, predictions)
    return ForecastReport(
        metrics=metrics,
        cost=cost,
        dow_errors=dow,
        top_error_items=top_items,
        sanity=sanity,
    )


# ============================================================================
# Pretty printer (used by demo script and CI logs)
# ============================================================================

def format_report(report: ForecastReport, model_name: str = "model") -> str:
    m = report.metrics
    c = report.cost
    lines = []
    lines.append(f"=== Forecast Report: {model_name} ===")
    lines.append(f"  n predictions   : {m.n}")
    lines.append(f"  MAE             : {m.mae:.3f}")
    lines.append(f"  RMSE            : {m.rmse:.3f}")
    lines.append(f"  MAPE            : {m.mape:.2f}%")
    lines.append(f"  sMAPE           : {m.smape:.2f}%")
    lines.append(f"  Bias            : {m.bias:+.3f}  ({m.bias_pct:+.2f}%)")
    lines.append(f"  R^2             : {m.r2:.3f}")
    lines.append(f"  p50/p90/p99 |e| : {m.p50_abs_error:.2f} / {m.p90_abs_error:.2f} / {m.p99_abs_error:.2f}")
    lines.append("")
    lines.append(f"  Cost (DKK)      : {c.total:>14,.0f}")
    lines.append(f"    waste         : {c.waste:>14,.0f}  ({c.waste_share*100:.1f}%)")
    lines.append(f"    stockout x1.5 : {c.total - c.waste:>14,.0f}  ({c.stockout_share*100:.1f}%)")
    lines.append("")
    lines.append("  MAE by day of week:")
    for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        if d in report.dow_errors:
            lines.append(f"    {d}: {report.dow_errors[d]:.2f}")
    lines.append("")
    lines.append("  Top 5 error items:")
    for iid, e in report.top_error_items[:5]:
        lines.append(f"    {iid}: total |e| = {e:,.1f}")
    lines.append("")
    lines.append("  Sanity checks:")
    for k, v in report.sanity.items():
        mark = "PASS" if v else "FAIL"
        lines.append(f"    [{mark}] {k}")
    return "\n".join(lines)
