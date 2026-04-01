---
title: "FlowPOS Demand Forecasting: Model Selection & Benchmarking"
author: "Report A"
date: "March 2026"
---

# 1. Introduction

This report presents the results of a large-scale model exploration for demand forecasting in FlowPOS, a Danish restaurant and food-service POS platform. The objective was to identify the best forecasting model by evaluating multiple model families against a business-impact cost metric.

A companion report (Report B) builds on these findings with investigations into data recency, seasonality, and per-store modeling strategies. Where relevant, findings from Report B are referenced.

# 2. Dataset Overview

## 2.1 Source Tables

The dataset consists of real POS transaction data from Danish restaurants, pubs, kiosks, and food shops.

| Table | Rows | Description |
|-------|------|-------------|
| fct_orders | 294,569 | Individual orders with timestamp, store, payment, type |
| fct_order_items | 481,624 | Line items: item, quantity, price, cost |
| dim_items | 88,921 | Menu items with titles, prices, categories |
| dim_places | 2,091 | Store metadata and configuration |
| dim_campaigns | 642 | Promotional campaigns |
| dim_users | 22,956 | Customer records |

## 2.2 Key Characteristics

The dataset spans **59 days** (December 18, 2023 to February 16, 2024) across **308 active stores** with **15,266 unique items**. Total revenue is 39.1M DKK with an average order value of 133 DKK. The business is overwhelmingly takeaway (96%) with card payments (93%) placed via app.

Top-selling items are classic Danish kiosk/pub fare: Sodavand (soda), various beers (Øl, Alm Øl), food boxes (Lille/Mellem/Stor box), and Ristet Hotdog.

## 2.3 The Sparsity Challenge

The single most important characteristic for model selection is the extreme sparsity:

| Metric | Value |
|--------|-------|
| Store-item pairs | 15,266 |
| Days in dataset | 61 |
| Possible (store, item, day) entries | 931,226 |
| Entries with non-zero demand | 144,761 |
| **Sparsity** | **84.5%** |

On any given day, 84.5% of store-item combinations have zero sales. This zero-inflation is the dominant modeling challenge and fundamentally determines which model families succeed or fail.

## 2.4 Demand Patterns

Weekly seasonality is strong: Friday is the peak day at 1.35x average, Sunday is the trough at 0.74x. The dataset also contains a massive demand trend --- orders grew roughly 10x from early December (634/day in week 51) to early February (7,504/day in week 5). This trend issue is explored in depth in Report B.

# 3. Evaluation Methodology

## 3.1 Train/Test Split

A temporal split was used: all data up to February 2 for training (323,564 rows after removing early lag-incomplete rows), and the final 14 days (February 3--16) as the test set (98,476 rows). This avoids future data leakage.

## 3.2 Business Cost Metric

Standard forecasting metrics (MAE, RMSE, WMAPE) were computed but the primary ranking metric is **Total Business Cost in DKK**:

$$\text{Total Cost} = \text{Waste Cost} + 1.5 \times \text{Stockout Cost}$$

Where:

- **Waste Cost** = overstock units $\times$ item price $\times$ 0.30 (30% of ingredient cost lost when food is wasted)
- **Stockout Cost** = understock units $\times$ item price (full lost revenue)
- The 1.5x multiplier on stockouts reflects that missed sales damage revenue and customer loyalty more than food waste.

This metric directly measures the business impact of forecasting errors.

## 3.3 Feature Engineering

38 features were engineered across six categories:

- **Time** (15 features): day of week, month, quarter, cyclical sin/cos encodings, weekend/Friday/Monday flags, season
- **Lag** (6 features): 1/7/14/28-day demand lags, same-weekday last week, 4-week same-weekday average
- **Rolling** (7 features): 7/14/30-day rolling means, 7/14-day rolling standard deviations, expanding mean
- **External** (7 features): weather stubs, holiday flags, promotion flags, store open flag
- **Categorical** (2 features): label-encoded place_id and item_id
- **Interaction** (1 feature): store-weekday interaction term

## 3.4 Parallel Team Execution

To maximize coverage, **10 specialized agents** were deployed in parallel, each exploring a different model family with 3--4 hyperparameter configurations. This produced 37 distinct model variants in a single session.

# 4. Results

## 4.1 Full Leaderboard

The complete ranking of all 37 model variants by Total Business Cost:

| Rank | Model | MAE | WMAPE | Total Cost (DKK) | Train Time |
|------|-------|-----|-------|-------------------|------------|
| 1 | **RF Default** | 1.781 | 84.9% | **6,035,987** | 18s |
| 2 | ET Default | 1.901 | 90.7% | 6,210,050 | 13s |
| 3 | RF Tuned | 1.823 | 86.9% | 6,212,328 | 29s |
| 4 | ET Tuned | 1.796 | 85.7% | 6,298,901 | 50s |
| 5 | RF Large | 1.729 | 82.4% | 6,387,003 | 154s |
| 6 | CatBoost Shallow | 1.773 | 84.6% | 6,421,793 | 176s |
| 7 | ET Large | 1.850 | 88.2% | 6,423,460 | 115s |
| 8 | CatBoost Deep | 1.748 | 83.3% | 6,453,977 | 328s |
| 9 | CatBoost Default | 1.795 | 85.6% | 6,454,638 | 120s |
| 10 | Stacking XGB Meta | 1.688 | 80.5% | 6,594,097 | 794s |
| 11 | Weighted ETS | 1.632 | 77.8% | 6,654,421 | 0s |
| 12 | Stacking Ridge Meta | 1.896 | 90.4% | 6,786,156 | 684s |
| 13 | SES (alpha=0.3) | 1.677 | 80.0% | 6,831,516 | 0s |
| 14 | Damped Trend ETS | 1.684 | 80.3% | 6,856,446 | 0s |
| 15 | LightGBM Default | 1.439 | 68.6% | 6,873,856 | 38s |
| 16 | MA7 baseline | 1.716 | 81.8% | 6,967,146 | 0s |
| 17 | LightGBM Sparse | 1.413 | 67.4% | 6,985,702 | 41s |
| 18 | LightGBM Tuned | 1.457 | 69.5% | 7,033,513 | 89s |
| 19 | Croston Hybrid | 1.929 | 92.0% | 7,060,510 | 0s |
| 20 | NaiveLastWeek | 1.797 | 85.7% | 7,308,750 | 0s |
| 21 | SGD Huber | 1.504 | 71.7% | 7,489,994 | 1s |
| 22 | Adaptive ETS | 1.863 | 88.8% | 7,528,529 | 1s |
| 23 | ElasticNet | 2.182 | 104.1% | 8,186,728 | 91s |
| 24 | SGD Eps-Insensitive | 1.583 | 75.5% | 8,412,233 | 2s |
| 25 | LinearSVR Regularized | 1.689 | 80.5% | 9,367,123 | 197s |
| 26 | LinearSVR Default | 1.692 | 80.7% | 9,388,702 | 725s |
| 27--31 | Croston variants | 2.2--2.3 | 106--109% | 11.2--11.5M | 0s |
| 32--36 | Linear models | 3.0--3.7 | 143--178% | 11.5--12.4M | 1--637s |
| 37 | Zero baseline | 2.097 | 100.0% | 13,664,654 | 0s |

## 4.2 Model Family Summary

| Family | Best Variant | Cost (DKK) | vs MA7 | Verdict |
|--------|-------------|------------|--------|---------|
| Random Forest | RF Default | 6,036K | -13.4% | **Winner** |
| Extra Trees | ET Default | 6,210K | -10.9% | Strong runner-up |
| CatBoost | Shallow | 6,422K | -7.8% | Solid |
| Exponential Smoothing | Weighted ETS | 6,654K | -4.5% | Best zero-training option |
| Stacking | XGB Meta | 6,594K | -5.4% | Not worth the complexity |
| LightGBM | Default | 6,874K | -1.3% | Best raw accuracy |
| Croston's | Hybrid | 7,061K | +1.3% | Disappointing |
| SVR | SGD Huber | 7,490K | +7.5% | Not competitive |
| ElasticNet | Default | 8,187K | +17.5% | Broken on sparse data |
| Bayesian Ridge | ARD | 12,354K | +77.3% | Completely broken |

# 5. Analysis: Why Accuracy Does Not Equal Business Value

The most important finding from this exploration is that **forecast accuracy and business value are inversely correlated** on this dataset.

| Model | WMAPE | Waste (DKK) | Stockout (DKK) | Over-predict % | Total Cost |
|-------|-------|-------------|----------------|----------------|------------|
| LightGBM Sparse | **67.4%** | 695K | 4,194K | 48.7% | 6,986K |
| RF Default | 84.9% | 1,616K | 2,947K | 54.3% | **6,036K** |

LightGBM is nearly twice as accurate by WMAPE yet costs 15% more. The mechanism:

**Random Forest's bagging creates a natural safety buffer.** Each of 100 trees is trained on a bootstrap sample. With 84.5% zeros, different trees see different zero/non-zero ratios and produce varied predictions. Their average sits slightly above the true mean --- a built-in tendency to over-predict.

**Gradient boosting is too precise.** LightGBM and XGBoost iteratively minimize prediction error, aggressively learning that 84.5% of predictions should be zero. They achieve excellent accuracy but produce expensive stockouts when demand does materialize.

Since the business metric penalizes stockouts at 1.5x, RF's slight over-prediction bias saves 1.2M DKK in stockouts while only adding 920K DKK in waste --- a net gain of nearly 1M DKK.

# 6. What Didn't Work and Why

| Approach | Root Cause of Failure |
|----------|----------------------|
| **Linear models** (Ridge, Lasso, ElasticNet, Bayesian Ridge) | Cannot learn the zero-inflation pattern. They predict moderate positive values everywhere instead of mostly zeros with occasional spikes. All scored 0% forecast accuracy and 12M+ DKK cost. |
| **Croston's method** | Designed for intermittent demand, but the sparsity here is structural (most items never sell at a given store) not stochastic (demand arriving at random intervals). In tabular form with pre-computed features, Croston loses its per-series advantage. |
| **Stacking ensemble** | The meta-learner averages base predictions, diluting RF's beneficial conservative bias. Costs 794s to train for worse results than a 18s RF. |
| **SVR / LinearSVR** | Linear kernel cannot capture the zero-inflation. RBF kernel doesn't scale to 323K rows. SGD Huber was the best SVR variant but still 7.5% worse than MA7. |

# 7. Conclusion

**Random Forest with default hyperparameters** (100 trees, unlimited depth) is the clear winner for this demand forecasting problem, achieving a 13.4% reduction in business cost versus the MA7 baseline.

The model's advantage stems not from sophistication but from a happy alignment between RF's bagging mechanism and the business objective: on highly sparse data, bagging naturally produces slightly conservative (over-predicting) forecasts, which is exactly what a stockout-penalizing cost function rewards.

Report B extends these findings with data recency strategies and a global/per-store blending approach that pushes total improvement to 19%.
