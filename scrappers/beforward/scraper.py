#!/usr/bin/env python3
"""
Beforward – full pipeline:
    - collect vehicle URLs from paginated stocklist
    - scrape each detail page (price, specs, images, features)
    - save all cars to a single JSON file.
"""

import time
import re
from urllib.parse import urljoin
from datetime import datetime

from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)

BASE_URL = "https://www.beforward.jp"
START_URL = "https://www.beforward.jp/stocklist/sar=steering/steering=Right/tp_country_id=27"
PROJECT_ROOT = get_project_root()
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "beforward"
LOG_DIR = PROJECT_ROOT / "logs" / "beforward"

DEFAULT_MAX_PAGES = None
REQUEST_DELAY = 1.5

def get_total_pages(soup, logger):
    """Read the highest page number from paginated results."""

    pages = [1]
    for a in soup.select("div.results-pagination ul li a"):
        text = a.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    total = max(pages)
    logger.info(f"Total pages detected: {total:,}")
    return total

def build_page_url(base_url, page):
    """
    BE FORWARD path-segment pagination:
      page 1 → /stocklist/sar=…
      page N → /stocklist/page=N/sar=…
    """
    if page == 1:
        return base_url
    return base_url.replace("/stocklist/", f"/stocklist/page={page}/", 1)

def extract_vehicle_urls(soup, logger) -> list:
    """
    Pull unique, non-SOLD vehicle URLs from one listing page.
    Only hrefs matching ``/make/model/variant/id/<id>/`` are accepted.
    """
    urls, seen = [], set()
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
            logger.debug("Found: %s", full_url)
    return urls

def scrape_vehicle_urls(logger, max_pages: int = None) -> list:
    all_urls = []
    soup = fetch(START_URL, logger=logger)
    if soup is None:
        return all_urls

    total_pages = get_total_pages(soup, logger)
    if max_pages:
        total_pages = min(total_pages, max_pages)
        logger.info(f"Capped at {max_pages} pages")

    page_urls = extract_vehicle_urls(soup, logger)
    all_urls.extend(page_urls)
    logger.info(f"Page 1/{total_pages} → {len(page_urls)} | Total: {len(all_urls)}")

    for page in range(2, total_pages + 1):
        url = build_page_url(START_URL, page)
        soup = fetch(url, logger=logger)
        if soup is None:
            logger.error(f"Page {page} failed, stopping.")
            break
        page_urls = extract_vehicle_urls(soup, logger)
        if not page_urls:
            logger.warning(f"Page {page}: no URLs found – stopping early")
            break
        all_urls.extend(page_urls)
        logger.info(f"Page {page}/{total_pages} → {len(page_urls)} | Total: {len(all_urls)}")
        time.sleep(REQUEST_DELAY)

    logger.info(f"Phase 1 complete — {len(all_urls)} URLs collected")
    return all_urls

# ----------------------------------------------------------------------
# Detail parsers
# ----------------------------------------------------------------------
def parse_title_and_ref(soup):
    title_tag = soup.select_one("div.car-info-flex-box h1")
    title = clean(title_tag.get_text()) if title_tag else "N/A"
    ref_tag = soup.select_one("div.detail-specs-text")
    ref_text = clean(ref_tag.get_text()) if ref_tag else ""
    parts = ref_text.split()
    model_code = parts[0] if parts else "N/A"
    ref_no = parts[1] if len(parts) > 1 else "N/A"
    return {"title": title, "model_code": model_code, "ref_no": ref_no}

def parse_pricing(soup):
    price = soup.select_one("span.price.ip-usd-price")
    total = soup.select_one("span#fn-vehicle-price-total-price")
    orig = soup.select_one("p.original-vehicle-price")
    save = soup.select_one("p#fn-current-save-rate")
    port = soup.select_one("p.destination-port")
    quote = soup.select_one("span#fn-vehicle-price-quote-type")
    return {
        "currency": "$",
        "vehicle_price": clean(price.get_text()) if price else "N/A",
        "total_price": clean(total.get_text()) if total else "N/A",
        "original_price": clean(orig.get_text()) if orig else "N/A",
        "discount_rate": clean(save.get_text()) if save else "N/A",
        "destination_port": clean(port.get_text(separator=" ")) if port else "N/A",
        "quote_type": clean(quote.get_text()) if quote else "N/A",
    }

def parse_specs_table(soup):
    """
    Full specification table (``table.specification``).
    Each row contains alternating th/td pairs → flattened to snake_case dict.
    """
    specs = {}
    table = soup.select_one("table.specification")
    if not table:
        return specs
    for row in table.select("tr"):
        cells = row.find_all(["th", "td"])
        for i in range(0, len(cells) - 1, 2):
            label = clean(cells[i].get_text(separator=" ")).lower()
            value = clean(cells[i+1].get_text()) if i+1 < len(cells) else ""
            label = re.sub(r"\s+", "_", label).strip("_")
            key = slugify(label)
            if key and value:
                specs[key] = value
    return specs

def parse_pickup_specs(soup):
    specs = {}
    table = soup.select_one("div.pickup-specification table")
    if not table:
        return specs
    
    rows = table.select("tr")
    if len(rows) < 2:
        return specs
    
    headers = [clean(td.get_text()).lower() for td in rows[0].select("td")]
    values = [clean(td.get_text(separator=" ")) for td in rows[1].select("td")]
    for h, v in zip(headers, values):
        specs[re.sub(r"\s+", "_", h)] = v
    return specs

def parse_location(soup):
    tag = soup.select_one("span.specs-pickup-icon b")
    return {"location": clean(tag.get_text()) if tag else "N/A"}

def parse_features(soup):
    features = []
    for li in soup.select("div.remarks li"):
        if "attached_on" in li.get("class", []):
            features.append(clean(li.get_text()))
    return features

def parse_images(soup):
    images, seen = [], set()
    for inp in soup.select("input.fn-images-pc"):
        path = inp.get("data-path", "")
        if path and path not in seen:
            images.append(("https:" + path) if path.startswith("//") else path)
            seen.add(path)
    return images

def parse_total_image_count(soup):
    tag = soup.select_one("span#fn-slider-total")
    try:
        return int(tag.get_text(strip=True)) if tag else 0
    except ValueError:
        return 0

def parse_detail_page(soup, car_url, logger):
    title_ref = parse_title_and_ref(soup)
    pricing = parse_pricing(soup)
    location = parse_location(soup)
    pickup = parse_pickup_specs(soup)
    specs = parse_specs_table(soup)
    features = parse_features(soup)
    images = parse_images(soup)
    image_count = parse_total_image_count(soup)

    car = {
        "car_url": car_url,
        "scraped_at": datetime.now().isoformat(),
        "source": "beforward",
        **title_ref,
        **pricing,
        **location,
        **pickup,
        **specs,
        "features": features,
        "image_count": image_count,
        "images": images,
    }
    logger.info(
        f"Parsed: {title_ref.get('title')} | Ref: {title_ref.get('ref_no')} | Price: {pricing.get('vehicle_price')} | Images: {image_count}")
    return car

def scrape_detail(url, logger):
    soup = fetch(url, logger=logger)
    if soup is None:
        logger.error(f"Failed to fetch {url}")
        return None
    return parse_detail_page(soup, url, logger)

# ----------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------
def run(max_pages: int = DEFAULT_MAX_PAGES):
    logger = my_logger("beforward", log_dir=LOG_DIR)
    logger.info("Beforward scraper started")
    urls = scrape_vehicle_urls(logger, max_pages)
    if not urls:
        logger.error("No URLs found, exiting.")
        return

    all_cars = []
    for idx, url in enumerate(urls, 1):
        logger.info(f"Scraping {idx}/{len(urls)}: {url}")
        car = scrape_detail(url, logger)
        if car:
            all_cars.append(car)
        time.sleep(REQUEST_DELAY)

    out_file = OUTPUT_DIR / f"beforward_all_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_to_json(all_cars, out_file, logger)
    logger.info(f"Pipeline complete – {len(all_cars)} cars saved.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Number of listing pages to scrape (default: all)")
    args = parser.parse_args()
    run(max_pages=args.max_pages)