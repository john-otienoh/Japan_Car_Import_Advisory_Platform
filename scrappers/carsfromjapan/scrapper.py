#!/usr/bin/env python3
"""
CarFromJapan – normalised output scraper.
Output: list of dicts with unified schema.
"""

import time
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

SPEC_KEY_MAP = {
    "Reference No."     : "ref_no",
    "Model Code"        : "model_code",
    "Registration Year" : "registration_year",
    "Model Grade"       : "grade",
    "Manufacture Year"  : "manufacture_year",
    "Transmission"      : "transmission",
    "Mileage"           : "mileage",
    "Engine Capacity"   : "engine_capacity",
    "Fuel Type"         : "fuel_type",
    "No. of Seats"      : "seats",
    "No. of Doors"      : "doors",
    "Steering"          : "steering",
    "Drive Type"        : "drive_type",
    "VIN / Chassis No." : "chassis_no",
    "Exterior Color"    : "exterior_color",
    # ignored: Dimension, Auction Grade
}

def to_price(text) -> float:
    if not text or str(text).strip() in ("N/A", "-", ""):
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", str(text).replace(",", ""))
    try:
        return float(cleaned) or 0.0
    except (ValueError, TypeError):
        return 0.0

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

# Listing parser – only keep what is needed (delivery_port for merging) ────

def parse_listing_card(card) -> dict:
    data = {}
    title_tag = card.select_one("h3 a")
    if title_tag:
        href = title_tag.get("href", "")
        data["url"] = BASE_URL + href if href.startswith("/") else href
    else:
        data["url"] = ""

    # delivery port from listing
    delivery_el = card.select_one(".max-w-35.line-clamp-1")
    if delivery_el:
        data["delivery_port"] = clean(delivery_el.get_text())
    return data

def scrape_listings(logger, max_pages: int = DEFAULT_MAX_PAGES) -> dict:
    cars = {}
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(REQUEST_DELAY)
        url = listing_url(page)
        soup = fetch(url, logger=logger)
        if soup is None:
            logger.warning(f"Page {page} fetch failed, stopping.")
            break
        cards = soup.select('[data-testid="car-item-list"]')
        for card in cards:
            car = parse_listing_card(card)
            if car.get("url"):
                cars[car["url"]] = car
        logger.info(f"Page {page}: {len(cards)} cards | total: {len(cars)}")
        if not cards:
            break
    logger.info(f"Stage 1 complete – {len(cars)} cars collected")
    return cars

# Detail parsers – only allowed keys ───────────────────────────────────────

def extract_images(soup) -> list:
    urls = []
    seen = set()
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
            key = SPEC_KEY_MAP.get(raw_label)
            if key:   # only keep keys we want
                specs[key] = raw_value
    return specs

def extract_prices(soup) -> dict:
    prices = {"currency": "USD"}
    els = soup.select(".car-price")
    if els:
        prices["vehicle_price"] = to_price(els[0].get_text())
    for el in els:
        if "font-bold" in (el.get("class") or []):
            prices["total_price"] = to_price(el.get_text())
            break
    return prices

def extract_features(soup) -> list:
    """Flat feature list (no categories)."""
    features = []
    heading = soup.find("h2", string=re.compile(r"Accessories", re.I))
    if not heading:
        return features
    wrapper = heading.find_parent("div", class_=lambda c: c and "w-full" in c)
    if not wrapper:
        return features
    for span in wrapper.select("span.text-\\[13px\\]"):
        text = clean(span.get_text())
        if text:
            features.append(text)
    return features

def extract_title(soup) -> str:
    h1 = soup.find("h1")
    if h1:
        return clean(h1.get_text())
    title_tag = soup.find("title")
    if title_tag:
        return clean(title_tag.get_text()).split("|")[0].strip()
    return ""

def scrape_detail(url, listing_data, logger):
    soup = fetch(url, logger=logger)
    if soup is None:
        return None
    specs = extract_specs(soup)
    raw = {
        "source"      : "carfromjapan",
        "car_url"     : url,
        "title"       : extract_title(soup),
        **specs,
        **extract_prices(soup),
        "features"    : extract_features(soup),
        "image_urls"  : extract_images(soup),
        "delivery_port": listing_data.get("delivery_port", ""),
        "currency"    : "USD"
    }
    logger.info(f"[detail] ref={raw.get('ref_no', '?')}  images={len(raw['image_urls'])}")
    return raw


def normalise_record(rec: dict) -> dict:
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

def run(max_pages: int = DEFAULT_MAX_PAGES):
    logger = my_logger("carfromjapan", log_dir=LOG_DIR)
    logger.info("CarFromJapan scraper started")
    listing_cars = scrape_listings(logger, max_pages)
    if not listing_cars:
        logger.error("No listing URLs found, exiting.")
        return
    all_cars = []
    total = len(listing_cars)
    for idx, (url, listing_data) in enumerate(listing_cars.items(), 1):
        car = scrape_detail(url, listing_data, logger)
        if car:
            all_cars.append(normalise_record(car))
        else:
            logger.warning(f"Skipped {url}")
        if idx < total:
            time.sleep(REQUEST_DELAY)
    out_file = OUTPUT_DIR / f"carfromjapan_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_to_json(all_cars, out_file, logger)
    logger.info(f"Pipeline complete – {len(all_cars)} cars saved.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    args = parser.parse_args()
    run(max_pages=args.max_pages)