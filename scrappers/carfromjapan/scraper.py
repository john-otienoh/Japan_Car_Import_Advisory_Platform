import time
import re

from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)
from utils import (
    Vehicle, clean_value, enrich_vehicle
)

SOURCE = "carsfromjapan"
BASE_URL = "https://carfromjapan.com"
START_PATH = "/kenya/cheap-used-cars-for-sale"
PROJECT_ROOT = get_project_root()
OUTPUT_DIR = PROJECT_ROOT / "data" / SOURCE
LOG_DIR = PROJECT_ROOT / "logs" / SOURCE
REQUEST_DELAY = 1.5
DEFAULT_MAX_PAGES = 10

SPEC_KEY_MAP = {
    "Reference No.":       "reference_no",
    "Model Code":          "model_code",
    "Model Grade":         "grade",
    "Manufacture Year":    "manufacturing_year",
    "Transmission":        "transmission",
    "Mileage":             "mileage",
    "Engine Capacity":     "engine",
    "Fuel Type":           "fuel",
    "No. of Seats":        "seats",
    "No. of Doors":        "doors",
    "Steering":            "steering",
    "Drive Type":          "drive",
    "Dimension":           "dimension",
    "VIN / Chassis No.":   "chassis_no",
    "Exterior Color":      "exterior_color",
}

THUMB_SUFFIX = "_100_100"
FULL_SUFFIX = "_640_0"
EXCLUDE_IMAGE_PATTERNS = ["banner-payment", "thumb-banner", "/public/next-desktop/"]


def _listing_url(page: int) -> str:
    base = f"{BASE_URL}{START_PATH}"
    return f"{base}?page={page}" if page > 1 else base


# Listing page 

def get_listing_urls(logger, max_pages: int = DEFAULT_MAX_PAGES) -> list:
    """Collect vehicle detail URLs from paginated listing pages."""
    urls, consecutive_empty = [], 0

    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(REQUEST_DELAY)

        url = _listing_url(page)
        logger.info(f"Page {page}")
        soup = fetch(url, logger=logger)

        if soup is None:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                logger.error("3 consecutive failures — stopping")
                break
            continue

        page_urls = []
        for card in soup.select('[data-testid="car-item-list"]'):
            tag = card.select_one("h3 a")
            if tag:
                href = tag.get("href", "")
                full = BASE_URL + href if href.startswith("/") else href
                if full and full not in urls:
                    page_urls.append(full)

        urls.extend(page_urls)
        found = len(page_urls)
        logger.info(f"Found {found} vehicles")
        consecutive_empty = 0 if found else consecutive_empty + 1

        if consecutive_empty >= 3:
            logger.error("3 consecutive empty pages — stopping")
            break

    logger.info(f"Total: {len(urls)} URLs")
    return urls

# Detail page section parsers 
def extract_title(soup) -> str:
    h1 = soup.find("h1")
    if h1:
        return clean(h1.get_text())
    tag = soup.find("title")
    return clean(tag.get_text()).split("|")[0].strip() if tag else ""


def extract_specs(soup) -> dict:
    """Parse the specification table using SPEC_KEY_MAP."""
    specs = {}
    table = soup.select_one("div.border-t-primary table, table.w-full.table-fixed")
    if not table:
        return specs
    for row in table.select("tbody tr"):
        cells = row.find_all("td", recursive=False)
        for i in range(0, len(cells) - 1, 2):
            raw_label = clean(cells[i].get_text())
            raw_value = clean(cells[i + 1].get_text())
            if not raw_label or raw_value in ("", "-"):
                continue
            key = SPEC_KEY_MAP.get(raw_label, slugify(raw_label))
            specs[key] = raw_value
    return specs


def extract_prices(soup) -> dict:
    prices = {}
    els = soup.select(".car-price")
    if els:
        prices["vehicle_price"] = clean(els[0].get_text())
    for el in els:
        if "font-bold" in (el.get("class") or []):
            prices["total_price"] = clean(el.get_text())
            break
    return prices


def extract_destination(soup) -> str:
    heading = soup.find("h2", string=re.compile(r"Delivery", re.I))
    if heading:
        port_el = heading.find_next("p")
        if port_el:
            return clean(port_el.get_text())
    return ""


def extract_features(soup) -> list:
    """Flatten accessories into a single feature list."""
    features = []
    heading = soup.find("h2", string=re.compile(r"Accessories", re.I))
    if not heading:
        return features
    wrapper = heading.find_parent("div", class_=lambda c: c and "w-full" in c)
    if not wrapper:
        return features
    for section in wrapper.select("div.pt-4\\.5"):
        for span in section.select("span.text-\\[13px\\]"):
            text = clean(span.get_text())
            if text:
                features.append(text)
    return features


def extract_images(soup) -> list:
    """Full-size image URLs from the thumbnail navigation."""
    urls, seen = [], set()
    for img in soup.select('nav[aria-label="Thumbnail Navigation"] button img'):
        src = img.get("src", "")
        if src.startswith("//"):
            src = "https:" + src
        if src.endswith(THUMB_SUFFIX):
            src = src[: -len(THUMB_SUFFIX)] + FULL_SUFFIX
        if src and not any(p in src for p in EXCLUDE_IMAGE_PATTERNS) and src not in seen:
            urls.append(src)
            seen.add(src)
    return urls


def parse_vehicle(soup, car_url: str) -> Vehicle:
    specs = extract_specs(soup)
    prices = extract_prices(soup)

    v = Vehicle(
        source=SOURCE,
        car_url=car_url,
        stock_id=specs.pop("reference_no", ""),
        chassis_no=specs.pop("chassis_no", ""),
        title=extract_title(soup),
        manufacturing_year=specs.pop("manufacturing_year", ""),
        make="",            
        model_name="",      
        model=specs.pop("grade", ""),
        body_type="",       
        model_code=clean_value(specs.pop("model_code", "")),
        grade=specs.get("grade", ""),
        mileage=specs.pop("mileage", ""),
        engine=specs.pop("engine", ""),
        transmission=specs.pop("transmission", ""),
        drive=specs.pop("drive", ""),
        steering=specs.pop("steering", ""),
        fuel=specs.pop("fuel", ""),
        doors=specs.pop("doors", ""),
        seats=specs.pop("seats", ""),
        exterior_color=specs.pop("exterior_color", "").title(),
        dimension=specs.pop("dimension", ""),
        currency="USD",
        vehicle_price=prices.get("vehicle_price", ""),
        total_price=prices.get("total_price", ""),
        freight_amount="",
        inspection_amount="",
        insurance_amount="",
        destination_port=extract_destination(soup),
        location="Japan",
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


def run(max_pages: int = DEFAULT_MAX_PAGES) -> None:
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
    ap.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    args = ap.parse_args()
    run(max_pages=args.max_pages)

