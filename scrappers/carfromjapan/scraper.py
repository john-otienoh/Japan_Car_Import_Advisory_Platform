"""
CarFromJapan Scraper
Scrapes all car listings from https://carfromjapan.com/cheap-used-cars-for-sale
Fixed at 400 pages × 25 listings per page = ~10,000 total listings.

Requirements:
    pip install requests beautifulsoup4 lxml

Usage:
    python carfromjapan_scraper.py
    # or import and call directly:
    # from carfromjapan_scraper import scrape_all_cars
    # cars = scrape_all_cars()
"""

import time
import json
import re
import logging
from typing import Optional
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://carfromjapan.com"
START_PATH = "/cheap-used-cars-for-sale"

TOTAL_PAGES = 400
PER_PAGE    = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://carfromjapan.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── helpers ───────────────────────────────────────────────────────────────────

def get_page(url: str, params: Optional[dict] = None, retries: int = 3) -> Optional[BeautifulSoup]:
    """Fetch a page and return a BeautifulSoup object, with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            log.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, e)
            if attempt < retries:
                time.sleep(3 * attempt)
    return None


def clean(text: Optional[str]) -> str:
    """Strip and normalise whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# ── per-card extraction ───────────────────────────────────────────────────────

def parse_car_card(card) -> dict:
    """
    Extract all available fields from a single car listing card.
    Returns a dict with car data and 'url' as the canonical key.
    """
    data: dict = {}

    # --- URL & title ---
    title_tag = card.select_one("h3 a")
    if title_tag:
        data["title"] = clean(title_tag.get_text())
        href = title_tag.get("href", "")
        data["url"] = BASE_URL + href if href.startswith("/") else href
    else:
        data["title"] = ""
        data["url"] = ""

    # --- CFJ reference ID (from compare checkbox) ---
    compare_div = card.select_one("[id^='compare-']")
    if compare_div:
        data["cfj_id"] = compare_div.get_text(strip=True).replace("Compare (", "").rstrip(")")

    # --- Photo count ---
    photo_btn = card.select_one(".z-3")
    if photo_btn:
        photo_text = clean(photo_btn.get_text())
        m = re.search(r"\((\d+)\)", photo_text)
        data["photo_count"] = int(m.group(1)) if m else None

    # --- Spec grid (Registration year / Mileage / Model code / Engine / Grade / Transmission) ---
    spec_rows = card.select("div.flex.mt-2\\.5")
    for row in spec_rows:
        items = row.find_all("div", class_=lambda c: c and "flex-1" in c, recursive=False)
        for item in items:
            label_el = item.select_one(".text-xs")
            value_el = label_el.find_next_sibling() if label_el else None
            if not label_el or not value_el:
                continue
            label = clean(label_el.get_text()).lower().replace(" ", "_")
            value = clean(value_el.get_text())
            if value and value != "-":
                data[label] = value

    # --- Prices ---
    price_section = card.select_one(".relative.w-61")
    if price_section:
        car_price_el = price_section.select_one(".car-price")
        if car_price_el:
            data["car_price"] = clean(car_price_el.get_text())

        delivery_el = price_section.select_one(".max-w-35.line-clamp-1")
        if delivery_el:
            data["delivery_port"] = clean(delivery_el.get_text())

        total_el = price_section.select_one(".car-price.font-bold")
        if total_el:
            data["total_cnf"] = clean(total_el.get_text())

    # --- Image URL ---
    img = card.select_one("img[alt*='CFJ']")
    if img:
        src = img.get("src", "")
        data["image_url"] = "https:" + src if src.startswith("//") else src

    return data


# ── page URL builder ──────────────────────────────────────────────────────────

def build_page_url(page: int) -> str:
    return f"{BASE_URL}{START_PATH}?page={page}"


# ── main scraper ──────────────────────────────────────────────────────────────

def process_page(soup: BeautifulSoup, cars: dict) -> int:
    """Parse all car cards on a page and add them to the cars dict. Returns count found."""
    cards = soup.select('[data-testid="car-item-list"]')
    for card in cards:
        car = parse_car_card(card)
        if car.get("url"):
            cars[car["url"]] = car
    return len(cards)


def scrape_all_cars(
    max_pages: Optional[int] = None,
    delay: float = 1.5,
    start_page: int = 1,
) -> dict:
    """
    Scrape pages 1 … TOTAL_PAGES (400) and return a dict keyed by car URL.

    Args:
        max_pages:   Override the page ceiling (default: TOTAL_PAGES = 400).
        delay:       Polite delay in seconds between requests (default: 1.5).
        start_page:  Resume from this page number (default: 1).

    Returns:
        { "https://carfromjapan.com/cheap-used-...": { ...car fields... }, ... }
    """
    cars: dict = {}
    total = min(max_pages, TOTAL_PAGES) if max_pages else TOTAL_PAGES
    expected_total = total * PER_PAGE

    log.info(
        "Starting scrape: pages %d – %d  |  ~%d listings expected  |  delay=%.1fs",
        start_page, total, expected_total, delay,
    )

    consecutive_empty = 0  # stop early if the site stops returning cars

    for page in range(start_page, total + 1):
        if page > start_page:
            time.sleep(delay)

        url = build_page_url(page)
        log.info("Fetching page %d / %d → %s", page, total, url)

        soup = get_page(url)
        if soup is None:
            log.warning("Page %d: fetch failed — skipping.", page)
            consecutive_empty += 1
        else:
            found = process_page(soup, cars)
            log.info(
                "Page %d: %d cars found  |  running total: %d / ~%d",
                page, found, len(cars), expected_total,
            )

            if found == 0:
                consecutive_empty += 1
                log.warning("Page %d returned 0 cars (%d consecutive empty).", page, consecutive_empty)
            else:
                consecutive_empty = 0  # reset on success

        # Abort if 5 pages in a row yield nothing (site may have changed / blocked us)
        if consecutive_empty >= 5:
            log.error(
                "5 consecutive empty/failed pages — stopping early at page %d. "
                "Check your User-Agent / IP / site structure.",
                page,
            )
            break

    log.info("Scraping complete. Total unique cars: %d", len(cars))
    return cars


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            f"Scrape carfromjapan.com listings  "
            f"[fixed: {TOTAL_PAGES} pages × {PER_PAGE} listings each]"
        )
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help=f"Override page limit (default: {TOTAL_PAGES})",
    )
    parser.add_argument(
        "--start-page", type=int, default=1,
        help="Resume from this page number (default: 1)",
    )
    parser.add_argument(
        "--delay", type=float, default=1.5,
        help="Seconds between page requests (default: 1.5)",
    )
    parser.add_argument(
        "--output", default="cars.json",
        help="Output JSON file (default: cars.json)",
    )
    args = parser.parse_args()

    result = scrape_all_cars(
        max_pages=args.max_pages,
        delay=args.delay,
        start_page=args.start_page,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n  Saved {len(result):,} cars to '{args.output}'")
    print(f"    Expected ≈ {TOTAL_PAGES * PER_PAGE:,}  |  "
          f"Got {len(result):,}  |  "
          f"Coverage {len(result) / (TOTAL_PAGES * PER_PAGE) * 100:.1f}%")

    # Pretty-print first 2 entries as a preview
    preview = dict(list(result.items()))
    print("\n── Preview (first 2 cars) ──")
    print(json.dumps(preview, indent=2, ensure_ascii=False))