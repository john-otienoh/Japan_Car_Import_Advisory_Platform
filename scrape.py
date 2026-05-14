import requests
from bs4 import BeautifulSoup

# 1. Fetch the webpage
# BASE_URL = 

url = "https://www.sbtjapan.com/used-cars"
top_viewed_models, car_brands, car_body_types, inventory_locations = [], [], [], []

response = requests.get(url)
html_content = response.content

# Parse the HTML
soup = BeautifulSoup(html_content, "html.parser")

def extract_home_page():
for p in soup.find_all(class_="card-model__product"):
    top_viewed_models.append(p.text)

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

print(top_viewed_models)
print(car_brands)
print(inventory_locations)
print(car_body_types)