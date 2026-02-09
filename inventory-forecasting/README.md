# Fresh Flow Markets - Demand Forecasting System

ML-powered demand forecasting and inventory optimization for Fresh Flow Markets, a chain of 101 restaurant locations in Copenhagen, Denmark. Built for the DIH Hackathon.

## Key Results

| Metric | Value |
|--------|-------|
| **Cost Reduction** | **27.8%** vs worst baseline (24.6M DKK/year est.) |
| **Forecast Accuracy** | 67.7% (WMAPE-based) |
| **Models Evaluated** | 32 configurations (baselines, ML, hybrids) |
| **Winning Model** | Hybrid: 30% XGBoost + 70% MA7 (rounded) |
| **Features Engineered** | 53 across 5 categories |
| **Stores Covered** | 101 active locations |
| **Data Span** | Feb 2021 - Feb 2024 (3 years, 400K+ orders) |
| **Test Period** | 93 days (Dec 2023 - Mar 2024) |

## Problem

Fresh Flow Markets suffers from inventory mismanagement:
- **Overstocking** leads to food waste (perishable items expire)
- **Understocking** leads to stockouts (lost revenue, unhappy customers)
- **No automated forecasting** - prep decisions rely on manual guesswork

We built a system that predicts daily demand per item per store, provides recommended prep quantities, and quantifies the business impact in DKK.

## Solution: Hybrid Forecasting Model

After evaluating 32 model configurations on business-impact metrics (DKK-denominated waste + stockout costs), we selected a **hybrid blend of XGBoost (30%) + 7-day Moving Average (70%)** with integer rounding:

- **XGBoost** captures promotions, weather, holidays, and day-of-week effects using 53 features
- **MA7** anchors predictions to recent actual demand, preventing overstocking
- **Rounding** matches discrete food prep (you prep whole portions, not fractions)

```
Forecast = round(0.3 x XGBoost_prediction + 0.7 x MA7_prediction)
```

### Why not pure XGBoost?
Pure XGBoost achieves the lowest statistical error (MAE=3.31) but **overstocks aggressively** on low-volume items, leading to high waste cost. The hybrid blend reduces total business cost by 6.2M DKK/year vs pure XGBoost.

### Business-Impact Evaluation
We evaluate using DKK costs, not just abstract metrics:
- **Waste cost** = (overstock x item price x 30% waste fraction)
- **Stockout cost** = (understock x item price), weighted 1.5x (customer LTV loss)
- **Total cost** = waste + 1.5x stockout

## Features

- **53-Feature Engineering Pipeline**: Calendar, lag/rolling, Copenhagen weather (Open-Meteo), Danish holidays, promotions
- **Inventory Optimizer**: Safety stock at 95% service level, daily prep quantity recommendations
- **Waste Risk Analysis**: Items classified by demand variability (high/medium/low risk)
- **Promotion Intelligence**: Slow-mover identification, campaign effectiveness analysis, discount recommendations
- **Interactive Dashboard**: 4-page Streamlit app with KPIs, forecast charts, inventory alerts, promotion insights

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Data Processing | pandas, numpy |
| ML Models | XGBoost, scikit-learn |
| Weather Data | Open-Meteo API (free, Copenhagen) |
| Holidays | `holidays` library (Denmark) |
| Dashboard | Streamlit + Plotly |
| Configuration | YAML |
| Testing | pytest (21 tests) |

## Project Structure

```
inventory-forecasting/
├── config/              # Settings and logging configuration
├── src/
│   ├── data/            # CSV loading, cleaning, schema validation
│   ├── features/        # Time, lag, weather, holiday, promotion features
│   ├── models/          # Baseline, XGBoost, hybrid ensemble, evaluation
│   ├── inventory/       # Safety stock, waste analysis, promotion engine
│   └── dashboard/       # Streamlit app with 4 pages
├── notebooks/           # EDA, feature engineering, model training
├── tests/               # Unit tests for all modules
└── docs/                # Data dictionary, architecture, results
```

## Installation

```bash
cd inventory-forecasting
pip install -r requirements.txt
```

## Usage

### Run the Dashboard

```bash
cd inventory-forecasting
streamlit run src/dashboard/app.py
```

The dashboard loads data, trains the hybrid model, and displays 4 pages:
1. **Overview**: KPIs, demand trends, store comparison
2. **Forecasts**: Interactive charts with confidence intervals
3. **Inventory**: Prep quantity recommendations with color-coded alerts
4. **Promotions**: Campaign impact analysis and discount suggestions

### Run the Full Pipeline

```python
from src.data.loader import load_key_tables, load_config
from src.data.cleaner import clean_all
from src.features.builder import build_features
from src.models.trainer import train_all_models

config = load_config()
tables = load_key_tables(config)
tables = clean_all(tables)
features = build_features(tables, top_n_items=20)
results = train_all_models(features)
```

### Run Tests

```bash
cd inventory-forecasting
pytest tests/ -v
```

## Data

19 CSV tables from the Inventory Management database. Key tables:

| Table | Rows | Description |
|-------|------|-------------|
| fct_orders | ~400K (325K cleaned) | Order-level data |
| fct_order_items | ~2M | Item-level demand signal |
| dim_items | ~89K | Product catalog with prices |
| dim_places | 323 (101 active) | Store locations and hours |
| fct_campaigns | 641 | Promotional campaigns |

See [docs/data_dictionary.md](docs/data_dictionary.md) for full documentation.

## Model Comparison (Top 5 of 32)

| Rank | Model | Total Cost (M DKK) | Savings |
|------|-------|-------------------|---------|
| 1 | MA7 + 20% buffer | 15.20 | 29.3% |
| 2 | **30% XGB + 70% MA7** | **15.51** | **27.8%** |
| 3 | 40% XGB + 60% MA7 | 15.52 | 27.8% |
| 4 | 50% XGB + 50% MA7 | 15.57 | 27.6% |
| 5 | 30% XGB + 70% MA7 (floored) | 15.58 | 27.5% |

See [docs/results.md](docs/results.md) for complete evaluation of all 32 models.

## Documentation

- [Results & Business Impact](docs/results.md) - Comprehensive model comparison and business metrics
- [Architecture](docs/architecture.md) - System design and data flow
- [Data Dictionary](docs/data_dictionary.md) - All 19 tables documented

## Team

| Member | Responsibility |
|--------|---------------|
| Member 1 | Data Pipeline + EDA |
| Member 2 | Feature Engineering + External Data |
| Member 3 | ML Models + Evaluation |
| Member 4 | Dashboard + Inventory + Documentation |
