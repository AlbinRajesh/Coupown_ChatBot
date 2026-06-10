"""
chat_context.py
───────────────
Builds the [DATA_BLOCK] string injected into chat system prompts.

Fixes from audit:
  1. _job_context: keywords with empty strings now filtered before Typesense call
  2. offer intent added — chat now has context for offer queries
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from model import ParsedIntent
from search import (
    search_jobs_typesense,
    search_products_typesense,
    search_services_typesense,
    search_shops_by_rating,
    search_shops_by_offer,
    search_shops_parallel,
    get_batch_shop_offers,
)
from constants import (
    CHAT_CONTEXT_LIMIT_SHOP,
    CHAT_CONTEXT_LIMIT_OFFER,
    CHAT_CONTEXT_LIMIT_PRODUCT,
    CHAT_CONTEXT_LIMIT_SERVICE,
    CHAT_CONTEXT_LIMIT_JOB,
    CHAT_CONTEXT_TIMEOUT,
)

logger = logging.getLogger(__name__)


def _clean_keywords(keywords: List[str], fallback: str = "*") -> List[str]:
    """
    Filter empty/whitespace strings from keyword list.
    
    Always returns a non-empty list — never sends blank string to Typesense.
    This fixes a bug where parsed.keywords = [''] is truthy in Python but
    represents an empty search to Typesense.
    
    Args:
        keywords (List[str]): Keyword list (may contain empty strings).
        fallback (str): Fallback keyword if all are empty (default '*' for match-all).
    
    Returns:
        List[str]: Non-empty list of cleaned keywords. Always has at least one element.
    
    Example:
        >>> _clean_keywords(['biryani', '', '  '], fallback='*')
        ['biryani']
        >>> _clean_keywords(['', '  ', None], fallback='*')
        ['*']
    """
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    return cleaned if cleaned else [fallback]


async def build_chat_context(
    query:     str,
    parsed:    ParsedIntent,
    user_lat:  Optional[float],
    user_lng:  Optional[float],
    radius_km: int,
) -> str:
    """
    Build a [DATA_BLOCK] string to inject into the chat system prompt.
    Returns "" on any failure — chat always works even without context.
    """
    intent = parsed.intent

    try:
        if intent == "product":
            return await _product_context(parsed, user_lat, user_lng, radius_km)

        if intent == "service":
            return await _service_context(parsed, user_lat, user_lng, radius_km)

        if intent == "job":
            return await _job_context(parsed, query, user_lat, user_lng)

        if intent == "offer":
            return await _offer_context(parsed, user_lat, user_lng, radius_km)

        if intent == "shop" and user_lat is None:
            return await _rating_context(parsed, query)

        if intent == "shop" and user_lat is not None:
            return await _geo_context(parsed, query, user_lat, user_lng, radius_km)

    except Exception as e:
        logger.warning("build_chat_context failed for intent=%s: %s", intent, e)

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Context builders — one per intent type
# ─────────────────────────────────────────────────────────────────────────────

async def _product_context(
    parsed:   ParsedIntent,
    user_lat: Optional[float],
    user_lng: Optional[float],
    radius_km: int,
) -> str:
    keywords = _clean_keywords(parsed.keywords)
    result   = await asyncio.wait_for(
        asyncio.to_thread(
            search_products_typesense,
            tuple(keywords), user_lat, user_lng, radius_km, CHAT_CONTEXT_LIMIT_PRODUCT,
        ),
        timeout=CHAT_CONTEXT_TIMEOUT,
    )
    products = result["products"]
    if not products:
        return "\n\n[DATA_BLOCK]\nNo products found nearby.\n[END DATA_BLOCK]"

    lines = [
        f"- {p.get('product_name','')} | {p.get('name','')} | "
        f"{p.get('distance_km','?')}km | offer: {p.get('offer_heading','none')}"
        for p in products
    ]
    return "\n\n[DATA_BLOCK — products]\n" + "\n".join(lines) + "\n[END DATA_BLOCK]"


async def _service_context(
    parsed:   ParsedIntent,
    user_lat: Optional[float],
    user_lng: Optional[float],
    radius_km: int,
) -> str:
    keywords = _clean_keywords(parsed.keywords)
    result   = await asyncio.wait_for(
        asyncio.to_thread(
            search_services_typesense,
            tuple(keywords), user_lat, user_lng, radius_km, CHAT_CONTEXT_LIMIT_SERVICE, 
        ),
        timeout=CHAT_CONTEXT_TIMEOUT,
    )
    services = result["services"]
    if not services:
        return "\n\n[DATA_BLOCK]\nNo services found nearby.\n[END DATA_BLOCK]"

    lines = [
        f"- {s.get('service_name','')} | {s.get('name','')} | "
        f"{s.get('distance_km','?')}km | offer: {s.get('offer_heading','none')}"
        for s in services
    ]
    return "\n\n[DATA_BLOCK — services]\n" + "\n".join(lines) + "\n[END DATA_BLOCK]"


async def _job_context(
    parsed:   ParsedIntent,
    query:    str,
    user_lat: Optional[float],
    user_lng: Optional[float],
) -> str:
    # FIX: _clean_keywords filters [''] before it reaches Typesense
    # FIX: fallback order is now explicit — no operator precedence ambiguity
    raw      = parsed.keywords or ([query.strip()] if query.strip() else [])
    keywords = _clean_keywords(raw)

    result = await asyncio.wait_for(
        asyncio.to_thread(
            search_jobs_typesense,
            tuple(keywords), user_lat, user_lng, CHAT_CONTEXT_LIMIT_JOB,
        ),
         timeout=CHAT_CONTEXT_TIMEOUT,
    )
    jobs = result["jobs"]
    if not jobs:
        return "\n\n[DATA_BLOCK]\nNo active job vacancies found.\n[END DATA_BLOCK]"

    lines = [
        f"- {j.get('position','')} | {j.get('job_type','')} | "
        f"{j.get('shop_name','')} | {j.get('city','')}"
        for j in jobs
    ]
    return "\n\n[DATA_BLOCK — job vacancies]\n" + "\n".join(lines) + "\n[END DATA_BLOCK]"


async def _offer_context(
    parsed:   ParsedIntent,
    user_lat: Optional[float],
    user_lng: Optional[float],
    radius_km: int,
) -> str:
    """
    FIX: offer intent was missing — chat had no context for offer queries.
    Now fetches nearby shops with active offers so the LLM can name them.
    Falls back gracefully when no location is available.
    """
    if user_lat is None or user_lng is None:
        return "\n\n[DATA_BLOCK]\nUser has not shared location. Cannot find nearby offers.\n[END DATA_BLOCK]"

    final_radius = parsed.radius_km or radius_km

    result = await asyncio.wait_for(
    asyncio.to_thread(
        search_shops_by_offer,
        user_lat,
        user_lng,
        final_radius,
        parsed.category,
        CHAT_CONTEXT_LIMIT_OFFER,
            ),
        timeout=CHAT_CONTEXT_TIMEOUT,  
    )

    shops = result.get("shops", [])
    if not shops:
        return "\n\n[DATA_BLOCK]\nNo shops with active offers found nearby.\n[END DATA_BLOCK]"

    raw_offers = result.get("offers", {})
    lines = []
    for s in shops:
        sid        = s["id"]
        offers     = raw_offers.get(sid, [])
        offer_str  = ", ".join(
            o.get("offer_heading", "") for o in offers if o.get("offer_heading")
        ) or "none"
        dist = f"{s['distance_km']}km" if s.get("distance_km") is not None else "?"
        lines.append(
            f"- {s.get('name','')} | {dist} | {s.get('city','')} | offers: {offer_str}"
        )

    radius_used = result.get("radius_used_km", final_radius)
    return (
        f"\n\n[DATA_BLOCK — offers nearby, radius={radius_used}km]\n"
        + "\n".join(lines)
        + "\n[END DATA_BLOCK]"
    )


async def _rating_context(parsed: ParsedIntent, query: str) -> str:
    """No location — return top-rated shops."""
    raw     = parsed.keywords or ([query.strip()] if query.strip() else [])
    keyword = _clean_keywords(raw)[0]

    shops = await asyncio.wait_for(
        asyncio.to_thread(search_shops_by_rating, keyword, CHAT_CONTEXT_LIMIT_SHOP),
        timeout=CHAT_CONTEXT_TIMEOUT,
    )
    if not shops:
        return "\n\n[DATA_BLOCK]\nNo shops found. User has not shared location.\n[END DATA_BLOCK]"

    lines = [
        f"- {s.get('name','')} | {s.get('city','')} | rating {s.get('rating','?')}"
        for s in shops
    ]
    return "\n\n[DATA_BLOCK — top-rated, no location]\n" + "\n".join(lines) + "\n[END DATA_BLOCK]"


async def _geo_context(
    parsed:   ParsedIntent,
    query:    str,
    user_lat: float,
    user_lng: float,
    radius_km: int,
) -> str:
    """Location available — return nearby shops with their offers."""
    raw          = parsed.keywords or ([query.strip()] if query.strip() else [])
    keywords     = _clean_keywords(raw)
    final_radius = parsed.radius_km or radius_km

    result = await asyncio.wait_for(
    asyncio.to_thread(
        search_shops_parallel,
        tuple(keywords),
        parsed.category,
        user_lat,
        user_lng,
        final_radius,
        CHAT_CONTEXT_LIMIT_SHOP,  # ✅
    ),
        timeout=CHAT_CONTEXT_TIMEOUT,
    )

    shops = result["shops"]
    if not shops:
        return f"\n\n[DATA_BLOCK]\nNo shops found within {final_radius}km.\n[END DATA_BLOCK]"

    shop_ids     = [s["id"] for s in shops]
    batch_offers = await asyncio.to_thread(get_batch_shop_offers, shop_ids)

    lines = []
    for s in shops:
        offers    = batch_offers.get(s["id"], [])
        offer_str = ", ".join(
            o.get("offer_heading", "") for o in offers if o.get("offer_heading")
        ) or "none"
        dist = f"{s['distance_km']}km" if s.get("distance_km") is not None else "?"
        lines.append(
            f"- {s.get('name','')} | {dist} | {s.get('city','')} | offers: {offer_str}"
        )

    radius_used = result.get("radius_used_km", final_radius)
    return (
        f"\n\n[DATA_BLOCK — geo results, radius={radius_used}km]\n"
        + "\n".join(lines)
        + "\n[END DATA_BLOCK]"
    )