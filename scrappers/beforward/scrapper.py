#!/usr/bin/env python3
"""
BeForward – normalised output scraper.
Output: list of dicts with unified schema.
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

# Final unified schema
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

# Price helper – returns float or 0.0
def to_price(text) -> float:
    if not text or str(text).strip() in ("N/A", "-", ""):
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", str(text).replace(",", ""))
    try:
        return float(cleaned) or 0.0
    except (ValueError, TypeError):
        return 0.0

# URL collection ────────────────────────────────────────────────────────────

def get_total_pages(soup, logger):
    pages = [1]
    for a in soup.select("div.results-pagination ul li a"):
        text = a.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    total = max(pages)
    logger.info(f"Total pages detected: {total:,}")
    return total

def build_page_url(page):
    if page == 1:
        return START_URL
    return START_URL.replace("/stocklist/", f"/stocklist/page={page}/", 1)

def extract_vehicle_urls(soup, logger) -> list:
    urls = []
    seen = set()
    for row in soup.select("tr.stocklist-row"):
        if not row.select_one("td.photo-col"):
            continue
        if row.select_one("div.price-col-sold"):
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
    return urls

def collect_urls(logger, max_pages=None) -> list:
    all_urls = []
    soup = fetch(START_URL, logger=logger)
    if soup is None:
        return all_urls
    total_pages = get_total_pages(soup, logger)
    if max_pages:
        total_pages = min(total_pages, max_pages)
        logger.info(f"Capped at {total_pages} pages")
    page_urls = extract_vehicle_urls(soup, logger)
    all_urls.extend(page_urls)
    logger.info(f"Page 1/{total_pages} → {len(page_urls)} cards | total: {len(all_urls)}")
    for page in range(2, total_pages + 1):
        url = build_page_url(page)
        soup = fetch(url, logger=logger)
        if soup is None:
            logger.error(f"Page {page} failed, stopping.")
            break
        page_urls = extract_vehicle_urls(soup, logger)
        if not page_urls:
            logger.warning(f"Page {page}: no URLs found – stopping early")
            break
        all_urls.extend(page_urls)
        logger.info(f"Page {page}/{total_pages} → {len(page_urls)} cards | total: {len(all_urls)}")
        time.sleep(REQUEST_DELAY)
    logger.info(f"Stage 1 complete – {len(all_urls)} URLs collected")
    return all_urls

# Detail parsers – only allowed keys are kept ──────────────────────────────

def parse_title_and_ref(soup):
    title_tag = soup.select_one("div.car-info-flex-box h1")
    title = clean(title_tag.get_text()) if title_tag else ""
    ref_tag = soup.select_one("div.detail-specs-text")
    ref_text = clean(ref_tag.get_text()) if ref_tag else ""
    parts = ref_text.split()
    model_code = parts[0] if parts else ""
    ref_no     = parts[1] if len(parts) > 1 else ""
    return {"title": title, "model_code": model_code, "ref_no": ref_no}

def parse_pricing(soup):
    price = soup.select_one("span.price.ip-usd-price")
    total = soup.select_one("span#fn-vehicle-price-total-price")
    save  = soup.select_one("p#fn-current-save-rate")
    port  = soup.select_one("p.destination-port")
    return {
        "currency"      : "USD",
        "vehicle_price" : to_price(price.get_text() if price else None),
        "total_price"   : to_price(total.get_text() if total else None),
        "discount_rate" : clean(save.get_text()) if save else "",
        "delivery_port" : clean(port.get_text(separator=" ")) if port else ""
    }

def parse_specs_table(soup) -> dict:
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

    # Rename to unified names
    rename_map = {
        "fuel"       : "fuel_type",
        "drive"      : "drive_type",
        "ext_color"  : "exterior_color",
        "engine_size": "engine_capacity",
        "engine"     : "engine_capacity",
        "versionclass": "grade",
        "trans"      : "transmission",
        "year"       : "registration_year",
        "dimension"  : None,          # remove
        "engine_code": None,
        "weight"     : None,
        "maxcap"     : None,
        "m3"         : None
    }
    for old, new in rename_map.items():
        if old in specs:
            if new is None:
                specs.pop(old)
            else:
                specs[new] = specs.pop(old)

    if "manufacture_yearmonth" in specs:
        mym = specs.pop("manufacture_yearmonth")
        specs.setdefault("manufacture_year", mym.split("/")[0])

    if "registration_yearmonth" in specs:
        specs.setdefault("registration_year", specs.pop("registration_yearmonth"))

    return specs

def parse_pickup_specs(soup) -> dict:
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

    rename_map = {
        "fuel"   : "fuel_type",
        "drive"  : "drive_type",
        "trans"  : "transmission",
        "year"   : "registration_year",
        "ext_color": "exterior_color",
        "engine_size": "engine_capacity",
        "engine" : "engine_capacity",
        "versionclass": "grade",
        "dimension": None,
        "m3"      : None,
        "weight"  : None
    }
    for old, new in rename_map.items():
        if old in specs:
            if new is None:
                specs.pop(old)
            else:
                specs[new] = specs.pop(old)
    return specs

def parse_location(soup):
    tag = soup.select_one("span.specs-pickup-icon b")
    return {"location": clean(tag.get_text()) if tag else ""}

def parse_features(soup) -> list:
    features = []
    for li in soup.select("div.remarks li"):
        if "attached_on" in li.get("class", []):
            features.append(clean(li.get_text()))
    return features

def parse_images(soup) -> list:
    images = []
    seen = set()
    for inp in soup.select("input.fn-images-pc"):
        path = inp.get("data-path", "")
        if path and path not in seen:
            full = ("https:" + path) if path.startswith("//") else path
            images.append(full)
            seen.add(path)
    return images

def scrape_detail_page(url, soup, logger):
    title_ref = parse_title_and_ref(soup)
    pricing   = parse_pricing(soup)
    location  = parse_location(soup)
    pickup    = parse_pickup_specs(soup)
    specs     = parse_specs_table(soup)
    features  = parse_features(soup)
    images    = parse_images(soup)

    # Merge all sub-dicts, priority: later overwrites earlier
    raw = {
        "source"        : "beforward",
        "car_url"       : url,
        **title_ref,
        **pricing,
        **location,
        **pickup,
        **specs,
        "features"      : features,
        "image_urls"    : images
    }

    logger.info(f"[detail] ref={raw.get('ref_no', '?')}  images={len(images)}")
    return raw

def normalise_record(rec: dict) -> dict:
    """Return a dict containing exactly FINAL_FIELDS with proper defaults."""
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

def run(max_pages=DEFAULT_MAX_PAGES):
    logger = my_logger("beforward", log_dir=LOG_DIR)
    logger.info("Beforward scraper started")
    urls = collect_urls(logger, max_pages)
    if not urls:
        logger.error("No URLs found, exiting.")
        return
    all_cars = []
    for idx, url in enumerate(urls, 1):
        soup = fetch(url, logger=logger)
        if soup is None:
            logger.error(f"Failed to fetch {url}")
            continue
        car = scrape_detail_page(url, soup, logger)
        normalised = normalise_record(car)
        all_cars.append(normalised)
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
    