#!/usr/bin/env python3
"""
SBTJapan – normalised output scraper.
Output: list of dicts with unified schema.
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

def to_price(text) -> float:
    if not text or str(text).strip() in ("N/A", "-", ""):
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", str(text).replace(",", ""))
    try:
        return float(cleaned) or 0.0
    except (ValueError, TypeError):
        return 0.0

# URL collection ────────────────────────────────────────────────────────────

def get_total_pages(soup) -> int:
    pages = []
    for link in soup.select("a.pagination__link"):
        text = link.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    return max(pages) if pages else 1

def collect_detail_urls(logger, max_pages=None):
    detail_urls = []
    soup = fetch(BASE_SEARCH_URL, logger=logger)
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
    logger.info(f"Page 1/{total_pages} → {len(detail_urls)} cards | total: {len(detail_urls)}")

    for page in range(2, total_pages + 1):
        paged_url = f"{BASE_SEARCH_URL}?page={page}"
        soup = fetch(paged_url, logger=logger)
        if soup is None:
            logger.error(f"Page {page} failed, stopping.")
            break
        page_urls = []
        for anchor in soup.select("a.card-product__wrap"):
            href = anchor.get("href", "")
            if href:
                page_urls.append(urljoin("https://www.sbtjapan.com", href))
        detail_urls.extend(page_urls)
        logger.info(f"Page {page}/{total_pages} → {len(page_urls)} cards | total: {len(detail_urls)}")
        if not page_urls:
            break
        time.sleep(REQUEST_DELAY)
    logger.info(f"Stage 1 complete – {len(detail_urls)} URLs collected")
    return detail_urls

# Detail parsers – only allowed keys ───────────────────────────────────────

def parse_header(soup):
    name_tag = soup.select_one("h1.product-detail__name")
    title = clean(name_tag.get_text()) if name_tag else ""
    detail_items = [clean(el.get_text()) for el in soup.select("div.product-detail__detail-item")]
    return {
        "title"           : title,
        "model_code"      : detail_items[0] if len(detail_items) > 0 else "",
        "manufacture_year": detail_items[1] if len(detail_items) > 1 else "",
        "body_type"       : detail_items[2] if len(detail_items) > 2 else "",
    }

def parse_identification(soup):
    stock_tag    = soup.select_one("span.product-detail__id-number")
    location_tag = soup.select_one("div.product-detail__location-country")
    return {
        "ref_no"  : clean(stock_tag.get_text())    if stock_tag    else "",
        "location": clean(location_tag.get_text()) if location_tag else "",
    }

def parse_pricing(soup):
    base_price    = soup.select_one("span.product-detail__base-price-range")
    total_tag     = soup.select_one("div#total_amount")

    def get_detail(el_id) -> float:
        el = soup.select_one(f"div#{el_id}")
        return to_price(el.get_text()) if el else 0.0

    return {
        "currency"               : "USD",
        "vehicle_price"          : to_price(base_price.get_text() if base_price else None),
        "total_price"            : to_price(total_tag.get_text() if total_tag else None),
        "freight_amount"         : get_detail("freight_amount"),
        "inspection_amount"      : get_detail("inspection_amount"),
        "insurance_amount"       : get_detail("insurance_amount"),
        "vehicle_price_breakdown": get_detail("vehicle_price"),
    }

def parse_car_specs(soup) -> dict:
    specs = {}
    for item in soup.select("div.product-detail__status-item"):
        label_el = item.select_one("div.product-detail__status-label")
        value_el = item.select_one("div.product-detail__status-value")
        if label_el and value_el:
            key = slugify(clean(label_el.get_text()).lower().replace(" ", "_"))
            if key == "door":
                key = "doors"
            specs[key] = clean(value_el.get_text())

    rename_map = {
        "engine"     : "engine_capacity",
        "fuel"       : "fuel_type",
        "drive"      : "drive_type",
        "body_color" : "exterior_color",
        # ignored: weight, gross_weight, etc.
    }
    for old, new in rename_map.items():
        if old in specs:
            specs[new] = specs.pop(old)
    # Remove forbidden keys
    forbidden = {"vehicle_weight", "gross_vehicle_weight", "max_loading_capacity", "m3", "dimension_raw"}
    for key in list(specs.keys()):
        if key in forbidden:
            del specs[key]
    return specs

def parse_info_lists(soup) -> dict:
    info = {}
    for block in soup.select("div.product-detail__info-block"):
        for item in block.select("li.product-detail__info-item"):
            label_el = item.select_one("div.product-detail__info-label")
            value_el = item.select_one("div.product-detail__info-value")
            if label_el and value_el:
                key = slugify(clean(label_el.get_text()).lower().replace(" ", "_"))
                value = clean(value_el.get_text())
                # only keep allowed ones
                if key in ("registration_yearmonth",):
                    info["registration_year"] = value
                # dimension / m3 are ignored
    return info

def parse_image_urls(soup) -> list:
    urls = []
    gallery = soup.select_one("div.product-detail__gallery-slider")
    if gallery:
        for slide in gallery.select("div.swiper-slide"):
            img = slide.select_one("div.product-detail__main-image img")
            if img and img.get("src"):
                urls.append(img["src"])
    return urls

def parse_features(soup) -> list:
    """Flat list of options (no categories)."""
    features = []
    for block in soup.select("div.product-detail__option-block"):
        for el in block.select("div.product-detail__option-item.-available"):
            features.append(clean(el.get_text()))
    return features

def scrape_detail(url, logger):
    soup = fetch(url, logger=logger)
    if soup is None:
        return None
    header   = parse_header(soup)
    ident    = parse_identification(soup)
    pricing  = parse_pricing(soup)
    specs    = parse_car_specs(soup)
    info     = parse_info_lists(soup)
    features = parse_features(soup)
    images   = parse_image_urls(soup)

    raw = {
        "source"      : "sbtjapan",
        "car_url"     : url,
        "delivery_port": "Mombasa",
        "currency"    : "USD",
        **header,
        **ident,
        **pricing,
        **specs,
        **info,
        "features"    : features,
        "image_urls"  : images,
        # make/model/model_name from header? we already have model_code, grade, etc.
        # We'll add "make" and "model" as empty for consistency, unless we parse.
        "make"        : "",
        "model"       : "",
        "model_name"  : "",
    }
    logger.info(f"[detail] ref={raw.get('ref_no', '?')}  images={len(images)}")
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
    logger = my_logger("sbtjapan", log_dir=LOG_DIR)
    logger.info("SBTJapan scraper started")
    urls = collect_detail_urls(logger, max_pages)
    if not urls:
        logger.error("No URLs found, exiting.")
        return
    all_cars = []
    for idx, url in enumerate(urls, 1):
        car = scrape_detail(url, logger)
        if car:
            all_cars.append(normalise_record(car))
        else:
            logger.warning(f"Skipped {url}")
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
    