#!/usr/bin/env python3
"""
SBTJapan – full pipeline:
    - collect car detail URLs from search results (paginated)
    - scrape each detail page and save a single JSON file with all cars.
"""

import time
from urllib.parse import urljoin
from datetime import datetime
from base import (
    my_logger, fetch, clean, save_to_json, get_project_root, slugify
)

BASE_SEARCH_URL = "https://www.sbtjapan.com/used-cars/search"
PROJECT_ROOT = get_project_root()
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "sbtjapan"
LOG_DIR = PROJECT_ROOT / "logs" / "sbtjapan"

DEFAULT_MAX_PAGES = None      
REQUEST_DELAY = 1.5

def get_total_pages(soup) -> int:
    """Return the highest page number found in the pagination links."""
    pages = []
    for link in soup.select("a.pagination__link"):
        text = link.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    return max(pages) if pages else 1

def get_car_detail_urls(search_url, logger, max_pages=None):
    """Pull all ``<a class='card-product__wrap'>`` hrefs from one listing page."""
    detail_urls = []

    logger.info(f"Fetching page 1: {search_url}")
    soup = fetch(search_url, logger=logger)
    if soup is None:
        return detail_urls

    total_pages = get_total_pages(soup)
    if max_pages:
        total_pages = min(total_pages, max_pages)
    logger.info(f"Total pages: {total_pages}")

    # Page 1 (already fetched)
    for anchor in soup.select("a.card-product__wrap"):
        href = anchor.get("href", "")
        if href:
            detail_urls.append(urljoin("https://www.sbtjapan.com", href))

    # Pages 2..N
    for page in range(2, total_pages + 1):
        paged_url = f"{search_url}?page={page}"
        logger.info(f"Fetching page {page}/{total_pages} | URLs so far: {len(detail_urls)}")
        soup = fetch(paged_url, logger=logger)
        if soup is None:
            logger.error(f"Failed on page {page}, stopping.")
            break
        for anchor in soup.select("a.card-product__wrap"):
            href = anchor.get("href", "")
            if href:
                detail_urls.append(urljoin("https://www.sbtjapan.com", href))
        time.sleep(REQUEST_DELAY)

    logger.info(f"Done — {len(detail_urls)} detail URLs collected")
    return detail_urls

def parse_header(soup):
    """Title, model code, manufacture year, and body type from the page header."""
    name_tag = soup.select_one("h1.product-detail__name")
    title = clean(name_tag.get_text()) if name_tag else "N/A"
    detail_items = [clean(el.get_text()) for el in soup.select("div.product-detail__detail-item")]
    return {
        "title": title,
        "model_code": detail_items[0] if len(detail_items) > 0 else "N/A",
        "manufacture_year": detail_items[1] if len(detail_items) > 1 else "N/A",
        "body_type": detail_items[2] if len(detail_items) > 2 else "N/A",
    }

def parse_identification(soup):
    """Stock ID and inventory location from the profile block."""
    stock_tag = soup.select_one("span.product-detail__id-number")
    location_tag = soup.select_one("div.product-detail__location-country")
    return {
        "stock_id": clean(stock_tag.get_text()) if stock_tag else "N/A",
        "location": clean(location_tag.get_text()) if location_tag else "N/A",
    }

def parse_pricing(soup):
    """
    Vehicle price, total price, and full pricing breakdown
    (freight, inspection, insurance, vanning) from the embedded price modal.
    """
    base_price = soup.select_one("span.product-detail__base-price-range")
    base_currency = soup.select_one("span.product-detail__base-price-currency")
    total_tag = soup.select_one("div#total_amount")
    def get_detail(el_id):
        el = soup.select_one(f"div#{el_id}")
        return clean(el.get_text()) if el else "N/A"
    return {
        "currency": clean(base_currency.get_text()) if base_currency else "USD",
        "vehicle_price": clean(base_price.get_text()) if base_price else "N/A",
        "total_price": clean(total_tag.get_text()) if total_tag else "N/A",
        "freight_amount": get_detail("freight_amount"),
        "inspection_amount": get_detail("inspection_amount"),
        "insurance_amount": get_detail("insurance_amount"),
        "vanning_amount": get_detail("vanning_amount"),
        "vehicle_price_breakdown": get_detail("vehicle_price"),
    }

def parse_car_specs(soup):
    """
    Specification items from ``div.product-detail__status-area``.
    Each item has a label div + value div → snake_case dict.
    """
    specs = {}
    for item in soup.select("div.product-detail__status-item"):
        label_el = item.select_one("div.product-detail__status-label")
        value_el = item.select_one("div.product-detail__status-value")
        if label_el and value_el:
            key = slugify(clean(label_el.get_text()).lower().replace(" ", "_"))
            if key == "door":
                key = "doors"
            specs[key] = clean(value_el.get_text())
    return specs

def parse_info_lists(soup):
    """Additional info blocks (registration, chassis, etc.)."""
    info = {}
    for block in soup.select("div.product-detail__info-block"):
        for item in block.select("li.product-detail__info-item"):
            label_el = item.select_one("div.product-detail__info-label")
            value_el = item.select_one("div.product-detail__info-value")
            if label_el and value_el:
                key = slugify(clean(label_el.get_text()).lower().replace(" ", "_"))
                info[key] = clean(value_el.get_text())
    return info

def parse_image_urls(soup):
    """
    Full-size gallery image URLs from the main gallery slider.
    Skips blank filler slides with no ``<img>``.
    """
    urls = []
    gallery = soup.select_one("div.product-detail__gallery-slider")
    if gallery:
        for slide in gallery.select("div.swiper-slide"):
            img = slide.select_one("div.product-detail__main-image img")
            if img and img.get("src"):
                urls.append(img["src"])
    return urls

def parse_options(soup):
    """
    Available car options grouped by category.
    Categories with zero available features are omitted.
    """
    options = {}
    for block in soup.select("div.product-detail__option-block"):
        cat_el = block.select_one("div.product-detail__option-category")
        if not cat_el:
            continue
        category = clean(cat_el.get_text())
        available = [clean(el.get_text()) for el in block.select("div.product-detail__option-item.-available")]
        if available:
            options[category] = available
    return options

def parse_modal_fields(soup):
    """
    Hidden form fields from the price-estimate modal — make, model, grade, etc.
    """
    fields = {}
    field_map = {
        "make": "make", "model": "model", "name": "model_name",
        "year": "manufacture_year", "month": "manufacture_month",
        "grade": "grade", "make_id": "make_id", "body_type": "body_type",
        "mileage": "mileage_raw"
    }
    for field, key in field_map.items():
        inp = soup.select_one(f'form#get_estimate_id input[name="{field}"]')
        if inp:
            fields[key] = inp.get("value", "").strip()
    return fields

def parse_engagement(soup):
    """View count, favourite count, rating, and review count."""
    view = soup.select_one("div.product-detail__view-counter")
    fav = soup.select_one("div.product-detail__favorite-counter")
    rating = soup.select_one("span.avg-score")
    reviews = soup.select_one("span.reviews-qa-label")
    return {
        "view_count": clean(view.get_text()) if view else "N/A",
        "favourite_count": clean(fav.get_text()) if fav else "N/A",
        "rating": clean(rating.get_text()) if rating else "N/A",
        "reviews": clean(reviews.get_text()) if reviews else "N/A",
    }

def parse_individual_car_page(soup, car_url, logger):
    """Master parser — merges all section parsers into one flat car dict."""
    header = parse_header(soup)
    ident = parse_identification(soup)
    pricing = parse_pricing(soup)
    specs = parse_car_specs(soup)
    info = parse_info_lists(soup)
    images = parse_image_urls(soup)
    options = parse_options(soup)
    modal = parse_modal_fields(soup)
    engagement = parse_engagement(soup)

    car = {
        "car_url": car_url,
        "scraped_at": datetime.now().isoformat(),
        **header,
        **ident,
        **pricing,
        **modal,
        **specs,
        **info,
        **engagement,
        "image_urls": images,
        "car_options": options,
    }
    logger.info(f"Parsed {ident.get('stock_id')} | {header.get('title')} | {len(images)} images | {sum(len(v) for v in options.values())} options")
    return car

def scrape_detail(car_url, logger):
    soup = fetch(car_url, logger=logger)
    if soup is None:
        logger.error(f"Failed to fetch {car_url}")
        return {}
    return parse_individual_car_page(soup, car_url, logger)

# ----------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------
def run(search_url: str = BASE_SEARCH_URL, max_pages: int = DEFAULT_MAX_PAGES):
    logger = my_logger("sbtjapan", log_dir=LOG_DIR)
    logger.info("SBTJapan scraper started")
    urls = get_car_detail_urls(search_url, logger, max_pages)
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

    out_file = OUTPUT_DIR / f"sbtjapan_all_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_to_json(all_cars, out_file, logger)
    logger.info(f"Pipeline complete – {len(all_cars)} cars saved.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Number of listing pages to scrape (default: all)")
    args = parser.parse_args()
    run(max_pages=args.max_pages)