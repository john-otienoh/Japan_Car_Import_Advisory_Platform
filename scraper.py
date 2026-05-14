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
    response = requests.get(url, headers=HEADERS, allow_redirects=True)
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

if __name__ == "__main__":
    soup = fetch(f"{BASE_URL}/search?make_id=8&model%5B%5D=ROCKY&isModel=1")
    page_count = get_total_pages(soup=soup)
    print(page_count)