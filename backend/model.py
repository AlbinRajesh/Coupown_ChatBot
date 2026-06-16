"""
models.py
─────────
All Pydantic request/response models + one central response builder.

Rules:
  - Every API response goes through build_response() — no raw dicts in handlers
  - SearchResponse is the single shape for ALL search endpoints
  - Optional fields use None, never missing keys
  - No handler can return a wrong key — structure enforced here
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class SearchRequest(BaseModel):
    query:    str           = Field(..., min_length=1, max_length=500)
    userLat:  Optional[float] = Field(None, ge=-90,   le=90)
    userLng:  Optional[float] = Field(None, ge=-180,  le=180)
    radiusKm: int           = Field(25,  ge=1,        le=500)

    @model_validator(mode="after")
    def validate_coords(self):
        if (self.userLat is None) != (self.userLng is None):
            raise ValueError("Provide both userLat and userLng, or neither")
        return self


class JobSearchRequest(BaseModel):
    query:    str           = Field("",  max_length=500)
    userLat:  Optional[float] = Field(None, ge=-90,   le=90)
    userLng:  Optional[float] = Field(None, ge=-180,  le=180)
    radiusKm: int           = Field(25,  ge=1,        le=500)
    limit:    int           = Field(20,  ge=1,        le=100)

    @model_validator(mode="after")
    def validate_coords(self):
        if (self.userLat is None) != (self.userLng is None):
            raise ValueError("Provide both userLat and userLng, or neither")
        return self


class ChatMessage(BaseModel):
    role:    str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    userLat:  Optional[float] = Field(None, ge=-90,  le=90)
    userLng:  Optional[float] = Field(None, ge=-180, le=180)
    radiusKm: int             = Field(25,  ge=1,     le=500)


class SmartRequest(BaseModel):
    query:    str                      = Field(..., min_length=1, max_length=500)
    userLat:  Optional[float]          = Field(None, ge=-90,  le=90)
    userLng:  Optional[float]          = Field(None, ge=-180, le=180)
    radiusKm: int                      = Field(25,  ge=1,     le=500)
    messages: Optional[List[ChatMessage]] = None


# ═══════════════════════════════════════════════════════════════════════════════
# RESULT ITEM MODELS
# These define the shape of individual items inside results[]
# ═══════════════════════════════════════════════════════════════════════════════

class OfferItem(BaseModel):
    """Single offer attached to a shop result."""
    offer_heading: str            = ""
    offer_price:   Optional[int]  = None
    actual_price:  Optional[int]  = None
    start_date:    str            = ""
    end_date:      str            = ""
    description:   str            = ""


class ShopResult(BaseModel):
    id:              int
    name:            str            = ""
    phone:           str            = ""
    logo:            str            = ""
    city:            str            = ""
    arearoadname:    str            = ""
    nearbylandmark:  str            = ""
    latitude:        Optional[float] = None
    longitude:       Optional[float] = None
    rating:          float          = 0.0
    review_count:    int            = 0
    category:        str            = ""
    subcategory:     str            = ""
    distance_km:     Optional[float] = None
    offers:          List[OfferItem] = []


class JobResult(BaseModel):
    id:          int
    shop_id:     Any    = ""
    shop_name:   str    = ""
    shop_logo:   str    = ""
    position:    str    = ""
    job_type:    str    = ""
    experience:  str    = ""
    description: str    = ""
    city:        str    = ""
    phone:       str    = ""
    latitude:    Optional[float] = None
    longitude:   Optional[float] = None
    distance_km: Optional[float] = None


class ProductResult(BaseModel):
    id:            str            = ""
    product_name:  str            = ""
    shop_id:       str            = ""
    name:          str            = ""      # shop name
    logo:          str            = ""      # shop logo
    phone:         str            = ""      # shop phone
    category:      str            = ""
    subcategory:   str            = ""
    city:          str            = ""
    offer_id:      str            = ""
    has_offer:     bool           = False
    offer_heading: str            = ""
    offer_price:   int            = 0
    actual_price:  int            = 0
    end_date:      str            = ""
    description:   str            = ""
    latitude:      Optional[float] = None
    longitude:     Optional[float] = None
    distance_km:   Optional[float] = None


class ServiceResult(BaseModel):
    id:             str            = ""
    service_name:   str            = ""
    shop_id:        str            = ""
    name:           str            = ""     # shop name
    logo:           str            = ""     # shop logo
    phone:          str            = ""     # shop phone
    category:       str            = ""
    subcategory:    str            = ""
    city:           str            = ""
    offer_id:       str            = ""
    has_offer:      bool           = False
    offer_heading:  str            = ""
    offer_price:    int            = 0
    actual_price:   int            = 0
    end_date:       str            = ""
    description:    str            = ""
    is_category_13: bool           = False
    latitude:       Optional[float] = None
    longitude:      Optional[float] = None
    distance_km:    Optional[float] = None


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED SEARCH RESPONSE
# Every search endpoint returns this exact shape — no exceptions.
# ═══════════════════════════════════════════════════════════════════════════════

class SearchResponse(BaseModel):
    """
    The single response shape for ALL search endpoints.

    Flags explain what kind of result this is:
      is_job_search        → results[] contains JobResult items
      is_exact_match       → single result from name lookup
      is_offer_search      → general offer search results
      is_shop_offer_search → offer lookup for a specific named shop
      is_product_search    → results[] contains ProductResult items
      is_service_search    → results[] contains ServiceResult items
      no_location          → user hasn't shared location; results are rating-based
      has_offers           → used only for shop-specific offer lookup
    """
    success:              bool
    message:              str            = ""
    intent_label:         str            = ""

    # Search type flags — exactly one should be True per response
    is_job_search:        bool           = False
    is_exact_match:       bool           = False
    is_offer_search:      bool           = False
    is_shop_offer_search: bool           = False
    is_product_search:    bool           = False
    is_service_search:    bool           = False

    # State flags
    no_location:          bool           = False
    has_offers:           Optional[bool] = None   # None = not applicable

    # Results
    total_results:        int            = 0
    results:              List[Any]      = []
    jobs:                 List[Any]      = []      # related jobs shown alongside shops
    radius_used_km:       int            = 0


class ChatResponse(BaseModel):
    success: bool
    reply:   str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# INTENT MODEL
# Structured output from intent.py — passed to every handler
# ═══════════════════════════════════════════════════════════════════════════════

class ParsedIntent(BaseModel):
    """
    Structured intent extracted from user query.
    Passed from intent.py → handlers.py → search.py
    """
    intent:         str        = "other"    # shop|job|product|service|offer|other
    search_type:    str        = "general"  # general|specific|category
    keywords:       List[str]  = []
    category:       str        = ""         # matched DB category/subcategory name
    category_names: List[str]  = []         # all parent category names from DB
    name:           str        = ""         # extracted business/job name
    radius_km:      int        = 0          # user-specified radius (0 = use default)
    sort_by_rating: bool       = False
    casual_type:    str        = ""  


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE BUILDER
# The ONLY way to create a SearchResponse in handlers.
# Enforces consistent shape. No handler builds dicts manually.
# ═══════════════════════════════════════════════════════════════════════════════

def build_response(
    *,
    success:              bool,
    message:              str,
    intent_label:         str            = "",
    results:              Optional[List[Any]] = None,
    jobs:                 Optional[List[Any]] = None,
    radius_used_km:       int            = 0,
    total_results:        Optional[int]  = None,

    # Search type flags — pass only the one that applies
    is_job_search:        bool           = False,
    is_exact_match:       bool           = False,
    is_offer_search:      bool           = False,
    is_shop_offer_search: bool           = False,
    is_product_search:    bool           = False,
    is_service_search:    bool           = False,

    # State flags
    no_location:          bool           = False,
    has_offers:           Optional[bool] = None,
) -> SearchResponse:
    """
    Central response builder. Every handler calls this.

    total_results defaults to len(results) if not provided.
    This prevents total_results=5 with results=[] type bugs.
    """
    results = results or []   
    jobs    = jobs    or []   

    return SearchResponse(
        success              = success,
        message              = message,
        intent_label         = intent_label,
        results              = results,
        jobs                 = jobs,
        radius_used_km       = radius_used_km,
        total_results        = total_results if total_results is not None else len(results),
        is_job_search        = is_job_search,
        is_exact_match       = is_exact_match,
        is_offer_search      = is_offer_search,
        is_shop_offer_search = is_shop_offer_search,
        is_product_search    = is_product_search,
        is_service_search    = is_service_search,
        no_location          = no_location,
        has_offers           = has_offers,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STANDARD ERROR RESPONSES
# Pre-built responses for common failure cases.
# Handlers use these instead of building error dicts manually.
# ═══════════════════════════════════════════════════════════════════════════════

def no_location_response(intent_label: str, flag_kwargs: Dict) -> SearchResponse:
    """User hasn't shared location. Returned before any search attempt."""
    return build_response(
        success       = False,
        message       = "Share your location to find results nearby.",
        intent_label  = intent_label,
        no_location   = True,
        radius_used_km= 0,
        **flag_kwargs,
    )


def no_results_response(
    query: str,
    radius_km: int,
    intent_label: str,
    flag_kwargs: Dict,
) -> SearchResponse:
    """Search ran but found nothing."""
    return build_response(
        success       = False,
        message       = f"No results found for '{query}' within {radius_km}km.",
        intent_label  = intent_label,
        radius_used_km= radius_km,
        **flag_kwargs,
    )


def not_found_response(
    name: str,
    intent_label: str,
    flag_kwargs: Dict,
) -> SearchResponse:
    """Exact name lookup returned nothing."""
    return build_response(
        success      = False,
        message      = f"No listing found for '{name}' in this area.",
        intent_label = intent_label,
        is_exact_match=True,
        **flag_kwargs,
    )


def timeout_response() -> SearchResponse:
    """Search timed out."""
    return build_response(
        success = False,
        message = "Search timed out. Please try again.",
    )


def error_response() -> SearchResponse:
    """Unexpected error — shown to user."""
    return build_response(
        success = False,
        message = "Something went wrong. Please try again.",
    )