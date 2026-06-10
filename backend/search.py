"""
search.py
─────────
Pure Typesense search module. No NLU, no intent parsing.

Design principles:
  - Single source of truth for category hierarchy (CATEGORY_TREE)
  - Every search path has an explicit fallback — no dead ends
  - _is_relevant() uses a scoring model, never defaults to True
  - _extract_distance() handles both int and dict Typesense responses
  - Exact name match uses similarity threshold — no wrong-shop returns
  - Cache keys never include full category_names list
  - Keyword-only retry uses whole-word matching, not substring
  - Product/service relevance sorts keywords by specificity first
  - Job distance correctly parsed and used for sorting
  - Offer search guards against missing location upfront
  - Parent fallback fires once per search, not once per keyword
  - Deduplication uses name + city composite key
  - Offers capped at 3 per shop in DB query
"""

from __future__ import annotations

import logging
import re
import difflib
from typing import Any, Dict, List, Optional, Tuple
import typesense

from typesense_setup import client  # noqa: F401 — keeps existing import contract
from config import config
from cache import cache_result
from resilience import retry_with_backoff
from database import fetch_all
from constants import STOP_WORDS as _NOISE_WORDS 
from constants import NAME_MATCH_THRESHOLD, FUZZY_MATCH_THRESHOLD

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_RADIUS_KM   = 25
MAX_RADIUS_KM       = 500
MAX_OFFERS_PER_SHOP = 3          # cap per shop in get_batch_shop_offers
GEO_SENTINEL        = 2_000_000_000  # Typesense sentinel for "no geo" (metres)

# Generic job words — when ALL keywords are these, search everything (*)
JOB_GENERIC_KEYWORDS: frozenset[str] = frozenset({
    "job", "jobs", "vacancy", "vacancies", "vaccency", "vaccencies",
    "employment", "hiring", "work", "career", "careers", "opening",
    "openings", "opportunity", "opportunities", "fresher", "freshers",
    "vaccecny", "vacency","job", "jobs", "vacancy", "vacancies", "vaccency", "vaccencies",
})

# Common noise words that shouldn't count as specificity signals


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY HIERARCHY — single source of truth
#
# Structure:
#   CATEGORY_TREE = {
#       "Parent Category": ["Subcategory A", "Subcategory B", ...],
#       ...
#   }
#
# Rules:
#   - Keys are parent (main) categories, exactly as stored in Typesense
#   - Values are their child subcategories, exactly as stored in Typesense
#   - All comparisons in code must normalise to lowercase
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_TREE: Dict[str, List[str]] = {
    "Food & Dining": [
        "Restaurent", "Drinks & Beverages",
    ],
    "Services": [
        "Beautician", "Doctors", "Photographer", "Home Services",
        "Plumbing Services", "Ac / Tv Services", "IT $ Services",
        "Real estate", "Used vehicles", "constructors / Engi",
        "Installations", "catering Services",
    ],
    "Transportation Services": [
        "Taxi", "Auto Rickshaw", "Load Vehicles", "Bike Taxi",
        "Tourist Bus", "Vehicle Rental",
    ],
    "Mobiles & Electronics": [
        "Mobiles", "Computers", "Tablets", "Headphones & Speakers",
        "Camera", "Personal Cares", "Smart Watches", "Accessories",
    ],
    "Grocery,Beauty & Health": [
        "Staples", "Vegitables", "Personal & Baby Care",
        "Household Care", "Snacks & Beverages",
    ],
    "Home & Living Furnitures": [
        "Furniture & Decor", "Bed & Bath", "Kitchen & Dining",
    ],
    "Automobiles": [
        "Bike & Car Servicing", "Bike & Car Selling",
    ],
    "Fashions": [
        "Clothing", "Footwear", "Watch & Sunglass",
        "Bags & Accessories", "Travel Accessories",
    ],
    "Electrical Appliances": [
        "Cooling Appliances", "Refrigerator", "Television",
        "Washing Machines", "Kitchen Appliances",
    ],
    "Entertainment": [
        "Movies", "Events", "Theme Parks", "Sports",
    ],
    "Gifts & Jewels": [
        "Jewellery", "Gifts", "Flowers", "Toys",
    ],
    "Sports Products": [
        "Nutrition", "Fitness",
    ],
    "Books & Stationery": [
        "Books", "Stationary",
    ],
    "Travel & Hospitality": [
        "Flight", "Train", "Bus", "Cabs",
        "Holidays", "Luxury Resorts", "Lodges",
    ],
    "Others": [
        "Education", "Pet Care", "Meat & Poultry",
        "Art & Graft", "Legal and Consulting", "Freelance and Gig",
    ],
}

# Derived lookup tables — computed once at import time, never manually maintained

# subcategory (lowercase) → parent category (original case)
_SUBCAT_TO_PARENT: Dict[str, str] = {
    sub.lower(): parent
    for parent, subs in CATEGORY_TREE.items()
    for sub in subs
}

# All parent category names in lowercase (for is_parent checks)
_PARENT_CATEGORIES_LOWER: frozenset[str] = frozenset(
    p.lower() for p in CATEGORY_TREE
)

# Pairs that are clearly unrelated — used as hard-reject in relevance scoring
# Format: (shop_category_lower, filter_category_lower)
_UNRELATED_PAIRS: frozenset[Tuple[str, str]] = frozenset({
    ("transportation services", "food & dining"),
    ("transportation services", "services"),
    ("transportation services", "mobiles & electronics"),
    ("transportation services", "home & living furnitures"),
    ("transportation services", "grocery,beauty & health"),
    ("transportation services", "others"),
    ("food & dining",           "transportation services"),
    ("food & dining",           "mobiles & electronics"),
    ("food & dining",           "home & living furnitures"),
    ("food & dining",           "services"),
    ("food & dining",           "automobiles"),
    ("mobiles & electronics",   "food & dining"),
    ("mobiles & electronics",   "transportation services"),
    ("home & living furnitures","transportation services"),
    ("home & living furnitures","food & dining"),
    ("home & living furnitures","services"),
    ("automobiles",             "food & dining"),
    ("automobiles",             "transportation services"),
    ("electrical appliances",   "food & dining"),
    ("electrical appliances",   "transportation services"),
    ("fashions",                "food & dining"),
    ("fashions",                "transportation services"),
})


def _get_parent(category: str) -> str:
    """
    Return the parent category for a given subcategory string.
    
    Args:
        category (str): Subcategory name (case-insensitive).
    
    Returns:
        str: Parent category name (original case from CATEGORY_TREE) or empty string if not found.
    
    Example:
        >>> _get_parent("Restaurent")
        'Food & Dining'
        >>> _get_parent("Unknown")
        ''
    """
    return _SUBCAT_TO_PARENT.get(category.lower().strip(), "")


def _is_parent_category(category: str) -> bool:
    """
    Return True if the given string is a top-level (parent) category.
    
    Args:
        category (str): Category name to check (case-insensitive).
    
    Returns:
        bool: True if category matches a key in CATEGORY_TREE, False otherwise.
    
    Example:
        >>> _is_parent_category("Food & Dining")
        True
        >>> _is_parent_category("Restaurent")  # This is a subcategory
        False
    """
    return category.lower().strip() in _PARENT_CATEGORIES_LOWER


# ─────────────────────────────────────────────────────────────────────────────
# Typesense client
# ─────────────────────────────────────────────────────────────────────────────

try:
    _ts = typesense.Client({
        "nodes": [{
            "host":     config.TYPESENSE_HOST,
            "port":     config.TYPESENSE_PORT,
            "protocol": config.TYPESENSE_PROTOCOL,
        }],
        "api_key":                    config.TYPESENSE_API_KEY,
        "connection_timeout_seconds": config.TYPESENSE_TIMEOUT,
    })
    logger.info("✅ Typesense: %s:%s", config.TYPESENSE_HOST, config.TYPESENSE_PORT)
except Exception as exc:
    logger.critical("❌ Typesense connection failed: %s", exc)
    raise


# ─────────────────────────────────────────────────────────────────────────────
# Document builders — convert Typesense hit → API response dict
# ─────────────────────────────────────────────────────────────────────────────

def _parse_location(doc: Dict) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract (lat, lng) from a Typesense document.
    
    Args:
        doc (Dict): Typesense document with optional 'location' field.
    
    Returns:
        Tuple[Optional[float], Optional[float]]: (latitude, longitude) or (None, None) on failure.
    
    Example:
        >>> lat, lng = _parse_location({'location': [13.0776, 80.2917]})
        >>> (lat, lng)
        (13.0776, 80.2917)
    """
    try:
        loc = doc.get("location")
        if loc and len(loc) >= 2:
            return float(loc[0]), float(loc[1])
    except (TypeError, ValueError, IndexError):
        pass
    return None, None


def _build_shop(doc: Dict, distance_km: Optional[float] = None) -> Dict[str, Any]:
    """
    Convert a Typesense shop document into API response format.
    
    Args:
        doc (Dict): Typesense shop document with fields: id, name, phone, logo, etc.
        distance_km (Optional[float]): Calculated distance from user location.
    
    Returns:
        Dict[str, Any]: API-ready shop dict with normalized field names and types.
    
    Example:
        >>> doc = {'id': '1', 'name': 'Royal Bakery', 'location': [13.0, 80.0], 'rating': 4.5}
        >>> shop = _build_shop(doc, distance_km=2.3)
        >>> shop['name']
        'Royal Bakery'
    """
    lat, lng = _parse_location(doc)
    return {
        "id":             int(doc.get("id", 0)),
        "name":           doc.get("name", "Unknown"),
        "phone":          doc.get("phone", ""),
        "logo":           doc.get("logo", ""),
        "city":           doc.get("city", ""),
        "arearoadname":   doc.get("address", ""),
        "nearbylandmark": doc.get("landmark", ""),
        "latitude":       lat,
        "longitude":      lng,
        "rating":         float(doc.get("rating", 0.0)),
        "review_count":   int(doc.get("review_count", 0)),
        "category":       doc.get("category", ""),
        "subcategory":    doc.get("subcategory", ""),
        "distance_km":    distance_km,
    }


def _build_job(doc: Dict, distance_km: Optional[float] = None) -> Dict[str, Any]:
    """
    Convert a Typesense job document into API response format.
    
    Args:
        doc (Dict): Typesense job document with fields: id, position, job_type, etc.
        distance_km (Optional[float]): Calculated distance from user location.
    
    Returns:
        Dict[str, Any]: API-ready job dict with normalized field names and types.
    """
    lat, lng = _parse_location(doc)
    return {
    "id":          int(doc.get("id", 0)),
    "shop_id":     doc.get("shop_id", ""),
    "shop_name":   doc.get("shop_name", ""),
    "shop_logo":   doc.get("shop_logo", ""),
    "position":    doc.get("position", ""),
    "job_type":    doc.get("job_type", ""),
    "experience":  doc.get("experience", ""),
    "description": doc.get("description", ""),
    "city":        doc.get("city", ""),
    "phone":       doc.get("phone", ""),
    "job_pic":     doc.get("job_pic", ""),
    "latitude":    lat,
    "longitude":   lng,
    "distance_km": distance_km,
    }


def _build_product(doc: Dict, distance_km: Optional[float] = None) -> Dict[str, Any]:
    """
    Convert a Typesense product document into API response format.
    """
    lat, lng = _parse_location(doc)
    
    
    shop_name = doc.get("shop_name") or doc.get("name", "")
    
    return {
        "id":            doc.get("id", ""),
        "product_name":  doc.get("product_name", ""),
        "shop_id":       doc.get("shop_id", ""),
        "name":          shop_name,  # Now properly gets the value
        "shop_name":     shop_name,  # ✅ Also add explicit shop_name key for API consistency
        "logo":          doc.get("shop_logo", ""),
        "category":      doc.get("category", ""),
        "subcategory":   doc.get("subcategory", ""),
        "city":          doc.get("city", ""),
        "offer_id":      doc.get("offer_id", ""),
        "has_offer":     bool(doc.get("has_offer", False)),
        "offer_heading": doc.get("offer_heading", ""),
        "offer_price":   int(doc.get("offer_price", 0) or 0),
        "offer_image":  doc.get("offer_image",  ""),
        "product_img1": doc.get("product_img1", ""),
        "product_img2": doc.get("product_img2", ""),
        "product_img3": doc.get("product_img3", ""),
        "actual_price":  int(doc.get("actual_price", 0) or 0),
        "end_date":      doc.get("end_date", ""),
        "description":   doc.get("description", ""),
        "category_name": doc.get("category", ""),
        "start_date":    "",
        "phone":         doc.get("shop_phone", ""),
        "latitude":      lat,
        "longitude":     lng,
        "distance_km":   distance_km,
    }


def _build_service(doc: Dict, distance_km: Optional[float] = None) -> Dict[str, Any]:
    """
    Convert a Typesense service document into API response format.
    """
    lat, lng = _parse_location(doc)
    
    shop_name = doc.get("shop_name") or doc.get("name", "")
    
    return {
        "id":              doc.get("id", ""),
        "service_name":    doc.get("service_name", ""),
        "shop_id":         doc.get("shop_id", ""),
        "name":            shop_name,  # Now properly gets the value
        "shop_name":       shop_name,  
        "logo":            doc.get("shop_logo", ""),
        "category":        doc.get("category", ""),
        "subcategory":     doc.get("subcategory", ""),
        "city":            doc.get("city", ""),
        "offer_id":        doc.get("offer_id", ""),
        "has_offer":       bool(doc.get("has_offer", False)),
        "offer_heading":   doc.get("offer_heading", ""),
        "offer_price":     int(doc.get("offer_price", 0) or 0),
        "actual_price":    int(doc.get("actual_price", 0) or 0),
        "offer_image":  doc.get("offer_image",  ""),
        "product_img1": doc.get("product_img1", ""),
        "product_img2": doc.get("product_img2", ""),
        "product_img3": doc.get("product_img3", ""),
        "end_date":        doc.get("end_date", ""),
        "description":     doc.get("description", ""),
        "category_name":   doc.get("category", ""), 
        "start_date":      "",
        "phone":           doc.get("shop_phone", ""),
        "is_category_13":  bool(doc.get("is_category_13", False)),
        "latitude":        lat,
        "longitude":       lng,
        "distance_km":     distance_km,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Distance extraction
#
# Typesense returns geo_distance_meters in two shapes depending on version:
#   A) Integer:  hit["geo_distance_meters"] = 1240  (metres)
#   B) Dict:     hit["geo_distance_meters"] = {"location": 1240}
#
# We handle both. Values above GEO_SENTINEL mean Typesense has no geo data
# for this document — we return None in that case.
# ─────────────────────────────────────────────────────────────────────────────

def _extract_distance(hit: Dict) -> Optional[float]:
    """
    Extract distance_km from a Typesense hit.
    
    Handles both integer and dict response shapes from Typesense:
      - Shape A: hit["geo_distance_meters"] = 1240 (metres, plain int)
      - Shape B: hit["geo_distance_meters"] = {"location": 1240} (dict with location key)
    
    Args:
        hit (Dict): Typesense search result document.
    
    Returns:
        Optional[float]: Distance in kilometers (rounded to 2 decimals), or None if unavailable.
    
    Note:
        Returns None if distance >= 2 billion metres (Typesense sentinel for no geo data).
    
    Example:
        >>> _extract_distance({'geo_distance_meters': 5000})
        5.0
        >>> _extract_distance({'geo_distance_meters': {'location': 2500}})
        2.5
    """
    raw_field = hit.get("geo_distance_meters")
    if raw_field is None:
        return None

    # Shape A: plain integer
    if isinstance(raw_field, (int, float)):
        raw_metres = int(raw_field)
    # Shape B: dict with "location" key
    elif isinstance(raw_field, dict):
        val = raw_field.get("location")
        if val is None:
            return None
        raw_metres = int(val)
    else:
        return None

    # Sentinel guard — Typesense uses ~2B when no geo data
    if raw_metres <= 0 or raw_metres >= GEO_SENTINEL:
        return None

    return round(raw_metres / 1000, 2)


def _escape(value: str) -> str:
    """
    Escape special characters for Typesense filter strings.
    
    Args:
        value (str): Raw string value to escape.
    
    Returns:
        str: Escaped string safe for use in Typesense filter_by expressions.
    
    Example:
        >>> _escape('Royal "Bakery"')
        'Royal \\"Bakery\\"'
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ─────────────────────────────────────────────────────────────────────────────
# Search parameter builders
# ─────────────────────────────────────────────────────────────────────────────

def _shop_base_params(keyword: str, limit: int) -> Dict:
    """
    Build base search parameters for shop searches.
    
    Args:
        keyword (str): Search query (or '*' for all).
        limit (int): Maximum results to return.
    
    Returns:
        Dict: Typesense search params with query_by fields and weighting.
    
    Note:
        Searches across name, categories, keywords, offers, and landmarks.
        Allows up to 2 typos for fuzzy matching.
    """
    return {
        "q":                      keyword or "*",
        "query_by":               "name,subcategory,category,keywords,tags,offer_text,city,landmark",
        "query_by_weights":       "4,3,3,2,2,1,1,1",
        "num_typos":              2,
        "per_page":               limit,
        "prioritize_exact_match": True,
    }


def _job_base_params(keyword: str, limit: int) -> Dict:
    """
    Build base search parameters for job searches.
    
    Args:
        keyword (str): Search query (or '*' for all).
        limit (int): Maximum results to return.
    
    Returns:
        Dict: Typesense search params optimized for job position matching.
    
    Note:
        Prioritizes 'position' field, searches shop_name and description as fallback.
    """
    return {
        "q":                      keyword or "*",
        "query_by":               "position,job_type,shop_name,description,city",
        "query_by_weights":       "4,3,2,2,1",
        "num_typos":              2,
        "per_page":               limit,
        "prioritize_exact_match": True,
    }


def _build_geo_filter(
    lat: float,
    lng: float,
    radius_km: int,
    category: str = "",
) -> str:
    """
    Build a Typesense filter string for geo + optional category.
    
    Args:
        lat (float): User latitude (-90 to 90).
        lng (float): User longitude (-180 to 180).
        radius_km (int): Search radius in kilometres.
        category (str): Optional category/subcategory to filter on.
    
    Returns:
        str: Typesense filter_by expression, e.g., "location:(13.0, 80.0, 25 km)"
    
    Category handling:
        - If category is a parent (main category) → filters on 'category' field
        - If category is a subcategory → filters on 'subcategory' field
        - If category is empty → geo filter only, no category filter
    
    Case-insensitive: normalises category before comparison with CATEGORY_TREE.
    
    Example:
        >>> _build_geo_filter(13.0776, 80.2917, 25, "Restaurent")
        'location:(13.0776, 80.2917, 25 km) && subcategory:Restaurent'
    """
    geo_part = f"location:({lat}, {lng}, {radius_km} km)"

    if not category or not category.strip():
        return geo_part

    escaped = _escape(category)
    if _is_parent_category(category):
        return f'category:=["{escaped}"] && {geo_part}'
    else:
        return f'subcategory:=["{escaped}"] && {geo_part}'


# ─────────────────────────────────────────────────────────────────────────────
# Typesense execution — retry-wrapped + safe wrappers
# ─────────────────────────────────────────────────────────────────────────────

@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(Exception,))
def _ts_search_shops(params: Dict) -> List[Dict]:
    return _ts.collections["shops"].documents.search(params).get("hits", [])


@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(Exception,))
def _ts_search_jobs(params: Dict) -> List[Dict]:
    return _ts.collections["jobs"].documents.search(params).get("hits", [])


@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(Exception,))
def _ts_search_products(params: Dict) -> List[Dict]:
    return _ts.collections["products"].documents.search(params).get("hits", [])


@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(Exception,))
def _ts_search_services(params: Dict) -> List[Dict]:
    return _ts.collections["services"].documents.search(params).get("hits", [])


def _safe_search(collection: str, params: Dict) -> List[Dict]:
    """
    Unified safe search wrapper. Routes to the correct collection.
    Returns empty list on any exception — callers never see Typesense errors.
    """
    _searchers = {
        "shops":    _ts_search_shops,
        "jobs":     _ts_search_jobs,
        "products": _ts_search_products,
        "services": _ts_search_services,
    }
    fn = _searchers.get(collection)
    if fn is None:
        logger.error("_safe_search: unknown collection '%s'", collection)
        return []
    try:
        return fn(params)
    except Exception as exc:
        logger.error("Typesense %s search failed: %s", collection, exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Relevance scoring
#
# Previous design: binary True/False with "return True" as default.
# New design:      integer score — reject if score == 0.
#
# Score accumulates:
#   +3  direct category/subcategory match (strongest signal)
#   +2  parent-child relationship known
#   +1  word overlap between filter category and shop category
#   +1  fuzzy match (SequenceMatcher ≥ 0.75)
#   -99 hard-reject for clearly unrelated pairs (overrides everything)
#
# A shop passes relevance if score > 0.
# When no category is provided, all shops pass (score = 1 by default).
# ─────────────────────────────────────────────────────────────────────────────

def _relevance_score(shop: Dict, category: str) -> int:
    """
    Return an integer relevance score for a shop against a category filter.
    Score ≤ 0 means the shop should be excluded.
    """
    if not category or not category.strip():
        return 1  # no filter → always relevant

    shop_cat  = (shop.get("category")    or "").lower().strip()
    shop_sub  = (shop.get("subcategory") or "").lower().strip()
    cat_lower = category.lower().strip()
    score     = 0

    # Hard reject — clearly unrelated category pairs
    if (shop_cat, cat_lower) in _UNRELATED_PAIRS:
        logger.debug(
            "Hard-rejected '%s' — shop_cat='%s' vs filter='%s'",
            shop.get("name"), shop_cat, cat_lower,
        )
        return -99

    # +3: direct containment (subcategory or category field matches filter)
    if cat_lower == shop_cat or cat_lower == shop_sub:
        score += 3
    elif cat_lower in shop_sub or shop_sub in cat_lower:
        score += 2
    elif cat_lower in shop_cat or shop_cat in cat_lower:
        score += 2

    # +2: known parent-child relationship
    parent_of_filter = _get_parent(cat_lower)        # filter is a subcategory
    if parent_of_filter:
        if parent_of_filter.lower() == shop_cat:
            score += 2
    # Also check if filter IS the parent of the shop's subcategory
    parent_of_shop_sub = _get_parent(shop_sub)
    if parent_of_shop_sub and parent_of_shop_sub.lower() == cat_lower:
        score += 2

    # +1: word-level overlap (skip noise words)
    cat_words  = set(cat_lower.split()) - _NOISE_WORDS
    shop_words = set(f"{shop_cat} {shop_sub}".split()) - _NOISE_WORDS
    if cat_words and shop_words and (cat_words & shop_words):
        score += 1

    # +1: fuzzy match — catches "Restaurent" vs "Restaurant" style typos
    if difflib.SequenceMatcher(None, cat_lower, shop_cat).ratio() >= FUZZY_MATCH_THRESHOLD:
        score += 1
    elif difflib.SequenceMatcher(None, cat_lower, shop_sub).ratio() >= FUZZY_MATCH_THRESHOLD:
        score += 1

    return score


def _is_relevant(shop: Dict, category: str) -> bool:
    """Public wrapper — returns True if shop passes relevance for the given category."""
    return _relevance_score(shop, category) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Keyword helpers
# ─────────────────────────────────────────────────────────────────────────────

def _prioritise_keywords(keywords: List[str]) -> List[str]:
    """
    Sort keywords so the most specific (longest, non-noise) term comes first.
    The primary keyword is used as the relevance anchor for product/service search.

    Example:
        ["near me", "plumber", "pipe repair"] → ["pipe repair", "plumber", "near me"]
    """
    def specificity(kw: str) -> int:
        words = [w for w in kw.lower().split() if w not in _NOISE_WORDS]
        return len(words)  # more meaningful words = higher specificity

    return sorted(keywords, key=specificity, reverse=True)


def _whole_word_match(keyword: str, text: str) -> bool:
    """
    Return True if keyword appears as a whole word in text.
    Prevents "it" matching "electrical", "in" matching "dining", etc.
    """
    if not keyword or not text:
        return False
    pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
    return bool(re.search(pattern, text.lower()))


def _deduplicate_shops(shops: List[Dict]) -> List[Dict]:
    """
    Remove duplicate shops. Deduplication key = (normalised_name, city).
    Two shops with the same name in different cities are kept — they are different shops.
    """
    seen: set = set()
    result: List[Dict] = []
    for shop in shops:
        name_norm = re.sub(r"\s+", " ", (shop.get("name") or "").lower().strip())
        city_norm = (shop.get("city") or "").lower().strip()
        key = (name_norm, city_norm)
        if key not in seen:
            seen.add(key)
            result.append(shop)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# EXACT NAME SEARCH — shop
# ─────────────────────────────────────────────────────────────────────────────

def search_shop_by_name(
    name: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Look up a specific shop by name. Returns the best match or None.
    Used when the user says "details about Royal Bakery" or "find Aryan Sweets".

    Confidence guard: if the top Typesense result's name does not meet
    NAME_MATCH_THRESHOLD similarity to the query, we return None rather
    than returning the wrong shop.

    No radius filter — exact name lookup is location-independent.
    Sort by distance when location is available, else by rating.
    """
    name = (name or "").strip()
    if not name:
        return None

    try:
        params: Dict[str, Any] = {
            "q":                      name,
            "query_by":               "name",
            "num_typos":              1,
            "per_page":               3,   # fetch top 3, pick best similarity
            "prioritize_exact_match": True,
        }

        if user_lat is not None and user_lng is not None:
            params["sort_by"] = f"_text_match:desc,location({user_lat}, {user_lng}):asc"
        else:
            params["sort_by"] = "_text_match:desc,rating:desc"

        hits = _safe_search("shops", params)
        if not hits:
            return None

        query_lower = name.lower()
        best_hit    = None
        best_score  = 0.0

        for hit in hits:
            doc        = hit["document"]
            result_name = (doc.get("name") or "").lower()
            score = difflib.SequenceMatcher(None, query_lower, result_name).ratio()
            if score > best_score:
                best_score = score
                best_hit   = hit

        if best_score < NAME_MATCH_THRESHOLD or best_hit is None:
            logger.info(
                "Exact shop lookup: '%s' → best match score %.2f < threshold %.2f → no result",
                name, best_score, NAME_MATCH_THRESHOLD,
            )
            return None

        doc         = best_hit["document"]
        distance_km = _extract_distance(best_hit)
        shop        = _build_shop(doc, distance_km)
        logger.info(
            "Exact shop match: '%s' → '%s' (score=%.2f)",
            name, shop["name"], best_score,
        )
        return shop

    except Exception as exc:
        logger.error("search_shop_by_name failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# EXACT TITLE SEARCH — job
# ─────────────────────────────────────────────────────────────────────────────

def search_job_by_title(
    title: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Look up a specific job by position title or shop name.
    Returns the best match or None. No radius filter.
    Always restricted to active jobs (status=1).
    """
    title = (title or "").strip()
    if not title:
        return None

    try:
        params: Dict[str, Any] = {
            "q":                      title,
            "query_by":               "position,shop_name",
            "query_by_weights":       "4,2",
            "num_typos":              1,
            "per_page":               3,
            "prioritize_exact_match": True,
            "filter_by":              "status:=1",
        }

        if user_lat is not None and user_lng is not None:
            params["sort_by"] = f"_text_match:desc,location({user_lat}, {user_lng}):asc,created_ts:desc"
        else:
            params["sort_by"] = "_text_match:desc,created_ts:desc"

        hits = _safe_search("jobs", params)
        if not hits:
            return None

        query_lower = title.lower()
        best_hit    = None
        best_score  = 0.0

        for hit in hits:
            doc           = hit["document"]
            position_name = (doc.get("position") or "").lower()
            score = difflib.SequenceMatcher(None, query_lower, position_name).ratio()
            if score > best_score:
                best_score = score
                best_hit   = hit

        if best_score < NAME_MATCH_THRESHOLD or best_hit is None:
            logger.info(
                "Exact job lookup: '%s' → best match score %.2f < threshold → no result",
                title, best_score,
            )
            return None

        doc         = best_hit["document"]
        distance_km = _extract_distance(best_hit)
        job         = _build_job(doc, distance_km)
        logger.info(
            "Exact job match: '%s' → '%s' (score=%.2f)",
            title, job["position"], best_score,
        )
        return job

    except Exception as exc:
        logger.error("search_job_by_title failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SHOP SEARCH — rating-based (no location)
# ─────────────────────────────────────────────────────────────────────────────

@cache_result(ttl=300, prefix="rated_search")
def _rating_search(keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search shops sorted by rating when the user has not shared location."""
    params = _shop_base_params(keyword or "*", limit)
    params["sort_by"] = "rating:desc,review_count:desc"
    hits = _safe_search("shops", params)
    return [_build_shop(h["document"]) for h in hits]


def search_shops_by_rating(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Public alias — return top-rated shops without location context."""
    return _rating_search(query or "*", limit)


# ─────────────────────────────────────────────────────────────────────────────
# SHOP SEARCH — geo multi-keyword
#
# Search strategy (in order):
#   1. keyword + category (subcategory or parent filter)
#   2. If 0 results and category is a subcategory → try parent category
#   3. If still 0 results and category is set → keyword only + strict relevance
#   4. If no location → fall back to rating-based search
#
# Cache key excludes category_names list — is_parent is computed internally
# using the derived lookup table, so no external list is needed.
# ─────────────────────────────────────────────────────────────────────────────

@cache_result(ttl=300, prefix="geo_search")
def search_shops_parallel(
    keywords: tuple,
    category: str = "",
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    radius_km: int = DEFAULT_RADIUS_KM,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Search shops using multiple AI-extracted keywords.

    Args:
        keywords:   Tuple of search keywords (tuple for cache hashing).
        category:   Optional category or subcategory filter.
        user_lat:   User latitude (None = no location).
        user_lng:   User longitude (None = no location).
        radius_km:  Search radius in km.
        limit:      Maximum results to return.

    Returns:
        {"shops": [...], "message": str, "radius_used_km": int}
    """
    kw_list   = [k for k in keywords if k and k.strip()] or ["*"]
    radius_km = max(1, min(MAX_RADIUS_KM, int(radius_km)))

    # ── No location → rating fallback ────────────────────────────────────────
    if user_lat is None or user_lng is None:
        logger.info("search_shops_parallel: no location → rating fallback")
        seen: Dict[int, Dict] = {}
        for kw in kw_list:
            for shop in _rating_search(kw, limit):
                if shop["id"] not in seen:
                    seen[shop["id"]] = shop
        return {
            "shops":          list(seen.values())[:limit],
            "message":        "",
            "radius_used_km": 0,
        }

    # ── Geo search ────────────────────────────────────────────────────────────
    geo_sort   = f"location({user_lat}, {user_lng}):asc"
    all_shops: Dict[int, Dict] = {}

    def _run_keyword(kw: str, filter_str: str) -> List[Dict]:
        params = _shop_base_params(kw, limit)
        params["sort_by"]   = geo_sort
        params["filter_by"] = filter_str
        return _safe_search("shops", params)

    # Phase 1 — keyword + category filter (all keywords, collect into all_shops)
    primary_filter = _build_geo_filter(user_lat, user_lng, radius_km, category)

    for kw in kw_list:
        hits = _run_keyword(kw, primary_filter)
        _merge_shop_hits(
            hits, all_shops, category,
            radius_km=radius_km,
            require_distance=(user_lat is not None),
        )


    # Phase 2 — if 0 results and category is a subcategory → try parent
    if not all_shops and category and not _is_parent_category(category):
        parent = _get_parent(category)
        if parent:
            parent_filter = _build_geo_filter(user_lat, user_lng, radius_km, parent)
            logger.info(
                "Phase 2: subcategory '%s' → 0 hits, trying parent '%s'",
                category, parent,
            )
            for kw in kw_list:
                hits = _run_keyword(kw, parent_filter)
                _merge_shop_hits(
                    hits, all_shops, parent,
                    radius_km=radius_km,
                    require_distance=(user_lat is not None),
                )

    # Phase 3 — if still 0 → keyword-only + strict whole-word relevance check
    if not all_shops and category:
        geo_only_filter = f"location:({user_lat}, {user_lng}, {radius_km} km)"
        logger.info(
            "Phase 3: still 0 results for '%s', trying keyword-only with relevance guard",
            category,
        )
        parent = _get_parent(category)  # compute once for all keywords

        for kw in kw_list:
            hits = _run_keyword(kw, geo_only_filter)
            for hit in hits:
                distance_km = _extract_distance(hit)
                shop = _build_shop(hit["document"], distance_km)
                sid  = shop["id"]
                if sid in all_shops:
                    continue

                # Distance guard — reject if no coords or beyond radius
                if distance_km is None or distance_km > radius_km:
                    continue

                shop_cat = (shop.get("category")    or "").lower()
                shop_sub = (shop.get("subcategory") or "").lower()
                cat_lower = category.lower()
                par_lower = parent.lower() if parent else ""

                # Whole-word match required — prevents "it" matching "electrical"
                category_match = (
                    _whole_word_match(cat_lower, shop_cat) or
                    _whole_word_match(cat_lower, shop_sub) or
                    (par_lower and _whole_word_match(par_lower, shop_cat))
                )

                if category_match:
                    all_shops[sid] = shop
                    logger.debug("Phase 3 accepted: '%s'", shop["name"])

    # ── No results at all ────────────────────────────────────────────────────
    if not all_shops:
        label   = category or ", ".join(kw_list) if kw_list != ["*"] else "shops"
        message = (
            f"No {label} found within {radius_km} km. "
            f"Try increasing the search radius."
        )
        logger.info(
            "No results: keywords=%s category='%s' radius=%skm",
            kw_list, category, radius_km,
        )
        return {"shops": [], "message": message, "radius_used_km": radius_km}

    # ── Sort, deduplicate, trim ───────────────────────────────────────────────
    # ── Hard distance cap: reject shops beyond radius ─────────────────────────
    # Guards against shops with missing/wrong coordinates slipping through
    # the Typesense geo filter.
    if user_lat is not None and user_lng is not None:
        capped = {
            sid: shop for sid, shop in all_shops.items()
            if shop.get("distance_km") is not None
            and shop["distance_km"] <= radius_km
        }
        if not capped:
            # All hits were beyond radius → genuinely no results nearby
            label   = category or ", ".join(kw_list) if kw_list != ["*"] else "shops"
            return {
                "shops": [],
                "message": f"No {label} found within {radius_km} km.",
                "radius_used_km": radius_km,
            }
        all_shops = capped

    # ── Sort, deduplicate, trim ───────────────────────────────────────────────
    shops_sorted = sorted(
        all_shops.values(),
        key=lambda s: (s.get("distance_km") or 999),
    )
    shops_list = _deduplicate_shops(shops_sorted)[:limit]

    logger.info(
        "Parallel shop search: %d keywords → %d shops (radius=%skm category='%s')",
        len(kw_list), len(shops_list), radius_km, category,
    )

    return {
        "shops":          shops_list,
        "message":        "",
        "radius_used_km": radius_km,
    }


def _merge_shop_hits(
    hits: List[Dict],
    all_shops: Dict[int, Dict],
    category: str,
    radius_km: Optional[int] = None,
    require_distance: bool = False,
) -> None:
    for hit in hits:
        distance_km = _extract_distance(hit)
        shop = _build_shop(hit["document"], distance_km)
        sid  = shop["id"]

        # Reject shops with no distance data when location was provided
        # These are shops indexed without coordinates — they bypass geo filter
        if require_distance and distance_km is None:
            logger.debug(
                "Distance guard rejected '%s' — no distance data",
                shop.get("name"),
            )
            continue

        # Hard radius cap at merge time (secondary guard)
        if radius_km is not None and distance_km is not None:
            if distance_km > radius_km:
                logger.debug(
                    "Radius guard rejected '%s' — %.1fkm > %dkm radius",
                    shop.get("name"), distance_km, radius_km,
                )
                continue

        if not _is_relevant(shop, category):
            logger.debug(
                "Relevance rejected: '%s' (shop_cat='%s' filter='%s')",
                shop.get("name"), shop.get("category"), category,
            )
            continue

        existing = all_shops.get(sid)
        if existing is None:
            all_shops[sid] = shop
        else:
            new_dist  = shop.get("distance_km") or 999
            prev_dist = existing.get("distance_km") or 999
            if new_dist < prev_dist:
                all_shops[sid] = shop


# ─────────────────────────────────────────────────────────────────────────────
# JOB SEARCH — Typesense multi-keyword
#
# Jobs are NEVER filtered by radius — they are sorted by distance only.
# This is intentional: job seekers will travel, unlike shop customers.
# Always filters by status=1 (active jobs only).
# ─────────────────────────────────────────────────────────────────────────────

@cache_result(ttl=120, prefix="job_search")
def search_jobs_typesense(
    keywords: tuple,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Search jobs using multiple AI-extracted keywords.
    Generic queries ("jobs near me", "vacancy") search all active jobs.

    Args:
        keywords:  Tuple of search keywords.
        user_lat:  User latitude for distance sorting (optional).
        user_lng:  User longitude for distance sorting (optional).
        limit:     Maximum results to return.

    Returns:
        {"jobs": [...], "total": int}
    """
    kw_list = [k.strip() for k in keywords if k and k.strip()] or ["*"]

    # Generic job query → search everything
    clean = [k.lower() for k in kw_list]
    if all(k in JOB_GENERIC_KEYWORDS for k in clean):
        kw_list = ["*"]

    has_location = user_lat is not None and user_lng is not None

    all_jobs: Dict[int, Dict] = {}

    for kw in kw_list:
        params = _job_base_params(kw, limit)
        params["filter_by"] = "status:=1"

        if has_location:
            params["sort_by"] = (
                f"location({user_lat}, {user_lng}):asc,created_ts:desc"
            )
        else:
            params["sort_by"] = "created_ts:desc"

        hits = _safe_search("jobs", params)

        for hit in hits:
            distance_km = _extract_distance(hit)
            job = _build_job(hit["document"], distance_km)
            jid = job["id"]
            if jid not in all_jobs:
                all_jobs[jid] = job
            elif has_location:
                # Keep closer distance if this keyword returned a better hit
                new_dist  = distance_km or 999
                prev_dist = all_jobs[jid].get("distance_km") or 999
                if new_dist < prev_dist:
                    all_jobs[jid] = job

    # Sort merged results
    if has_location:
        jobs_sorted = sorted(
            all_jobs.values(),
            key=lambda j: (j.get("distance_km") or 999),
        )
    else:
        jobs_sorted = list(all_jobs.values())

    jobs_list = jobs_sorted[:limit]
    logger.info(
        "Job search: %d keywords → %d unique jobs (location=%s)",
        len(kw_list), len(jobs_list), has_location,
    )
    return {"jobs": jobs_list, "total": len(jobs_list)}


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT SEARCH
#
# One Typesense doc per (product × shop) pair.
# Relevance guard: primary keyword (most specific) must appear in product name.
# Primary keyword = first after sorting by specificity.
# ─────────────────────────────────────────────────────────────────────────────

@cache_result(ttl=120, prefix="product_search")
def search_products_typesense(
    keywords: tuple,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    radius_km: int = DEFAULT_RADIUS_KM,
    limit: int = 6,
) -> Dict[str, Any]:
    """
    Search products in Typesense.
    Returns shops that sell the product, sorted by distance.

    Returns:
        {"products": [...], "total": int}
    """
    kw_list = [k.strip() for k in keywords if k and k.strip()] or ["*"]

    # Sort by specificity so the most meaningful term is the anchor
    kw_prioritised = _prioritise_keywords(kw_list)
    primary_words  = set(
        w for w in kw_prioritised[0].lower().split()
        if w not in _NOISE_WORDS
    ) if kw_prioritised else set()

    has_location   = user_lat is not None and user_lng is not None
    all_products: Dict[str, Dict] = {}

    for kw in kw_prioritised:
        params: Dict[str, Any] = {
            "q":                      kw,
            "query_by":               "product_name,shop_name,category,subcategory",
            "query_by_weights":       "4,2,1,1",
            "num_typos":              1,
            "per_page":               limit,
            "prioritize_exact_match": True,
        }

        if has_location:
            params["filter_by"] = f"location:({user_lat}, {user_lng}, {radius_km} km)"
            params["sort_by"]   = f"location({user_lat}, {user_lng}):asc"
        else:
            params["sort_by"] = "has_offer:desc"

        hits = _safe_search("products", params)

        for hit in hits:
            doc    = hit["document"]
            doc_id = doc.get("id", "")
            if doc_id in all_products:
                continue

            # Relevance guard: at least one primary word must appear in product name
            if primary_words:
                product_words = set(
                    (doc.get("product_name") or "").lower().split()
                )
                if not (primary_words & product_words):
                    logger.debug(
                        "Product rejected: '%s' for primary_words=%s",
                        doc.get("product_name"), primary_words,
                    )
                    continue

            all_products[doc_id] = _build_product(doc, _extract_distance(hit))

    # Sort by distance
    if has_location:
        products_sorted = sorted(
            all_products.values(),
            key=lambda p: (p.get("distance_km") or 999),
        )
    else:
        products_sorted = list(all_products.values())

    result = products_sorted[:limit]
    logger.info("Product search: %d keywords → %d results", len(kw_list), len(result))
    return {"products": result, "total": len(result)}


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE SEARCH
#
# Same structure as product search. Relevance guard on service_name.
# Category 13 services use user_address stored at index time.
# ─────────────────────────────────────────────────────────────────────────────

@cache_result(ttl=120, prefix="service_search")
def search_services_typesense(
    keywords: tuple,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    radius_km: int = DEFAULT_RADIUS_KM,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Search services in Typesense.
    Returns shops that provide the service, sorted by distance.

    Returns:
        {"services": [...], "total": int}
    """
    kw_list = [k.strip() for k in keywords if k and k.strip()] or ["*"]

    # Sort so most specific term is the relevance anchor
    kw_prioritised = _prioritise_keywords(kw_list)
    primary_words  = set(
        w for w in kw_prioritised[0].lower().split()
        if w not in _NOISE_WORDS
    ) if kw_prioritised else set()

    has_location    = user_lat is not None and user_lng is not None
    all_services: Dict[str, Dict] = {}

    for kw in kw_prioritised:
        params: Dict[str, Any] = {
            "q":                      kw,
            "query_by":               "service_name,shop_name,category,subcategory",
            "query_by_weights":       "4,2,1,1",
            "num_typos":              1,
            "per_page":               limit,
            "prioritize_exact_match": True,
        }

        if has_location:
            params["filter_by"] = f"location:({user_lat}, {user_lng}, {radius_km} km)"
            params["sort_by"]   = f"location({user_lat}, {user_lng}):asc"
        else:
            params["sort_by"] = "has_offer:desc"

        hits = _safe_search("services", params)

        for hit in hits:
            doc    = hit["document"]
            doc_id = doc.get("id", "")
            if doc_id in all_services:
                continue

            # Relevance guard: at least one primary word must appear in service name
            if primary_words:
                service_words = set(
                    (doc.get("service_name") or "").lower().split()
                )
                if not (primary_words & service_words):
                    logger.debug(
                        "Service rejected: '%s' for primary_words=%s",
                        doc.get("service_name"), primary_words,
                    )
                    continue

            all_services[doc_id] = _build_service(doc, _extract_distance(hit))

    # Sort by distance
    if has_location:
        services_sorted = sorted(
            all_services.values(),
            key=lambda s: (s.get("distance_km") or 999),
        )
    else:
        services_sorted = list(all_services.values())

    result = services_sorted[:limit]
    logger.info("Service search: %d keywords → %d results", len(kw_list), len(result))
    return {"services": result, "total": len(result)}


# ─────────────────────────────────────────────────────────────────────────────
# OFFERS — batch DB fetch
# ─────────────────────────────────────────────────────────────────────────────

def get_batch_shop_offers(shop_ids: List[int]) -> Dict[int, List[Dict]]:
    """
    Fetch active offers for multiple shops in a single DB query.
    Capped at MAX_OFFERS_PER_SHOP per shop to prevent frontend overload.

    Returns:
        {shop_id: [offer_dict, ...]}
    """
    if not shop_ids:
        return {}

    try:
        placeholders = ",".join(["%s"] * len(shop_ids))
        # ROW_NUMBER() caps results per shop without multiple queries
        rows = fetch_all(
            f"""
            SELECT
                shop_id,
                offer_heading,
                offer_price,
                actual_price,
                start_date,
                end_date,
                description,
                category_name,
                offer_image,
                product_img1,
                product_img2,
                product_img3
            FROM (
                SELECT
                    o.shop_id,
                    o.offer_heading,
                    o.offer_price,
                    o.actual_price,
                    o.start_date,
                    o.end_date,
                    o.description,
                    o.offer_image,
                    o.product_img1,
                    o.product_img2,
                    o.product_img3,
                    c.categoriesname  AS category_name,
                    ROW_NUMBER() OVER (
                        PARTITION BY o.shop_id
                        ORDER BY o.created_at DESC
                    ) AS rn
                FROM   offer o
                LEFT JOIN categories c ON c.id = o.category_id
                WHERE  o.shop_id IN ({placeholders})
                  AND  o.status   = 1
                  AND  o.end_date >= CURDATE()
            ) ranked
            WHERE rn <= %s
            ORDER BY shop_id, rn
            """,
            (*shop_ids, MAX_OFFERS_PER_SHOP),
        )

        from typesense_setup import _offer_img_url
        result: Dict[int, List[Dict]] = {sid: [] for sid in shop_ids}
        for row in (rows or []):
            sid = row.get("shop_id")
            if sid in result:
                result[sid].append({
                    **row,
                    "offer_image":  _offer_img_url(row.get("offer_image")  or ""),
                    "product_img1": _offer_img_url(row.get("product_img1") or ""),
                    "product_img2": _offer_img_url(row.get("product_img2") or ""),
                    "product_img3": _offer_img_url(row.get("product_img3") or ""),
                })
        return result

    except Exception as exc:
        logger.warning("get_batch_shop_offers failed: %s", exc)
        return {sid: [] for sid in shop_ids}


def get_shop_offers(shop_id: int) -> List[Dict]:
    """Get offers for a single shop."""
    return get_batch_shop_offers([shop_id]).get(shop_id, [])


# ─────────────────────────────────────────────────────────────────────────────
# OFFER SEARCH
#
# Three-step pipeline:
#   1. DB  → collect shop_ids that have active offers (optionally by category)
#   2. Typesense → geo-filter those shop_ids to find nearby ones
#   3. DB  → fetch the actual offer rows for matched shops
#
# Location is required. If missing, returns a clear error message.
# Category filtering handles parent/subcategory distinction correctly.
# ─────────────────────────────────────────────────────────────────────────────

def search_shops_by_offer(
    user_lat: Optional[float],
    user_lng: Optional[float],
    radius_km: int = DEFAULT_RADIUS_KM,
    category_name: str = "",
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Return nearby shops that have at least one active offer.

    Args:
        user_lat:      User latitude. Required — returns error if None.
        user_lng:      User longitude. Required — returns error if None.
        radius_km:     Search radius in km.
        category_name: Optional category filter (parent or subcategory name).
        limit:         Max shops to return.

    Returns:
        {
            "shops":          [shop_dict, ...],
            "offers":         {shop_id: [offer_dict, ...]},
            "message":        str,
            "radius_used_km": int,
        }
    """
    _empty = {
        "shops": [], "offers": {}, "message": "", "radius_used_km": radius_km,
    }

    # ── Guard: location is required for offer search ──────────────────────────
    if user_lat is None or user_lng is None:
        logger.info("search_shops_by_offer: no location provided")
        return {
            **_empty,
            "message": "Please share your location to find nearby offers.",
        }

    radius_km = max(1, min(MAX_RADIUS_KM, int(radius_km)))

    # ── Step 1: DB → shop_ids with active offers ──────────────────────────────
    try:
        shop_ids = _fetch_offer_shop_ids(category_name)
    except Exception as exc:
        logger.error("search_shops_by_offer DB step failed: %s", exc)
        return {**_empty, "message": "Offer search temporarily unavailable."}

    if not shop_ids:
        label   = f" for {category_name}" if category_name else ""
        return {
            **_empty,
            "message": f"No active offers found{label} right now.",
        }

    # ── Step 2: Typesense → geo-filter to nearby shops ───────────────────────
    try:
        id_filter  = f"id:[{', '.join(str(i) for i in shop_ids)}]"
        geo_filter = f"location:({user_lat}, {user_lng}, {radius_km} km)"

        params = {
            "q":         "*",
            "query_by":  "name",
            "filter_by": f"{id_filter} && {geo_filter}",
            "sort_by":   f"location({user_lat}, {user_lng}):asc",
            "per_page":  limit,
        }
        hits = _safe_search("shops", params)

    except Exception as exc:
        logger.error("search_shops_by_offer Typesense step failed: %s", exc)
        return {**_empty, "message": "Offer search temporarily unavailable."}

    if not hits:
        label   = f" for {category_name}" if category_name else ""
        return {
            **_empty,
            "message": (
                f"No shops with active offers found within {radius_km} km{label}. "
                f"Try increasing the search radius."
            ),
        }

    # ── Step 3: build shop objects + fetch their offers ───────────────────────
    shops        = [_build_shop(h["document"], _extract_distance(h)) for h in hits]
    int_ids      = [s["id"] for s in shops]
    batch_offers = get_batch_shop_offers(int_ids)

    # Edge case: offer may have expired between DB query and now
    shops_with_offers = [s for s in shops if batch_offers.get(s["id"])]

    if not shops_with_offers:
        label = f" for {category_name}" if category_name else ""
        return {
            **_empty,
            "message": (
                f"No shops with active offers found within {radius_km} km{label}."
            ),
        }

    logger.info(
        "Offer search: category='%s' radius=%skm → %d shops",
        category_name, radius_km, len(shops_with_offers),
    )

    return {
        "shops":          shops_with_offers,
        "offers":         {s["id"]: batch_offers[s["id"]] for s in shops_with_offers},
        "message":        "",
        "radius_used_km": radius_km,
    }



def _fetch_offer_shop_ids(category_name: str) -> List[int]:
    """
    DB query helper — returns shop_ids that have active, non-expired offers.
    Handles parent category, subcategory, and no-filter cases.
    Falls back from subcategory to parent if subcategory returns 0 rows.

    Returns a list of integer shop_ids.
    """
    base_join = """
        JOIN   shop_details sd ON sd.id = o.shop_id AND sd.status = 1
        JOIN   users u         ON u.id  = sd.partner_id AND u.subscriber_status = 1
        WHERE  o.status   = 1
          AND  o.end_date >= CURDATE()
        LIMIT  200
    """

    if not category_name or not category_name.strip():
        # No category filter
        rows = fetch_all(
            f"SELECT DISTINCT o.shop_id FROM offer o {base_join}"
        )

    elif _is_parent_category(category_name):
        # Filter by parent category name
        rows = fetch_all(
            f"""
            SELECT DISTINCT o.shop_id
            FROM   offer o
            JOIN   categories c ON c.id = o.category_id
                               AND c.categoriesname = %s
            {base_join}
            """,
            (category_name,),
        )

    else:
        # Filter by subcategory name; fall back to parent if 0 rows
        rows = fetch_all(
            f"""
            SELECT DISTINCT o.shop_id
            FROM   offer o
            JOIN   subcategories sc ON sc.id = o.subcategory_id
                                   AND sc.subcategoryname = %s
            {base_join}
            """,
            (category_name,),
        )
        if not rows:
            parent = _get_parent(category_name)
            if parent:
                logger.info(
                    "Offer subcategory '%s' → 0 rows, trying parent '%s'",
                    category_name, parent,
                )
                rows = fetch_all(
                    f"""
                    SELECT DISTINCT o.shop_id
                    FROM   offer o
                    JOIN   categories c ON c.id = o.category_id
                                       AND c.categoriesname = %s
                    {base_join}
                    """,
                    (parent,),
                )

    return [int(row["shop_id"]) for row in (rows or []) if row.get("shop_id")]