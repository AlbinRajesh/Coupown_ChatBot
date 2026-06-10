"""
Typesense setup and shop index initialization
Run once to create the search index.

Typesense 27.1 geo search syntax:
  sort_by:    location(lat, lng):asc
  filter_by:  location:(lat, lng, 10 km)
"""

import typesense
import logging
from config import config
from database import fetch_all

logger = logging.getLogger(__name__)


_STORAGE_BASE = "https://coupown.in/storage/"

def _offer_img_url(path: str) -> str:
    """Convert a raw DB path to a full storage URL. No-op if already a URL or empty."""
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return f"{_STORAGE_BASE}{path}"

client = typesense.Client({
    "nodes": [{
        "host": config.TYPESENSE_HOST,
        "port": config.TYPESENSE_PORT,
        "protocol": config.TYPESENSE_PROTOCOL
    }],
    "api_key": config.TYPESENSE_API_KEY,
    "connection_timeout_seconds": config.TYPESENSE_TIMEOUT
})
SHOP_SCHEMA = {
    "name": "shops",
    "fields": [
        {"name": "location",      "type": "geopoint", "optional": True},
        {"name": "rating",        "type": "float",    "optional": True},
        {"name": "review_count",  "type": "int32",    "optional": True},
        {"name": "name",         "type": "string"},
        {"name": "category",     "type": "string",  "facet": True,  "optional": True},
        {"name": "subcategory",  "type": "string",  "facet": True,  "optional": True},
        {"name": "city",         "type": "string",  "facet": True,  "optional": True},
        {"name": "phone",        "type": "string",  "optional": True},
        {"name": "logo",         "type": "string",  "optional": True},
        {"name": "address",      "type": "string",  "optional": True},
        {"name": "landmark",     "type": "string",  "optional": True},
        {"name": "keywords",     "type": "string",  "optional": True},
        {"name": "description",  "type": "string",  "optional": True},
        {"name": "offers",       "type": "string",  "optional": True},
        {"name": "offer_text",   "type": "string",  "optional": True},
        {"name": "has_offer",    "type": "bool",    "facet": True, "optional": True},
        {"name": "tags",         "type": "string",  "optional": True},
        {"name": "review_texts", "type": "string",  "optional": True},
    ]
}
JOB_SCHEMA = {
    "name": "jobs",
    "fields": [
        {"name": "shop_id",     "type": "string",   "optional": True},
        {"name": "shop_name",   "type": "string",   "optional": True},
        {"name": "shop_logo",   "type": "string",   "optional": True},
        {"name": "position",    "type": "string"},
        {"name": "job_type",    "type": "string",   "optional": True},
        {"name": "experience",  "type": "string",   "optional": True},
        {"name": "description", "type": "string",   "optional": True},
        {"name": "city",        "type": "string",   "optional": True},
        {"name": "phone",       "type": "string",   "optional": True},
        {"name": "job_pic",     "type": "string",   "optional": True},
        {"name": "status",      "type": "int32",    "optional": True},
        {"name": "created_ts",  "type": "int64",    "optional": True},
        {"name": "location",    "type": "geopoint", "optional": True},
    ]
}

PRODUCT_SCHEMA = {
    "name": "products",
    "fields": [
        {"name": "product_name", "type": "string"},
        {"name": "shop_id",      "type": "string",   "optional": True},
        {"name": "shop_name",    "type": "string",   "optional": True},
        {"name": "shop_logo",    "type": "string",   "optional": True},
        {"name": "shop_phone",   "type": "string",   "optional": True},
        {"name": "category",     "type": "string",   "facet": True, "optional": True},
        {"name": "subcategory",  "type": "string",   "facet": True, "optional": True},
        {"name": "city",         "type": "string",   "facet": True, "optional": True},
        {"name": "offer_id",     "type": "string",   "optional": True},
        {"name": "has_offer",    "type": "bool",     "facet": True, "optional": True},
        {"name": "offer_heading","type": "string",   "optional": True},
        {"name": "offer_price",  "type": "int32",    "optional": True},
        {"name": "actual_price", "type": "int32",    "optional": True},
        {"name": "end_date",     "type": "string",   "optional": True},
        {"name": "description",  "type": "string",   "optional": True},
        {"name": "keywords",     "type": "string",   "optional": True},
        {"name": "location",     "type": "geopoint", "optional": True},
        {"name": "offer_image",   "type": "string", "optional": True},
        {"name": "product_img1",  "type": "string", "optional": True},
        {"name": "product_img2",  "type": "string", "optional": True},
        {"name": "product_img3",  "type": "string", "optional": True},
    ]
}

SERVICE_SCHEMA = {
    "name": "services",
    "fields": [
        {"name": "service_name", "type": "string"},
        {"name": "shop_id",      "type": "string",   "optional": True},
        {"name": "shop_name",    "type": "string",   "optional": True},
        {"name": "shop_logo",    "type": "string",   "optional": True},
        {"name": "shop_phone",   "type": "string",   "optional": True},
        {"name": "category",     "type": "string",   "facet": True, "optional": True},
        {"name": "subcategory",  "type": "string",   "facet": True, "optional": True},
        {"name": "city",         "type": "string",   "facet": True, "optional": True},
        {"name": "offer_id",     "type": "string",   "optional": True},
        {"name": "has_offer",    "type": "bool",     "facet": True, "optional": True},
        {"name": "offer_heading","type": "string",   "optional": True},
        {"name": "offer_price",  "type": "int32",    "optional": True},
        {"name": "actual_price", "type": "int32",    "optional": True},
        {"name": "end_date",     "type": "string",   "optional": True},
        {"name": "description",  "type": "string",   "optional": True},
        {"name": "keywords",     "type": "string",   "optional": True},
        {"name": "is_category_13","type": "bool",    "optional": True},
        {"name": "location",     "type": "geopoint", "optional": True},
        {"name": "offer_image",   "type": "string", "optional": True},
        {"name": "product_img1",  "type": "string", "optional": True},
        {"name": "product_img2",  "type": "string", "optional": True},
        {"name": "product_img3",  "type": "string", "optional": True},
    ]
}
SHOP_JOIN_SQL = """
    SELECT
        sd.id, sd.name, sd.phone, sd.shoplogo, sd.status,
        sa.city, sa.latitude, sa.longitude,
        sa.arearoadname, sa.nearbylandmark,
        c.categoriesname                                        AS category,
        s.subcategoryname                                       AS subcategory,
        ROUND(AVG(r.rating), 1)                                 AS avg_rating,
        COUNT(DISTINCT r.id)                                    AS review_count,
        GROUP_CONCAT(DISTINCT o.offer_heading
            ORDER BY o.created_at DESC
            SEPARATOR ' | ')                                    AS offer_text
    FROM shop_details sd

    INNER JOIN users u                          -- ← add this
        ON  u.id                = sd.partner_id
        AND u.subscriber_status = 1

    JOIN  shop_address   sa ON sa.shop_id      = sd.id
                           AND sa.is_default   = 1
    JOIN  categories     c  ON c.id            = sd.category_id
    LEFT JOIN subcategories s  ON s.id         = sd.subcategory_id
    LEFT JOIN reviews       r  ON r.shop_id    = sd.id
    LEFT JOIN offer         o  ON o.shop_id    = sd.id
                               AND o.status    = 1
                               AND o.end_date >= CURDATE()
    WHERE sd.status = 1
    GROUP BY
        sd.id, sd.name, sd.phone, sd.shoplogo,
        sa.city, sa.latitude, sa.longitude,
        sa.arearoadname, sa.nearbylandmark,
        c.categoriesname, s.subcategoryname
"""

SHOP_JOIN_BY_ID_SQL = SHOP_JOIN_SQL.replace(
    "WHERE sd.status = 1",
    "WHERE sd.id = %s"    # no status filter — checked in Python
)
JOB_JOIN_SQL = """
    SELECT
        j.id, 
        j.shop_id, 
        j.position, 
        j.job_type,
        j.experience, 
        j.description, 
        j.created_at,
        j.status,
        j.phone,  
        j.job_pic,                                    
        COALESCE(sd.name, '') AS shop_name,
        COALESCE(sd.shoplogo, '') AS shoplogo,
        sa.city, 
        sa.latitude, 
        sa.longitude
    FROM jobsdata j
    INNER JOIN shop_details sd ON sd.id = j.shop_id
    INNER JOIN users u ON u.id = j.user_id AND u.subscriber_status = 1
    LEFT JOIN shop_address sa ON sa.shop_id = j.shop_id AND sa.is_default = 1
    WHERE j.status = 1
      AND (j.job_endDate IS NULL OR j.job_endDate >= CURDATE())
"""

JOB_JOIN_BY_ID_SQL = JOB_JOIN_SQL.replace(
    "WHERE j.status = 1",
    "WHERE j.id = %s AND j.status = 1"          # no status filter — we check status in Python
)

PRODUCT_JOIN_SQL = """
    SELECT
        p.id                                    AS product_id,
        p.product_name,
        p.user_id,
        sd.id                                   AS shop_id,
        sd.name                                 AS shop_name,
        sd.shoplogo                             AS shop_logo,
        sd.phone                                AS shop_phone,
        sa.city,
        sa.latitude,
        sa.longitude,
        c.categoriesname                        AS category,
        s.subcategoryname                       AS subcategory,
        o.id                                    AS offer_id,
        o.offer_heading,
        o.offer_price,
        o.actual_price,
        o.end_date,
        o.description                           AS offer_description,
        o.status                                AS offer_status,
        o.offer_image,
        o.product_img1,
        o.product_img2,
        o.product_img3
    FROM products p
    INNER JOIN users u
        ON  u.id                = p.user_id
        AND u.subscriber_status = 1
    INNER JOIN offer o
        ON  o.product_id        = p.id
    INNER JOIN shop_details sd
        ON  sd.id               = o.shop_id
        AND sd.status           = 1
    INNER JOIN shop_address sa
        ON  sa.shop_id          = sd.id
        AND sa.is_default       = 1
    LEFT JOIN categories c
        ON  c.id                = sd.category_id
    LEFT JOIN subcategories s
        ON  s.id                = sd.subcategory_id
"""

PRODUCT_JOIN_BY_ID_SQL = PRODUCT_JOIN_SQL + " WHERE p.id = %s"

SERVICE_JOIN_SQL = """
    SELECT
        sv.id                                   AS service_id,
        sv.service_name,
        sv.user_id,
        sd.id                                   AS shop_id,
        sd.name                                 AS shop_name,
        sd.shoplogo                             AS shop_logo,
        sd.phone                                AS shop_phone,
        o.id                                    AS offer_id,
        o.category_id                           AS offer_category_id,
        o.offer_heading,
        o.offer_price,
        o.actual_price,
        o.end_date,
        o.description                           AS offer_description,
        o.status                                AS offer_status,
        o.offer_image,
        o.product_img1,
        o.product_img2,
        o.product_img3,
        c.categoriesname                        AS category,
        s.subcategoryname                       AS subcategory,
        -- category 13: location from user_address
        ua.latitude                             AS ua_latitude,
        ua.longitude                            AS ua_longitude,
        ua.city                                 AS ua_city,
        ua.phone                                AS ua_phone,
        -- non category 13: location from shop_address
        sa.latitude                             AS sa_latitude,
        sa.longitude                            AS sa_longitude,
        sa.city                                 AS sa_city
    FROM service sv
    INNER JOIN users u
        ON  u.id                = sv.user_id
        AND u.subscriber_status = 1
    INNER JOIN offer o
        ON  o.service_id        = sv.id
        
    INNER JOIN shop_details sd
        ON  sd.id               = o.shop_id
        AND sd.status           = 1
    LEFT JOIN shop_address sa
        ON  sa.shop_id          = sd.id
        AND sa.is_default       = 1
    LEFT JOIN user_address ua
        ON  ua.user_id          = sv.user_id
        AND o.category_id       = 13
        
    LEFT JOIN categories c
        ON  c.id                = sd.category_id
    LEFT JOIN subcategories s
        ON  s.id                = sd.subcategory_id
"""

SERVICE_JOIN_BY_ID_SQL = SERVICE_JOIN_SQL + " WHERE sv.id = %s"

def build_shop_doc(row: dict):
    """
    Convert a database shop row into a Typesense document.
    
    Args:
        row (dict): Shop data from JOIN query, containing:
            - id, name, phone, shoplogo, city, arearoadname, nearbylandmark
            - category, subcategory, avg_rating, review_count, offer_text
            - latitude, longitude
    
    Returns:
        dict: Typesense-ready document with schema fields or None if row is empty.
            Document includes keywords for full-text search and location for geo queries.
    
    Example:
        >>> doc = build_shop_doc({'id': 1, 'name': 'Royal Bakery', 'latitude': 13.0, 'longitude': 80.0})
        >>> doc['location']
        [13.0, 80.0]
    """
    if not row:
        return None
    offer_text  = row.get("offer_text") or row.get("offers") or ""
    subcategory = row.get("subcategory") or ""
    category    = row.get("category") or ""
    keywords = " ".join(filter(None, [
        row.get("name"), category, subcategory,
        row.get("city"), row.get("arearoadname"),
        row.get("nearbylandmark"), offer_text,
    ]))
    tags = " ".join(filter(None, [category, subcategory, row.get("city")]))
    doc = {
        "id":           str(row["id"]),
        "name":         row.get("name")           or "",
        "phone":        row.get("phone")           or "",
        "logo":         row.get("shoplogo")        or "",
        "city":         row.get("city")            or "",
        "address":      row.get("arearoadname")    or "",
        "landmark":     row.get("nearbylandmark")  or "",
        "category":     category,
        "subcategory":  subcategory,
        "keywords":     keywords,
        "tags":         tags,
        "has_offer":    bool(offer_text.strip()),
        "offer_text":   offer_text,
        "offers":       offer_text,
        "rating":       float(row.get("avg_rating")   or 0.0),
        "review_count": int(row.get("review_count")   or 0),
    }
    lat, lng = row.get("latitude"), row.get("longitude")
    if lat is not None and lng is not None:
        try:
            doc["location"] = [float(lat), float(lng)]
        except (ValueError, TypeError):
            pass
    return doc

def build_job_doc(row: dict):
    """
    Convert a database job row into a Typesense document.
    
    Args:
        row (dict): Job data from JOIN query, containing:
            - id, shop_id, position, job_type, experience, description
            - shop_name, shoplogo (shop_logo), city, phone
            - created_at, status, latitude, longitude
    
    Returns:
        dict: Typesense-ready job document with schema fields or None if row is empty.
            Includes created_ts (Unix timestamp) for sorting by job posting date.
    
    Note:
        created_at is converted to Unix timestamp (created_ts) to allow Typesense sorting.
    """
    if not row:
        return None
    import datetime
    created_ts = 0
    raw = row.get("created_at")
    if raw:
        try:
            dt = datetime.datetime.fromisoformat(str(raw))
            created_ts = int(dt.timestamp())
        except Exception:
            created_ts = 0

    doc = {
    "id":          str(row["id"]),
    "shop_id":     str(row.get("shop_id") or ""),
    "shop_name":   row.get("shop_name")   or "",
    "shop_logo":   row.get("shoplogo")    or "",
    "position":    row.get("position")    or "",
    "job_type":    row.get("job_type")    or "",
    "experience":  str(row.get("experience")) if row.get("experience") is not None else "",
    "description": row.get("description") or "",
    "city":        row.get("city")         or "",
    "phone":       str(row.get("phone") or ""),
    "job_pic":     row.get("job_pic")      or "",
    "created_ts":  created_ts,
    "status":      int(row.get("status") or 0),
    }
    lat, lng = row.get("latitude"), row.get("longitude")
    if lat is not None and lng is not None:
        try:
            doc["location"] = [float(lat), float(lng)]
        except (ValueError, TypeError):
            pass
    return doc


def build_product_doc(row: dict):
    """
    Convert a database product row into a Typesense document.
    
    Product documents are created per product-shop pair via the offers table.
    This prevents collisions when the same product exists in multiple shops.
    
    Args:
        row (dict): Product data from JOIN query, containing:
            - product_id, shop_id, product_name, shop_name, shop_logo, shop_phone
            - category, subcategory, city, latitude, longitude
            - offer_id, offer_heading, offer_price, actual_price, end_date
            - offer_description, offer_status
    
    Returns:
        dict: Typesense document with:
            - id: Composite key f"p_{product_id}_{shop_id}" to prevent duplicates
            - has_offer: Boolean indicating if offer is active and not expired
            - Offer fields populated only if has_offer is True
        Or None if row is empty.
    
    Example:
        >>> row = {'product_id': '10', 'shop_id': '5', 'product_name': 'biryani', 'offer_status': 1, 'end_date': '2026-06-30'}
        >>> doc = build_product_doc(row)
        >>> doc['id']
        'p_10_5'
    """
    if not row:
        return None

    # Unique id: product_id + shop_id combination
    # prevents collision when same product is in multiple shops
    product_id = str(row.get("product_id") or "")
    shop_id    = str(row.get("shop_id")    or "")
    doc_id     = f"p_{product_id}_{shop_id}"

    # Check if offer is active
    import datetime
    has_offer   = False
    end_date_str = ""
    offer_status = int(row.get("offer_status") or 0)
    end_date_raw = row.get("end_date")

    if offer_status == 1 and end_date_raw:
        try:
            end_date = end_date_raw if isinstance(end_date_raw, datetime.date) else datetime.date.fromisoformat(str(end_date_raw))
            has_offer = end_date >= datetime.date.today()
            end_date_str = str(end_date_raw)
        except Exception:
            has_offer = False

    product_name = row.get("product_name") or ""
    category     = row.get("category")     or ""
    subcategory  = row.get("subcategory")  or ""
    city         = row.get("city")         or ""

    keywords = " ".join(filter(None, [
        product_name, category, subcategory,
    ]))

    doc = {
        "id":            doc_id,
        "product_name":  product_name,
        "shop_id":       shop_id,
        "shop_name":     row.get("shop_name")   or "",
        "shop_logo":     row.get("shop_logo")   or "",
        "shop_phone":    str(row.get("shop_phone") or ""),
        "category":      category,
        "subcategory":   subcategory,
        "city":          city,
        "offer_id":      str(row.get("offer_id") or ""),
        "has_offer":     has_offer,
        "offer_heading": row.get("offer_heading") or "" if has_offer else "",
        "offer_price":   int(row.get("offer_price")  or 0) if has_offer else 0,
        "actual_price":  int(row.get("actual_price") or 0) if has_offer else 0,
        "end_date":      end_date_str if has_offer else "",
        "description":   row.get("offer_description") or "",
        "keywords":      keywords,
    }

    doc["offer_image"]  = _offer_img_url(row.get("offer_image")  or "")
    doc["product_img1"] = _offer_img_url(row.get("product_img1") or "")
    doc["product_img2"] = _offer_img_url(row.get("product_img2") or "")
    doc["product_img3"] = _offer_img_url(row.get("product_img3") or "")

    lat, lng = row.get("latitude"), row.get("longitude")
    if lat is not None and lng is not None:
        try:
            doc["location"] = [float(lat), float(lng)]
        except (ValueError, TypeError):
            pass

    return doc


def build_service_doc(row: dict):
    """
    Convert a database service row into a Typesense document.
    
    Service documents are created per service-shop pair via the offers table.
    Supports dual location sources based on offer category:
      - category_id = 13 (home services): uses user_address (ua_*)
      - other categories: uses shop_address (sa_*)
    
    Args:
        row (dict): Service data from JOIN query, containing:
            - service_id, shop_id, service_name, shop_name, shop_logo, shop_phone
            - category, subcategory, city
            - offer_id, offer_heading, offer_price, actual_price, end_date, offer_category_id
            - ua_latitude, ua_longitude, ua_city, ua_phone (user address)
            - sa_latitude, sa_longitude, sa_city (shop address)
    
    Returns:
        dict: Typesense document with:
            - id: Composite key f"s_{service_id}_{shop_id}" to prevent duplicates
            - location: Chosen from user_address (cat 13) or shop_address (others)
            - is_category_13: Boolean flag for location source used
        Or None if row is empty.
    """
    if not row:
        return None

    service_id = str(row.get("service_id") or "")
    shop_id    = str(row.get("shop_id")    or "")
    doc_id     = f"s_{service_id}_{shop_id}"

    is_category_13 = int(row.get("offer_category_id") or 0) == 13

    # Pick location source based on category
    if is_category_13:
        lat  = row.get("ua_latitude")
        lng  = row.get("ua_longitude")
        city = row.get("ua_city") or ""
        phone = str(row.get("ua_phone") or "")
    else:
        lat  = row.get("sa_latitude")
        lng  = row.get("sa_longitude")
        city = row.get("sa_city") or ""
        phone = str(row.get("shop_phone") or "")

    # Check if offer is active
    import datetime
    has_offer    = False
    end_date_str = ""
    offer_status = int(row.get("offer_status") or 0)
    end_date_raw = row.get("end_date")

    if offer_status == 1 and end_date_raw:
        try:
            end_date  = end_date_raw if isinstance(end_date_raw, datetime.date) else datetime.date.fromisoformat(str(end_date_raw))
            has_offer = end_date >= datetime.date.today()
            end_date_str = str(end_date_raw)
        except Exception:
            has_offer = False

    service_name = row.get("service_name") or ""
    category     = row.get("category")     or ""
    subcategory  = row.get("subcategory")  or ""

    keywords = " ".join(filter(None, [
        service_name, category, subcategory, city,
        row.get("shop_name"), row.get("offer_heading"),
    ]))

    doc = {
        "id":              doc_id,
        "service_name":    service_name,
        "shop_id":         shop_id,
        "shop_name":       row.get("shop_name") or "",
        "shop_logo":       row.get("shop_logo") or "",
        "shop_phone":      phone,
        "category":        category,
        "subcategory":     subcategory,
        "city":            city,
        "offer_id":        str(row.get("offer_id") or ""),
        "has_offer":       has_offer,
        "offer_heading":   row.get("offer_heading") or "" if has_offer else "",
        "offer_price":     int(row.get("offer_price")  or 0) if has_offer else 0,
        "actual_price":    int(row.get("actual_price") or 0) if has_offer else 0,
        "end_date":        end_date_str if has_offer else "",
        "description":     row.get("offer_description") or "",
        "keywords":        keywords,
        "is_category_13":  is_category_13,
    }

    doc["offer_image"]  = _offer_img_url(row.get("offer_image")  or "")
    doc["product_img1"] = _offer_img_url(row.get("product_img1") or "")
    doc["product_img2"] = _offer_img_url(row.get("product_img2") or "")
    doc["product_img3"] = _offer_img_url(row.get("product_img3") or "")

    if lat is not None and lng is not None:
        try:
            doc["location"] = [float(lat), float(lng)]
        except (ValueError, TypeError):
            pass

    return doc

def _bulk_import(collection: str, docs: list, batch_size: int = 1000) -> int:
    """
    Batch upsert documents to a Typesense collection.
    
    Splits the document list into batches to prevent memory/request size issues.
    Each batch is upser'd with action='upsert' (insert or update).
    
    Args:
        collection (str): Name of Typesense collection (e.g., 'shops', 'products').
        docs (list): List of document dicts to import.
        batch_size (int): Documents per batch (default 1000). Adjust if hitting size limits.
    
    Returns:
        int: Total number of successfully upserted documents.
    
    Note:
        Logs failures for first 3 documents in each failed batch.
        Continues on error — partial imports are allowed.
    
    Example:
        >>> docs = [{'id': '1', 'name': 'Shop A'}, {'id': '2', 'name': 'Shop B'}]
        >>> success = _bulk_import('shops', docs, batch_size=500)
        >>> print(f"Imported {success} docs")
    """
    if not docs:
        return 0
    
    total_success = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        try:
            result = client.collections[collection].documents.import_(
                batch, {"action": "upsert"}
            )
            success = sum(1 for r in result if r.get("success", False))
            total_success += success
            
            # Log failures
            failures = [r for r in result if not r.get("success")]
            if failures:
                for f in failures[:3]:  # Log first 3 failures
                    logger.warning(f"Upsert failed: {f}")
        except Exception as e:
            logger.error(f"Batch import to {collection} failed: {e}")
    
    return total_success




def create_schema(force: bool = False):
    """
    Create Typesense collection schemas for all four data types.
    
    Manages four collections:
      1. shops: Local businesses with ratings and offers
      2. jobs: Job vacancies with experience and benefits
      3. products: Product listings with offers
      4. services: Services (plumbing, taxi, etc.) with offers
    
    Args:
        force (bool): If True, deletes existing collections before recreating.
                      If False (default), skips creation if collection already exists.
                      Use force=True only for development/testing.
    
    Returns:
        bool: True if all schemas created/verified successfully, False otherwise.
    
    Behavior:
        - Each collection has a matching SCHEMA constant (e.g., SHOP_SCHEMA)
        - Geo-enabled collections include 'location' as geopoint field
        - Facetable fields (category, city, etc.) speed up filters
        - Optional fields use optional=True to allow partial documents
    
    Example:
        >>> if create_schema(force=False):
        ...     print("Schemas ready")
        ... else:
        ...     print("Failed to create schemas")
    """
    try:
        # ── Handle all four collections ───────────────────────────────────────
        collections = [
            ("shops",    SHOP_SCHEMA),
            ("jobs",     JOB_SCHEMA),
            ("products", PRODUCT_SCHEMA),
            ("services", SERVICE_SCHEMA),
        ]

        for name, schema in collections:
            if force:
                try:
                    client.collections[name].delete()
                    logger.info(f"Deleted existing '{name}' collection (force=True)")
                except Exception:
                    logger.info(f"No existing '{name}' collection to delete")
            else:
                logger.info(f"Skipping deletion of '{name}' (force=False)")

            try:
                client.collections[name].retrieve()
                logger.info(
                    f"Collection '{name}' already exists — "
                    f"skipping creation (use force=True to recreate)"
                )
                continue
            except Exception:
                pass  # Collection doesn't exist, safe to create

            client.collections.create(schema)
            logger.info(f"Schema '{name}' created successfully")

        return True
    except Exception as e:
        logger.error(f"Failed to create schema: {e}")
        return False


def sync_shops(batch_size: int = 1000):
    """
    Sync shops from database to Typesense collection.
    
    Uses batched fetching (LIMIT/OFFSET) to prevent memory spikes with 100k+ shops.
    Each batch is processed, documents built, and upserted in a single call.
    
    Args:
        batch_size (int): Number of shops per batch (default 1000).
                         Lower values reduce memory footprint; higher values are faster.
    
    Returns:
        bool: True if at least one shop was imported, False otherwise.
    
    Key features:
        - Filters for active shops (status=1) and active subscribers only
        - Includes ratings and review counts in each document
        - Builds keywords from name, category, synonyms, city, and offers
        - Logs progress every batch with success/failure counts and GPS coverage
    
    Database query: Joins shop_details, shop_address, categories, reviews, and offers.
    
    Example:
        >>> if sync_shops(batch_size=500):
        ...     print("Shops synced successfully")
    """
    try:
        logger.info("Fetching shops from database (batched)...")
        
        # FIX: Single joined query with ratings — no separate fetch_all
        # Reduces from 2 queries to 1, and includes ratings inline
        offset = 0
        total_imported = 0
        
        while True:
            batch = fetch_all(f"""
                SELECT
                    sd.id,
                    sd.name,
                    sd.phone,
                    sd.shoplogo,
                    sd.status,
                    sd.category_id,
                    sd.subcategory_id,
                    sa.city,
                    sa.latitude,
                    sa.longitude,
                    sa.arearoadname,
                    sa.nearbylandmark,
                    c.categoriesname                                    AS category,
                    s.subcategoryname                                   AS subcategory,
                    ROUND(AVG(r.rating), 1)                             AS avg_rating,
                    COUNT(DISTINCT r.id)                                AS review_count,
                    GROUP_CONCAT(
                        DISTINCT r.review
                        ORDER BY r.created_at DESC
                        SEPARATOR ' | '
                    )                                                   AS review_texts,
                    GROUP_CONCAT(
                        DISTINCT o.offer_heading
                        ORDER BY o.created_at DESC
                        SEPARATOR ' | '
                    )                                                   AS offer_text
                FROM shop_details sd

                INNER JOIN users u
                    ON  u.id                = sd.partner_id
                    AND u.subscriber_status = 1

                INNER JOIN shop_address sa
                    ON  sa.shop_id    = sd.id
                    AND sa.is_default = 1

                INNER JOIN categories c
                    ON  c.id = sd.category_id

                LEFT JOIN subcategories s
                    ON  s.id = sd.subcategory_id

                LEFT JOIN reviews r
                    ON  r.shop_id = sd.id

                LEFT JOIN offer o
                    ON  o.shop_id  = sd.id
                    AND o.status   = 1
                    AND o.end_date >= CURDATE()

                WHERE sd.status = 1

                GROUP BY
                    sd.id,
                    sd.name,
                    sd.phone,
                    sd.status,
                    sd.category_id,
                    sd.subcategory_id,
                    sa.city,
                    sa.latitude,
                    sa.longitude,
                    sa.arearoadname,
                    sa.nearbylandmark,
                    c.categoriesname,
                    s.subcategoryname

                LIMIT {batch_size} OFFSET {offset}
            """)
            
            if not batch:
                break
            
            logger.info(f"Processing batch: offset={offset}, size={len(batch)}")
            documents = []
            shops_with_location = 0
            
            for shop in batch:
                offer_text   = shop.get("offer_text")   or ""
                review_texts = shop.get("review_texts") or ""
                subcategory  = shop.get("subcategory")  or ""
                category     = shop.get("category")    or ""

                keywords = " ".join(filter(None, [
                    shop.get("name"),
                    category,
                    subcategory,
                    shop.get("city"),
                    shop.get("arearoadname"),
                    shop.get("nearbylandmark"),
                    offer_text,
                    review_texts,
                ]))

                tags = " ".join(filter(None, [
                    category, subcategory, shop.get("city")
                ]))

                doc = {
                    "id":           str(shop["id"]),
                    "name":         shop.get("name")           or "",
                    "phone":        shop.get("phone")           or "",
                    "logo":         shop.get("shoplogo")        or "",
                    "city":         shop.get("city")            or "",
                    "address":      shop.get("arearoadname")    or "",
                    "landmark":     shop.get("nearbylandmark")  or "",
                    "category":     category,
                    "subcategory":  subcategory,
                    "keywords":     keywords,
                    "tags":         tags,
                    "has_offer":    bool(offer_text.strip()),
                    "offer_text":   offer_text,
                    "offers":       offer_text,
                    "review_texts": review_texts,
                    "rating":       float(shop.get("avg_rating")   or 0.0),
                    "review_count": int(shop.get("review_count")   or 0),
                }
                
                lat = shop.get("latitude")
                lng = shop.get("longitude")
                if lat is not None and lng is not None:
                    try:
                        doc["location"] = [float(lat), float(lng)]
                        shops_with_location += 1
                    except (ValueError, TypeError):
                        pass
                
                documents.append(doc)
            
            if documents:
                logger.info(f"Importing {len(documents)} shops...")
                result = client.collections["shops"].documents.import_(
                    documents, {"action": "upsert"}
                )
                
                success = sum(1 for r in result if r.get("success", False))
                fail    = len(result) - success
                total_imported += success
                
                logger.info(f"Batch result: {success} succeeded, {fail} failed, {shops_with_location} with GPS")
                
                for f in [r for r in result if not r.get("success")][:3]:
                    logger.warning(f"Failure: {f}")
            
            offset += batch_size
        
        logger.info(f"Total imported: {total_imported} shops")
        return total_imported > 0

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return False


def sync_products(batch_size: int = 1000) -> bool:
    """
    Sync products from database to Typesense collection.
    
    Creates one document per product-shop pair via the offers table.
    Only syncs products where the user has subscriber_status = 1.
    
    Args:
        batch_size (int): Number of products per batch (default 1000).
    
    Returns:
        bool: True if at least one product was imported, False otherwise.
    
    Key features:
        - Filters for active offers and non-expired end_dates
        - Composite ID (p_product_id_shop_id) prevents duplicates
        - Includes offer details only if offer is currently active
        - Supports geo-search via location field
    
    Database query: Joins products, offers, shop_details, and shop_address.
    
    Example:
        >>> if sync_products(batch_size=1000):
        ...     print("Products synced successfully")
    """
    try:
        logger.info("Fetching products from database (batched)...")
        offset = 0
        total_imported = 0

        while True:
            batch = fetch_all(f"""
                SELECT
                    p.id                                AS product_id,
                    p.product_name,
                    p.user_id,
                    sd.id                               AS shop_id,
                    sd.name                             AS shop_name,
                    sd.shoplogo                         AS shop_logo,
                    sd.phone                            AS shop_phone,
                    sa.city,
                    sa.latitude,
                    sa.longitude,
                    c.categoriesname                    AS category,
                    s.subcategoryname                   AS subcategory,
                    o.id                                AS offer_id,
                    o.offer_heading,
                    o.offer_price,
                    o.actual_price,
                    o.end_date,
                    o.description                       AS offer_description,
                    o.status                            AS offer_status,
                    o.offer_image,
                    o.product_img1,
                    o.product_img2,
                    o.product_img3
                FROM products p
                INNER JOIN users u
                    ON  u.id                = p.user_id
                    AND u.subscriber_status = 1
                INNER JOIN offer o
                    ON  o.product_id        = p.id
                INNER JOIN shop_details sd
                    ON  sd.id               = o.shop_id
                    AND sd.status           = 1
                INNER JOIN shop_address sa
                    ON  sa.shop_id          = sd.id
                    AND sa.is_default       = 1
                LEFT JOIN categories c
                    ON  c.id                = sd.category_id
                LEFT JOIN subcategories s
                    ON  s.id                = sd.subcategory_id
                LIMIT {batch_size} OFFSET {offset}
            """)

            if not batch:
                break

            logger.info(f"Processing product batch: offset={offset}, size={len(batch)}")
            documents = []
            products_with_location = 0

            for row in batch:
                doc = build_product_doc(row)
                if doc:
                    if doc.get("location"):
                        products_with_location += 1
                    documents.append(doc)

            if documents:
                logger.info(f"Importing {len(documents)} product docs...")
                result = client.collections["products"].documents.import_(
                    documents, {"action": "upsert"}
                )
                success = sum(1 for r in result if r.get("success", False))
                fail    = len(result) - success
                total_imported += success
                logger.info(
                    f"Product batch: {success} succeeded, "
                    f"{fail} failed, {products_with_location} with GPS"
                )
                for f in [r for r in result if not r.get("success")][:3]:
                    logger.warning(f"Product failure: {f}")

            offset += batch_size

        logger.info(f"Total products imported: {total_imported}")
        return total_imported > 0

    except Exception as e:
        logger.error(f"Product sync failed: {e}")
        return False


def sync_services(batch_size: int = 1000) -> bool:
    """
    Sync services from database to Typesense collection.
    
    Creates one document per service-shop pair via the offers table.
    Supports two location sources based on offer category:
      - category_id = 13 (home services): Uses user_address for location
      - Others: Uses shop_address for location
    
    Args:
        batch_size (int): Number of services per batch (default 1000).
    
    Returns:
        bool: True if at least one service was imported, False otherwise.
    
    Key features:
        - Filters for active offers and non-expired end_dates
        - Composite ID (s_service_id_shop_id) prevents duplicates
        - Smart location selection based on service category (is_category_13 flag)
        - Home service categories show provider's location, not shop's
    
    Database query: Joins service, offers, shop_details, shop_address, and user_address.
    
    Example:
        >>> if sync_services(batch_size=1000):
        ...     print("Services synced successfully")
    """
    try:
        logger.info("Fetching services from database (batched)...")
        offset = 0
        total_imported = 0

        while True:
            batch = fetch_all(f"""
                SELECT
                    sv.id                               AS service_id,
                    sv.service_name,
                    sv.user_id,
                    sd.id                               AS shop_id,
                    sd.name                             AS shop_name,
                    sd.shoplogo                         AS shop_logo,
                    sd.phone                            AS shop_phone,
                    o.id                                AS offer_id,
                    o.category_id                       AS offer_category_id,
                    o.offer_heading,
                    o.offer_price,
                    o.actual_price,
                    o.end_date,
                    o.description                       AS offer_description,
                    o.status                            AS offer_status,
                    o.offer_image,
                    o.product_img1,
                    o.product_img2,
                    o.product_img3,
                    c.categoriesname                    AS category,
                    s.subcategoryname                   AS subcategory,
                    ua.latitude                         AS ua_latitude,
                    ua.longitude                        AS ua_longitude,
                    ua.city                             AS ua_city,
                    ua.phone                            AS ua_phone,
                    sa.latitude                         AS sa_latitude,
                    sa.longitude                        AS sa_longitude,
                    sa.city                             AS sa_city
                FROM service sv
                INNER JOIN users u
                    ON  u.id                = sv.user_id
                    AND u.subscriber_status = 1
                INNER JOIN offer o
                    ON  o.service_id        = sv.id
                INNER JOIN shop_details sd
                    ON  sd.id               = o.shop_id
                    AND sd.status           = 1
                LEFT JOIN shop_address sa
                    ON  sa.shop_id          = sd.id
                    AND sa.is_default       = 1
                LEFT JOIN user_address ua
                    ON  ua.user_id          = sv.user_id
                    AND o.category_id       = 13
                LEFT JOIN categories c
                    ON  c.id                = sd.category_id
                LEFT JOIN subcategories s
                    ON  s.id                = sd.subcategory_id
                LIMIT {batch_size} OFFSET {offset}
            """)

            if not batch:
                break

            logger.info(f"Processing service batch: offset={offset}, size={len(batch)}")
            documents = []
            services_with_location = 0

            for row in batch:
                doc = build_service_doc(row)
                if doc: # ← add has_offer check
                    if doc.get("location"):
                        services_with_location += 1
                    documents.append(doc)

            if documents:
                logger.info(f"Importing {len(documents)} service docs...")
                result = client.collections["services"].documents.import_(
                    documents, {"action": "upsert"}
                )
                success = sum(1 for r in result if r.get("success", False))
                fail    = len(result) - success
                total_imported += success
                logger.info(
                    f"Service batch: {success} succeeded, "
                    f"{fail} failed, {services_with_location} with GPS"
                )
                for f in [r for r in result if not r.get("success")][:3]:
                    logger.warning(f"Service failure: {f}")

            offset += batch_size

        logger.info(f"Total services imported: {total_imported}")
        return total_imported > 0

    except Exception as e:
        logger.error(f"Service sync failed: {e}")
        return False


def verify_geo():

    """
    Correct Typesense 27.1 geo syntax:
      sort_by:   location(lat, lng):asc
      filter_by: location:(lat, lng, radius km)
    """
    logger.info("Verifying geo search (Typesense 27.1 syntax)...")

    # Geo sort
    try:
        r = client.collections["shops"].documents.search({
            "q": "*",
            "query_by": "name",
            "per_page": 1,
            "sort_by": "location(13.0776, 80.2917):asc"   # ← correct format
        })
        logger.info(f"Geo sort OK — {r['found']} docs")
    except Exception as e:
        logger.error(f"Geo sort FAILED: {e}")

    # Geo filter
    try:
        r = client.collections["shops"].documents.search({
            "q": "*",
            "query_by": "name",
            "per_page": 1,
            "filter_by": "location:(13.0776, 80.2917, 500 km)"  # ← correct format
        })
        logger.info(f"Geo filter OK — {r['found']} shops within 500 km of Chennai")
    except Exception as e:
        logger.error(f"Geo filter FAILED: {e}")


def health_check():
    try:
        client.operations.is_healthy()
        logger.info("Typesense is healthy")
        return True
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False


def setup(force: bool = False):
    from sync_manage import sync_all_jobs
    
    logger.info("=" * 60)
    logger.info("TYPESENSE SETUP")
    logger.info("=" * 60)

    logger.info("1. Checking connectivity...")
    if not health_check():
        return False

    logger.info("2. Creating schema...")
    if not create_schema(force=force):
        return False

    logger.info("3. Syncing shops...")
    if not sync_shops():
        return False

    logger.info("4. Syncing jobs...")
    sync_all_jobs()  # non-fatal — log warning if fails

    logger.info("5. Syncing products...")
    sync_products()  # non-fatal — log warning if fails

    logger.info("6. Syncing services...")
    sync_services()  # non-fatal — log warning if fails

    logger.info("7. Verifying geo search...")
    verify_geo()

    logger.info("SETUP COMPLETE")
    return True

if __name__ == "__main__":
    import sys
    from logging_config import configure_logging
    configure_logging()
    
    # Use force=True only when you explicitly want to recreate the index
    # Default is force=False for safety
    sys.exit(0 if setup(force=True) else 1)


     