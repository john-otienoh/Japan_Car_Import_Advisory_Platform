#!/usr/bin/env python3
"""
Combine all car data from BeForward, CarFromJapan and SBTJapan into
a single JSON file ready for PostgreSQL insertion.
"""

import json
import glob
import os
from datetime import datetime
from base import get_project_root, my_logger

PROJECT_ROOT = get_project_root()
OUTPUT_DIR   = PROJECT_ROOT / "data" / "unified"
LOG_DIR      = PROJECT_ROOT / "logs" / "combiner"
SOURCE_DIRS  = {
    "beforward"   : PROJECT_ROOT / "data" / "raw" / "beforward",
    "carfromjapan": PROJECT_ROOT / "data" / "raw" / "carfromjapan",
    "sbtjapan"    : PROJECT_ROOT / "data" / "raw" / "sbtjapan",
}

FINAL_FIELDS = [
    "source", "car_url", "title", "model_code", "ref_no",
    "registration_year", "manufacture_year", "grade", "transmission",
    "mileage", "engine_capacity", "fuel_type", "seats", "doors",
    "steering", "drive_type", "exterior_color", "chassis_no",
    "currency", "vehicle_price", "total_price", "discount_rate",
    "delivery_port", "location", "body_type",
    "freight_amount", "inspection_amount", "insurance_amount",
    "vehicle_price_breakdown", "make", "model", "model_name",
    "features", "image_urls"
]

def normalise_record(rec: dict) -> dict:
    """Ensure the record contains exactly FINAL_FIELDS with correct defaults."""
    out = {}
    for field in FINAL_FIELDS:
        if field in rec:
            out[field] = rec[field]
        else:
            if field in ("features", "image_urls"):
                out[field] = []
            elif field in (
                "vehicle_price", "total_price", "freight_amount",
                "inspection_amount", "insurance_amount", "vehicle_price_breakdown"
            ):
                out[field] = 0.0
            else:
                out[field] = ""
    return out

def combine_all(logger):
    all_cars = []
    for source, directory in SOURCE_DIRS.items():
        if not directory.exists():
            logger.warning(f"Directory {directory} does not exist, skipping.")
            continue
        json_files = glob.glob(str(directory / "*.json"))
        logger.info(f"Processing {len(json_files)} file(s) from {source}")
        for filepath in json_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # data can be a list or a dict (if old CarFromJapan format)
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    records = list(data.values())
                else:
                    logger.warning(f"Unsupported format in {filepath}, skipping.")
                    continue
                for rec in records:
                    # Ensure source is correctly set (may be missing)
                    rec.setdefault("source", source)
                    normalised = normalise_record(rec)
                    all_cars.append(normalised)
                logger.info(f"  Loaded {len(records)} records from {os.path.basename(filepath)}")
            except Exception as e:
                logger.error(f"Error reading {filepath}: {e}")

    out_file = OUTPUT_DIR / f"all_cars_data.json"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_cars, f, indent=2, ensure_ascii=False)
    logger.info(f"Combined {len(all_cars)} records -> {out_file}")

if __name__ == "__main__":
    logger = my_logger("combiner", log_dir=LOG_DIR)
    combine_all(logger)