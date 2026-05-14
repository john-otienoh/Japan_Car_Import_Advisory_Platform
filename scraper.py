import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode,quote

BASE_URL = "https://www.sbtjapan.com/used-cars"
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

def get_total_pages(soup):
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
    page_numbers = []
    for link in soup.select("a.pagination__link"):
        text = link.get_text(strip=True)
        if text.isdigit():
            page_numbers.append(int(text))
    return max(page_numbers) if page_numbers else 1

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
        

if __name__ == "__main__":
    soup = fetch(BASE_URL)
    page_count = get_total_pages(soup=soup)
    homepage_data = get_homepage_details()
    print(page_count)
    print(homepage_data)

    make_urls = get_make_urls(homepage_data)
    print(f"\nTotal make URLs: {len(make_urls)}")
    for url in make_urls:
        print(url)
