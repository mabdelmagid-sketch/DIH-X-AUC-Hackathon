# Loving Loyalty AI Intelligence Suite — Pillar 1: Sales Forecasting

Demand forecasting microservice for Danish restaurants, built as part of the
DIH-X-AUC Hackathon.  Delivers daily per-item sales predictions with
newsvendor-calibrated safety buffers, confidence scores, and forecast drivers.

---

## Architecture

The forecasting model is an **AdaptiveBlendModel**: a weighted combination of
a global Random Forest and per-store Extra Trees regressors.

| Component | Detail |
|-----------|--------|
| Global model | `RandomForestRegressor(n_estimators=300, min_samples_leaf=2)` |
| Per-store model | `ExtraTreesRegressor(n_estimators=800)` |
| Blend ratio | 75 % global / 25 % per-store, adaptive: weight shifts toward local once a store has >= 100 training samples |
| Training weights | Exponential decay, half-life = 12 days (recent data weighted higher) |
| Feature interactions | lag7d × day_of_week, rolling_mean × is_weekend, lag7d / expanding_mean |
| Safety buffer | Newsvendor optimal buffer per item (see below) |

**Best validated result**: 5,225,357 DKK total business cost on the 14-day
hold-out test set — a 25 % reduction vs the MA-7 baseline.

### Newsvendor Safety Buffer

For each menu item:

```
critical_ratio = 1.5 / (1.5 + 0.3)  = 0.833
buffer = 1 + z_{0.833} × σ / μ
       = 1 + 0.967 × (std_demand / mean_demand)
clamped to [1.0, 2.0]
fallback 1.27 for items with < 30 days of history
```

---

## Output Variants

Three model variants are produced from the same trained model:

| Variant | Buffer scale | Use case |
|---------|-------------|----------|
| `balanced` | × 1.00 | Default — newsvendor buffer fully applied |
| `waste_optimized` | × 0.90 | Accepts more stockout risk; reduces food waste |
| `stockout_optimized` | × 1.06 | Reduces stockout frequency; accepts slightly more waste |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ai/forecast/items` | Per-item daily forecasts (SRS Pillar 1, primary endpoint) |
| POST | `/api/ai/forecast` | Legacy per-item forecast (older schema) |
| POST | `/api/forecast` | Forecast using the pre-trained ensemble models |
| POST | `/api/train` | Retrain the model on the demo dataset |
| GET | `/api/health` | Service health check |
| GET | `/api/model/features` | Top feature importances from trained model |
| GET | `/api/forecast/ingredients` | Ingredient-level demand via BOM explosion |
| POST | `/api/forecast/cold-start` | Demand estimate for new products with no history |

### POST /api/ai/forecast/items

Request:

```json
{
  "placeId": 123,
  "startDate": "2024-02-01",
  "endDate": "2024-02-07",
  "granularity": "daily",
  "variant": "balanced",
  "topN": 20
}
```

Response:

```json
{
  "placeId": 123,
  "startDate": "2024-02-01",
  "endDate": "2024-02-07",
  "granularity": "daily",
  "variant": "balanced",
  "generatedAt": "2024-01-31T12:00:00Z",
  "itemForecasts": [
    {
      "itemId": 42,
      "itemTitle": "Smørrebrød",
      "predictions": [
        {
          "date": "2024-02-01",
          "predictedUnits": 14,
          "lowerBound": 10,
          "upperBound": 18,
          "confidence": 0.82,
          "forecastDrivers": [
            "same day last week: 12 units",
            "7-day rolling average: 11.4 units/day avg",
            "Demand trending up week-over-week"
          ]
        }
      ]
    }
  ]
}
```

**Confidence scores** follow SRS Table 25:

| History depth | Confidence range |
|---------------|-----------------|
| 90+ days | 0.75 – 0.95 |
| 30–89 days | 0.50 – 0.74 |
| < 30 days | 0.20 – 0.49 |
| 0 orders | 0.10 – 0.25 |

---

## Project Structure

```
services/forecasting/
├── src/
│   ├── main.py                   # FastAPI app, router registration
│   ├── config.py                 # Settings (env vars, paths)
│   ├── api/
│   │   ├── forecast_items_routes.py  # POST /ai/forecast/items (Pillar 1)
│   │   ├── forecast_routes.py        # POST /ai/forecast (legacy)
│   │   ├── model_routes.py           # /train, /forecast, /model/features
│   │   ├── data_routes.py            # /sales, /inventory
│   │   ├── chat_routes.py            # LLM chat + prep recommendation
│   │   ├── schemas.py                # Shared Pydantic schemas
│   │   └── dependencies.py           # FastAPI dependency injectors
│   ├── forecast/                 # Production pipeline (new in Pillar 1)
│   │   ├── __init__.py
│   │   ├── data_loader.py        # Load MySQL/CSV → daily demand grid
│   │   ├── feature_engineer.py   # All features, expanding_mean leakage-safe
│   │   ├── trainer.py            # AdaptiveBlendModel training + artifact save
│   │   └── predictor.py          # Load artifacts, generate forecasts
│   ├── features/
│   │   ├── lag_features.py       # Lag + rolling features (patched per Report B)
│   │   ├── time_features.py      # Calendar/seasonality features
│   │   ├── external_features.py  # Weather + holiday features
│   │   └── builder.py            # Feature pipeline orchestrator
│   ├── models/
│   │   ├── ensemble.py           # HybridForecaster (XGB + MA7)
│   │   ├── model_service.py      # Load pkl models + predict_multi_day
│   │   └── trainer.py            # Legacy training pipeline
│   ├── data/
│   │   └── loader.py             # DuckDB-based CSV/Supabase loader
│   └── llm/
│       └── ...                   # LLM client, RAG, tools
├── autoresearch/
│   ├── evaluate.py               # Evaluation harness (expanding_mean fix applied)
│   ├── experiment.py             # Current best model definition
│   └── results.tsv               # All experiment results
├── data/
│   ├── demo/                     # CSV demo dataset
│   └── models/                   # Trained model artifacts (.pkl)
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## How to Run Locally

### Prerequisites

- Python 3.11+
- Install dependencies: `pip install -r requirements.txt`

### Start the API

```bash
# From services/forecasting/
python run.py
# or
uvicorn src.main:app --reload --port 8002
```

The API will be available at `http://localhost:8002`.
Interactive docs: `http://localhost:8002/docs`

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `USE_MYSQL` | Set to `1` to use MySQL instead of CSV demo data | `0` (CSV) |
| `DB_DSN` | Full SQLAlchemy DSN for MySQL | — |
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | MySQL connection parts | — |
| `OPENROUTER_API_KEY` | API key for LLM chat features | — |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Real POS data via Supabase | — |

Copy `.env.example` to `.env` and fill in values before starting.

---

## How to Retrain

The autoresearch agent runs experiments and stores results in
`autoresearch/results.tsv`.  The current best model is defined in
`autoresearch/experiment.py`.

### Retrain via the API

```bash
curl -X POST http://localhost:8002/api/train
```

### Retrain via the production pipeline (CLI)

```python
from src.forecast.data_loader import DataLoader
from src.forecast.trainer import AdaptiveBlendTrainer

loader = DataLoader(source="csv")   # or source="mysql"
daily_df = loader.load_daily_demand(top_n_items=30)

trainer = AdaptiveBlendTrainer(decay_half_life=12.0)
artifacts = trainer.fit(daily_df, save=True)
print(artifacts)
# Saves balanced_model.pkl, waste_optimized_model.pkl,
# stockout_optimized_model.pkl to data/models/
```

### After retraining

If you fix a data leakage issue (e.g., the expanding_mean fix from Report B),
delete the autoresearch cache to force full regeneration:

```bash
rm autoresearch/.cache/prepared_data.pkl
```

---

## Data Leakage Fix (Report B, Section 4)

An independent audit (Report B) identified that `expanding_mean` was
computed across the entire dataset before the train/test split, allowing
test rows to see future demand in their feature values.

**Fix applied in two places:**

1. `src/features/lag_features.py` — added `shift(1)` before `expanding()`,
   plus documentation that callers must pass only the training partition.

2. `autoresearch/evaluate.py` — changed from:
   ```python
   # LEAKY (old):
   df["expanding_mean"] = df.groupby(grp)["quantity_sold"].expanding().mean()...
   ```
   to:
   ```python
   # FIXED:
   df["expanding_mean"] = df.groupby(grp)["quantity_sold"].transform(
       lambda x: x.shift(1).expanding(min_periods=1).mean()
   )
   ```

3. `src/forecast/feature_engineer.py` — `FeatureEngineer.fit_transform()` computes
   expanding_mean only on training rows, then `transform()` freezes the value at
   the training cutoff for all inference rows.
