#!/usr/bin/env python3
"""
Car Inventory Pipeline - PostgreSQL only, file-based logging
=============================================================
Reads a unified JSON array of car listings, normalises the data,
and inserts it into a PostgreSQL database. All progress and errors
are written to `pipeline.log` (configurable).
"""

import json
import logging
import os
import re
import sys

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL environment variable not set.", file=sys.stderr)
    sys.exit(1)

JSON_FILE = os.getenv("JSON_FILE")
LOG_FILE = os.getenv("LOG_FILE", "pipeline.log")

# Logging – writes to a file
logger = logging.getLogger("car_pipeline")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

# Helpers
def extract_int(text: str | None) -> int | None:
    if not text:
        return None
    t = str(text).split("km")[0].replace(",", "")
    digits = re.sub(r"[^\d]", "", t)
    return int(digits) if digits else None


def extract_engine_cc(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"(\d[\d,]*)", str(text))
    if m:
        return int(m.group(1).replace(",", ""))
    return None


# Schema DDL
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
    engine_capacity_cc INTEGER,
    transmission      VARCHAR(30),
    fuel_type         VARCHAR(30),
    drive_type        VARCHAR(30),
    steering          VARCHAR(10),
    seats             SMALLINT,
    doors             SMALLINT,
    exterior_color    VARCHAR(50),
    chassis_no        VARCHAR(100),
    delivery_port     VARCHAR(100),
    source_location   VARCHAR(100),
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
    insurance_amount  NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS car_features (
    id       SERIAL       PRIMARY KEY,
    car_id   INTEGER      NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    feature  VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS car_images (
    id            SERIAL   PRIMARY KEY,
    car_id        INTEGER  NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    image_url     TEXT     NOT NULL,
    display_order SMALLINT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cars_source   ON cars(source);
CREATE INDEX IF NOT EXISTS idx_cars_mileage  ON cars(mileage_km);
CREATE INDEX IF NOT EXISTS idx_price_vehicle ON car_pricing(vehicle_price);
CREATE INDEX IF NOT EXISTS idx_feat_car      ON car_features(car_id);
CREATE INDEX IF NOT EXISTS idx_img_car       ON car_images(car_id);
"""

# Transform one raw record → rows for the related tables
def transform(raw: dict):
    car_url = (raw.get("car_url") or "").strip()
    if not car_url:
        logger.warning("Skipping record – empty car_url")
        return None

    source = raw.get("source", "unknown")

    mileage_km = extract_int(raw.get("mileage"))
    eng_cc = extract_engine_cc(raw.get("engine_capacity"))
    try:
        seats = int(raw["seats"]) if str(raw.get("seats", "")).strip() else None
    except (ValueError, TypeError):
        seats = None
    try:
        doors = int(raw["doors"]) if str(raw.get("doors", "")).strip() else None
    except (ValueError, TypeError):
        doors = None

    car = {
        "source": source,
        "car_url": car_url,
        "ref_no": raw.get("ref_no"),
        "title": raw.get("title"),
        "make": raw.get("make"),
        "model_name": raw.get("model_name"),
        "model_code": raw.get("model_code"),
        "grade": raw.get("grade"),
        "body_type": raw.get("body_type"),
        "registration_year": raw.get("registration_year"),
        "manufacture_year": raw.get("manufacture_year"),
        "mileage": raw.get("mileage"),
        "mileage_km": mileage_km,
        "engine_capacity": raw.get("engine_capacity"),
        "engine_capacity_cc": eng_cc,
        "transmission": raw.get("transmission"),
        "fuel_type": raw.get("fuel_type"),
        "drive_type": raw.get("drive_type"),
        "steering": raw.get("steering"),
        "seats": seats,
        "doors": doors,
        "exterior_color": raw.get("exterior_color"),
        "chassis_no": raw.get("chassis_no"),
        "delivery_port": raw.get("delivery_port"),
        "source_location": raw.get("location"),
    }

    pricing = {
        "currency": raw.get("currency", "USD"),
        "vehicle_price": raw.get("vehicle_price"),
        "total_price": raw.get("total_price"),
        "original_price": raw.get("vehicle_price_breakdown"),
        "discount_rate": raw.get("discount_rate"),
        "freight_amount": raw.get("freight_amount"),
        "inspection_amount": raw.get("inspection_amount"),
        "insurance_amount": raw.get("insurance_amount"),
    }

    features = [{"feature": f} for f in raw.get("features") or []]

    images = [
        {"image_url": url, "display_order": i}
        for i, url in enumerate(raw.get("image_urls") or [])
    ]

    return car, pricing, features, images


# Database operations
def create_schema(conn):
    logger.info("Creating schema if not exists...")
    conn.execute(text(SCHEMA_SQL))
    logger.info("Schema ready.")


def truncate_all(conn):
    logger.info("Truncating all tables...")
    conn.execute(text("TRUNCATE TABLE cars RESTART IDENTITY CASCADE"))
    logger.info("Tables cleared.")


def insert_cars(conn, records: list[dict]) -> tuple[int, int]:
    loaded = skipped = 0
    for idx, raw in enumerate(records, start=1):
        try:
            result = transform(raw)
            if result is None:
                skipped += 1
                continue

            car, pricing, features, images = result

            car_stmt = text("""
                INSERT INTO cars (
                    source, car_url, ref_no, title, make, model_name, model_code,
                    grade, body_type, registration_year, manufacture_year,
                    mileage, mileage_km, engine_capacity, engine_capacity_cc,
                    transmission, fuel_type, drive_type, steering, seats, doors,
                    exterior_color, chassis_no, delivery_port, source_location
                ) VALUES (
                    :source, :car_url, :ref_no, :title, :make, :model_name, :model_code,
                    :grade, :body_type, :registration_year, :manufacture_year,
                    :mileage, :mileage_km, :engine_capacity, :engine_capacity_cc,
                    :transmission, :fuel_type, :drive_type, :steering, :seats, :doors,
                    :exterior_color, :chassis_no, :delivery_port, :source_location
                )
                RETURNING id
            """)
            car_id = conn.execute(car_stmt, car).scalar()

            pricing_stmt = text("""
                INSERT INTO car_pricing (
                    car_id, currency, vehicle_price, total_price, original_price,
                    discount_rate, freight_amount, inspection_amount, insurance_amount
                ) VALUES (
                    :car_id, :currency, :vehicle_price, :total_price, :original_price,
                    :discount_rate, :freight_amount, :inspection_amount, :insurance_amount
                )
            """)
            conn.execute(pricing_stmt, {"car_id": car_id, **pricing})

            if features:
                feat_stmt = text(
                    "INSERT INTO car_features (car_id, feature) VALUES (:car_id, :feature)"
                )
                conn.execute(
                    feat_stmt,
                    [{"car_id": car_id, "feature": f["feature"]} for f in features],
                )

            if images:
                img_stmt = text(
                    "INSERT INTO car_images (car_id, image_url, display_order) VALUES (:car_id, :image_url, :display_order)"
                )
                conn.execute(
                    img_stmt,
                    [{"car_id": car_id, **img} for img in images],
                )

            loaded += 1
            if loaded % 100 == 0:
                logger.info("Progress: %d records inserted", loaded)

        except Exception as exc:
            logger.error("Record %d [%s] failed: %s", idx, raw.get("car_url", "?"), exc)
            skipped += 1

    return loaded, skipped


def verify(conn):
    logger.info("Running verification queries...")
    tables = ["cars", "car_pricing", "car_features", "car_images"]
    for t in tables:
        cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        logger.info("  %-20s │ %5d rows", t, cnt)

    sources = conn.execute(
        text("SELECT source, COUNT(*) FROM cars GROUP BY source ORDER BY 2 DESC")
    ).fetchall()
    for src, cnt in sources:
        logger.info("  %-22s │ %4d cars", src, cnt)

    minmax = conn.execute(
        text(
            "SELECT MIN(vehicle_price), MAX(vehicle_price), ROUND(AVG(vehicle_price)::numeric,2) "
            "FROM car_pricing WHERE vehicle_price IS NOT NULL"
        )
    ).fetchone()
    if minmax and minmax[0]:
        logger.info(
            "  Price  min=$%s  max=$%s  avg=$%s",
            f"{minmax[0]:,.2f}",
            f"{minmax[1]:,.2f}",
            f"{minmax[2]:,.2f}",
        )
    logger.info("Verification complete.")

# Main pipeline
def run():
    logger.info("=" * 60)
    logger.info("Car Inventory Pipeline started")
    logger.info("JSON file: %s", JSON_FILE)
    logger.info(
        "Database : %s",
        DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL,
    )

    if not os.path.exists(JSON_FILE):
        logger.error("JSON file not found: %s", JSON_FILE)
        sys.exit(1)

    with open(JSON_FILE, encoding="utf-8") as f:
        raw_content = f.read().strip()
    try:
        data = json.loads(raw_content)
        if isinstance(data, dict):
            data = [data]
        elif not isinstance(data, list):
            logger.error("JSON content is not a list or object. Aborting.")
            sys.exit(1)
    except json.JSONDecodeError:
        data = []
        for line in raw_content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning("Skipping malformed JSON line: %s", e)
        logger.info("Interpreted file as JSONL (%d lines read).", len(data))

    logger.info("Number of raw records to process: %d", len(data))

    engine = create_engine(DATABASE_URL, echo=False, future=True)
    with engine.begin() as conn:
        create_schema(conn)
        truncate_all(conn)
        loaded, skipped = insert_cars(conn, data)
        verify(conn)

    logger.info("Pipeline finished – inserted: %d, skipped: %d", loaded, skipped)
    logger.info("=" * 60)


if __name__ == "__main__":
    run()