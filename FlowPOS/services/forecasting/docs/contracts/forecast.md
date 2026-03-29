# Forecast API Contract

**Service:** FlowPOS AI Intelligence Suite — Pillar 1: Sales Forecasting
**Base path:** `/ai`
**Protocol:** HTTPS, JSON
**Auth:** Bearer token via `Authorization` header (passed through API gateway)

---

## POST /ai/forecast

Generate multi-day demand forecasts for all items at a given place (restaurant location).

### Request

```
POST /ai/forecast
Content-Type: application/json
Authorization: Bearer <token>
```

**Body** (SRS Table 4):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `placeId` | `string` (UUID) | Yes | Loving Loyalty place identifier |
| `startDate` | `string` (ISO 8601 date) | Yes | First day of forecast window (`YYYY-MM-DD`) |
| `endDate` | `string` (ISO 8601 date) | Yes | Last day of forecast window (`YYYY-MM-DD`). Max span: 30 days. |
| `granularity` | `string` enum | No | `"daily"` (default) or `"weekly"` |
| `variant` | `string` enum | No | `"balanced"` (default), `"waste_optimized"`, or `"stockout_optimized"` |
| `topN` | `integer` | No | Limit results to top N items by predicted volume. Omit for all items. |
| `itemFilter` | `string` | No | Substring match on item title (case-insensitive). |

**Example request:**

```json
{
  "placeId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "startDate": "2026-04-01",
  "endDate": "2026-04-07",
  "granularity": "daily",
  "variant": "balanced",
  "topN": 15
}
```

### Response `200 OK`

**Body** (SRS Table 5):

| Field | Type | Description |
|-------|------|-------------|
| `placeId` | `string` | Echo of request `placeId` |
| `forecastedAt` | `string` (ISO 8601 datetime) | Server timestamp when forecast was generated |
| `granularity` | `string` | Echo of request `granularity` |
| `variant` | `string` | Echo of request `variant` |
| `predictions` | `array<Prediction>` | Per-item per-day forecast entries (see below) |
| `drivers` | `array<Driver>` | Top demand drivers explaining this forecast (minimum 3, never empty) |
| `scenarios` | `object` | Best / expected / worst case total demand over the window |
| `baselineCostDkk` | `number` | Estimated total business cost (DKK) under MA-7 baseline model |
| `forecastCostDkk` | `number` | Estimated total business cost (DKK) under this forecast |
| `costReductionPct` | `number` | Percentage reduction vs baseline (`(baseline - forecast) / baseline * 100`) |

**Prediction object:**

| Field | Type | Description |
|-------|------|-------------|
| `date` | `string` (ISO 8601 date) | Forecast date |
| `itemTitle` | `string` | Human-readable item name |
| `itemId` | `integer` \| `null` | Internal item ID (null for items matched by title only) |
| `predicted` | `number` | Point forecast (units). Rounded to 1 decimal place. |
| `lower` | `number` | Lower bound of 80% prediction interval |
| `upper` | `number` | Upper bound of 80% prediction interval |
| `confidence` | `string` enum | `"high"` (≥30 days history), `"medium"` (14–29 days), `"low"` (5–13 days), `"very_low"` (<5 days) |
| `demandRisk` | `string` enum | `"low"`, `"medium"`, `"high"` based on coefficient of variation |
| `isPerishable` | `boolean` | Whether the item is classified as perishable |
| `safetyStock` | `number` | Recommended safety stock units (newsvendor buffer: `1.65 × σ`) |
| `modelSource` | `string` | Model that produced this prediction (e.g. `"RF300+ET800_blend_75_25"`, `"cold_start_estimate"`) |

**Driver object:**

| Field | Type | Description |
|-------|------|-------------|
| `factor` | `string` | Name of the demand driver (e.g. `"day_of_week"`, `"recent_trend"`, `"weekend_effect"`) |
| `impact` | `string` enum | `"positive"` or `"negative"` |
| `weight` | `number` | Relative importance in range [0, 1]. All weights in the array sum to ≤ 1.0. |

**Scenarios object:**

| Field | Type | Description |
|-------|------|-------------|
| `best` | `number` | Total forecasted units under optimistic scenario (upper bound sum) |
| `expected` | `number` | Total forecasted units under base scenario (sum of `predicted`) |
| `worst` | `number` | Total forecasted units under pessimistic scenario (lower bound sum) |

**Example response:**

```json
{
  "placeId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "forecastedAt": "2026-03-29T14:22:05.123456",
  "granularity": "daily",
  "variant": "balanced",
  "predictions": [
    {
      "date": "2026-04-01",
      "itemTitle": "Classic Burger",
      "itemId": 42,
      "predicted": 18.5,
      "lower": 13.0,
      "upper": 25.9,
      "confidence": "high",
      "demandRisk": "low",
      "isPerishable": false,
      "safetyStock": 5.2,
      "modelSource": "RF300+ET800_blend_75_25"
    }
  ],
  "drivers": [
    { "factor": "day_of_week",    "impact": "positive", "weight": 0.38 },
    { "factor": "recent_trend",   "impact": "positive", "weight": 0.27 },
    { "factor": "weekend_effect", "impact": "negative", "weight": 0.18 }
  ],
  "scenarios": {
    "best": 1420.0,
    "expected": 1105.0,
    "worst": 812.0
  },
  "baselineCostDkk": 6967146.0,
  "forecastCostDkk": 5225357.0,
  "costReductionPct": 25.0
}
```

### Error responses

| Status | Code | Description |
|--------|------|-------------|
| `400 Bad Request` | `INVALID_DATE_RANGE` | `endDate` before `startDate`, or span > 30 days |
| `400 Bad Request` | `INVALID_GRANULARITY` | Unknown granularity value |
| `400 Bad Request` | `INVALID_VARIANT` | Unknown variant value |
| `404 Not Found` | `PLACE_NOT_FOUND` | No sales history found for `placeId` |
| `422 Unprocessable Entity` | `VALIDATION_ERROR` | Missing required fields |
| `500 Internal Server Error` | `FORECAST_FAILED` | Model inference error |

---

## POST /ai/forecast/items

Generate demand forecasts broken down by individual menu item, with ingredient-level impact.

### Request

```
POST /ai/forecast/items
Content-Type: application/json
Authorization: Bearer <token>
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `placeId` | `string` (UUID) | Yes | Loving Loyalty place identifier |
| `startDate` | `string` (ISO 8601 date) | Yes | First day of forecast window |
| `endDate` | `string` (ISO 8601 date) | Yes | Last day of forecast window |
| `itemIds` | `array<integer>` | No | Restrict to specific item IDs. Omit for all items. |
| `includeIngredients` | `boolean` | No | If `true`, explode forecasts through BOM to ingredient level. Default: `false`. |
| `variant` | `string` enum | No | `"balanced"` (default), `"waste_optimized"`, `"stockout_optimized"` |

**Example request:**

```json
{
  "placeId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "startDate": "2026-04-01",
  "endDate": "2026-04-07",
  "itemIds": [42, 55, 67],
  "includeIngredients": true,
  "variant": "balanced"
}
```

### Response `200 OK`

| Field | Type | Description |
|-------|------|-------------|
| `placeId` | `string` | Echo of request `placeId` |
| `forecastedAt` | `string` (ISO 8601 datetime) | Server timestamp |
| `variant` | `string` | Echo of request `variant` |
| `items` | `array<ItemForecast>` | Per-item forecast summary over the full window |
| `ingredients` | `array<IngredientForecast>` \| `null` | Ingredient-level demand (present only if `includeIngredients: true`) |
| `summary` | `object` | Aggregate statistics over the forecast window |

**ItemForecast object:**

| Field | Type | Description |
|-------|------|-------------|
| `itemId` | `integer` \| `null` | Internal item ID |
| `itemTitle` | `string` | Item name |
| `totalPredicted` | `number` | Total forecasted units over the full window |
| `dailyAvgPredicted` | `number` | Average daily forecast (`totalPredicted / days`) |
| `lower` | `number` | Lower bound sum over the window |
| `upper` | `number` | Upper bound sum over the window |
| `confidence` | `string` enum | `"high"`, `"medium"`, `"low"`, `"very_low"` |
| `demandRisk` | `string` enum | `"low"`, `"medium"`, `"high"` |
| `isPerishable` | `boolean` | Whether the item is perishable |
| `safetyStock` | `number` | Recommended safety stock units |
| `dailyBreakdown` | `array<DailyEntry>` | Per-day predictions (same structure as `Prediction` in `/ai/forecast`) |

**IngredientForecast object:**

| Field | Type | Description |
|-------|------|-------------|
| `ingredientTitle` | `string` | Ingredient / SKU name |
| `skuId` | `integer` | Internal SKU ID |
| `unit` | `string` | Unit of measure (e.g. `"kg"`, `"L"`, `"pcs"`) |
| `forecastedDemand` | `number` | Total quantity needed over the window |
| `currentStock` | `number` | Current stock level |
| `daysOfStockRemaining` | `number` | Days until stock runs out at forecasted rate |
| `needsReorder` | `boolean` | True if stock will be insufficient |
| `reorderUrgency` | `string` enum | `"critical"`, `"soon"`, `"low_stock"`, `"ok"` |
| `suggestedReorderQty` | `number` | Recommended reorder quantity (1.5× daily rate × days ahead minus current stock) |
| `demandDrivers` | `array<string>` | Item titles driving this ingredient's demand |

**Summary object:**

| Field | Type | Description |
|-------|------|-------------|
| `totalItems` | `integer` | Number of items in response |
| `daysAhead` | `integer` | Number of forecast days |
| `needsReorderCount` | `integer` | Number of ingredients needing reorder (only present if `includeIngredients: true`) |
| `criticalCount` | `integer` | Number of ingredients at critical stock level |
| `mappedProducts` | `integer` | Number of products successfully mapped to BOM |

**Example response:**

```json
{
  "placeId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "forecastedAt": "2026-03-29T14:22:05.123456",
  "variant": "balanced",
  "items": [
    {
      "itemId": 42,
      "itemTitle": "Classic Burger",
      "totalPredicted": 129.5,
      "dailyAvgPredicted": 18.5,
      "lower": 90.7,
      "upper": 181.3,
      "confidence": "high",
      "demandRisk": "low",
      "isPerishable": false,
      "safetyStock": 5.2,
      "dailyBreakdown": [
        {
          "date": "2026-04-01",
          "predicted": 18.5,
          "lower": 13.0,
          "upper": 25.9,
          "confidence": "high"
        }
      ]
    }
  ],
  "ingredients": [
    {
      "ingredientTitle": "Beef Patty 150g",
      "skuId": 301,
      "unit": "pcs",
      "forecastedDemand": 129.5,
      "currentStock": 200.0,
      "daysOfStockRemaining": 10.8,
      "needsReorder": false,
      "reorderUrgency": "ok",
      "suggestedReorderQty": 0.0,
      "demandDrivers": ["Classic Burger"]
    }
  ],
  "summary": {
    "totalItems": 1,
    "daysAhead": 7,
    "needsReorderCount": 0,
    "criticalCount": 0,
    "mappedProducts": 1
  }
}
```

### Error responses

Same error codes as `POST /ai/forecast`. Additional:

| Status | Code | Description |
|--------|------|-------------|
| `400 Bad Request` | `BOM_UNAVAILABLE` | `includeIngredients: true` but no BOM data found for this place |

---

## GET /ai/forecast/health

Service liveness and readiness probe.

### Request

```
GET /ai/forecast/health
```

No authentication required.

### Response `200 OK`

| Field | Type | Description |
|-------|------|-------------|
| `status` | `string` | `"healthy"` or `"degraded"` |
| `timestamp` | `string` (ISO 8601 datetime) | Server time of health check |
| `modelsLoaded` | `object` | Map of model name → `true`/`false` |
| `dataSourceStatus` | `string` enum | `"mysql_live"`, `"csv_demo"`, `"unavailable"` |
| `forecastLatencyP50Ms` | `number` \| `null` | Median forecast latency over last 100 requests (null if no requests yet) |
| `version` | `string` | API version string |

**Example response:**

```json
{
  "status": "healthy",
  "timestamp": "2026-03-29T14:22:05.123456",
  "modelsLoaded": {
    "balanced": true,
    "waste_optimized": true,
    "rnn_lstm": false
  },
  "dataSourceStatus": "csv_demo",
  "forecastLatencyP50Ms": 142.3,
  "version": "1.0.0"
}
```

### Response `503 Service Unavailable`

Returned when the primary forecast model failed to load:

```json
{
  "status": "degraded",
  "timestamp": "2026-03-29T14:22:05.123456",
  "modelsLoaded": {
    "balanced": false,
    "waste_optimized": false,
    "rnn_lstm": false
  },
  "dataSourceStatus": "unavailable",
  "forecastLatencyP50Ms": null,
  "version": "1.0.0"
}
```

---

## Notes for implementors (Reda / Sam)

1. **CORS** — The service sets `Access-Control-Allow-Origin: *` for development. Production deployments should restrict to the Loving Loyalty frontend origin.

2. **Caching** — Forecast results are cached in-process for 5 minutes keyed on `(placeId, startDate, endDate, granularity, variant, topN, itemFilter)`. The cache is invalidated on model retrain.

3. **Confidence scoring** (SRS Table 25):
   - `high` — item has ≥ 30 days of sales history
   - `medium` — 14–29 days
   - `low` — 5–13 days
   - `very_low` — < 5 days (cold-start estimate used)

4. **Newsvendor safety buffer** — `safetyStock = 1.65 × σ` where σ is the rolling 14-day standard deviation of daily demand. The 1.65 z-score corresponds to a 95% service level.

5. **Variant semantics:**
   - `balanced` — ensemble median (RF300 global 75% + ET800 per-store 25%), 24% safety buffer
   - `waste_optimized` — conservative lower-bound prediction (minimise overstock waste)
   - `stockout_optimized` — balanced × 1.20 (minimise stockout risk)

6. **Drivers array** is always present with at least 3 entries. Generated from feature importances of the RF/ET ensemble; never empty.
