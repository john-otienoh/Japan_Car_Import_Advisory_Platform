#!/usr/bin/env python3
"""
base.py — Shared utilities for all website scrapers.

Provides:
    - my_logger: create a file + console logger with timestamps.
    - fetch: GET a URL and return a BeautifulSoup object.
    - clean: normalise whitespace in extracted text.
    - save_json: write Python dict/list to a JSON file.
    - get_project_root: locate the project root directory dynamically.
    - HEADERS: standard browser headers.
"""

import json
import logging
import re
import requests
import warnings
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def my_logger(name, log_dir="logs"):
    """
    Create a logger with both console and file output."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"{name}_{timestamp}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        logger.handlers.clear()
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(console)
    logger.addHandler(file_handler)
    logger.info(f"Logger ready → {log_file}")
    return logger

def fetch(url, logger, retries = 3):
    """GET a URL and return BeautifulSoup. Returns None if all retries fail."""

    session = requests.Session()
    session.headers.update(HEADERS)

    for attempt in range(1, retries+1):
        try:
            response = session.get(url)
            response.raise_for_status()
            logger.debug(f"Fetched {url} [HTTP {response.status_code}]")
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
                soup = BeautifulSoup(response.text, "lxml")

            return soup
        except requests.RequestException as e:
            logger.warning("Attempt %d/%d for %s failed: %s", attempt, retries, url, e)
    logger.error("All %d attempts failed for %s", retries, url)
    return None

def clean(text):
    """Normalise whitespace in extracted text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()

def save_to_json(data, path, logger):
    """Write Python data to a JSON file (UTF-8, pretty-printed)."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    count = len(data) if isinstance(data, (dict, list)) else "?"
    logger.info(f"Saved {count} record(s) to {output_path}")

def slugify(label):
    """Convert a human-readable label into a snake_case dict key."""
    label = clean(label).lower()
    label = re.sub(r"[^\w\s]", "", label)
    label = re.sub(r"\s+", "_", label)
    return label.strip("_")


def get_project_root(marker: str = ".git") -> Path:
    """Walk upwards until a marker file/dir is found."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / marker).exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parents[1]