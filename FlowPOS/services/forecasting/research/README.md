# Demand Forecasting Research — Adam Aberbach

Research code backing the FlowPOS forecasting service.

## Timeline

| Date | Commit | Headline |
|---|---|---|
| 2026-04-01 | `research: Apr 1 — shelf-life classification pipeline` | 15,207 items classified (rules + Haiku agents) |
| 2026-04-02 | `research: Apr 2 — shelf-aware buffer tuning on demo` | log-scaled per-item buffers, -13.5% cost on demo |
| 2026-04-06 | `research: Apr 6 — production scale-up` | 2.4M orders, shelf-aware eval → 8.42M DKK (-29.1%) |
| 2026-04-07 | `research: Apr 7 — evaluation pipeline` | 29 pytest gates + Diebold-Mariano promotion test |
| 2026-04-14 | `research: Apr 14 — XGB-GPU + buffer cap sweep` | 6.56M DKK (cap=3), -31% vs production baseline |

## Layout

- `reports/`                     — per-date markdown + PDF write-ups
- `classification/`              — shelf-life classification scripts (April 1)
- `shelf_life_data/`             — produced shelf-life lookup CSVs
- `flowpos_forecasting/`         — cost / evaluation modules + tests
- `notebooks/`                   — training scripts and experiments
- `scripts/`                     — demo runners, CI helpers
- `results/`                     — experiment artifacts (JSON logs, charts)

## What's not here

The production database (`data/raw/production.db`, ~790 MB) is proprietary POS
data and is never committed. Scripts reference it by relative path; you need a
local copy to re-run.

## Final production recommendation

See `reports/Report_Adam_Aberbach_April_14.md`. TL;DR:

```python
GROUP_BUFFERS = {
    "ultra_fresh":    1.98,
    "fresh":          3.00,
    "medium":         3.00,
    "long_shelf":     3.00,
    "non_perishable": 3.00,
}
# Test cost: 6,558,810 DKK vs 9,498,367 DKK baseline (-31.0%).
```
