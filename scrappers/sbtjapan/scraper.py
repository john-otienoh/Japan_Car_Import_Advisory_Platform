#!/usr/bin/env python3
"""
sbtjapan.py — Scrape SBT Japan and emit unified Vehicle records.

Pipeline:
    get_listing_urls()  →  scrape_vehicle()  →  parse_vehicle()  →  save_json()
"""
import time
from urllib.parse import urljoin

from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)
from utils import (
    Vehicle, clean_value, enrich_vehicle
)

SOURCE = "sbtjapan"
BASE_URL = "https://www.sbtjapan.com"
BASE_SEARCH_URL = f"{BASE_URL}/used-cars/search"
PROJECT_ROOT = get_project_root()
OUTPUT_DIR = PROJECT_ROOT / "data" / SOURCE
LOG_DIR = PROJECT_ROOT / "logs" / SOURCE
REQUEST_DELAY = 1.5


# Listing page 
def get_total_pages(soup) -> int:
    pages = [
        int(a.get_text(strip=True))
        for a in soup.select("a.pagination__link")
        if a.get_text(strip=True).isdigit()
    ]
    return max(pages) if pages else 1

def get_listing_urls(search_url: str, logger, max_pages=None) -> list:
    """Collect all vehicle detail URLs from paginated search results."""
    urls = []

    logger.info(f"Page 1: {search_url}")
    soup = fetch(search_url, logger=logger)
    if soup is None:
        return urls

    total = get_total_pages(soup)
    if max_pages:
        total = min(total, max_pages)
    logger.info(f"Total pages: {total}")

    for a in soup.select("a.card-product__wrap"):
        if href := a.get("href", ""):
            urls.append(urljoin(BASE_URL, href))

    for page in range(2, total + 1):
        soup = fetch(f"{search_url}?page={page}", logger=logger)
        if soup is None:
            logger.error(f"Page {page} failed — stopping.")
            break
        for a in soup.select("a.card-product__wrap"):
            if href := a.get("href", ""):
                urls.append(urljoin(BASE_URL, href))
        logger.info(f"Page {page}/{total} | URLs: {len(urls)}")
        time.sleep(REQUEST_DELAY)

    logger.info(f"Found {len(urls)} URLs")
    return urls


def parse_header(soup) -> dict:
    """Title, model_code, manufacturing_year, body_type from page header."""
    name_tag = soup.select_one("h1.product-detail__name")
    items = [clean(el.get_text()) for el in soup.select("div.product-detail__detail-item")]
    return {
        "title": clean(name_tag.get_text()) if name_tag else "",
        "model_code": items[0] if len(items) > 0 else "",
        "manufacturing_year": items[1] if len(items) > 1 else "",
        "body_type": items[2] if len(items) > 2 else "",
    }

def parse_identification(soup) -> dict:
    """Stock ID and inventory location."""
    stock_tag = soup.select_one("span.product-detail__id-number")
    location_tag = soup.select_one("div.product-detail__location-country")
    return {
        "stock_id": clean(stock_tag.get_text()) if stock_tag else "",
        "location": clean(location_tag.get_text()) if location_tag else "",
    }


def parse_pricing(soup) -> dict:
    """Vehicle price, total, and cost breakdown."""
    def _get(el_id: str) -> str:
        el = soup.select_one(f"div#{el_id}")
        return clean(el.get_text()) if el else ""

    base_price = soup.select_one("span.product-detail__base-price-range")
    base_curr = soup.select_one("span.product-detail__base-price-currency")
    total_tag = soup.select_one("div#total_amount")
    return {
        "currency": clean(base_curr.get_text()) if base_curr else "USD",
        "vehicle_price": clean(base_price.get_text()) if base_price else "",
        "total_price": clean(total_tag.get_text()) if total_tag else "",
        "freight_amount": _get("freight_amount"),
        "inspection_amount": _get("inspection_amount"),
        "insurance_amount": _get("insurance_amount"),
    }


def parse_specs(soup) -> dict:
    """Specification items (mileage, engine, transmission, etc.)."""
    specs = {}
    for item in soup.select("div.product-detail__status-item"):
        label_el = item.select_one("div.product-detail__status-label")
        value_el = item.select_one("div.product-detail__status-value")
        if label_el and value_el:
            key = slugify(clean(label_el.get_text()))
            key = "doors" if key == "door" else key
            specs[key] = clean(value_el.get_text())
    return specs


def parse_modal_fields(soup) -> dict:
    """
    Hidden form fields from price-estimate modal.
    Provides: make, model_name, grade, body_type, manufacturing_year.
    """
    field_map = {
        "make": "make",
        "name": "model_name",
        "grade": "grade",
        "body_type": "body_type",
        "year": "manufacturing_year",
    }
    result = {}
    for input_name, key in field_map.items():
        inp = soup.select_one(f'form#get_estimate_id input[name="{input_name}"]')
        if inp:
            result[key] = inp.get("value", "").strip()
    return result


def parse_features(soup) -> list:
    """Available car options as a flat feature list (replaces car_options)."""
    return [
        clean(el.get_text())
        for block in soup.select("div.product-detail__option-block")
        for el in block.select("div.product-detail__option-item.-available")
        if clean(el.get_text())
    ]


def parse_images(soup) -> list:
    """Full-size gallery image URLs."""
    urls = []
    gallery = soup.select_one("div.product-detail__gallery-slider")
    if gallery:
        for slide in gallery.select("div.swiper-slide"):
            img = slide.select_one("div.product-detail__main-image img")
            if img and img.get("src"):
                urls.append(img["src"])
    return urls


def parse_vehicle(soup, car_url: str) -> Vehicle:
    """Merge all section parsers and return a unified Vehicle."""
    header = parse_header(soup)
    ident = parse_identification(soup)
    pricing = parse_pricing(soup)
    specs = parse_specs(soup)
    modal = parse_modal_fields(soup)

    mfg_year = modal.get("manufacturing_year") or header.get("manufacturing_year", "")
    body_type = modal.get("body_type") or header.get("body_type", "")

    v = Vehicle(
        source=SOURCE,
        car_url=car_url,
        stock_id=ident.get("stock_id", ""),
        chassis_no="",
        title=header.get("title", ""),
        manufacturing_year=mfg_year,
        make=modal.get("make", "").title(),
        model_name=modal.get("model_name", "").title(),
        model=modal.get("grade", ""),           
        body_type=body_type.title(),
        model_code=clean_value(header.get("model_code", "")),
        grade=modal.get("grade", ""),
        mileage=specs.get("mileage", ""),
        engine=specs.get("engine", ""),
        transmission=specs.get("transmission", ""),
        drive=specs.get("drive", ""),
        steering=specs.get("steering", ""),
        fuel=specs.get("fuel", ""),
        doors=specs.get("doors", ""),
        seats=specs.get("seats", ""),
        exterior_color=specs.get("body_color", "").title(),
        dimension=specs.get("dimension", ""),
        currency=pricing.get("currency", "USD"),
        vehicle_price=pricing.get("vehicle_price", ""),
        total_price=pricing.get("total_price", ""),
        freight_amount=pricing.get("freight_amount", ""),
        inspection_amount=pricing.get("inspection_amount", ""),
        insurance_amount=pricing.get("insurance_amount", ""),
        destination_port="Mombasa",
        location=ident.get("location", ""),
        features=parse_features(soup),
        image_urls=parse_images(soup),
    )
    return enrich_vehicle(v)

def scrape_vehicle(url: str, logger) -> Vehicle | None:
    soup = fetch(url, logger=logger)
    if soup is None:
        logger.error(f"Failed: {url}")
        return None
    return parse_vehicle(soup, url)


# Pipeline 

def run(search_url: str = BASE_SEARCH_URL, max_pages: int = None) -> None:
    logger = my_logger(SOURCE, log_dir=LOG_DIR)
    logger.info("Starting scrape...")

    urls = get_listing_urls(search_url, logger, max_pages)
    if not urls:
        logger.error("No URLs found.")
        return

    vehicles = []
    total = len(urls)
    for idx, url in enumerate(urls, 1):
        logger.info(f"\nVehicle {idx}/{total}")
        v = scrape_vehicle(url, logger)
        if v:
            vehicles.append(v.to_dict())
            logger.info(f"Saved — {v.make} {v.model_name}")
        else:
            logger.info(f"Skipped — {url}")
        time.sleep(REQUEST_DELAY)

    save_to_json(vehicles, OUTPUT_DIR / f"{SOURCE}.json", logger)
    logger.info(f"\nFinished\n{len(vehicles)} vehicles saved")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=None)
    args = ap.parse_args()
    run(max_pages=args.max_pages)
