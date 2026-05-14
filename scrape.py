import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import time
import sys

BASE_URL = "https://www.sbtjapan.com/used-cars"

def extract_home_page_data(url):
    """
    Extracts top viewed models, car brands, body types, and inventory locations
    from the SBT Japan homepage.
        
    Returns:
        dict: A dictionary containing lists of extracted data
    """
    top_viewed_models = []
    car_brands = []
    car_body_types = []
    inventory_locations = []
    
    try:
        # Fetch the webpage
        response = requests.get(url)
        response.raise_for_status()  
        
        html_content = response.content
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Extract top viewed models
        for p in soup.find_all(class_="card-model__product"):
            top_viewed_models.append(p.text)
        
        # Extract categories
        for category in soup.select("div.car-choose__category"):
            header = category.select_one("div.car-choose__category-head")
            if not header:
                continue
            
            names = [el.get_text(strip=True).lower() for el in category.select(".car-choose__category-name")]
            label = header.get_text(strip=True).lower()
            
            if "brand" in label:
                car_brands = names
            elif "body" in label:
                car_body_types = names
            elif "location" in label:
                inventory_locations = names
        
        return {
            'top_viewed_models': top_viewed_models,
            'car_brands': car_brands,
            'car_body_types': car_body_types,
            'inventory_locations': inventory_locations
        }
        
    except requests.RequestException as e:
        print(f"Error fetching the webpage: {e}")
        return None

def extract_car_brands_data():
    """
    Extracts car types from various car brands in the SBT Japan makers page.
    
    Args:
        base_url (str): The base URL of the SBT Japan website (default: BASE_URL)
        
    Returns:
        dict: A dictionary with brand names as keys and lists of car models as values
    """
    cars_by_maker_dict = {}
    data = extract_home_page_data(url=BASE_URL)
    car_brands = data.get("car_brands")

    for brand in car_brands:
        brand_url = f"{BASE_URL}/maker/{brand}"
        try:
            response = requests.get(url=brand_url)
            response.raise_for_status()

            html_content = response.content
            soup = BeautifulSoup(html_content, "html.parser")

            cars_for_brand = []
            for p in soup.find_all(class_="card-model__product"):
                cars_for_brand.append(p.text.strip())

            cars_by_maker_dict[brand] = cars_for_brand

        except requests.RequestException as e:
            print(f"Error fetching data for {brand}: {e}")
            cars_by_maker_dict[brand] = []  
            continue
    return cars_by_maker_dict

def scrape_all_pages(base_search_url):
    """
    Scrape all pages from SBT Japan search results with proper pagination handling.
    
    Args:
        base_search_url: The search URL without page parameter
    
    Returns:
        List of all product URLs
    """
    all_products = []
    page = 1
    
    # Remove existing page parameter if present
    if 'page=' in base_search_url:
        parsed = urlparse(base_search_url)
        params = parse_qs(parsed.query)
        params.pop('page', None)
        base_search_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(params, doseq=True)}"
    
    while True:
        # Construct URL with page parameter
        if '?' in base_search_url:
            url = f"{base_search_url}&page={page}"
        else:
            url = f"{base_search_url}?page={page}"
        
        print(f"Scraping page {page}...", file=sys.stderr)
        
        try:
            response = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all product links
            products = soup.find_all('a', class_='card-product__wrap')
            
            if not products:
                print(f"No products found on page {page}. Stopping.", file=sys.stderr)
                break
            
            # Extract product URLs
            for product in products:
                link = product.get('href')
                if link:
                    full_url = urljoin("https://www.sbtjapan.com", link)
                    all_products.append(full_url)
                    # print(full_url)  # This goes to stdout for file redirection
            
            print(f"Found {len(products)} products on page {page} (Total: {len(all_products)})", file=sys.stderr)
            
            # Check for next page using the actual pagination structure
            next_page_exists = False
            
            # Look for the next button that is NOT disabled
            next_button = soup.find('a', class_='pagination__link -next')
            if next_button and '-is-disabled' not in next_button.get('class', []):
                next_page_exists = True
            else:
                # Alternative: Check if there's a current page and see if there's a next number
                current_page = soup.find('a', class_='pagination__link -is-current')
                if current_page:
                    current_page_num = int(current_page.text.strip())
                    # Check if there's a link to page + 1
                    next_page_link = soup.find('a', class_='pagination__link', string=str(current_page_num + 1))
                    if next_page_link:
                        next_page_exists = True
            
            if not next_page_exists:
                print(f"Reached last page ({page}). Scraping complete!", file=sys.stderr)
                break
            
            page += 1
            time.sleep(0.5)  # Be respectful to the server
            
        except requests.RequestException as e:
            print(f"Error on page {page}: {e}", file=sys.stderr)
            break
        except Exception as e:
            print(f"Unexpected error on page {page}: {e}", file=sys.stderr)
            break
    
    return all_products

if __name__ == "__main__":
    
    # data = extract_home_page_data(url=BASE_URL)
    # if data:
    #     print("Top Viewed Models:", data['top_viewed_models'])
    #     print("Car Brands:", data['car_brands'])
    #     print("Car Body Types:", data['car_body_types'])
    #     print("Inventory Locations:", data['inventory_locations'])
    
    # cars_data = extract_car_brands_data()
    # if cars_data:
    #     for brand, models in cars_data.items():
    #         print(f"Brand: {brand} - Models: {models}")

    search_url = "https://www.sbtjapan.com/used-cars/search?make_id=4&model%5B0%5D=ACCORD&isModel=1&page"
    products = scrape_all_pages(search_url)
    print(f"\nTotal products scraped: {len(products)}")
    for p in products:
        print(p)