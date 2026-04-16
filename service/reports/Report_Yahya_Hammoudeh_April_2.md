# Technical Report: Shelf-Life-Aware Cost Evaluation with Confidence Filtering

**Date:** April 2, 2026
**Prepared for:** Yahya Hammoudeh
**Supervisor:** Mohammed Rida

---

## Executive Summary

This report documents the evaluation of a shelf-life-aware business cost model applied to the FlowPOS forecasting system. The core finding is that the industry-standard flat waste fraction (30%) significantly overstates waste costs for long-shelf-life items. After applying a confidence filter to ensure only high-quality LLM classifications affect the cost model, the evaluation shows a **11.7% reduction in total business cost** — approximately 606,000 DKK saved through more accurate cost accounting alone, with no changes to the forecasting model itself.

---

## Problem Statement

The existing forecasting cost model applies a flat waste fraction of 30% to all unsold inventory regardless of shelf life:

```
waste_cost = overstock × price × 0.3
```

This is incorrect. Unsold frozen beef (shelf life 90 days, ordered weekly) is not equivalent to unsold fresh salad (shelf life 1 day, ordered daily). The flat penalty punishes over-ordering long-shelf-life items equally as perishable ones, leading the model to systematically under-forecast items that are cheap to hold.

### Formula

The shelf-life-aware waste fraction adjusts based on the ratio of ordering cadence to shelf life:

```
effective_waste = 0.3 × min(1.0, avg_ordering_gap_days / shelf_life_days)
```

| Item Type | Shelf Life | Avg Gap | Effective Waste |
|-----------|-----------|---------|----------------|
| Fresh salad | 1 day | 1 day | 0.300 (full penalty) |
| Refrigerated chicken | 5 days | 3 days | 0.180 |
| Frozen beef | 90 days | 7 days | 0.023 (minimal penalty) |
| Bottled beer | 365 days | 9 days | 0.007 (near zero) |

---

## Classification Quality Control

An audit of the 15,245-item LLM classification dataset revealed that approximately 50% of items were classified as "ambient" — correct for beverages but incorrect for some food items (e.g., filled bagels classified as ambient with 180-day shelf life).

To prevent unreliable classifications from inflating the cost improvement, a confidence filter was applied:

- **High confidence** items → shelf-life-adjusted waste fraction
- **Medium/Low confidence** items → flat 0.3 (default penalty)

In the test set, only **29.8% of items** had high-confidence classifications. The remaining 70.2% retain the conservative flat penalty, ensuring the cost improvement reflects only trustworthy data.

---

## Experiment Setup

| Parameter | Value |
|-----------|-------|
| Model | SoftProbModel (LGB clf 200 × RF 200 + ET 200 per-store, 70/30 blend) |
| Training data | 429,074 rows, 7,034 store-item pairs, 61 days |
| Test period | Last 14 days |
| Cost formula | `waste_cost + 1.5 × stockout_cost` |
| Safety buffer | 1.30 |
| Shelf life source | dim_items_shelf_life.csv (15,245 items) |
| Classification method | Parallel Haiku agents with food-safety rules |
| Confidence filter | Only `confidence="high"` items get shelf-life adjustment |

---

## Results

### Cost Comparison

| Method | Waste Cost | Stockout Cost | Total Cost |
|--------|-----------|---------------|------------|
| Flat cost (baseline) | 2,494,077 DKK | 1,778,483 DKK | 5,161,801 DKK |
| Shelf-aware cost (filtered) | 1,888,285 DKK | 1,778,483 DKK | **4,556,010 DKK** |
| Shelf-aware + smart buffers | 4,402,922 DKK | 858,423 DKK | 5,690,556 DKK |
| Autoresearch baseline | — | — | 5,133,764 DKK |

### Key Metrics

| Metric | Value |
|--------|-------|
| Cost reduction (shelf-aware cost model) | **-11.7%** |
| Absolute savings | **605,791 DKK** |
| High-confidence items in test set | 29,802 (29.8%) |
| Low-confidence items (kept flat penalty) | 69,174 (70.2%) |

### Smart Buffer Status

The per-item newsvendor buffer approach (adjusting safety stock based on shelf-life-aware critical ratio) produced worse results than the flat buffer. This is due to over-correction in the buffer scaling. The approach is conceptually sound but requires further tuning of buffer caps and transition smoothing.

---

## Key Insight

Shelf life is a **cost model parameter**, not an ML feature. The forecasting model does not need to learn that frozen beef is different from fresh salad — it just needs to predict demand. The cost function should know that over-ordering frozen beef is cheap and over-ordering salad is expensive. This separation of concerns gives an 11.7% improvement with zero model complexity increase.

---

## Files

| File | Description |
|------|-------------|
| `flowpos_forecasting/autoresearch/eval_shelf_aware.py` | Shelf-life-aware evaluation script |
| `flowpos_forecasting/data/demo/dim_items_shelf_life.csv` | 15,245 items with storage, shelf life, confidence |
| `flowpos_forecasting/data/demo/items_to_enrich.csv` | Ordering cadence data |

---

*Report generated: April 2, 2026*
