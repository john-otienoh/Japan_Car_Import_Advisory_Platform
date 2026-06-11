# 🚗 KenyaDrive Intelligence — Japan Car Import Advisory Platform

> **A full-stack data engineering, machine learning, and web application platform that helps Kenyan car buyers estimate the true cost of importing vehicles from Japan versus buying locally.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18.x-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-1.5-F7931E?logo=scikit-learn&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📌 Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Tech Stack & Tooling Rationale](#3-tech-stack--tooling-rationale)
4. [GitHub Repository Structure](#4-github-repository-structure)
5. [5-Day × 15-Hour Project Roadmap](#5-5-day--15-hour-project-roadmap)
   - [Day 1 — Infrastructure & Data Extraction](#day-1--infrastructure--data-extraction-15-hrs)
   - [Day 2 — Data Pipeline & Cleaning](#day-2--data-pipeline--cleaning-15-hrs)
   - [Day 3 — ML Model Development](#day-3--ml-model-development-15-hrs)
   - [Day 4 — Backend API & Import Calculator](#day-4--backend-api--import-calculator-15-hrs)
   - [Day 5 — Frontend Dashboard & Deployment](#day-5--frontend-dashboard--deployment-15-hrs)
6. [KRA Import Cost Methodology](#6-kra-import-cost-methodology)
7. [ML Model Design](#7-ml-model-design)
8. [Database Schema](#8-database-schema)
9. [Local Development Setup](#9-local-development-setup)
10. [Environment Variables Reference](#10-environment-variables-reference)
11. [API Endpoints Reference](#11-api-endpoints-reference)
12. [Deliverables Checklist](#12-deliverables-checklist)
13. [Contributing](#13-contributing)
14. [License](#14-license)

---

## 1. Project Overview

**KenyaDrive Intelligence** solves a real and costly problem: Kenyan car buyers lack a single, data-driven platform to accurately assess whether importing a specific vehicle from Japan is cheaper than buying the same model locally, after accounting for every fee, tax, and levy that KRA, Kenya Ports Authority, and NTSA impose.</br>
This project demonstrates:

* Data Engineering
* Web Scraping
* ETL Pipelines
* Data Warehousing
* Machine Learning
* MLOps Fundamentals
* Analytics Engineering
* Dashboard Development
* Cloud Deployment
* Domain Knowledge in Automotive Imports

### Core Features

| Feature | Description |
|---|---|
| 🕷️ **Multi-source Scraper** | Extracts live listings from 3 Japanese export platforms (2018+ vehicles) |
| 🗄️ **Data Warehouse** | PostgreSQL + DuckDB analytical layer for structured, deduplicated car data |
| 🧹 **Cleaning Pipeline** | Pandas-based ETL with Great Expectations validation gates |
| 🔢 **KRA Calculator** | Programmatic implementation of Kenya's full vehicle import duty chain |
| 🤖 **Price Prediction ML** | XGBoost/LightGBM ensemble predicting JPY price from vehicle features |
| ⚖️ **Local Market Comparison** | Real-time comparison against Cheki Kenya / Cars45 Kenya listings |
| 📊 **React Dashboard** | Interactive, mobile-responsive UI with Recharts visualizations |
| 🐳 **Docker Deployment** | Single-command `docker compose up` for full stack |

### Target Platforms Scraped

| Platform | URL | Key Data |
|---|---|---|
| SBT Japan | sbtjapan.com | FOB price, mileage, grade, auction |
| BE FORWARD | beforward.jp | CIF price, stock status, location |
| Car From Japan | carfromjapan.com | Price, specs, dealer reviews |

> **Kenya Age Rule:** As of 2026, Kenya allows passenger vehicle imports up to **8 years old** (2018 onward). All scraper filters enforce this boundary.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        KENYADRIVE INTELLIGENCE                       │
│                        System Architecture                           │
└─────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │  DATA LAYER                                                       │
  │                                                                   │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
  │  │  SBT JP  │  │BE FORWARD│  │  CFJ /   │  │  JCT / AAAJapan  │ │
  │  │ Scrapy + │  │ Scrapy + │  │ AAAJapan │  │  Playwright      │ │
  │  │Playwright│  │Playwright│  │  Spider  │  │  Spider          │ │
  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘ │
  │       └─────────────┴──────────────┴─────────────────┘           │
  │                              │                                    │
  │                    ┌─────────▼──────────┐                        │
  │                    │  Scrapy Item        │                        │
  │                    │  Pipeline (raw)     │                        │
  │                    │  → PostgreSQL       │                        │
  │                    │    raw.listings     │                        │
  │                    └─────────┬──────────┘                        │
  └──────────────────────────────┼───────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────┐
  │  PIPELINE LAYER                                                   │
  │                                                                   │
  │  ┌────────────────────────────────────────────────────────────┐  │
  │  │  Prefect Flow (or APScheduler)                              │  │
  │  │                                                             │  │
  │  │  raw.listings → [dedupe] → [clean] → [validate] → [enrich] │  │
  │  │                                           ↓                 │  │
  │  │                                  curated.vehicles           │  │
  │  │                                  curated.prices             │  │
  │  │                                  curated.features           │  │
  │  └────────────────────────────────────────────────────────────┘  │
  │                         │                 │                       │
  │              ┌──────────▼──────┐  ┌──────▼────────┐             │
  │              │  DuckDB OLAP    │  │  Parquet store │             │
  │              │  (analytics)    │  │  (ML pipeline) │             │
  │              └─────────────────┘  └───────────────┘             │
  └──────────────────────────────────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────┐
  │  ML LAYER                                                         │
  │                                                                   │
  │  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌───────────────┐  │
  │  │  Feature │  │  XGBoost │  │  LightGBM  │  │  MLflow       │  │
  │  │  Eng.    │→ │  Regress.│  │  Regress.  │  │  Tracking     │  │
  │  │  Pipeline│  └────┬─────┘  └─────┬──────┘  └───────────────┘  │
  │  └──────────┘       └──────┬────────┘                            │
  │                     ┌──────▼──────┐  ┌───────────────────────┐  │
  │                     │  Ensemble   │  │  SHAP Explainability   │  │
  │                     │  Stacking   │  │  (feature importance)  │  │
  │                     └──────┬──────┘  └───────────────────────┘  │
  │                     ┌──────▼──────┐                              │
  │                     │  Serialized │  (joblib → /models/artifacts)│
  │                     │  Model      │                              │
  │                     └─────────────┘                              │
  └──────────────────────────────────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────┐
  │  API LAYER  (FastAPI)                                             │
  │                                                                   │
  │  /api/v1/                                                         │
  │    ├── cars/search          ← filtered listing search            │
  │    ├── cars/{id}            ← single listing detail              │
  │    ├── import/calculate     ← full KRA cost breakdown            │
  │    ├── predict/price        ← ML price prediction                │
  │    ├── compare/local        ← import vs local comparison         │
  │    ├── exchange/rates       ← live JPY→KES / USD→KES             │
  │    └── analytics/summary    ← dashboard aggregates               │
  │                                                                   │
  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐                   │
  │  │  Redis   │  │  Celery  │  │  PostgreSQL   │                   │
  │  │  Cache   │  │  Workers │  │  (primary DB) │                   │
  │  └──────────┘  └──────────┘  └──────────────┘                   │
  └──────────────────────────────────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────┐
  │  FRONTEND LAYER  (React 18 + TypeScript + Vite)                  │
  │                                                                   │
  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
  │  │  Car Search  │  │Import Cost   │  │  Market Comparison   │    │
  │  │  & Filter   │  │  Calculator  │  │  Dashboard           │    │
  │  └─────────────┘  └──────────────┘  └──────────────────────┘    │
  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
  │  │  ML Price   │  │  Exchange    │  │  Savings Estimator   │    │
  │  │  Predictor  │  │  Rate Widget │  │  Chart               │    │
  │  └─────────────┘  └──────────────┘  └──────────────────────┘    │
  └──────────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack & Tooling Rationale

### 3.1 Data Extraction

| Tool | Version | Role | Why |
|---|---|---|---|
| **Scrapy** | 2.11 | Core spider framework | Async crawling, middleware hooks, item pipelines |
| **Playwright** | 1.44 | JS-rendered page rendering | SBT Japan & JCT use React/SPAs |
| **scrapy-playwright** | 0.0.34 | Scrapy↔Playwright bridge | Unified spider interface |
| **BeautifulSoup4** | 4.12 | HTML parsing fallback | Lightweight for static sub-pages |
| **httpx** | 0.27 | Async HTTP client | Concurrent API calls for exchange rates |
| **fake-useragent** | 1.5 | UA rotation | Reduces bot detection fingerprint |
| **tenacity** | 8.3 | Retry logic | Exponential backoff on network failures |

### 3.2 Database & Storage

| Tool | Version | Role | Why |
|---|---|---|---|
| **PostgreSQL** | 16 | Primary relational store | ACID compliance, JSONB for raw data |
| **SQLAlchemy** | 2.0 | ORM + Core | Async sessions, type safety |
| **Alembic** | 1.13 | Schema migrations | Version-controlled DB state |
| **DuckDB** | 0.10 | OLAP analytics | Column-store queries over Parquet, zero-copy |
| **Redis** | 7.2 | Caching layer | TTL-based API response cache, Celery broker |
| **Parquet (pyarrow)** | 16.1 | ML data format | Columnar, compressed, pandas-native |

### 3.3 Data Processing & Cleaning

| Tool | Version | Role | Why |
|---|---|---|---|
| **Pandas** | 2.2 | Core data manipulation | Vectorized cleaning, group-bys |
| **NumPy** | 1.26 | Numerical ops | Array math, currency arithmetic |
| **Great Expectations** | 0.18 | Data validation | Expectation suites, data docs |
| **ydata-profiling** | 4.8 | EDA reports | Auto HTML profile reports per source |
| **Loguru** | 0.7 | Structured logging | JSON logs with context binding |

### 3.4 Machine Learning

| Tool | Version | Role | Why |
|---|---|---|---|
| **Scikit-learn** | 1.5 | Preprocessing + baselines | Pipeline API, StandardScaler, cross-val |
| **XGBoost** | 2.0 | Primary ensemble model | Best-in-class tabular regression |
| **LightGBM** | 4.4 | Secondary ensemble model | Faster training, handles categoricals natively |
| **Optuna** | 3.6 | Hyperparameter tuning | TPE sampler, pruning callbacks |
| **SHAP** | 0.45 | Explainability | Feature importance, waterfall plots |
| **MLflow** | 2.13 | Experiment tracking | Run logging, model registry |
| **joblib** | 1.4 | Model serialization | Persistent artifact storage |
| **Jupyter** | 7.2 | EDA notebooks | Interactive exploration |

### 3.5 Backend API

| Tool | Version | Role | Why |
|---|---|---|---|
| **FastAPI** | 0.111 | REST API framework | Async, auto-docs, Pydantic validation |
| **Pydantic** | 2.7 | Data schemas | Request/response models, field validators |
| **Uvicorn** | 0.29 | ASGI server | High-performance, compatible with Gunicorn |
| **Celery** | 5.4 | Task queue | Background scraping, async cost calc |
| **APScheduler** | 3.10 | Cron-style scheduling | Daily scraper refresh jobs |
| **python-jose** | 3.3 | JWT auth | Optional user session tokens |

### 3.6 Frontend

| Tool | Version | Role | Why |
|---|---|---|---|
| **React** | 18.3 | UI framework | Component model, concurrent mode |
| **TypeScript** | 5.5 | Type safety | Prevents API contract mismatches |
| **Vite** | 5.3 | Build tool | Sub-second HMR, ESM-native |
| **Tailwind CSS** | 3.4 | Utility-first CSS | Rapid, consistent styling |
| **shadcn/ui** | latest | Component library | Accessible, headless, Tailwind-based |
| **Recharts** | 2.12 | Charts | Composable React chart components |
| **TanStack Query** | 5.x | Server state | Cache, refetch, loading/error states |
| **React Hook Form** | 7.52 | Form management | Performant, schema-validated forms |
| **Zod** | 3.23 | Frontend validation | Matches Pydantic schemas end-to-end |
| **Zustand** | 4.5 | Global state | Lightweight, hooks-based |
| **Axios** | 1.7 | HTTP client | Interceptors, typed responses |

### 3.7 DevOps & Infrastructure

| Tool | Version | Role | Why |
|---|---|---|---|
| **Docker** | 26 | Containerization | Reproducible environments |
| **Docker Compose** | 2.27 | Orchestration | Single-command full-stack spin-up |
| **GitHub Actions** | — | CI/CD pipeline | Lint, test, build, deploy on push |
| **Railway** | — | Cloud deployment | PaaS with PostgreSQL, Redis add-ons |
| **pytest** | 8.2 | Testing framework | Unit + integration tests |
| **Ruff** | 0.4 | Python linter/formatter | 100× faster than flake8 |
| **pre-commit** | 3.7 | Git hooks | Enforce lint before commit |

---

## 4. GitHub Repository Structure

```
kenyadrive-intelligence/
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                  # Lint, test, typecheck
│   │   ├── deploy.yml              # Railway deployment on main push
│   │   └── scraper-schedule.yml    # Daily scraper cron trigger
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
│
├── scrapers/                       # Scrapy project root
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── settings.py             # Scrapy global settings
│   │   ├── items.py                # CarListing Item schema
│   │   ├── middlewares.py          # Playwright, UA rotation, proxy
│   │   ├── pipelines.py            # Validation → Dedup → PostgreSQL
│   │   └── spiders/
│   │       ├── base_spider.py      # Shared BaseCar spider class
│   │       ├── sbt_japan.py        # SBT Japan spider
│   │       ├── be_forward.py       # BE FORWARD spider
│   │       ├── car_from_japan.py   # Car From Japan spider
│   │       ├── aaa_japan.py        # AAAJapan spider
│   │       └── jct.py              # JapanesCarTrade spider
│   └── scrapy.cfg
│
├── pipeline/                       # Data cleaning & transformation
│   ├── __init__.py
│   ├── run_pipeline.py             # Entry point: raw → curated
│   ├── cleaning/
│   │   ├── __init__.py
│   │   ├── deduplicator.py         # Cross-platform dedup by VIN / hash
│   │   ├── normalizer.py           # Price units, mileage, fuel types
│   │   ├── currency.py             # JPY → KES / USD → KES conversion
│   │   └── imputer.py              # Missing value strategies
│   ├── transformation/
│   │   ├── __init__.py
│   │   ├── feature_builder.py      # Engineered features for ML
│   │   └── exporter.py             # Parquet + DuckDB export
│   └── validation/
│       ├── __init__.py
│       ├── expectations/           # Great Expectations suites (JSON)
│       └── validator.py            # Run suites, gate on failures
│
├── models/                         # ML model code
│   ├── __init__.py
│   ├── train.py                    # Main training script (CLI)
│   ├── predict.py                  # Inference wrapper
│   ├── features.py                 # Feature engineering (sklearn Pipeline)
│   ├── evaluation.py               # Cross-val, metrics, SHAP
│   ├── tuning.py                   # Optuna hyperparameter search
│   └── artifacts/                  # Serialized models (gitignored > 50MB)
│       ├── .gitkeep
│       └── model_registry.json     # Points to latest model metadata
│
├── api/                            # FastAPI application
│   ├── __init__.py
│   ├── main.py                     # App factory, lifespan events
│   ├── config.py                   # Settings (pydantic BaseSettings)
│   ├── deps.py                     # Shared DB / Redis dependencies
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── cars.py                 # /cars/* endpoints
│   │   ├── import_cost.py          # /import/calculate
│   │   ├── prediction.py           # /predict/price
│   │   ├── comparison.py           # /compare/local
│   │   └── analytics.py            # /analytics/summary
│   ├── services/
│   │   ├── __init__.py
│   │   ├── kra_calculator.py       # Full KRA duty chain logic
│   │   ├── shipping_estimator.py   # Freight + insurance estimation
│   │   ├── local_market.py         # Cheki/Cars45 comparison scraper
│   │   ├── exchange_service.py     # ExchangeRate-API integration
│   │   └── ml_service.py           # Load model + serve predictions
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── car.py
│   │   ├── import_cost.py
│   │   ├── prediction.py
│   │   └── comparison.py
│   └── tasks/
│       ├── __init__.py
│       └── scraper_tasks.py        # Celery task wrappers
│
├── frontend/                       # React + TypeScript + Vite
│   ├── public/
│   │   └── favicon.ico
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/                    # Axios client + typed hooks
│   │   │   ├── client.ts
│   │   │   ├── cars.ts
│   │   │   ├── importCost.ts
│   │   │   └── prediction.ts
│   │   ├── components/
│   │   │   ├── ui/                 # shadcn re-exports
│   │   │   ├── CarCard.tsx
│   │   │   ├── CostBreakdown.tsx
│   │   │   ├── ImportCalculator.tsx
│   │   │   ├── PricePredictor.tsx
│   │   │   ├── ComparisonChart.tsx
│   │   │   ├── SavingsBadge.tsx
│   │   │   └── ExchangeRateTicker.tsx
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── Search.tsx
│   │   │   ├── Calculator.tsx
│   │   │   ├── Predictor.tsx
│   │   │   └── Analytics.tsx
│   │   ├── store/
│   │   │   └── useAppStore.ts      # Zustand global state
│   │   ├── types/
│   │   │   └── index.ts            # TypeScript interfaces (mirrors Pydantic)
│   │   └── utils/
│   │       ├── formatters.ts       # KES/JPY formatting
│   │       └── constants.ts
│   ├── index.html
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── package.json
│
├── db/                             # Database migrations & seeds
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       ├── 0001_init_schema.py
│   │       ├── 0002_add_curated_tables.py
│   │       └── 0003_add_local_market.py
│   └── seeds/
│       └── seed_exchange_rates.py
│
├── notebooks/                      # Jupyter EDA & experiments
│   ├── 01_raw_data_audit.ipynb
│   ├── 02_cleaning_exploration.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_baseline.ipynb
│   ├── 05_xgboost_tuning.ipynb
│   └── 06_shap_analysis.ipynb
│
├── tests/
│   ├── unit/
│   │   ├── test_kra_calculator.py
│   │   ├── test_normalizer.py
│   │   └── test_deduplicator.py
│   ├── integration/
│   │   ├── test_api_cars.py
│   │   ├── test_api_import_cost.py
│   │   └── test_api_prediction.py
│   └── conftest.py
│
├── docs/
│   ├── architecture.md
│   ├── kra_tax_methodology.md
│   ├── ml_model_card.md
│   ├── api_reference.md
│   └── deployment_guide.md
│
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.scraper
│   └── Dockerfile.frontend
│
├── docker-compose.yml              # Full local stack
├── docker-compose.prod.yml         # Production overrides
├── .env.example                    # Template env file
├── pyproject.toml                  # Python deps (Poetry or uv)
├── .pre-commit-config.yaml
├── .gitignore
├── LICENSE
└── README.md                       ← YOU ARE HERE
```

---

## 5. 5-Day × 15-Hour Project Roadmap

> **Total hours:** 75 hrs | **Output:** Production-grade, portfolio-deployable platform
>
> Legend: 🔴 Critical path  🟡 High value  🟢 Enhancement

---

### Day 1 — Infrastructure & Data Extraction (15 hrs)

**Goal:** Scaffolded repo + live data flowing into PostgreSQL from ≥ 3 sources

| Hour(s) | Deliverable | Tools & Commands | Priority |
|---|---|---|---|
| **1–2** | Repo init, Python env (uv), Docker Compose skeleton (`postgres`, `redis`, `pgadmin`), pre-commit hooks | `uv init`, `docker compose up -d postgres redis`, `pre-commit install` | 🔴 |
| **3** | PostgreSQL schema v1: `raw.listings` table (JSONB `raw_data` + typed columns). Alembic `0001_init_schema.py` | `SQLAlchemy`, `Alembic`, `psycopg2` | 🔴 |
| **4** | Scrapy project init, `items.py` CarListing schema, `settings.py` (Playwright download delay, cookies) | `scrapy startproject scrapers`, `scrapy-playwright` | 🔴 |
| **5–6** | **SBT Japan spider** — paginated search (`/stock/`), Playwright for JS-render, extract: make, model, year, mileage, engine cc, price (JPY), grade, fuel, transmission | `SBT Japan spider`, `Playwright`, `BeautifulSoup4` | 🔴 |
| **7–8** | **BE FORWARD spider** — REST-like paginated listing pages, CIF price extraction, stock number, body type, colour, location | `BE FORWARD spider`, `httpx`, `lxml` | 🔴 |
| **9** | **Car From Japan spider** — search results + detail pages, dealer name, inspection score | `CFJ spider`, `scrapy.Request` callback chaining | 🟡 |
| **10** | **AAAJapan spider** — auction data, grade (4, 4.5, R), odometer, model code | `AAAJapan spider`, `Playwright` | 🟡 |
| **11** | **JCT spider** — paginated listings, regional depot, freight estimate field | `JCT spider`, `fake-useragent`, `tenacity` retry | 🟡 |
| **12–13** | **Scrapy Item Pipeline** — field validation → normalize price to float → dedup check (hash of make+model+year+mileage+source) → PostgreSQL `INSERT ON CONFLICT DO NOTHING` | `scrapers/pipelines.py`, `psycopg2` bulk insert | 🔴 |
| **14** | APScheduler job: trigger all spiders daily at 02:00 EAT, write last-run status to `scraper_runs` table | `APScheduler`, `Celery beat` alternative | 🟡 |
| **15** | Run all spiders, verify ≥ 500 raw records ingested. Write `notebooks/01_raw_data_audit.ipynb` — row counts per source, null rates, price range | `ydata-profiling`, `DuckDB` | 🔴 |

**Day 1 Exit Criteria:** `raw.listings` has ≥ 500 real records from ≥ 3 platforms. All spiders run headlessly in Docker.

---

### Day 2 — Data Pipeline & Cleaning (15 hrs)

**Goal:** `curated.vehicles` table with clean, standardised, enriched car features ready for ML

| Hour(s) | Deliverable | Tools & Commands | Priority |
|---|---|---|---|
| **1–2** | **Deduplication engine** (`pipeline/cleaning/deduplicator.py`) — cross-platform merge on (make, model, year, mileage ±5%, engine_cc). Mark duplicates, keep record with richest attribute coverage | `pandas`, `fuzzywuzzy` / `thefuzz` for model name fuzzy match | 🔴 |
| **3** | **Currency normalisation** (`currency.py`) — fetch live JPY/KES and USD/KES from ExchangeRate-API, cache in Redis (TTL 3600s), convert all prices to KES and USD simultaneously | `httpx`, `Redis`, `python-dotenv` | 🔴 |
| **4–5** | **Field normaliser** (`normalizer.py`) — standardise: fuel_type (petrol/diesel/hybrid/EV), transmission (auto/manual/CVT), body_type (sedan/SUV/hatchback/pickup), make (Toyota/Nissan/Honda canonical forms), mileage to km | `pandas`, `re`, mapping dicts | 🔴 |
| **6** | **Imputer** (`imputer.py`) — engine_cc: KNN impute from (make, model, year); colour: "Unknown"; grade: median per source; mileage: flag outliers (>300,000 km) for review | `sklearn.impute.KNNImputer` | 🟡 |
| **7** | **Age calculation** — `vehicle_age_years = 2026 - year_of_manufacture`. Flag any > 8 yrs (outside KRA import eligibility) | `pandas`, `datetime` | 🔴 |
| **8** | **Feature engineering** (`feature_builder.py`) — `price_per_km`, `engine_cc_band` (bins), `mileage_band`, `is_hybrid`, `is_popular_make` (Toyota/Nissan/Honda/Mazda/Suzuki/Mitsubishi flag) | `pandas`, `numpy` | 🟡 |
| **9** | **Alembic migration `0002`** — `curated.vehicles` + `curated.prices` tables with FK to `raw.listings.id` | `Alembic`, `SQLAlchemy` | 🔴 |
| **10** | Run cleaning pipeline end-to-end, insert into `curated.vehicles`. Print summary stats. | `pipeline/run_pipeline.py` | 🔴 |
| **11** | **Great Expectations validation suite** — expectations: price > 0, year ∈ [2018, 2026], mileage ≥ 0, fuel_type ∈ enum, no nulls in primary features. Gate: fail pipeline if > 5% records violate. | `great_expectations`, `ge.dataset.PandasDataset` | 🟡 |
| **12** | Export cleaned data to `data/cleaned/vehicles_clean.parquet` (pyarrow) and `data/exports/vehicles_clean.csv` | `pandas.to_parquet`, `pyarrow` | 🔴 |
| **13** | **EDA notebook `02_cleaning_exploration.ipynb`** — price distribution per make, histogram of mileage, correlation heatmap, top 20 models by listing count | `matplotlib`, `seaborn`, `DuckDB` queries | 🟡 |
| **14** | **Local market scraper stub** (`api/services/local_market.py`) — scrape Cheki Kenya `/used-cars/` for make/model/year/price to build `local_market.listings` table | `httpx`, `BeautifulSoup4` | 🟡 |
| **15** | Review data quality. Document cleaning decisions in `docs/architecture.md`. Update README data pipeline section. | Markdown | 🟡 |

**Day 2 Exit Criteria:** `curated.vehicles` has ≥ 400 clean records. Parquet export ≤ 50 MB. GE validation passes with < 2% violations.

---

### Day 3 — ML Model Development (15 hrs)

**Goal:** Serialised XGBoost model with < 15% MAPE, tracked in MLflow, serving via prediction endpoint

| Hour(s) | Deliverable | Tools & Commands | Priority |
|---|---|---|---|
| **1–2** | **EDA notebook `03_feature_engineering.ipynb`** — target distribution (log-price), VIF for multicollinearity, missing pattern matrix. Decide log-transform on price. | `seaborn`, `scipy.stats`, `statsmodels` VIF | 🔴 |
| **3** | **Feature engineering sklearn Pipeline** (`models/features.py`) — `ColumnTransformer`: OrdinalEncoder (make, model, fuel_type, transmission, body_type, source_platform), StandardScaler (mileage, engine_cc, vehicle_age), PassThrough (boolean flags) | `sklearn.pipeline.Pipeline`, `ColumnTransformer` | 🔴 |
| **4** | **Baseline models** (`04_model_baseline.ipynb`) — LinearRegression, Ridge, DecisionTreeRegressor. Log to MLflow. Establish RMSE/MAE/MAPE baseline. | `sklearn`, `MLflow` | 🔴 |
| **5–6** | **XGBoost model** — `XGBRegressor(objective='reg:squarederror', n_estimators=500, early_stopping_rounds=50)`. Train/val split 80/20 stratified by `source_platform`. | `xgboost`, `MLflow.sklearn.autolog()` | 🔴 |
| **7** | **LightGBM model** — `LGBMRegressor(num_leaves=63, learning_rate=0.05)`. Native categorical handling for make/model/fuel columns. | `lightgbm`, `MLflow` | 🟡 |
| **8–9** | **Optuna hyperparameter tuning** (`models/tuning.py`) — 100-trial TPE study for XGBoost: `max_depth` [3–12], `learning_rate` [0.01–0.3], `subsample` [0.5–1.0], `colsample_bytree` [0.5–1.0], `min_child_weight` [1–10]. Prune unpromising trials. | `optuna`, `optuna-integration-xgboost`, `optuna.visualization` | 🔴 |
| **10** | **Model evaluation** (`models/evaluation.py`) — 5-fold cross-validation, report R², RMSE, MAE, MAPE. Residual plots. Prediction interval calibration check. | `sklearn.model_selection`, `matplotlib` | 🔴 |
| **11** | **SHAP explainability** (`06_shap_analysis.ipynb`) — `shap.TreeExplainer` on best model. Global feature importance bar chart. Waterfall plot for a sample Toyota Harrier. | `shap`, `matplotlib` | 🟡 |
| **12** | **Stacking ensemble** — `StackingRegressor([xgb, lgbm], final_estimator=RidgeCV())`. Compare to individual models. | `sklearn.ensemble.StackingRegressor` | 🟢 |
| **13** | **Serialise best model** — `joblib.dump(pipeline, 'models/artifacts/price_model_v1.joblib')`. Save feature names list, scaler params, SHAP explainer. Write `model_registry.json`. | `joblib`, `json` | 🔴 |
| **14** | **ML inference service** (`api/services/ml_service.py`) — load model on startup (lifespan event), `predict_price(features: dict) → float` with input validation | `FastAPI lifespan`, `joblib.load` | 🔴 |
| **15** | **MLflow Model Card** (`docs/ml_model_card.md`) — intended use, training data description, metrics, limitations, bias analysis (is model less accurate for rare makes?). | Markdown | 🟡 |

**Day 3 Exit Criteria:** Best model MAPE < 15% on holdout set. Model serialised and loadable in < 2s. MLflow UI shows ≥ 3 tracked experiments.

---

### Day 4 — Backend API & Import Calculator (15 hrs)

**Goal:** Full FastAPI backend with KRA cost engine, local market comparison, and all endpoints tested

| Hour(s) | Deliverable | Tools & Commands | Priority |
|---|---|---|---|
| **1–2** | **FastAPI app factory** (`api/main.py`) — lifespan (load model, connect DB, init Redis), CORS config, health endpoint, Prometheus metrics middleware, versioned router `/api/v1/` | `FastAPI`, `contextlib.asynccontextmanager`, `prometheus-fastapi-instrumentator` | 🔴 |
| **3** | **Pydantic schemas** (`api/schemas/`) — `CarListing`, `ImportCostRequest`, `ImportCostResponse`, `PredictionRequest`, `ComparisonResult`. Mirror TypeScript `types/index.ts` | `pydantic.BaseModel`, `Field`, `validator` | 🔴 |
| **4–6** | **KRA Tax Calculator** (`api/services/kra_calculator.py`) — implement full duty chain (see §6 below). Inputs: CIF value (KES), engine_cc, year. Outputs: itemised breakdown dict with line totals and grand total. Validated against [KRA iTax tables](https://www.kra.go.ke). | `Python dataclasses`, `decimal.Decimal` (monetary precision) | 🔴 |
| **7** | **Shipping estimator** (`api/services/shipping_estimator.py`) — parametric model: `shipping_cost = base_freight[region] + volume_factor * CBM + insurance_rate * FOB`. Regions: Osaka/Nagoya/Tokyo → Mombasa. Freight reference data from Shipmens.com. | `Python`, `math` | 🔴 |
| **8** | **Port + clearing fees** — KPA handling charges (per CBM), ICD Nairobi transit, clearing agent fee (KES 30,000–60,000 typical), pre-shipment inspection (PVOC/KEBS: KES 15,000). Expose as config constants with override option. | `api/config.py`, Pydantic `BaseSettings` | 🟡 |
| **9** | **Registration cost engine** — NTSA transfer: KES 7,500. Number plates: KES 3,000. Comprehensive insurance year 1 estimate (2.5% of market value). | `api/services/kra_calculator.py` (addendum) | 🟡 |
| **10** | **`/import/calculate` endpoint** — accepts `ImportCostRequest` (make, model, year, engine_cc, fob_price_jpy, source_platform), returns `ImportCostResponse` with each fee line item, subtotals, grand total in KES and USD. | `api/routes/import_cost.py` | 🔴 |
| **11** | **Local market comparison service** (`api/services/local_market.py`) — query `local_market.listings` for same make/model/year within ±1 year. Return median local price, listing count, price range. | `SQLAlchemy`, `statistics.median` | 🔴 |
| **12** | **`/compare/local` endpoint** — takes import cost result + local market data, computes `savings = local_median - import_total`, `savings_pct`, `verdict` (IMPORT/LOCAL/BREAK_EVEN). | `api/routes/comparison.py` | 🔴 |
| **13** | **`/predict/price` + `/cars/search` endpoints** — ML prediction with SHAP explanation (top 3 feature contributions). Car search with filters: make, model, year range, price range, fuel, source, page/limit. Redis cache with 30-minute TTL. | `api/routes/prediction.py`, `api/routes/cars.py`, `redis.asyncio` | 🔴 |
| **14** | **Exchange rate endpoint** (`/exchange/rates`) + **analytics summary** (`/analytics/summary`) — average import cost by make, popular models, price trend by year | `api/routes/analytics.py`, `DuckDB` aggregate queries | 🟡 |
| **15** | **API tests** (`tests/integration/`) — pytest + `httpx.AsyncClient` for import_cost happy path, KRA calculation accuracy (test against known vehicle: 2021 Toyota RAV4 2.5L). Test ML endpoint response shape. | `pytest`, `pytest-asyncio`, `httpx` | 🔴 |

**Day 4 Exit Criteria:** All 8 API endpoints return 200 with correct schema. KRA calculator verified against ≥ 3 known import scenarios. pytest suite: ≥ 20 tests, ≥ 80% pass rate.

---

### Day 5 — Frontend Dashboard & Deployment (15 hrs)

**Goal:** Deployed, mobile-responsive full-stack application live on Railway with CI/CD pipeline

| Hour(s) | Deliverable | Tools & Commands | Priority |
|---|---|---|---|
| **1** | **Vite + React + TS scaffold** — `npm create vite@latest frontend -- --template react-ts`. Install Tailwind, shadcn/ui init, configure `vite.config.ts` proxy to FastAPI dev server. | `npm`, `tailwindcss`, `shadcn-ui init` | 🔴 |
| **2** | **Typed API client** (`src/api/`) — Axios instance with base URL, auth interceptor, typed response wrappers. TanStack Query hooks: `useCars`, `useImportCost`, `usePrediction`, `useComparison`. | `axios`, `@tanstack/react-query` | 🔴 |
| **3** | **`<CarCard />`** — listing thumbnail (fallback placeholder), make/model/year badge, mileage, price in KES (formatted), source platform pill, "Calculate Import Cost" CTA button | `shadcn/ui Card`, `Badge`, `Button` | 🔴 |
| **4–5** | **`<ImportCalculator />`** — stepper form (React Hook Form + Zod): Step 1: select car (search autocomplete or manual entry); Step 2: shipping options (select port region); Step 3: animated cost breakdown table showing each KRA line item with tooltips explaining each fee. | `react-hook-form`, `zod`, `shadcn/ui Stepper`, `framer-motion` fade-in | 🔴 |
| **6** | **`<CostBreakdown />`** — Recharts `BarChart` stacked bars: Purchase (FOB), Freight, IDF, Import Duty, Excise Duty, VAT, RDL, Port Charges, Clearing, Registration. Each bar colour-coded by category. | `recharts`, `ResponsiveContainer` | 🔴 |
| **7** | **`<ComparisonChart />`** — dual `BarChart`: Import Total vs Local Market Median. Savings badge: green if import cheaper, amber if break-even (±10%), red if local cheaper. Verdict card with brief plain-English explanation. | `recharts`, `shadcn/ui Badge`, `cn()` conditional styling | 🔴 |
| **8** | **`<PricePredictor />`** — form with dropdowns (make, model, year, engine_cc, mileage, fuel, transmission, body, source). On submit: spinner → display predicted FOB price in JPY + KES + SHAP top-3 factors chip list. | `shadcn/ui Select`, `react-hook-form`, `axios` | 🟡 |
| **9** | **`<ExchangeRateTicker />`** — small sticky banner: JPY/KES and USD/KES rates with last-updated timestamp. Refetches every 5 min via TanStack Query `refetchInterval`. | `TanStack Query`, `Intl.NumberFormat` | 🟡 |
| **10** | **Analytics page** — 4 Recharts panels: (1) Average import cost by make, (2) Listings by source platform donut, (3) Price trend line by year of manufacture, (4) Top 10 most-listed models table with average savings. | `recharts LineChart PieChart`, `shadcn/ui Table` | 🟡 |
| **11** | **Responsive polish** — mobile breakpoints (`sm:`, `md:`), drawer menu on mobile, `useMediaQuery` hook, `<Skeleton />` loading states, empty states per page, `<ErrorBoundary />`. | `tailwind responsive`, `shadcn/ui Skeleton`, `react-error-boundary` | 🟡 |
| **12** | **Docker production build** — `Dockerfile.api` (multi-stage, Uvicorn + Gunicorn), `Dockerfile.frontend` (Vite build → nginx:alpine), `docker-compose.prod.yml`. Test `docker compose -f docker-compose.prod.yml up` locally. | `Docker multi-stage`, `nginx.conf` | 🔴 |
| **13** | **GitHub Actions CI** (`.github/workflows/ci.yml`) — on PR: Ruff lint, pytest (unit), TypeScript `tsc --noEmit`, Vite build check. On push to `main`: build and push Docker images, deploy to Railway via `railway up`. | `GitHub Actions`, `railway CLI` | 🔴 |
| **14** | **Final documentation** — `docs/deployment_guide.md` (Railway setup, env vars, DB migrations on deploy), update README with live demo URL, screenshots, and badges | Markdown, `railway add postgres redis` | 🟡 |
| **15** | **Portfolio wrap-up** — record a 3-min Loom demo video (scraper → cleaned data → calculator → comparison). Write a LinkedIn project post. Tag `v1.0.0` in git. | `git tag`, Loom | 🟢 |

**Day 5 Exit Criteria:** Live URL accessible. All 5 pages functional. Docker Compose starts clean in < 60s. CI pipeline green on `main`.

---

## 6. KRA Import Cost Methodology

This section documents the exact calculation logic implemented in `api/services/kra_calculator.py`.

### 6.1 Input Variables

```python
fob_price_kes: float      # Purchase price (FOB) in KES
freight_kes: float         # Estimated ocean freight KES (see shipping_estimator)
insurance_kes: float       # = 0.5% of FOB (marine insurance standard)
engine_cc: int             # Engine displacement in cubic centimetres
year_of_manufacture: int   # Vehicle year
```

### 6.2 CIF Value

```
CIF = FOB + Freight + Insurance
```

> CIF (Cost, Insurance, Freight) is the customs value base for all KRA duty calculations.

### 6.3 Import Declaration Fee (IDF)

```
IDF = max(3.5% × CIF, KES 5,000)
```

### 6.4 Railway Development Levy (RDL)

```
RDL = 2.0% × CIF
```

### 6.5 Import Duty (Customs Duty)

Passenger vehicles attract **25% import duty** on CIF value.

```
Import Duty = 25% × CIF
```

### 6.6 Excise Duty

Based on engine displacement (EAC Excise Duty schedule):

| Engine CC | Rate |
|---|---|
| ≤ 1,000 cc | 0% |
| 1,001 – 2,000 cc | 20% |
| 2,001 – 3,000 cc | 30% |
| > 3,000 cc | 35% |

```
Excise Duty = rate × (CIF + Import Duty)
```

### 6.7 Value Added Tax (VAT)

```
VAT Base = CIF + Import Duty + Excise Duty
VAT = 16% × VAT Base
```

### 6.8 Port Charges (KPA — Kenya Ports Authority)

| Charge | Estimate |
|---|---|
| Handling (per CBM) | KES 3,200/CBM (~14 CBM for sedan) |
| Storage (if > 7 days) | KES 5,000/day |
| Terminal charges | KES 25,000 flat |

### 6.9 Clearing & Forwarding Fees

| Fee | Estimate |
|---|---|
| Clearing agent | KES 30,000 – KES 60,000 |
| Road transport (Mombasa → Nairobi) | KES 18,000 – KES 35,000 |
| KEBS/PVOC Pre-shipment Inspection | KES 15,000 |

### 6.10 Registration & Compliance

| Fee | Amount |
|---|---|
| NTSA Transfer / First Registration | KES 7,500 |
| Number plates | KES 3,000 |
| Comprehensive Insurance (Year 1 est.) | 2.5% of market value |

### 6.11 Grand Total Formula

```
Grand Total (KES) = 
  FOB
  + Freight
  + Insurance
  + IDF
  + RDL
  + Import Duty
  + Excise Duty
  + VAT
  + Port Charges
  + Clearing & Forwarding
  + KEBS Inspection
  + NTSA Registration
  + Number Plates
```

### 6.12 Sample Calculation

**Vehicle:** 2021 Toyota Harrier, 2.0L petrol, FOB ¥2,500,000 (≈ KES 2,100,000 at ¥1 = KES 0.84)

| Line Item | KES |
|---|---|
| FOB Price | 2,100,000 |
| Freight (Osaka → Mombasa) | 195,000 |
| Insurance (0.5% FOB) | 10,500 |
| **CIF Total** | **2,305,500** |
| IDF (3.5% × CIF) | 80,693 |
| RDL (2% × CIF) | 46,110 |
| Import Duty (25% × CIF) | 576,375 |
| Excise Duty (20% × CIF+Duty) | 576,375 |
| VAT (16% × cumulative) | 552,680 |
| Port Charges (est.) | 70,000 |
| Clearing & Forwarding | 45,000 |
| KEBS Inspection | 15,000 |
| NTSA Registration | 7,500 |
| Number Plates | 3,000 |
| **GRAND TOTAL** | **≈ KES 4,328,233** |

---

## 7. ML Model Design

### 7.1 Target Variable
`log_price_jpy` — natural log of FOB price in JPY. Log-transform reduces right skew and improves linear model fit. Predictions are exponentiated back to JPY on serving.

### 7.2 Feature Set

| Feature | Type | Engineering |
|---|---|---|
| `make` | Categorical | OrdinalEncoder (frequency-sorted) |
| `model` | Categorical | OrdinalEncoder (frequency-sorted) |
| `year_of_manufacture` | Numeric | PassThrough |
| `vehicle_age_years` | Numeric | `= 2026 - year` |
| `mileage_km` | Numeric | StandardScaler |
| `engine_cc` | Numeric | StandardScaler |
| `fuel_type` | Categorical | OrdinalEncoder |
| `transmission` | Categorical | OrdinalEncoder |
| `body_type` | Categorical | OrdinalEncoder |
| `source_platform` | Categorical | OrdinalEncoder |
| `is_hybrid` | Boolean | PassThrough |
| `is_popular_make` | Boolean | `True` for top-6 Japanese makes |
| `mileage_band` | Categorical | `pd.cut` bins: 0-50k, 50-100k, 100-150k, 150k+ |
| `engine_cc_band` | Categorical | ≤1000, 1001-2000, 2001-3000, >3000 |

### 7.3 Evaluation Metrics

| Metric | Target |
|---|---|
| MAPE | < 15% |
| R² | > 0.82 |
| RMSE (log space) | < 0.25 |

### 7.4 Model Inference API Contract

**Request:**
```json
{
  "make": "Toyota",
  "model": "Harrier",
  "year_of_manufacture": 2021,
  "mileage_km": 45000,
  "engine_cc": 2000,
  "fuel_type": "Petrol",
  "transmission": "Automatic",
  "body_type": "SUV",
  "source_platform": "SBT Japan"
}
```

**Response:**
```json
{
  "predicted_fob_jpy": 2750000,
  "predicted_fob_kes": 2310000,
  "confidence_interval_jpy": [2400000, 3100000],
  "shap_top_factors": [
    {"feature": "model", "impact": "+¥340,000", "direction": "positive"},
    {"feature": "vehicle_age_years", "impact": "-¥180,000", "direction": "negative"},
    {"feature": "mileage_km", "impact": "-¥95,000", "direction": "negative"}
  ],
  "model_version": "v1.2.0",
  "inference_time_ms": 12
}
```

---

## 8. Database Schema

```sql
-- Raw ingested listings (schema: raw)
CREATE TABLE raw.listings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_platform VARCHAR(50)  NOT NULL,
    source_url      TEXT         UNIQUE,
    raw_data        JSONB        NOT NULL,  -- full scraped payload
    scraped_at      TIMESTAMPTZ  DEFAULT NOW(),
    is_processed    BOOLEAN      DEFAULT FALSE
);
CREATE INDEX idx_raw_source ON raw.listings(source_platform);
CREATE INDEX idx_raw_processed ON raw.listings(is_processed);

-- Curated clean vehicles (schema: curated)
CREATE TABLE curated.vehicles (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id               UUID REFERENCES raw.listings(id),
    source_platform      VARCHAR(50)  NOT NULL,
    make                 VARCHAR(80)  NOT NULL,
    model                VARCHAR(100) NOT NULL,
    year_of_manufacture  SMALLINT     NOT NULL CHECK (year_of_manufacture >= 2018),
    mileage_km           INTEGER      CHECK (mileage_km >= 0),
    engine_cc            SMALLINT,
    fuel_type            VARCHAR(30),
    transmission         VARCHAR(20),
    body_type            VARCHAR(30),
    colour               VARCHAR(30),
    auction_grade        VARCHAR(10),
    fob_price_jpy        NUMERIC(12,2),
    fob_price_kes        NUMERIC(14,2),
    fob_price_usd        NUMERIC(10,2),
    currency_date        DATE,
    is_hybrid            BOOLEAN DEFAULT FALSE,
    is_duplicate         BOOLEAN DEFAULT FALSE,
    canonical_id         UUID,            -- points to primary record if duplicate
    vehicle_age_years    SMALLINT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Local Kenyan market prices (schema: local_market)
CREATE TABLE local_market.listings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_platform     VARCHAR(50),
    make                VARCHAR(80),
    model               VARCHAR(100),
    year_of_manufacture SMALLINT,
    mileage_km          INTEGER,
    asking_price_kes    NUMERIC(14,2),
    is_imported         BOOLEAN,
    scraped_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Exchange rate snapshots
CREATE TABLE reference.exchange_rates (
    id              SERIAL PRIMARY KEY,
    from_currency   CHAR(3) NOT NULL,
    to_currency     CHAR(3) NOT NULL,
    rate            NUMERIC(16,6) NOT NULL,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 9. Local Development Setup

### Prerequisites

- Docker Desktop ≥ 26 (with Compose v2)
- Python 3.11+
- Node.js 20 LTS
- `uv` (Python package manager) — `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 1. Clone and configure

```bash
git clone https://github.com/<your-org>/kenyadrive-intelligence.git
cd kenyadrive-intelligence
cp .env.example .env
# Edit .env — add your ExchangeRate-API key (free tier: 1,500 req/month)
```

### 2. Start infrastructure

```bash
docker compose up -d postgres redis pgadmin
# pgAdmin available at http://localhost:5050
# postgres on localhost:5432
# redis on localhost:6379
```

### 3. Python backend

```bash
uv venv && source .venv/bin/activate
uv sync                          # installs all deps from pyproject.toml
alembic upgrade head             # run all DB migrations
python pipeline/run_pipeline.py  # run cleaning pipeline (requires raw data)
uvicorn api.main:app --reload    # API at http://localhost:8000/docs
```

### 4. Run scrapers

```bash
cd scrapers
# Run individual spider
scrapy crawl sbt_japan -s CLOSESPIDER_ITEMCOUNT=100
# Run all spiders sequentially
scrapy crawl be_forward & scrapy crawl car_from_japan & wait
```

### 5. Train ML model

```bash
python models/train.py \
  --data data/cleaned/vehicles_clean.parquet \
  --model-output models/artifacts/price_model_v1.joblib \
  --experiment-name "kd-price-prediction-v1"
# MLflow UI: mlflow ui --port 5000
```

### 6. Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### 7. Full stack (production-like)

```bash
docker compose -f docker-compose.prod.yml up --build
# App at http://localhost:3000
```

---

## 10. Environment Variables Reference

```dotenv
# Database
DATABASE_URL=postgresql+asyncpg://kd_user:kd_pass@localhost:5432/kenyadrive
POSTGRES_USER=kd_user
POSTGRES_PASSWORD=kd_pass
POSTGRES_DB=kenyadrive

# Redis
REDIS_URL=redis://localhost:6379/0

# External APIs
EXCHANGE_RATE_API_KEY=your_api_key_here   # https://www.exchangerate-api.com (free)

# ML
MODEL_ARTIFACT_PATH=models/artifacts/price_model_v1.joblib
MLFLOW_TRACKING_URI=http://localhost:5000

# Scraper
SCRAPER_CONCURRENCY=4
SCRAPER_DOWNLOAD_DELAY=2.0   # seconds between requests (be respectful)
PLAYWRIGHT_HEADLESS=true

# API
API_SECRET_KEY=change_this_in_production
CORS_ORIGINS=http://localhost:5173,https://your-domain.com

# Frontend
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

---

## 11. API Endpoints Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/cars/search` | Search listings with filters |
| `GET` | `/api/v1/cars/{id}` | Single listing detail |
| `POST` | `/api/v1/import/calculate` | Full KRA cost breakdown |
| `POST` | `/api/v1/predict/price` | ML price prediction + SHAP |
| `GET` | `/api/v1/compare/local` | Import vs local market |
| `GET` | `/api/v1/exchange/rates` | Current JPY/KES, USD/KES |
| `GET` | `/api/v1/analytics/summary` | Aggregated dashboard stats |

Full OpenAPI docs available at `/docs` (Swagger UI) and `/redoc` when running.

---

## 12. Deliverables Checklist

| # | Deliverable | Day | Status |
|---|---|---|---|
| 1 | ✅ Working spiders for 5 Japanese platforms | Day 1 | ⬜ |
| 2 | ✅ PostgreSQL database with raw + curated schemas | Day 1–2 | ⬜ |
| 3 | ✅ Cleaned dataset (≥ 400 vehicles) as Parquet + CSV | Day 2 | ⬜ |
| 4 | ✅ Great Expectations validation suite | Day 2 | ⬜ |
| 5 | ✅ EDA notebooks (6 notebooks) | Day 2–3 | ⬜ |
| 6 | ✅ Trained XGBoost/LightGBM model (MAPE < 15%) | Day 3 | ⬜ |
| 7 | ✅ MLflow experiment tracking | Day 3 | ⬜ |
| 8 | ✅ SHAP explainability analysis | Day 3 | ⬜ |
| 9 | ✅ FastAPI backend (8 endpoints, tested) | Day 4 | ⬜ |
| 10 | ✅ KRA import cost calculator (full duty chain) | Day 4 | ⬜ |
| 11 | ✅ Local market comparison engine | Day 4 | ⬜ |
| 12 | ✅ React dashboard (5 pages, mobile-responsive) | Day 5 | ⬜ |
| 13 | ✅ Docker Compose (single-command spin-up) | Day 5 | ⬜ |
| 14 | ✅ GitHub Actions CI/CD pipeline | Day 5 | ⬜ |
| 15 | ✅ Project documentation (5 doc files) | All days | ⬜ |

---

## 13. Contributing

```bash
# Create feature branch
git checkout -b feat/your-feature-name

# Install pre-commit (runs Ruff on commit)
pre-commit install

# Run tests before pushing
pytest tests/ -v

# Open pull request against main
```

**Code style:** Ruff (E, F, I rules). Python type hints required on all function signatures. Pydantic models for all API I/O.

---

## 14. License

MIT License — see [LICENSE](LICENSE) for details.

---