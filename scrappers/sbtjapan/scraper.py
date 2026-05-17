import requests
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup

BASE_URL    = "https://www.sbtjapan.com/used-cars/search"
OUTPUT_DIR  = Path("data/raw/sbtjapan/data")          # JSON files saved here
LOG_DIR     = Path("logs")              # Log files saved here

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch(url: str):
    """
    Fetch a URL and return a BeautifulSoup object of the parsed HTML.
    
    This function handles common network errors, retries on failure,
    and validates the URL before making the request.
    
    Args:
        url (str): The complete URL to fetch (must include scheme like http:// or https://).
    
    Returns:
        BeautifulSoup | None: A BeautifulSoup object parsed with 'html.parser',
        or None if the request fails after all retries.
    
    """
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")

def get_total_pages(soup) -> int:
    """
    Extract the total number of pages from pagination links.

    This function parses a BeautifulSoup object to find all anchor tags with the class
    'pagination__link', filters the text content that consists of digits, and returns
    the highest page number found. If no numeric page links are present, it defaults
    to 1 (indicating a single page).

    Args:
        soup (BeautifulSoup): A BeautifulSoup object of the HTML page containing the pagination elements.

    Returns:
        int: The maximum page number found from the pagination links, or 1 if no
            numeric links exist.
    """
    pages = []
    for link in soup.select("a.pagination__link"):
        text = link.get_text(strip=True)
        if text.isdigit():
            pages.append(int(text))
    return max(pages) if pages else 1

def get_car_detail_urls(search_url: str) -> list:
    """
    Scrapes all pages of a search URL and returns a flat list of
    individual car detail URLs e.g. https://www.sbtjapan.com/used-cars/AI1937

    Args:
        search_url: A brand-level search URL e.g.
                    https://www.sbtjapan.com/used-cars/search/

    Returns:
        list[str]: All individual car detail URLs found across all pages.
    """
    detail_urls = []

    # # Strip any stale page param so we always start from page 1
    # base_url = search_url.split("&page=")[0]

    log.info(f"Fetching page 1: {BASE_URL}")
    soup = fetch(BASE_URL)

    total_pages = get_total_pages(soup) - 5739
    log.info(f"Total pages: {total_pages}")

    # Extract from page 1 — already fetched, no extra request
    for anchor in soup.select("a.card-product__wrap"):
        href = anchor.get("href", "")
        if href:
            detail_urls.append(urljoin("https://www.sbtjapan.com", href))

    # Pages 2..N
    for page in range(2, total_pages + 1):
        paged_url = f"{BASE_URL}?page={page}"
        log.info(f"Fetching page {page}/{total_pages} | URLs so far: {len(detail_urls)}")

        try:
            soup = fetch(paged_url)
        except requests.RequestException as e:
            log.error(f"Failed on page {page}: {e}")
            break

        for anchor in soup.select("a.card-product__wrap"):
            href = anchor.get("href", "")
            if href:
                detail_urls.append(urljoin("https://www.sbtjapan.com", href))

        time.sleep(1.5)

    log.info(f"Done — {len(detail_urls)} detail URLs collected from {BASE_URL}")
    return detail_urls

def parse_header(soup):
    """
    Extracts title, manufacture date, model code, year and body type
    from the page header block.
    """
    name_tag = soup.select_one("h1.product-detail__name")
    title    = name_tag.get_text(strip=True) if name_tag else "N/A"

    detail_items = [
        el.get_text(strip=True)
        for el in soup.select("div.product-detail__detail-item")
    ]

    return {
        "title":            title,
        "model_code":       detail_items[0] if len(detail_items) > 0 else "N/A",
        "manufacture_year": detail_items[1] if len(detail_items) > 1 else "N/A",  # FIX 1: year → manufacture_year
        "body_type":        detail_items[2] if len(detail_items) > 2 else "N/A",
    }

def parse_identification(soup) -> dict:
    """
    Extracts stock ID and inventory location from the profile block.
    """
    stock_tag = soup.select_one("span.product-detail__id-number")
    stock_id  = stock_tag.get_text(strip=True) if stock_tag else "N/A"

    location_tag = soup.select_one("div.product-detail__location-country")
    location     = location_tag.get_text(strip=True) if location_tag else "N/A"

    return {
        "stock_id": stock_id,
        "location": location,
    }

def parse_pricing(soup):
    """
    Extracts vehicle price, total price, and the full pricing
    breakdown (freight, inspection, insurance, vanning) from the
    price calculator modal which is embedded in the HTML.
    """
    base_price_tag = soup.select_one("span.product-detail__base-price-range")
    base_currency = soup.select_one("span.product-detail__base-price-currency")

    total_tag = soup.select_one("div#total_amount")
    
    def get_detail(el_id: str) -> str:
        el = soup.select_one(f"div#{el_id}")
        return el.get_text(strip=True) if el else "N/A"

    return {
        "currency": base_currency.get_text(strip=True) if base_currency else "USD",
        "vehicle_price": base_price_tag.get_text(strip=True) if base_price_tag else "N/A",
        "total_price": total_tag.get_text(strip=True) if total_tag else "N/A",
        "freight_amount":   get_detail("freight_amount"),
        "inspection_amount": get_detail("inspection_amount"),
        "insurance_amount": get_detail("insurance_amount"),
        "vanning_amount":   get_detail("vanning_amount"),
        "vehicle_price_breakdown": get_detail("vehicle_price"),
    }

def parse_car_specs(soup):
    """
    Extracts car specs from the product-detail__status-area block.
    Each item has a label div and a value div — we pair them into a dict.
    """
    specs = {}
    for item in soup.select("div.product-detail__status-item"):
        label = item.select_one("div.product-detail__status-label")
        value = item.select_one("div.product-detail__status-value")
        if label and value:
            key = label.get_text(strip=True).lower().replace(" ", "_")
            if key == "door":
                key = "doors"
            specs[key] = value.get_text(strip=True)
    return specs

def parse_info_lists(soup):
    info = {}
    for block in soup.select("div.product-detail__info-block"):
        for item in block.select("li.product-detail__info-item"):
            label = item.select_one("div.product-detail__info-label")
            value = item.select_one("div.product-detail__info-value")
            if label and value:
                key = label.get_text(strip=True).lower().replace(" ", "_")
                info[key] = value.get_text(strip=True)
    return info

def parse_image_urls(soup):
    """
    Extracts all full-size image URLs from the main gallery slider.
    Skips blank filler slides that have no img tag.
    Deduplicates by targeting only product-detail__main-image divs.
    """
    image_urls = []
    gallery = soup.select_one("div.product-detail__gallery-slider")
    if not gallery:
        return image_urls
    for slide in gallery.select("div.swiper-slide"):
        img = slide.select_one("div.product-detail__main-image img")
        if img and img.get("src"):
            image_urls.append(img["src"])
    return image_urls

def parse_options(soup):
    """
    Extracts only AVAILABLE car options grouped by category.
    Categories with zero available features are omitted entirely.
    """
    options = {}
    for block in soup.select("div.product-detail__option-block"):
        category_tag = block.select_one("div.product-detail__option-category")
        if not category_tag:
            continue
        category = category_tag.get_text(strip=True)
        available = [
            el.get_text(strip=True)
            for el in block.select("div.product-detail__option-item.-available")
        ]
        if available:
            options[category] = available
    return options
def parse_modal_fields(soup):
    fields = {}
    field_map = {
        "make":      "make",
        "model":     "model",
        "name":      "model_name",   
        "year":      "manufacture_year",
        "month":     "manufacture_month",
        "grade":     "grade",
        "make_id":   "make_id",
        "body_type": "body_type",
        "mileage":   "mileage_raw",   
    }
    for field, key in field_map.items():
        inp = soup.select_one(f'form#get_estimate_id input[name="{field}"]')
        if inp:
            fields[key] = inp.get("value", "").strip()
    return fields

def parse_engagement(soup) -> dict:
    """
    Extracts view count, favourite count, and review rating/count.
    """
    view_tag = soup.select_one("div.product-detail__view-counter")
    fav_tag  = soup.select_one("div.product-detail__favorite-counter")
    rating_tag = soup.select_one("span.avg-score")
    review_tag = soup.select_one("span.reviews-qa-label")

    return {
        "view_count": view_tag.get_text(strip=True) if view_tag else "N/A",
        "favourite_count":  fav_tag.get_text(strip=True) if fav_tag else "N/A",
        "rating":           rating_tag.get_text(strip=True) if rating_tag else "N/A",
        "reviews":          review_tag.get_text(strip=True) if review_tag else "N/A",
    }

def parse_individual_car_page(soup, car_url):
    header         = parse_header(soup)
    identification = parse_identification(soup)
    pricing        = parse_pricing(soup)
    specs          = parse_car_specs(soup)
    info           = parse_info_lists(soup)
    image_urls         = parse_image_urls(soup)
    options        = parse_options(soup)
    modal          = parse_modal_fields(soup)
    engagement     = parse_engagement(soup)

    car = {
        "car_url":    car_url,
        "scraped_at": datetime.now().isoformat(),
        **header,
        **identification,
        **pricing,
        **modal,      
        **specs,     
        **info,      
        **engagement,
        "image_urls":  image_urls,
        "options": options,
    }

    log.info(
        f"Parsed {identification.get('stock_id', '?')} | "
        f"{header.get('title', '?')} | "
        f"{len(image_urls)} image_urls | "
        f"{sum(len(v) for v in options.values())} available options"
    )
    return car

if __name__ == "__main__":
    car_url = "https://www.sbtjapan.com/used-cars/AI1937"
    soup = fetch(BASE_URL)
    # print(parse_individual_car_page(soup, car_url))
    print(get_total_pages(soup))
    urls = get_car_detail_urls(BASE_URL)
    print(f"Total: {len(urls)}")
    for url in urls:
        print(url)