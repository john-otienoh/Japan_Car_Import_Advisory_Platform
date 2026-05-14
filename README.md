# Japan Car Import Advisory Platform

> A data engineering and machine learning platform that helps Kenyan car buyers compare the true cost of importing cars from Japan against buying locally.

Project by [LuxDevHQ](https://github.com/LuxDevHQ/LuxDevHQ-Projects/blob/main/japan-car-price-prediction-project.md)

---

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Project Status](#project-status)
- [Architecture](#architecture)
- [Data Sources](#data-sources)
- [Project Structure](#project-structure)
- [What Has Been Built](#what-has-been-built)
- [What Remains To Be Built](#what-remains-to-be-built)
- [Setup & Installation](#setup--installation)
- [Usage](#usage)
- [Import Cost Methodology](#import-cost-methodology)
- [ML Model](#ml-model)
- [Tech Stack](#tech-stack)
- [Contributing](#contributing)

---

## Project Overview

Importing a car from Japan is often significantly cheaper than buying locally in Kenya — but the full picture is complex. Shipping, KRA duty, VAT, excise duty, port charges, clearing fees, and registration all add up. This platform:

1. **Scrapes** live car listings from major Japanese exporters (2018 onwards)
2. **Stores and cleans** the data in a structured database
3. **Calculates** the true all-in import cost into Kenya
4. **Compares** that cost against Kenyan local market prices
5. **Predicts** Japan-side car prices using a machine learning model
6. **Presents** everything through an interactive dashboard

---

## Project Status

| Phase | Status |
|---|---|
| SBT Japan scraper — homepage data | ✅ Complete |
| SBT Japan scraper — brand & model discovery | ✅ Complete |
| SBT Japan scraper — paginated search results | ✅ Complete |
| SBT Japan scraper — individual car detail page | ✅ Complete (specs, info, dimensions, options, images) |
| Database design & storage | 🔲 Not started |
| Data cleaning pipeline | 🔲 Not started |
| Additional source scrapers (CFJ, AAA, JCT, BE FORWARD) | 🔲 Not started |
| Import cost calculator (KRA, shipping, fees) | 🔲 Not started |
| Local market price comparison | 🔲 Not started |
| ML price prediction model | 🔲 Not started |
| Dashboard / web application | 🔲 Not started |
| Documentation & presentation | 🔲 Not started |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              DATA EXTRACTION LAYER           │
│  SBT Japan │ Car From Japan │ BE FORWARD     │
│  AAA Japan │ JapanesCarTrade                 │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│              DATABASE LAYER                  │
│  Raw tables → Cleaned tables → Feature store │
└────────────────────┬────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌─────────────────┐   ┌─────────────────────┐
│  COST CALCULATOR │   │   ML PRICE MODEL    │
│  KRA duty        │   │   XGBoost/RF        │
│  Shipping        │   │   Price prediction  │
│  Port charges    │   │   by make/model/    │
│  Clearing fees   │   │   year/mileage etc. │
│  Registration    │   └─────────────────────┘
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│              DASHBOARD / WEB APP             │
│  Import cost estimate vs local market price  │
│  Savings calculator │ Price prediction tool  │
└─────────────────────────────────────────────┘
```

---

## Data Sources

| Platform | URL | Status |
|---|---|---|
| SBT Japan | www.sbtjapan.com | ✅ Scraper built |
| Car From Japan | carfromjapan.com | 🔲 Pending |
| AAA Japan | aaajapan.com | 🔲 Pending |
| JapanesCarTrade (JCT) | www.japanesecartrade.com | 🔲 Pending |
| BE FORWARD | www.beforward.jp | 🔲 Pending |

All scrapers target vehicles manufactured **2018 onwards** only.

---

## Project Structure

```
japan-car-import-platform/
│
├── scrapers/
│   ├── sbtjapan/
│   │   ├── scraper.py          # Main scraper — homepage, brands, search, detail
│   │   └── utils.py            # get_total_pages(), HEADERS, fetch()
│   ├── carfromjapan/           # 🔲 Pending
│   ├── beforward/              # 🔲 Pending
│   ├── aaajapan/               # 🔲 Pending
│   └── japanesecartrade/       # 🔲 Pending
│
├── database/
│   ├── schema.sql              # 🔲 Pending — table definitions
│   └── models.py               # 🔲 Pending — ORM models
│
├── pipeline/
│   ├── clean.py                # 🔲 Pending — data cleaning
│   └── transform.py            # 🔲 Pending — feature engineering
│
├── calculator/
│   └── import_cost.py          # 🔲 Pending — KRA + all fees
│
├── ml/
│   ├── train.py                # 🔲 Pending — model training
│   ├── predict.py              # 🔲 Pending — inference
│   └── evaluate.py             # 🔲 Pending — metrics
│
├── dashboard/
│   └── app.py                  # 🔲 Pending — Streamlit/Flask app
│
├── data/
│   ├── raw/                    # Raw scraped data
│   └── cleaned/                # Processed data ready for ML
│
├── docs/
│   └── import_cost_methodology.md
│
├── requirements.txt
└── README.md
```

---

## What Has Been Built

### SBT Japan Scraper (`scrapers/sbtjapan/scraper.py`)

**`get_homepage_data()`**
Scrapes the SBT Japan homepage and returns:
- Top viewed models
- All car brands
- All body types
- All inventory locations

**`get_search_urls(homepage_data)`**
Takes the homepage data, visits each brand's maker page, extracts the correct `make_id`, and returns a list of correctly encoded search URLs for every model — handling spaces in model names (e.g. `ODYSSEY HYBRID → ODYSSEY%20HYBRID`).

**`get_car_detail_urls(search_url)`**
Takes a single search URL, detects the total number of pages from pagination, iterates all pages, and returns a list of individual car detail URLs (e.g. `https://www.sbtjapan.com/used-cars/AG2813`).

**`parse_car_specs(soup)`**
Extracts the spec block (mileage, engine, transmission, drive, steering, fuel, doors, seats) from a detail page into a dict.

**`parse_car_info(soup)`**
Extracts the info block (make, model, body colour, body type, doors, seats) into a dict.

**`parse_car_dimensions(soup)`**
Extracts the dimensions block (dimension, m3, vehicle weight, gross weight, max loading capacity) into a dict.

**`parse_car_options(soup)`**
Extracts only **available** car options grouped by category (Comfort & Convenience, Safety, etc.) — skipping unavailable features.

**`parse_gallery_images(soup)`**
Extracts all full-size image URLs from the Swiper gallery slider — deduplicating by targeting the main slider only, skipping blank filler slides.

---

## What Remains To Be Built

### 1. Database Layer
- Design a normalised schema: `cars`, `specs`, `options`, `images`, `prices`, `sources`
- Set up PostgreSQL (recommended) or SQLite for local dev
- Write an ingestion script that maps scraper output → DB rows
- Add a `scraped_at` timestamp and `source_platform` column to every record

### 2. Data Cleaning Pipeline
- Normalise price fields: strip commas and currency symbols → float
- Normalise mileage: strip `km` → integer
- Normalise engine capacity: strip `cc` → integer
- Handle `-` values (missing data) → `NULL`
- Standardise make/model casing across platforms
- Filter to 2018+ only based on year parsed from title
- Deduplicate listings that appear across multiple platforms

### 3. Additional Scrapers
Build scrapers for Car From Japan, BE FORWARD, AAA Japan, and JapanesCarTrade following the same interface:
- `get_search_urls()` → list of search URLs
- `get_car_detail_urls(search_url)` → list of detail URLs
- `parse_car_detail(soup)` → dict of car data

### 4. Import Cost Calculator
Implement Kenya-specific cost components:

| Component | Basis |
|---|---|
| Purchase price | Scraped FOB price (USD) |
| Shipping | Approx. USD 1,200–1,800 depending on port (Mombasa) |
| Marine insurance | ~1.5% of (FOB + freight) |
| Import duty | 25% of CIF value |
| Excise duty | 20–35% depending on engine size |
| VAT | 16% of (CIF + import duty + excise duty) |
| IDF levy | 3.5% of CIF |
| Railway development levy | 2% of CIF |
| Port charges | Fixed ~KES 15,000–25,000 |
| Clearing agent fees | ~KES 30,000–50,000 |
| NTSA registration | Based on vehicle age and value |

All rates should be updatable as KRA revises them.

### 5. Local Market Price Comparison
- Scrape or integrate local Kenyan platforms (e.g. Cheki Kenya, PigiaMe) for equivalent models
- Match on make + model + year + mileage band
- Display: `Import all-in cost` vs `Local market median price` → `Estimated saving`

### 6. ML Price Prediction Model
Target: predict the Japan-side FOB price of a car given its features.

Features:
- Make, Model, Year, Mileage, Engine size
- Fuel type, Transmission, Body type, Drive type
- Source platform, Inventory location

Suggested approach:
- Baseline: Linear Regression
- Main model: XGBoost or LightGBM
- Evaluation: RMSE, MAE, R²
- Save model with `joblib` for serving

### 7. Dashboard / Web Application
- Framework: Streamlit (quick) or Flask + React (production-grade)
- Pages:
  - **Search** — filter by make/model/year/budget
  - **Import Calculator** — enter a car, get full landed cost in KES
  - **Compare** — import cost vs local price, savings estimate
  - **Price Predictor** — ML model input form, returns predicted FOB price
  - **Market Insights** — charts: price by brand, mileage distribution, popular models

---

## Setup & Installation

```bash
git clone https://github.com/your-username/japan-car-import-platform.git
cd japan-car-import-platform

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

**requirements.txt**
```
requests
beautifulsoup4
lxml
psycopg2-binary       # PostgreSQL driver
sqlalchemy
pandas
scikit-learn
xgboost
streamlit
python-dotenv
```

---

## Usage

```python
from scrapers.sbtjapan.scraper import (
    get_homepage_data,
    get_search_urls,
    get_car_detail_urls,
)

# Step 1 — get brands, models, body types
homepage = get_homepage_data()

# Step 2 — get search URLs for all models
search_urls = get_search_urls(homepage)

# Step 3 — get individual car links from first search
car_urls = get_car_detail_urls(search_urls[0])
print(car_urls)
# ['https://www.sbtjapan.com/used-cars/AG2813', ...]
```

---

## Import Cost Methodology

Full documentation of the KRA duty calculation methodology will live in `docs/import_cost_methodology.md`. The core formula:

```
CIF = FOB price + Freight + Marine Insurance
Import Duty = 25% × CIF
Excise Duty = rate × (CIF + Import Duty)
VAT = 16% × (CIF + Import Duty + Excise Duty)
IDF = 3.5% × CIF
RDL = 2% × CIF

Total Tax = Import Duty + Excise Duty + VAT + IDF + RDL
Landed Cost (KES) = (CIF + Total Tax) × USD/KES rate
                  + Port charges + Clearing fees + Registration
```

---

## ML Model

Target variable: `vehicle_price_usd` (FOB Japan)

```
Input features
──────────────────────────────────────
make           │ Toyota, Honda, Nissan…
model          │ Corolla, Accord, X-Trail…
year           │ 2018 – present
mileage_km     │ integer
engine_cc      │ integer
fuel_type      │ Petrol, Diesel, Hybrid…
transmission   │ AT, MT
body_type      │ Sedan, SUV, Hatchback…
drive_type     │ 2WD, 4WD, AWD
source         │ sbtjapan, beforward…

Output
──────────────────────────────────────
predicted_price_usd
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Scraping | Python, Requests, BeautifulSoup4 |
| Database | PostgreSQL + SQLAlchemy |
| Data processing | Pandas |
| ML | scikit-learn, XGBoost |
| Dashboard | Streamlit (planned) |
| Version control | Git / GitHub |

---

## Contributing

This is a [LuxDevHQ](https://github.com/LuxDevHQ) project. To contribute:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/beforward-scraper`
3. Commit your changes: `git commit -m "add BE FORWARD scraper"`
4. Push and open a pull request

---

*Built as part of the LuxDevHQ Data Engineering & ML Programme.*