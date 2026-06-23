#!/usr/bin/env python3
"""
Combine all car data from BeForward, CarFromJapan and SBTJapan into
a single JSON file ready for PostgreSQL insertion.
"""

import json
import glob
import os
from base import get_project_root, my_logger
from utils import REQUIRED_KEYS

PROJECT_ROOT = get_project_root()
OUTPUT_DIR   = PROJECT_ROOT / "data"
LOG_DIR      = PROJECT_ROOT / "logs" / "combiner"
SOURCE_DIRS  = {
    "beforward"   : PROJECT_ROOT / "data" / "beforward",
    "carsfromjapan": PROJECT_ROOT / "data" / "carsfromjapan",
    "sbtjapan"    : PROJECT_ROOT / "data" / "sbtjapan",
}

def normalise_record(rec: dict) -> dict:
    out = {}
    for field in REQUIRED_KEYS:
        if field in rec:
            out[field] = rec[field]
        else:
            if field in ("features", "image_urls"):
                out[field] = []
            elif field in (
                "vehicle_price", "total_price", "freight_amount",
                "inspection_amount", "insurance_amount"
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
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    records = list(data.values())
                else:
                    logger.warning(f"Unsupported format in {filepath}, skipping.")
                    continue
                for rec in records:
                    rec.setdefault("source", source)
                    normalised = normalise_record(rec)
                    all_cars.append(normalised)
                logger.info(f"  Loaded {len(records)} records from {os.path.basename(filepath)}")
            except Exception as e:
                logger.error(f"Error reading {filepath}: {e}")

    out_file = OUTPUT_DIR / f"all_combined_cars.json"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_cars, f, indent=2, ensure_ascii=False)
    logger.info(f"Combined {len(all_cars)} records -> {out_file}")

if __name__ == "__main__":
    logger = my_logger("combiner", log_dir=LOG_DIR)
    combine_all(logger)