# AI-Enhanced Inventory Forecasting: Improvement Opportunities

## Executive Summary

Current system achieves **15% stockout rate** using time-series features. This document proposes AI enhancements to reduce stockouts to **<10%** and improve accuracy by **20-30%** using:

1. **Internal data sources** (campaigns, location, weather patterns)
2. **External AI integrations** (news sentiment, events, weather APIs)
3. **Advanced ML techniques** (LLM embeddings, ensemble models, anomaly detection)

---

## Available Internal Data Sources (Not Yet Used)

### 1. Marketing Campaigns ⭐ HIGH IMPACT
**Data:** `fct_campaigns.csv` (641 campaigns)

**Available Information:**
- Campaign type: "2 for 1", "Discount", "Freebie"
- Discount amount: 10%, 15%, 20%, 33%
- Item-specific promotions (553 campaigns target specific items)
- Date ranges: start_date_time → end_date_time
- Redemptions: actual usage count

**Expected Impact:** **+15-25% accuracy improvement**
- 2-for-1 campaigns can **double** sales of specific items
- Discounts typically increase demand by 25-50%
- Currently our model treats promotional days as "normal" demand

**Implementation:**
```python
# Feature engineering
df['has_active_campaign'] = campaign_check(df['day'], df['place_id'])
df['campaign_discount_pct'] = get_discount_pct(df['day'], df['place_id'])
df['campaign_type'] = get_campaign_type(df['day'], df['item_id'])
df['days_since_last_campaign'] = calculate_recency(df['item_id'])
df['campaign_redemption_history'] = get_avg_redemptions(df['item_id'])
```

**Example Scenario:**
```
Normal day: Latte sales = 45 units
Campaign day (20% off): Latte sales = 67 units (+49% spike)
Without campaign features: Model predicts 45 → 22 unit shortage (49% stockout)
With campaign features: Model predicts 65 → 2 unit shortage (3% stockout)
```

---

### 2. Restaurant Location & Context ⭐ MEDIUM IMPACT
**Data:** `dim_places.csv` (1,824 restaurants)

**Available Information:**
- **Cuisine types** (cuisine_ids): Ethiopian, Indian, Italian, Asian, etc.
- **Opening hours** (JSON): Day-specific schedules
- **Location** (latitude, longitude, street_address, area)
- **Service types**: delivery, eat_in, takeaway flags
- **Business indicators**: active, seasonal, accepting_orders

**Expected Impact:** **+10-15% accuracy improvement**
- Weather affects outdoor seating (eat_in vs takeaway)
- Cuisine preferences vary by location + season
- Opening hours affect peak demand times

**Implementation:**
```python
# Location-based features
df['cuisine_type'] = map_cuisine(df['place_id'])
df['has_outdoor_seating'] = check_eat_in(df['place_id'])
df['opens_late'] = check_opening_hours(df['place_id'], 'late')  # After 8pm
df['weekend_only'] = check_opening_hours(df['place_id'], 'weekend')
df['neighborhood_type'] = cluster_by_location(df['latitude'], df['longitude'])

# Cross-features with weather (if integrated)
df['outdoor_favorable'] = df['has_outdoor_seating'] * df['good_weather']
df['delivery_weather_boost'] = df['takeaway'] * df['bad_weather']
```

**Example Scenario:**
```
Pizza restaurant with outdoor seating:
Rainy day → +30% delivery demand, -40% eat-in demand
Sunny Saturday → +50% eat-in demand, normal delivery
Model learns: Italian + outdoor + sunny + weekend = high demand spike
```

---

### 3. Order Patterns (Already Partially Used)
**Data:** `fct_orders.csv` + `fct_order_items.csv`

**Currently using:** Daily aggregates, lags, rolling averages
**Not yet using:**
- **Order timing** (hour of day)
- **Order size distribution** (avg items per order)
- **Order types** (eat_in vs delivery vs takeaway split)
- **Customer behavior** (repeat orders, basket correlation)

**Expected Impact:** **+5-10% accuracy improvement**

**Implementation:**
```python
# Temporal patterns
df['peak_hours_pct'] = calc_peak_hour_concentration(df['item_id'])
df['lunch_vs_dinner_ratio'] = calc_meal_period_split(df['item_id'])

# Basket patterns
df['frequently_ordered_with'] = get_correlated_items(df['item_id'])
df['avg_basket_size'] = calc_avg_basket(df['item_id'])

# Customer patterns
df['repeat_customer_pct'] = calc_repeat_rate(df['item_id'])
```

---

## External Data Sources (AI Integration Opportunities)

### 4. Weather Data ⭐⭐ VERY HIGH IMPACT
**Source:** OpenWeatherMap API, Weather.com API (free tiers available)

**Key Variables:**
- Temperature (°C)
- Precipitation (mm/day)
- Conditions (sunny, rainy, cloudy, snowy)
- Wind speed
- Humidity

**Expected Impact:** **+20-30% accuracy improvement**
- Hot days (+25°C) → +40% cold drinks, -20% hot drinks
- Rainy days → +60% delivery demand, -50% eat-in demand
- Cold days (<5°C) → +30% soup/hot dishes

**Implementation:**
```python
import requests

def get_historical_weather(lat, lon, date):
    """Fetch historical weather via API"""
    api_key = "YOUR_KEY"
    url = f"https://api.openweathermap.org/data/3.0/onecall/day_summary"
    params = {
        "lat": lat,
        "lon": lon,
        "date": date.strftime("%Y-%m-%d"),
        "appid": api_key,
    }
    response = requests.get(url, params=params)
    weather = response.json()
    return {
        "temp_avg": weather["temperature"]["afternoon"],
        "precipitation": weather["precipitation"]["total"],
        "weather_main": weather["cloud_cover"]["afternoon"],
    }

# Feature engineering
df['temperature'] = df.apply(lambda x: get_weather(x['latitude'], x['longitude'], x['day']), axis=1)
df['is_rainy'] = (df['precipitation'] > 5).astype(int)
df['is_hot_day'] = (df['temperature'] > 25).astype(int)
df['is_cold_day'] = (df['temperature'] < 10).astype(int)

# Cross-features
df['hot_day_cold_drink'] = df['is_hot_day'] * df['is_cold_beverage']
df['rainy_day_delivery'] = df['is_rainy'] * df['is_delivery_item']
```

**Cost:** Free tier (1,000 calls/day) sufficient for historical analysis

---

### 5. News & Events Sentiment Analysis ⭐ HIGH IMPACT
**Source:** News APIs + LLM Sentiment Analysis

**Relevant Events:**
- **Local events**: Festivals, concerts, sports games → +50-200% demand nearby
- **Holidays**: Christmas, Easter, National Day → seasonal menu demand shifts
- **Breaking news**: COVID restrictions, strikes → -30-80% demand crashes
- **Food trends**: "Veganuary", health trends → +100% vegan item demand

**Expected Impact:** **+15-20% accuracy for anomalies**

**Implementation:**

**Option A: News API + Sentiment Analysis**
```python
from newsapi import NewsApiClient
from transformers import pipeline

# Initialize
newsapi = NewsApiClient(api_key='YOUR_KEY')
sentiment_analyzer = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")

def get_local_news_sentiment(date, location="Copenhagen"):
    """Get news sentiment for location and date"""
    articles = newsapi.get_everything(
        q=f"{location} restaurants food",
        from_param=date,
        to=date,
        language='en',
        sort_by='relevancy',
        page_size=20
    )
    
    sentiments = [
        sentiment_analyzer(article['title'] + " " + article['description'])[0]
        for article in articles['articles']
    ]
    
    positive_count = sum(1 for s in sentiments if s['label'] == 'POSITIVE')
    return positive_count / len(sentiments) if sentiments else 0.5

# Feature engineering
df['news_sentiment'] = df['day'].apply(lambda d: get_local_news_sentiment(d))
df['news_sentiment_lag_7'] = df.groupby('place_id')['news_sentiment'].shift(7)
```

**Option B: LLM-Based Event Detection**
```python
from openai import OpenAI

client = OpenAI(api_key='YOUR_KEY')

def detect_special_events(date, location):
    """Use GPT to identify special events"""
    prompt = f"""
    List any major events, holidays, or unusual circumstances in {location} 
    on {date.strftime('%Y-%m-%d')} that would affect restaurant demand.
    
    Format: EVENT_TYPE | IMPACT_LEVEL (1-5) | DESCRIPTION
    Examples:
    - FESTIVAL | 5 | Copenhagen Pride Festival (high foot traffic)
    - HOLIDAY | 3 | National Day (some restaurants closed)
    - WEATHER | 4 | Heat wave (high demand for cold drinks)
    - NONE | 0 | Regular day
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150
    )
    
    event_info = response.choices[0].message.content
    # Parse and return structured data
    return parse_event_impact(event_info)

# Feature engineering
df['event_impact_level'] = df.apply(
    lambda x: detect_special_events(x['day'], x['location']),
    axis=1
)
df['is_festival_day'] = (df['event_impact_level'] >= 4).astype(int)
```

**Cost:**
- NewsAPI: Free tier (100 requests/day)
- OpenAI GPT-4: ~$0.03 per day analyzed (~$10/year for 3 years of data)
- Alternative: Use free Hugging Face models (DistilBERT, RoBERTa)

---

### 6. Social Media Trends ⭐ MEDIUM IMPACT
**Source:** Instagram, TikTok, Google Trends

**Use Cases:**
- Viral food trends (e.g., "Dalgona coffee" in 2020 → +300% coffee sales)
- Restaurant mentions → demand spikes next day
- Hashtag tracking (#vegan, #healthyfood) → category demand shifts

**Implementation:**
```python
from pytrends.request import TrendReq

def get_google_trends(keyword, date_range):
    """Get Google search trends for food items"""
    pytrends = TrendReq(hl='en-US', tz=360)
    pytrends.build_payload([keyword], timeframe=date_range, geo='DK')
    trends = pytrends.interest_over_time()
    return trends[keyword] if keyword in trends else 0

# Feature engineering
df['vegan_trend_score'] = df['day'].apply(
    lambda d: get_google_trends("vegan food copenhagen", d)
)
df['item_search_trend'] = df.apply(
    lambda x: get_google_trends(x['item_name'], x['day']),
    axis=1
)
```

**Cost:** Free (Google Trends API)

---

## Advanced ML Techniques

### 7. LLM Embeddings for Item Similarity ⭐ MEDIUM-HIGH IMPACT
**Concept:** Use language models to understand item relationships

**Problem:** 
- "Cappuccino" and "Latte" are similar → should have correlated demand
- "Vegan burger" and "Beyond burger" → same customer segment
- Current model treats all 17,273 items independently

**Solution:**
```python
from sentence_transformers import SentenceTransformer

# Load model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Get embeddings for all items
items = df[['item_id', 'item_name', 'description']].drop_duplicates()
items['text'] = items['item_name'] + " " + items['description'].fillna("")
items['embedding'] = items['text'].apply(lambda x: model.encode(x))

# Find similar items
from sklearn.metrics.pairwise import cosine_similarity

def get_similar_items(item_id, top_k=5):
    """Find k most similar items"""
    target_emb = items[items['item_id'] == item_id]['embedding'].values[0]
    similarities = cosine_similarity([target_emb], list(items['embedding']))[0]
    top_indices = similarities.argsort()[-top_k:][::-1]
    return items.iloc[top_indices]['item_id'].tolist()

# Use as features
df['similar_item_demand_avg'] = df.apply(
    lambda x: df[
        df['item_id'].isin(get_similar_items(x['item_id'])) &
        (df['day'] == x['day'])
    ]['demand'].mean(),
    axis=1
)
```

**Expected Impact:** **+10-15% accuracy** for new/rare items

---

### 8. Ensemble Models & AutoML
**Current:** LightGBM and XGBoost separately
**Proposed:** Stacked ensemble

```python
from sklearn.ensemble import StackingRegressor
from sklearn.linear_model import Ridge

# Base models
base_models = [
    ('lgb', lgb.LGBMRegressor(objective="quantile", alpha=0.90)),
    ('xgb', xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.90)),
    ('gb', GradientBoostingRegressor(loss='quantile', alpha=0.90)),
]

# Meta-learner
meta_model = Ridge()

# Stacked ensemble
stacked_model = StackingRegressor(
    estimators=base_models,
    final_estimator=meta_model,
    cv=5
)
```

**Expected Impact:** **+5-8% accuracy improvement**

---

### 9. Anomaly Detection for Demand Shocks
**Problem:** Sudden demand changes (COVID lockdowns, venue closures) skew forecasts

**Solution:**
```python
from sklearn.ensemble import IsolationForest

# Train anomaly detector
anomaly_detector = IsolationForest(contamination=0.05, random_state=42)
anomaly_detector.fit(df[features])

# Flag anomalies
df['is_anomaly'] = anomaly_detector.predict(df[features]) == -1

# Adjust predictions
df['adjusted_prediction'] = np.where(
    df['is_anomaly'],
    df['demand_rolling_mean_28'],  # Use long-term average for anomalies
    df['prediction']  # Use model prediction for normal days
)
```

**Expected Impact:** **+10-15% accuracy during disruptions**

---

## Implementation Roadmap

### Phase 1: Internal Data (2-3 weeks)
**Immediate improvements using existing data**

1. **Week 1: Campaign Integration**
   - Load fct_campaigns.csv
   - Engineer campaign features (has_campaign, discount_pct, campaign_type)
   - Retrain models with campaign features
   - **Target:** Reduce stockout rate from 15% → 12%

2. **Week 2: Location & Opening Hours**
   - Extract cuisine types, opening hours
   - Create location clusters (neighborhood types)
   - Add service type features (delivery/eat-in split)
   - **Target:** Improve MAE by 10%

3. **Week 3: Order Pattern Analysis**
   - Add hour-of-day patterns
   - Basket correlation analysis
   - Customer repeat behavior
   - **Target:** Improve high-demand item accuracy by 15%

**Expected Results:**
- Stockout rate: 15% → **10-11%**
- MAE: 3.84 → **3.2-3.4 units**
- High-risk items (>70% stockout): 4 items → **1-2 items**

---

### Phase 2: Weather Integration (1-2 weeks)
**External API integration**

1. **Week 1: Historical Weather**
   - Sign up for OpenWeatherMap API (free tier)
   - Fetch historical weather for all dates (2021-2024)
   - Engineer weather features (temp, precipitation, conditions)
   - Create weather × item interaction features

2. **Week 2: Weather-Aware Models**
   - Retrain with weather features
   - A/B test: weather vs no-weather models
   - Optimize weather feature engineering
   - **Target:** Reduce stockout rate to **8-9%**

**Expected Results:**
- Stockout rate: 10-11% → **8-9%**
- MAE: 3.2-3.4 → **2.8-3.0 units**
- Weather-sensitive items (drinks, soups): **+25% accuracy**

---

### Phase 3: News & Events (2-4 weeks)
**AI-powered event detection**

1. **Option A: Simple (Free)**
   - Use Google Trends API for food trend tracking
   - Manual event calendar (holidays, festivals)
   - Rule-based adjustments

2. **Option B: Advanced (Paid)**
   - NewsAPI integration ($449/month or free tier with limits)
   - LLM-based event detection (GPT-4 or open-source)
   - Sentiment analysis pipeline
   - **Target:** Reduce stockout rate to **7-8%**

**Expected Results:**
- Stockout rate: 8-9% → **7-8%**
- Anomaly detection: **+30% accuracy** during events
- Viral trend response: **+50% accuracy** for trending items

---

### Phase 4: Advanced ML (3-4 weeks)
**State-of-the-art techniques**

1. **LLM Embeddings**
   - Generate item embeddings
   - Similarity-based features
   - Cold-start item forecasting

2. **Ensemble Models**
   - Stacked ensemble (LightGBM + XGBoost + GradientBoosting)
   - AutoML hyperparameter optimization (Optuna)
   - Model selection per item category

3. **Anomaly Detection**
   - Isolation Forest for outlier detection
   - Adjust predictions during disruptions
   - **Target:** Stockout rate **<7%**

**Expected Results:**
- Stockout rate: 7-8% → **<7%**
- MAE: 2.8-3.0 → **<2.5 units**
- Overall accuracy: **+30-35% vs baseline**

---

## Cost-Benefit Analysis

### Costs

| Component | Cost | Frequency |
|-----------|------|-----------|
| **Phase 1** (Internal data) | $0 | One-time |
| **Phase 2** (Weather API) | $0 (free tier) | Ongoing |
| NewsAPI (optional) | $0 - $449/month | Ongoing |
| **OpenAI GPT-4** (optional) | ~$10/year | Annual |
| **Developer time** | 6-10 weeks | One-time |

**Total: $0 - $5,388/year** (depending on paid APIs)

### Benefits

**Stockout Reduction:**
- Current: 15% stockout rate → **~36.5 days per item** running out
- Target: 7% stockout rate → **~17 days per item** running out
- **Reduction: 19.5 days** per item per year

**Revenue Impact (per item):**
```
Assume:
- Average item price: 100 DKK
- Average daily demand: 10 units
- Stockout = lost sales

Lost revenue per stockout day = 10 units × 100 DKK = 1,000 DKK
Stockout reduction per item = 19.5 days
Revenue recovered = 19.5 × 1,000 DKK = 19,500 DKK/item/year

For top 100 items:
Total revenue recovery = 100 items × 19,500 DKK = 1,950,000 DKK/year (~$285,000/year)
```

**ROI:** ~5,000% (even with paid APIs)

---

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DATA INGESTION LAYER                     │
├─────────────────────────────────────────────────────────────┤
│ Internal:                    │ External:                     │
│ - Order items                │ - Weather API                 │
│ - Campaigns                  │ - News API                    │
│ - Places                     │ - Google Trends               │
│ - Opening hours              │ - Social media                │
└────────────────┬────────────────────────────┬────────────────┘
                 │                            │
                 ▼                            ▼
┌─────────────────────────────┐  ┌──────────────────────────┐
│   FEATURE ENGINEERING       │  │   AI ENRICHMENT          │
├─────────────────────────────┤  ├──────────────────────────┤
│ - Time features             │  │ - LLM embeddings         │
│ - Lag/rolling stats         │  │ - Sentiment analysis     │
│ - Campaign flags            │  │ - Event detection        │
│ - Weather features          │  │ - Trend analysis         │
│ - Location features         │  │                          │
└────────────────┬────────────┘  └─────────┬────────────────┘
                 │                         │
                 └────────────┬────────────┘
                              ▼
                 ┌────────────────────────┐
                 │   MODELING LAYER       │
                 ├────────────────────────┤
                 │ - LightGBM (Q90)       │
                 │ - XGBoost (Q90)        │
                 │ - Gradient Boosting    │
                 │ - Stacked Ensemble     │
                 │ - Anomaly Detection    │
                 └────────────┬───────────┘
                              ▼
                 ┌────────────────────────┐
                 │   PREDICTION ENGINE    │
                 ├────────────────────────┤
                 │ - Multi-horizon (1/7/30)│
                 │ - Business metrics     │
                 │ - Confidence intervals │
                 │ - Anomaly flags        │
                 └────────────┬───────────┘
                              ▼
                 ┌────────────────────────┐
                 │   OUTPUT & MONITORING  │
                 ├────────────────────────┤
                 │ - Daily forecasts      │
                 │ - Stockout alerts      │
                 │ - Accuracy dashboards  │
                 │ - Model retraining     │
                 └────────────────────────┘
```

---

## Sample Code: Full Pipeline with AI Enhancements

```python
import pandas as pd
import numpy as np
import lightgbm as lgb
import requests
from sentence_transformers import SentenceTransformer

class EnhancedInventoryForecaster:
    """AI-enhanced inventory forecasting system"""
    
    def __init__(self, weather_api_key=None, news_api_key=None):
        self.weather_api_key = weather_api_key
        self.news_api_key = news_api_key
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
    def load_data(self):
        """Load all data sources"""
        # Internal data
        self.demand_df = pd.read_csv("data/fct_order_items.csv")
        self.campaigns_df = pd.read_csv("data/fct_campaigns.csv")
        self.places_df = pd.read_csv("data/dim_places.csv")
        
        # Preprocess campaigns
        self.campaigns_df['start_date'] = pd.to_datetime(self.campaigns_df['start_date_time'], unit='s')
        self.campaigns_df['end_date'] = pd.to_datetime(self.campaigns_df['end_date_time'], unit='s')
        
    def engineer_campaign_features(self, df):
        """Add campaign features"""
        df['has_campaign'] = df.apply(
            lambda x: self._check_active_campaign(x['day'], x['place_id'], x['item_id']),
            axis=1
        )
        df['campaign_discount'] = df.apply(
            lambda x: self._get_discount(x['day'], x['place_id']),
            axis=1
        )
        return df
    
    def engineer_weather_features(self, df):
        """Add weather features via API"""
        if not self.weather_api_key:
            return df
        
        df['temperature'] = df.apply(
            lambda x: self._get_weather(x['latitude'], x['longitude'], x['day'])['temp'],
            axis=1
        )
        df['precipitation'] = df.apply(
            lambda x: self._get_weather(x['latitude'], x['longitude'], x['day'])['precip'],
            axis=1
        )
        df['is_rainy'] = (df['precipitation'] > 5).astype(int)
        df['is_hot'] = (df['temperature'] > 25).astype(int)
        
        return df
    
    def engineer_news_features(self, df):
        """Add news sentiment features"""
        if not self.news_api_key:
            return df
        
        df['news_sentiment'] = df['day'].apply(
            lambda d: self._get_news_sentiment(d)
        )
        return df
    
    def engineer_item_similarity_features(self, df):
        """Add LLM-based item similarity features"""
        # Get item embeddings
        items = df[['item_id', 'item_name']].drop_duplicates()
        items['embedding'] = items['item_name'].apply(
            lambda x: self.embedder.encode(x)
        )
        
        # Add average demand of similar items
        df['similar_items_demand'] = df.apply(
            lambda x: self._get_similar_items_demand(x, items),
            axis=1
        )
        return df
    
    def train_ensemble(self, X_train, y_train):
        """Train stacked ensemble"""
        from sklearn.ensemble import StackingRegressor
        from sklearn.linear_model import Ridge
        
        base_models = [
            ('lgb', lgb.LGBMRegressor(objective="quantile", alpha=0.90)),
            ('xgb', xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.90)),
        ]
        
        self.model = StackingRegressor(
            estimators=base_models,
            final_estimator=Ridge(),
            cv=5
        )
        
        self.model.fit(X_train, y_train)
    
    def predict_with_anomaly_detection(self, X_test):
        """Predict with anomaly adjustment"""
        from sklearn.ensemble import IsolationForest
        
        # Detect anomalies
        anomaly_detector = IsolationForest(contamination=0.05)
        anomalies = anomaly_detector.fit_predict(X_test) == -1
        
        # Get predictions
        predictions = self.model.predict(X_test)
        
        # Adjust anomalies
        predictions[anomalies] = X_test.loc[anomalies, 'demand_rolling_mean_28']
        
        return predictions, anomalies
    
    def _check_active_campaign(self, day, place_id, item_id):
        """Check if campaign active on day"""
        active = self.campaigns_df[
            (self.campaigns_df['place_id'] == place_id) &
            (self.campaigns_df['start_date'] <= day) &
            (self.campaigns_df['end_date'] >= day) &
            (self.campaigns_df['item_ids'].str.contains(str(item_id), na=False))
        ]
        return len(active) > 0
    
    def _get_weather(self, lat, lon, date):
        """Fetch weather data"""
        url = f"https://api.openweathermap.org/data/3.0/onecall/day_summary"
        params = {
            "lat": lat,
            "lon": lon,
            "date": date.strftime("%Y-%m-%d"),
            "appid": self.weather_api_key,
        }
        response = requests.get(url, params=params)
        data = response.json()
        return {
            'temp': data['temperature']['afternoon'],
            'precip': data['precipitation']['total']
        }
    
    def _get_news_sentiment(self, date):
        """Get news sentiment for date"""
        # Implementation using NewsAPI + sentiment model
        pass
    
    def _get_similar_items_demand(self, row, items_with_embeddings):
        """Calculate demand from similar items"""
        # Find similar items using cosine similarity
        # Average their demand on the same day
        pass

# Usage
forecaster = EnhancedInventoryForecaster(
    weather_api_key="YOUR_WEATHER_KEY",
    news_api_key="YOUR_NEWS_KEY"
)

forecaster.load_data()
df = forecaster.engineer_all_features(demand_df)
forecaster.train_ensemble(X_train, y_train)
predictions, anomalies = forecaster.predict_with_anomaly_detection(X_test)
```

---

## Monitoring & Continuous Improvement

### Real-Time Monitoring Dashboard
```python
import streamlit as st
import plotly.express as px

# Daily accuracy tracking
st.title("AI-Enhanced Inventory Forecast Monitor")

# Key metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Today's Stockout Rate", "7.2%", "-2.8%")
col2.metric("MAE (24h)", "2.4 units", "-1.4 units")
col3.metric("Revenue Protected", "$12,450", "+$3,200")
col4.metric("Active Campaigns", "23", "+5")

# Prediction accuracy over time
fig = px.line(accuracy_df, x='date', y=['mae', 'stockout_rate'])
st.plotly_chart(fig)

# High-risk items alert
st. subheader("⚠️ High-Risk Items (Stockout > 15%)")
st.dataframe(high_risk_items[['item_name', 'predicted_demand', 'stockout_risk']])

# Campaign impact
st.subheader("📊 Campaign Performance")
st.dataframe(campaign_lift_df)
```

### A/B Testing Framework
```python
def ab_test_features(baseline_features, new_features, test_period_days=30):
    """Compare model performance with/without new features"""
    
    # Train baseline model
    baseline_model = train_model(baseline_features)
    baseline_mae = evaluate_model(baseline_model, test_period_days)
    
    # Train enhanced model
    enhanced_model = train_model(baseline_features + new_features)
    enhanced_mae = evaluate_model(enhanced_model, test_period_days)
    
    # Statistical test
    improvement_pct = (baseline_mae - enhanced_mae) / baseline_mae * 100
    p_value = statistical_significance_test(baseline_mae, enhanced_mae)
    
    print(f"Improvement: {improvement_pct:.1f}%")
    print(f"Statistically significant: {p_value < 0.05}")
    
    return enhanced_model if p_value < 0.05 else baseline_model
```

---

## Conclusion & Recommendations

### Immediate Actions (Do This First)
1. ✅ **Integrate campaign data** (Week 1)
   - Highest ROI: +15-25% accuracy improvement
   - Zero cost, uses existing data
   - Implementation: 2-3 days

2. ✅ **Add weather features** (Week 2)
   - Very high impact: +20-30% accuracy
   - Free API tier available
   - Implementation: 3-5 days

3. ✅ **Location & opening hours** (Week 3)
   - Medium impact: +10-15% accuracy
   - Zero cost, uses existing data
   - Implementation: 2-3 days

### Medium-Term (Month 2-3)
4. **News & events integration**
   - High impact: +15-20% for anomalies
   - Cost: $0 (free tier) or $449/month (paid)
   - Consider: Start with free Google Trends

5. **LLM embeddings**
   - Medium-high impact: +10-15% for rare items
   - Free (open-source models)
   - Implementation: 1 week

### Long-Term (Month 4+)
6. **Ensemble models & AutoML**
   - Medium impact: +5-8% accuracy
   - Zero cost
   - Implementation: 2 weeks

7. **Real-time monitoring dashboard**
   - Operational efficiency
   - Zero cost (Streamlit open-source)
   - Implementation: 1 week

### Expected Final Results
| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| **Stockout Rate** | 15.0% | <7.0% | **-53%** |
| **MAE** | 3.84 units | <2.5 units | **-35%** |
| **Revenue Protected** | Baseline | +$285K/year | **+** |
| **High-Risk Items** | 4 items | <2 items | **-50%** |

### Total Investment
- **Development time:** 8-12 weeks
- **Ongoing costs:** $0 - $5,388/year
- **ROI:** ~5,000% (based on revenue recovery)

---

## Appendix: Data Quality Recommendations

### Current Data Gaps
1. **Bill of Materials:** Only 2 records → Cannot forecast ingredients
   - **Action:** Populate BOM or deprioritize ingredient forecasting
   
2. **Missing weather history:** Need historical weather data
   - **Action:** Backfill via OpenWeatherMap historical API

3. **Campaign redemptions:** Some campaigns have 0 redemptions
   - **Action:** Data quality audit of campaign tracking

### Data Collection Priorities
1. **High priority:** Weather data (massive impact)
2. **Medium priority:** Complete campaign redemption tracking
3. **Low priority:** Social media monitoring (nice-to-have)

---

**Document Version:** 1.0  
**Last Updated:** February 7, 2026  
**Next Review:** Post Phase 1 completion (3 weeks)
