```markdown
# Scraper Documentation

This guide covers three **Japanese car marketplace scrapers**:

- **SBTJapan** – scrapes search results and individual car detail pages.
- **Beforward** – scrapes the stocklist and detail pages.
- **CarFromJapan** – two‑stage scraper (listing + detailed specs).

All scrapers share a common base module (`scrappers/base.py`) that provides logging, HTTP fetching with retries, JSON saving, and project root detection.  
**Now with CLI support** – you can control the number of listing pages directly from the command line.

---

## 📦 Installation

### 1. Clone repository
```bash
https://github.com/john-otienoh/Japan_Car_Import_Advisory_Platform
```

### 2. Navigate to the project root
```bash
cd scrappers/
```
### 3. Create a virtual environment (recommended)
```bash
python -m venv venv
source venv/bin/activate      # Linux/Mac
source .\venv\Scripts\activate   # Windows
```

### 4. Install dependencies
```bash
pip install requests beautifulsoup4 lxml
```

> **Note**: `lxml` is used by all scrapers for faster HTML parsing.

### 4. Verify folder structure
Your project should look like this:
```
scrappers/
│
├── base.py                      
├── USAGE.md                     
├── thought.md                   
│
├── aaajapan/
│   ├── __init__.py
│   └── scraper.py               
│
├── beforward/
│   ├── __init__.py
│   └── scraper.py               
│
├── carfromjapan/
│   ├── __init__.py
│   └── scraper.py               
│
├── japanesecartrade/
│   ├── __init__.py
│   └── scraper.py               
│
├── sbtjapan/
│   ├── __init__.py
│   └── scraper.py               
│
└── __pycache__/                 
```

---

## Common Configuration via CLI

You can now **limit the number of listing pages** directly when running any scraper:

```bash
python -m <site>.scraper --max-pages  N
```

- `--max-pages N` – scrape only the first `N` listing pages (good for testing).
- If **omitted**, the scraper will scrape **all available pages** (full run).

> **Note**: For CarFromJapan, the default value of `DEFAULT_MAX_PAGES` in the script is ignored when you use `--max-pages`. If you want a permanent limit, still edit the file.

---

## SBTJapan Scraper

**Scrapes**:  
- Paginated search results (e.g., all Honda Accord listings).  
- Each car's detail page (price, specs, images, options, engagement stats).  
- Saves **one JSON file** containing all scraped cars.

### Run the scraper
```bash
# Scrape all pages
python -m sbtjapan.scraper

# Scrape only first 5 pages
python -m sbtjapan.scraper --max-pages 5
```

### Customisation (optional – edit the file)

You can still edit `scrappers/sbtjapan/scraper.py` to change the search URL or delay:

```python
BASE_SEARCH_URL = "https://www.sbtjapan.com/used-cars/search"
REQUEST_DELAY = 1.5
```

### Output
- **JSON file**: `data/raw/sbtjapan/sbtjapan_all_YYYYMMDD_HHMMSS.json`
- **Log file**: `logs/sbtjapan_YYYYMMDD_HHMMSS.log`

### Sample JSON structure
```json
[
  {
    "car_url": "https://www.sbtjapan.com/used-cars/AJ0311",
    "scraped_at": "2026-05-21T12:00:00",
    "title": "1998 MITSUBISHI ROSA",
    "model_code": "KC-BE654G",
    "stock_id": "AJ0311",
    "vehicle_price": "21,993",
    "total_price": "24,564",
    "image_urls": ["https://.../img1.jpg", ...],
    "car_options": { "Safety": ["ABS", "Airbag"], ... },
    ...
  }
]
```

---

## Beforward Scraper

**Scrapes**:  
- Paginated stocklist (`/stocklist/...`).  
- Each vehicle’s detail page (price, full specs table, features list, image gallery).  
- Saves **one JSON file** with all vehicles.

### Run the scraper
```bash
# All pages
python -m beforward.scraper

# Only first 3 pages
python -m beforward.scraper --max-pages 3
```

### Customisation (optional)

Edit `scrappers/beforward/scraper.py` to change the starting URL or delay:

```python
START_URL = "https://www.beforward.jp/stocklist/sar=steering/steering=Right/tp_country_id=27"
REQUEST_DELAY = 1.5
```

### Output
- **JSON file**: `data/raw/beforward/beforward_all_YYYYMMDD_HHMMSS.json`
- **Log file**: `logs/beforward_YYYYMMDD_HHMMSS.log`

### Sample JSON structure
```json
[
  {
    "car_url": "https://www.beforward.jp/toyota/regiusace-van/cc260209/id/14289814/",
    "title": "2012 TOYOTA REGIUSACE VAN WIDE SUPER GL",
    "ref_no": "CC260209",
    "model_code": "CBF-TRH216K",
    "vehicle_price": "$7,970",
    "total_price": "$11,336",
    "location": "OSAKA",
    "mileage": "145,779 km",
    "features": ["Power Steering", "A/C", "ABS", ...],
    "images": ["https://.../img1.jpg", ...],
    "specifications": { "Dimension": "4.90×1.88×2.10 m", ... },
    ...
  }
]
```

---

## CarFromJapan Scraper

**Two‑stage scraper**:

1. **Listing stage** – collects car cards from paginated `/kenya/cheap-used-cars-for-sale` (or any similar page).  
2. **Detail stage** – visits each URL and extracts full specifications, accessories, all images, and exact prices.  
   Merges listing fields into the final record.

### Run the scraper
```bash
# Use default limit (4 pages if you haven't changed the file)
python -m carfromjapan.scraper

# Override – scrape only 2 pages
python -m carfromjapan.scraper --max-pages 2

# Override – scrape all pages (if you want full run)
python -m carfromjapan.scraper --max-pages 1000   # or a very high number
```

> **Tip**: To make “no argument” mean **all pages**, set `DEFAULT_MAX_PAGES = None` at the top of `carfromjapan/scraper.py`. Otherwise, the built‑in default is `4`.

### Customisation (optional)

Edit `scrappers/carfromjapan/scraper.py` to change the search path or delay:

```python
START_PATH = "/kenya/cheap-used-cars-for-sale"
REQUEST_DELAY = 1.5
DEFAULT_MAX_PAGES = None      # now `--max-pages` is optional and defaults to all
```

### Output

Two files are saved:

1. **Listing intermediate**  
   `data/raw/carfromjapan/carfromjapan_listing_YYYYMMDD_HHMMSS.json`  
2. **Final details**  
   `data/raw/carfromjapan/carfromjapan_details_YYYYMMDD_HHMMSS.json`

### Sample JSON (final)
```json
{
  "https://carfromjapan.com/cheap-used-cars/...": {
    "car_url": "https://...",
    "scraped_at": "2026-05-21T12:00:00+00:00",
    "title": "2015 TOYOTA 4RUNNER SR5",
    "reference_no": "4T4BZ1CJ5FR123456",
    "model_code": "N280",
    "transmission": "Automatic",
    "mileage": "61,000 km",
    "car_price": "$21,560",
    "total_cnf": "$24,564",
    "accessories": {
      "Comfort": ["Air Conditioning", "Power Steering"],
      "Safety": ["ABS", "Airbag"]
    },
    "image_urls": ["https://cdn.carfromjapan.com/.../img1_640_0.jpg", ...],
    "cfj_id": "CFJ12345",
    "photo_count": 45,
    "thumbnail_url": "https://.../thumb.jpg"
  }
}
```

---

## Common Troubleshooting

### `ModuleNotFoundError: No module named 'scrappers'`
- Run from the **project root** using the `-m` flag:  
  `python -m sbtjapan.scraper`
- Or add the project root to `PYTHONPATH`:  
  `export PYTHONPATH=/path/to/Japan_Car_Import_Advisory_Platform`

### HTTP errors (403, 503)
- The `fetch()` function already retries 3 times. Increase `REQUEST_DELAY` or use a VPN/proxy.
- Some sites may require `cloudscraper` – you can replace `requests` in `base.py`.

### No data or empty JSON
- Check the log file – it will show if the scraping was blocked or if HTML selectors changed.
- Run a quick test with `--max-pages 1` and inspect the logs.

### `KeyError` or missing fields
- The HTML structure may have changed. Update CSS selectors in the respective parser functions.

---

## Performance & Ethics

| Scraper | Average time per car | Memory usage |
|---------|---------------------|---------------|
| SBTJapan | ~1.5–2 seconds | ~50 MB |
| Beforward | ~1.5–2 seconds | ~50 MB |
| CarFromJapan | ~2–3 seconds (two requests per car) | ~80 MB |

**Best practices**:
- Always respect `robots.txt`.
- Keep `REQUEST_DELAY` ≥ 1 second.
- Use `--max-pages` to limit test runs.
- For production, consider rotating user‑agents and IPs.

---

## Resuming Interrupted Scrapes

CarFromJapan saves intermediate listing JSON, so you can:

1. Load the listing file manually.
2. Modify `scrape_details()` to accept a pre‑loaded dictionary.
3. Restart from where it stopped.

For the other scrapers, you would need to extend the code (e.g., by checking already scraped URLs).

---

## Testing a Single URL

You can test any detail page parser without running the full pipeline:

```python
from sbtjapan.scraper import scrape_detail
from base import setup_logger

logger = setup_logger("test")
car = scrape_detail("https://www.sbtjapan.com/used-cars/AJ0311", logger)
print(car.keys())
```

Similarly for Beforward and CarFromJapan.

---

## Customising Output Format

All scrapers use `save_to_json()` from `base.py`. If you prefer CSV or SQLite, modify the `run()` function to write to another format. Example for CSV:

```python
import csv
with open(out_file.with_suffix(".csv"), "w") as f:
    writer = csv.DictWriter(f, fieldnames=all_cars[0].keys())
    writer.writeheader()
    writer.writerows(all_cars)
```

---

## Getting Help

- Check the logs in `logs/` – they contain detailed DEBUG output.
- For HTML selector changes, use browser developer tools to inspect the current page structure, then update the CSS selectors in the scraper.
- If you encounter bugs, please open an issue with the log file and the URL that caused the error.

---

**Happy scraping – and remember to always be a good citizen of the web!**
```