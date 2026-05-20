# KenJapAI — Week 1 Daily Checklist
> Japan → Kenya Car Import Intelligence Platform  
> **Goal:** Check off every task before midnight each day. Links are reference material — read them *before* you code, not after.

---

## Day 1 — Project Setup, Infrastructure & Scraping Pipeline
`Hours 0–12 · Phase: Infrastructure & Web Scraping`

### Morning — Hours 1–6: Environment & Schema

- [ ] **Create GitHub repository** with the following folder structure:
  ```
  kenjapai/
  ├── scraper/
  ├── etl/
  ├── ml/
  ├── api/
  ├── frontend/
  ├── notebooks/
  ├── docs/
  ├── docker-compose.yml
  └── .env.example
  ```
  > 📖 [GitHub — Creating a repo](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)  
  > 📖 [Structuring Python projects](https://docs.python-guide.org/writing/structure/)

- [ ] **Set up Python virtual environment** (`python -m venv .venv`) and create `requirements.txt` with initial dependencies: `scrapy`, `playwright`, `sqlalchemy`, `psycopg2-binary`, `python-dotenv`, `redis`
  > 📖 [Python venv docs](https://docs.python.org/3/library/venv.html)  
  > 📖 [pip & requirements.txt best practices](https://pip.pypa.io/en/stable/reference/requirements-file-format/)

- [ ] **Write `docker-compose.yml`** with three services: `postgres:15`, `redis:7-alpine`, `dpage/pgadmin4`
  > 📖 [Docker Compose getting started](https://docs.docker.com/compose/gettingstarted/)  
  > 📖 [Official Postgres Docker image](https://hub.docker.com/_/postgres)  
  > 📖 [Redis Docker image](https://hub.docker.com/_/redis)

- [ ] **Run `docker compose up -d`** and verify all three containers are healthy (`docker ps`)

- [ ] **Set up `pre-commit` hooks**: `black`, `isort`, `flake8`
  > 📖 [pre-commit official docs](https://pre-commit.com/)  
  > 📖 [Black formatter](https://black.readthedocs.io/en/stable/)

- [ ] **Design and write `schema.sql`** — create these tables in PostgreSQL:
  - `raw_listings` (id, source_platform, raw_json, scraped_at, url)
  - `cleaned_listings` (id, make, model, year, mileage_km, engine_cc, fuel_type, transmission, body_type, price_usd, price_kes, source_platform, listing_url, scraped_at)
  - `platforms`, `makes`, `models`, `price_predictions`, `import_estimates`
  > 📖 [PostgreSQL CREATE TABLE docs](https://www.postgresql.org/docs/current/sql-createtable.html)  
  > 📖 [Database schema design — normalization primer](https://www.geeksforgeeks.org/database-normalization-normal-forms/)  
  > 📖 [SQLAlchemy ORM quickstart](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)

- [ ] **Confirm schema is live** in pgAdmin (`localhost:5050`)

---

### Afternoon — Hours 7–12: Scrapers

- [ ] **Read and understand Scrapy fundamentals** before writing a single spider
  > 📖 [Scrapy official tutorial](https://docs.scrapy.org/en/latest/intro/tutorial.html)  
  > 📖 [Scrapy architecture overview](https://docs.scrapy.org/en/latest/topics/architecture.html)  
  > 📖 [Scrapy items & pipelines](https://docs.scrapy.org/en/latest/topics/item-pipeline.html)

- [ ] **Spider #1 — BE FORWARD** (`beforward.jp`)
  - [ ] Handle pagination (detect last page)
  - [ ] Filter: `year >= 2018`
  - [ ] Extract: make, model, year, mileage, engine cc, fuel, transmission, body type, price (USD), listing URL
  - [ ] Store raw JSON to `raw_listings` table
  > 📖 [Scrapy spiders docs](https://docs.scrapy.org/en/latest/topics/spiders.html)  
  > 📖 [CSS & XPath selectors in Scrapy](https://docs.scrapy.org/en/latest/topics/selectors.html)

- [ ] **Spider #2 — SBT Japan** (`sbtjapan.com`) — JS-rendered, use Playwright
  - [ ] Install `scrapy-playwright`: `pip install scrapy-playwright && playwright install`
  - [ ] Set `PLAYWRIGHT_LAUNCH_OPTIONS` in `settings.py`
  - [ ] Extract same fields as Spider #1
  > 📖 [scrapy-playwright GitHub](https://github.com/scrapy-plugins/scrapy-playwright)  
  > 📖 [Playwright Python docs](https://playwright.dev/python/docs/intro)  
  > 📖 [Handling JavaScript-rendered pages](https://scrapeops.io/python-scrapy-playbook/scrapy-playwright/)

- [ ] **Spider #3 — Car From Japan** (`carfromjapan.com`)
  - [ ] Add rotating user-agent middleware
  - [ ] Set `DOWNLOAD_DELAY = 2` in `settings.py`
  > 📖 [Scrapy downloader middleware](https://docs.scrapy.org/en/latest/topics/downloader-middleware.html)  
  > 📖 [scrapy-rotating-proxies](https://github.com/TeamHG-Memex/scrapy-rotating-proxies)  
  > 📖 [Fake user agents — fake-useragent library](https://pypi.org/project/fake-useragent/)

- [ ] **Spider #4 — AAA Japan** (`aaajapan.com`)

- [ ] **Spider #5 — JapaneseCarTrade / JCT** (`japanesecartrade.com`)

- [ ] **Verify** at least **500 raw listings** are in the `raw_listings` table

---

### ✅ Day 1 Deliverables
- [ ] Raw scraper codebase (5 spiders)
- [ ] Docker Compose stack running (Postgres + Redis + pgAdmin)
- [ ] PostgreSQL schema v1 applied
- [ ] ≥ 500 raw listings in `raw_listings`
- [ ] Git repo with meaningful first commit

---

---

## Day 2 — ETL Pipeline, Data Cleaning & Database Finalisation
`Hours 12–24 · Phase: ETL & Data Engineering`

### Morning — Hours 1–6: Cleaning Module

- [ ] **Read about ETL pipeline patterns** before writing code
  > 📖 [ETL vs ELT — what's the difference](https://www.databricks.com/glossary/etl-pipeline)  
  > 📖 [pandas data cleaning guide](https://pandas.pydata.org/docs/getting_started/intro_tutorials/04_reshaping_tidy_data.html)  
  > 📖 [ydata-profiling (pandas profiling)](https://docs.profiling.ydata.ai/4.6/getting-started/quickstart/)

- [ ] **Build `etl/cleaner.py`** — normalise price fields:
  - [ ] Parse JPY/USD amounts from raw strings (strip `$`, `,`, `¥`)
  - [ ] Convert JPY → USD using a static or fetched rate
  - [ ] Convert USD → KES using the CBK daily rate (or OpenExchangeRates free tier)
  > 📖 [CBK exchange rates portal](https://www.centralbank.go.ke/forex-exchange-rates/)  
  > 📖 [Open Exchange Rates API (free)](https://openexchangerates.org/api/latest.json?app_id=YOUR_KEY)  
  > 📖 [regex for currency parsing](https://docs.python.org/3/library/re.html)

- [ ] **Standardise make/model names** using fuzzy matching (e.g. "Toyota" vs "TOYOTA" vs "toyota")
  > 📖 [rapidfuzz library (fast fuzzy matching)](https://github.com/maxbachmann/RapidFuzz)  
  > 📖 [thefuzz (original fuzzywuzzy)](https://github.com/seatgeek/thefuzz)

- [ ] **Handle nulls and type coercion**:
  - [ ] `year`: cast to int, drop rows where `year < 2018`
  - [ ] `mileage_km`: cast to int, impute median per make+model+year group
  - [ ] `engine_cc`: impute median per make+model group
  - [ ] `price_usd`: drop rows with price = 0 or null

- [ ] **Feature engineering** — add these derived columns:
  - [ ] `age_years = 2025 - year`
  - [ ] `price_per_cc = price_usd / engine_cc`
  - [ ] `mileage_band` = `Low (<50k)`, `Medium (50–120k)`, `High (>120k)`
  - [ ] One-hot encode: `fuel_type`, `transmission`, `body_type`
  > 📖 [pandas cut() for binning](https://pandas.pydata.org/docs/reference/api/pandas.cut.html)  
  > 📖 [sklearn LabelEncoder / OneHotEncoder](https://scikit-learn.org/stable/modules/preprocessing.html#encoding-categorical-features)

- [ ] **Build `etl/validator.py`** using Great Expectations:
  - [ ] Null % check: `price_usd` nulls < 5%
  - [ ] Range checks: `year` between 2018–2025, `mileage_km` between 0–500,000, `price_usd` between 500–200,000
  - [ ] Duplicate detection on `(make, model, year, mileage_km, source_platform)`
  > 📖 [Great Expectations quickstart](https://docs.greatexpectations.io/docs/tutorials/quickstart/)  
  > 📖 [GE core concepts — Expectations](https://docs.greatexpectations.io/docs/reference/learn/conceptual_guides/expectation_classes)

---

### Afternoon — Hours 7–12: Airflow & Exports

- [ ] **Install and configure Apache Airflow** (local or Docker)
  > 📖 [Airflow quickstart (Docker)](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html)  
  > 📖 [Airflow DAG writing guide](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html)  
  > 📖 [Airflow TaskFlow API (modern style)](https://airflow.apache.org/docs/apache-airflow/stable/tutorial/taskflow.html)

- [ ] **Write `dags/scrape_and_clean_dag.py`**:
  - [ ] Task 1: `scrape_all_platforms`
  - [ ] Task 2: `validate_raw`
  - [ ] Task 3: `clean_and_load`
  - [ ] Task 4: `notify_slack_or_log`
  - [ ] Set retry: 3 retries, 5-minute retry delay
  - [ ] Dead-letter queue: failed records → Redis list `failed_listings`
  > 📖 [Airflow XComs (passing data between tasks)](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/xcoms.html)  
  > 📖 [Redis Python client (redis-py)](https://redis-py.readthedocs.io/en/stable/)

- [ ] **Finalise `cleaned_listings` table**:
  - [ ] Add composite index on `(make, model, year)`
  - [ ] Add index on `source_platform`
  - [ ] Create materialized view `ml_features_view` with all engineered columns

  > 📖 [PostgreSQL indexes](https://www.postgresql.org/docs/current/indexes.html)  
  > 📖 [PostgreSQL materialized views](https://www.postgresql.org/docs/current/rules-materializedviews.html)

- [ ] **Export cleaned dataset**:
  - [ ] `data/cleaned_listings.csv`
  - [ ] `data/cleaned_listings.parquet` (use `pandas.to_parquet`)
  > 📖 [pandas to_parquet docs](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_parquet.html)  
  > 📖 [Why Parquet over CSV](https://towardsdatascience.com/the-best-format-to-save-pandas-data-414dca023e0d)

- [ ] **Generate data profiling report** in a Jupyter notebook using `ydata-profiling`

---

### ✅ Day 2 Deliverables
- [ ] `etl/cleaner.py` and `etl/validator.py` modules
- [ ] Airflow DAG running end-to-end
- [ ] `cleaned_listings` table with ≥ 1,000 rows
- [ ] Data quality GE report (HTML)
- [ ] `cleaned_listings.csv` and `.parquet` exports
- [ ] Schema v2 with indexes and materialized view

---

---

## Day 3 — Exploratory Data Analysis & KRA Import Cost Research
`Hours 24–36 · Phase: EDA & Domain Research`

### Morning — Hours 1–6: EDA Notebooks

- [ ] **Open Jupyter Lab** and create `notebooks/01_pricing_eda.ipynb`

- [ ] **EDA Notebook #1 — Pricing Analysis**:
  - [ ] Price distribution histograms per make (top 10 makes)
  - [ ] Box plots: price by year (2018–2024)
  - [ ] Scatter: mileage vs price, coloured by make
  - [ ] Bar chart: median price per source platform (compare SBT vs BE FORWARD vs others)
  - [ ] Outlier analysis: IQR method, flag and exclude
  > 📖 [matplotlib plotting guide](https://matplotlib.org/stable/tutorials/pyplot.html)  
  > 📖 [seaborn statistical data visualisation](https://seaborn.pydata.org/tutorial.html)  
  > 📖 [Plotly Express for interactive plots](https://plotly.com/python/plotly-express/)  
  > 📖 [IQR outlier detection explained](https://www.thoughtco.com/what-is-the-interquartile-range-rule-3126244)

- [ ] **EDA Notebook #2 — Feature Correlations** (`notebooks/02_feature_correlations.ipynb`):
  - [ ] Correlation heatmap (all numeric features)
  - [ ] Violin plots: price by fuel type, by transmission type
  - [ ] Body type pricing tiers (sedan vs SUV vs hatchback)
  - [ ] Engine cc vs price curve (line plot with confidence band)
  > 📖 [pandas correlation methods](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.corr.html)  
  > 📖 [seaborn heatmap](https://seaborn.pydata.org/generated/seaborn.heatmap.html)

- [ ] **Write down your 5 most interesting findings** as markdown cells in the notebook — these become slides later

---

### Afternoon — Hours 7–12: KRA Research & Local Market Data

- [ ] **Study the KRA CRSP (Current Retail Selling Price) system**
  - [ ] Understand how CRSP value is determined (not FOB — it's KRA's own valuation)
  - [ ] Note the KEBS age restriction: **max 8 years old** at the time of import
  > 📖 [KRA — Motor vehicle duty guide](https://www.kra.go.ke/individual/filing-paying/types-of-taxes/customs-border-control/motor-vehicles)  
  > 📖 [KEBS vehicle import age limits](https://www.kebs.org/index.php/technical/standards/vehicle-standards)  
  > 📖 [KRA CRSP lookup portal](https://crsp.kra.go.ke/)

- [ ] **Document the full KRA import duty formula** in `docs/import_cost_formula.md`:
  - [ ] **CIF** = FOB price + freight + insurance
  - [ ] **Import Declaration Fee (IDF)**: 2.25% of CIF
  - [ ] **Railway Development Levy (RDL)**: 2% of CIF
  - [ ] **Customs Duty**: 25% of CIF (for passenger cars)
  - [ ] **Excise Duty**: based on engine cc brackets (see table below)
  - [ ] **VAT**: 16% of (CIF + Customs + Excise)

  | Engine cc       | Excise Duty Rate |
  |-----------------|-----------------|
  | ≤ 1,000 cc      | 20%             |
  | 1,001–2,000 cc  | 30%             |
  | > 2,000 cc      | 35%             |

  > 📖 [KRA Excise Duty Act (motor vehicles)](https://www.kra.go.ke/individual/filing-paying/types-of-taxes/excise-duty/excise-duty-on-motor-vehicles)  
  > 📖 [Customs & Border Control — tariff schedules](https://www.kra.go.ke/images/publications/East_African_Community_Customs_Management_Act.pdf)

- [ ] **Document port & clearing costs** in `docs/import_cost_formula.md`:
  - [ ] Mombasa port handling (RORO): ~ KES 15,000–25,000
  - [ ] CFS (Container Freight Station) charges if containerised
  - [ ] Clearing agent fee: 3–5% of CIF value (typical)
  - [ ] KPA documentation charges
  - [ ] Transit to Nairobi (SGR or road): KES 30,000–80,000
  > 📖 [Kenya Ports Authority tariff schedule](https://www.kpa.co.ke/)  
  > 📖 [SGR cargo rates — Madaraka Express](https://www.krc.co.ke/cargo/)

- [ ] **Build Kenya local market price dataset**:
  - [ ] Write a simple `requests` + `BeautifulSoup` scraper for Cheki.co.ke or PigiaMe
  - [ ] Target: 2018+ vehicles, same makes as Japan dataset
  - [ ] Store in `local_market_listings` table
  > 📖 [BeautifulSoup docs](https://beautiful-soup-4.readthedocs.io/en/latest/)  
  > 📖 [requests library quickstart](https://requests.readthedocs.io/en/latest/user/quickstart/)

- [ ] **Produce a visual price gap analysis** — for top 5 makes, plot:
  - `Japan total import cost` vs `Kenya local market price` (stacked bar or grouped bar)

---

### ✅ Day 3 Deliverables
- [ ] `notebooks/01_pricing_eda.ipynb` (complete with findings)
- [ ] `notebooks/02_feature_correlations.ipynb`
- [ ] `docs/import_cost_formula.md` (full formula with sources)
- [ ] `data/local_market_prices.csv`
- [ ] Price gap analysis chart (saved as PNG)

---

---

## Day 4 — Machine Learning Model: Japan Car Price Predictor
`Hours 36–48 · Phase: ML Modelling`

### Morning — Hours 1–6: Baselines & Feature Prep

- [ ] **Read about the ML workflow** before opening a notebook
  > 📖 [scikit-learn user guide — supervised learning](https://scikit-learn.org/stable/supervised_learning.html)  
  > 📖 [ML workflow overview — Google Developers](https://developers.google.com/machine-learning/crash-course/ml-intro)  
  > 📖 [Target encoding for high-cardinality categoricals](https://towardsdatascience.com/target-encoding-for-categorical-features-in-machine-learning-models-c75b76753b69)

- [ ] **Create `notebooks/03_ml_price_predictor.ipynb`**

- [ ] **Feature prep**:
  - [ ] Load `ml_features_view` from PostgreSQL
  - [ ] Drop columns: `listing_url`, `scraped_at`, `raw_id`
  - [ ] One-hot encode: `fuel_type`, `transmission`, `body_type`, `source_platform`
  - [ ] Log-transform target: `y = log1p(price_usd)` (reduces skew)
  - [ ] Stratified 80/20 train/test split on `make`
  > 📖 [numpy log1p](https://numpy.org/doc/stable/reference/generated/numpy.log1p.html)  
  > 📖 [sklearn train_test_split stratified](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.train_test_split.html)  
  > 📖 [sklearn Pipeline](https://scikit-learn.org/stable/modules/pipeline.html)

- [ ] **Baseline models** — run all three, record MAE/RMSE/R²:
  - [ ] `LinearRegression`
  - [ ] `Ridge(alpha=1.0)`
  - [ ] `RandomForestRegressor(n_estimators=100)` — also extract `.feature_importances_`
  > 📖 [Regression metrics explained — MAE, RMSE, R²](https://towardsdatascience.com/what-are-the-best-metrics-to-evaluate-your-regression-model-418ca4d5e601)  
  > 📖 [sklearn cross_val_score](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.cross_val_score.html)

---

### Afternoon — Hours 7–12: XGBoost, SHAP & MLflow

- [ ] **XGBoost hyperparameter tuning with Optuna**:
  - [ ] Install: `pip install xgboost lightgbm optuna`
  - [ ] Define Optuna objective function: optimise RMSE on validation fold
  - [ ] Run 100 trials, `n_jobs=-1`
  - [ ] Retrieve best params, retrain final model
  > 📖 [XGBoost Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html)  
  > 📖 [LightGBM Python quickstart](https://lightgbm.readthedocs.io/en/stable/Python-Intro.html)  
  > 📖 [Optuna — hyperparameter optimisation](https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/001_first.html)  
  > 📖 [Optuna + XGBoost tutorial](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/003_attributes.html)

- [ ] **5-fold cross-validation** on final XGBoost model — confirm R² ≥ 0.82

- [ ] **SHAP explainability**:
  - [ ] `pip install shap`
  - [ ] Generate global summary plot (`shap.summary_plot`)
  - [ ] Generate waterfall chart for a single prediction
  - [ ] Save top-5 feature importance as JSON for the API to serve
  > 📖 [SHAP official docs](https://shap.readthedocs.io/en/latest/)  
  > 📖 [SHAP with XGBoost tutorial](https://shap.readthedocs.io/en/latest/example_notebooks/tabular_examples/tree_based_models/Census+income+classification+with+XGBoost.html)  
  > 📖 [Interpretable ML book — SHAP chapter](https://christophm.github.io/interpretable-ml-book/shap.html)

- [ ] **MLflow experiment tracking**:
  - [ ] `pip install mlflow`
  - [ ] Wrap training in `with mlflow.start_run():`
  - [ ] Log: params, metrics (MAE, RMSE, R²), model artifact, SHAP plot as artifact
  - [ ] Register best model in MLflow Model Registry as `"japan_car_price_v1"`
  > 📖 [MLflow quickstart](https://mlflow.org/docs/latest/getting-started/intro-quickstart/index.html)  
  > 📖 [MLflow model registry](https://mlflow.org/docs/latest/model-registry.html)  
  > 📖 [MLflow autolog for sklearn/XGBoost](https://mlflow.org/docs/latest/tracking/autolog.html)

- [ ] **Serialise the model**:
  - [ ] `joblib.dump(model, 'ml/models/xgb_price_v1.pkl')`
  - [ ] Export to ONNX for portable inference
  - [ ] Write `ml/model_card.md`: training data, features, metrics, known limitations, bias notes
  > 📖 [joblib model persistence](https://scikit-learn.org/stable/model_persistence.html)  
  > 📖 [ONNX — open neural network exchange](https://onnx.ai/sklearn-onnx/)  
  > 📖 [Model cards for ML — Google paper](https://arxiv.org/abs/1810.03993)

---

### ✅ Day 4 Deliverables
- [ ] `notebooks/03_ml_price_predictor.ipynb`
- [ ] Trained XGBoost/LGBM model (`.pkl` file)
- [ ] MLflow run log (all experiments tracked)
- [ ] SHAP summary + waterfall plots (saved as PNG)
- [ ] `ml/model_card.md`
- [ ] R² ≥ 0.82 confirmed on test set

---

---

## Day 5 — FastAPI Backend: Cost Calculator + Prediction API
`Hours 48–60 · Phase: Backend API Development`

### Morning — Hours 1–6: App Scaffold & Core Endpoints

- [ ] **Read FastAPI fundamentals** before writing a line
  > 📖 [FastAPI official tutorial](https://fastapi.tiangolo.com/tutorial/)  
  > 📖 [Pydantic v2 — data validation](https://docs.pydantic.dev/latest/)  
  > 📖 [Async SQLAlchemy with FastAPI](https://fastapi.tiangolo.com/tutorial/sql-databases/)  
  > 📖 [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/tutorial.html)

- [ ] **Scaffold `api/main.py`** with routers:
  - [ ] `GET  /health` — returns `{"status": "ok"}`
  - [ ] `GET  /listings` — paginated, filterable car listings
  - [ ] `POST /import-cost` — full import cost breakdown
  - [ ] `POST /predict` — ML price prediction
  - [ ] `GET  /compare` — Japan import total vs local market price

- [ ] **Define Pydantic request/response models** in `api/schemas.py`:
  ```python
  class ImportCostRequest(BaseModel):
      make: str
      model: str
      year: int
      engine_cc: int
      fob_price_usd: float
      shipping_cost_usd: float = 1800.0

  class ImportCostResponse(BaseModel):
      cif_usd: float
      idf_kes: float
      rdl_kes: float
      customs_duty_kes: float
      excise_duty_kes: float
      vat_kes: float
      port_charges_kes: float
      clearing_fee_kes: float
      transit_kes: float
      total_landed_kes: float
      exchange_rate: float
  ```

- [ ] **Implement `POST /import-cost`** using the formula from Day 3
  - [ ] Fetch live USD/KES rate from CBK or Open Exchange Rates
  - [ ] Return itemised breakdown
  > 📖 [httpx async HTTP client](https://www.python-httpx.org/)  
  > 📖 [FastAPI background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)

- [ ] **Implement `GET /compare`**:
  - [ ] Query `cleaned_listings` for matched Japan car (make + model + year ± 1)
  - [ ] Query `local_market_listings` for same match
  - [ ] Return both prices + `savings_kes` field

---

### Afternoon — Hours 7–12: ML Endpoint, Auth & Tests

- [ ] **Implement `POST /predict`**:
  - [ ] Load model from MLflow registry or local `.pkl`
  - [ ] Apply same preprocessing pipeline used during training
  - [ ] Return: `predicted_price_usd`, `confidence_interval`, `top_5_shap_features`
  > 📖 [FastAPI — handling ML models](https://fastapi.tiangolo.com/deployment/manually/)  
  > 📖 [Loading MLflow models in production](https://mlflow.org/docs/latest/models.html#deploy-mlflow-models)

- [ ] **Add API key authentication middleware**:
  ```python
  from fastapi.security.api_key import APIKeyHeader
  ```
  - [ ] Read key from `X-API-Key` header
  - [ ] Validate against `.env` variable
  > 📖 [FastAPI security — API keys](https://fastapi.tiangolo.com/advanced/security/api-key/)

- [ ] **Add Redis-backed rate limiter** (100 requests/min per API key)
  > 📖 [fastapi-limiter](https://github.com/long2ice/fastapi-limiter)  
  > 📖 [Redis INCR + EXPIRE pattern for rate limiting](https://redis.io/docs/latest/develop/use/patterns/rate-limiting/)

- [ ] **Write test suite** in `api/tests/`:
  - [ ] `pytest` + `httpx.AsyncClient`
  - [ ] Test `/import-cost` with known input → verify each line-item
  - [ ] Test `/predict` returns shape and type expected
  - [ ] Confirm ≥ 80% coverage with `pytest-cov`
  > 📖 [Testing FastAPI with pytest](https://fastapi.tiangolo.com/tutorial/testing/)  
  > 📖 [pytest-cov coverage reports](https://pytest-cov.readthedocs.io/en/latest/)  
  > 📖 [Locust load testing](https://docs.locust.io/en/stable/quickstart.html)

- [ ] **Verify OpenAPI docs** are auto-generated at `http://localhost:8000/docs`

---

### ✅ Day 5 Deliverables
- [ ] FastAPI app with all 5 endpoints live
- [ ] `POST /import-cost` returns correct itemised breakdown
- [ ] `POST /predict` returns price + SHAP features
- [ ] API key auth + rate limiter working
- [ ] Pytest suite passing with ≥ 80% coverage
- [ ] Swagger/OpenAPI docs accessible

---

---

## Day 6 — React Frontend Dashboard
`Hours 60–72 · Phase: Frontend Dashboard`

### Morning — Hours 1–6: Scaffold & Listings Page

- [ ] **Read before coding**
  > 📖 [Vite — Getting started](https://vitejs.dev/guide/)  
  > 📖 [React Router v6](https://reactrouter.com/en/main/start/tutorial)  
  > 📖 [TanStack Query (react-query) v5](https://tanstack.com/query/latest/docs/framework/react/overview)  
  > 📖 [Zustand state management](https://zustand-demo.pmnd.rs/)  
  > 📖 [Tailwind CSS docs](https://tailwindcss.com/docs/installation)  
  > 📖 [Recharts — React chart library](https://recharts.org/en-US/guide)

- [ ] **Scaffold React + Vite app**:
  ```bash
  npm create vite@latest frontend -- --template react
  cd frontend && npm install
  npm install tailwindcss react-router-dom @tanstack/react-query axios zustand recharts
  ```

- [ ] **Set up React Router** with 5 routes:
  - [ ] `/` — Analytics dashboard (home)
  - [ ] `/listings` — Car listings browser
  - [ ] `/calculator` — Import cost calculator
  - [ ] `/predict` — ML price predictor
  - [ ] `/compare` — Market comparison

- [ ] **Build the listings browser page** (`/listings`):
  - [ ] Filter sidebar: make, model, year range, mileage range, fuel type, body type, platform
  - [ ] Sortable table with columns: make, model, year, mileage, engine, price (USD), source
  - [ ] Pagination (10/25/50 per page)
  - [ ] Thumbnail gallery toggle
  > 📖 [TanStack Table v8 (headless table)](https://tanstack.com/table/latest/docs/introduction)  
  > 📖 [React filter/search patterns](https://www.robinwieruch.de/react-filter-component/)

---

### Afternoon — Hours 7–12: Calculator, Predictor & Analytics

- [ ] **Build import cost calculator UI** (`/calculator`):
  - [ ] Step 1: Select make + model + year (typeahead dropdown)
  - [ ] Step 2: Enter FOB price (USD) + shipping estimate
  - [ ] Step 3: Show animated itemised cost breakdown in KES
  - [ ] Include a progress bar or stepper component
  > 📖 [React controlled components — forms](https://react.dev/learn/sharing-state-between-components)  
  > 📖 [Headless UI combobox (autocomplete)](https://headlessui.com/react/combobox)

- [ ] **Build ML price predictor UI** (`/predict`):
  - [ ] Input form: make, model, year, mileage, engine cc, fuel type, transmission
  - [ ] Submit → show predicted price (USD) with confidence interval
  - [ ] Render SHAP waterfall chart (horizontal bar chart in Recharts)

- [ ] **Build price comparison view** (`/compare`):
  - [ ] Search for a make + model + year
  - [ ] Side-by-side card: Japan total landed cost vs Kenya local market price
  - [ ] Savings badge (green if importing is cheaper)

- [ ] **Build analytics dashboard** (home `/`):
  - [ ] Platform price comparison bar chart (Recharts `BarChart`)
  - [ ] Price over year trend line (`LineChart`)
  - [ ] Mileage distribution histogram
  - [ ] Top 10 value imports table

  > 📖 [Recharts BarChart example](https://recharts.org/en-US/examples/SimpleBarChart)  
  > 📖 [Recharts LineChart example](https://recharts.org/en-US/examples/SimpleLineChart)  
  > 📖 [Axios with React — data fetching](https://axios-http.com/docs/example)

---

### ✅ Day 6 Deliverables
- [ ] React SPA running at `localhost:5173` with 5 routes
- [ ] Listings browser with working filters + pagination
- [ ] Import cost calculator (step-by-step wizard UI)
- [ ] ML price predictor with SHAP output
- [ ] Market comparison view with savings badge
- [ ] Analytics dashboard with 4 charts

---

---

## Day 7 — Integration, Testing, Deployment & Documentation
`Hours 72–84 · Phase: Polish, Deploy & Document`

### Morning — Hours 1–6: Integration Testing & Production Build

- [ ] **End-to-end smoke test**: scraper → ETL → DB → API → frontend
  - [ ] Trigger a fresh scraper run manually
  - [ ] Confirm cleaned data lands in `cleaned_listings`
  - [ ] Hit `/listings` API — confirm frontend renders results
  - [ ] Hit `/import-cost` — confirm all line items populate in UI
  - [ ] Hit `/predict` — confirm prediction + SHAP renders

- [ ] **Write multi-stage `Dockerfile` for the API**:
  ```dockerfile
  FROM python:3.11-slim AS builder
  # ... install deps
  FROM python:3.11-slim AS runtime
  # ... copy only what's needed
  ```
  > 📖 [Multi-stage Dockerfiles](https://docs.docker.com/build/building/multi-stage/)  
  > 📖 [Docker best practices for Python](https://testdriven.io/blog/docker-best-practices/)

- [ ] **Write `docker-compose.prod.yml`**:
  - [ ] Services: `api`, `db` (postgres), `redis`, `nginx`
  - [ ] Nginx as reverse proxy for API + static frontend build
  - [ ] Read secrets from `.env.prod`
  > 📖 [Nginx as reverse proxy — Docker guide](https://www.nginx.com/resources/wiki/start/topics/examples/full/)  
  > 📖 [Docker secrets / env management](https://docs.docker.com/compose/use-secrets/)

- [ ] **Build React production bundle**: `npm run build` → `dist/`

- [ ] **Deploy to cloud**:
  - [ ] API + Postgres → [Railway](https://railway.app) or [Render](https://render.com/docs/deploy-fastapi)
  - [ ] Frontend → [Vercel](https://vercel.com/docs/frameworks/vite) (`vercel --prod`)
  - [ ] Set environment variables in each platform's dashboard
  > 📖 [Deploy FastAPI on Render](https://render.com/docs/deploy-fastapi)  
  > 📖 [Railway — deploy Docker services](https://docs.railway.app/guides/dockerfiles)  
  > 📖 [Vercel — deploy Vite app](https://vercel.com/docs/frameworks/vite)

- [ ] **Verify live URLs** — test every endpoint on production

---

### Afternoon — Hours 7–12: Documentation & Portfolio

- [ ] **Write `README.md`** — the most important file in your repo:
  - [ ] Project overview + problem statement
  - [ ] Architecture diagram (embed the roadmap image or draw with Mermaid)
  - [ ] Setup instructions (Docker Compose, env variables)
  - [ ] API reference (link to `/docs`)
  - [ ] Live demo link
  - [ ] Badges: `![CI](...)`, `![Coverage](...)`, `![License](...)`
  > 📖 [Making a great README](https://www.makeareadme.com/)  
  > 📖 [Shields.io — readme badges](https://shields.io/)  
  > 📖 [Mermaid architecture diagrams in markdown](https://mermaid.js.org/syntax/architecture.html)

- [ ] **Write `docs/data_dictionary.md`** — document every column in `cleaned_listings`

- [ ] **Write `docs/deployment_guide.md`** — step-by-step from clone to live

- [ ] **Build 10-slide presentation deck** (PowerPoint or Google Slides):
  1. Problem: why Kenyans overpay for cars
  2. Solution overview: what KenJapAI does
  3. Data: sources, volume, methodology
  4. EDA insights: top 3 findings
  5. Import cost breakdown: formula walkthrough
  6. ML model: features, algorithm, results (R², RMSE)
  7. SHAP: what actually drives price
  8. Product demo: screenshot tour
  9. Savings analysis: how much can buyers save?
  10. Next steps: roadmap, mobile app, dealer partnerships

- [ ] **Polish GitHub repo**:
  - [ ] Clean commit history (squash any "fix typo" commits)
  - [ ] Add `LICENSE` file (MIT)
  - [ ] Record a 60-second demo GIF with [LiceCap](https://www.cockos.com/licecap/) or [Kap](https://getkap.co/)
  - [ ] Pin repo to your GitHub profile
  - [ ] Draft LinkedIn post: project summary + demo GIF + live link

  > 📖 [git rebase --interactive for squashing](https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History)  
  > 📖 [Choosing an open source license](https://choosealicense.com/)

---

### ✅ Day 7 Deliverables
- [ ] Live deployed platform (API + frontend URLs working)
- [ ] `docker-compose.prod.yml` + Nginx config
- [ ] `README.md` (complete, with badges + demo link)
- [ ] `docs/data_dictionary.md`
- [ ] `docs/deployment_guide.md`
- [ ] 10-slide presentation deck
- [ ] Portfolio-ready GitHub repo (clean, pinned, demo GIF)

---

---

## Master Deliverables Checklist

| # | Deliverable | Day | Status |
|---|-------------|-----|--------|
| 1 | Raw scraper codebase (5 spiders) | Day 1 | `[ ]` |
| 2 | Docker Compose stack | Day 1 | `[ ]` |
| 3 | ETL pipeline + Airflow DAG | Day 2 | `[ ]` |
| 4 | Cleaned dataset (CSV + Parquet) | Day 2 | `[ ]` |
| 5 | EDA notebooks (2) | Day 3 | `[ ]` |
| 6 | KRA import cost formula + local market data | Day 3 | `[ ]` |
| 7 | Trained ML model (R² ≥ 0.82) + MLflow log | Day 4 | `[ ]` |
| 8 | FastAPI backend (5 endpoints, tested) | Day 5 | `[ ]` |
| 9 | React frontend (5 pages) | Day 6 | `[ ]` |
| 10 | Live deployed platform | Day 7 | `[ ]` |
| 11 | Full project documentation | Day 7 | `[ ]` |
| 12 | 10-slide presentation deck | Day 7 | `[ ]` |

---

*Built with Python · PostgreSQL · Airflow · scikit-learn · XGBoost · MLflow · SHAP · FastAPI · React · Docker*
