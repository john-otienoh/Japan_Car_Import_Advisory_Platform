"""
CarFromJapan — Combined Scraper
================================
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════
#  CONFIG  — edit these before running
# ══════════════════════════════════════════════════════════════════

MAX_LISTING_PAGES  = 4        # listing pages to crawl (≈ 400 × 25 = 10 000 cars)
PER_PAGE           = 25         # listings per page (carfromjapan default)
REQUEST_DELAY      = 1.5        # polite delay between requests (seconds)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "carsfromjapan"
LISTING_OUTPUT     = OUTPUT_DIR / "cars.json"          # intermediate: all discovered URLs + summary fields
DETAIL_OUTPUT      = OUTPUT_DIR / "car_details.json"   # final: full car records
LOG_LEVEL          = logging.INFO         # logging.DEBUG for verbose output

# ══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════

BASE_URL     = "https://carfromjapan.com"
START_PATH   = "/kenya/cheap-used-cars-for-sale"
CDN_BASE     = "https://static.carfromjapan.com"
THUMB_SUFFIX = "_100_100"
FULL_SUFFIX  = "_640_0"

EXCLUDE_IMAGE_PATTERNS = [
    "banner-payment",
    "thumb-banner",
    "/public/next-desktop/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://carfromjapan.com/",
}

SPEC_KEY_MAP = {
    "Reference No.":     "reference_no",
    "Model Code":        "model_code",
    "Registration Year": "registration_year",
    "Model Grade":       "model_grade",
    "Manufacture Year":  "manufacture_year",
    "Transmission":      "transmission",
    "Mileage":           "mileage",
    "Engine Capacity":   "engine_capacity",
    "Fuel Type":         "fuel_type",
    "No. of Seats":      "seats",
    "No. of Doors":      "doors",
    "Steering":          "steering",
    "Drive Type":        "drive_type",
    "Dimension":         "dimension",
    "VIN / Chassis No.": "vin_chassis_no",
    "Exterior Color":    "exterior_color",
    "Auction Grade":     "auction_grade",
}

# ══════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  SHARED HTTP SESSION
# ══════════════════════════════════════════════════════════════════

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ══════════════════════════════════════════════════════════════════
#  SHARED UTILITIES
# ══════════════════════════════════════════════════════════════════

def clean(text: Optional[str]) -> str:
    """Strip and collapse internal whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str, retries: int = 3, backoff: float = 3.0) -> Optional[BeautifulSoup]:
    """
    GET a URL and return a BeautifulSoup tree.
    Retries up to `retries` times with exponential back-off on failure.
    """
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(url, timeout=20)
            resp.raise_for_status()
            log.debug("Fetched %s  [HTTP %s]", url, resp.status_code)
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as exc:
            log.warning("Attempt %d/%d failed for %s — %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(backoff * attempt)
    log.error("All %d attempts failed for %s", retries, url)
    return None


def save_json(data: dict | list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("Saved %d record(s) → %s", len(data), path)


# ══════════════════════════════════════════════════════════════════
#  STAGE 1 — LISTING SCRAPER
#  Visits paginated listing pages and collects summary car dicts
#  keyed by their detail-page URL.
# ══════════════════════════════════════════════════════════════════

def _listing_url(page: int) -> str:
    return f"{BASE_URL}{START_PATH}?page={page}" if page > 1 else f"{BASE_URL}{START_PATH}"


def _parse_card(card) -> dict:
    """
    Extract summary fields from a single <div data-testid="car-item-list"> card.
    Returns a dict; 'url' is the canonical key used by the caller.
    """
    data: dict = {}

    # URL + title
    title_tag = card.select_one("h3 a")
    if title_tag:
        data["title"] = clean(title_tag.get_text())
        href = title_tag.get("href", "")
        data["url"] = (BASE_URL + href) if href.startswith("/") else href
    else:
        data["title"] = data["url"] = ""

    # CFJ reference ID
    compare_div = card.select_one("[id^='compare-']")
    if compare_div:
        raw = compare_div.get_text(strip=True)
        data["cfj_id"] = raw.replace("Compare (", "").rstrip(")")

    # Photo count
    photo_btn = card.select_one(".z-3")
    if photo_btn:
        m = re.search(r"\((\d+)\)", clean(photo_btn.get_text()))
        data["photo_count"] = int(m.group(1)) if m else None

    # Spec grid: Registration year / Mileage / Model code / Engine / Grade / Transmission
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

    # Prices + delivery port
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

    # Thumbnail image (listing card — single image)
    img = card.select_one("img[alt*='CFJ']")
    if img:
        src = img.get("src", "")
        data["thumbnail_url"] = ("https:" + src) if src.startswith("//") else src

    return data


def _process_listing_page(soup: BeautifulSoup, cars: dict) -> int:
    """Parse all cards on one listing page; return number found."""
    cards = soup.select('[data-testid="car-item-list"]')
    for card in cards:
        car = _parse_card(card)
        if car.get("url"):
            cars[car["url"]] = car
    return len(cards)


def scrape_listings() -> dict:
    """
    Crawl MAX_LISTING_PAGES listing pages and return a dict keyed by car URL.
    Stops early if 5 consecutive pages return no cars.
    Saves intermediate results to LISTING_OUTPUT after every page.
    """
    cars: dict = {}
    consecutive_empty = 0
    expected = MAX_LISTING_PAGES * PER_PAGE

    log.info(
        "STAGE 1 — listing scraper  |  pages 1–%d  |  ~%d listings expected",
        MAX_LISTING_PAGES, expected,
    )

    for page in range(1, MAX_LISTING_PAGES + 1):
        if page > 1:
            time.sleep(REQUEST_DELAY)

        url = _listing_url(page)
        log.info("[listing] page %d / %d → %s", page, MAX_LISTING_PAGES, url)

        soup = fetch(url)
        if soup is None:
            consecutive_empty += 1
            log.warning("[listing] page %d fetch failed (%d consecutive).", page, consecutive_empty)
        else:
            found = _process_listing_page(soup, cars)
            log.info(
                "[listing] page %d: %d cards  |  total so far: %d / ~%d",
                page, found, len(cars), expected,
            )
            consecutive_empty = 0 if found else consecutive_empty + 1

            # Save progress after every page
            save_json(cars, LISTING_OUTPUT)

        if consecutive_empty >= 5:
            log.error(
                "[listing] 5 consecutive empty/failed pages — stopping early at page %d.",
                page,
            )
            break

    log.info("STAGE 1 complete — %d unique listing URLs collected.", len(cars))
    return cars


# ══════════════════════════════════════════════════════════════════
#  STAGE 2 — DETAIL SCRAPER
#  Visits each individual car page and returns a rich record that
#  mirrors the sbtjapan JSON schema.
# ══════════════════════════════════════════════════════════════════

# ── image helpers ─────────────────────────────────────────────────

def _normalise_src(src: str) -> str:
    """Make the CDN URL absolute and upgrade thumbnail → full-size."""
    if src.startswith("//"):
        src = "https:" + src
    elif src.startswith("/"):
        src = BASE_URL + src
    if src.endswith(THUMB_SUFFIX):
        src = src[: -len(THUMB_SUFFIX)] + FULL_SUFFIX
    return src


def _is_valid_image(src: str) -> bool:
    return not any(pat in src for pat in EXCLUDE_IMAGE_PATTERNS)


def _extract_images(soup: BeautifulSoup) -> list[str]:
    """
    Collect all car photo URLs from the image-gallery widget.

    - Primary source: thumbnail nav (has every photo, even lazy-loaded ones).
      Each _100_100 thumbnail is upgraded to _640_0 full-size.
    - Supplement: main slide <img> tags (eager-loaded slides 1–2).
    - Excludes payment banners and site-asset images.
    """
    urls: list[str] = []
    seen: set[str] = set()

    def add(src: str) -> None:
        src = _normalise_src(src)
        if src and _is_valid_image(src) and src not in seen:
            seen.add(src)
            urls.append(src)

    thumb_nav = soup.select_one('nav[aria-label="Thumbnail Navigation"]')
    if thumb_nav:
        for img in thumb_nav.select("button.image-gallery-thumbnail img"):
            if src := img.get("src", ""):
                add(src)
        log.debug("[detail] %d images from thumbnail nav.", len(urls))

    # Supplement with eager-loaded main slides (deduplicated via `seen`)
    for slide_img in soup.select("div.image-gallery-slide img"):
        alt = slide_img.get("alt", "")
        if "CFJ" in alt or "image" in alt.lower():
            if src := slide_img.get("src", ""):
                add(src)

    if not urls:
        log.warning("[detail] No images found in gallery.")
    else:
        log.debug("[detail] %d unique image(s) extracted.", len(urls))

    return urls


# ── spec-table parser ─────────────────────────────────────────────

def _extract_specs(soup: BeautifulSoup) -> dict:
    """
    Parse the Car Specifications table (4-cell rows: label|value|label|value).
    Rows with colspan cells (e.g. VIN disclaimer) are silently skipped.
    """
    specs: dict = {}

    table = soup.select_one(
        "div.border-t-primary table, "
        "table.w-full.table-fixed"
    )
    if not table:
        log.warning("[detail] Specifications table not found.")
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
            key = SPEC_KEY_MAP.get(
                raw_label,
                raw_label.lower().replace(" ", "_").replace(".", "").replace("/", ""),
            )
            specs[key] = raw_value

    return specs


# ── accessories parser ────────────────────────────────────────────

def _extract_accessories(soup: BeautifulSoup) -> dict:
    """
    Parse the Accessories section into { category: [feature, ...] }.
    Categories: Comfort, Safety, Windows, Others, etc.
    """
    accessories: dict = {}

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
        items = [
            clean(s.get_text())
            for s in section.select("span.text-\\[13px\\]")
            if clean(s.get_text())
        ]
        if items:
            accessories[category] = items

    return accessories


# ── price parser ──────────────────────────────────────────────────

def _extract_prices(soup: BeautifulSoup) -> dict:
    prices: dict = {}
    els = soup.select(".car-price")
    if els:
        prices["car_price"] = clean(els[0].get_text())
    for el in els:
        if "font-bold" in (el.get("class") or []):
            prices["total_cnf"] = clean(el.get_text())
            break
    return prices


# ── title parser ──────────────────────────────────────────────────

def _extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        return clean(h1.get_text())
    title_tag = soup.find("title")
    if title_tag:
        return clean(title_tag.get_text()).split("|")[0].strip()
    return ""


# ── detail page assembler ─────────────────────────────────────────

# Fields guaranteed to exist in every output record (empty string if absent)
_DEFAULT_FIELDS = [
    "reference_no", "model_code", "registration_year", "manufacture_year",
    "model_grade", "transmission", "mileage", "engine_capacity", "fuel_type",
    "seats", "doors", "steering", "drive_type", "dimension",
    "exterior_color", "auction_grade", "vin_chassis_no",
    "car_price", "total_cnf",
]


def _parse_detail_page(url: str, soup: BeautifulSoup) -> dict:
    """Assemble one complete car record from a detail-page BeautifulSoup tree."""
    data: dict = {
        "car_url":    url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    data["title"]       = _extract_title(soup)
    data.update(_extract_specs(soup))
    data.update(_extract_prices(soup))
    data["accessories"] = _extract_accessories(soup)
    data["image_urls"]  = _extract_images(soup)

    # Guarantee every schema field is present
    for field in _DEFAULT_FIELDS:
        data.setdefault(field, "")

    log.info(
        "[detail] ref=%-12s  images=%2d  accessories=%s",
        data.get("reference_no", "?"),
        len(data["image_urls"]),
        {k: len(v) for k, v in data["accessories"].items()} or "{}",
    )
    return data


def scrape_detail(url: str) -> Optional[dict]:
    """Fetch and parse a single car detail page. Returns None on failure."""
    soup = fetch(url)
    if soup is None:
        return None
    return _parse_detail_page(url, soup)


def scrape_details(listing_cars: dict) -> dict:
    """
    Scrape the detail page for every URL in `listing_cars`.
    Saves incremental progress to DETAIL_OUTPUT after each car so the run can
    be inspected or resumed if interrupted.

    Returns { car_url: full_detail_dict, ... }
    """
    results: dict = {}
    urls  = list(listing_cars.keys())
    total = len(urls)

    log.info("STAGE 2 — detail scraper  |  %d cars to process", total)

    for idx, url in enumerate(urls, start=1):
        log.info("[detail] %d / %d  %s", idx, total, url)

        detail = scrape_detail(url)
        if detail:
            # Merge the quick summary fields from the listing stage
            listing_summary = listing_cars.get(url, {})
            for key in ("cfj_id", "photo_count", "delivery_port", "thumbnail_url"):
                if key in listing_summary and key not in detail:
                    detail[key] = listing_summary[key]
            results[url] = detail
        else:
            log.warning("[detail] Skipped (fetch failed): %s", url)

        # Save progress after every successful car
        if results:
            save_json(results, DETAIL_OUTPUT)

        if idx < total:
            time.sleep(REQUEST_DELAY)

    log.info("STAGE 2 complete — %d / %d cars scraped.", len(results), total)
    return results


# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def main() -> dict:
    """
    Run the full pipeline:
        Stage 1 → collect listing URLs  → LISTING_OUTPUT
        Stage 2 → scrape detail pages   → DETAIL_OUTPUT

    Returns the final details dict.
    """
    start = time.time()
    log.info("═" * 60)
    log.info("CarFromJapan combined scraper — starting")
    log.info("Listing pages : %d  (~%d cars)", MAX_LISTING_PAGES, MAX_LISTING_PAGES * PER_PAGE)
    log.info("Request delay : %.1f s", REQUEST_DELAY)
    log.info("Output files  : %s  /  %s", LISTING_OUTPUT, DETAIL_OUTPUT)
    log.info("═" * 60)

    # ── Stage 1 ───────────────────────────────────────────────────
    listing_cars = scrape_listings()
    save_json(listing_cars, LISTING_OUTPUT)

    # ── Stage 2 ───────────────────────────────────────────────────
    details = scrape_details(listing_cars)
    save_json(details, DETAIL_OUTPUT)

    elapsed = time.time() - start
    log.info("═" * 60)
    log.info("All done in %.0f s  |  %d cars saved to '%s'", elapsed, len(details), DETAIL_OUTPUT)
    log.info("═" * 60)

    # Print a preview of the first record
    if details:
        first = next(iter(details.values()))
        print("\n── Preview: first car ──")
        print(json.dumps(first, indent=2, ensure_ascii=False))

    return details


if __name__ == "__main__":
    main()