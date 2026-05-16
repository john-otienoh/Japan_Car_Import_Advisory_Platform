import re
from urllib.parse import urljoin

BASE_URL  = "https://carfromjapan.com"
def get_total_pages(soup):
    """
    Targets the exact pagination container:
    <div data-testid="dynamic-pagination">
    Then reads every <a> inside it that has href containing page=N,
    returning the highest number found.
    Page 1 has href="?", not "?page=1", so we default min to 1.
    """
    pagination = soup.select_one("div[data-testid='dynamic-pagination']")
    if not pagination:
        return 1

    pages = [1] 
    for a in pagination.select("a[href]"):
        href = a.get("href", "")
        match = re.search(r"page=(\d+)", href)
        if match:
            pages.append(int(match.group(1)))

    return max(pages)

def parse_card(card):
    anchor = card.select_one("h3 a")
    rel_href = anchor.get("href", "") if anchor else ""
    car_url  = urljoin(BASE_URL, rel_href)

    # ── Title ──────────────────────────────────────────────────────────────
    title = anchor.get_text(strip=True) if anchor else "N/A"

    # ── Stock / CFJ ID ─────────────────────────────────────────────────────
    # Embedded in the compare checkbox label e.g. "Compare (CFJ1568485)"
    cfj_id = "N/A"
    compare_el = card.select_one("[id^='compare-']")
    if compare_el:
        match = re.search(r"CFJ\w+", compare_el.get_text())
        if match:
            cfj_id = match.group(0)

    # ── Main image URL ─────────────────────────────────────────────────────
    img_tag   = card.select_one("img[alt]")
    photo_url = img_tag.get("src", "") if img_tag else ""

    # ── Image count ────────────────────────────────────────────────────────
    # "View all" label shows e.g. "(42) View all"
    image_count = None
    view_all_div = card.select_one("div.z-3")
    if view_all_div:
        match = re.search(r"\((\d+)\)", view_all_div.get_text())
        if match:
            image_count = int(match.group(1))

    # ── Spec rows ─────────────────────────────────────────────────────────
    # Each spec block is a div.flex-1 containing a gray label + gray-900 value
    specs = {}
    for block in card.select("div.flex-1"):
        label_el = block.select_one("div.text-xs.text-gray-500")
        value_el = block.select_one("div.text-gray-900")
        if not label_el or not value_el:
            continue
        # "Registration year" → "registration_year"
        label = re.sub(r"\s+", "_", label_el.get_text(strip=True).lower())
        value = value_el.get_text(separator=" ", strip=True)
        if label and value and label not in specs:
            specs[label] = value

    # ── Prices ────────────────────────────────────────────────────────────
    # There are two span.car-price elements:
    # first = car price, last = total C&F
    price_spans = card.select("span.car-price")
    car_price = price_spans[0].get_text(strip=True) if len(price_spans) > 0 else "N/A"
    total_cnf = price_spans[-1].get_text(strip=True) if len(price_spans) > 1 else "N/A"

    # ── Delivery port ─────────────────────────────────────────────────────
    # "Mombasa (Port)" lives in span.max-w-35
    port_el = card.select_one("span.max-w-35")
    port    = port_el.get_text(strip=True) if port_el else "N/A"

    return {
        "cfj_id":          cfj_id,
        "title":           title,
        "car_url":         car_url,
        "photo_url":       photo_url,
        "image_count":     image_count,
        "car_price":       car_price,
        "total_cnf":       total_cnf,
        "delivery_port":   port,
        **specs,   # registration_year, mileage, model_code, engine, grade, transmission
    }
