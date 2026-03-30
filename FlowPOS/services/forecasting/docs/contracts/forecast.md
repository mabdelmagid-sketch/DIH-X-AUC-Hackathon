# Forecast API Contract

**Service:** FlowPOS AI Intelligence Suite -- Pillar 1: Sales Forecasting
**Base path:** `/ai`
**Protocol:** HTTPS, JSON
**Auth:** Bearer token via `Authorization` header (passed through API gateway)

---

## POST /ai/forecast

Generate multi-day revenue and demand forecasts for a given place (restaurant location).

### Request

```
POST /ai/forecast
Content-Type: application/json
Authorization: Bearer <token>
```

**Body** (SRS Table 4):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `placeId` | `string` | Yes | Loving Loyalty place identifier |
| `startDate` | `string` | Yes | First day of forecast window (`YYYY-MM-DD`) |
| `endDate` | `string` | Yes | Last day of forecast window (`YYYY-MM-DD`). Max span: 30 days. |
| `granularity` | `string` enum | No | `"day"` (default), `"week"`, `"month"`, `"hour"` |
| `variant` | `string` enum | No | `"balanced"` (default), `"waste_optimized"`, `"stockout_optimized"` |

**Example request:**

```json
{
  "placeId": "552477",
  "startDate": "2026-04-01",
  "endDate": "2026-04-07",
  "granularity": "day",
  "variant": "balanced"
}
```

### Response `200 OK`

**Body** (SRS Table 5):

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| `placeId` | `string` | | Echo of request `placeId` |
| `forecastedAt` | `string` | ISO 8601 | Server timestamp when forecast was generated |
| `granularity` | `string` | | Echo of request `granularity` |
| `variant` | `string` | | Echo of request `variant` |
| `predictions` | `array<Prediction>` | | Per-date forecast entries |
| `drivers` | `array<Driver>` | Min 3 items, never empty | Top demand drivers explaining this forecast |
| `scenarios` | `object` | | Best / expected / worst case scenarios |
| `baselineCostDkk` | `float` | | Estimated total business cost (DKK) under MA-7 baseline |
| `forecastCostDkk` | `float` | | Estimated total business cost (DKK) under this forecast |
| `costReductionPct` | `float` | | Percentage reduction vs baseline |

**Prediction object:**

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| `date` | `string` | `YYYY-MM-DD` | Forecast date |
| `predicted` | `float` | DKK | Point forecast (revenue in DKK) |
| `lower` | `float` | Always < predicted | Lower bound of prediction interval |
| `upper` | `float` | Always > predicted | Upper bound of prediction interval |
| `confidence` | `float` | 0.0 to 1.0 | Confidence score based on data history length |

**Driver object:**

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| `factor` | `string` | Plain language | Name of the demand driver (e.g. "Strong Friday demand pattern") |
| `impact` | `string` | `"positive"` or `"negative"` | Direction of impact |
| `weight` | `float` | 0.0 to 1.0 | Relative importance |

**Scenarios object:**

| Field | Type | Description |
|-------|------|-------------|
| `best` | `object` | `{ "total": float, "confidence": float }` -- optimistic scenario |
| `expected` | `object` | `{ "total": float, "confidence": float }` -- base scenario |
| `worst` | `object` | `{ "total": float, "confidence": float }` -- pessimistic scenario |

**Example response:**

```json
{
  "placeId": "552477",
  "forecastedAt": "2026-03-30T10:15:00.000Z",
  "granularity": "day",
  "variant": "balanced",
  "predictions": [
    {
      "date": "2026-04-01",
      "predicted": 12450.50,
      "lower": 9960.40,
      "upper": 14940.60,
      "confidence": 0.82
    },
    {
      "date": "2026-04-02",
      "predicted": 11200.00,
      "lower": 8960.00,
      "upper": 13440.00,
      "confidence": 0.79
    },
    {
      "date": "2026-04-03",
      "predicted": 13100.75,
      "lower": 10480.60,
      "upper": 15720.90,
      "confidence": 0.81
    },
    {
      "date": "2026-04-04",
      "predicted": 18750.25,
      "lower": 15000.20,
      "upper": 22500.30,
      "confidence": 0.85
    },
    {
      "date": "2026-04-05",
      "predicted": 16200.00,
      "lower": 12960.00,
      "upper": 19440.00,
      "confidence": 0.83
    },
    {
      "date": "2026-04-06",
      "predicted": 8900.50,
      "lower": 7120.40,
      "upper": 10680.60,
      "confidence": 0.78
    },
    {
      "date": "2026-04-07",
      "predicted": 11800.00,
      "lower": 9440.00,
      "upper": 14160.00,
      "confidence": 0.80
    }
  ],
  "drivers": [
    { "factor": "Strong Friday demand pattern", "impact": "positive", "weight": 0.35 },
    { "factor": "7-day demand trend increasing", "impact": "positive", "weight": 0.28 },
    { "factor": "Weekend seasonal uplift", "impact": "positive", "weight": 0.19 },
    { "factor": "Recent rolling average above historical mean", "impact": "positive", "weight": 0.11 },
    { "factor": "Sunday typically low traffic", "impact": "negative", "weight": 0.07 }
  ],
  "scenarios": {
    "best": { "total": 110401.80, "confidence": 0.70 },
    "expected": { "total": 92402.00, "confidence": 0.82 },
    "worst": { "total": 74001.60, "confidence": 0.70 }
  },
  "baselineCostDkk": 6967146.0,
  "forecastCostDkk": 5133764.0,
  "costReductionPct": 26.3
}
```

### Error responses

| Status | Code | Description |
|--------|------|-------------|
| `400` | `INVALID_DATE_RANGE` | `endDate` before `startDate`, or span > 30 days |
| `400` | `INVALID_GRANULARITY` | Unknown granularity value |
| `400` | `INVALID_VARIANT` | Unknown variant value |
| `404` | `PLACE_NOT_FOUND` | No sales history found for `placeId` |
| `422` | `VALIDATION_ERROR` | Missing required fields |
| `500` | `FORECAST_FAILED` | Model inference error |

---

## POST /ai/forecast/items

Generate demand forecasts broken down by individual menu item.

### Request

```
POST /ai/forecast/items
Content-Type: application/json
Authorization: Bearer <token>
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `placeId` | `string` | Yes | Loving Loyalty place identifier |
| `startDate` | `string` | Yes | First day of forecast window (`YYYY-MM-DD`) |
| `endDate` | `string` | Yes | Last day of forecast window (`YYYY-MM-DD`) |
| `granularity` | `string` enum | No | `"day"` (default), `"week"`, `"month"`, `"hour"` |

**Example request:**

```json
{
  "placeId": "552477",
  "startDate": "2026-04-01",
  "endDate": "2026-04-07",
  "granularity": "day"
}
```

### Response `200 OK`

| Field | Type | Description |
|-------|------|-------------|
| `placeId` | `string` | Echo of request `placeId` |
| `itemForecasts` | `array<ItemForecast>` | Per-item forecast with daily breakdown |

**ItemForecast object:**

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| `itemTitle` | `string` | | Human-readable item name |
| `predictions` | `array<ItemPrediction>` | | Per-day predictions for this item |

**ItemPrediction object:**

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| `date` | `string` | `YYYY-MM-DD` | Forecast date |
| `predictedUnits` | `integer` | >= 0 | Forecasted demand in whole units |
| `confidence` | `float` | 0.0 to 1.0 | Confidence score |

**Example response:**

```json
{
  "placeId": "552477",
  "itemForecasts": [
    {
      "itemTitle": "Alm \u00d8l",
      "predictions": [
        { "date": "2026-04-01", "predictedUnits": 22, "confidence": 0.85 },
        { "date": "2026-04-02", "predictedUnits": 19, "confidence": 0.82 },
        { "date": "2026-04-03", "predictedUnits": 24, "confidence": 0.84 },
        { "date": "2026-04-04", "predictedUnits": 35, "confidence": 0.88 },
        { "date": "2026-04-05", "predictedUnits": 30, "confidence": 0.86 },
        { "date": "2026-04-06", "predictedUnits": 15, "confidence": 0.79 },
        { "date": "2026-04-07", "predictedUnits": 20, "confidence": 0.81 }
      ]
    },
    {
      "itemTitle": "Sodavand",
      "predictions": [
        { "date": "2026-04-01", "predictedUnits": 18, "confidence": 0.83 },
        { "date": "2026-04-02", "predictedUnits": 15, "confidence": 0.80 },
        { "date": "2026-04-03", "predictedUnits": 20, "confidence": 0.82 },
        { "date": "2026-04-04", "predictedUnits": 28, "confidence": 0.86 },
        { "date": "2026-04-05", "predictedUnits": 25, "confidence": 0.84 },
        { "date": "2026-04-06", "predictedUnits": 12, "confidence": 0.77 },
        { "date": "2026-04-07", "predictedUnits": 16, "confidence": 0.79 }
      ]
    },
    {
      "itemTitle": "Ristet Hotdog",
      "predictions": [
        { "date": "2026-04-01", "predictedUnits": 8, "confidence": 0.72 },
        { "date": "2026-04-02", "predictedUnits": 6, "confidence": 0.68 },
        { "date": "2026-04-03", "predictedUnits": 9, "confidence": 0.71 },
        { "date": "2026-04-04", "predictedUnits": 14, "confidence": 0.76 },
        { "date": "2026-04-05", "predictedUnits": 12, "confidence": 0.74 },
        { "date": "2026-04-06", "predictedUnits": 5, "confidence": 0.65 },
        { "date": "2026-04-07", "predictedUnits": 7, "confidence": 0.69 }
      ]
    }
  ]
}
```

### Error responses

Same error codes as `POST /ai/forecast`.

---

## GET /ai/forecast/health

Service health check.

### Request

```
GET /ai/forecast/health
```

No authentication required.

### Response `200 OK`

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| `status` | `string` | Value: `"ok"` | Service status |
| `modelsLoaded` | `boolean` | | Whether forecast models are loaded and ready |
| `lastTrainedAt` | `string` | ISO 8601 | Timestamp of last model training run |

**Example response:**

```json
{
  "status": "ok",
  "modelsLoaded": true,
  "lastTrainedAt": "2026-03-29T02:00:00.000Z"
}
```

### Response `503 Service Unavailable`

Returned when models failed to load:

```json
{
  "status": "ok",
  "modelsLoaded": false,
  "lastTrainedAt": null
}
```

---

## Notes for implementors (Reda / Sam)

1. **Confidence scoring** (SRS Table 25): confidence is a float from 0.0 to 1.0 computed from data history length:
   - 90+ days of history: 0.75 to 0.95
   - 30 to 90 days: 0.50 to 0.74
   - Fewer than 30 days: 0.20 to 0.49
   - Zero orders: 0.10 to 0.25

2. **Drivers array** always contains at least 3 items and is never empty. Generated from feature importances of the ensemble model.

3. **Variant semantics:**
   - `balanced` -- default, applies newsvendor-optimal safety buffer. Minimizes total business cost.
   - `waste_optimized` -- newsvendor buffer x 0.90. Less over-preparation, accepts more stockout risk.
   - `stockout_optimized` -- newsvendor buffer x 1.06. More over-preparation, reduces stockout frequency.

4. **Newsvendor safety buffer per item:**
   - Critical ratio = stockout_cost / (stockout_cost + waste_cost) = 1.5 / 1.8 = 0.833
   - buffer_multiplier = 1 + z_0.833 x sigma / mean_demand
   - Clamped between 1.0 and 2.0
   - Items with fewer than 30 days of history fall back to uniform 1.27 buffer

5. **Forecast horizon:** Do not request more than 14 days in a single prediction window. For longer ranges, the system stitches overlapping 14-day windows. Predictions beyond 14 days from the training cutoff will have reduced confidence.

6. **lower is always less than predicted. upper is always greater than predicted.** This is enforced server-side.

7. **predictions[].predictedUnits in /ai/forecast/items is always an integer** (whole units). Revenue predictions in /ai/forecast are floats.
