#!/usr/bin/env python3
"""
schema.py — Canonical Vehicle data model.
"""

from dataclasses import dataclass, field, asdict
from typing import List
from typing import Union
import re

# All keys a valid vehicle record must contain
REQUIRED_KEYS: set = {
    "source", "car_url", "stock_id", "chassis_no",
    "title", "manufacturing_year", "make", "model_name", "model", "body_type",
    "model_code", "grade", "mileage", "engine", "transmission", "drive",
    "steering", "fuel", "doors", "seats", "exterior_color", "dimension",
    "currency", "vehicle_price", "total_price", "freight_amount",
    "inspection_amount", "insurance_amount", "destination_port", "location",
    "features", "image_urls",
}


@dataclass
class Vehicle:
    #  Identity 
    source: str = ""            # sbtjapan | carsfromjapan | beforward
    car_url: str = ""
    stock_id: str = ""          # ref_no / reference_no / stock_id
    chassis_no: str = ""        # VIN / chassis number

    #  Title & derived fields 
    title: str = ""
    manufacturing_year: str = ""
    make: str = ""
    model_name: str = ""        # e.g. Hiace, Harrier, RAV4
    model: str = ""             # grade / trim / variant, e.g. DX, Premium
    body_type: str = ""

    #  Vehicle details 
    model_code: str = ""        # technical model code, e.g. 5BA-A200A
    grade: str = ""             # raw grade string from scraper
    mileage: str = ""
    engine: str = ""
    transmission: str = ""
    drive: str = ""
    steering: str = ""
    fuel: str = ""
    doors: str = ""
    seats: str = ""
    exterior_color: str = ""
    dimension: str = ""

    #  Pricing & logistics 
    currency: str = ""
    vehicle_price: str = ""
    total_price: str = ""
    freight_amount: str = ""
    inspection_amount: str = ""
    insurance_amount: str = ""
    destination_port: str = ""
    location: str = ""

    #  Collections ─
    features: List[str] = field(default_factory=list) 
    image_urls: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

# Values treated as empty/missing
EMPTY_PLACEHOLDERS = {"", "—", "-", "N/A", "n/a", "None", "null", "—kg", "-"}


def is_empty(value: Union[str, None]) -> bool:
    """Return True if value is None or a known empty placeholder."""
    return value is None or str(value).strip() in EMPTY_PLACEHOLDERS


def clean_value(value: str) -> str:
    """Replace dash/N/A placeholders with empty string."""
    return "" if is_empty(value) else str(value).strip()


def flatten_options(options: dict) -> list:
    """Flatten a nested {category: [item, ...]} dict into a flat feature list."""
    features = []
    for items in (options or {}).values():
        if isinstance(items, list):
            features.extend(item.strip() for item in items if item.strip())
    return features


def normalize_transmission(value: str) -> str:
    """Normalize to AT or MT."""
    v = str(value).upper().strip().replace("/", "").replace(" ", "")
    if v in ("AT", "AUTOMATIC", "AUTO", "A", "AT"):
        return "AT"
    if v in ("MT", "MANUAL", "M", "MT"):
        return "MT"
    return value


def normalize_drive(value: str) -> str:
    """Normalize to 2WD or 4WD."""
    v = str(value).upper().replace(" ", "")
    if any(x in v for x in ("4WD", "4X4", "AWD", "ALLWHEEL")):
        return "4WD"
    if any(x in v for x in ("2WD", "4X2", "FWD", "RWD")):
        return "2WD"
    return value


def normalize_steering(value: str) -> str:
    """Normalize to RHD or LHD."""
    v = str(value).upper()
    if "RIGHT" in v or "RHD" in v:
        return "RHD"
    if "LEFT" in v or "LHD" in v:
        return "LHD"
    return value


def normalize_fuel(value: str) -> str:
    """Normalize fuel type to a consistent label."""
    v = str(value).upper()
    if any(x in v for x in ("PETROL", "GASOLINE", "GAS")):
        return "Petrol"
    if "DIESEL" in v:
        return "Diesel"
    if "HYBRID" in v:
        return "Hybrid"
    if any(x in v for x in ("ELECTRIC", "EV", "BEV")):
        return "Electric"
    return value.title()

#  Make reference list
MAKES: list = [
    "Land Rover", "Nissan Diesel", "John Deere", "Tata Motors", "Audi",
    "Bentley", "BMW", "Caterpillar", "Chevrolet", "Citroen", "Daihatsu",
    "Ferrari", "Ford", "Hino", "Honda", "Hummer", "Isuzu", "Jaguar", "JCB", 
    "Jeep", "Kawasaki", "KIA", "Komatsu", "Lamborghini", "Lexus", "Mercedes", 
    "Mini", "Mitsubishi", "Mazda", "Nissan", "Peugeot", "Porsche", "Renault",
    "Scania", "Subaru", "Suzuki", "Tesla", "Toyota", "Volkswagen", "Volvo",
]

#  Body type reference list 
BODY_TYPES: list = [
    "Station Wagon", "Mini Van", "Pick Up", "Smart Cab",
    "Heavy Equipment", "Sports Cars", "Sedan Cars", "Pickup Trucks",
    "Dump Truck", "Flatbody Truck", "Box Body Truck", "Freezer Truck",
    "Crane Truck", "Wingbody Truck", "Tanker Truck", "Trailer Head",
    "Double Cabin", "Garbage Truck", "Vaccum Truck", "Concrete Pump",
    "Self Loader", "Car Carrier", "Fire Fighting", "Mixer Truck",
    "Cargo Truck", "Drilling Truck", "All Machinery", "Wheel Loader",
    "Heavy Cranes", "Aerial Platform", "Motor Grader", "Air Compressor",
    "Stone Crusher", "Asphalt Finisher", "Farm Machinery", "Other Machinery",
    "Camper Van", "Mini Truck", "Large Bus", "Mini Bus",
    "Sedan", "Coupe", "Hatchback", "Wagon", "SUV", "Convertible",
    "Bus", "Truck", "Van", "Excavator", "Bulldozer", "Roller", "Crawler",
    "Generator", "Forklifts", "Tractors", "Bicycle", "Bikes", "Boats",
    "Parts", "Jeep", "MUV",
]

_YEAR_RE = re.compile(r"\b(19[7-9]\d|20[0-3]\d)(?:/\d{1,2})?\b")
_MODEL_CODE_RE = re.compile(r"\b[A-Z0-9]{2,5}-[A-Z0-9]{3,10}\b")

def parse_title(title: str) -> dict:
    """
    Parse a raw listing title into structured vehicle fields.

    Parameters
    ----------
    title : str
        Raw title string, e.g. "2020 TOYOTA HIACE VAN DX"

    Returns
    -------
    dict
        Keys: manufacturing_year, make, model_name, model, body_type
        Values are str or "" (never None).

    Notes
    -----
    Parsing order:
        1. Extract year  (handle YYYY/MM format → keep YYYY)
        2. Strip embedded model codes (e.g. 6AA-AXAH54, 5BA-A200A)
        3. Extract make  (longest match wins; only first occurrence removed)
        4. Extract body type  (longest match wins)
        5. Remaining tokens → model_name (first) + model (rest)
    """
    result = {
        "manufacturing_year": "",
        "make": "",
        "model_name": "",
        "model": "",
        "body_type": "",
    }

    if not isinstance(title, str) or not title.strip():
        return result

    working = title.strip().upper()

    # 1. Extract manufacturing year
    m = _YEAR_RE.search(working)
    if m:
        result["manufacturing_year"] = m.group().split("/")[0]
        working = (working[: m.start()] + working[m.end() :]).strip()

    # 2. Remove embedded model codes 
    working = _MODEL_CODE_RE.sub("", working).strip()

    # 3. Extract make 
    for make in MAKES:
        pattern = r"\b" + re.escape(make.upper()) + r"\b"
        if re.search(pattern, working):
            result["make"] = make.title()
            working = re.sub(pattern, "", working, count=1).strip()
            break

    # 4. Extract body type 
    for bt in BODY_TYPES:
        pattern = r"\b" + re.escape(bt.upper()) + r"\b"
        if re.search(pattern, working):
            result["body_type"] = bt.title()
            working = re.sub(pattern, "", working, count=1).strip()
            break

    # 5. Remaining tokens → model_name + model
    tokens = working.split()
    if tokens:
        result["model_name"] = tokens[0].title()
    if len(tokens) > 1:
        result["model"] = " ".join(tokens[1:]).title()

    return result

def enrich_vehicle(vehicle) -> object:
    """Apply title-parsed fields to a Vehicle object."""

    parsed = parse_title(vehicle.title)

    for field_name, parsed_value in parsed.items():
        current = getattr(vehicle, field_name, "")
        if is_empty(current) and parsed_value:
            setattr(vehicle, field_name, parsed_value)

    return vehicle

