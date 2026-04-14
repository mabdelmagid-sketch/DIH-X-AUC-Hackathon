# Technical Report: Production-Scale Training & Shelf-Life Data Augmentation

**Date:** April 6, 2026
**Prepared for:** Adam Aberbach
**Supervisor:** Mohammed Rida

---

## Executive Summary

This report documents the scaling of the demand forecasting system from demo data to production data (2.4M orders across 494 stores), and the construction of a shelf-life data augmentation pipeline using parallel AI classification agents. The baseline production model achieves a total business cost of 11.87M DKK. After augmenting 12,348 items with shelf-life classifications and switching to shelf-life-aware evaluation, cost drops to **8.42M DKK (-29.1%)** with waste cost specifically reduced by 73.7%.

---

## Production Dataset

| Parameter | Demo | Production |
|-----------|------|------------|
| Database size | ~50 MB | 828 MB |
| Orders | ~100K | 2,266,131 |
| Line items | ~200K | 3,445,953 |
| Active stores | ~50 | 494 (678 total, filtered by >=30 days history) |
| Unique items in training | ~7,034 | 12,348 (top 30 per store) |
| Feature grid rows | ~430K | 2,259,684 |
| Date range | ~2 months | Oct 3 2025 - Apr 3 2026 (183 days) |
| Features | 61 | 68 |

All columns in the production SQLite database were untyped TEXT, requiring explicit numeric conversions for quantity, cost, price, and timestamps.

---

## Three-Phase Experiment Design

### Phase 1: Recency Sweep (LightGBM fixed)

Tested 10 recency configurations to isolate the optimal training window and decay rate before evaluating all models.

| Config | Cost (DKK) |
|--------|-----------|
| LGB window=120d decay=12d | **12,812,760** (baseline winner) |
| LGB window=90d decay=12d | 12,831,308 |
| LGB full-history decay=12d | 12,889,261 |
| LGB window=60d no-decay | 12,902,547 |
| LGB full-history decay=6d | 12,904,234 |
| LGB window=90d no-decay | 12,996,242 |

### Phase 2: Model Comparison (best recency from Phase 1)

Six model architectures evaluated with train_days=120, decay=12d:

| Rank | Model | Cost (DKK) | MAE | Train Time |
|------|-------|-----------|-----|------------|
| 1 | SoftProbV2 (LGB hierarchical) | 12,228,236 | 1.455 | 156s |
| 2 | XGBoost | 12,706,983 | 1.455 | 69s |
| 3 | LightGBM | 12,812,760 | 1.407 | 46s |
| 4 | Blend (LGB+XGB+CB avg) | 12,827,883 | 1.411 | 131s |
| 5 | CatBoost | 13,070,234 | 1.408 | 49s |
| 6 | ElasticNet | 13,228,950 | 1.539 | 65s |

Note: RandomForest, ExtraTrees, and Stacking were removed due to memory constraints on the 16GB machine. RF alone took 100+ minutes without `max_depth` limits due to fully-grown trees on 1.4M training rows.

### Phase 3: Safety Buffer Optimization

Buffer sweep on top 3 models. Higher buffers continued to reduce total cost because the stockout penalty (1.5x) dominates:

**Baseline best**: SoftProbV2 buf=1.40 -> **11,868,433 DKK** (waste: 4,203,070, stockout: 5,110,242)

---

## Shelf-Life Data Augmentation Pipeline

### Problem

The production training used a flat `WASTE_FRACTION = 0.3` for all items. As demonstrated in the demo evaluation (April 2), this overstates waste costs for long-shelf-life items.

### Challenge: 12,348 Items Need Classification

The demo dataset had ~2,285 items pre-classified. The production dataset has 12,348 unique training items, most with Danish-language titles and no existing shelf-life metadata.

### Two-Stage Classification Pipeline

**Stage 1: Rule-Based Classifier**

A keyword-matching classifier covering 20+ Danish food categories:

| Category | Keywords | Shelf Life |
|----------|----------|-----------|
| Alcoholic beverages | ol, fadol, vin, shots, gin, vodka... | 365d |
| Hot drinks | kaffe, espresso, latte, chai... | 365d |
| Pizza | pizza | 2d (fresh) / 90d (frozen if gap>=14d) |
| Kebab/wraps | kebab, durum, pita, falafel... | 1d (fresh) / 60d (frozen) |
| Fresh salads | salat, grontsag, tomat... | 3d |
| Frozen fried | pommes, fries, nuggets... | 90d |

Result: **7,127 items matched (57.7%)** with high/medium confidence.

**Stage 2: Parallel Haiku Agent Classification**

The remaining 5,221 items were split into 10 batches of ~523 items. Each batch was dispatched to a Haiku agent running in parallel, with instructions to classify based on Danish title and ordering cadence (`max_gap_days`).

Classification categories:
- `fresh_perishable` (1-2d): fresh sandwiches, sushi, open-face dishes
- `short_shelf` (3-7d): bread, pastries, cooked meals, dairy
- `medium_shelf` (14-60d): cheese, sauces, frozen foods, processed meats
- `long_shelf` (90-365d): beverages, alcohol, canned goods, snacks
- `non_food` (9999d): services (haircuts, massages, repairs), gift cards, entrance fees

10 agents completed in ~60 seconds total. All 5,221 items classified.

**Post-Processing**: Agent outputs used inconsistent storage_type values (e.g., "Refrigerated", "refrigerated/frozen", "Room Temperature"). A normalization step mapped all variants to 5 canonical types: ambient, refrigerated, dry, frozen, non_food.

### Final Coverage

| Metric | Value |
|--------|-------|
| Total training items | 12,348 |
| Rule-based (high confidence) | 7,127 (57.7%) |
| Haiku-classified | 5,221 (42.3%) |
| Coverage | **100%** |

**Shelf-life distribution:**

| Bucket | Items |
|--------|-------|
| 1-2 days (fresh) | 1,289 |
| 3-7 days (short) | 1,948 |
| 8-30 days (medium) | 2,723 |
| 31-90 days (long) | 1,474 |
| 91-365 days (shelf-stable) | 4,334 |
| >365 days (non-food) | 580 |

---

## Shelf-Aware Production Results

### Per-Item Waste Fraction

```
effective_waste = 0.3 * min(1.0, avg_gap_days / shelf_life_days)
```

Non-food items (shelf_life >= 9999) receive a waste fraction of 0.0.

### Phase 1 Recency (Shelf-Aware)

Best config shifted from windowed to full history:

| Config | Baseline Cost | Shelf-Aware Cost |
|--------|-------------|-----------------|
| window=120d, decay=12d | 12,812,760 (best) | 10,352,994 |
| **full history, decay=6d** | 12,904,234 | **10,020,346 (best)** |

### Phase 2 Ranking (Shelf-Aware)

| Rank | Model | Cost (DKK) |
|------|-------|-----------|
| 1 | SoftProbV2 (LGB hierarchical) | 9,395,177 |
| 2 | XGBoost | 9,986,183 |
| 3 | LightGBM | 10,020,346 |
| 4 | Blend (LGB+XGB+CB) | 10,119,622 |
| 5 | ElasticNet | 10,396,697 |
| 6 | CatBoost | 10,703,792 |

### Overall Best (Shelf-Aware + Buffer Sweep)

**LightGBM buf=1.40, full history, decay=6d**: **8,415,905 DKK**

---

## Comparative Results

| Metric | Baseline (flat waste) | Shelf-Aware | Improvement |
|--------|--------------------|-------------|-------------|
| **Total cost** | 11,868,433 DKK | **8,415,905 DKK** | **-29.1%** |
| Waste cost | 4,203,070 DKK | 1,105,724 DKK | -73.7% |
| Stockout cost | 5,110,242 DKK | 4,873,454 DKK | -4.6% |
| Mean cost/store | 24,025 DKK | 17,036 DKK | -29.1% |
| Median cost/store | 14,192 DKK | 9,942 DKK | -30.0% |
| Best model | SoftProbV2 buf=1.40 | LightGBM buf=1.40 | — |
| Best recency | 120d window, 12d decay | Full history, 6d decay | — |

---

## Reproducibility

All models use `random_state=42` (CatBoost: `random_seed=42`). Results are fully deterministic.

---

## Files

| File | Description |
|------|-------------|
| `notebooks/run_production_training.py` | Production training script (shelf-aware) |
| `notebooks/results/experiment_results.json` | Shelf-aware experiment results |
| `notebooks/results_baseline_no_shelf/experiment_results.json` | Baseline results (preserved) |
| `data/raw/production_shelf_life_final.csv` | 12,348 items with shelf life classifications |
| `data/raw/production_training_items.csv` | Training items with ordering cadence |
| `classify_production_items.py` | Rule-based classification script |
| `notebooks/results/phase1_recency.png` | Phase 1 recency comparison chart |
| `notebooks/results/phase2_models.png` | Phase 2 model ranking chart |
| `notebooks/results/phase3_buffer.png` | Phase 3 buffer sweep chart |
| `notebooks/results/per_store_analysis.png` | Per-store cost distribution |

---

*Report generated: April 6, 2026*
