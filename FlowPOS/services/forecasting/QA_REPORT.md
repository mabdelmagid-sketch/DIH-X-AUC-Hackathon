# QA Report — SRS Implementation Verification

**Date:** 2026-03-31
**QA Agent:** qa
**Working directory:** `FlowPOS/services/forecasting`

---

## Task #1 — Rolling Reforecast Stitching

**File:** `src/forecast/stitcher.py`
**Status: PASS**

### Checks

| Check | Result | Notes |
|-------|--------|-------|
| Ranges > 14 days broken into windows | PASS | `_build_windows()` creates overlapping 14-day windows with stride=7 |
| No single window exceeds 14 days | PASS | `win_end = min(win_start + timedelta(days=13), end_date)` enforces this |
| Exactly 14 days: single window | PASS | Fast path taken when `total_days <= 14`; no stitching |
| 15 days: 2 windows (days 1-14 and 8-15) | PASS | Verified programmatically |
| 30 days: 4 windows, all <= 14 days | PASS | Verified programmatically |
| Full coverage (no gaps) | PASS | All dates in 30-day range covered by at least one window |
| Overlapping dates: closest cutoff wins | PASS | `cutoff_str > existing_cutoff` comparison correctly prefers newer cutoff |
| Look-ahead prevention | PASS | `window_df = daily_df[daily_df["date"] <= cutoff_ts]` limits each window to its training data |
| `forecast_window` diagnostic key added | PASS | Added to each result with training cutoff date |

### Edge Case Results
- **14-day range**: 1 window (span=14), no stitching — correct
- **15-day range**: 2 windows (spans 14 and 8) — correct
- **30-day range**: 4 windows (spans 14, 14, 14, 9) — correct
- **Overlap resolution**: date 2024-01-08 covered by both window-1 (cutoff 2023-12-31) and window-2 (cutoff 2024-01-07); result uses cutoff 2024-01-07 — correct

---

## Task #2 — Lag-Free Monthly Model

**File:** `src/forecast/monthly_model.py`
**Status: PASS**

### Checks

| Check | Result | Notes |
|-------|--------|-------|
| Only trend/seasonality features | PASS | `_MONTHLY_FEATURE_COLS` contains only: month, quarter, week_of_year, day_of_week, is_weekend, Fourier terms (8 cols), expanding_mean, wow_growth |
| No lag_1d, lag_7d, lag_14d, lag_28d | PASS | None present in feature list |
| No rolling_mean or rolling_std features | PASS | None present in feature list |
| Reduced confidence (×0.6) | PASS | `_CONFIDENCE_SCALE = 0.6`; `confidence = base_confidence * 0.6` |
| Confidence clamped to [0.0, 1.0] | PASS | `max(0.0, min(1.0, confidence))` enforced |
| Separate from main model | PASS | `MonthlyRevenueModel` is an entirely independent class in its own file |
| `model_type` = `"monthly_lag_free"` | PASS | Explicitly set on each result dict |
| Never used for operational/item decisions | PASS | Class is only instantiated directly; not referenced in predictor.py |
| Fallback buffer 1.27 (no rolling_std for lag-free) | PASS | `_FALLBACK_BUFFER = 1.27` applied in predict() |

### Confidence Calculation Verification
- Input `base_confidence=0.75` → output `0.75 * 0.6 = 0.45` — correct
- Input `base_confidence=1.0` → output `0.6` — correct and clamped

### Minor Observations
- `wow_growth` uses a 7-day historical shift. This is computed from training data only and is a proxy for trend, not a future-leaking lag. Consistent with SRS intent.
- `expanding_mean` is frozen from training history — no look-ahead leak.

---

## Task #3 — Assertions and Tests

**File:** `tests/test_srs_assertions.py`
**Status: PASS — 37/37 tests pass**

### Test Run
```
$ python -m pytest tests/test_srs_assertions.py -v
======================== 37 passed in 1.35s ========================
```

### Coverage

| SRS Section 8 Constraint | Tests | Result |
|--------------------------|-------|--------|
| `buffer_multiplier` always > 1.0 and ≤ 2.0 | 7 tests in `TestBufferMultiplier` | PASS |
| `confidence` always 0.0–1.0 | 7 tests in `TestConfidenceRange` | PASS |
| `forecast_drivers` always ≥ 3 items, never empty | 5 tests in `TestForecastDrivers` | PASS |
| `lower ≤ predicted ≤ upper` | 9 tests in `TestPredictionBounds` | PASS |
| Newsvendor formula (critical ratio, z-score) | 4 tests in `TestNewsvendorFormula` | PASS |
| Stitcher windows ≤ 14 days | 5 tests in `TestStitcherWindowSize` | PASS |

### Specific Checks Passed
- `_FALLBACK_BUFFER == 1.27` asserted
- `_BUFFER_CLAMP == (1.0, 2.0)` asserted
- Confidence monotonically non-decreasing with history depth
- Monthly model confidence scaled down by factor 0.6
- Buffer uses `rolling_std_14d` not all-history std (verified via data construction)
- Stitcher full-range coverage verified programmatically
- Overlap date resolution: most recent cutoff wins

---

## Task #4 — Per-Item Newsvendor Buffer

**File:** `src/forecast/trainer.py` (`compute_newsvendor_buffers`) + `src/forecast/predictor.py`
**Status: PASS**

### Checks

| Check | Result | Notes |
|-------|--------|-------|
| Critical ratio = 0.833 | PASS | `1.5 / (1.5 + 0.3) = 0.8333` |
| z_0.833 ≈ 0.967 | PASS | `scipy.stats.norm.ppf(0.8333) = 0.9674` |
| Formula: `1 + z * sigma / mean` | PASS | `buf = 1.0 + _Z_CRITICAL * rolling_std_14d / mean_d` |
| Clamped to [1.0, 2.0] | PASS | `np.clip(buf, 1.0, 2.0)` |
| Fallback 1.27 for items < 30 days | PASS | `if n_days < 30: buf = _FALLBACK_BUFFER` (1.27) |
| Predictor clamps buffer again | PASS | `float(np.clip(buffer, 1.0, 2.0))` in predictor.py:248 |
| Stable item buffer (~1.12) | PASS | sigma=1, mean=10 → 1.097 |
| Volatile item buffer (~1.45) | PASS | sigma=5, mean=10 → 1.484 |
| Zero-mean guard (no division by zero) | PASS | `mean_d < 0.01` falls back to 1.27 |

### Constants Verification
```
_CRITICAL_RATIO = 1.5 / (1.5 + 0.3) = 0.8333  ✓
_Z_CRITICAL = norm.ppf(0.8333) = 0.9674         ✓ (≈ 0.967)
_MIN_HISTORY_FOR_BUFFER = 30                     ✓
_FALLBACK_BUFFER = 1.27                          ✓
_BUFFER_CLAMP = (1.0, 2.0)                       ✓
```

---

## Task #5 — API Response Wrapper

**Files:** `src/api/response_wrapper.py`, `src/api/forecast_routes.py`, `src/api/forecast_items_routes.py`
**Status: PASS WITH ONE BUG**

### New File: `response_wrapper.py`
The wrapper module was correctly created with:
- `wrap_response(payload)` → `{ "data": <payload>, "meta": { "version", "timestamp", "requestId" } }`
- `wrap_error(status_code, code, message, details)` → raises `HTTPException` with `{ "error": { "code", "message", "details", "timestamp", "requestId" } }`
- `meta.requestId` is a new UUID per call
- `meta.timestamp` is UTC ISO-8601 (ends in "Z")
- `meta.version` = `"1.0.0"`

### `forecast_items_routes.py` — PASS
- Success response at line 286 correctly wrapped: `return wrap_response(ForecastItemsResponse(...))`
- All error paths use `raise wrap_error(...)`
- No unwrapped returns found

### `forecast_routes.py` — PASS WITH BUG

**BUG FOUND: Cache hit path returns unwrapped response**

Location: `src/api/forecast_routes.py:540`

```python
cached = _get_cached(ck)
if cached is not None:
    return AiForecastResponse(**cached)   # <-- MISSING wrap_response()!
```

The non-cached path correctly returns `wrap_response(AiForecastResponse(**payload))` at line 682, but the cache hit path at line 540 returns the raw Pydantic model without the `{ data, meta }` envelope. This means repeated requests for the same forecast (within the 5-minute TTL) will receive a response that is missing the `meta` field, breaking the API contract.

**Fix required:**
```python
if cached is not None:
    return wrap_response(AiForecastResponse(**cached))
```

### Other Checks for `forecast_routes.py`

| Check | Result | Notes |
|-------|--------|-------|
| POST /ai/forecast success response wrapped | PASS | line 682: `return wrap_response(...)` |
| POST /ai/forecast/items success response wrapped | PASS | line 949: `return wrap_response(...)` |
| GET /ai/forecast/health response wrapped | PASS | lines 1014, 1018: `return wrap_response(...)` |
| Error responses use `wrap_error` | PASS | All `raise HTTPException` replaced with `raise wrap_error(...)` |
| `meta.version` present | PASS | `_API_VERSION = "1.0.0"` |
| `meta.timestamp` present | PASS | UTC ISO-8601 with Z suffix |
| `meta.requestId` present | PASS | UUID4 generated per call |
| Error has `code`, `message`, `details`, `timestamp`, `requestId` | PASS | All 5 fields present |
| Wrapper consistent across both route files | PASS | Both import from same `response_wrapper.py` |
| Cache hit path wrapped | **FAIL** | `forecast_routes.py:540` returns unwrapped |

---

## Summary

| Task | Status | Issues |
|------|--------|--------|
| #1 Rolling Reforecast Stitching | **PASS** | None |
| #2 Lag-Free Monthly Model | **PASS** | None |
| #3 Assertions and Tests | **PASS** | 37/37 tests pass |
| #4 Newsvendor Per-Item Buffer | **PASS** | None |
| #5 API Response Wrapper | **PASS WITH BUG** | Cache hit path returns unwrapped response |

### Bug Requiring Fix

**File:** `/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/src/api/forecast_routes.py`
**Line:** 540
**Issue:** Cache hit path for `POST /ai/forecast` returns raw `AiForecastResponse` without `{ data, meta }` envelope.
**Fix:** Change `return AiForecastResponse(**cached)` to `return wrap_response(AiForecastResponse(**cached))`
