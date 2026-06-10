"""
handlers.py
───────────
Search intent handlers. One function per intent type.

Each handler:
  - Receives (parsed: ParsedIntent, req: SearchRequest)
  - Returns SearchResponse via build_response() — never a raw dict
  - Owns its own guard, primary search, fallback, enrichment, message

Handler routing lives in _handle_search() at the bottom of this file.
main.py calls only _handle_search() — nothing else from here.

Intent → Handler map:
  other            → _handle_other
  offer            → _handle_offer
  product          → _handle_product
  service          → _handle_service
  job              → _handle_job  (unified — covers exact + general)
  shop + specific  → _handle_exact_shop (only when is_valid_name)
  shop (general)   → _handle_shop
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

from model import (
    ParsedIntent,
    SearchRequest,
    SearchResponse,
    build_response,
    error_response,
    no_location_response,
    no_results_response,
    not_found_response,
    timeout_response,
)
from constants import (
    TYPESENSE_SEARCH_TIMEOUT,
    TYPESENSE_HARD_TIMEOUT,
    CHAT_CONTEXT_TIMEOUT,
    JOB_SEARCH_TIMEOUT,
    PRODUCT_SERVICE_TIMEOUT,
    OFFER_SEARCH_TIMEOUT,
)

from intent import is_valid_name
from search import (
    get_batch_shop_offers,
    search_job_by_title,
    search_jobs_typesense,
    search_shop_by_name,
    search_shops_by_offer,
    search_shops_by_rating,
    search_shops_parallel,
    search_products_typesense,
    search_services_typesense,
 
)
from enrichment import (
    enrich_shop,
    enrich_shops,
    smart_fallback,
    build_result_message,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# INTENT LABELS
# One dict — no scattered label strings across handlers.
# ═══════════════════════════════════════════════════════════════════════════════

_INTENT_LABELS: Dict[str, str] = {
    "shop":        "🔍 Searching nearby shops",
    "job":         "💼 Searching job vacancies",
    "product":     "🛒 Looking for products",
    "service":     "🔧 Looking for services",
    "offer":       "🏷️ Looking for offers",
    "shop_offer":  "🏷️ Shop offers",
    "exact_shop":  "🔍 Searching by name",
    "exact_job":   "💼 Searching job by title",
    "other":       "🔍 Searching nearby",
}


def _label(intent_key: str, category: str = "") -> str:
    """Return intent label, including category name for shop searches."""
    if intent_key == "shop" and category:
        return f"🔍 Looking for {category}"
    return _INTENT_LABELS.get(intent_key, "🔍 Searching nearby")


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _handle_other(parsed: ParsedIntent, req: SearchRequest) -> SearchResponse:
    """
    Casual query or unrecognised intent.
    Returns success=True with a helpful nudge — not an error state.
    """
    return build_response(
        success      = True,
        message      = "Looking for shops, services, or jobs nearby — what can I help you find?",
        intent_label = _label("other"),
    )


async def _handle_offer(parsed: ParsedIntent, req: SearchRequest) -> SearchResponse:

    # ── Path A: named shop ────────────────────────────────────────────────────
    if is_valid_name(parsed.name):
        shop = await asyncio.wait_for(
            asyncio.to_thread(search_shop_by_name, parsed.name, req.userLat, req.userLng),
            timeout=10.0,
        )
        if not shop:
            return not_found_response(
                name         = parsed.name,
                intent_label = _label("shop_offer"),
                flag_kwargs  = {"is_shop_offer_search": True},
            )

        enriched   = await asyncio.to_thread(enrich_shop, shop)
        has_offers = len(enriched.get("offers", [])) > 0
        message    = build_result_message([enriched], context="shop_offer")

        return build_response(
            success              = True,
            message              = message,
            intent_label         = _label("shop_offer"),
            results              = [enriched],
            is_shop_offer_search = True,
            is_exact_match       = True,
            has_offers           = has_offers,
        )

    # ── Path B: general / category offer search ───────────────────────────────
    if req.userLat is None or req.userLng is None:
        return no_location_response(
            intent_label = _label("offer"),
            flag_kwargs  = {"is_offer_search": True},
        )

    final_radius = parsed.radius_km or req.radiusKm   # ← move here

    _GENERIC_OFFER_WORDS = {"offers", "deals", "discount", "discounts", "sale", "promo"}
    _PRODUCT_LIKE_INTENTS = {"product"}
    has_specific_keywords = bool(
        parsed.keywords and
        not all(k.lower() in _GENERIC_OFFER_WORDS for k in parsed.keywords)
    )
    parent_categories = {
    "food & dining", "grocery,beauty & health", "fashions",
    "mobiles & electronics", "home & living furnitures",
    "electrical appliances", "services", "others",
    }
    category_is_parent_only = (
        parsed.category.lower() in parent_categories
        if parsed.category else False
    )

    
    if has_specific_keywords and (not parsed.category or category_is_parent_only):
        return build_response(
            success         = False,
            message         = f"No offers found for '{parsed.keywords[0]}'. Try 'offers nearby' to see all available offers.",
            intent_label    = _label("offer"),
            is_offer_search = True,
            radius_used_km  = final_radius,
    )
    offer_result = await asyncio.wait_for(
        asyncio.to_thread(
            search_shops_by_offer,
            user_lat      = req.userLat,
            user_lng      = req.userLng,
            radius_km     = final_radius,
            category_name = parsed.category,
            limit         = 5,
        ),
        timeout=OFFER_SEARCH_TIMEOUT,
    )

    shops = offer_result["shops"]
    if not shops:
        return build_response(
            success         = False,
            message         = offer_result.get("message") or f"No offers found within {final_radius}km.",
            intent_label    = _label("offer"),
            is_offer_search = True,
            radius_used_km  = offer_result.get("radius_used_km", final_radius),
        )

    raw_offers = offer_result["offers"]
    enriched   = [
        {
            **shop,
            "offers": [
                {
            "offer_heading": o.get("offer_heading", ""),
            "offer_price":   o.get("offer_price"),
            "actual_price":  o.get("actual_price"),
            "start_date":    str(o["start_date"]) if o.get("start_date") else "",
            "end_date":      str(o["end_date"])   if o.get("end_date")   else "",
            "description":   o.get("description", ""),
            "category_name": o.get("category_name", ""),
            "offer_image":   o.get("offer_image", ""),
            "product_img1":  o.get("product_img1", ""),
            "product_img2":  o.get("product_img2", ""),
            "product_img3":  o.get("product_img3", ""),
        }
                for o in raw_offers.get(shop["id"], [])
            ],
        }
        for shop in shops
    ]

    radius_used = offer_result.get("radius_used_km", final_radius)
    return build_response(
        success         = True,
        message         = build_result_message(enriched, context="offer", radius_used_km=radius_used),
        intent_label    = _label("offer"),
        results         = enriched,
        is_offer_search = True,
        radius_used_km  = radius_used,
    )


async def _handle_product(parsed: ParsedIntent, req: SearchRequest) -> SearchResponse:
    """
    Product intent handler.

    Primary:  search_products_typesense → normalised to shop+offers shape
    Fallback: smart_fallback → shop search with keyword relevance filter

    Both paths always return is_product_search=True.
    Both paths always return results in the same shop+offers shape so the
    frontend never needs to distinguish between search paths.
    """
    if req.userLat is None or req.userLng is None:
        return no_location_response(
            intent_label = _label("product"),
            flag_kwargs  = {"is_product_search": True},
        )

    keywords     = parsed.keywords or [req.query.strip().lower()]
    final_radius = parsed.radius_km or req.radiusKm
    specific     = keywords[0] if keywords else req.query.strip()

    products = (await asyncio.wait_for(
        asyncio.to_thread(
            search_products_typesense,
            tuple(keywords), req.userLat, req.userLng, final_radius, 6,
        ),
        timeout=PRODUCT_SERVICE_TIMEOUT,
    ))["products"]

    if products:
        # Normalise product docs → shop+offers shape for consistent frontend contract.
        # Raw product docs have offer fields at top level; frontend expects them
        # nested under "offers" array — same shape as enrich_shops() output.
        normalized = [
            {
                "id":          p.get("shop_id"),
                "name":        p.get("shop_name") or p.get("name", ""),
                "logo":  p.get("logo") or p.get("shop_logo", ""),
                "phone": p.get("phone") or p.get("shop_phone", ""),
                "city":        p.get("city", ""),
                "category":    p.get("category", ""),
                "subcategory": p.get("subcategory", ""),
                "distance_km": p.get("distance_km"),
                "latitude":    p.get("latitude"),
                "longitude":   p.get("longitude"),
                "offers": [{
                    "offer_image":   p.get("offer_image", ""),
                    "offer_heading": p.get("offer_heading", ""),
                    "offer_price":   p.get("offer_price"),
                    "actual_price":  p.get("actual_price"),
                    "end_date":      p.get("end_date", ""),
                    "start_date":    p.get("start_date", ""),
                    "description":   p.get("description", ""),
                    "category_name": p.get("category_name") or p.get("category", ""),
                }],
            }
            for p in products
        ]
        return build_response(
            success           = True,
            message           = build_result_message(normalized, context="product", specific_term=specific),
            intent_label      = _label("product"),
            results           = normalized,
            is_product_search = True,
            radius_used_km    = final_radius,
        )

    # ── Fallback: shop search with relevance filter ───────────────────────────
    # smart_fallback already returns enrich_shops() output — correct shape, no normalisation needed.
    fb = await asyncio.wait_for(
        asyncio.to_thread(
            smart_fallback, keywords, parsed.category,
            req.userLat, req.userLng, final_radius,
        ),
        timeout=PRODUCT_SERVICE_TIMEOUT,
    )

    if not fb.found:
        return no_results_response(
            query        = req.query,
            radius_km    = final_radius,
            intent_label = _label("product"),
            flag_kwargs  = {"is_product_search": True},
        )

    return build_response(
        success           = True,
        message           = build_result_message(
                                fb.shops, context="product_fallback",
                                specific_term=specific, radius_used_km=fb.radius_used_km,
                            ),
        intent_label      = _label("product"),
        results           = fb.shops,
        is_product_search = True,
        radius_used_km    = fb.radius_used_km,
    )

async def _handle_service(parsed: ParsedIntent, req: SearchRequest) -> SearchResponse:
    """
    Service intent handler.

    Primary:  search_services_typesense → normalised to shop+offers shape
    Fallback: smart_fallback → shop search with keyword relevance filter

    Both paths always return is_service_search=True.
    Both paths always return results in the same shop+offers shape so the
    frontend never needs to distinguish between search paths.
    """
    if req.userLat is None or req.userLng is None:
        return no_location_response(
            intent_label = _label("service"),
            flag_kwargs  = {"is_service_search": True},
        )

    keywords     = parsed.keywords or [req.query.strip().lower()]
    final_radius = parsed.radius_km or req.radiusKm
    specific     = keywords[0] if keywords else req.query.strip()

    raw_services = (await asyncio.wait_for(
        asyncio.to_thread(
            search_services_typesense,
            tuple(keywords), req.userLat, req.userLng, final_radius, 6,
        ),
        timeout=PRODUCT_SERVICE_TIMEOUT,
    ))["services"]

    if raw_services:
        # Normalise service docs → shop+offers shape for consistent frontend contract.
        # Raw service docs have offer fields at top level; frontend expects them
        # nested under "offers" array — same shape as enrich_shops() output.
        normalized = [
            {
                "id":          s.get("shop_id"),
                "name":        s.get("shop_name") or s.get("name", ""),
                "logo":  s.get("logo") or s.get("shop_logo", ""),
                "phone": s.get("phone") or s.get("shop_phone", ""),
                "city":        s.get("city", ""),
                "category":    s.get("category", ""),
                "subcategory": s.get("subcategory", ""),
                "distance_km": s.get("distance_km"),
                "latitude":    s.get("latitude"),
                "longitude":   s.get("longitude"),
                "offers": [{
                    "offer_image":   s.get("offer_image", ""),
                    "offer_heading": s.get("offer_heading", ""),
                    "offer_price":   s.get("offer_price"),
                    "actual_price":  s.get("actual_price"),
                    "end_date":      s.get("end_date", ""),
                    "start_date":    s.get("start_date", ""),
                    "description":   s.get("description", ""),
                    "category_name": s.get("category_name") or s.get("category", ""),
                }],
            }
            for s in raw_services
        ]
        return build_response(
            success           = True,
            message           = build_result_message(normalized, context="service", specific_term=specific),
            intent_label      = _label("service"),
            results           = normalized,
            is_service_search = True,
            radius_used_km    = final_radius,
        )

    # ── Fallback: shop search with relevance filter ───────────────────────────
    # smart_fallback already returns enrich_shops() output — correct shape, no normalisation needed.
    fb = await asyncio.wait_for(
        asyncio.to_thread(
            smart_fallback, keywords, parsed.category,
            req.userLat, req.userLng, final_radius,
        ),
        timeout=PRODUCT_SERVICE_TIMEOUT,
    )

    if not fb.found:
        return no_results_response(
            query        = req.query,
            radius_km    = final_radius,
            intent_label = _label("service"),
            flag_kwargs  = {"is_service_search": True},
        )

    # Fallback returns shop dicts from enrich_shops() — already correct shape.
    # Inject service_name so downstream consumers can identify what was searched.
    normalized_fallback = [
        {**shop, "service_name": specific}
        for shop in fb.shops
    ]
    return build_response(
        success           = True,
        message           = build_result_message(
                                normalized_fallback, context="service_fallback",
                                specific_term=specific, radius_used_km=fb.radius_used_km,
                            ),
        intent_label      = _label("service"),
        results           = normalized_fallback,
        is_service_search = True,
        radius_used_km    = fb.radius_used_km,
    )



async def _handle_exact_shop(parsed: ParsedIntent, req: SearchRequest) -> SearchResponse:
    """
    Exact shop lookup by name.
    Only reached when parsed.search_type == "specific" AND is_valid_name(parsed.name).
    Confidence-guarded in search.py — returns None if similarity < 0.60.
    """
    shop = await asyncio.wait_for(
        asyncio.to_thread(search_shop_by_name, parsed.name, req.userLat, req.userLng),
        timeout=10.0,
    )

    if not shop:
        return not_found_response(
            name         = parsed.name,
            intent_label = _label("exact_shop"),
            flag_kwargs  = {},
        )

    enriched = await asyncio.to_thread(enrich_shop, shop)

    return build_response(
        success        = True,
        message        = build_result_message([enriched], context="exact_shop"),
        intent_label   = _label("exact_shop"),
        results        = [enriched],
        is_exact_match = True,
    )


async def _handle_job(parsed: ParsedIntent, req: SearchRequest) -> SearchResponse:
    """
    Unified job handler — covers both exact and general job search.

    If parsed.name is a valid job title → exact lookup (search_job_by_title)
    Otherwise                           → general keyword search

    Jobs are NOT filtered by radius — sorted by distance only.
    Job seekers will travel; shop customers won't.
    """
    # ── Exact job lookup ──────────────────────────────────────────────────────
    if is_valid_name(parsed.name):
        job = await asyncio.wait_for(
            asyncio.to_thread(search_job_by_title, parsed.name, req.userLat, req.userLng),
            timeout=10.0,
        )
        if not job:
            return not_found_response(
                name         = parsed.name,
                intent_label = _label("exact_job"),
                flag_kwargs  = {"is_job_search": True},
            )

        return build_response(
            success        = True,
            message        = build_result_message([job], context="exact_job"),
            intent_label   = _label("exact_job"),
            results        = [job],
            is_job_search  = True,
            is_exact_match = True,
        )

    # ── General job search ────────────────────────────────────────────────────
    keywords = parsed.keywords or [req.query.strip().lower()]
    jobs     = (await asyncio.wait_for(
        asyncio.to_thread(
            search_jobs_typesense,
            tuple(keywords), req.userLat, req.userLng, 10,
        ),
        timeout=JOB_SEARCH_TIMEOUT,
    ))["jobs"]

    if not jobs:
        return no_results_response(
            query        = req.query,
            radius_km    = req.radiusKm,
            intent_label = _label("job"),
            flag_kwargs  = {"is_job_search": True},
        )

    return build_response(
        success       = True,
        message       = build_result_message(jobs, context="job"),
        intent_label  = _label("job"),
        results       = jobs,
        is_job_search = True,
    )


async def _handle_shop(parsed: ParsedIntent, req: SearchRequest) -> SearchResponse:
    """
    General shop search handler — two paths:

    Path A — No location: rating-based results + prompt to enable location
    Path B — Geo: parallel keyword search with category filter + related jobs

    Related jobs fetched only on Path B when results are found.
    (Old code fetched related jobs on every path including failures — wasted calls.)
    """
    keywords     = parsed.keywords or [req.query.strip().lower()]
    final_radius = parsed.radius_km or req.radiusKm

    # ── Path A: no location ───────────────────────────────────────────────────
    if req.userLat is None or req.userLng is None:
        shops = await asyncio.wait_for(
            asyncio.to_thread(search_shops_by_rating, keywords[0], 10),
            timeout=TYPESENSE_SEARCH_TIMEOUT,
        )
        if not shops:
            return build_response(
                success      = False,
                message      = "Share your location to find shops nearby.",
                intent_label = _label("shop", parsed.category),
                no_location  = True,
            )

        enriched = await asyncio.to_thread(enrich_shops, shops[:5])
        return build_response(
            success      = True,
            message      = build_result_message(enriched, context="shop_no_location"),
            intent_label = _label("shop", parsed.category),
            results      = enriched,
            no_location  = True,
        )

    # ── Path B: geo search ────────────────────────────────────────────────────
    result = await asyncio.wait_for(
        asyncio.to_thread(
            search_shops_parallel,
            tuple(keywords),
            parsed.category,
            req.userLat,
            req.userLng,
            final_radius,
            5,
        ),
        timeout=TYPESENSE_SEARCH_TIMEOUT,
    )

    shops       = result["shops"]
    radius_used = result.get("radius_used_km", final_radius)

    if not shops:
        return build_response(
            success        = False,
            message        = result.get("message") or f"No results found within {radius_used}km.",
            intent_label   = _label("shop", parsed.category),
            radius_used_km = radius_used,
        )

    enriched = await asyncio.to_thread(enrich_shops, shops)

    # Related jobs — only fetched when geo results were found
    related_jobs = (await asyncio.wait_for(
        asyncio.to_thread(
            search_jobs_typesense,
            tuple(keywords), req.userLat, req.userLng, 5,
        ),
         timeout=JOB_SEARCH_TIMEOUT,
    ))["jobs"]

    return build_response(
        success        = True,
        message        = build_result_message(enriched, context="shop", radius_used_km=radius_used),
        intent_label   = _label("shop", parsed.category),
        results        = enriched,
        jobs           = related_jobs,
        radius_used_km = radius_used,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCHER
# The only function main.py imports from this file.
# Routes parsed intent → correct handler.
# Zero business logic here — pure routing.
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_search(parsed: ParsedIntent, req: SearchRequest) -> SearchResponse:
    try:
        intent = parsed.intent

        if intent == "other":
            return await _handle_other(parsed, req)
        if intent == "offer":
            return await _handle_offer(parsed, req)
        if intent == "product":
            return await _handle_product(parsed, req)
        if intent == "service":
            return await _handle_service(parsed, req)
        if intent == "job":
            return await _handle_job(parsed, req)

        # intent == "shop"
        # Exact match when: type=specific AND name looks like a real business name
        # Extra guard: name must be 2+ words OR a known business-like token
        # (prevents single-word fallbacks like "food" hitting exact shop search)
        _SERVICE_SUBCATEGORIES = {
            "auto rickshaw", "taxi", "bike taxi", "tourist bus", "load vehicles",
            "vehicle rental", "plumbing services", "ac / tv services",
            "beautician", "catering services", "constructors / engi",
            "home services", "it $ services", "photographer",
        }
        if (
            parsed.category
            and parsed.category.lower() in _SERVICE_SUBCATEGORIES
            and not is_valid_name(parsed.name)
        ):
            logger.info(
                "Shop→Service reroute: category='%s' matched service subcategory",
                parsed.category,
            )
            return await _handle_service(parsed, req)

        # Single-word or short queries that look like names
        # but have no category match → treat as exact lookup, no fallback
        _query_words = req.query.strip().split()
        _looks_like_name = (
            parsed.search_type == "specific"
            and is_valid_name(parsed.name)
        )

        # Guard: any shop query with no category signal and not a known
        # general search → try exact name lookup first, never dump nearby shops.
        # Covers: "f12", "abc motors", "reema", "hotel aqeel nagercoil", etc.
        # Skips: "food nearby" (has category), "grocery store near me" (4+ words general)
        _no_category             = not parsed.category
        _no_known_shop_intent    = parsed.search_type not in ("general",) or _no_category
        _long_descriptive_query  = len(_query_words) >= 4

        _is_unknown_query = (
            _no_category
            and _no_known_shop_intent
            and not _long_descriptive_query
        )

        if _looks_like_name and len(parsed.name.strip().split()) >= 2:
            return await _handle_exact_shop(parsed, req)

        # Unknown query with no category → exact lookup only, no shop dump fallback
        if _is_unknown_query:
            shop = await asyncio.wait_for(
                asyncio.to_thread(
                    search_shop_by_name, req.query.strip(),
                    req.userLat, req.userLng
                ),
                timeout=10.0,
            )
            if shop:
                enriched = await asyncio.to_thread(enrich_shop, shop)
                return build_response(
                    success        = True,
                    message        = build_result_message([enriched], context="exact_shop"),
                    intent_label   = _label("exact_shop"),
                    results        = [enriched],
                    is_exact_match = True,
                )
            return not_found_response(
                name         = req.query.strip(),
                intent_label = _label("exact_shop"),
                flag_kwargs  = {},
            )

        return await _handle_shop(parsed, req)


    except asyncio.TimeoutError:
        logger.warning("Handler timeout: intent=%s query='%s'", parsed.intent, req.query[:40])
        return timeout_response()
    except Exception as exc:
        logger.error("Handler error: intent=%s error=%s", parsed.intent, exc, exc_info=True)
        return error_response()