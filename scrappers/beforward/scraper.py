#!/usr/bin/env python3
"""
beforward.py — Scrape BeForward and emit unified Vehicle records.

Pipeline:
    get_listing_urls()  →  scrape_vehicle()  →  parse_vehicle()  →  save_json()
"""

import time
from urllib.parse import urljoin
import re

from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)
from utils import (
    Vehicle, clean_value, enrich_vehicle
)


SOURCE = "beforward"
BASE_URL = "https://www.beforward.jp"
START_URL = (
    "https://www.beforward.jp/stocklist/sar=steering/steering=Right/tp_country_id=27"
)
PROJECT_ROOT = get_project_root()
OUTPUT_DIR = PROJECT_ROOT / "data" / SOURCE
LOG_DIR = PROJECT_ROOT / "logs" / SOURCE
REQUEST_DELAY = 1.5


# Listing page 

def _get_total_pages(soup, logger) -> int:
    pages = [1]
    for a in soup.select("div.results-pagination ul li a"):
        text = a.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    total = max(pages)
    logger.info(f"Total pages: {total:,}")
    return total


def _build_page_url(base_url: str, page: int) -> str:
    """BeForward uses path-segment pagination: /stocklist/page=N/sar=..."""
    if page == 1:
        return base_url
    return base_url.replace("/stocklist/", f"/stocklist/page={page}/", 1)


def extract_page_urls(soup) -> list:
    urls = []
    for row in soup.select("tr.stocklist-row"):
        if row.select_one("div.price-col-sold"):
            continue                     
        link = row.select_one("a.vehicle-url-link")
        if link:
            href = link.get("href", "").strip()
            if href and re.match(r"^/[^/]+/[^/]+/[^/]+/id/\d+/$", href):
                urls.append(urljoin(BASE_URL, href))
    return urls


def get_listing_urls(logger, max_pages=None) -> list:
    """Collect vehicle detail URLs from paginated stocklist."""
    all_urls = []

    soup = fetch(START_URL, logger=logger)
    if soup is None:
        return all_urls

    total = _get_total_pages(soup, logger)
    if max_pages:
        total = min(total, max_pages)

    page_urls = extract_page_urls(soup)
    all_urls.extend(page_urls)
    logger.info(f"Page 1/{total} → {len(page_urls)} | Total: {len(all_urls)}")

    for page in range(2, total + 1):
        soup = fetch(_build_page_url(START_URL, page), logger=logger)
        if soup is None:
            logger.error(f"Page {page} failed — stopping.")
            break
        page_urls = extract_page_urls(soup)
        if not page_urls:
            logger.warning(f"Page {page}: no URLs — stopping.")
            break
        all_urls.extend(page_urls)
        logger.info(f"Page {page}/{total} → {len(page_urls)} | Total: {len(all_urls)}")
        time.sleep(REQUEST_DELAY)

    logger.info(f"Found {len(all_urls)} URLs")
    return all_urls


#  Detail page section parsers

def extract_title_and_ref(soup) -> dict:
    """Title, model_code, and reference number."""
    title_tag = soup.select_one("div.car-info-flex-box h1")
    title = clean(title_tag.get_text()) if title_tag else ""
    ref_tag = soup.select_one("div.detail-specs-text")
    parts = clean(ref_tag.get_text()).split() if ref_tag else []
    return {
        "title": title,
        "model_code": parts[0] if parts else "",
        "stock_id": parts[1] if len(parts) > 1 else "",
    }


def extract_pricing(soup) -> dict:
    price = soup.select_one("span.price.ip-usd-price")
    total = soup.select_one("span#fn-vehicle-price-total-price")
    port = soup.select_one("p.destination-port")
    return {
        "currency": "USD",
        "vehicle_price": clean(price.get_text()) if price else "",
        "total_price": clean(total.get_text()) if total else "",
        "destination_port": clean(port.get_text(separator=" ")) if port else "Mombasa",
    }


def extract_specs(soup) -> dict:
    """Full specification table — dynamic slug keys."""
    specs = {}
    table = soup.select_one("table.specification")
    if not table:
        return specs
    for row in table.select("tr"):
        cells = row.find_all(["th", "td"])
        for i in range(0, len(cells) - 1, 2):
            label = slugify(clean(cells[i].get_text(separator=" ")))
            value = clean(cells[i + 1].get_text()) if i + 1 < len(cells) else ""
            if label and value:
                specs[label] = value
    return specs


def extract_pickup_specs(soup) -> dict:
    """Pickup specification block (year, registration, etc.)."""
    specs = {}
    table = soup.select_one("div.pickup-specification table")
    if not table:
        return specs
    rows = table.select("tr")
    if len(rows) < 2:
        return specs
    headers = [slugify(clean(td.get_text())) for td in rows[0].select("td")]
    values = [clean(td.get_text(separator=" ")) for td in rows[1].select("td")]
    return dict(zip(headers, values))


def extract_location(soup) -> str:
    tag = soup.select_one("span.specs-pickup-icon b")
    return clean(tag.get_text()) if tag else ""


def extract_features(soup) -> list:
    """Attached features from remarks section."""
    return [
        clean(li.get_text())
        for li in soup.select("div.remarks li.attached_on")
        if clean(li.get_text())
    ]


def extract_images(soup) -> list:
    """Full-size image URLs from hidden input fields."""
    images, seen = [], set()
    for inp in soup.select("input.fn-images-pc"):
        path = inp.get("data-path", "")
        if path and path not in seen:
            url = ("https:" + path) if path.startswith("//") else path
            images.append(url)
            seen.add(path)
    return images


#  Vehicle builder

def parse_vehicle(soup, car_url: str) -> Vehicle:
    title_ref = extract_title_and_ref(soup)
    pricing = extract_pricing(soup)
    specs = extract_specs(soup)
    pickup = extract_pickup_specs(soup)
    all_specs = {**pickup, **specs}       

    mfg_year = (
        all_specs.get("manufacture_yearmonth", "").split("/")[0]
        or all_specs.get("year", "").split("/")[0]
        or all_specs.get("registration_yearmonth", "").split("/")[0]
    ).strip()

    v = Vehicle(
        source=SOURCE,
        car_url=car_url,
        stock_id=title_ref.get("stock_id", ""),
        chassis_no=clean_value(all_specs.get("chassis_no", "")),
        title=title_ref.get("title", ""),
        manufacturing_year=mfg_year,
        make="",            
        model_name="",      
        model=all_specs.get("versionclass", ""),
        body_type="",      
        model_code=clean_value(title_ref.get("model_code", "")),
        grade=all_specs.get("versionclass", ""),
        mileage=all_specs.get("mileage", ""),
        engine=all_specs.get("engine_size", all_specs.get("engine", "")),
        transmission=all_specs.get("transmission", all_specs.get("trans_", "")),
        drive=all_specs.get("drive", ""),
        steering=all_specs.get("steering", ""),
        fuel=all_specs.get("fuel", ""),
        doors=all_specs.get("doors", ""),
        seats=all_specs.get("seats", ""),
        exterior_color=all_specs.get("ext_color", "").title(),
        dimension=all_specs.get("dimension", ""),
        currency=pricing.get("currency", "USD"),
        vehicle_price=pricing.get("vehicle_price", ""),
        total_price=pricing.get("total_price", ""),
        freight_amount="",
        inspection_amount="",
        insurance_amount="",
        destination_port=pricing.get("destination_port", ""),
        location=extract_location(soup),
        features=extract_features(soup),
        image_urls=extract_images(soup),
    )
    return enrich_vehicle(v)


def scrape_vehicle(url: str, logger) -> Vehicle | None:
    soup = fetch(url, logger=logger)
    if soup is None:
        logger.error(f"Failed: {url}")
        return None
    return parse_vehicle(soup, url)


#  Pipeline 

def run(max_pages: int = None) -> None:
    logger = my_logger(SOURCE, log_dir=LOG_DIR)
    logger.info("Starting scrape...")

    urls = get_listing_urls(logger, max_pages)
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
