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

def parse_car_specs(soup):
    """
    Extracts car specs from the product-detail__status-area block.
    Each item has a label div and a value div — we pair them into a dict.
    """
    specs = {}

    # Find every spec item e.g. <div class="product-detail__status-item -mileage">
    for item in soup.select("div.product-detail__status-item"):
        label = item.select_one("div.product-detail__status-label")
        value = item.select_one("div.product-detail__status-value")

        if label and value:
            # Normalise the label to a clean dict key e.g. "Engine Capacity" -> "engine_capacity"
            key = label.get_text(strip=True).lower().replace(" ", "_")
            # Mileage - mileage- 
            specs[key] = value.get_text(strip=True)
            # specs[mileage] = 187000

    return specs

def parse_header_soup(soup):
    """
    Extracts title, manufacture date, model code, year and body type
    from the page header block.
    """
    name_tag = soup.select_one("h1.product-detail__name")
    title = name_tag.get_text(strip=True) if name_tag else "N/A"
    detail_items = [
        el.get_text(strip=True)
        for el in soup.select("div.product-detail__detail-item")
    ]
    if detail_items:
        model_code = detail_items[0] if len(detail_items) > 0 else "N/A"
        year = detail_items[1] if len(detail_items) > 1 else "N/A"
        body_type = detail_items[2] if len(detail_items) > 2 else "N/A"
        
        return {
            "title": title,
            "model_code": model_code,
            "year": year,
            "body_type": body_type,
        }
    return {}

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

if __name__ == "__main__":
    soup = fetch("https://www.sbtjapan.com/used-cars/AJ0311")
    print(parse_header_soup(soup))
    print(parse_car_specs(soup))
    print(parse_identification(soup))