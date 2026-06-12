# Day 2 — Curated Layer & Data Cleaning Pipeline
### `curated.vehicles` — Clean, Standardised, ML-Ready

**Goal:** Transform raw scraped records from CarFromJapan, BeForward, and SBT Japan into a
deduplicated, normalised, feature-enriched curated layer, validated and exported for ML use.

---

## Project Structure

```
car_pipeline/
├── pipeline/
│   ├── cleaning/
│   │   ├── __init__.py
│   │   ├── deduplicator.py          # Hours 1–2
│   │   ├── currency.py              # Hour  3
│   │   ├── normalizer.py            # Hours 4–5
│   │   ├── imputer.py               # Hour  6
│   │   └── feature_builder.py       # Hours 7–8
│   └── run_pipeline.py              # Hours 10 + 12
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_raw_schema_baseline.py
│       └── 0002_curated_vehicles.py  # Hour 9
├── validation/
│   └── ge_suite.py                  # Hour 11
├── api/
│   └── services/
│       └── local_market.py          # Hour 14
├── notebooks/
│   └── 02_cleaning_exploration.ipynb # Hour 13
├── data/
│   ├── cleaned/                     # .parquet output
│   └── exports/                     # .csv output
├── docs/
│   └── architecture.md              # Hour 15
├── alembic.ini
├── .env
└── requirements_day2.txt
```

---

## Prerequisites

```bash
pip install -r requirements_day2.txt
```

**`requirements_day2.txt`**

```text
# Cleaning & enrichment
pandas>=2.0.0
numpy>=1.26.0
thefuzz>=0.20.0
python-levenshtein>=0.21.0

# ML imputation
scikit-learn>=1.3.0

# Currency API + caching
httpx>=0.25.0
redis>=5.0.0
python-dotenv>=1.0.0

# Database
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
alembic>=1.13.0

# Validation
great-expectations>=0.18.0

# Export
pyarrow>=14.0.0

# EDA notebook
matplotlib>=3.7.0
seaborn>=0.12.0
duckdb>=0.9.0
jupyterlab>=4.0.0
ipykernel>=6.25.0

# Local market scraper
beautifulsoup4>=4.12.0
```

**`.env`**

```dotenv
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/car_inventory
EXCHANGE_RATE_API_KEY=your_key_from_exchangerate-api.com
REDIS_URL=redis://localhost:6379
```

---

## Hours 1–2 — Deduplication Engine

**File:** `pipeline/cleaning/deduplicator.py`

Cross-platform duplicate detection on `(make, year, model ≈ fuzzy, mileage ±5%, engine_cc ±100)`.
Uses Union-Find for O(n) group resolution after O(n²) pairwise comparison within make+year buckets.
The record with the most non-null attributes wins; all others are flagged `is_duplicate = True`.

```python
"""
pipeline/cleaning/deduplicator.py
----------------------------------
Cross-platform deduplication for CFJ · BeForward · SBT Japan records.

Algorithm
---------
1. Bucket rows by (make_upper, year_int) — exact match to shrink the search space.
2. For every pair within a bucket:
     a. fuzzy model name similarity (token_sort_ratio ≥ threshold)
     b. engine_cc within ±100 cc
     c. mileage_km within ±5%
   All three must pass for a pair to be considered the same vehicle.
3. Union-Find groups the confirmed duplicate pairs.
4. Within each group the record with the most non-null columns is canonical;
   the rest receive  is_duplicate = True, canonical_id = <winner index>.
"""

import re
from collections import defaultdict
from itertools import combinations
from typing import Optional

import numpy as np
import pandas as pd
from thefuzz import fuzz


# ─────────────────────────────────────────────────────────────────────────────
# Union-Find (Disjoint Set Union) with path compression + union by rank
# ─────────────────────────────────────────────────────────────────────────────
class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank   = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # halving
            x = self.parent[x]
        return x

    def union(self, x: int, y: int):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ─────────────────────────────────────────────────────────────────────────────
# Similarity helpers
# ─────────────────────────────────────────────────────────────────────────────
def _mileage_close(m1, m2, pct: float = 0.05) -> bool:
    """True if both unknown, or abs difference ≤ pct of mean."""
    if pd.isna(m1) or pd.isna(m2):
        return True          # can't rule out duplicate when mileage missing
    if m1 == 0 and m2 == 0:
        return True
    avg = (float(m1) + float(m2)) / 2
    return (abs(float(m1) - float(m2)) / avg) <= pct if avg > 0 else True


def _cc_close(cc1, cc2, tol: int = 100) -> bool:
    """True if both unknown, or abs difference ≤ tol cc."""
    if pd.isna(cc1) or pd.isna(cc2):
        return True
    return abs(int(cc1) - int(cc2)) <= tol


def _richness(row: pd.Series) -> int:
    """Count of non-null, non-empty values — used to pick the canonical record."""
    return int(row.apply(lambda v: pd.notna(v) and str(v).strip() not in ("", "nan")).sum())


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def deduplicate(
    df: pd.DataFrame,
    model_threshold: int  = 80,
    mileage_pct:     float = 0.05,
    cc_tolerance:    int  = 100,
) -> pd.DataFrame:
    """
    Detect cross-source duplicates and annotate the DataFrame.

    Parameters
    ----------
    df               : normalised DataFrame (must have make, year_int,
                       model_name, mileage_km, engine_cc columns)
    model_threshold  : fuzz.token_sort_ratio minimum (0–100)
    mileage_pct      : fractional mileage tolerance (0.05 → ±5 %)
    cc_tolerance     : engine cc absolute tolerance

    Returns
    -------
    df with two new columns:
      is_duplicate (bool)  – True for non-canonical duplicates
      canonical_id (int)   – integer row-index of the canonical record
    """
    df = df.copy().reset_index(drop=True)
    n  = len(df)
    uf = _UnionFind(n)

    make_key  = df["make"].fillna("UNKNOWN").astype(str).str.upper().str.strip()
    year_key  = df["year_int"].fillna(-1).astype(int).astype(str)
    bucket_key = make_key + "||" + year_key

    # Pre-compute normalised model names for fuzzy comparison
    model_str = (
        df["model_name"].fillna("").astype(str).str.upper().str.strip()
    )

    pairs_found = 0
    for _, group_idx in df.groupby(bucket_key, sort=False).groups.items():
        idx_list = list(group_idx)
        if len(idx_list) < 2:
            continue

        for i, j in combinations(idx_list, 2):
            # Gate 1 — fuzzy model name
            if model_str.iloc[i] and model_str.iloc[j]:
                score = fuzz.token_sort_ratio(model_str.iloc[i], model_str.iloc[j])
                if score < model_threshold:
                    continue

            # Gate 2 — engine cc
            if not _cc_close(df.at[i, "engine_cc"], df.at[j, "engine_cc"], cc_tolerance):
                continue

            # Gate 3 — mileage ±5 %
            if not _mileage_close(df.at[i, "mileage_km"], df.at[j, "mileage_km"], mileage_pct):
                continue

            uf.union(i, j)
            pairs_found += 1

    # Resolve groups
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    is_duplicate = [False] * n
    canonical_id = list(range(n))

    dup_count = 0
    for root, members in groups.items():
        if len(members) < 2:
            continue
        richness = [_richness(df.iloc[m]) for m in members]
        winner   = members[int(np.argmax(richness))]
        for m in members:
            canonical_id[m] = winner
            if m != winner:
                is_duplicate[m] = True
                dup_count += 1

    df["is_duplicate"] = is_duplicate
    df["canonical_id"] = canonical_id

    print(
        f"  Deduplication: {dup_count} duplicates marked "
        f"({dup_count / n * 100:.1f}% of {n} records) "
        f"| {pairs_found} duplicate pairs found"
    )
    return df
```

---

## Hour 3 — Currency Normalisation

**File:** `pipeline/cleaning/currency.py`

Fetches live JPY/KES and USD/KES from ExchangeRate-API, caches results in Redis (TTL 3600 s),
and adds four price columns in KES and USD. Falls back to hardcoded rates when the API key is
absent or the request fails — never crashes the pipeline.

```python
"""
pipeline/cleaning/currency.py
------------------------------
Live exchange rate conversion: USD and JPY → KES + USD.

Redis cache key format: fx_rates:{BASE_CURRENCY}  TTL: 3600 s
Fallback rates used when EXCHANGE_RATE_API_KEY is absent or request fails.
"""

import json
import os
from typing import Optional

import httpx
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

EXCHANGE_RATE_API_KEY: str = os.getenv("EXCHANGE_RATE_API_KEY", "")
REDIS_URL:             str = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL:             int = 3600  # seconds

# Hard-coded fallback rates (approximate mid-2026 values)
_FALLBACK = {
    "USD_TO_KES": 129.50,
    "JPY_TO_USD": 0.00668,
}


# ─────────────────────────────────────────────────────────────────────────────
# Redis helper — never raises; returns None when unavailable
# ─────────────────────────────────────────────────────────────────────────────
def _redis_client():
    try:
        import redis
        r = redis.from_url(REDIS_URL, socket_connect_timeout=2)
        r.ping()
        return r
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Rate fetcher
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_rates(base: str = "USD") -> dict:
    """
    Returns {currency_code: rate, ...} where rate = how many of that
    currency per 1 unit of `base`. Checks Redis cache first.
    """
    if not EXCHANGE_RATE_API_KEY:
        print("  ⚠  EXCHANGE_RATE_API_KEY not set — using fallback rates")
        return {}

    cache_key = f"fx_rates:{base}"
    r = _redis_client()

    if r:
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)

    try:
        url  = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/latest/{base}"
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") != "success":
            raise ValueError(data.get("error-type", "unknown error"))
        rates = data["conversion_rates"]
        if r:
            r.setex(cache_key, CACHE_TTL, json.dumps(rates))
        print(f"  ✓  Live rates fetched (USD→KES: {rates.get('KES', '?'):.2f})")
        return rates
    except Exception as exc:
        print(f"  ⚠  ExchangeRate-API failed ({exc}) — using fallback rates")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def add_price_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert vehicle_price and total_price to KES and USD.

    New columns added
    -----------------
    vehicle_price_usd, vehicle_price_kes
    total_price_usd,   total_price_kes
    usd_to_kes_rate    (scalar stored per row for audit)
    """
    df = df.copy()

    usd_rates  = _fetch_rates("USD")
    usd_to_kes = usd_rates.get("KES", _FALLBACK["USD_TO_KES"])
    usd_to_jpy = usd_rates.get("JPY", 1 / _FALLBACK["JPY_TO_USD"])

    jpy_to_usd = 1.0 / usd_to_jpy if usd_to_jpy else _FALLBACK["JPY_TO_USD"]
    jpy_to_kes = jpy_to_usd * usd_to_kes

    def _to_usd(price, currency: str) -> Optional[float]:
        if pd.isna(price):
            return None
        c = str(currency).upper().strip().replace("$", "USD")
        p = float(price)
        if c in ("USD",):
            return p
        if c == "JPY":
            return p * jpy_to_usd
        if c in ("KES", "KSH"):
            return p / usd_to_kes
        return p  # default: already USD

    def _to_kes(usd_val) -> Optional[float]:
        return round(float(usd_val) * usd_to_kes, 2) if pd.notna(usd_val) else None

    # vehicle price
    df["vehicle_price_usd"] = df.apply(
        lambda r: _to_usd(r.get("vehicle_price"), r.get("currency", "USD")), axis=1
    )
    df["vehicle_price_kes"] = df["vehicle_price_usd"].apply(_to_kes)

    # total CnF price
    df["total_price_usd"] = df.apply(
        lambda r: _to_usd(r.get("total_price"), r.get("currency", "USD")), axis=1
    )
    df["total_price_kes"] = df["total_price_usd"].apply(_to_kes)

    # audit column
    df["usd_to_kes_rate"] = round(usd_to_kes, 4)

    return df
```

---

## Hours 4–5 — Field Normaliser

**File:** `pipeline/cleaning/normalizer.py`

Standardises all categorical and numeric fields using map-based lookups and regex extraction.
Also handles make extraction from the title string for CFJ/BeForward records where `make` is NULL.

```python
"""
pipeline/cleaning/normalizer.py
--------------------------------
Standardise raw scraped fields → unified categorical values.

Covers: fuel_type, transmission, body_type, make, steering, engine_cc,
        year_int (extracted from registration/manufacture strings), mileage_km.
"""

import re
from typing import Optional

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Lookup maps
# ─────────────────────────────────────────────────────────────────────────────
FUEL_MAP: dict[str, str] = {
    "petrol"            : "Petrol",
    "gasoline"          : "Petrol",
    "gas"               : "Petrol",
    "diesel"            : "Diesel",
    "hybrid"            : "Hybrid",
    "petrol/hybrid"     : "Hybrid",
    "petrol hybrid"     : "Hybrid",
    "plug-in hybrid"    : "Hybrid",
    "phev"              : "Hybrid",
    "mild hybrid"       : "Hybrid",
    "electric"          : "EV",
    "ev"                : "EV",
    "full electric"     : "EV",
    "cng"               : "CNG",
    "lpg"               : "LPG",
}

TRANSMISSION_MAP: dict[str, str] = {
    "at"        : "Automatic",
    "automatic" : "Automatic",
    "auto"      : "Automatic",
    "4at"       : "Automatic",
    "5at"       : "Automatic",
    "6at"       : "Automatic",
    "cvt"       : "CVT",
    "mt"        : "Manual",
    "manual"    : "Manual",
    "5mt"       : "Manual",
    "6mt"       : "Manual",
    "4mt"       : "Manual",
}

BODY_TYPE_MAP: dict[str, str] = {
    "suv"         : "SUV",
    "crossover"   : "SUV",
    "sedan"       : "Sedan",
    "saloon"      : "Sedan",
    "hatchback"   : "Hatchback",
    "pickup"      : "Pickup",
    "pick-up"     : "Pickup",
    "truck"       : "Truck",
    "van"         : "Van",
    "minivan"     : "Van",
    "minibus"     : "Van",
    "wagon"       : "Wagon",
    "estate"      : "Wagon",
    "coupe"       : "Coupe",
    "convertible" : "Convertible",
    "bus"         : "Bus",
}

MAKE_CANONICAL: dict[str, str] = {
    "toyota"        : "Toyota",
    "nissan"        : "Nissan",
    "honda"         : "Honda",
    "mazda"         : "Mazda",
    "suzuki"        : "Suzuki",
    "mitsubishi"    : "Mitsubishi",
    "subaru"        : "Subaru",
    "isuzu"         : "Isuzu",
    "daihatsu"      : "Daihatsu",
    "lexus"         : "Lexus",
    "bmw"           : "BMW",
    "mercedes"      : "Mercedes-Benz",
    "mercedes-benz" : "Mercedes-Benz",
    "volkswagen"    : "Volkswagen",
    "vw"            : "Volkswagen",
    "ford"          : "Ford",
    "hyundai"       : "Hyundai",
    "kia"           : "Kia",
    "land rover"    : "Land Rover",
    "landrover"     : "Land Rover",
    "jeep"          : "Jeep",
    "peugeot"       : "Peugeot",
    "renault"       : "Renault",
    "audi"          : "Audi",
    "volvo"         : "Volvo",
    "canter"        : "Mitsubishi",   # "CANTER TRUCK" titles
}


# ─────────────────────────────────────────────────────────────────────────────
# Per-field normalizers
# ─────────────────────────────────────────────────────────────────────────────
def _norm(val, mapping: dict) -> Optional[str]:
    if pd.isna(val) or not str(val).strip():
        return None
    key = str(val).strip().lower()
    return mapping.get(key, str(val).strip().title())


def normalize_fuel(val)         -> Optional[str]: return _norm(val, FUEL_MAP)
def normalize_transmission(val) -> Optional[str]: return _norm(val, TRANSMISSION_MAP)
def normalize_body_type(val)    -> Optional[str]: return _norm(val, BODY_TYPE_MAP)


def normalize_make(val) -> Optional[str]:
    if pd.isna(val) or not str(val).strip():
        return None
    key = str(val).strip().lower()
    # Direct lookup first
    if key in MAKE_CANONICAL:
        return MAKE_CANONICAL[key]
    # Partial match (e.g. "TOYOTA RAV4")
    for k, v in MAKE_CANONICAL.items():
        if k in key:
            return v
    return str(val).strip().title()


def extract_make_from_title(title: str) -> Optional[str]:
    """Extract known make from a full title string. Used when 'make' column is NULL."""
    if not title:
        return None
    t = str(title).lower()
    for key, canonical in MAKE_CANONICAL.items():
        if re.search(r"\b" + re.escape(key) + r"\b", t):
            return canonical
    return None


def parse_engine_cc(val) -> Optional[int]:
    """
    Extract integer cc from strings:
      '2500 cc(2.50 liters)' → 2500
      '1,980cc'              → 1980
      '3,000cc'              → 3000
      '2.0L'                 → 2000
      '2498'                 → 2498  (bare integer treated as cc if 500–9999)
    """
    if pd.isna(val) or not str(val).strip():
        return None
    s = str(val).lower().replace(",", "")

    # Explicit cc
    m = re.search(r"(\d+)\s*cc", s)
    if m:
        return int(m.group(1))

    # Explicit liters / L
    m = re.search(r"([\d.]+)\s*(?:l|lit(?:er|re)s?)\b", s)
    if m:
        return int(float(m.group(1)) * 1000)

    # Bare float like "2.5" (assume litres)
    m = re.match(r"^([\d]+\.\d+)$", s.strip())
    if m:
        v = float(m.group(1))
        if 0.5 <= v <= 8.0:
            return int(v * 1000)

    # Bare integer
    m = re.search(r"(\d{3,5})", s)
    if m:
        v = int(m.group(1))
        if 500 <= v <= 9_999:
            return v

    return None


def parse_year(val) -> Optional[int]:
    """Extract 4-digit year from '2019 / Dec', '2009/4', '2017/5', bare '2019'."""
    if pd.isna(val) or not str(val).strip():
        return None
    m = re.search(r"(19|20)\d{2}", str(val))
    return int(m.group(0)) if m else None


def normalize_steering(val) -> Optional[str]:
    if pd.isna(val):
        return None
    v = str(val).upper().strip()
    if v in ("RIGHT", "RHD", "R"):
        return "RHD"
    if v in ("LEFT",  "LHD", "L"):
        return "LHD"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Master normalizer
# ─────────────────────────────────────────────────────────────────────────────
def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all field-level normalisations in place.
    Returns a new DataFrame with extra columns: engine_cc (int), year_int (int).
    """
    df = df.copy()

    # Categorical fields
    df["fuel_type"]    = df["fuel_type"].apply(normalize_fuel)
    df["transmission"] = df["transmission"].apply(normalize_transmission)
    df["body_type"]    = df["body_type"].apply(normalize_body_type)
    df["steering"]     = df["steering"].apply(normalize_steering)

    # Make: normalise existing values, then backfill from title
    df["make"] = df["make"].apply(normalize_make)
    missing_make = df["make"].isna()
    if missing_make.any():
        df.loc[missing_make, "make"] = (
            df.loc[missing_make, "title"].apply(extract_make_from_title)
        )

    # Engine cc
    df["engine_cc"] = df["engine_capacity"].apply(parse_engine_cc)

    # Year integer (prefer manufacture_year, fall back to registration_year)
    df["year_int"] = df.apply(
        lambda r: (
            parse_year(r.get("manufacture_year"))
            or parse_year(r.get("registration_year"))
        ),
        axis=1,
    ).astype("Int64")

    # Mileage — already integer from scraper; coerce stragglers
    df["mileage_km"] = (
        pd.to_numeric(df["mileage_km"], errors="coerce").astype("Int64")
    )

    # Seats and doors as int
    df["seats"] = pd.to_numeric(df["seats"], errors="coerce").astype("Int64")
    df["doors"] = pd.to_numeric(df["doors"], errors="coerce").astype("Int64")

    return df
```

---

## Hour 6 — Imputer

**File:** `pipeline/cleaning/imputer.py`

KNN imputes `engine_cc` from `(make, year_int)`. Fills colour and grade with sentinel strings.
Flags mileage outliers. Never modifies the original DataFrame.

```python
"""
pipeline/cleaning/imputer.py
-----------------------------
Missing-value handling:
  engine_cc  → KNNImputer from (one-hot make, year_int)
  exterior_color → "Unknown"
  grade          → "Unknown"
  mileage        → flag outliers > 300,000 km for manual review
"""

import numpy as np
import pandas as pd
from sklearn.impute import KNNImputer

OUTLIER_MILEAGE_KM = 300_000
KNN_NEIGHBORS      = 5


def _impute_engine_cc(df: pd.DataFrame) -> pd.DataFrame:
    """
    KNN impute engine_cc using year_int and one-hot-encoded make.
    Only rows where engine_cc IS NULL are updated.
    """
    df = df.copy()

    needs_impute = df["engine_cc"].isna().any()
    if not needs_impute:
        return df

    # Features for KNN
    make_dummies = pd.get_dummies(df["make"].fillna("Unknown"), prefix="mk")
    knn_input    = pd.concat(
        [df[["year_int", "engine_cc"]].astype(float), make_dummies.astype(float)],
        axis=1,
    )

    imputer  = KNNImputer(n_neighbors=KNN_NEIGHBORS)
    imputed  = imputer.fit_transform(knn_input)

    # Column 1 is engine_cc in knn_input
    null_mask            = df["engine_cc"].isna()
    df.loc[null_mask, "engine_cc"] = (
        pd.array(imputed[null_mask.values, 1].round(), dtype="Int64")
    )

    imputed_count = int(null_mask.sum())
    print(f"  Imputer: engine_cc filled for {imputed_count} rows via KNN")
    return df


def impute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Run all imputation steps and return annotated DataFrame."""
    df = df.copy()

    # engine_cc: KNN
    df = _impute_engine_cc(df)

    # Colour sentinel
    df["exterior_color"] = (
        df["exterior_color"]
        .fillna("Unknown")
        .apply(lambda v: "Unknown" if str(v).strip() in ("", "nan", "-") else v)
    )

    # Grade sentinel
    df["grade"] = (
        df["grade"]
        .fillna("Unknown")
        .apply(lambda v: "Unknown" if str(v).strip() in ("", "nan", "-") else v)
    )

    # Mileage outlier flag
    df["mileage_outlier_flag"] = (
        df["mileage_km"].notna() & (df["mileage_km"] > OUTLIER_MILEAGE_KM)
    )
    outlier_count = df["mileage_outlier_flag"].sum()
    if outlier_count:
        print(f"  Imputer: {outlier_count} mileage outlier(s) flagged (> {OUTLIER_MILEAGE_KM:,} km)")

    return df
```

---

## Hours 7–8 — Age Calculation + Feature Engineering

**File:** `pipeline/cleaning/feature_builder.py`

```python
"""
pipeline/cleaning/feature_builder.py
--------------------------------------
Add derived features for ML and analytics.

Age features (Hour 7)
  vehicle_age_years      = CURRENT_YEAR - year_int
  exceeds_kra_age_limit  = age > 8  (KRA import eligibility: 2018–2026)

Engineered features (Hour 8)
  price_per_km_usd      = vehicle_price_usd / mileage_km
  engine_cc_band        = binned engine_cc label
  mileage_band          = binned mileage label
  is_hybrid             = True when fuel_type == Hybrid or EV
  is_popular_make       = True for Toyota/Nissan/Honda/Mazda/Suzuki/Mitsubishi
"""

import numpy as np
import pandas as pd

CURRENT_YEAR  = 2026
KRA_MAX_AGE   = 8   # vehicles older than 8 yrs fail KRA import check

POPULAR_MAKES = frozenset(
    {"Toyota", "Nissan", "Honda", "Mazda", "Suzuki", "Mitsubishi"}
)

MILEAGE_BINS   = [0, 30_000, 70_000, 120_000, 200_000, 300_000, float("inf")]
MILEAGE_LABELS = ["0–30k", "30k–70k", "70k–120k", "120k–200k", "200k–300k", "300k+"]

ENGINE_CC_BINS   = [0, 1_000, 1_500, 2_000, 2_500, 3_000, float("inf")]
ENGINE_CC_LABELS = ["<1000cc", "1000–1500", "1500–2000", "2000–2500", "2500–3000", ">3000cc"]


# ── Hour 7 ────────────────────────────────────────────────────────────────────

def add_age_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["vehicle_age_years"] = (
        CURRENT_YEAR - df["year_int"].astype("Int64")
    ).astype("Int64")
    df["exceeds_kra_age_limit"] = df["vehicle_age_years"] > KRA_MAX_AGE

    kra_flag_count = df["exceeds_kra_age_limit"].sum()
    print(f"  Age features: {kra_flag_count} record(s) exceed KRA 8-year import limit")
    return df


# ── Hour 8 ────────────────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # price_per_km — avoid division by zero
    km = df["mileage_km"].replace(0, np.nan).astype(float)
    df["price_per_km_usd"] = (
        df["vehicle_price_usd"].astype(float) / km
    ).round(4)

    # engine_cc_band
    df["engine_cc_band"] = pd.cut(
        df["engine_cc"].astype(float),
        bins=ENGINE_CC_BINS,
        labels=ENGINE_CC_LABELS,
        right=False,
    ).astype(str).replace("nan", "Unknown")

    # mileage_band
    df["mileage_band"] = pd.cut(
        df["mileage_km"].astype(float),
        bins=MILEAGE_BINS,
        labels=MILEAGE_LABELS,
        right=False,
    ).astype(str).replace("nan", "Unknown")

    # is_hybrid
    df["is_hybrid"] = df["fuel_type"].isin({"Hybrid", "EV"})

    # is_popular_make
    df["is_popular_make"] = df["make"].isin(POPULAR_MAKES)

    return df
```

---

## Hour 9 — Alembic Migration `0002`

### `alembic.ini`

```ini
[alembic]
script_location     = migrations
sqlalchemy.url      = postgresql+psycopg2://postgres:postgres@localhost:5432/car_inventory
file_template       = %%(rev)s_%%(slug)s
truncate_slug_length = 40

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

### `migrations/env.py`

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

load_dotenv()

config = context.config

# Override URL from .env if present
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### `migrations/versions/0001_raw_schema_baseline.py`

```python
"""Raw schema baseline — marks existing public.cars tables as already present.

Revision ID: 0001
"""
from alembic import op

revision    = "0001"
down_revision = None
branch_labels = None
depends_on  = None


def upgrade():
    # Raw schema was created manually by pipeline.py.
    # This migration only registers it as the baseline.
    pass


def downgrade():
    pass
```

### `migrations/versions/0002_curated_vehicles.py`

```python
"""Create curated schema with vehicles and prices tables.

Revision ID: 0002
Revises:     0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision      = "0002"
down_revision = "0001"
branch_labels = None
depends_on    = None


def upgrade():
    # ── curated schema ────────────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS curated")

    # ── curated.vehicles ──────────────────────────────────────────────────────
    op.create_table(
        "vehicles",
        # identity
        sa.Column("id",              sa.Integer,     primary_key=True),
        sa.Column("raw_car_id",      sa.Integer,
                  sa.ForeignKey("cars.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source",          sa.String(30),  nullable=False),
        sa.Column("car_url",         sa.Text,        unique=True, nullable=False),
        sa.Column("ref_no",          sa.String(100)),
        sa.Column("title",           sa.String(300)),
        # make / model
        sa.Column("make",            sa.String(100)),
        sa.Column("model_name",      sa.String(100)),
        sa.Column("model_code",      sa.String(100)),
        sa.Column("grade",           sa.String(200)),
        sa.Column("body_type",       sa.String(100)),
        # time
        sa.Column("year_int",           sa.SmallInteger),
        sa.Column("vehicle_age_years",  sa.SmallInteger),
        sa.Column("exceeds_kra_age_limit", sa.Boolean, default=False),
        # mileage
        sa.Column("mileage_km",          sa.Integer),
        sa.Column("mileage_band",        sa.String(20)),
        sa.Column("mileage_outlier_flag",sa.Boolean, default=False),
        # engine
        sa.Column("engine_cc",           sa.Integer),
        sa.Column("engine_cc_band",      sa.String(20)),
        # drivetrain
        sa.Column("transmission",        sa.String(20)),
        sa.Column("fuel_type",           sa.String(30)),
        sa.Column("drive_type",          sa.String(30)),
        sa.Column("steering",            sa.String(10)),
        # body
        sa.Column("seats",               sa.SmallInteger),
        sa.Column("doors",               sa.SmallInteger),
        sa.Column("exterior_color",      sa.String(50)),
        sa.Column("chassis_no",          sa.String(100)),
        sa.Column("dimension_m3",        sa.Numeric(8, 3)),
        sa.Column("delivery_port",       sa.String(100)),
        # ML flags
        sa.Column("is_hybrid",           sa.Boolean, default=False),
        sa.Column("is_popular_make",     sa.Boolean, default=False),
        # deduplication
        sa.Column("is_duplicate",        sa.Boolean, default=False, nullable=False),
        sa.Column("canonical_id",        sa.Integer),   # row-index of canonical record
        # audit
        sa.Column("curated_at",          sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now()),
        schema="curated",
    )

    op.create_index("ix_curated_vehicles_make",
                    "vehicles", ["make"], schema="curated")
    op.create_index("ix_curated_vehicles_year",
                    "vehicles", ["year_int"], schema="curated")
    op.create_index("ix_curated_vehicles_source",
                    "vehicles", ["source"], schema="curated")
    op.create_index("ix_curated_vehicles_is_dup",
                    "vehicles", ["is_duplicate"], schema="curated")

    # ── curated.prices ────────────────────────────────────────────────────────
    op.create_table(
        "prices",
        sa.Column("id",          sa.Integer, primary_key=True),
        sa.Column("vehicle_id",  sa.Integer,
                  sa.ForeignKey("curated.vehicles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("raw_car_id",  sa.Integer,
                  sa.ForeignKey("cars.id", ondelete="SET NULL"), nullable=True),
        sa.Column("currency",              sa.String(10), default="USD"),
        sa.Column("vehicle_price_usd",     sa.Numeric(12, 2)),
        sa.Column("vehicle_price_kes",     sa.Numeric(14, 2)),
        sa.Column("total_price_usd",       sa.Numeric(12, 2)),
        sa.Column("total_price_kes",       sa.Numeric(14, 2)),
        sa.Column("freight_amount_usd",    sa.Numeric(12, 2)),
        sa.Column("inspection_amount_usd", sa.Numeric(12, 2)),
        sa.Column("insurance_amount_usd",  sa.Numeric(12, 2)),
        sa.Column("discount_rate",         sa.String(20)),
        sa.Column("usd_to_kes_rate",       sa.Numeric(10, 4)),
        sa.Column("price_per_km_usd",      sa.Numeric(10, 4)),
        sa.Column("fetched_at",            sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now()),
        schema="curated",
    )

    op.create_index("ix_curated_prices_vehicle_id",
                    "prices", ["vehicle_id"], schema="curated")


def downgrade():
    op.drop_table("prices",   schema="curated")
    op.drop_table("vehicles", schema="curated")
    op.execute("DROP SCHEMA IF EXISTS curated")
```

**Apply migration:**

```bash
# Register the raw schema baseline (tables already exist from pipeline.py)
alembic stamp 0001

# Run migration 0002
alembic upgrade 0002
```

---

## Hour 11 — Great Expectations Validation Suite

**File:** `validation/ge_suite.py`

Gate: if **any** expectation sees > 5% violations the pipeline raises `PipelineValidationError`.

```python
"""
validation/ge_suite.py
-----------------------
Great Expectations validation suite for the curated DataFrame.

Expectations
------------
1. vehicle_price_usd > 0
2. year_int ∈ [2018, 2026]
3. mileage_km ≥ 0
4. fuel_type in allowed enum
5. No nulls in: make, mileage_km, year_int, vehicle_price_usd, fuel_type

Gate: fail pipeline when any expectation has > 5% unexpected rate.
"""

from __future__ import annotations

import pandas as pd
import great_expectations as ge

VALID_FUEL_TYPES   = {"Petrol", "Diesel", "Hybrid", "EV", "CNG", "LPG"}
FAILURE_THRESHOLD  = 0.05   # 5 %
YEAR_MIN, YEAR_MAX = 2018, 2026
PRIMARY_NOT_NULL   = ["make", "mileage_km", "year_int", "vehicle_price_usd", "fuel_type"]


class PipelineValidationError(RuntimeError):
    pass


def _violation_rate(result) -> float:
    """Extract unexpected fraction from a GE expectation result object."""
    res = result.result
    total = res.get("element_count", 1) or 1
    unexpected = res.get("unexpected_count", 0)
    return unexpected / total


def validate(df: pd.DataFrame) -> tuple[bool, dict]:
    """
    Run expectations against df.

    Returns
    -------
    (passed: bool, report: dict)
    Raises PipelineValidationError if any expectation breaches the 5% gate.
    """
    ge_df   = ge.from_pandas(df)
    report  = {}
    breaches = {}

    # 1. Price > 0
    r = ge_df.expect_column_values_to_be_between(
        "vehicle_price_usd", min_value=0, strict_min=True
    )
    report["price_positive"] = r
    rate = _violation_rate(r)
    if rate > FAILURE_THRESHOLD:
        breaches["price_positive"] = rate

    # 2. Year ∈ [2018, 2026]
    r = ge_df.expect_column_values_to_be_between(
        "year_int", min_value=YEAR_MIN, max_value=YEAR_MAX
    )
    report["year_in_range"] = r
    rate = _violation_rate(r)
    if rate > FAILURE_THRESHOLD:
        breaches["year_in_range"] = rate

    # 3. Mileage ≥ 0
    r = ge_df.expect_column_values_to_be_between("mileage_km", min_value=0)
    report["mileage_non_negative"] = r
    rate = _violation_rate(r)
    if rate > FAILURE_THRESHOLD:
        breaches["mileage_non_negative"] = rate

    # 4. fuel_type in allowed set
    r = ge_df.expect_column_values_to_be_in_set(
        "fuel_type", list(VALID_FUEL_TYPES)
    )
    report["fuel_type_valid"] = r
    rate = _violation_rate(r)
    if rate > FAILURE_THRESHOLD:
        breaches["fuel_type_valid"] = rate

    # 5. No nulls in primary features
    for col in PRIMARY_NOT_NULL:
        r = ge_df.expect_column_values_to_not_be_null(col)
        key = f"not_null_{col}"
        report[key] = r
        rate = _violation_rate(r)
        if rate > FAILURE_THRESHOLD:
            breaches[key] = rate

    passed = len(breaches) == 0

    # Print summary
    print(f"\n  {'─' * 48}")
    print(f"  GE Validation: {'✅ PASS' if passed else '❌ FAIL'}")
    for name, res in report.items():
        vr = _violation_rate(res)
        status = "✅" if vr <= FAILURE_THRESHOLD else "❌"
        unexp  = res.result.get("unexpected_count", 0)
        total  = res.result.get("element_count", len(df))
        print(f"  {status}  {name:<30} {unexp:>4}/{total}  ({vr*100:.1f}%)")
    print(f"  {'─' * 48}\n")

    if breaches:
        msg = "Validation breaches (> 5%): " + ", ".join(
            f"{k}={v*100:.1f}%" for k, v in breaches.items()
        )
        raise PipelineValidationError(msg)

    return passed, report
```

---

## Hours 10 + 12 — Run Pipeline + Export

**File:** `pipeline/run_pipeline.py`

Orchestrates every step in order. Reads from the `cars` + `car_pricing` DB tables,
runs the full cleaning chain, validates, inserts into `curated.vehicles` / `curated.prices`,
and exports to Parquet + CSV.

```python
"""
pipeline/run_pipeline.py
-------------------------
End-to-end cleaning pipeline.

Usage
-----
  python -m pipeline.run_pipeline            # reads from DB
  python -m pipeline.run_pipeline --json scraped_cars.json  # reads from JSON

Steps
-----
1. Load raw data from public.cars + public.car_pricing
2. Normalize fields (fuel, transmission, body_type, make, engine_cc, year_int)
3. Add KES / USD price columns (live rates or fallback)
4. Deduplicate across sources
5. KNN impute engine_cc; fill sentinel strings; flag mileage outliers
6. Age features (vehicle_age_years, exceeds_kra_age_limit)
7. Engineered features (price_per_km, bands, flags)
8. Great Expectations validation (gate: < 5% violations per expectation)
9. Insert into curated.vehicles + curated.prices
10. Export → data/cleaned/vehicles_clean.parquet + data/exports/vehicles_clean.csv
11. Print summary stats
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Cleaning modules
from pipeline.cleaning.normalizer     import normalize
from pipeline.cleaning.currency       import add_price_columns
from pipeline.cleaning.deduplicator   import deduplicate
from pipeline.cleaning.imputer        import impute_all
from pipeline.cleaning.feature_builder import add_age_features, build_features

# Validation
from validation.ge_suite import validate, PipelineValidationError

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/car_inventory"
)
OUTPUT_DIR_CLEANED = Path("data/cleaned")
OUTPUT_DIR_EXPORTS = Path("data/exports")


# ─────────────────────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────────────────────
_RAW_QUERY = """
    SELECT
        c.id            AS raw_car_id,
        c.source, c.car_url, c.ref_no, c.title,
        c.make, c.model_name, c.model_code, c.grade, c.body_type,
        c.registration_year, c.manufacture_year,
        c.mileage, c.mileage_km, c.engine_capacity,
        c.transmission, c.fuel_type, c.drive_type, c.steering,
        c.seats, c.doors, c.exterior_color, c.chassis_no,
        c.dimension_m3, c.dimension_raw, c.weight_kg,
        c.delivery_port, c.source_location, c.scraped_at,
        p.currency, p.vehicle_price, p.total_price,
        p.original_price, p.discount_rate,
        p.freight_amount, p.inspection_amount,
        p.insurance_amount, p.vanning_amount
    FROM cars c
    LEFT JOIN car_pricing p ON p.car_id = c.id
"""


def load_from_db(engine) -> pd.DataFrame:
    df = pd.read_sql(_RAW_QUERY, engine)
    print(f"  Loaded {len(df):,} raw records from DB")
    return df


def load_from_json(path: str) -> pd.DataFrame:
    """Load directly from scraper JSON output (array or url-keyed dict)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    records = list(data.values()) if isinstance(data, dict) else data
    df = pd.DataFrame(records)
    # Rename price fields from raw scraper names → pipeline names
    df = df.rename(columns={
        "car_price": "vehicle_price",   # legacy CFJ
        "total_cnf": "total_price",
    })
    print(f"  Loaded {len(df):,} records from {path}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Curated insert
# ─────────────────────────────────────────────────────────────────────────────
_VEHICLE_COLS = [
    "raw_car_id", "source", "car_url", "ref_no", "title",
    "make", "model_name", "model_code", "grade", "body_type",
    "year_int", "vehicle_age_years", "exceeds_kra_age_limit",
    "mileage_km", "mileage_band", "mileage_outlier_flag",
    "engine_cc", "engine_cc_band",
    "transmission", "fuel_type", "drive_type", "steering",
    "seats", "doors", "exterior_color", "chassis_no",
    "dimension_m3", "delivery_port",
    "is_hybrid", "is_popular_make",
    "is_duplicate", "canonical_id",
]

_PRICE_COLS = [
    "vehicle_price_usd", "vehicle_price_kes",
    "total_price_usd",   "total_price_kes",
    "freight_amount",    "inspection_amount", "insurance_amount",
    "discount_rate", "usd_to_kes_rate", "price_per_km_usd", "currency",
]


def insert_curated(df: pd.DataFrame, engine) -> int:
    """Insert clean records and return count of inserted vehicles."""
    vehicle_df = df[[c for c in _VEHICLE_COLS if c in df.columns]].copy()

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE curated.vehicles RESTART IDENTITY CASCADE"))

    vehicle_df.to_sql(
        "vehicles", engine,
        schema="curated", if_exists="append",
        index=False, method="multi",
    )

    # Re-read IDs to build prices FK
    with engine.connect() as conn:
        id_map = pd.read_sql(
            "SELECT id, car_url FROM curated.vehicles", conn
        ).set_index("car_url")["id"]

    price_df = df[[c for c in _PRICE_COLS if c in df.columns]].copy()
    price_df.insert(0, "vehicle_id", df["car_url"].map(id_map))
    price_df["raw_car_id"] = df.get("raw_car_id")

    price_df.to_sql(
        "prices", engine,
        schema="curated", if_exists="append",
        index=False, method="multi",
    )

    count = len(vehicle_df)
    print(f"  Inserted {count:,} records into curated.vehicles + curated.prices")
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Export  (Hour 12)
# ─────────────────────────────────────────────────────────────────────────────
def export(df: pd.DataFrame):
    OUTPUT_DIR_CLEANED.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR_EXPORTS.mkdir(parents=True, exist_ok=True)

    parquet_path = OUTPUT_DIR_CLEANED / "vehicles_clean.parquet"
    csv_path     = OUTPUT_DIR_EXPORTS  / "vehicles_clean.csv"

    df.to_parquet(parquet_path, engine="pyarrow", index=False)
    df.to_csv(csv_path, index=False)

    parquet_mb = parquet_path.stat().st_size / 1_048_576
    csv_mb     = csv_path.stat().st_size     / 1_048_576
    print(f"  Exported  Parquet: {parquet_path}  ({parquet_mb:.2f} MB)")
    print(f"            CSV:     {csv_path}  ({csv_mb:.2f} MB)")


# ─────────────────────────────────────────────────────────────────────────────
# Summary stats
# ─────────────────────────────────────────────────────────────────────────────
def print_summary(df: pd.DataFrame):
    print("\n" + "═" * 56)
    print("  PIPELINE SUMMARY")
    print("═" * 56)
    print(f"  Total records   : {len(df):>6,}")
    print(f"  Unique records  : {(~df['is_duplicate']).sum():>6,}")
    print(f"  Duplicates      : {df['is_duplicate'].sum():>6,}")
    print(f"  KRA age flagged : {df['exceeds_kra_age_limit'].sum():>6,}")
    print(f"  Mileage outliers: {df['mileage_outlier_flag'].sum():>6,}")
    print()
    print("  By source:")
    for src, grp in df.groupby("source"):
        print(f"    {src:<20} {len(grp):>5,} total  "
              f"({grp['is_duplicate'].sum():>3} dup)")
    print()
    print("  Price range (USD):")
    p = df["vehicle_price_usd"].dropna()
    if len(p):
        print(f"    min  ${p.min():>10,.0f}")
        print(f"    max  ${p.max():>10,.0f}")
        print(f"    mean ${p.mean():>10,.0f}")
    print()
    print("  Price range (KES):")
    k = df["vehicle_price_kes"].dropna()
    if len(k):
        print(f"    min  KES {k.min():>12,.0f}")
        print(f"    max  KES {k.max():>12,.0f}")
        print(f"    mean KES {k.mean():>12,.0f}")
    print()
    print("  Top makes:")
    for make, cnt in df["make"].value_counts().head(5).items():
        print(f"    {make:<20} {cnt:>4}")
    print("═" * 56 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def run(json_path: str | None = None):
    print("\n🚗  Day 2 Cleaning Pipeline")
    print("─" * 56)

    engine = create_engine(DATABASE_URL, echo=False)

    # Step 1 — Load
    print("\n[1/9] Loading raw data...")
    df = load_from_json(json_path) if json_path else load_from_db(engine)

    # Step 2 — Normalize
    print("[2/9] Normalizing fields...")
    df = normalize(df)

    # Step 3 — Currency
    print("[3/9] Converting currencies...")
    df = add_price_columns(df)

    # Step 4 — Deduplicate
    print("[4/9] Deduplicating...")
    df = deduplicate(df)

    # Step 5 — Impute
    print("[5/9] Imputing missing values...")
    df = impute_all(df)

    # Step 6 + 7 — Age + Features
    print("[6/9] Age features...")
    df = add_age_features(df)
    print("[7/9] Engineered features...")
    df = build_features(df)

    # Step 8 — Validate
    print("[8/9] Running GE validation suite...")
    try:
        validate(df)
    except PipelineValidationError as exc:
        print(f"\n❌  Validation FAILED — pipeline halted\n    {exc}\n")
        sys.exit(1)

    # Step 9 — Insert curated
    print("[9/9] Inserting into curated schema...")
    insert_curated(df, engine)

    # Export
    print("\n  Exporting files...")
    export(df)

    # Summary
    print_summary(df)
    print("🎉  Pipeline complete.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Day 2 cleaning pipeline")
    parser.add_argument(
        "--json", dest="json_path", default=None,
        help="Load from a JSON file instead of the database"
    )
    args = parser.parse_args()
    run(json_path=args.json_path)
```

---

## Hour 13 — EDA Notebook

**File:** `notebooks/02_cleaning_exploration.ipynb`

Save as `.py` and open with Jupyter or convert with `jupytext --to notebook 02_cleaning_exploration.py`.

```python
# %% [markdown]
# # 02 — Cleaning Exploration
# Exploratory analysis of the curated vehicle dataset.

# %% — Setup
import warnings
warnings.filterwarnings("ignore")

import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from pathlib import Path

PARQUET = "data/cleaned/vehicles_clean.parquet"
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
plt.rcParams["figure.dpi"] = 120

con = duckdb.connect()
df  = pd.read_parquet(PARQUET)
con.register("vehicles", df)

print(f"Shape: {df.shape}")
display(df.head(3))

# %% — 1. Price distribution per make (USD)
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Box plot
top_makes = df["make"].value_counts().head(8).index
plot_df   = df[df["make"].isin(top_makes) & df["vehicle_price_usd"].notna()]

sns.boxplot(
    data=plot_df, x="make", y="vehicle_price_usd",
    order=top_makes, ax=axes[0], showfliers=False
)
axes[0].set_title("Vehicle Price Distribution by Make (USD)")
axes[0].set_xlabel("")
axes[0].set_ylabel("Price (USD)")
axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
axes[0].tick_params(axis="x", rotation=30)

# Violin
sns.violinplot(
    data=plot_df, x="make", y="vehicle_price_usd",
    order=top_makes, ax=axes[1], inner="quartile", cut=0
)
axes[1].set_title("Price Density by Make (USD)")
axes[1].set_xlabel("")
axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
axes[1].tick_params(axis="x", rotation=30)

plt.tight_layout()
plt.savefig("docs/price_by_make.png", bbox_inches="tight")
plt.show()

# %% — 2. Mileage histogram by source
fig, ax = plt.subplots(figsize=(10, 5))
for src, grp in df[df["mileage_km"].notna()].groupby("source"):
    ax.hist(grp["mileage_km"] / 1000, bins=30, alpha=0.6, label=src, edgecolor="white")

ax.set_title("Mileage Distribution by Source")
ax.set_xlabel("Mileage (× 1,000 km)")
ax.set_ylabel("Count")
ax.axvline(300, color="crimson", linestyle="--", linewidth=1.2, label="300k outlier threshold")
ax.legend()
plt.tight_layout()
plt.savefig("docs/mileage_histogram.png", bbox_inches="tight")
plt.show()

# %% — 3. Correlation heatmap (numeric features)
num_cols = [
    "vehicle_price_usd", "total_price_usd", "mileage_km",
    "engine_cc", "vehicle_age_years", "seats", "doors",
    "dimension_m3", "price_per_km_usd",
]
corr = df[num_cols].corr()

fig, ax = plt.subplots(figsize=(10, 8))
mask = corr.isnull()
sns.heatmap(
    corr, annot=True, fmt=".2f", cmap="coolwarm",
    center=0, mask=mask, ax=ax,
    linewidths=0.5, square=True,
)
ax.set_title("Feature Correlation Heatmap")
plt.tight_layout()
plt.savefig("docs/correlation_heatmap.png", bbox_inches="tight")
plt.show()

# %% — 4. Top 20 models by listing count
top20 = (
    con.execute("""
        SELECT
            make || ' ' || COALESCE(model_name, 'Unknown') AS full_model,
            COUNT(*) AS listings,
            ROUND(AVG(vehicle_price_usd), 0)               AS avg_price_usd,
            ROUND(AVG(mileage_km), 0)                      AS avg_mileage_km
        FROM vehicles
        WHERE is_duplicate = false
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 20
    """).df()
)

fig, ax = plt.subplots(figsize=(11, 7))
bars = ax.barh(top20["full_model"][::-1], top20["listings"][::-1], color="#4C72B0")
ax.bar_label(bars, padding=3, fontsize=9)
ax.set_xlabel("Number of Listings")
ax.set_title("Top 20 Models by Listing Count (unique records only)")
plt.tight_layout()
plt.savefig("docs/top20_models.png", bbox_inches="tight")
plt.show()

display(top20.to_string(index=False))

# %% — 5. KRA eligibility breakdown
kra_summary = con.execute("""
    SELECT
        source,
        COUNT(*)                                              AS total,
        SUM(CASE WHEN exceeds_kra_age_limit THEN 1 ELSE 0 END) AS kra_flagged,
        ROUND(
            100.0 * SUM(CASE WHEN exceeds_kra_age_limit THEN 1 ELSE 0 END) / COUNT(*), 1
        )                                                     AS pct_flagged
    FROM vehicles
    GROUP BY source
    ORDER BY total DESC
""").df()

display(kra_summary)

# %% — 6. Fuel type breakdown
fig, ax = plt.subplots(figsize=(7, 5))
fuel_counts = df["fuel_type"].value_counts()
fuel_counts.plot.bar(ax=ax, color=sns.color_palette("muted", len(fuel_counts)))
ax.set_title("Listings by Fuel Type")
ax.set_xlabel("")
ax.set_ylabel("Count")
ax.tick_params(axis="x", rotation=30)
plt.tight_layout()
plt.savefig("docs/fuel_type_distribution.png", bbox_inches="tight")
plt.show()
```

---

## Hour 14 — Local Market Scraper Stub (Cheki Kenya)

**File:** `api/services/local_market.py`

```python
"""
api/services/local_market.py
-----------------------------
Stub scraper for Cheki Kenya used-car listings.
Populates local_market.listings table for price benchmarking.

Usage
-----
  from api.services.local_market import run
  run(max_pages=5)

Notes
-----
• Selector names reflect Cheki Kenya's markup as of mid-2026.
  Rerun against live HTML and update selectors if layout changes.
• Requires: httpx, beautifulsoup4
"""

import re
import time
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL    = "https://www.cheki.co.ke"
SEARCH_URL  = f"{BASE_URL}/used-cars/"
REQUEST_DELAY = 1.5

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/car_inventory"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────
_CREATE_TABLE = """
CREATE SCHEMA IF NOT EXISTS local_market;
CREATE TABLE IF NOT EXISTS local_market.listings (
    id          SERIAL PRIMARY KEY,
    source      VARCHAR(30) DEFAULT 'cheki_kenya',
    listing_url TEXT UNIQUE,
    title       VARCHAR(300),
    make        VARCHAR(100),
    model_name  VARCHAR(100),
    year_int    SMALLINT,
    price_kes   NUMERIC(14, 2),
    mileage_km  INTEGER,
    fuel_type   VARCHAR(30),
    transmission VARCHAR(20),
    location    VARCHAR(100),
    scraped_at  TIMESTAMPTZ DEFAULT NOW()
);
"""


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────
def _parse_price_kes(text: str) -> float | None:
    """'KSh 1,200,000' → 1200000.0"""
    digits = re.sub(r"[^\d]", "", text or "")
    return float(digits) if digits else None


def _parse_mileage(text: str) -> int | None:
    """'45,000 km' → 45000"""
    m = re.search(r"([\d,]+)\s*km", (text or ""), re.I)
    return int(m.group(1).replace(",", "")) if m else None


def _parse_year(text: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", text or "")
    return int(m.group(0)) if m else None


def _parse_card(card, base_url: str) -> dict | None:
    """Extract fields from a single listing card."""
    car: dict = {}

    # Title and URL
    link = card.select_one("a.listing-title, h2.title a, a[data-testid='listing-title']")
    if not link:
        return None
    car["title"] = link.get_text(strip=True)
    href = link.get("href", "")
    car["listing_url"] = urljoin(base_url, href) if href else None

    # Price
    price_el = card.select_one(
        "span.price, div.price, p.listing-price, [data-testid='listing-price']"
    )
    if price_el:
        car["price_kes"] = _parse_price_kes(price_el.get_text())

    # Year
    year_el = card.select_one("span.year, li.year, [data-spec='year']")
    if year_el:
        car["year_int"] = _parse_year(year_el.get_text())
    else:
        # Fall back to parsing year from title
        car["year_int"] = _parse_year(car["title"])

    # Mileage
    mileage_el = card.select_one(
        "span.mileage, li.mileage, [data-spec='mileage']"
    )
    if mileage_el:
        car["mileage_km"] = _parse_mileage(mileage_el.get_text())

    # Fuel type
    fuel_el = card.select_one("span.fuel, li.fuel, [data-spec='fuel_type']")
    if fuel_el:
        car["fuel_type"] = fuel_el.get_text(strip=True)

    # Transmission
    trans_el = card.select_one("span.transmission, li.transmission, [data-spec='transmission']")
    if trans_el:
        car["transmission"] = trans_el.get_text(strip=True)

    # Location
    loc_el = card.select_one(
        "span.location, div.location, [data-testid='listing-location']"
    )
    if loc_el:
        car["location"] = loc_el.get_text(strip=True)

    # Extract make from title (first word or known make lookup)
    words = car["title"].split()
    car["make"]       = words[1] if len(words) > 1 else None   # "2019 TOYOTA RAV4" → "TOYOTA"
    car["model_name"] = words[2] if len(words) > 2 else None   # → "RAV4"

    car["scraped_at"] = datetime.now().isoformat()
    car["source"]     = "cheki_kenya"
    return car


def scrape_page(url: str) -> list[dict]:
    """Scrape one listing page, return list of car dicts."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"  ⚠  Fetch error: {exc}")
        return []

    soup  = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select(
        "article.classified, div.vehicle-card, div[data-testid='listing-card'], li.listing-item"
    )

    results = []
    for card in cards:
        parsed = _parse_card(card, BASE_URL)
        if parsed and parsed.get("title"):
            results.append(parsed)
    return results


def get_total_pages(soup: BeautifulSoup) -> int:
    """Read highest page number from pagination."""
    pages = [1]
    for a in soup.select("a.pagination__link, ul.pagination a"):
        t = a.get_text(strip=True)
        if t.isdigit():
            pages.append(int(t))
    return max(pages)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_schema(engine):
    with engine.begin() as conn:
        conn.execute(text(_CREATE_TABLE))


def _upsert_listings(cars: list[dict], engine):
    if not cars:
        return 0
    df_ins = __import__("pandas").DataFrame(cars)
    df_ins.to_sql(
        "listings", engine,
        schema="local_market", if_exists="append",
        index=False, method="multi",
    )
    return len(df_ins)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def run(max_pages: int | None = None):
    """Scrape Cheki Kenya used-car listings and insert into local_market.listings."""
    print("🏪  Local Market Scraper — Cheki Kenya")
    engine = create_engine(DATABASE_URL, echo=False)
    _ensure_schema(engine)

    # Discover total pages from page 1
    try:
        resp = httpx.get(SEARCH_URL, headers=_HEADERS, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        soup  = BeautifulSoup(resp.text, "html.parser")
        total = get_total_pages(soup)
    except Exception as exc:
        print(f"  ❌  Could not fetch page 1: {exc}")
        return

    if max_pages:
        total = min(total, max_pages)
    print(f"  Scraping {total} page(s)...")

    all_cars: list[dict] = []
    for page in range(1, total + 1):
        url = f"{SEARCH_URL}?page={page}" if page > 1 else SEARCH_URL
        print(f"  Page {page}/{total}  ", end="")
        cars = scrape_page(url)
        all_cars.extend(cars)
        print(f"→ {len(cars)} listings | total: {len(all_cars)}")
        if page < total:
            time.sleep(REQUEST_DELAY)

    inserted = _upsert_listings(all_cars, engine)
    print(f"  ✓  {inserted} listings inserted into local_market.listings\n")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--max-pages", type=int, default=None)
    args = p.parse_args()
    run(max_pages=args.max_pages)
```

---

## Hour 15 — Architecture Notes

**File:** `docs/architecture.md`

```markdown
# Data Pipeline Architecture

## Layer Overview

```
Raw Scraper Output (JSON)
        │
        ▼
┌─────────────────────┐
│   pipeline.py       │  Loads JSON → public.cars + car_pricing
│   (Day 1)           │  Three sources: CFJ · BeForward · SBT Japan
└─────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────┐
│   run_pipeline.py   (Day 2)                     │
│                                                 │
│  normalize → currency → deduplicate → impute    │
│  → age/features → GE validate → export         │
└─────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────┐       ┌──────────────────────┐
│  curated.vehicles   │──FK──▶│  curated.prices      │
│  curated.prices     │       │  (KES + USD cols)    │
└─────────────────────┘       └──────────────────────┘
        │
        ▼
data/cleaned/vehicles_clean.parquet   ← ML input
data/exports/vehicles_clean.csv       ← analyst access
```

## Cleaning Decisions

| Decision | Reason |
|----------|--------|
| Mileage ±5% dedup tolerance | Same vehicle listed on two platforms within a week may differ by a few hundred km (odometer scroll) |
| KNN engine_cc imputation from (make, year) | Engine size is a deterministic property of a specific model-year; neighbours in make/year space are reliable predictors |
| Colour → "Unknown" sentinel | Colour has no predictive power for price in our current feature set; NULL would break one-hot encoding |
| `exceeds_kra_age_limit` flag — not filter | We keep the records for data completeness; the downstream model or business rules decide whether to exclude them |
| GE gate at 5% | Tighter than typical 10% because we are dealing with a small dataset (< 1,000 rows); a 5% violation on 400 rows = 20 bad records which is significant |
| Prices stored as float from scrapers | Eliminates redundant `parse_price()` calls in pipeline; audit trail maintained via `usd_to_kes_rate` column |

## Exchange Rate Caching

ExchangeRate-API → Redis (TTL 3600 s) → fallback hardcoded rates.
Redis key: `fx_rates:USD`. If Redis is unavailable the pipeline continues
with fallback rates and logs a warning — it never blocks.

## Field Normalisation Reference

See `pipeline/cleaning/normalizer.py` for the complete FUEL_MAP,
TRANSMISSION_MAP, BODY_TYPE_MAP, and MAKE_CANONICAL dictionaries.
```

---

## Running Everything

```bash
# 1. Apply Alembic migration (first time only)
alembic stamp 0001          # mark raw schema as baseline
alembic upgrade 0002        # create curated.vehicles + curated.prices

# 2. Run the full cleaning pipeline (reads from DB)
python -m pipeline.run_pipeline

# OR load directly from JSON (skips DB read)
python -m pipeline.run_pipeline --json data/raw/carfromjapan/carfromjapan_details_20260611.json

# 3. Launch EDA notebook
jupyter lab notebooks/02_cleaning_exploration.ipynb

# 4. Scrape Cheki Kenya (optional, max 5 pages for testing)
python api/services/local_market.py --max-pages 5
```

**Expected terminal output:**

```
🚗  Day 2 Cleaning Pipeline
────────────────────────────────────────────────────────

[1/9] Loading raw data...
  Loaded 3 raw records from DB
[2/9] Normalizing fields...
[3/9] Converting currencies...
  ✓  Live rates fetched (USD→KES: 129.50)
[4/9] Deduplicating...
  Deduplication: 0 duplicates marked (0.0% of 3 records) | 0 duplicate pairs found
[5/9] Imputing missing values...
  Imputer: engine_cc filled for 0 rows via KNN
[6/9] Age features...
  Age features: 1 record(s) exceed KRA 8-year import limit
[7/9] Engineered features...
[8/9] Running GE validation suite...

  ────────────────────────────────────────────────────────
  GE Validation: ✅ PASS
  ✅  price_positive               0/   3  (0.0%)
  ✅  year_in_range                0/   3  (0.0%)
  ✅  mileage_non_negative         0/   3  (0.0%)
  ✅  fuel_type_valid              0/   3  (0.0%)
  ✅  not_null_make                0/   3  (0.0%)
  ...
  ────────────────────────────────────────────────────────

[9/9] Inserting into curated schema...
  Inserted 3 records into curated.vehicles + curated.prices

  Exporting files...
  Exported  Parquet: data/cleaned/vehicles_clean.parquet  (0.01 MB)
            CSV:     data/exports/vehicles_clean.csv  (0.01 MB)

════════════════════════════════════════════════════════
  PIPELINE SUMMARY
...
🎉  Pipeline complete.
```

---

## Day 2 Exit Criteria Checklist

| Criterion | How to verify |
|-----------|---------------|
| `curated.vehicles` has ≥ 400 clean records | `SELECT COUNT(*) FROM curated.vehicles WHERE is_duplicate = false` |
| Parquet export ≤ 50 MB | `ls -lh data/cleaned/vehicles_clean.parquet` |
| GE validation passes < 2% violations | Printed at end of pipeline run |
| KRA age flagged records identifiable | `SELECT COUNT(*) FROM curated.vehicles WHERE exceeds_kra_age_limit = true` |
| KES + USD prices present | `SELECT vehicle_price_usd, vehicle_price_kes FROM curated.prices LIMIT 5` |
| Deduplication run | `SELECT is_duplicate, COUNT(*) FROM curated.vehicles GROUP BY 1` |
| EDA charts generated | Check `docs/` for `.png` files |


# Unified Car Scraper Suite — Normalized Field Names
### CarFromJapan · BeForward · SBT Japan · Pipeline

---

## Why Normalization?

The three scrapers previously produced incompatible field names for the same concepts:

| Concept | CarFromJapan | BeForward | SBT Japan | **Unified** |
|---------|-------------|-----------|-----------|-------------|
| Vehicle price | `car_price` `"US$ 14,285"` | `vehicle_price` `"$3,100"` | `vehicle_price` `"5,930"` | **`vehicle_price` `14285.0` (float)** |
| CnF total | `total_cnf` | `total_price` | `total_price` | **`total_price` (float)** |
| Currency | embedded in string | `"$"` | `"USD"` | **`currency: "USD"` always** |
| Reference | `reference_no` | `ref_no` ✅ | `stock_id` | **`ref_no`** |
| Grade/trim | `model_grade` | `versionclass` | `grade` ✅ | **`grade`** |
| VIN | `vin_chassis_no` | `chassis_no` ✅ | `chassis_no` ✅ | **`chassis_no`** |
| Engine | `engine_capacity` ✅ | `engine` / `engine_size` | `engine` | **`engine_capacity`** |
| Fuel | `fuel_type` ✅ | `fuel` | `fuel` | **`fuel_type`** |
| Drive | `drive_type` ✅ | `drive` | `drive` | **`drive_type`** |
| Transmission | `transmission` ✅ | `trans.` | `transmission` ✅ | **`transmission`** |
| Exterior color | `exterior_color` ✅ | `ext_color` | `body_color` | **`exterior_color`** |
| Reg. year | `registration_year` ✅ | `year` | `registration_yearmonth` | **`registration_year`** |
| Mfg. year | `manufacture_year` ✅ | `manufacture_yearmonth` | `manufacture_year` ✅ | **`manufacture_year`** |
| Images | `image_urls` ✅ | `images` | `image_urls` ✅ | **`image_urls`** |
| Delivery port | `delivery_port` ✅ | `destination_port` | ❌ missing | **`delivery_port`** |
| Accessories | `accessories` (dict) | ❌ missing | `car_options` (dict) ✅ | **`car_options` (dict)** |
| Flat features | ❌ missing | `features` (list) ✅ | ❌ missing | **`features` (list)** |
| Volume m³ | `dimension` `"14.3 m3"` | `m3` `"14.924"` ✅ | `m3` `"15.773"` ✅ | **`m3` (numeric string)** |
| WxHxL dims | ❌ not available | `dimension` `"4.64×1.72×1.87 m"` | `dimension` `"4.69m×1.69m×1.99m"` | **`dimension_raw`** |
| Source tag | ❌ missing | `source` ✅ | ❌ missing | **`source`** |

Changes are annotated inline as `# ← CHANGED: <reason>` and `# ← NEW`.

---

## Scraper 1 — CarFromJapan

### Changes Made
- `SPEC_KEY_MAP`: `"Reference No."` → `ref_no`; `"Model Grade"` → `grade`; `"VIN / Chassis No."` → `chassis_no`
- `extract_prices()`: `car_price` → `vehicle_price`; `total_cnf` → `total_price`; values now cleaned to `float`; `currency: "USD"` added
- `parse_listing_card()`: same price field renames, values now numeric
- `extract_accessories()` renamed to `extract_car_options()`; return key `"accessories"` → `"car_options"`
- `parse_detail_page()`: `"dimension"` string `"14.3 m3"` split into `m3` (numeric) + `dimension_raw: ""`; `"features"` flat list added; `"source": "carfromjapan"` added
- `DEFAULT_FIELDS` updated throughout
- `to_price()` helper added

```python
#!/usr/bin/env python3
"""
CarFromJapan – normalized output scraper.
Changes from original are annotated # ← CHANGED / # ← NEW.
"""

import time
import argparse
import re
from datetime import datetime, timezone

from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)

BASE_URL    = "https://carfromjapan.com"
START_PATH  = "/kenya/cheap-used-cars-for-sale"
PROJECT_ROOT = get_project_root()
OUTPUT_DIR  = PROJECT_ROOT / "data" / "raw" / "carfromjapan"
LOG_DIR     = PROJECT_ROOT / "logs" / "carfromjapan"

DEFAULT_MAX_PAGES = 400
PER_PAGE          = 25
REQUEST_DELAY     = 1.5

THUMB_SUFFIX            = "_100_100"
FULL_SUFFIX             = "_640_0"
EXCLUDE_IMAGE_PATTERNS  = ["banner-payment", "thumb-banner", "/public/next-desktop/"]

SPEC_KEY_MAP = {
    "Reference No."     : "ref_no",           # ← CHANGED: was "reference_no"
    "Model Code"        : "model_code",
    "Registration Year" : "registration_year",
    "Model Grade"       : "grade",             # ← CHANGED: was "model_grade"
    "Manufacture Year"  : "manufacture_year",
    "Transmission"      : "transmission",
    "Mileage"           : "mileage",
    "Engine Capacity"   : "engine_capacity",
    "Fuel Type"         : "fuel_type",
    "No. of Seats"      : "seats",
    "No. of Doors"      : "doors",
    "Steering"          : "steering",
    "Drive Type"        : "drive_type",
    "Dimension"         : "dimension",         # post-processed in parse_detail_page → m3 + dimension_raw
    "VIN / Chassis No." : "chassis_no",        # ← CHANGED: was "vin_chassis_no"
    "Exterior Color"    : "exterior_color",
    "Auction Grade"     : "auction_grade",
}

DEFAULT_FIELDS = [
    "ref_no",            # ← CHANGED: was "reference_no"
    "model_code",
    "registration_year",
    "manufacture_year",
    "grade",             # ← CHANGED: was "model_grade"
    "transmission",
    "mileage",
    "engine_capacity",
    "fuel_type",
    "seats",
    "doors",
    "steering",
    "drive_type",
    "m3",                # ← CHANGED: was "dimension" (now numeric-only field)
    "dimension_raw",     # ← NEW: empty string for CFJ (no WxHxL available)
    "exterior_color",
    "auction_grade",
    "chassis_no",        # ← CHANGED: was "vin_chassis_no"
    "vehicle_price",     # ← CHANGED: was "car_price"
    "total_price",       # ← CHANGED: was "total_cnf"
    "currency",          # ← NEW
]


# ── price helper ──────────────────────────────────────────────────────────────

def to_price(text) -> float | None:                       # ← NEW
    """Strip currency symbols and commas, return float or None.
    'US$ 14,285' → 14285.0   |   'N/A' → None
    """
    if not text or str(text).strip() in ("N/A", "-", ""):
        return None
    cleaned = re.sub(r"[^\d.]", "", str(text).replace(",", ""))
    try:
        return float(cleaned) or None
    except (ValueError, TypeError):
        return None


# ── URL helpers ───────────────────────────────────────────────────────────────

def listing_url(page: int) -> str:
    return f"{BASE_URL}{START_PATH}?page={page}" if page > 1 else f"{BASE_URL}{START_PATH}"

def normalise_src(src: str) -> str:
    if src.startswith("//"):
        src = "https:" + src
    elif src.startswith("/"):
        src = BASE_URL + src
    if src.endswith(THUMB_SUFFIX):
        src = src[:-len(THUMB_SUFFIX)] + FULL_SUFFIX
    return src

def is_valid_image(src: str) -> bool:
    return not any(pat in src for pat in EXCLUDE_IMAGE_PATTERNS)


# ── Listing parser ────────────────────────────────────────────────────────────

def parse_listing_card(card) -> dict:
    data = {}
    title_tag = card.select_one("h3 a")
    if title_tag:
        data["title"] = clean(title_tag.get_text())
        href = title_tag.get("href", "")
        data["url"] = BASE_URL + href if href.startswith("/") else href
    else:
        data["title"] = data["url"] = ""

    compare_div = card.select_one("[id^='compare-']")
    if compare_div:
        raw = compare_div.get_text(strip=True)
        data["cfj_id"] = raw.replace("Compare (", "").rstrip(")")

    photo_btn = card.select_one(".z-3")
    if photo_btn:
        m = re.search(r"\((\d+)\)", clean(photo_btn.get_text()))
        data["photo_count"] = int(m.group(1)) if m else None

    for row in card.select("div.flex.mt-2\\.5"):
        for item in row.find_all("div", class_=lambda c: c and "flex-1" in c, recursive=False):
            label_el = item.select_one(".text-xs")
            value_el = label_el.find_next_sibling() if label_el else None
            if not (label_el and value_el):
                continue
            label = clean(label_el.get_text()).lower().replace(" ", "_")
            value = clean(value_el.get_text())
            if value and value != "-":
                data[label] = value

    price_box = card.select_one(".relative.w-61")
    if price_box:
        car_price_el = price_box.select_one(".car-price")
        if car_price_el:
            data["vehicle_price"] = to_price(car_price_el.get_text())  # ← CHANGED: was "car_price"; now float
        delivery_el = price_box.select_one(".max-w-35.line-clamp-1")
        if delivery_el:
            data["delivery_port"] = clean(delivery_el.get_text())
        total_el = price_box.select_one(".car-price.font-bold")
        if total_el:
            data["total_price"] = to_price(total_el.get_text())         # ← CHANGED: was "total_cnf"; now float

    img = card.select_one("img[alt*='CFJ']")
    if img:
        src = img.get("src", "")
        data["thumbnail_url"] = ("https:" + src) if src.startswith("//") else src

    return data


# ── Stage 1: listing pages ────────────────────────────────────────────────────

def scrape_listings(logger, max_pages: int = DEFAULT_MAX_PAGES) -> dict:
    cars = {}
    consecutive_empty = 0
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(REQUEST_DELAY)
        url = listing_url(page)
        logger.info(f"[listing] page {page}/{max_pages} → {url}")
        soup = fetch(url, logger=logger)
        if soup is None:
            consecutive_empty += 1
            logger.warning(f"Page {page} fetch failed, consecutive={consecutive_empty}")
        else:
            cards = soup.select('[data-testid="car-item-list"]')
            for card in cards:
                car = parse_listing_card(card)
                if car.get("url"):
                    cars[car["url"]] = car
            found = len(cards)
            logger.info(f"Page {page}: {found} cards | total: {len(cars)}")
            consecutive_empty = 0 if found else consecutive_empty + 1
        if consecutive_empty >= 5:
            logger.error("5 consecutive empty pages – stopping")
            break
    logger.info(f"Stage 1 complete – {len(cars)} cars collected")
    return cars


# ── Stage 2: detail page parsers ─────────────────────────────────────────────

def extract_images(soup) -> list:
    urls, seen = [], set()
    def add(src):
        src = normalise_src(src)
        if src and is_valid_image(src) and src not in seen:
            seen.add(src)
            urls.append(src)

    thumb_nav = soup.select_one('nav[aria-label="Thumbnail Navigation"]')
    if thumb_nav:
        for img in thumb_nav.select("button.image-gallery-thumbnail img"):
            if src := img.get("src", ""):
                add(src)
    for slide_img in soup.select("div.image-gallery-slide img"):
        alt = slide_img.get("alt", "")
        if "CFJ" in alt or "image" in alt.lower():
            if src := slide_img.get("src", ""):
                add(src)
    return urls


def extract_specs(soup) -> dict:
    specs = {}
    table = soup.select_one("div.border-t-primary table, table.w-full.table-fixed")
    if not table:
        return specs
    for row in table.select("tbody tr"):
        cells = row.find_all("td", recursive=False)
        for i in range(0, len(cells) - 1, 2):
            label_cell, value_cell = cells[i], cells[i + 1]
            if label_cell.get("colspan") or value_cell.get("colspan"):
                continue
            raw_label = clean(label_cell.get_text())
            raw_value = clean(value_cell.get_text())
            if not raw_label or raw_value in ("", "-"):
                continue
            key = SPEC_KEY_MAP.get(raw_label, raw_label.lower().replace(" ", "_").replace(".", ""))
            specs[key] = raw_value
    return specs


def extract_car_options(soup) -> dict:            # ← CHANGED: renamed from extract_accessories
    """Return categorized options dict: {category: [feature, ...]}"""
    car_options = {}                              # ← CHANGED: was accessories = {}
    heading = soup.find("h2", string=re.compile(r"Accessories", re.I))
    if not heading:
        return car_options
    wrapper = heading.find_parent("div", class_=lambda c: c and "w-full" in c)
    if not wrapper:
        return car_options
    for section in wrapper.select("div.pt-4\\.5"):
        cat_el = section.select_one("p.font-semibold")
        if not cat_el:
            continue
        category = clean(cat_el.get_text())
        items = [
            clean(s.get_text())
            for s in section.select("span.text-\\[13px\\]")
            if clean(s.get_text())
        ]
        if items:
            car_options[category] = items
    return car_options


def extract_prices(soup) -> dict:
    prices = {"currency": "USD"}                  # ← NEW: always emit currency key
    els = soup.select(".car-price")
    if els:
        prices["vehicle_price"] = to_price(els[0].get_text())    # ← CHANGED: was "car_price"; now float
    for el in els:
        if "font-bold" in (el.get("class") or []):
            prices["total_price"] = to_price(el.get_text())      # ← CHANGED: was "total_cnf"; now float
            break
    return prices


def extract_title(soup) -> str:
    h1 = soup.find("h1")
    if h1:
        return clean(h1.get_text())
    title_tag = soup.find("title")
    if title_tag:
        return clean(title_tag.get_text()).split("|")[0].strip()
    return ""


def parse_detail_page(url: str, soup, logger) -> dict:
    specs = extract_specs(soup)

    # ← NEW: CFJ 'dimension' is "14.3 m3" — split into m3 (numeric) + empty dimension_raw
    if "dimension" in specs:
        dim_str = specs.pop("dimension")
        m = re.search(r"([\d.]+)", dim_str)
        specs["m3"]            = m.group(1) if m else ""
        specs["dimension_raw"] = ""            # CFJ does not provide WxHxL

    car_options = extract_car_options(soup)    # ← CHANGED: was extract_accessories

    data = {
        "car_url"      : url,
        "source"       : "carfromjapan",       # ← NEW
        "scraped_at"   : datetime.now(timezone.utc).isoformat(),
        "title"        : extract_title(soup),
        **specs,
        **extract_prices(soup),
        "car_options"  : car_options,          # ← CHANGED: was "accessories"
        "features"     : [                     # ← NEW: flat list (flattened car_options)
            item
            for items in car_options.values()
            for item in items
        ],
        "image_urls"   : extract_images(soup),
    }

    for field in DEFAULT_FIELDS:
        data.setdefault(field, "")

    logger.info(f"[detail] ref={data.get('ref_no', '?')}  images={len(data['image_urls'])}")  # ← CHANGED: ref_no
    return data


def scrape_detail(url: str, logger):
    soup = fetch(url, logger=logger)
    if soup is None:
        return None
    return parse_detail_page(url, soup, logger)


def scrape_details(listing_cars: dict, logger) -> dict:
    results = {}
    total = len(listing_cars)
    for idx, url in enumerate(listing_cars.keys(), 1):
        logger.info(f"[detail] {idx}/{total} {url}")
        detail = scrape_detail(url, logger)
        if detail:
            for key in ("cfj_id", "photo_count", "delivery_port", "thumbnail_url"):
                if key in listing_cars[url] and key not in detail:
                    detail[key] = listing_cars[url][key]
            results[url] = detail
        else:
            logger.warning(f"Skipped {url}")
        if idx < total:
            time.sleep(REQUEST_DELAY)
    logger.info(f"Stage 2 complete – {len(results)} / {total} cars scraped")
    return results


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run(max_pages: int = DEFAULT_MAX_PAGES):
    logger = my_logger("carfromjapan", log_dir=LOG_DIR)
    logger.info("CarFromJapan scraper started")
    listing_cars = scrape_listings(logger, max_pages)
    if not listing_cars:
        logger.error("No listing URLs found, exiting.")
        return
    details = scrape_details(listing_cars, logger)
    out_file = OUTPUT_DIR / f"carfromjapan_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_to_json(details, out_file, logger)
    logger.info(f"Pipeline complete – {len(details)} cars saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    args = parser.parse_args()
    run(max_pages=args.max_pages)
```

---

## Scraper 2 — BeForward

### Changes Made
- `FIELD_NORMALISATION` dict added — applied after every spec parse to rename keys in bulk
- `apply_normalisation()` helper added
- `to_price()` helper added
- `parse_pricing()`: `destination_port` → `delivery_port`; `currency: "$"` → `"USD"`; all price values now `float`
- `parse_specs_table()`: `FIELD_NORMALISATION` applied; `manufacture_yearmonth` → `manufacture_year` (year extracted); `registration_yearmonth` → `registration_year`
- `parse_pickup_specs()`: `FIELD_NORMALISATION` applied (`trans.`→`transmission`, `year`→`registration_year`, etc.)
- `parse_detail_page()`: `images` → `image_urls`; `car_options: {}` added; `dimension` key in full spec → `dimension_raw`

```python
#!/usr/bin/env python3
"""
BeForward – normalized output scraper.
Changes from original are annotated # ← CHANGED / # ← NEW.
"""

import time
import re
from urllib.parse import urljoin
from datetime import datetime

from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)

BASE_URL    = "https://www.beforward.jp"
START_URL   = "https://www.beforward.jp/stocklist/sar=steering/steering=Right/tp_country_id=27"
PROJECT_ROOT = get_project_root()
OUTPUT_DIR  = PROJECT_ROOT / "data" / "raw" / "beforward"
LOG_DIR     = PROJECT_ROOT / "logs" / "beforward"

DEFAULT_MAX_PAGES = None
REQUEST_DELAY     = 1.5

# ← NEW: maps every BeForward-specific key → unified schema name.
#   Applied to both parse_pickup_specs and parse_specs_table output.
FIELD_NORMALISATION = {
    "fuel"                 : "fuel_type",        # spec table "Fuel"          → fuel_type
    "drive"                : "drive_type",        # spec table "Drive"         → drive_type
    "ext_color"            : "exterior_color",    # slugify("Ext. Color")      → exterior_color
    "engine_size"          : "engine_capacity",   # spec table "Engine Size"   → engine_capacity
    "engine"               : "engine_capacity",   # pickup spec "Engine"       → engine_capacity
    "versionclass"         : "grade",             # spec table "VersionClass"  → grade
    "trans"                : "transmission",      # slugify("Trans.")          → transmission
    "year"                 : "registration_year", # pickup spec "Year"         → registration_year
    "dimension"            : "dimension_raw",     # WxHxL string e.g. "4.64×1.72×1.87 m"
}


def to_price(text) -> float | None:               # ← NEW
    """'$3,100' → 3100.0  |  'N/A' → None"""
    if not text or str(text).strip() in ("N/A", "-", ""):
        return None
    cleaned = re.sub(r"[^\d.]", "", str(text).replace(",", ""))
    try:
        return float(cleaned) or None
    except (ValueError, TypeError):
        return None


def apply_normalisation(d: dict, mapping: dict) -> dict:    # ← NEW
    """Rename keys in d according to mapping. Modifies in-place, returns d."""
    for old_key, new_key in mapping.items():
        if old_key in d:
            d[new_key] = d.pop(old_key)
    return d


# ── Listing / URL collection (unchanged) ─────────────────────────────────────

def get_total_pages(soup, logger):
    pages = [1]
    for a in soup.select("div.results-pagination ul li a"):
        text = a.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    total = max(pages)
    logger.info(f"Total pages detected: {total:,}")
    return total

def build_page_url(base_url, page):
    if page == 1:
        return base_url
    return base_url.replace("/stocklist/", f"/stocklist/page={page}/", 1)

def extract_vehicle_urls(soup, logger) -> list:
    urls, seen = [], set()
    for row in soup.select("tr.stocklist-row"):
        if not row.select_one("td.photo-col"):
            continue
        if row.select_one("div.price-col-sold"):
            logger.debug("Skipping SOLD listing")
            continue
        link = row.select_one("a.vehicle-url-link")
        if not link:
            continue
        href = link.get("href", "").strip()
        if not href or href in seen:
            continue
        if re.match(r"^/[^/]+/[^/]+/[^/]+/id/\d+/$", href):
            full_url = urljoin(BASE_URL, href)
            urls.append(full_url)
            seen.add(href)
            logger.debug("Found: %s", full_url)
    return urls

def scrape_vehicle_urls(logger, max_pages=None) -> list:
    all_urls = []
    soup = fetch(START_URL, logger=logger)
    if soup is None:
        return all_urls
    total_pages = get_total_pages(soup, logger)
    if max_pages:
        total_pages = min(total_pages, max_pages)
        logger.info(f"Capped at {max_pages} pages")
    page_urls = extract_vehicle_urls(soup, logger)
    all_urls.extend(page_urls)
    logger.info(f"Page 1/{total_pages} → {len(page_urls)} | Total: {len(all_urls)}")
    for page in range(2, total_pages + 1):
        url = build_page_url(START_URL, page)
        soup = fetch(url, logger=logger)
        if soup is None:
            logger.error(f"Page {page} failed, stopping.")
            break
        page_urls = extract_vehicle_urls(soup, logger)
        if not page_urls:
            logger.warning(f"Page {page}: no URLs found – stopping early")
            break
        all_urls.extend(page_urls)
        logger.info(f"Page {page}/{total_pages} → {len(page_urls)} | Total: {len(all_urls)}")
        time.sleep(REQUEST_DELAY)
    logger.info(f"Phase 1 complete — {len(all_urls)} URLs collected")
    return all_urls


# ── Detail parsers ────────────────────────────────────────────────────────────

def parse_title_and_ref(soup):
    """ref_no already matches unified schema — unchanged."""
    title_tag = soup.select_one("div.car-info-flex-box h1")
    title = clean(title_tag.get_text()) if title_tag else "N/A"
    ref_tag = soup.select_one("div.detail-specs-text")
    ref_text = clean(ref_tag.get_text()) if ref_tag else ""
    parts = ref_text.split()
    model_code = parts[0] if parts else "N/A"
    ref_no     = parts[1] if len(parts) > 1 else "N/A"
    return {"title": title, "model_code": model_code, "ref_no": ref_no}


def parse_pricing(soup):
    price = soup.select_one("span.price.ip-usd-price")
    total = soup.select_one("span#fn-vehicle-price-total-price")
    orig  = soup.select_one("p.original-vehicle-price")
    save  = soup.select_one("p#fn-current-save-rate")
    port  = soup.select_one("p.destination-port")
    quote = soup.select_one("span#fn-vehicle-price-quote-type")
    return {
        "currency"      : "USD",                                                     # ← CHANGED: was "$"
        "vehicle_price" : to_price(price.get_text() if price else None),             # ← CHANGED: now float
        "total_price"   : to_price(total.get_text() if total else None),             # ← CHANGED: now float
        "original_price": to_price(orig.get_text()  if orig  else None),             # ← CHANGED: now float
        "discount_rate" : clean(save.get_text()) if save else None,
        "delivery_port" : clean(port.get_text(separator=" ")) if port else None,     # ← CHANGED: was "destination_port"
        "quote_type"    : clean(quote.get_text()) if quote else None,
    }


def parse_specs_table(soup) -> dict:
    """
    Full specification table.
    FIELD_NORMALISATION applied after parsing; manufacture/registration dates
    extracted to unified field names.
    """
    specs = {}
    table = soup.select_one("table.specification")
    if not table:
        return specs
    for row in table.select("tr"):
        cells = row.find_all(["th", "td"])
        for i in range(0, len(cells) - 1, 2):
            label = clean(cells[i].get_text(separator=" ")).lower()
            value = clean(cells[i + 1].get_text()) if i + 1 < len(cells) else ""
            label = re.sub(r"\s+", "_", label).strip("_")
            key   = slugify(label)
            if key and value:
                specs[key] = value

    apply_normalisation(specs, FIELD_NORMALISATION)   # ← NEW: bulk key rename

    # ← NEW: extract year-only from "2009/2" → manufacture_year: "2009"
    if "manufacture_yearmonth" in specs:
        mym = specs.pop("manufacture_yearmonth")
        specs.setdefault("manufacture_year", mym.split("/")[0])

    # ← NEW: registration_yearmonth → registration_year (keep full "2009/4" string)
    if "registration_yearmonth" in specs:
        specs.setdefault("registration_year", specs.pop("registration_yearmonth"))

    return specs


def parse_pickup_specs(soup) -> dict:
    """
    Summary bar below the main photo.
    FIELD_NORMALISATION applied: trans.→transmission, year→registration_year, etc.
    """
    specs = {}
    table = soup.select_one("div.pickup-specification table")
    if not table:
        return specs
    rows = table.select("tr")
    if len(rows) < 2:
        return specs
    headers = [clean(td.get_text()).lower() for td in rows[0].select("td")]
    values  = [clean(td.get_text(separator=" ")) for td in rows[1].select("td")]
    for h, v in zip(headers, values):
        specs[re.sub(r"\s+", "_", h)] = v

    apply_normalisation(specs, FIELD_NORMALISATION)   # ← NEW: bulk key rename
    return specs


def parse_location(soup):
    tag = soup.select_one("span.specs-pickup-icon b")
    return {"location": clean(tag.get_text()) if tag else None}


def parse_features(soup) -> list:
    """Flat feature list — already matches unified schema."""
    features = []
    for li in soup.select("div.remarks li"):
        if "attached_on" in li.get("class", []):
            features.append(clean(li.get_text()))
    return features


def parse_images(soup) -> list:
    """Image URLs collected here; renamed to image_urls in parse_detail_page."""
    images, seen = [], set()
    for inp in soup.select("input.fn-images-pc"):
        path = inp.get("data-path", "")
        if path and path not in seen:
            images.append(("https:" + path) if path.startswith("//") else path)
            seen.add(path)
    return images


def parse_total_image_count(soup):
    tag = soup.select_one("span#fn-slider-total")
    try:
        return int(tag.get_text(strip=True)) if tag else 0
    except ValueError:
        return 0


def parse_detail_page(soup, car_url, logger):
    title_ref   = parse_title_and_ref(soup)
    pricing     = parse_pricing(soup)
    location    = parse_location(soup)
    pickup      = parse_pickup_specs(soup)
    specs       = parse_specs_table(soup)
    features    = parse_features(soup)
    images      = parse_images(soup)
    image_count = parse_total_image_count(soup)

    car = {
        "car_url"     : car_url,
        "source"      : "beforward",                   # already present ✅
        "scraped_at"  : datetime.now().isoformat(),
        **title_ref,
        **pricing,
        **location,
        **pickup,                                      # normalized keys via apply_normalisation
        **specs,                                       # normalized keys via apply_normalisation
        "features"    : features,                      # flat list ✅
        "car_options" : {},                            # ← NEW: empty dict (no categories in BeForward)
        "image_urls"  : images,                        # ← CHANGED: was "images"
        "image_count" : image_count,
    }

    logger.info(
        f"Parsed: {title_ref.get('title')} | "
        f"Ref: {title_ref.get('ref_no')} | "
        f"Price: {pricing.get('vehicle_price')} | "
        f"Images: {image_count}"
    )
    return car


def scrape_detail(url, logger):
    soup = fetch(url, logger=logger)
    if soup is None:
        logger.error(f"Failed to fetch {url}")
        return None
    return parse_detail_page(soup, url, logger)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run(max_pages=DEFAULT_MAX_PAGES):
    logger = my_logger("beforward", log_dir=LOG_DIR)
    logger.info("Beforward scraper started")
    urls = scrape_vehicle_urls(logger, max_pages)
    if not urls:
        logger.error("No URLs found, exiting.")
        return
    all_cars = []
    for idx, url in enumerate(urls, 1):
        logger.info(f"Scraping {idx}/{len(urls)}: {url}")
        car = scrape_detail(url, logger)
        if car:
            all_cars.append(car)
        time.sleep(REQUEST_DELAY)
    out_file = OUTPUT_DIR / f"beforward_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_to_json(all_cars, out_file, logger)
    logger.info(f"Pipeline complete – {len(all_cars)} cars saved.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()
    run(max_pages=args.max_pages)
```

---

## Scraper 3 — SBT Japan

### Changes Made
- `SPEC_NORMALISATION` and `INFO_NORMALISATION` dicts added
- `apply_normalisation()` helper added
- `to_price()` helper added
- `parse_identification()`: `stock_id` → `ref_no`
- `parse_pricing()`: all values now `float`; `currency` hardcoded `"USD"`
- `parse_car_specs()`: `SPEC_NORMALISATION` applied (`engine`→`engine_capacity`, `fuel`→`fuel_type`, `drive`→`drive_type`, `body_color`→`exterior_color`)
- `parse_info_lists()`: `INFO_NORMALISATION` applied (`registration_yearmonth`→`registration_year`, `dimension`→`dimension_raw`)
- `parse_individual_car_page()`: `source: "sbtjapan"` added; `features` flat list added; `delivery_port: ""` added; logger updated to use `ref_no`

```python
#!/usr/bin/env python3
"""
SBTJapan – normalized output scraper.
Changes from original are annotated # ← CHANGED / # ← NEW.
"""

import re
import time
from urllib.parse import urljoin
from datetime import datetime

from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)

BASE_SEARCH_URL = "https://www.sbtjapan.com/used-cars/search"
PROJECT_ROOT    = get_project_root()
OUTPUT_DIR      = PROJECT_ROOT / "data" / "raw" / "sbtjapan"
LOG_DIR         = PROJECT_ROOT / "logs" / "sbtjapan"

DEFAULT_MAX_PAGES = None
REQUEST_DELAY     = 1.5

# ← NEW: maps SBT spec item keys (after slugify) → unified schema names
SPEC_NORMALISATION = {
    "engine"     : "engine_capacity",   # spec item "Engine"      → engine_capacity
    "fuel"       : "fuel_type",         # spec item "Fuel"        → fuel_type
    "drive"      : "drive_type",        # spec item "Drive"       → drive_type
    "body_color" : "exterior_color",    # spec item "Body Color"  → exterior_color
}

# ← NEW: maps info-list keys (after slugify) → unified schema names
INFO_NORMALISATION = {
    "registration_yearmonth": "registration_year",  # keep full "2009/4" string
    "dimension"             : "dimension_raw",       # WxHxL string
}


def to_price(text) -> float | None:                  # ← NEW
    """'5,930' → 5930.0  |  'N/A' → None"""
    if not text or str(text).strip() in ("N/A", "-", ""):
        return None
    cleaned = re.sub(r"[^\d.]", "", str(text).replace(",", ""))
    try:
        return float(cleaned) or None
    except (ValueError, TypeError):
        return None


def apply_normalisation(d: dict, mapping: dict) -> dict:   # ← NEW
    """Rename keys in d according to mapping. Modifies in-place, returns d."""
    for old_key, new_key in mapping.items():
        if old_key in d:
            d[new_key] = d.pop(old_key)
    return d


# ── URL collection (unchanged) ────────────────────────────────────────────────

def get_total_pages(soup) -> int:
    pages = []
    for link in soup.select("a.pagination__link"):
        text = link.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    return max(pages) if pages else 1

def get_car_detail_urls(search_url, logger, max_pages=None):
    detail_urls = []
    logger.info(f"Fetching page 1: {search_url}")
    soup = fetch(search_url, logger=logger)
    if soup is None:
        return detail_urls
    total_pages = get_total_pages(soup)
    if max_pages:
        total_pages = min(total_pages, max_pages)
    logger.info(f"Total pages: {total_pages}")
    for anchor in soup.select("a.card-product__wrap"):
        href = anchor.get("href", "")
        if href:
            detail_urls.append(urljoin("https://www.sbtjapan.com", href))
    for page in range(2, total_pages + 1):
        paged_url = f"{search_url}?page={page}"
        logger.info(f"Fetching page {page}/{total_pages} | URLs so far: {len(detail_urls)}")
        soup = fetch(paged_url, logger=logger)
        if soup is None:
            logger.error(f"Failed on page {page}, stopping.")
            break
        for anchor in soup.select("a.card-product__wrap"):
            href = anchor.get("href", "")
            if href:
                detail_urls.append(urljoin("https://www.sbtjapan.com", href))
        time.sleep(REQUEST_DELAY)
    logger.info(f"Done — {len(detail_urls)} detail URLs collected")
    return detail_urls


# ── Detail parsers ────────────────────────────────────────────────────────────

def parse_header(soup):
    """Unchanged — manufacture_year already correct."""
    name_tag = soup.select_one("h1.product-detail__name")
    title = clean(name_tag.get_text()) if name_tag else "N/A"
    detail_items = [clean(el.get_text()) for el in soup.select("div.product-detail__detail-item")]
    return {
        "title"           : title,
        "model_code"      : detail_items[0] if len(detail_items) > 0 else "N/A",
        "manufacture_year": detail_items[1] if len(detail_items) > 1 else "N/A",
        "body_type"       : detail_items[2] if len(detail_items) > 2 else "N/A",
    }


def parse_identification(soup):
    stock_tag    = soup.select_one("span.product-detail__id-number")
    location_tag = soup.select_one("div.product-detail__location-country")
    return {
        "ref_no"  : clean(stock_tag.get_text())    if stock_tag    else "N/A",  # ← CHANGED: was "stock_id"
        "location": clean(location_tag.get_text()) if location_tag else "N/A",
    }


def parse_pricing(soup):
    base_price    = soup.select_one("span.product-detail__base-price-range")
    base_currency = soup.select_one("span.product-detail__base-price-currency")
    total_tag     = soup.select_one("div#total_amount")

    def get_detail(el_id) -> float | None:                     # ← CHANGED: now returns float
        el = soup.select_one(f"div#{el_id}")
        return to_price(el.get_text()) if el else None

    return {
        "currency"               : "USD",                      # ← CHANGED: was parsed from element
        "vehicle_price"          : to_price(base_price.get_text() if base_price else None),  # ← CHANGED: now float
        "total_price"            : to_price(total_tag.get_text() if total_tag else None),    # ← CHANGED: now float
        "freight_amount"         : get_detail("freight_amount"),
        "inspection_amount"      : get_detail("inspection_amount"),
        "insurance_amount"       : get_detail("insurance_amount"),
        "vanning_amount"         : get_detail("vanning_amount"),
        "vehicle_price_breakdown": get_detail("vehicle_price"),
    }


def parse_car_specs(soup) -> dict:
    """
    Status-area spec items → snake_case dict.
    SPEC_NORMALISATION applied to rename engine/fuel/drive/body_color.
    """
    specs = {}
    for item in soup.select("div.product-detail__status-item"):
        label_el = item.select_one("div.product-detail__status-label")
        value_el = item.select_one("div.product-detail__status-value")
        if label_el and value_el:
            key = slugify(clean(label_el.get_text()).lower().replace(" ", "_"))
            if key == "door":
                key = "doors"
            specs[key] = clean(value_el.get_text())

    apply_normalisation(specs, SPEC_NORMALISATION)    # ← NEW: bulk key rename
    return specs


def parse_info_lists(soup) -> dict:
    """
    Additional info blocks.
    INFO_NORMALISATION applied: registration_yearmonth→registration_year, dimension→dimension_raw.
    """
    info = {}
    for block in soup.select("div.product-detail__info-block"):
        for item in block.select("li.product-detail__info-item"):
            label_el = item.select_one("div.product-detail__info-label")
            value_el = item.select_one("div.product-detail__info-value")
            if label_el and value_el:
                key = slugify(clean(label_el.get_text()).lower().replace(" ", "_"))
                info[key] = clean(value_el.get_text())

    apply_normalisation(info, INFO_NORMALISATION)     # ← NEW: bulk key rename
    return info


def parse_image_urls(soup) -> list:                   # name already matches schema ✅
    urls = []
    gallery = soup.select_one("div.product-detail__gallery-slider")
    if gallery:
        for slide in gallery.select("div.swiper-slide"):
            img = slide.select_one("div.product-detail__main-image img")
            if img and img.get("src"):
                urls.append(img["src"])
    return urls


def parse_options(soup) -> dict:                      # car_options — already correct name ✅
    options = {}
    for block in soup.select("div.product-detail__option-block"):
        cat_el = block.select_one("div.product-detail__option-category")
        if not cat_el:
            continue
        category  = clean(cat_el.get_text())
        available = [
            clean(el.get_text())
            for el in block.select("div.product-detail__option-item.-available")
        ]
        if available:
            options[category] = available
    return options


def parse_modal_fields(soup) -> dict:
    """Hidden form fields — unchanged (grade, make, mileage_raw already correct)."""
    fields = {}
    field_map = {
        "make"     : "make",
        "model"    : "model",
        "name"     : "model_name",
        "year"     : "manufacture_year",
        "month"    : "manufacture_month",
        "grade"    : "grade",
        "make_id"  : "make_id",
        "body_type": "body_type",
        "mileage"  : "mileage_raw",
    }
    for field, key in field_map.items():
        inp = soup.select_one(f'form#get_estimate_id input[name="{field}"]')
        if inp:
            fields[key] = inp.get("value", "").strip()
    return fields


def parse_engagement(soup):
    view    = soup.select_one("div.product-detail__view-counter")
    fav     = soup.select_one("div.product-detail__favorite-counter")
    rating  = soup.select_one("span.avg-score")
    reviews = soup.select_one("span.reviews-qa-label")
    return {
        "view_count"     : clean(view.get_text())    if view    else "N/A",
        "favourite_count": clean(fav.get_text())     if fav     else "N/A",
        "rating"         : clean(rating.get_text())  if rating  else "N/A",
        "reviews"        : clean(reviews.get_text()) if reviews else "N/A",
    }


def parse_individual_car_page(soup, car_url, logger):
    header      = parse_header(soup)
    ident       = parse_identification(soup)
    pricing     = parse_pricing(soup)
    specs       = parse_car_specs(soup)
    info        = parse_info_lists(soup)
    images      = parse_image_urls(soup)
    car_options = parse_options(soup)
    modal       = parse_modal_fields(soup)
    engagement  = parse_engagement(soup)

    car = {
        "car_url"      : car_url,
        "source"       : "sbtjapan",                    # ← NEW
        "scraped_at"   : datetime.now().isoformat(),
        **header,
        **ident,
        **pricing,
        **modal,
        **specs,                                        # engine_capacity, fuel_type, drive_type, exterior_color
        **info,                                         # registration_year, dimension_raw, chassis_no…
        **engagement,
        "car_options"  : car_options,                   # name already correct ✅
        "features"     : [                              # ← NEW: flat list from car_options
            item
            for items in car_options.values()
            for item in items
        ],
        "image_urls"   : images,                        # name already correct ✅
        "delivery_port": "",                            # ← NEW: SBT doesn't expose delivery port
    }

    logger.info(
        f"Parsed {ident.get('ref_no')} | "              # ← CHANGED: was stock_id
        f"{header.get('title')} | "
        f"{len(images)} images | "
        f"{sum(len(v) for v in car_options.values())} options"
    )
    return car


def scrape_detail(car_url, logger):
    soup = fetch(car_url, logger=logger)
    if soup is None:
        logger.error(f"Failed to fetch {car_url}")
        return {}
    return parse_individual_car_page(soup, car_url, logger)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run(search_url: str = BASE_SEARCH_URL, max_pages: int = DEFAULT_MAX_PAGES):
    logger = my_logger("sbtjapan", log_dir=LOG_DIR)
    logger.info("SBTJapan scraper started")
    urls = get_car_detail_urls(search_url, logger, max_pages)
    if not urls:
        logger.error("No URLs found, exiting.")
        return
    all_cars = []
    for idx, url in enumerate(urls, 1):
        logger.info(f"Scraping {idx}/{len(urls)}: {url}")
        car = scrape_detail(url, logger)
        if car:
            all_cars.append(car)
        time.sleep(REQUEST_DELAY)
    out_file = OUTPUT_DIR / f"sbtjapan_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_to_json(all_cars, out_file, logger)
    logger.info(f"Pipeline complete – {len(all_cars)} cars saved.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()
    run(max_pages=args.max_pages)
```

---

## Updated Pipeline (`pipeline.py`)

### Changes Made
- `transform()` no longer branches per source for field names — all fields are now unified
- `source` is read directly from the scraper output (`raw.get("source")`) instead of inferred
- Price values are now `float` from scrapers so no `parse_price()` calls needed in `transform()`
- `features` insert logic simplified: uses `car_options` dict (CFJ/SBT) or flat `features` list (BeForward) — no per-source conditional needed beyond that
- `extra_data` built generically from a fixed set of overflow keys
- All per-source field-name aliases (`car_price`, `total_cnf`, `reference_no`, etc.) removed from `transform()`

```python
#!/usr/bin/env python3
"""
Car Inventory Pipeline — updated for normalized scraper output
=============================================================
Schema creation → TRUNCATE → Load JSON → Insert → Verify

Because all three scrapers now emit the same field names,
transform() is source-agnostic. Per-source branching is gone.
"""

import json
import re
import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/car_inventory"
)
JSON_FILE = os.getenv("JSON_FILE", "scraped_cars.json")

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA DDL (unchanged from previous version)
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cars (
    id                SERIAL        PRIMARY KEY,
    source            VARCHAR(30)   NOT NULL,
    car_url           TEXT          UNIQUE NOT NULL,
    ref_no            VARCHAR(100),
    title             VARCHAR(300),
    make              VARCHAR(100),
    model_name        VARCHAR(100),
    model_code        VARCHAR(100),
    grade             VARCHAR(200),
    body_type         VARCHAR(100),
    registration_year VARCHAR(20),
    manufacture_year  VARCHAR(10),
    mileage           VARCHAR(100),
    mileage_km        INTEGER,
    engine_capacity   VARCHAR(30),
    transmission      VARCHAR(20),
    fuel_type         VARCHAR(30),
    drive_type        VARCHAR(30),
    steering          VARCHAR(10),
    seats             SMALLINT,
    doors             SMALLINT,
    exterior_color    VARCHAR(50),
    chassis_no        VARCHAR(100),
    dimension_m3      NUMERIC(8, 3),
    dimension_raw     VARCHAR(100),
    weight_kg         VARCHAR(30),
    delivery_port     VARCHAR(100),
    source_location   VARCHAR(100),
    extra_data        JSONB,
    scraped_at        TIMESTAMPTZ,
    loaded_at         TIMESTAMPTZ   DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS car_pricing (
    id                SERIAL        PRIMARY KEY,
    car_id            INTEGER       NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    currency          VARCHAR(10)   DEFAULT 'USD',
    vehicle_price     NUMERIC(12,2),
    total_price       NUMERIC(12,2),
    original_price    NUMERIC(12,2),
    discount_rate     VARCHAR(20),
    freight_amount    NUMERIC(12,2),
    inspection_amount NUMERIC(12,2),
    insurance_amount  NUMERIC(12,2),
    vanning_amount    NUMERIC(12,2)
);
CREATE TABLE IF NOT EXISTS car_features (
    id       SERIAL       PRIMARY KEY,
    car_id   INTEGER      NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    category VARCHAR(100),
    feature  VARCHAR(255) NOT NULL
);
CREATE TABLE IF NOT EXISTS car_images (
    id            SERIAL   PRIMARY KEY,
    car_id        INTEGER  NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    image_url     TEXT     NOT NULL,
    is_thumbnail  BOOLEAN  DEFAULT FALSE,
    display_order SMALLINT DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cars_source   ON cars(source);
CREATE INDEX IF NOT EXISTS idx_cars_mileage  ON cars(mileage_km);
CREATE INDEX IF NOT EXISTS idx_price_vehicle ON car_pricing(vehicle_price);
CREATE INDEX IF NOT EXISTS idx_feat_car      ON car_features(car_id);
CREATE INDEX IF NOT EXISTS idx_img_car       ON car_images(car_id);
"""


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def parse_int(val) -> int | None:
    """Extract integer from mileage strings. '45,000 km(Approx...)' → 45000"""
    if val is None:
        return None
    segment = str(val).split("km")[0].replace(",", "")
    digits  = re.sub(r"[^\d]", "", segment)
    return int(digits) if digits else None


def detect_source(url: str) -> str:
    """Fallback source detection for legacy JSON that lacks a 'source' key."""
    u = url.lower()
    if "carfromjapan" in u: return "carfromjapan"
    if "beforward"    in u: return "beforward"
    if "sbtjapan"     in u: return "sbtjapan"
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFORM — now source-agnostic thanks to normalized scrapers
# ─────────────────────────────────────────────────────────────────────────────
def transform(raw: dict):
    """
    ← SIMPLIFIED vs previous version:
      • No per-source if/elif blocks for field names
      • Prices are already floats — no parse_price() needed
      • 'source' comes directly from scraper output
      • 'features' logic: car_options dict (CFJ/SBT) or flat list (BeForward)
    """
    url = (raw.get("car_url") or "").strip()
    if not url:
        return None

    # ← CHANGED: read source tag emitted by all three scrapers;
    #             fall back to URL detection for legacy files
    source = raw.get("source") or detect_source(url)

    # ── car row ───────────────────────────────────────────────────────────────
    car = {
        "source"           : source,
        "car_url"          : url,
        "title"            : raw.get("title"),
        "ref_no"           : raw.get("ref_no"),                   # ← unified across all sources
        "model_code"       : raw.get("model_code"),
        "make"             : raw.get("make"),
        "model_name"       : raw.get("model_name"),
        "grade"            : raw.get("grade"),                    # ← unified (was model_grade / versionclass)
        "body_type"        : raw.get("body_type"),
        "registration_year": raw.get("registration_year"),        # ← unified
        "manufacture_year" : raw.get("manufacture_year"),
        "mileage"          : raw.get("mileage"),
        "mileage_km"       : parse_int(                           # try display string first, fall back to raw int
            raw.get("mileage") or str(raw.get("mileage_raw") or "")
        ),
        "engine_capacity"  : raw.get("engine_capacity"),          # ← unified (was engine / engine_size)
        "transmission"     : raw.get("transmission"),             # ← unified (was trans.)
        "fuel_type"        : raw.get("fuel_type"),                # ← unified (was fuel)
        "drive_type"       : raw.get("drive_type"),               # ← unified (was drive)
        "steering"         : raw.get("steering"),
        "seats"            : parse_int(raw.get("seats")),
        "doors"            : parse_int(raw.get("doors")),
        "exterior_color"   : raw.get("exterior_color"),           # ← unified (was ext_color / body_color)
        "chassis_no"       : raw.get("chassis_no"),               # ← unified (was vin_chassis_no)
        "dimension_m3"     : raw.get("m3"),                       # ← unified (was "dimension" string for CFJ)
        "dimension_raw"    : raw.get("dimension_raw"),
        "weight_kg"        : raw.get("weight"),
        "delivery_port"    : raw.get("delivery_port"),            # ← unified (was destination_port for BeForward)
        "source_location"  : raw.get("location"),
        "scraped_at"       : raw.get("scraped_at"),
        # source-specific overflow — generic, no per-source branching needed
        "extra_data"       : json.dumps({
            k: raw.get(k)
            for k in ("photo_count", "engine_code", "view_count",
                      "max_loading_capacity", "gross_vehicle_weight")
            if raw.get(k)
        }),
    }

    # ── pricing row ───────────────────────────────────────────────────────────
    # ← CHANGED: vehicle_price / total_price are already floats from scrapers;
    #             total_cnf / car_price aliases removed
    pricing = {
        "currency"         : raw.get("currency", "USD"),
        "vehicle_price"    : raw.get("vehicle_price"),
        "total_price"      : raw.get("total_price"),
        "original_price"   : raw.get("original_price"),
        "discount_rate"    : raw.get("discount_rate"),
        "freight_amount"   : raw.get("freight_amount"),
        "inspection_amount": raw.get("inspection_amount"),
        "insurance_amount" : raw.get("insurance_amount"),
        "vanning_amount"   : raw.get("vanning_amount"),
    }

    # ── features ─────────────────────────────────────────────────────────────
    # ← SIMPLIFIED: car_options dict is present for CFJ and SBT (with categories),
    #   empty dict for BeForward → fall back to flat features list.
    features   = []
    car_options = raw.get("car_options") or {}
    if car_options:
        # CFJ and SBT: use categorized car_options
        for category, items in car_options.items():
            for item in items:
                features.append({"category": category, "feature": item})
    else:
        # BeForward: flat features list, no categories
        for feat_str in (raw.get("features") or []):
            features.append({"category": "General", "feature": feat_str})

    # ── images ────────────────────────────────────────────────────────────────
    # ← CHANGED: all sources now use "image_urls" — no "images" alias needed
    images = [
        {"image_url": u, "is_thumbnail": False, "display_order": i}
        for i, u in enumerate(raw.get("image_urls") or [])
    ]
    if raw.get("thumbnail_url"):    # CFJ only
        images.append({
            "image_url"    : raw["thumbnail_url"],
            "is_thumbnail" : True,
            "display_order": -1
        })

    return car, pricing, features, images


# ─────────────────────────────────────────────────────────────────────────────
# JSON LOADER — handles array, url-keyed dict, or JSONL (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def load_json(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            records = []
            for key, val in data.items():
                if isinstance(val, dict):
                    val.setdefault("car_url", key)
                    records.append(val)
            return records
    except json.JSONDecodeError:
        pass
    records = []
    for i, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"   ⚠  Skipping malformed JSONL line {i}: {e}")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE STEPS (schema/truncate/insert/verify unchanged in structure)
# ─────────────────────────────────────────────────────────────────────────────
def create_schema(conn):
    print("📐 Creating schema...")
    conn.execute(text(SCHEMA_SQL))
    print("   ✓ Schema ready")

def truncate_all(conn):
    print("🗑️  Truncating all tables...")
    conn.execute(text("TRUNCATE TABLE cars RESTART IDENTITY CASCADE"))
    print("   ✓ Cleared")

def insert_cars(conn, records: list[dict]) -> tuple[int, int]:
    loaded = skipped = 0
    for raw in records:
        result = transform(raw)
        if result is None:
            skipped += 1
            continue
        car, pricing, features, images = result
        try:
            row = conn.execute(text("""
                INSERT INTO cars (
                    source, car_url, ref_no, title, make, model_name, model_code,
                    grade, body_type, registration_year, manufacture_year,
                    mileage, mileage_km, engine_capacity, transmission, fuel_type,
                    drive_type, steering, seats, doors, exterior_color, chassis_no,
                    dimension_m3, dimension_raw, weight_kg, delivery_port,
                    source_location, extra_data, scraped_at
                ) VALUES (
                    :source, :car_url, :ref_no, :title, :make, :model_name, :model_code,
                    :grade, :body_type, :registration_year, :manufacture_year,
                    :mileage, :mileage_km, :engine_capacity, :transmission, :fuel_type,
                    :drive_type, :steering, :seats, :doors, :exterior_color, :chassis_no,
                    :dimension_m3, :dimension_raw, :weight_kg, :delivery_port,
                    :source_location, :extra_data::jsonb, :scraped_at
                )
                ON CONFLICT (car_url) DO NOTHING
                RETURNING id
            """), car)
            car_id_row = row.fetchone()
            if car_id_row is None:
                skipped += 1
                continue
            car_id = car_id_row[0]

            conn.execute(text("""
                INSERT INTO car_pricing (
                    car_id, currency, vehicle_price, total_price,
                    original_price, discount_rate, freight_amount,
                    inspection_amount, insurance_amount, vanning_amount
                ) VALUES (
                    :car_id, :currency, :vehicle_price, :total_price,
                    :original_price, :discount_rate, :freight_amount,
                    :inspection_amount, :insurance_amount, :vanning_amount
                )
            """), {"car_id": car_id, **pricing})

            if features:
                conn.execute(text("""
                    INSERT INTO car_features (car_id, category, feature)
                    VALUES (:car_id, :category, :feature)
                """), [{"car_id": car_id, **f} for f in features])

            if images:
                conn.execute(text("""
                    INSERT INTO car_images (car_id, image_url, is_thumbnail, display_order)
                    VALUES (:car_id, :image_url, :is_thumbnail, :display_order)
                """), [{"car_id": car_id, **img} for img in images])

            loaded += 1
        except Exception as e:
            print(f"   ⚠  Skipped [{raw.get('car_url','?')[:60]}]: {e}")
            skipped += 1
    return loaded, skipped


def verify(conn):
    def q(sql): return conn.execute(text(sql))
    print("\n" + "─" * 52)
    print("📊 VERIFICATION")
    print("─" * 52)
    for table in ("cars", "car_pricing", "car_features", "car_images"):
        n = q(f"SELECT COUNT(*) FROM {table}").scalar()
        print(f"  {table:<20} │ {n:>5} rows")
    print()
    rows = q("SELECT source, COUNT(*) FROM cars GROUP BY source ORDER BY 2 DESC").fetchall()
    for r in rows:
        print(f"  {r[0]:<22} │ {r[1]:>4} cars")
    r = q("""
        SELECT MIN(vehicle_price), MAX(vehicle_price), ROUND(AVG(vehicle_price)::numeric,2)
        FROM car_pricing WHERE vehicle_price IS NOT NULL
    """).fetchone()
    if r and r[0]:
        print(f"\n  Price  min=${r[0]:,.2f}  max=${r[1]:,.2f}  avg=${r[2]:,.2f}")
    print("─" * 52)


def run():
    print("\n🚗  Car Inventory Pipeline (normalized)")
    db_display = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"    JSON: {JSON_FILE}   DB: {db_display}\n")
    if not os.path.exists(JSON_FILE):
        print(f"❌  File not found: {JSON_FILE}")
        sys.exit(1)
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.begin() as conn:
        create_schema(conn)
        truncate_all(conn)
        records = load_json(JSON_FILE)
        print(f"📂  {len(records)} records loaded")
        loaded, skipped = insert_cars(conn, records)
        print(f"✅  Inserted: {loaded}   Skipped: {skipped}")
        verify(conn)
    print("\n🎉  Done.\n")

if __name__ == "__main__":
    run()
```

---

## Quick Reference — All Changes by File

| File | What changed |
|------|-------------|
| `carfromjapan.py` | `to_price()` added; `SPEC_KEY_MAP` updated (3 keys); `extract_accessories` → `extract_car_options`; `extract_prices` output renamed + numeric; `parse_detail_page` adds `source`, `features`, `car_options`, `m3`, `dimension_raw`; `DEFAULT_FIELDS` updated |
| `beforward.py` | `to_price()` + `apply_normalisation()` added; `FIELD_NORMALISATION` dict added; `parse_pricing` renames `destination_port`→`delivery_port`, `"$"`→`"USD"`, prices to float; `parse_specs_table` + `parse_pickup_specs` apply normalisation; `parse_detail_page` renames `images`→`image_urls`, adds `car_options: {}` |
| `sbtjapan.py` | `to_price()` + `apply_normalisation()` added; `SPEC_NORMALISATION` + `INFO_NORMALISATION` dicts added; `parse_identification` renames `stock_id`→`ref_no`; `parse_pricing` prices to float; `parse_car_specs` + `parse_info_lists` apply normalisation; `parse_individual_car_page` adds `source`, `features`, `delivery_port` |
| `pipeline.py` | `transform()` loses all per-source `if/elif` field-name branches; `parse_price()` calls removed (prices already float); `detect_source()` becomes fallback only; features logic simplified to `car_options` dict vs flat list |
