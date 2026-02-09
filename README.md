# FlowPOS - AI-Powered Point of Sale & Demand Intelligence Platform

> Built for the **DIH x AUC Hackathon** | Fresh Flow Markets, Copenhagen

FlowPOS is a full-stack POS and inventory intelligence system for restaurants, cafes, and grocery stores. It combines a production-grade point-of-sale terminal with AI-driven demand forecasting, real-time context awareness, and an LLM-powered assistant that helps managers make smarter prep, ordering, and waste-reduction decisions every day.

### Live Demo

| Service | URL |
|---------|-----|
| **POS Dashboard** | [https://pos-frontend-production-56bb.up.railway.app](https://pos-frontend-production-56bb.up.railway.app) |
| **Forecasting API** | [https://hopeful-elegance-production-c09a.up.railway.app](https://hopeful-elegance-production-c09a.up.railway.app) |
| **API Health Check** | [https://hopeful-elegance-production-c09a.up.railway.app/api/health](https://hopeful-elegance-production-c09a.up.railway.app/api/health) |

---

## Table of Contents

- [Live Demo](#live-demo)
- [Problem Statement](#problem-statement)
- [Solution Overview](#solution-overview)
- [System Architecture](#system-architecture)
- [POS Platform](#pos-platform)
- [AI Forecasting Engine](#ai-forecasting-engine)
- [LLM Intelligence Layer](#llm-intelligence-layer)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Model Performance](#model-performance)
- [Team](#team)

---

## Problem Statement

Fresh Flow Markets operates 100+ stores across Denmark. They face a classic dual-cost problem:

- **Waste cost**: Overordering perishable items leads to spoilage. Food waste costs DKK millions annually.
- **Stockout cost**: Underordering means lost sales and frustrated customers. Estimated at 1.5x the item price (accounts for lost customer lifetime value).

Managers currently rely on gut feeling and static par levels. There is no system that adapts to weather, holidays, day-of-week patterns, or real-time context.

## Solution Overview

FlowPOS addresses this with three integrated systems:

1. **POS Platform** - A full-featured, role-based point-of-sale system with 33 screens, real-time order management, kitchen display, inventory tracking, loyalty programs, and multi-location support.

2. **AI Forecasting Engine** - Dual trained ML models (HybridForecaster and WasteOptimizedForecaster) that predict demand per item per store per day, with 44 engineered features and business-cost-optimized training.

3. **LLM Intelligence Layer** - An AI assistant powered by DeepSeek v3.2 that arbitrates between the two models per item based on real-time context signals (weather, holidays, payday cycles, Danish retail events), and provides natural-language insights, anomaly explanations, promotion suggestions, and what-if scenario simulations.

---

## System Architecture

```
                        +------------------+
                        |   POS Frontend   |
                        |  Next.js 15 + TS |
                        |    Port 3001     |
                        +--------+---------+
                                 |
                    /api/forecast/* proxy (Next.js rewrites)
                                 |
                        +--------v---------+
                        | Forecasting API  |
                        | FastAPI + Python  |
                        |    Port 8002     |
                        +--------+---------+
                                 |
              +------------------+------------------+
              |                  |                  |
     +--------v------+  +-------v-------+  +-------v--------+
     | DuckDB Engine |  | Trained .pkl  |  | LLM (DeepSeek) |
     | 2M+ order     |  | Models (dual) |  | via OpenRouter  |
     | items loaded  |  | balanced +    |  | + Function      |
     | from CSV      |  | waste-optim.  |  | Calling (10     |
     +---------------+  +---------------+  | tools)          |
                                           +-------+--------+
                                                   |
                                           +-------v--------+
                                           | Context Signals|
                                           | Weather API    |
                                           | Holiday Cal.   |
                                           | Daylight/Astral|
                                           | Payday Cycles  |
                                           +----------------+
```

The frontend communicates with the forecasting backend through Next.js API rewrites, eliminating CORS issues and allowing seamless deployment behind any reverse proxy. The forecasting backend loads all CSV data into an in-memory DuckDB instance at startup for sub-second analytical queries across 400K orders and 2M order items.

---

## POS Platform

The POS frontend is a full-featured, production-ready system built with Next.js 15, React 19, and TypeScript, backed by Supabase (PostgreSQL with Row-Level Security).

### Core Features

| Module | Description |
|--------|-------------|
| **POS Terminal** | Full cart/checkout flow with split payments, modifiers, hold/recall orders |
| **Kitchen Display (KDS)** | Real-time order queue with start/bump workflow, station routing |
| **Order Management** | Order history, status tracking, void/refund with manager approval |
| **Inventory Management** | Stock levels, low-stock alerts, expiry tracking, auto-reorder thresholds |
| **Table Management** | Interactive floor plan editor, merge/split tables, waitlist |
| **Employee Management** | Shifts, clock in/out, role-based access, cash drawer reconciliation |
| **Loyalty Program** | Points, tiered rewards, store credit, birthday promotions |
| **Menu Engineering** | Products, categories, recipes, bill of materials, cost tracking |
| **Coupons & Promotions** | Discount codes, campaign management, auto-apply rules |
| **Reports & Analytics** | Sales reports, product mix, employee performance, daily summaries |
| **Multi-Location** | Organization-level management with per-location settings |
| **Platform Admin** | Organization management, user oversight, audit logs |

### Role-Based Access Control

Six roles with 65+ granular permissions:

| Role | Access Level |
|------|-------------|
| **Owner** | Full access including billing and multi-location management |
| **Admin** | All operations except billing |
| **Manager** | Staff management, reports, voids, inventory, AI features |
| **Cashier** | POS terminal, orders, basic customer info |
| **Waiter** | Table orders, order status updates |
| **Kitchen** | KDS only, order preparation and bumping |

### Technical Highlights

- **22 Zustand stores** for state management (cart, orders, tables, inventory, loyalty, employees, etc.)
- **15 tRPC routers** with 43 type-safe API endpoints
- **Supabase Realtime** for live order and table updates across devices
- **PWA with IndexedDB** for offline operation with background sync
- **i18n** with full English and Arabic (RTL) support
- **Sentry** error tracking in production
- **Email notifications** via Resend (receipts, stock alerts)

### AI-Powered Dashboard Pages

Three dedicated AI pages integrated into the POS dashboard, plus a floating chat panel available on every screen:

- **`/dashboard/forecast`** - Demand forecast with trained model predictions, item filtering, and multi-day horizon
- **`/dashboard/insights`** - AI-generated daily briefings and custom inventory questions
- **`/dashboard/simulator`** - What-if scenario analysis for business decisions
- **Chat Panel** (floating on all pages) - Real-time SSE-streaming AI assistant with tool-calling

---

## AI Forecasting Engine

### Dual-Model Architecture

We evaluated **32 model configurations** on business-impact metrics (total DKK cost = waste + 1.5x stockout) across a 93-day test period covering 101 stores and 1,976 item-pairs.

The winning architecture uses two complementary models:

#### 1. HybridForecaster (Balanced)
- **Blend**: 30% XGBoost + 70% 7-day Moving Average, with rounding
- **Purpose**: Best general-purpose forecast minimizing total business cost
- **Performance**: 15.51M DKK total cost (27.8% savings vs. worst baseline)
- XGBoost captures demand spikes and promotional effects; MA7 tracks recent trends conservatively. The blend smooths XGBoost's tendency to overstock low-volume items.

#### 2. WasteOptimizedForecaster
- **Strategy**: 85% of the balanced prediction (15% shrink factor)
- **Purpose**: Aggressive waste reduction for perishable and volatile items
- **Trade-off**: Accepts slightly more stockouts to dramatically reduce spoilage

### Feature Engineering (44 Features)

The feature pipeline builds a rich representation of each item-day:

| Category | Features | Examples |
|----------|----------|---------|
| **Time** | 12 | day_of_week, month, quarter, is_weekend, is_friday, season |
| **Cyclical** | 4 | dow_sin, dow_cos, month_sin, month_cos |
| **Lag** | 5 | demand_lag_1d, 7d, 14d, 28d, same_weekday_last_week |
| **Rolling** | 7 | rolling_mean_7d/14d/30d, rolling_std_7d/14d, 4-week weekday avg, expanding_mean |
| **Weather** | 4 | temperature_max/min, precipitation_mm, is_rainy |
| **Calendar** | 3 | is_holiday, is_day_before_holiday, is_day_after_holiday |
| **Promotion** | 3 | is_promotion_active, discount_percentage, campaign_count |
| **Store** | 3 | is_open, place_id_encoded, item_id_encoded |
| **Categoricals** | 3 | Encoded via LabelEncoder for XGBoost |

### Training Pipeline

```
Raw CSV Data (2M order items)
    |
    v
DuckDB Aggregation (daily sales per item per store)
    |
    v
Feature Engineering (44 columns)
    |
    v
Train/Test Split (chronological, 93-day test window)
    |
    v
32-Model Grid Search (XGBoost, MA, Hybrid blends, buffer variants)
    |
    v
Business-Cost Evaluation (waste DKK + 1.5x stockout DKK)
    |
    v
Winner: HybridForecaster (30% XGB + 70% MA7, rounded)
    |
    v
Serialized to .pkl (balanced_model.pkl + waste_optimized_model.pkl)
```

---

## LLM Intelligence Layer

The LLM layer turns raw model predictions into actionable decisions. Instead of showing managers two numbers and asking them to choose, the AI decides per item which model to use based on real-time context.

### How It Works

1. **Manager asks**: "What should I prep today?" (via chat, streaming endpoint, or prep-recommendation API)
2. **LLM calls `get_context_signals`**: Fetches today's weather (Open-Meteo API), Danish holidays (workalendar), daylight hours (astral), payday proximity, and retail event calendar
3. **LLM calls `get_dual_forecast`**: Gets both model predictions for all relevant items using the trained .pkl models
4. **LLM arbitrates per item**: Chooses waste-optimized or stockout-optimized based on context rules:

| Use Waste-Optimized | Use Stockout-Optimized |
|---------------------|----------------------|
| Item is perishable (salads, juice, sandwiches) | Friday/Saturday or pre-holiday |
| Slow day (Monday, post-holiday) | Payday week (within 2 days) |
| Bad weather (rain >60%, storms) | Good weather + grilling season (May-Aug, >18C) |
| High demand volatility (CV > 0.8) | School holidays |
| Post-payday period (>10 days since) | Julefrokost, Christmas, Sankt Hans |
| No active promotions | Top sellers with low CV (<0.3) |

5. **LLM responds**: A structured table with per-item prep quantities, safety stock, risk flags (RED/YELLOW/GREEN), and total cost implications in DKK.

### Available LLM Tools (Function Calling)

The LLM has access to 10 data-querying tools:

| Tool | Description |
|------|-------------|
| `query_inventory` | Current stock levels by location/category |
| `get_sales_history` | Historical daily sales with revenue |
| `get_forecast` | Model predictions for items |
| `get_dual_forecast` | Both model predictions with risk analysis |
| `get_context_signals` | Weather, holidays, daylight, payday, events |
| `get_low_stock` | Items below reorder threshold |
| `get_expiring_items` | Items approaching expiry date |
| `get_top_sellers` | Revenue and volume rankings |
| `get_bill_of_materials` | Ingredient breakdown for menu items |
| `run_sql` | Custom analytical queries against all tables |

### Context Signals (Real-Time, Free APIs)

| Signal | Source | Data |
|--------|--------|------|
| **Weather** | Open-Meteo API | Temperature, precipitation, wind, weather code, severity |
| **Holidays** | workalendar (Denmark) | Public holidays, bridge days, pre/post-holiday flags |
| **Daylight** | astral library | Sunrise, sunset, daylight hours (affects evening trade) |
| **Payday** | Calendar heuristic | Danish standard: last business day of month, proximity |
| **Retail Events** | Built-in calendar | Julefrokost, school holidays, Sankt Hans, etc. |
| **Severe Weather** | Open-Meteo | Wind >20 m/s or heavy precipitation warnings |

### Specialized AI Personas

| Persona | Purpose |
|---------|---------|
| **Chat Assistant** | General Q&A with tool-calling against live data |
| **Inventory Analyst** | Structured daily briefings with priority alerts and actions |
| **Inventory Advisor** | Per-item dual-model arbitration with context signals |
| **Anomaly Explainer** | Root-cause analysis when actual sales deviate from forecast |
| **Promotion Strategist** | Discount and bundle suggestions for expiring inventory |
| **Scenario Simulator** | What-if analysis with quantified impact estimates |
| **Daily Briefing** | 60-second morning summary for managers |

---

## Tech Stack

### Frontend
| Technology | Purpose |
|-----------|---------|
| Next.js 15 | React framework with App Router and Turbopack |
| React 19 | UI component library |
| TypeScript | Type safety |
| Tailwind CSS v4 | Utility-first styling with CSS variables for theming |
| Zustand | State management (22 stores) |
| tRPC v11 | Type-safe API layer (15 routers, 43 endpoints) |
| next-intl | Internationalization (English + Arabic RTL) |
| next-pwa | Progressive Web App with offline support |

### Backend (Forecasting Microservice)
| Technology | Purpose |
|-----------|---------|
| FastAPI | High-performance async Python API |
| DuckDB | In-memory analytical database (loads 2M+ rows at startup) |
| scikit-learn | Model serialization and utilities |
| XGBoost | Gradient-boosted tree model component |
| pandas / NumPy | Feature engineering and data manipulation |
| joblib | Model persistence (.pkl serialization) |
| httpx | Async HTTP client for OpenRouter and weather APIs |
| Pydantic | Request/response validation |

### Database & Infrastructure
| Technology | Purpose |
|-----------|---------|
| Supabase (PostgreSQL) | Primary database with RLS for multi-tenancy |
| Supabase Auth | Authentication (email, magic link, PIN) |
| Supabase Realtime | Live order and table sync across devices |
| Resend | Transactional email (receipts, alerts) |
| Sentry | Error tracking and monitoring |

### AI / ML
| Technology | Purpose |
|-----------|---------|
| DeepSeek v3.2 | LLM for chat, insights, arbitration (via OpenRouter) |
| OpenRouter | LLM API gateway |
| Open-Meteo | Weather forecasts (free, no API key) |
| workalendar | Danish holiday calendar |
| astral | Solar position and daylight calculation |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- pnpm 9+

### 1. Clone and Install

```bash
git clone https://github.com/mabdelmagid-sketch/DIH-X-AUC-Hackathon.git
cd DIH-X-AUC-Hackathon
```

### 2. Start the Forecasting Backend

```bash
cd FlowPOS/services/forecasting

# Create .env
cat > .env << EOF
OPENROUTER_API_KEY=your-openrouter-api-key
DEFAULT_LLM=deepseek/deepseek-v3.2
DATA_PATH=./data/Inventory Management
EOF

# Install Python dependencies
pip install -r requirements.txt

# Start the API (port 8002)
python run.py
```

The backend loads all CSV data into DuckDB and pre-loads the trained .pkl models at startup. Health check: `http://localhost:8002/api/health`

### 3. Start the POS Frontend

```bash
cd FlowPOS

# Install dependencies
pnpm install

# Start dev server (port 3001)
pnpm dev
```

The frontend proxies all `/api/forecast/*` requests to the backend automatically via Next.js rewrites.

### 4. Access the Platform

| URL | Page |
|-----|------|
| `http://localhost:3001` | POS Login |
| `http://localhost:3001/dashboard` | Dashboard Home |
| `http://localhost:3001/dashboard/forecast` | AI Demand Forecast |
| `http://localhost:3001/dashboard/insights` | AI Insights & Briefings |
| `http://localhost:3001/dashboard/simulator` | What-If Simulator |
| `http://localhost:3001/pos` | POS Terminal |
| `http://localhost:3001/kitchen` | Kitchen Display |
| `http://localhost:8002/docs` | Forecasting API (Swagger) |

---

## API Reference

### Forecasting Backend (port 8002)

#### Data Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check with model and LLM status |
| GET | `/api/data/tables` | List all loaded data tables with row counts |
| GET | `/api/data/inventory` | Current stock levels across all locations |
| GET | `/api/data/sales` | Historical daily sales data |
| GET | `/api/data/menu` | Menu items with pricing |
| GET | `/api/data/query` | Run custom SQL against loaded tables |

#### AI & Forecast Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/forecast` | Generate demand predictions using trained models |
| POST | `/api/train` | Train/retrain the forecasting model |
| GET | `/api/model/features` | Feature importance from trained model |
| POST | `/api/chat` | Chat with AI assistant (function-calling) |
| POST | `/api/chat/stream` | SSE streaming chat with tool execution |
| POST | `/api/insights` | Generate AI inventory insights |
| POST | `/api/simulate` | Run what-if scenario simulation |
| POST | `/api/prep-recommendation` | AI prep/order recommendation with dual-model arbitration |
| POST | `/api/prep-recommendation/stream` | Streaming version of prep recommendations |
| POST | `/api/explain-anomaly` | Explain why sales deviated from forecast |
| POST | `/api/suggest-promotion` | Get promotion suggestions for expiring items |

Full interactive documentation available at `http://localhost:8002/docs` (Swagger UI).

---

## Project Structure

```
DIH-X-AUC-Hackathon/
|
+-- FlowPOS/                          # Main production platform
|   +-- apps/web/                     # Next.js 15 POS frontend
|   |   +-- src/
|   |   |   +-- app/                  # 33 pages (App Router)
|   |   |   |   +-- dashboard/        # 17 dashboard pages including AI
|   |   |   |   +-- pos/              # POS terminal
|   |   |   |   +-- kitchen/          # Kitchen display
|   |   |   |   +-- (auth)/           # Login & PIN
|   |   |   |   +-- admin/            # Platform admin
|   |   |   +-- components/           # React components
|   |   |   |   +-- dashboard/        # Chat panel, AI widgets
|   |   |   |   +-- layout/           # Sidebar, header, dashboard layout
|   |   |   +-- server/               # tRPC routers (15 routers)
|   |   |   +-- store/                # Zustand stores (22 stores)
|   |   |   +-- lib/                  # Utilities, forecasting API client
|   |   |   +-- i18n/                 # English + Arabic translations
|   |   +-- next.config.ts            # API rewrites to forecasting backend
|   |
|   +-- services/forecasting/         # Python forecasting microservice
|   |   +-- src/
|   |   |   +-- api/                  # FastAPI routes (18 endpoints)
|   |   |   |   +-- chat_routes.py    # Chat, insights, simulation, prep-rec
|   |   |   |   +-- model_routes.py   # Forecast, train, features
|   |   |   |   +-- data_routes.py    # Inventory, sales, menu data
|   |   |   +-- models/               # ML models
|   |   |   |   +-- ensemble.py       # HybridForecaster, WasteOptimized
|   |   |   |   +-- xgboost_model.py  # XGBoost with 40 feature columns
|   |   |   |   +-- baseline.py       # Moving average baseline
|   |   |   |   +-- model_service.py  # .pkl model loading & inference
|   |   |   +-- features/             # Feature engineering pipeline
|   |   |   |   +-- builder.py        # Main feature builder
|   |   |   |   +-- time_features.py  # Temporal features
|   |   |   |   +-- lag_features.py   # Lag and rolling features
|   |   |   |   +-- external_features.py  # Weather, holidays
|   |   |   +-- llm/                  # LLM intelligence layer
|   |   |   |   +-- client.py         # OpenRouter client with tool-calling
|   |   |   |   +-- tools.py          # 10 function-calling tools
|   |   |   |   +-- context_signals.py # Weather, holidays, daylight, events
|   |   |   |   +-- prompts.py        # 7 specialized AI personas
|   |   |   |   +-- simulator.py      # What-if scenario engine
|   |   |   +-- inventory/            # Inventory optimization
|   |   |       +-- optimizer.py      # Reorder point calculations
|   |   |       +-- waste_analyzer.py # Waste pattern analysis
|   |   |       +-- promotion_engine.py # Dynamic promotion logic
|   |   +-- data/
|   |   |   +-- Inventory Management/ # CSV data files (19 tables)
|   |   |   +-- models/               # Trained .pkl model files
|   |   +-- run.py                    # Uvicorn launcher
|   |   +-- requirements.txt          # Python dependencies
|   |
|   +-- packages/                     # Shared monorepo packages
|       +-- db/                       # Supabase types & Prisma schema
|       +-- ui/                       # Shared UI components
|
+-- inventory-forecasting/            # ML model development & training
|   +-- src/
|   |   +-- models/                   # Model definitions and training
|   |   +-- features/                 # Feature engineering source
|   |   +-- inventory/                # Optimization algorithms
|   |   +-- data/                     # Data loading and cleaning
|   +-- scripts/                      # Training scripts
|
+-- data/models/                      # Trained model artifacts
|   +-- balanced_model.pkl            # HybridForecaster (30% XGB + 70% MA7)
|   +-- waste_optimized_model.pkl     # WasteOptimizedForecaster (85% shrink)
|
+-- notebooks/                        # Jupyter notebooks
|   +-- 01_eda.ipynb                  # Exploratory data analysis
|   +-- 02_feature_engineering.ipynb  # Feature development
|   +-- 03_model_training.ipynb       # Model training & evaluation
|
+-- docs/                             # Documentation
+-- config/                           # Configuration files
+-- tests/                            # Unit tests
```

---

## Model Performance

### Business-Cost Evaluation (93-day test, 101 stores, 1,976 items)

| Rank | Model | Total Cost (DKK) | Savings |
|------|-------|------------------|---------|
| 1 | MA7 + 20% safety buffer | 15.20M | 29.3% |
| **2** | **HybridForecaster (30% XGB + 70% MA7)** | **15.51M** | **27.8%** |
| 3 | 40% XGB + 60% MA7 | 15.52M | 27.8% |
| 4 | Pure MA7 | 16.44M | 23.5% |
| 22 | Pure XGBoost | 17.08M | 20.5% |
| 32 | MA28 (worst) | 21.49M | Baseline |

The HybridForecaster was selected as the primary model because it is the best **ML-enhanced** approach (XGBoost captures promotional effects and demand spikes that pure MA cannot), while the pure buffer approach (rank 1) has no learning capability.

### Key Metrics (HybridForecaster)

| Metric | Value |
|--------|-------|
| Forecast Accuracy (WMAPE) | 67.7% |
| Overstock Days | 33.6% |
| Understock Days | 28.3% |
| Balanced Days | 38.1% |
| Total Cost Reduction | 27.8% vs. worst baseline |

### With LLM Arbitration

The LLM selects waste-optimized predictions for perishable/volatile items on slow days, and stockout-optimized predictions for popular items on busy days. This context-aware per-item switching further reduces total business cost beyond using either model uniformly.

---

## Team

Built by the AUC team for the DIH x AUC Hackathon.
