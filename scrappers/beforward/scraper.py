#!/usr/bin/env python3
"""
Scrape a single BE FORWARD vehicle detail page and extract all key information.

Usage:
    python scrape_beforward_car.py <url> [--output OUTPUT_FILE]

Example:
    python scrape_beforward_car.py https://www.beforward.jp/toyota/regiusace-van/cc260209/id/14289814/ --output car.json
"""
import requests
import json
import logging
import time
import re
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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

def fetch(url: str, logger: logging.Logger):
    logger.debug(f"GET {url}")
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ─────────────────────────────────────────────────────────────
# PAGINATION
# BE FORWARD uses path-based pagination:
# /stocklist/page=2/sar=steering/steering=Right/tp_country_id=27
# The last page number is shown in the pagination list (up to 4000)
# ─────────────────────────────────────────────────────────────

def get_total_pages(soup, logger: logging.Logger) -> int:
    """
    Extracts the highest page number from the pagination list.
    BE FORWARD pagination structure:
      <li><a href="/stocklist/page=4000/...">4000</a></li>
    """
    pages = [1]
    for li in soup.select("div.results-pagination ul li a"):
        text = li.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))

    total = max(pages)
    logger.info(f"Total pages detected: {total:,}")
    return total


def build_page_url(base_url: str, page: int) -> str:
    """
    BE FORWARD uses path segments instead of query params.
    Page 1: /stocklist/sar=steering/steering=Right/tp_country_id=27
    Page 2: /stocklist/page=2/sar=steering/steering=Right/tp_country_id=27
    """
    if page == 1:
        return base_url

    # Insert page=N after /stocklist/
    return base_url.replace("/stocklist/", f"/stocklist/page={page}/", 1)


# ─────────────────────────────────────────────────────────────
# URL EXTRACTION
# Vehicle links appear in two places per card:
# 1. <a href="/toyota/sienta/bw726274/id/9989384/"> (photo col)
# 2. <a class="vehicle-url-link" href="..."> (multiple per card)
# We use vehicle-url-link and deduplicate.
# ─────────────────────────────────────────────────────────────

def extract_vehicle_urls(soup, logger: logging.Logger) -> list:
    """
    Extracts all unique vehicle detail URLs from a single listing page.
    Skips sold vehicles, banner rows, and non-vehicle links.
    """
    urls = []
    seen = set()

    for row in soup.select("tr.stocklist-row"):
        # Skip banner/login rows — they have no photo-col
        if not row.select_one("td.photo-col"):
            continue

        # Skip SOLD listings — we only want available cars
        if row.select_one("div.price-col-sold"):
            logger.debug("Skipping SOLD listing")
            continue

        # Get the first vehicle-url-link in this row (all links point to same car)
        link = row.select_one("a.vehicle-url-link")
        if not link:
            continue

        href = link.get("href", "").strip()
        if not href or href in seen:
            continue

        # Only keep paths matching /make/model/ref/id/ pattern
        if re.match(r"^/[^/]+/[^/]+/[^/]+/id/\d+/$", href):
            full_url = urljoin(BASE_URL, href)
            urls.append(full_url)
            seen.add(href)
            logger.debug(f"Found: {full_url}")

    return urls


# ─────────────────────────────────────────────────────────────
# JSON OUTPUT
# ─────────────────────────────────────────────────────────────

def save_to_json(urls: list, logger: logging.Logger) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path  = OUTPUT_DIR / f"vehicle_urls_{timestamp}.json"

    payload = {
        "source":     START_URL,
        "scraped_at": datetime.now().isoformat(),
        "total":      len(urls),
        "urls":       urls,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(urls):,} URLs → {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────────────────────────

def scrape_vehicle_urls(max_pages: int = None) -> list:
    """
    Scrapes all pages and returns a list of vehicle detail URLs.

    Args:
        max_pages: optional cap e.g. max_pages=10 for testing.
                   Pass None to scrape all pages (up to 4000).
    """
    logger    = setup_logger("beforward_urls")
    all_urls  = []

    logger.info("=" * 60)
    logger.info("BE FORWARD vehicle URL scraper started")
    logger.info(f"Source: {START_URL}")
    logger.info("=" * 60)

    # Fetch page 1 to detect total pages
    try:
        soup = fetch(START_URL, logger)
    except requests.RequestException as e:
        logger.error(f"Failed to fetch page 1: {e}")
        return all_urls

    total_pages = get_total_pages(soup, logger)

    if max_pages:
        total_pages = min(total_pages, max_pages)
        logger.info(f"Capped at {max_pages} pages")

    # Parse page 1
    page_urls = extract_vehicle_urls(soup, logger)
    all_urls.extend(page_urls)
    logger.info(f"Page 1/{total_pages} → {len(page_urls)} URLs | Total: {len(all_urls):,}")

    # Pages 2..N
    for page in range(2, total_pages + 1):
        url = build_page_url(START_URL, page)
        try:
            soup      = fetch(url, logger)
            page_urls = extract_vehicle_urls(soup, logger)

            if not page_urls:
                logger.warning(f"Page {page} returned no URLs — stopping early")
                break

            all_urls.extend(page_urls)
            logger.info(f"Page {page}/{total_pages} → {len(page_urls)} URLs | Total: {len(all_urls):,}")

        except requests.RequestException as e:
            logger.error(f"Page {page} failed: {e}")
            break

        time.sleep(1.5)

    # Save to JSON
    save_to_json(all_urls, logger)

    logger.info("=" * 60)
    logger.info(f"Done. Total vehicle URLs collected: {len(all_urls):,}")
    logger.info("=" * 60)

    return all_urls


if __name__ == "__main__":
    # Test run — first 5 pages only
    # Remove max_pages to scrape all 4000 pages
    urls = scrape_vehicle_urls(max_pages=5)

    print(f"\nTotal: {len(urls)} URLs")
    for url in urls[:5]:
        print(url)
        
import argparse
import json
import re
import sys
from typing import Optional, Dict, Any

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_soup(url: str) -> Optional[BeautifulSoup]:
    """Fetch the URL and return a BeautifulSoup object."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def clean_text(text: Optional[str]) -> str:
    """Strip and normalise whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()

def extract_from_spec_table(soup: BeautifulSoup, label: str) -> str:
    """
    Extract a value from the specification table (class="specification").
    Looks for a <th> containing the label and returns the next <td> text.
    """
    # Find the th that exactly or partially matches the label (case‑insensitive)
    th = soup.find("th", string=re.compile(re.escape(label), re.IGNORECASE))
    if not th:
        # Try finding any th with the label in its text
        th = soup.find("th", string=lambda s: s and label.lower() in s.lower())
    if th:
        td = th.find_next_sibling("td")
        if td:
            return clean_text(td.get_text())
    return ""

def extract_from_pickup_table(soup: BeautifulSoup, label: str) -> str:
    """
    Extract a value from the pickup specification table (class="pickup-specification").
    The table has rows of 5 columns; we find the <td> that follows the label.
    """
    pickup_table = soup.find("div", class_="pickup-specification")
    if not pickup_table:
        return ""
    # The labels are in <td class="specs-pickup-text">
    for row in pickup_table.find_all("tr"):
        labels = row.find_all("td", class_="specs-pickup-text")
        values = row.find_all("td", class_="pickup-specification-text")
        for i, lbl in enumerate(labels):
            if label.lower() in clean_text(lbl.get_text()).lower():
                if i < len(values):
                    return clean_text(values[i].get_text())
    return ""

def extract_features(soup: BeautifulSoup):
    """
    Extract the features list from the .remarks section.
    Returns a dict with keys "available" and "not_available".
    """
    features = []
    remarks = soup.find("div", class_="remarks")
    if not remarks:
        return features

    for li in remarks.find_all("li"):
        text = clean_text(li.get_text())
        if not text:
            continue
        if "attached_on" in li.get("class", []):
            features.append(text)
        else:
            # fallback: if no class, assume available? We'll skip.
            pass
    return features

def scrape_car_page(url: str) -> Dict[str, Any]:
    """
    Extract all required car information from the BE FORWARD detail page.
    """
    soup = fetch_soup(url)
    if not soup:
        return {}

    data: Dict[str, Any] = {}

    # ----- Basic info (from title and right panel) -----
    # Title: h1 contains make and model (e.g., "2012 TOYOTA REGIUSACE VAN WIDE SUPER GL")
    h1 = soup.find("h1")
    if h1:
        full_title = clean_text(h1.get_text())
        data["title"] = full_title
        # Try to extract year, make, model from title
        # Example: "2012 TOYOTA REGIUSACE VAN WIDE SUPER GL"
        parts = full_title.split()
        if parts and parts[0].isdigit():
            data["year"] = parts[0]
            if len(parts) > 1:
                data["make"] = parts[1]
                # The rest is model + grade
                data["model"] = " ".join(parts[2:]) if len(parts) > 2 else ""
        else:
            data["year"] = ""
            data["make"] = ""
            data["model"] = ""

    # Stock ID (Ref. No.)
    data["stock_id"] = extract_from_spec_table(soup, "Ref. No.")

    # Model code
    data["model_code"] = extract_from_spec_table(soup, "Model Code")

    # Mileage
    mileage_raw = extract_from_spec_table(soup, "Mileage")
    data["mileage"] = mileage_raw

    # Engine (Engine Size)
    data["engine"] = extract_from_spec_table(soup, "Engine Size")

    # Transmission – from pickup table or spec table
    trans = extract_from_pickup_table(soup, "Trans.") or extract_from_spec_table(soup, "Transmission")
    data["transmission"] = trans

    # Drive type
    data["drive_type"] = extract_from_spec_table(soup, "Drive")

    # Steering
    data["steering"] = extract_from_spec_table(soup, "Steering")

    # Fuel type
    data["fuel_type"] = extract_from_spec_table(soup, "Fuel")

    # Doors
    data["doors"] = extract_from_spec_table(soup, "Doors")

    # Seats
    data["seats"] = extract_from_spec_table(soup, "Seats")

    # Color (Ext. Color)
    data["color"] = extract_from_spec_table(soup, "Ext. Color")

    # Location
    data["location"] = extract_from_spec_table(soup, "Location")

    # Grade / Version
    data["grade"] = extract_from_spec_table(soup, "Version/Class")

    # Body type – not explicitly present in the given snippet, but we can try to find a row with "Body Type"
    data["body_type"] = extract_from_spec_table(soup, "Body Type")
    if not data["body_type"]:
        # Fallback: maybe from the "About this vehicle" paragraph? Leave empty.
        data["body_type"] = ""

    # Registration year/month
    reg = extract_from_spec_table(soup, "Registration Year/month")
    if reg and "/" in reg:
        parts = reg.split("/")
        data["year"] = data.get("year", parts[0].strip())
        data["month"] = parts[1].strip() if len(parts) > 1 else ""
    else:
        data["month"] = ""

    # Manufacture year/month (optional, but we can store)
    data["manufacture_year_month"] = extract_from_spec_table(soup, "Manufacture Year/month")

    # ----- Pricing and currency -----
    # Vehicle price
    price_elem = soup.select_one(".vehicle-price .price")
    if price_elem:
        price_text = clean_text(price_elem.get_text())
        # Extract currency symbol and numeric value
        match = re.match(r"([\$€£¥])([\d,]+)", price_text)
        if match:
            data["currency"] = match.group(1)
            data["vehicle_price"] = match.group(2)
        else:
            data["currency"] = ""
            data["vehicle_price"] = price_text
    else:
        data["currency"] = ""
        data["vehicle_price"] = ""

    # Total price (CIF or Total Price)
    total_elem = soup.select_one("#fn-vehicle-price-total-price")
    if total_elem:
        total_val = clean_text(total_elem.get_text())
        data["total_price"] = total_val
    else:
        # fallback: find .total-price .price or similar
        total_alt = soup.select_one(".total-price .price")
        if total_alt:
            data["total_price"] = clean_text(total_alt.get_text())
        else:
            data["total_price"] = ""

    # ----- Vehicle Details (Make, Model, Body color, Body Type, Doors, Seats) -----
    # Some of these we already have, but we can fill missing from other tables
    data["vehicle_details"] = {
        "Make": data.get("make", ""),
        "Model": data.get("model", ""),
        "Body color": data.get("color", ""),
        "Body Type": data.get("body_type", ""),
        "Doors": data.get("doors", ""),
        "Seats": data.get("seats", ""),
    }

    # ----- Specifications (Dimension, M3, Weight, Gross Weight, Max Loading) -----
    data["specifications"] = {
        "Dimension": extract_from_spec_table(soup, "Dimension"),
        "M3": extract_from_spec_table(soup, "M3"),
        "Vehicle Weight": extract_from_spec_table(soup, "Weight"),
        "Gross Vehicle Weight": extract_from_spec_table(soup, "Gross Vehicle Weight"),
        "Max Loading Capacity": extract_from_spec_table(soup, "Max.Cap"),
    }

    # ----- Features list (available / not available) -----
    data["features"] = extract_features(soup)

    # Additional useful info: image count (optional)
    total_images = soup.select_one("#fn-slider-total")
    if total_images:
        data["image_count"] = clean_text(total_images.get_text())
    else:
        data["image_count"] = ""

    return data

def main():
    parser = argparse.ArgumentParser(description="Scrape a BE FORWARD car detail page")
    parser.add_argument("url", help="Vehicle URL (e.g., https://www.beforward.jp/toyota/regiusace-van/cc260209/id/14289814/)")
    parser.add_argument("--output", "-o", default="car_data.json", help="Output JSON file name")
    args = parser.parse_args()

    data = scrape_car_page(args.url)
    if not data:
        print("Failed to extract data. Exiting.", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved extracted data to {args.output}")
    # Print a quick summary
    print(f"Stock ID: {data.get('stock_id')}")
    print(f"Title: {data.get('title')}")
    print(f"Price: {data.get('currency')}{data.get('vehicle_price')}  |  Total: {data.get('total_price')}")

if __name__ == "__main__":
    main()