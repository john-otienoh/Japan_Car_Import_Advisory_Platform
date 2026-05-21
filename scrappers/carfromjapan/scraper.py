#!/usr/bin/env python3
"""
CarFromJapan – combined scraper:
    Stage 1 – collect listing cards (URL, thumbnail, summary fields)
    Stage 2 – scrape each detail page (full specs, images, accessories)
    Saves intermediate and final JSON files.
"""

import time
import argparse
import re
from datetime import datetime, timezone

from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)

BASE_URL = "https://carfromjapan.com"
START_PATH = "/kenya/cheap-used-cars-for-sale"
PROJECT_ROOT = get_project_root()
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "carfromjapan"
LOG_DIR = PROJECT_ROOT / "logs" / "carfromjapan"

DEFAULT_MAX_PAGES = 400        
PER_PAGE = 25                
REQUEST_DELAY = 1.5

# Image CDN patterns
THUMB_SUFFIX = "_100_100"
FULL_SUFFIX = "_640_0"
EXCLUDE_IMAGE_PATTERNS = ["banner-payment", "thumb-banner", "/public/next-desktop/"]

SPEC_KEY_MAP = {
    "Reference No.": "reference_no",
    "Model Code": "model_code",
    "Registration Year": "registration_year",
    "Model Grade": "model_grade",
    "Manufacture Year": "manufacture_year",
    "Transmission": "transmission",
    "Mileage": "mileage",
    "Engine Capacity": "engine_capacity",
    "Fuel Type": "fuel_type",
    "No. of Seats": "seats",
    "No. of Doors": "doors",
    "Steering": "steering",
    "Drive Type": "drive_type",
    "Dimension": "dimension",
    "VIN / Chassis No.": "vin_chassis_no",
    "Exterior Color": "exterior_color",
    "Auction Grade": "auction_grade",
}

DEFAULT_FIELDS = [
    "reference_no", "model_code", "registration_year", "manufacture_year",
    "model_grade", "transmission", "mileage", "engine_capacity", "fuel_type",
    "seats", "doors", "steering", "drive_type", "dimension",
    "exterior_color", "auction_grade", "vin_chassis_no",
    "car_price", "total_cnf",
]

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
            data["car_price"] = clean(car_price_el.get_text())
        delivery_el = price_box.select_one(".max-w-35.line-clamp-1")
        if delivery_el:
            data["delivery_port"] = clean(delivery_el.get_text())
        total_el = price_box.select_one(".car-price.font-bold")
        if total_el:
            data["total_cnf"] = clean(total_el.get_text())

    img = card.select_one("img[alt*='CFJ']")
    if img:
        src = img.get("src", "")
        data["thumbnail_url"] = ("https:" + src) if src.startswith("//") else src

    return data

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
            logger.warning(f"Page {page} fetch failed, consecutive empty = {consecutive_empty}")
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
            label_cell, value_cell = cells[i], cells[i+1]
            if label_cell.get("colspan") or value_cell.get("colspan"):
                continue
            raw_label = clean(label_cell.get_text())
            raw_value = clean(value_cell.get_text())
            if not raw_label or raw_value in ("", "-"):
                continue
            key = SPEC_KEY_MAP.get(raw_label, raw_label.lower().replace(" ", "_").replace(".", ""))
            specs[key] = raw_value
    return specs

def extract_accessories(soup) -> dict:
    accessories = {}
    heading = soup.find("h2", string=re.compile(r"Accessories", re.I))
    if not heading:
        return accessories
    wrapper = heading.find_parent("div", class_=lambda c: c and "w-full" in c)
    if not wrapper:
        return accessories
    for section in wrapper.select("div.pt-4\\.5"):
        cat_el = section.select_one("p.font-semibold")
        if not cat_el:
            continue
        category = clean(cat_el.get_text())
        items = [clean(s.get_text()) for s in section.select("span.text-\\[13px\\]") if clean(s.get_text())]
        if items:
            accessories[category] = items
    return accessories

def extract_prices(soup) -> dict:
    prices = {}
    els = soup.select(".car-price")
    if els:
        prices["car_price"] = clean(els[0].get_text())
    for el in els:
        if "font-bold" in (el.get("class") or []):
            prices["total_cnf"] = clean(el.get_text())
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
    data = {
        "car_url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "title": extract_title(soup),
        **extract_specs(soup),
        **extract_prices(soup),
        "accessories": extract_accessories(soup),
        "image_urls": extract_images(soup),
    }
    for field in DEFAULT_FIELDS:
        data.setdefault(field, "")
    logger.info(f"[detail] ref={data.get('reference_no', '?')}  images={len(data['image_urls'])}")
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

# ----------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------
def run(max_pages: int = DEFAULT_MAX_PAGES):
    logger = my_logger("carfromjapan", log_dir=LOG_DIR)
    logger.info("CarFromJapan scraper started")
    
    listing_cars = scrape_listings(logger, max_pages)
    if not listing_cars:
        logger.error("No listing URLs found, exiting.")
        return
    # Save intermediate listing file
    # listing_path = OUTPUT_DIR / f"carfromjapan_listing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    # save_to_son(listing_cars, listing_path, logger)

    details = scrape_details(listing_cars, logger)
    out_file = OUTPUT_DIR / f"carfromjapan_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_to_json(details, out_file, logger)
    logger.info(f"Pipeline complete – {len(details)} cars saved.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        help="Number of listing pages to scrape")
    args = parser.parse_args()
    run(max_pages=args.max_pages)
