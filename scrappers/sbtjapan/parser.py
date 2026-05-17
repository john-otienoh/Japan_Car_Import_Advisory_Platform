# import requests
# import json
# import logging
# import math
# import time
# from datetime import datetime
# from pathlib import Path
# from urllib.parse import urljoin, quote

# # ─────────────────────────────────────────────────────────────
# # CONSTANTS
# # ─────────────────────────────────────────────────────────────
# BASE_URL    = "https://www.sbtjapan.com/used-cars"
# OUTPUT_DIR  = Path("data/raw")          # JSON files saved here
# LOG_DIR     = Path("logs")              # Log files saved here

# HEADERS = {
#     "User-Agent": (
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#         "AppleWebKit/537.36 (KHTML, like Gecko) "
#         "Chrome/124.0.0.0 Safari/537.36"
#     ),
#     "Accept-Language": "en-US,en;q=0.9",
# }


# # ─────────────────────────────────────────────────────────────
# # LOGGING SETUP
# # Writes to both the terminal AND a timestamped log file.
# # ─────────────────────────────────────────────────────────────

# def setup_logger(brand: str) -> logging.Logger:
#     """
#     Creates a logger that writes simultaneously to:
#       - stdout (console) via StreamHandler
#       - logs/<brand>_<timestamp>.log via FileHandler

#     Each scrape run for a brand gets its own log file so runs
#     never overwrite each other.
#     """
#     LOG_DIR.mkdir(parents=True, exist_ok=True)

#     timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
#     log_file   = LOG_DIR / f"{brand.lower()}_{timestamp}.log"

#     logger = logging.getLogger(brand)
#     logger.setLevel(logging.DEBUG)

#     # Prevent duplicate handlers if function is called more than once
#     if logger.handlers:
#         logger.handlers.clear()

#     fmt = logging.Formatter(
#         fmt="%(asctime)s | %(levelname)-8s | %(message)s",
#         datefmt="%Y-%m-%d %H:%M:%S",
#     )

#     # Console handler — INFO and above
#     console_handler = logging.StreamHandler()
#     console_handler.setLevel(logging.INFO)
#     console_handler.setFormatter(fmt)

#     # File handler — DEBUG and above (more verbose in the file)
#     file_handler = logging.FileHandler(log_file, encoding="utf-8")
#     file_handler.setLevel(logging.DEBUG)
#     file_handler.setFormatter(fmt)

#     logger.addHandler(console_handler)
#     logger.addHandler(file_handler)

#     logger.info(f"Logger initialised — writing to {log_file}")
#     return logger


# # ─────────────────────────────────────────────────────────────
# # JSON OUTPUT
# # ─────────────────────────────────────────────────────────────

# def save_to_json(brand: str, cars: list, logger: logging.Logger) -> Path:
#     """
#     Saves the scraped car list to data/raw/<brand>.json.
#     If the file already exists it is overwritten with fresh data.
#     Returns the path of the saved file.
#     """
#     OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
#     out_path = OUTPUT_DIR / f"{brand.lower()}.json"

#     payload = {
#         "brand":      brand,
#         "scraped_at": datetime.now().isoformat(),
#         "total":      len(cars),
#         "cars":       cars,
#     }

#     with open(out_path, "w", encoding="utf-8") as f:
#         json.dump(payload, f, ensure_ascii=False, indent=2)

#     logger.info(f"Saved {len(cars):,} cars → {out_path}")
#     return out_path


# # ─────────────────────────────────────────────────────────────
# # CORE UTILITIES
# # ─────────────────────────────────────────────────────────────

# def fetch(url: str, logger: logging.Logger):
#     """Fetch a URL and return a BeautifulSoup object."""
#     from bs4 import BeautifulSoup
#     logger.debug(f"GET {url}")
#     response = requests.get(url, headers=HEADERS, timeout=15)
#     response.raise_for_status()
#     return BeautifulSoup(response.text, "html.parser")


# def get_total_pages(soup) -> int:
#     """Return the highest page number found in pagination links."""
#     pages = []
#     for link in soup.select("a.pagination__link"):
#         text = link.get_text(strip=True)
#         if text.isdigit():
#             pages.append(int(text))
#     return max(pages) if pages else 1


# # ─────────────────────────────────────────────────────────────
# # HOMEPAGE
# # ─────────────────────────────────────────────────────────────

# def get_homepage_details(logger: logging.Logger) -> dict:
#     """Scrape brands, body types, and inventory locations from the homepage."""
#     logger.info("Fetching homepage data...")
#     soup = fetch(BASE_URL, logger)

#     top_viewed_models, car_brands, car_body_types, inventory_locations = [], [], [], []

#     for p in soup.find_all(class_="card-model__product"):
#         top_viewed_models.append(p.get_text(strip=True))

#     for category in soup.select("div.car-choose__category"):
#         header = category.select_one("div.car-choose__category-head")
#         if not header:
#             continue
#         names = [el.get_text(strip=True) for el in category.select(".car-choose__category-name")]
#         label = header.get_text(strip=True).lower()
#         if "brand" in label:
#             car_brands = names
#         elif "body" in label:
#             car_body_types = names
#         elif "location" in label:
#             inventory_locations = names

#     logger.info(
#         f"Homepage parsed — "
#         f"{len(car_brands)} brands, "
#         f"{len(car_body_types)} body types, "
#         f"{len(inventory_locations)} locations"
#     )
#     return {
#         "top_viewed_models": top_viewed_models,
#         "car_brands":        car_brands,
#         "car_body_types":    car_body_types,
#         "inventory_location": inventory_locations,
#     }


# # ─────────────────────────────────────────────────────────────
# # SEARCH URL DISCOVERY
# # ─────────────────────────────────────────────────────────────

# def get_make_urls(homepage_data: dict) -> list:
#     return [
#         f"{BASE_URL}/maker/{brand.lower()}"
#         for brand in homepage_data.get("car_brands", [])
#     ]


# def build_search_url(make_id, model_name: str) -> str:
#     encoded_model = quote(model_name)
#     return (
#         f"{BASE_URL}/search"
#         f"?make_id={make_id}"
#         f"&model%5B0%5D={encoded_model}"
#         f"&isModel=1"
#     )


# def get_brand_models(brand: str, logger: logging.Logger) -> list:
#     """Return list of {brand, model, url} dicts for every model of a brand."""
#     maker_page_url = f"{BASE_URL}/maker/{brand.lower()}"
#     results = []
#     try:
#         soup = fetch(maker_page_url, logger)
#     except requests.RequestException as e:
#         logger.warning(f"Could not fetch maker page for {brand}: {e}")
#         return results

#     for anchor in soup.select("a.card-model"):
#         brand_tag = anchor.select_one("div.card-model__company")
#         model_tag = anchor.select_one("p.card-model__product")
#         href      = anchor.get("href", "")
#         if brand_tag and model_tag and href:
#             results.append({
#                 "brand": brand_tag.get_text(strip=True),
#                 "model": model_tag.get_text(strip=True),
#                 "url":   urljoin("https://www.sbtjapan.com", href),
#             })

#     logger.debug(f"{brand}: {len(results)} models found")
#     return results


# def get_search_urls(homepage_data: dict, logger: logging.Logger) -> list:
#     """Return one brand-level search URL per brand (e.g. ?make_id=2)."""
#     search_urls = []
#     for link in get_make_urls(homepage_data):
#         try:
#             soup = fetch(link, logger)
#         except requests.RequestException as e:
#             logger.warning(f"Skipping {link}: {e}")
#             continue

#         tag = soup.select_one("a.text-link.-next")
#         if tag:
#             href     = tag.get("href", "")
#             full_url = urljoin("https://www.sbtjapan.com", href)
#             search_urls.append(full_url)
#             logger.debug(f"Search URL: {full_url}")

#         time.sleep(1)

#     logger.info(f"Discovered {len(search_urls)} brand search URLs")
#     return search_urls


# # ─────────────────────────────────────────────────────────────
# # CARD PARSER
# # ─────────────────────────────────────────────────────────────

# def parse_card(card) -> dict:
#     """Extract every available field from a single listing card."""
#     anchor       = card.select_one("a.card-product__wrap")
#     relative_url = anchor.get("href", "") if anchor else ""
#     car_url      = urljoin("https://www.sbtjapan.com", relative_url)

#     img_tag   = card.select_one("div.card-product__image img")
#     photo_url = img_tag.get("src", "") if img_tag else ""

#     title_tag = card.select_one("span.card-product__product")
#     title     = title_tag.get_text(strip=True) if title_tag else "N/A"

#     stock_tag = card.select_one("span.card-product__stock-value")
#     stock_id  = stock_tag.get_text(strip=True) if stock_tag else "N/A"

#     location_tag = card.select_one("span.card-product__location-value")
#     location     = location_tag.get_text(strip=True) if location_tag else "N/A"

#     sale_tag  = card.select_one("ins.card-product__price-sale-value span.card-product__price")
#     reg_tag   = card.select_one("div.card-product__vehicle-price span.card-product__price")
#     price_tag = sale_tag or reg_tag
#     veh_price = price_tag.get_text(strip=True) if price_tag else "N/A"

#     curr_tag  = card.select_one("div.card-product__vehicle-price span.card-product__price-currency")
#     currency  = curr_tag.get_text(strip=True) if curr_tag else "USD"

#     total_tag   = card.select_one("div.card-product__total-price span.card-product__price")
#     total_price = total_tag.get_text(strip=True) if total_tag else "N/A"

#     spec_map = {
#         "-model-code":      "model_code",
#         "-mileage":         "mileage",
#         "-engine-capacity": "engine",
#         "-transmission":    "transmission",
#         "-drive-type":      "drive_type",
#         "-steering-type":   "steering",
#         "-fuel-type":       "fuel_type",
#         "-door":            "doors",
#         "-seats":           "seats",
#         "-body-color":      "color",
#     }
#     specs = {}
#     for span in card.select("span.card-product__status"):
#         classes = span.get("class", [])
#         for modifier, key in spec_map.items():
#             if modifier in classes and key not in specs:
#                 specs[key] = span.get_text(strip=True)

#     modal_fields = {}
#     for field in ["make", "model", "year", "month", "grade", "body_type", "mileage"]:
#         inp = card.select_one(f'input[name="{field}"]')
#         if inp:
#             modal_fields[field] = inp.get("value", "").strip()

#     return {
#         "stock_id":      stock_id,
#         "title":         title,
#         "car_url":       car_url,
#         "photo_url":     photo_url,
#         "currency":      currency,
#         "vehicle_price": veh_price,
#         "total_price":   total_price,
#         "location":      location,
#         **specs,
#         **modal_fields,
#     }


# # ─────────────────────────────────────────────────────────────
# # MAIN SCRAPER
# # ─────────────────────────────────────────────────────────────

# def scrape_brand(brand: str, brand_url: str, logger: logging.Logger) -> list:
#     """
#     Scrapes all pages for a single brand and returns a list of car dicts.
#     Saves results to data/raw/<brand>.json after all pages are done.
#     """
#     cars = []
#     logger.info(f"Starting scrape → {brand_url}")

#     try:
#         soup = fetch(brand_url, logger)
#     except requests.RequestException as e:
#         logger.error(f"Failed to fetch {brand_url}: {e}")
#         return cars

#     total_pages = get_total_pages(soup)
#     logger.info(f"Pages detected: {total_pages}")

#     # Page 1 — already fetched
#     page_cards = soup.select("li.search-result__item")
#     logger.info(f"Page 1/{total_pages} — {len(page_cards)} cards")
#     for card in page_cards:
#         cars.append(parse_card(card))

#     # Pages 2..N
#     for page in range(2, total_pages + 1):
#         paged_url = f"{brand_url}&page={page}"
#         try:
#             soup = fetch(paged_url, logger)
#         except requests.RequestException as e:
#             logger.error(f"Page {page} failed: {e}")
#             break

#         page_cards = soup.select("li.search-result__item")
#         logger.info(f"Page {page}/{total_pages} — {len(page_cards)} cards | running total: {len(cars) + len(page_cards):,}")

#         if not page_cards:
#             logger.warning(f"No cards on page {page} — stopping early")
#             break

#         for card in page_cards:
#             cars.append(parse_card(card))

#         time.sleep(1.5)

#     logger.info(f"Scrape complete — {len(cars):,} cars for {brand}")

#     # Save to JSON immediately after each brand finishes
#     save_to_json(brand, cars, logger)

#     return cars


# def scrape_all(brand_filter: str = None):
#     """
#     Full pipeline:
#       1. Fetch homepage data
#       2. Discover one search URL per brand
#       3. Scrape all pages per brand
#       4. Save each brand to data/raw/<brand>.json

#     Args:
#         brand_filter: optional brand name e.g. "subaru" to scrape only that brand.
#                       Pass None to scrape all brands.
#     """
#     # Use a root logger for pipeline-level messages
#     root_logger = setup_logger(brand_filter or "all_brands")
#     root_logger.info("=" * 60)
#     root_logger.info("SBT Japan scraper started")
#     root_logger.info(f"Filter: {brand_filter or 'ALL BRANDS'}")
#     root_logger.info("=" * 60)

#     homepage_data = get_homepage_details(root_logger)
#     search_urls   = get_search_urls(homepage_data, root_logger)

#     brands          = homepage_data.get("car_brands", [])
#     brand_url_pairs = list(zip(brands, search_urls))

#     if brand_filter:
#         brand_url_pairs = [
#             (b, u) for b, u in brand_url_pairs
#             if b.lower() == brand_filter.lower()
#         ]
#         if not brand_url_pairs:
#             root_logger.error(f"Brand '{brand_filter}' not found. Available: {brands}")
#             return []

#     root_logger.info(f"Brands to scrape: {[b for b, _ in brand_url_pairs]}")

#     all_cars = []
#     for brand, brand_url in brand_url_pairs:
#         # Each brand gets its own logger → its own log file
#         brand_logger = setup_logger(brand)
#         brand_cars   = scrape_brand(brand, brand_url, brand_logger)
#         all_cars.extend(brand_cars)

#     root_logger.info("=" * 60)
#     root_logger.info(f"All done. Grand total: {len(all_cars):,} cars")
#     root_logger.info("=" * 60)
#     return all_cars


# # ─────────────────────────────────────────────────────────────
# # ENTRY POINT
# # ─────────────────────────────────────────────────────────────

# def main():
#     # Single brand test
#     cars = scrape_all(brand_filter="subaru")
#     print(f"\nDone. Total Subaru cars: {len(cars):,}")

#     # Scrape everything (comment out the line above first)
#     # cars = scrape_all()
#     # print(f"\nDone. Grand total: {len(cars):,} cars")


# if __name__ == "__main__":
#     main()




# import requests
# from urllib.parse import urljoin, quote
# import time
# from ..base import fetch, get_total_pages

# BASE_URL = "https://www.sbtjapan.com/used-cars"

# def build_search_url(make_id, model_name):
#     """
#     Build the search URL for a given make ID and model name.

#     The URL follows the SBT Japan search format with the model name properly
#     URL-encoded and the required query parameters.

#     Args:
#         make_id (int or str): The manufacturer ID (e.g., 4 for Honda, 2 for Toyota).
#         model_name (str): The name of the car model (e.g., "ACCORD", "4RUNNER").

#     Returns:
#         str: A fully constructed search URL that can be used to retrieve
#              paginated results for the specified make and model.
#     """
#     encoded_model = quote(model_name)
#     return (
#         f"{BASE_URL}/search"
#         f"?make_id={make_id}"
#         f"&model%5B0%5D={encoded_model}"
#         f"&isModel=1"
#     )

# def get_homepage_details():
#     """
#     Extract key information from the SBT Japan homepage.

#     Parses the main page of SBT Japan to gather:
#         - Most viewed car models (from "card-model__product" elements)
#         - Available car brands
#         - Available car body types
#         - Inventory locations

#     The function relies on the global `BASE_URL` and `fetch()` helper to retrieve
#     and parse the HTML. It navigates through category sections (`div.car-choose__category`)
#     and classifies them based on the header text (case‑insensitive keywords
#     "brand", "body", "location").

#     Returns:
#         dict: A dictionary with the following keys:
#             - "top_viewed_models" (list[str]): Names of top viewed models.
#             - "car_brands" (list[str]): All car brand names found.
#             - "car_body_types" (list[str]): All car body type names found.
#             - "inventory_location" (list[str]): All inventory location names found.
#     """
#     soup = fetch(BASE_URL)

#     top_viewed_models, car_brands, car_body_types, inventory_locations = [], [], [], []

#     for p in soup.find_all(class_="card-model__product"):
#         top_viewed_models.append(p.get_text(strip=True))

#     for category in soup.select("div.car-choose__category"):
#         header = category.select_one("div.car-choose__category-head")
#         if not header:
#             continue

#         names = [el.get_text(strip=True) for el in category.select(".car-choose__category-name")]
#         label = header.get_text(strip=True).lower()

#         if "brand" in label:
#             car_brands = names
#         elif "body" in label:
#             car_body_types = names
#         elif "location" in label:
#             inventory_locations = names

#     return {
#         "top_viewed_models": top_viewed_models,
#         "car_brands": car_brands,
#         "car_body_types": car_body_types,
#         "inventory_location": inventory_locations,
#     }

# def get_make_urls(homepage_data):
#     make_urls = []
#     car_brands = homepage_data.get("car_brands", [])

#     for brand in car_brands:
#         maker_page_url=f"{BASE_URL}/maker/{brand.lower()}"
#         make_urls.append(maker_page_url)

#     return make_urls

# def get_brand_models(brand):
#     """
#     For a given brand, returns a list of dicts each containing:
#     - brand:  e.g. "TOYOTA"
#     - model:  e.g. "4RUNNER"
#     - url:    e.g. "https://www.sbtjapan.com/used-cars/search?make_id=2&model%5B%5D=4RUNNER&isModel=1"
#     """
#     maker_page_url = f"{BASE_URL}/maker/{brand.lower()}"
#     results = []

#     try:
#         soup = fetch(maker_page_url)
#     except requests.RequestException as e:
#         print(f"Skipping {brand}: {e}")
#         return results

#     for anchor in soup.select("a.card-model"):
#         brand_tag = anchor.select_one("div.card-model__company")
#         model_tag = anchor.select_one("p.card-model__product")
#         href      = anchor.get("href", "")

#         if brand_tag and model_tag and href:
#             results.append({
#                 "brand": brand_tag.get_text(strip=True),
#                 "model": model_tag.get_text(strip=True),
#                 "url":   urljoin("https://www.sbtjapan.com", href),
#             })

#     return results

# def get_search_urls(homepage_data):
#     search_urls = []
#     maker_page_urls = get_make_urls(homepage_data=homepage_data)
#     for link in maker_page_urls:
#         brand = link.split('/')[-1]
#         try:
#             soup = fetch(link)
#         except requests.RequestException as e:
#             print(f"Skipping {link}: {e}")
#             continue

#         all_model_links = soup.select_one("a.text-link.-next")
#         if all_model_links:
#             href = all_model_links.get("href", "")
#             full_url = urljoin("https://www.sbtjapan.com", href)
#             search_urls.append(full_url)
#         time.sleep(1)

#     return search_urls

# def parse_card(card):
#     anchor = card.select_one("a.card-product__wrap")
#     relative_url = anchor.get("href", "") if anchor else ""
#     car_url = urljoin(BASE_URL, relative_url)
#     img_tag   = card.select_one("div.card-product__image img")
#     photo_url = img_tag.get("src", "") if img_tag else ""

#     # ── Title ─────────────────────────────────────────────────────────────
#     title_tag = card.select_one("span.card-product__product")
#     title     = title_tag.get_text(strip=True) if title_tag else "N/A"

#     # ── Stock ID ──────────────────────────────────────────────────────────
#     stock_tag = card.select_one("span.card-product__stock-value")
#     stock_id  = stock_tag.get_text(strip=True) if stock_tag else "N/A"

#     # ── Location ──────────────────────────────────────────────────────────
#     location_tag = card.select_one("span.card-product__location-value")
#     location     = location_tag.get_text(strip=True) if location_tag else "N/A"

#     # ── Vehicle price (sale price takes priority over regular price) ───────
#     sale_tag   = card.select_one("ins.card-product__price-sale-value span.card-product__price")
#     reg_tag    = card.select_one("div.card-product__vehicle-price span.card-product__price")
#     price_tag  = sale_tag or reg_tag
#     veh_price  = price_tag.get_text(strip=True) if price_tag else "N/A"

#     # ── Vehicle price currency ─────────────────────────────────────────────
#     curr_tag  = card.select_one("div.card-product__vehicle-price span.card-product__price-currency")
#     currency  = curr_tag.get_text(strip=True) if curr_tag else "USD"

#     # ── Total price ────────────────────────────────────────────────────────
#     total_tag   = card.select_one("div.card-product__total-price span.card-product__price")
#     total_price = total_tag.get_text(strip=True) if total_tag else "N/A"

#     # ── Specs — map BEM modifier → readable key ────────────────────────────
#     spec_map = {
#         "-model-code":    "model_code",
#         "-mileage":       "mileage",
#         "-engine-capacity": "engine",
#         "-transmission":  "transmission",
#         "-drive-type":    "drive_type",
#         "-steering-type": "steering",
#         "-fuel-type":     "fuel_type",
#         "-door":          "doors",
#         "-seats":         "seats",
#         "-body-color":    "color",
#     }
#     specs = {}
#     for span in card.select("span.card-product__status"):
#         classes = span.get("class", [])
#         for modifier, key in spec_map.items():
#             # Only assign once per key — engine-capacity appears twice
#             # (cc value and engine code e.g. "204PT"); first match wins
#             if modifier in classes and key not in specs:
#                 specs[key] = span.get_text(strip=True)

#     # ── Estimate modal hidden fields (extra structured data) ───────────────
#     # The modal embeds year, month, grade, make, body_type as hidden inputs
#     modal_fields = {}
#     for field in ["make", "model", "year", "month", "grade", "body_type", "mileage"]:
#         inp = card.select_one(f'input[name="{field}"]')
#         if inp:
#             modal_fields[field] = inp.get("value", "").strip()

#     return {
#         "stock_id":       stock_id,
#         "title":          title,
#         "car_url":        car_url,
#         "photo_url":      photo_url,
#         "currency":       currency,
#         "vehicle_price":  veh_price,
#         "total_price":    total_price,
#         "location":       location,
#         **specs,           
#         **modal_fields,
#     }

# def scrape_all(brand_filter=None):
#     """
#     brand_filter: optional string e.g. "jaguar" — scrapes only that brand.
#     If None, scrapes all brands.
#     """
#     all_cars = []
#     homepage_data = get_homepage_details()
#     search_urls = get_search_urls(homepage_data)

#     # Pair each brand name with its search URL so we can filter by name
#     brands = homepage_data.get("car_brands", [])
#     brand_url_pairs = list(zip(brands, search_urls))

#     # Filter to one brand if requested
#     if brand_filter:
#         brand_url_pairs = [
#             (b, u) for b, u in brand_url_pairs
#             if b.lower() == brand_filter.lower()
#         ]

#     print(f"Brands to scrape: {[b for b, _ in brand_url_pairs]}")

#     for brand, brand_url in brand_url_pairs:
#         print(f"\nScraping {brand}: {brand_url}")

#         try:
#             soup = fetch(brand_url)
#         except requests.RequestException as e:
#             print(f"Failed to fetch {brand_url}: {e}")
#             continue

#         total_pages = get_total_pages(soup)
#         print(f"  Pages detected: {total_pages}")

#         for card in soup.select("li.search-result__item"):
#             all_cars.append(parse_card(card))

#         for page in range(2, total_pages + 1):
#             paged_url = f"{brand_url}&page={page}"
#             print(f"  Fetching page {page}/{total_pages}...")
#             try:
#                 soup = fetch(paged_url)
#             except requests.RequestException as e:
#                 print(f"  Error on page {page}: {e}")
#                 break

#             for card in soup.select("li.search-result__item"):
#                 all_cars.append(parse_card(card))

#             time.sleep(1.5)

#         print(f"  Running total: {len(all_cars)} cars")

#     return all_cars

# def main():

#     # # soup = fetch(BASE_URL)
#     # homepage_data = get_homepage_details()
#     # print(homepage_data)

#     # toyota_models = get_brand_models("toyota")
#     # print(toyota_models)
#     # all_models = []
#     # for brand in homepage_data["car_brands"]:
#     #     all_models.extend(get_brand_models(brand))
#     #     time.sleep(1)

#     # print(f"Total models across all brands: {len(all_models)}")

#     # make_urls = get_make_urls(homepage_data)
#     # print(f"\nTotal make URLs: {len(make_urls)}")
#     # for url in make_urls:
#     #     print(url)

#     # search_urls = get_search_urls(homepage_data)
#     # print(f"\nTotal search URLs: {len(search_urls)}")
#     # for url in search_urls:
#     #     print(url)

#     cars = scrape_all(brand_filter="subaru")
#     print(f"\nDone. Total Subaru cars scraped: {len(cars)}")

#     for car in cars:      
#         for k, v in car.items():
#             print(f"  {k}: {v}")
#         print()

# if __name__ == "__main__":
#     main()
import requests
import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

BASE_URL   = "https://www.sbtjapan.com"
OUTPUT_DIR = Path("data/raw/detail")
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
    from bs4 import BeautifulSoup
    logger.debug(f"GET {url}")
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ─────────────────────────────────────────────────────────────
# PARSERS — each extracts one section, returns a dict
# ─────────────────────────────────────────────────────────────

def parse_header(soup) -> dict:
    """
    Extracts title, manufacture date, model code, year and body type
    from the page header block.
    """
    name_tag = soup.select_one("h1.product-detail__name")
    title    = name_tag.get_text(strip=True) if name_tag else "N/A"

    # Detail items: [model_code, year, body_type]
    detail_items = [
        el.get_text(strip=True)
        for el in soup.select("div.product-detail__detail-item")
    ]

    return {
        "title":      title,
        "model_code": detail_items[0] if len(detail_items) > 0 else "N/A",
        "year":       detail_items[1] if len(detail_items) > 1 else "N/A",
        "body_type":  detail_items[2] if len(detail_items) > 2 else "N/A",
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


def parse_pricing(soup) -> dict:
    """
    Extracts vehicle price, total price, and the full pricing
    breakdown (freight, inspection, insurance, vanning) from the
    price calculator modal which is embedded in the HTML.
    """
    # Base vehicle price (shown in the profile sidebar)
    base_price_tag = soup.select_one("span.product-detail__base-price-range")
    base_currency  = soup.select_one("span.product-detail__base-price-currency")

    # Total amount from the calculator modal
    total_tag      = soup.select_one("div#total_amount")

    # Individual breakdown lines inside pricing-details
    def get_detail(el_id: str) -> str:
        el = soup.select_one(f"div#{el_id}")
        return el.get_text(strip=True) if el else "N/A"

    return {
        "currency":         base_currency.get_text(strip=True) if base_currency else "USD",
        "vehicle_price":    base_price_tag.get_text(strip=True) if base_price_tag else "N/A",
        "total_price":      total_tag.get_text(strip=True) if total_tag else "N/A",
        "freight_amount":   get_detail("freight_amount"),
        "inspection_amount": get_detail("inspection_amount"),
        "insurance_amount": get_detail("insurance_amount"),
        "vanning_amount":   get_detail("vanning_amount"),
        "vehicle_price_breakdown": get_detail("vehicle_price"),
    }


def parse_specs(soup) -> dict:
    """
    Extracts the spec grid: mileage, engine, transmission, drive,
    steering, fuel, doors, seats.
    """
    specs = {}
    for item in soup.select("div.product-detail__status-item"):
        label = item.select_one("div.product-detail__status-label")
        value = item.select_one("div.product-detail__status-value")
        if label and value:
            key = label.get_text(strip=True).lower().replace(" ", "_")
            specs[key] = value.get_text(strip=True)
    return specs


def parse_info_lists(soup) -> dict:
    """
    Extracts all product-detail__info-block sections:
    - Vehicle Details (make, model, color, body type, doors, seats)
    - Specifications (dimension, M3, weights)
    Each label→value pair is merged into one flat dict.
    """
    info = {}
    for block in soup.select("div.product-detail__info-block"):
        for item in block.select("li.product-detail__info-item"):
            label = item.select_one("div.product-detail__info-label")
            value = item.select_one("div.product-detail__info-value")
            if label and value:
                key = label.get_text(strip=True).lower().replace(" ", "_")
                info[key] = value.get_text(strip=True)
    return info


def parse_images(soup) -> list:
    """
    Extracts all full-size image URLs from the main gallery slider.
    Skips blank filler slides that have no img tag.
    Deduplicates by targeting only product-detail__main-image divs.
    """
    images = []
    gallery = soup.select_one("div.product-detail__gallery-slider")
    if not gallery:
        return images

    for slide in gallery.select("div.swiper-slide"):
        img = slide.select_one("div.product-detail__main-image img")
        if img and img.get("src"):
            images.append(img["src"])

    return images


def parse_options(soup) -> dict:
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


def parse_modal_fields(soup) -> dict:
    """
    Extracts structured hidden inputs from the estimate modal.
    These give clean values for make, model, grade, body_type, mileage etc.
    without needing to parse the title string.
    """
    fields = {}
    for field in ["make", "model", "name", "year", "month", "grade", "make_id", "body_type", "mileage"]:
        inp = soup.select_one(f'form#get_estimate_id input[name="{field}"]')
        if inp:
            fields[field] = inp.get("value", "").strip()
    return fields


def parse_engagement(soup) -> dict:
    """
    Extracts view count, favourite count, and review rating/count
    from the review block.
    """
    view_tag = soup.select_one("div.product-detail__view-counter")
    fav_tag = soup.select_one("div.product-detail__favorite-counter")
    rating_tag = soup.select_one("span.avg-score")
    review_tag = soup.select_one("span.reviews-qa-label")

    return {
        "view_count":     view_tag.get_text(strip=True) if view_tag else "N/A",
        "favourite_count": fav_tag.get_text(strip=True) if fav_tag else "N/A",
        "rating":         rating_tag.get_text(strip=True) if rating_tag else "N/A",
        "reviews":        review_tag.get_text(strip=True) if review_tag else "N/A",
    }


# ─────────────────────────────────────────────────────────────
# MASTER PARSER — composes all section parsers
# ─────────────────────────────────────────────────────────────

def parse_detail_page(soup, car_url: str, logger: logging.Logger) -> dict:
    """
    Runs every section parser and merges results into one flat dict.
    """
    logger.debug("Parsing header...")
    header = parse_header(soup)

    logger.debug("Parsing identification...")
    identification = parse_identification(soup)

    logger.debug("Parsing pricing...")
    pricing = parse_pricing(soup)

    logger.debug("Parsing specs...")
    specs = parse_specs(soup)

    logger.debug("Parsing info lists (vehicle details + specifications)...")
    info = parse_info_lists(soup)

    logger.debug("Parsing images...")
    images = parse_images(soup)

    logger.debug("Parsing available options...")
    options = parse_options(soup)

    logger.debug("Parsing modal fields...")
    modal = parse_modal_fields(soup)

    logger.debug("Parsing engagement stats...")
    engagement = parse_engagement(soup)

    car = {
        "car_url":    car_url,
        "scraped_at": datetime.now().isoformat(),
        **header,
        **identification,
        **pricing,
        **specs,
        **info,           # make, model, body_color, dimension, weight etc.
        **modal,          # grade, make_id — cleaner structured values
        **engagement,
        "images":  images,
        "options": options,
    }

    logger.info(
        f"Parsed {identification.get('stock_id', '?')} | "
        f"{header.get('title', '?')} | "
        f"{len(images)} images | "
        f"{sum(len(v) for v in options.values())} available options"
    )
    return car


# ─────────────────────────────────────────────────────────────
# JSON OUTPUT
# ─────────────────────────────────────────────────────────────

def save_to_json(stock_id: str, data: dict, logger: logging.Logger) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{stock_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved → {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

def scrape_detail(car_url: str, logger: logging.Logger) -> dict:
    """
    Fetches a single car detail page, parses all sections,
    saves to JSON, and returns the data dict.
    """
    try:
        soup = fetch(car_url, logger)
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {car_url}: {e}")
        return {}

    data     = parse_detail_page(soup, car_url, logger)
    stock_id = data.get("stock_id", "unknown")
    save_to_json(stock_id, data, logger)
    return data


def main():
    logger = setup_logger("detail_scraper")

    # Single car test
    url  = "https://www.sbtjapan.com/used-cars/AJ0311"
    data = scrape_detail(url, logger)

    print(f"\n{'='*50}")
    for k, v in data.items():
        if k == "images":
            print(f"  images ({len(v)}): {v[:3]}...")
        elif k == "options":
            print(f"  options: {v}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()