"""
stitcher.py -- Loving Loyalty AI Suite, Pillar 1: Sales Forecasting

Rolling Reforecast Stitching (SRS Section 5).

For date ranges that exceed 14 days, breaks the range into overlapping
14-day forecast windows.  Each window uses its own training cutoff (the
day before the window starts).  For any date covered by multiple windows,
the prediction from the window whose training cutoff is closest (most
recent) to that date wins.

No single prediction window ever exceeds 14 days.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Maximum days a single prediction window may span (SRS Section 5)
_MAX_WINDOW_DAYS = 14
# Overlap between consecutive windows (allows the stitcher to prefer the
# prediction from the window whose training cutoff is closer to the date)
_WINDOW_OVERLAP_DAYS = 7


def _build_windows(
    start_date: date,
    end_date: date,
    max_window: int = _MAX_WINDOW_DAYS,
    overlap: int = _WINDOW_OVERLAP_DAYS,
) -> list[tuple[date, date, date]]:
    """Return a list of (window_start, window_end, training_cutoff) tuples.

    The training cutoff for each window is the day before window_start,
    so the model for that window is trained only on data available before
    the window begins.

    Windows advance by (max_window - overlap) days each step, ensuring
    the total range is covered without any single window exceeding max_window.
    """
    stride = max_window - overlap
    if stride < 1:
        stride = 1

    windows: list[tuple[date, date, date]] = []
    win_start = start_date

    while win_start <= end_date:
        win_end = min(win_start + timedelta(days=max_window - 1), end_date)
        training_cutoff = win_start - timedelta(days=1)
        windows.append((win_start, win_end, training_cutoff))
        if win_end >= end_date:
            break
        win_start = win_start + timedelta(days=stride)

    return windows


def stitch_forecasts(
    daily_df: pd.DataFrame,
    start_date: date,
    end_date: date,
    predict_fn: Callable[[pd.DataFrame, date, date, Optional[int]], list[dict]],
    place_id: Optional[int] = None,
) -> list[dict]:
    """Generate stitched item-level forecasts for an arbitrary date range.

    For ranges <= 14 days, a single window is used (no stitching needed).
    For longer ranges, the range is split into overlapping 14-day windows.
    Overlapping dates are resolved by preferring the window whose training
    cutoff is closest (most recent) to the target date.

    Args:
        daily_df: Historical daily demand DataFrame.  Each window receives
                  only the rows up to (and including) that window's training
                  cutoff, preventing look-ahead leakage.
        start_date: First forecast date (inclusive).
        end_date: Last forecast date (inclusive).
        predict_fn: Callable with signature
                    ``predict_fn(daily_df, start, end, place_id) -> list[dict]``
                    where each dict has at least the keys returned by
                    ForecastPredictor.predict().
        place_id: Optional restaurant filter forwarded to predict_fn.

    Returns:
        Stitched list of prediction dicts, one per (item_id, date), ordered
        by date then item_id.  The ``forecast_window`` key is added to each
        dict with the window's training cutoff date string for diagnostics.
    """
    total_days = (end_date - start_date).days + 1

    if total_days <= _MAX_WINDOW_DAYS:
        # Fast path: single window, no stitching needed
        results = predict_fn(daily_df, start_date, end_date, place_id)
        cutoff = (start_date - timedelta(days=1)).isoformat()
        for r in results:
            r["forecast_window"] = cutoff
        return results

    windows = _build_windows(start_date, end_date)
    logger.info(
        "Stitching %d-day range into %d overlapping windows (max=%d days each)",
        total_days,
        len(windows),
        _MAX_WINDOW_DAYS,
    )

    daily_df = daily_df.copy()
    daily_df["date"] = pd.to_datetime(daily_df["date"])

    # Key: (item_id, place_id, date_str) -> best prediction dict
    # Value also stores the training_cutoff so we can resolve overlaps
    best: dict[tuple, dict] = {}

    for win_start, win_end, training_cutoff in windows:
        cutoff_ts = pd.Timestamp(training_cutoff)
        # Give the window only data up to its training cutoff
        window_df = daily_df[daily_df["date"] <= cutoff_ts]

        logger.debug(
            "Window %s – %s (cutoff %s): %d history rows",
            win_start,
            win_end,
            training_cutoff,
            len(window_df),
        )

        try:
            window_results = predict_fn(window_df, win_start, win_end, place_id)
        except Exception:
            logger.exception(
                "Forecast window %s – %s failed; skipping", win_start, win_end
            )
            continue

        cutoff_str = training_cutoff.isoformat()
        for r in window_results:
            r["forecast_window"] = cutoff_str
            date_str = r["date"]
            item_id = r.get("item_id")
            p_id = r.get("place_id", place_id or 0)
            key = (item_id, p_id, date_str)

            if key not in best:
                best[key] = r
            else:
                # Prefer the window whose training cutoff is more recent
                # (i.e. closer to the forecast date)
                existing_cutoff = best[key]["forecast_window"]
                if cutoff_str > existing_cutoff:
                    best[key] = r

    stitched = list(best.values())
    stitched.sort(key=lambda r: (r["date"], str(r.get("item_id", ""))))
    logger.info("Stitched %d predictions across %d windows", len(stitched), len(windows))
    return stitched
