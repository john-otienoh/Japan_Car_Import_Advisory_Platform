import requests
from urllib.parse import urljoin, quote
import time
from scrappers.base import fetch, get_total_pages

BASE_URL = "https://www.sbtjapan.com/used-cars"

def build_search_url(make_id, model_name):
    """
    Build the search URL for a given make ID and model name.

    The URL follows the SBT Japan search format with the model name properly
    URL-encoded and the required query parameters.

    Args:
        make_id (int or str): The manufacturer ID (e.g., 4 for Honda, 2 for Toyota).
        model_name (str): The name of the car model (e.g., "ACCORD", "4RUNNER").

    Returns:
        str: A fully constructed search URL that can be used to retrieve
             paginated results for the specified make and model.
    """
    encoded_model = quote(model_name)
    return (
        f"{BASE_URL}/search"
        f"?make_id={make_id}"
        f"&model%5B0%5D={encoded_model}"
        f"&isModel=1"
    )

def get_homepage_details():
    """
    Extract key information from the SBT Japan homepage.

    Parses the main page of SBT Japan to gather:
        - Most viewed car models (from "card-model__product" elements)
        - Available car brands
        - Available car body types
        - Inventory locations

    The function relies on the global `BASE_URL` and `fetch()` helper to retrieve
    and parse the HTML. It navigates through category sections (`div.car-choose__category`)
    and classifies them based on the header text (case‑insensitive keywords
    "brand", "body", "location").

    Returns:
        dict: A dictionary with the following keys:
            - "top_viewed_models" (list[str]): Names of top viewed models.
            - "car_brands" (list[str]): All car brand names found.
            - "car_body_types" (list[str]): All car body type names found.
            - "inventory_location" (list[str]): All inventory location names found.
    """
    soup = fetch(BASE_URL)

    top_viewed_models, car_brands, car_body_types, inventory_locations = [], [], [], []

    for p in soup.find_all(class_="card-model__product"):
        top_viewed_models.append(p.get_text(strip=True))

    for category in soup.select("div.car-choose__category"):
        header = category.select_one("div.car-choose__category-head")
        if not header:
            continue

        names = [el.get_text(strip=True) for el in category.select(".car-choose__category-name")]
        label = header.get_text(strip=True).lower()

        if "brand" in label:
            car_brands = names
        elif "body" in label:
            car_body_types = names
        elif "location" in label:
            inventory_locations = names

    return {
        "top_viewed_models": top_viewed_models,
        "car_brands": car_brands,
        "car_body_types": car_body_types,
        "inventory_location": inventory_locations,
    }

def get_make_urls(homepage_data):
    make_urls = []
    car_brands = homepage_data.get("car_brands", [])

    for brand in car_brands:
        maker_page_url=f"{BASE_URL}/maker/{brand.lower()}"
        make_urls.append(maker_page_url)

    return make_urls

def get_brand_models(brand):
    """
    For a given brand, returns a list of dicts each containing:
    - brand:  e.g. "TOYOTA"
    - model:  e.g. "4RUNNER"
    - url:    e.g. "https://www.sbtjapan.com/used-cars/search?make_id=2&model%5B%5D=4RUNNER&isModel=1"
    """
    maker_page_url = f"{BASE_URL}/maker/{brand.lower()}"
    results = []

    try:
        soup = fetch(maker_page_url)
    except requests.RequestException as e:
        print(f"Skipping {brand}: {e}")
        return results

    for anchor in soup.select("a.card-model"):
        brand_tag = anchor.select_one("div.card-model__company")
        model_tag = anchor.select_one("p.card-model__product")
        href      = anchor.get("href", "")

        if brand_tag and model_tag and href:
            results.append({
                "brand": brand_tag.get_text(strip=True),
                "model": model_tag.get_text(strip=True),
                "url":   urljoin("https://www.sbtjapan.com", href),
            })

    return results

def get_search_urls(homepage_data):
    search_urls = []
    maker_page_urls = get_make_urls(homepage_data=homepage_data)
    for link in maker_page_urls:
        brand = link.split('/')[-1]
        try:
            soup = fetch(link)
        except requests.RequestException as e:
            print(f"Skipping {link}: {e}")
            continue

        all_model_links = soup.select_one("a.text-link.-next")
        if all_model_links:
            href = all_model_links.get("href", "")
            full_url = urljoin("https://www.sbtjapan.com", href)
            search_urls.append(full_url)
        time.sleep(1)

    return search_urls

def parse_card(card):
    anchor = card.select_one("a.card-product__wrap")
    relative_url = anchor.get("href", "") if anchor else ""
    car_url = urljoin(BASE_URL, relative_url)
    img_tag   = card.select_one("div.card-product__image img")
    photo_url = img_tag.get("src", "") if img_tag else ""

    # ── Title ─────────────────────────────────────────────────────────────
    title_tag = card.select_one("span.card-product__product")
    title     = title_tag.get_text(strip=True) if title_tag else "N/A"

    # ── Stock ID ──────────────────────────────────────────────────────────
    stock_tag = card.select_one("span.card-product__stock-value")
    stock_id  = stock_tag.get_text(strip=True) if stock_tag else "N/A"

    # ── Location ──────────────────────────────────────────────────────────
    location_tag = card.select_one("span.card-product__location-value")
    location     = location_tag.get_text(strip=True) if location_tag else "N/A"

    # ── Vehicle price (sale price takes priority over regular price) ───────
    sale_tag   = card.select_one("ins.card-product__price-sale-value span.card-product__price")
    reg_tag    = card.select_one("div.card-product__vehicle-price span.card-product__price")
    price_tag  = sale_tag or reg_tag
    veh_price  = price_tag.get_text(strip=True) if price_tag else "N/A"

    # ── Vehicle price currency ─────────────────────────────────────────────
    curr_tag  = card.select_one("div.card-product__vehicle-price span.card-product__price-currency")
    currency  = curr_tag.get_text(strip=True) if curr_tag else "USD"

    # ── Total price ────────────────────────────────────────────────────────
    total_tag   = card.select_one("div.card-product__total-price span.card-product__price")
    total_price = total_tag.get_text(strip=True) if total_tag else "N/A"

    # ── Specs — map BEM modifier → readable key ────────────────────────────
    spec_map = {
        "-model-code":    "model_code",
        "-mileage":       "mileage",
        "-engine-capacity": "engine",
        "-transmission":  "transmission",
        "-drive-type":    "drive_type",
        "-steering-type": "steering",
        "-fuel-type":     "fuel_type",
        "-door":          "doors",
        "-seats":         "seats",
        "-body-color":    "color",
    }
    specs = {}
    for span in card.select("span.card-product__status"):
        classes = span.get("class", [])
        for modifier, key in spec_map.items():
            # Only assign once per key — engine-capacity appears twice
            # (cc value and engine code e.g. "204PT"); first match wins
            if modifier in classes and key not in specs:
                specs[key] = span.get_text(strip=True)

    # ── Estimate modal hidden fields (extra structured data) ───────────────
    # The modal embeds year, month, grade, make, body_type as hidden inputs
    modal_fields = {}
    for field in ["make", "model", "year", "month", "grade", "body_type", "mileage"]:
        inp = card.select_one(f'input[name="{field}"]')
        if inp:
            modal_fields[field] = inp.get("value", "").strip()

    return {
        "stock_id":       stock_id,
        "title":          title,
        "car_url":        car_url,
        "photo_url":      photo_url,
        "currency":       currency,
        "vehicle_price":  veh_price,
        "total_price":    total_price,
        "location":       location,
        **specs,           
        **modal_fields,
    }

def scrape_all(brand_filter=None):
    """
    brand_filter: optional string e.g. "jaguar" — scrapes only that brand.
    If None, scrapes all brands.
    """
    all_cars = []
    homepage_data = get_homepage_details()
    search_urls = get_search_urls(homepage_data)

    # Pair each brand name with its search URL so we can filter by name
    brands = homepage_data.get("car_brands", [])
    brand_url_pairs = list(zip(brands, search_urls))

    # Filter to one brand if requested
    if brand_filter:
        brand_url_pairs = [
            (b, u) for b, u in brand_url_pairs
            if b.lower() == brand_filter.lower()
        ]

    print(f"Brands to scrape: {[b for b, _ in brand_url_pairs]}")

    for brand, brand_url in brand_url_pairs:
        print(f"\nScraping {brand}: {brand_url}")

        try:
            soup = fetch(brand_url)
        except requests.RequestException as e:
            print(f"Failed to fetch {brand_url}: {e}")
            continue

        total_pages = get_total_pages(soup)
        print(f"  Pages detected: {total_pages}")

        for card in soup.select("li.search-result__item"):
            all_cars.append(parse_card(card))

        for page in range(2, total_pages + 1):
            paged_url = f"{brand_url}&page={page}"
            print(f"  Fetching page {page}/{total_pages}...")
            try:
                soup = fetch(paged_url)
            except requests.RequestException as e:
                print(f"  Error on page {page}: {e}")
                break

            for card in soup.select("li.search-result__item"):
                all_cars.append(parse_card(card))

            time.sleep(1.5)

        print(f"  Running total: {len(all_cars)} cars")

    return all_cars
    
if __name__ == "__main__":
    soup = fetch(BASE_URL)
    homepage_data = get_homepage_details()
    print(homepage_data)

    toyota_models = get_brand_models("toyota")
    print(toyota_models)
    all_models = []
    for brand in homepage_data["car_brands"]:
        all_models.extend(get_brand_models(brand))
        time.sleep(1)

    print(f"Total models across all brands: {len(all_models)}")

    make_urls = get_make_urls(homepage_data)
    print(f"\nTotal make URLs: {len(make_urls)}")
    for url in make_urls:
        print(url)

    search_urls = get_search_urls(homepage_data)
    print(f"\nTotal search URLs: {len(search_urls)}")
    for url in search_urls:
        print(url)

    cars = scrape_all(brand_filter="jaguar")
    print(f"\nDone. Total Jaguar cars scraped: {len(cars)}")

    for car in cars:      
        for k, v in car.items():
            print(f"  {k}: {v}")
        print()