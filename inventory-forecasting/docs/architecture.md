# System Architecture

## Overview

The Fresh Flow Markets Demand Forecasting System is a modular ML pipeline that predicts daily demand per item per store and provides actionable inventory management recommendations.

## Data Flow

```
Raw CSV Data (19 tables)
    |
    v
[Data Pipeline] -- loader.py --> cleaner.py --> schema.py
    |
    v
Cleaned DataFrames (fct_orders, fct_order_items, dim_items, dim_places, fct_campaigns)
    |
    v
[Feature Engineering] -- builder.py orchestrates:
    |-- time_features.py      (calendar features)
    |-- lag_features.py        (lag/rolling/expanding)
    |-- external_features.py   (weather API, Danish holidays)
    |-- promotion_features.py  (campaign data)
    |
    v
Feature Matrix (date x store x item = ~1.2M rows x 53 features)
    |
    v
[Model Training] -- trainer.py
    |-- baseline.py       (naive, moving average, buffered MA)
    |-- xgboost_model.py  (gradient boosting with 53 features)
    |-- ensemble.py       (hybrid: 30% XGB + 70% MA7 = winning model)
    |-- evaluator.py      (MAE, WMAPE, DKK waste/stockout costs)
    |
    v
Predictions + Evaluation Metrics
    |
    v
[Inventory Optimization] -- optimizer.py
    |-- Safety stock calculation
    |-- Prep quantity recommendations
    |-- waste_analyzer.py (waste risk classification)
    |-- promotion_engine.py (discount suggestions)
    |
    v
[Streamlit Dashboard] -- app.py
    |-- Overview: KPIs, trends, store comparison
    |-- Forecasts: interactive charts, CI, download
    |-- Inventory: prep recommendations, alerts
    |-- Promotions: slow-mover identification, campaign impact
```

## Key Design Decisions

1. **Daily granularity** as base level, aggregated to weekly/monthly in the dashboard.

2. **Per (store, item) modeling** - separate time series for each store-item pair, using top 20 items per store to manage scale while covering ~80% of revenue.

3. **Hybrid model (30% XGBoost + 70% MA7)** selected from 32-model evaluation on business-impact metrics. XGBoost captures external factors (weather, holidays, promotions); MA7 anchors to recent trends and prevents overstocking. This combination reduces total business cost by 27.8% vs the worst baseline.

4. **Business-impact evaluation** using DKK-denominated waste cost + stockout cost (weighted 1.5x). This replaced abstract metrics (MAE/MAPE) as the primary model selection criterion.

5. **Safety stock formula** uses z-score approach: `safety_stock = z * sigma * sqrt(lead_time)` at 95% service level (z=1.65).

6. **No actual inventory data** - `fct_inventory_reports` is empty, so all demand signal comes from sales data (fct_orders + fct_order_items). We recommend prep quantities based on forecasted demand + safety stock.

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| Data Processing | pandas, numpy |
| ML Models | XGBoost, Prophet, scikit-learn |
| Weather Data | Open-Meteo API (free) |
| Holidays | `holidays` Python library |
| Dashboard | Streamlit + Plotly |
| Configuration | YAML |
| Testing | pytest |

## Model Evaluation Strategy

- **Time-series split**: Train on first 30 months, validate on next 3, test on final 3 (93 days).
- **Walk-forward validation**: Expanding window cross-validation respecting temporal order.
- **Primary metric**: Total Business Cost (DKK) = Waste Cost + 1.5x Stockout Cost.
- **Standard metrics**: MAE, WMAPE, Forecast Accuracy (1 - WMAPE).
- **32 models evaluated**: baselines, ML, hybrids, buffered, and post-processed variants.
- Stockout cost weighted 1.5x (lost customer lifetime value > food waste cost).

## Results Summary

- **Winning model**: Hybrid (30% XGBoost + 70% MA7 with rounding)
- **Total business cost**: 15.51M DKK on 93-day test (27.8% reduction)
- **Estimated annual savings**: 24.6M DKK across 101 stores
- See [results.md](results.md) for full analysis.
