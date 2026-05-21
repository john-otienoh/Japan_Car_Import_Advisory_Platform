import requests
import json
import logging
import time
import re
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
BASE_URL   = "https://www.beforward.jp"
START_URL  = "https://www.beforward.jp/stocklist/sar=steering/steering=Right/tp_country_id=27"
OUTPUT_DIR = Path("data/raw/beforward")
LOG_DIR    = Path("logs")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

def setup_logger(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = LOG_DIR / f"{name}_{timestamp}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        logger.handlers.clear()

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    file_h = logging.FileHandler(log_file, encoding="utf-8")
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(file_h)
    logger.info(f"Logger ready → {log_file}")
    return logger


# ─────────────────────────────────────────────────────────────
# FETCH
# ─────────────────────────────────────────────────────────────

def fetch(url: str, logger: logging.Logger) -> BeautifulSoup:
    logger.debug(f"GET {url}")
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ─────────────────────────────────────────────────────────────
# JSON OUTPUT — shared helper
# ─────────────────────────────────────────────────────────────

def save_json(path: Path, data: dict, logger: logging.Logger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved → {path}")


# ═════════════════════════════════════════════════════════════
# PART 1 — STOCKLIST SCRAPER
# Collects all individual vehicle URLs from paginated listing
# and saves them to: data/raw/beforward/vehicle_urls_<ts>.json
# ═════════════════════════════════════════════════════════════

def get_total_pages(soup: BeautifulSoup, logger: logging.Logger) -> int:
    pages = [1]
    for a in soup.select("div.results-pagination ul li a"):
        text = a.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    total = max(pages)
    logger.info(f"Total pages detected: {total:,}")
    return total


def build_page_url(base_url: str, page: int) -> str:
    """
    BE FORWARD uses path-segment pagination:
    Page 1: /stocklist/sar=steering/...
    Page 2: /stocklist/page=2/sar=steering/...
    """
    if page == 1:
        return base_url
    return base_url.replace("/stocklist/", f"/stocklist/page={page}/", 1)


def extract_vehicle_urls(soup: BeautifulSoup, logger: logging.Logger) -> list:
    """
    Extracts unique vehicle URLs from one listing page.
    Skips SOLD items, banner rows and non-vehicle anchors.
    """
    urls = []
    seen = set()

    for row in soup.select("tr.stocklist-row"):
        if not row.select_one("td.photo-col"):
            continue
        if row.select_one("div.price-col-sold"):
            logger.debug("Skipping SOLD listing")
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
            logger.debug(f"Found: {full_url}")

    return urls


def scrape_vehicle_urls(logger: logging.Logger, max_pages: int = None) -> list:
    """
    Phase 1 — scrapes the stocklist and returns a list of vehicle URLs.
    Also saves them immediately to:
        data/raw/beforward/vehicle_urls_<timestamp>.json
    """
    all_urls = []

    logger.info("=" * 60)
    logger.info("PHASE 1 — Collecting vehicle URLs")
    logger.info(f"Source: {START_URL}")
    logger.info("=" * 60)

    try:
        soup = fetch(START_URL, logger)
    except requests.RequestException as e:
        logger.error(f"Failed to fetch page 1: {e}")
        return all_urls

    total_pages = get_total_pages(soup, logger)
    if max_pages:
        total_pages = min(total_pages, max_pages)
        logger.info(f"Capped at {max_pages} pages")

    # Page 1 — already fetched
    page_urls = extract_vehicle_urls(soup, logger)
    all_urls.extend(page_urls)
    logger.info(f"Page 1/{total_pages} → {len(page_urls)} | Total: {len(all_urls):,}")

    # Pages 2..N
    for page in range(2, total_pages + 1):
        url = build_page_url(START_URL, page)
        try:
            soup      = fetch(url, logger)
            page_urls = extract_vehicle_urls(soup, logger)

            if not page_urls:
                logger.warning(f"Page {page}: no URLs found — stopping early")
                break

            all_urls.extend(page_urls)
            logger.info(f"Page {page}/{total_pages} → {len(page_urls)} | Total: {len(all_urls):,}")

        except requests.RequestException as e:
            logger.error(f"Page {page} failed: {e}")
            break

        time.sleep(1.5)

    # Save URL list immediately after collection
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    url_path   = OUTPUT_DIR / f"vehicle_urls_{timestamp}.json"
    save_json(url_path, {
        "source":     START_URL,
        "scraped_at": datetime.now().isoformat(),
        "total":      len(all_urls),
        "urls":       all_urls,
    }, logger)

    logger.info(f"Phase 1 complete — {len(all_urls):,} URLs collected")
    return all_urls


# ═════════════════════════════════════════════════════════════
# PART 2 — DETAIL PAGE SCRAPER
# Visits each URL and extracts full car data
# Saves all results to: data/raw/beforward/cars_<timestamp>.json
# ═════════════════════════════════════════════════════════════

def parse_title_and_ref(soup: BeautifulSoup) -> dict:
    title_tag  = soup.select_one("div.car-info-flex-box h1")
    title      = title_tag.get_text(strip=True) if title_tag else "N/A"

    ref_tag    = soup.select_one("div.detail-specs-text")
    ref_text   = ref_tag.get_text(strip=True) if ref_tag else ""
    parts      = ref_text.split()
    model_code = parts[0] if len(parts) > 0 else "N/A"
    ref_no     = parts[1] if len(parts) > 1 else "N/A"

    return {"title": title, "model_code": model_code, "ref_no": ref_no}


def parse_pricing(soup: BeautifulSoup) -> dict:
    price_tag     = soup.select_one("span.price.ip-usd-price")
    total_tag     = soup.select_one("span#fn-vehicle-price-total-price")
    orig_tag      = soup.select_one("p.original-vehicle-price")
    save_tag      = soup.select_one("p#fn-current-save-rate")
    port_tag      = soup.select_one("p.destination-port")
    quote_tag     = soup.select_one("span#fn-vehicle-price-quote-type")

    return {
        "currency":         "$",
        "vehicle_price":    price_tag.get_text(strip=True) if price_tag else "N/A",
        "total_price":      total_tag.get_text(strip=True) if total_tag else "N/A",
        "original_price":   orig_tag.get_text(strip=True) if orig_tag else "N/A",
        "discount_rate":    save_tag.get_text(strip=True) if save_tag else "N/A",
        "destination_port": port_tag.get_text(separator=" ", strip=True) if port_tag else "N/A",
        "quote_type":       quote_tag.get_text(strip=True) if quote_tag else "N/A",
    }


def parse_specs_table(soup: BeautifulSoup) -> dict:
    """
    Parses the full specification table (table.specification).
    Each row has th/td pairs — flattened to a dict.
    """
    specs = {}
    table = soup.select_one("table.specification")
    if not table:
        return specs

    for row in table.select("tr"):
        cells = row.find_all(["th", "td"])
        for i in range(0, len(cells) - 1, 2):
            label = cells[i].get_text(separator=" ", strip=True).lower()
            value = cells[i + 1].get_text(separator=" ", strip=True) if i + 1 < len(cells) else ""
            label = re.sub(r"\s+", "_", label).strip("_")
            if label and value:
                specs[label] = value

    return specs


def parse_pickup_specs(soup: BeautifulSoup) -> dict:
    """Quick 5-column specs row: Mileage, Year, Engine, Trans, Fuel."""
    specs = {}
    table = soup.select_one("div.pickup-specification table")
    if not table:
        return specs

    rows = table.select("tr")
    if len(rows) < 2:
        return specs

    headers = [td.get_text(strip=True).lower() for td in rows[0].select("td")]
    values  = [td.get_text(separator=" ", strip=True) for td in rows[1].select("td")]

    for h, v in zip(headers, values):
        specs[re.sub(r"\s+", "_", h)] = v

    return specs


def parse_location(soup: BeautifulSoup) -> dict:
    tag = soup.select_one("span.specs-pickup-icon b")
    return {"location": tag.get_text(strip=True) if tag else "N/A"}


def parse_features(soup: BeautifulSoup):
    features = []
    for li in soup.select("div.remarks li"):
        text    = li.get_text(strip=True)
        classes = li.get("class", [])
        if "attached_on" in classes:
            features.append(text)
    return features


def parse_images(soup: BeautifulSoup) -> list:
    """Reads all image paths from hidden <input class='fn-images-pc'> elements."""
    images, seen = [], set()
    for inp in soup.select("input.fn-images-pc"):
        path = inp.get("data-path", "")
        if path and path not in seen:
            images.append(("https:" + path) if path.startswith("//") else path)
            seen.add(path)
    return images


def parse_total_image_count(soup: BeautifulSoup) -> int:
    tag = soup.select_one("span#fn-slider-total")
    try:
        return int(tag.get_text(strip=True)) if tag else 0
    except ValueError:
        return 0


def parse_detail_page(soup: BeautifulSoup, car_url: str, logger: logging.Logger) -> dict:
    """Master parser — merges all section parsers into one flat dict."""
    title_ref   = parse_title_and_ref(soup)
    pricing     = parse_pricing(soup)
    location    = parse_location(soup)
    pickup      = parse_pickup_specs(soup)
    specs       = parse_specs_table(soup)
    features    = parse_features(soup)
    images      = parse_images(soup)
    image_count = parse_total_image_count(soup)

    car = {
        "car_url":     car_url,
        "scraped_at":  datetime.now().isoformat(),
        "source":      "beforward",
        **title_ref,
        **pricing,
        **location,
        **pickup,
        **specs,
        "features": features,
        "image_count": image_count,
        "images":      images,
    }

    logger.info(
        f"Parsed: {title_ref.get('title', '?')} | "
        f"Ref: {title_ref.get('ref_no', '?')} | "
        f"Price: {pricing.get('vehicle_price', '?')} | "
        f"Images: {image_count}"
    )
    return car


def scrape_details(urls: list, logger: logging.Logger) -> list:
    """
    Phase 2 — visits each vehicle URL, parses the detail page,
    and returns a list of car dicts.
    Also saves all cars to:
        data/raw/beforward/cars_<timestamp>.json
    """
    all_cars = []

    logger.info("=" * 60)
    logger.info(f"PHASE 2 — Scraping {len(urls):,} detail pages")
    logger.info("=" * 60)

    for i, url in enumerate(urls, 1):
        try:
            soup = fetch(url, logger)
            car  = parse_detail_page(soup, url, logger)
            all_cars.append(car)
            logger.info(f"[{i}/{len(urls)}] Done: {car.get('ref_no', '?')}")
        except requests.RequestException as e:
            logger.error(f"[{i}/{len(urls)}] Failed {url}: {e}")
            all_cars.append({"car_url": url, "error": str(e), "scraped_at": datetime.now().isoformat()})

        time.sleep(1.5)

    # Save full car dataset
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    cars_path  = OUTPUT_DIR / f"cars_{timestamp}.json"
    save_json(cars_path, {
        "source":     START_URL,
        "scraped_at": datetime.now().isoformat(),
        "total":      len(all_cars),
        "cars":       all_cars,
    }, logger)

    logger.info(f"Phase 2 complete — {len(all_cars):,} cars scraped")
    return all_cars


# ═════════════════════════════════════════════════════════════
# PIPELINE — wires both phases together
# ═════════════════════════════════════════════════════════════

def run(max_pages: int = None):
    """
    Full pipeline:
      Phase 1 → collect all vehicle URLs  → saves vehicle_urls_<ts>.json
      Phase 2 → scrape each detail page   → saves cars_<ts>.json

    Args:
        max_pages: cap on listing pages scraped (None = all pages).
                   e.g. max_pages=5 scrapes ~125 cars for testing.
    """
    logger = setup_logger("beforward")

    logger.info("▶ BE FORWARD full pipeline started")

    # Phase 1 — collect URLs
    urls = scrape_vehicle_urls(logger, max_pages=max_pages)

    if not urls:
        logger.error("No URLs collected — aborting Phase 2")
        return

    # Phase 2 — scrape details
    cars = scrape_details(urls, logger)

    logger.info("=" * 60)
    logger.info(f"Pipeline complete")
    logger.info(f"  URLs collected : {len(urls):,}")
    logger.info(f"  Cars scraped   : {len(cars):,}")
    logger.info(f"  Output dir     : {OUTPUT_DIR.resolve()}")
    logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test: scrape first 2 listing pages (~50 cars)
    # Remove max_pages to scrape everything
    run(max_pages=1)