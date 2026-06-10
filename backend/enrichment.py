"""
enrichment.py
─────────────
Post-search enrichment and shared fallback logic.

Responsibilities:
  - enrich_shops()      Attach offers to a list of shop results (one DB call)
  - enrich_shop()       Attach offers to a single shop result
  - smart_fallback()    Shared product/service → shop fallback (fixes copy-paste bugs)
  - build_result_message() Consistent human-readable summary line for all search paths

Design rules:
  - All offer data uses a single full shape (OfferShape) — no slim vs full inconsistency
  - smart_fallback() owns ALL fallback logic — handlers never duplicate it
  - Relevance filtering uses whole-word matching (not substring) — matches search.py
  - Every function is synchronous — callers use asyncio.to_thread() where needed
  - No Typesense calls here — this layer sits above search.py, below handlers.py
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from search import get_batch_shop_offers, search_shops_parallel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_FALLBACK_LIMIT = 5  # max shops returned from smart_fallback


# ─────────────────────────────────────────────────────────────────────────────
# Offer shape
#
# Previous code had two incompatible offer shapes:
#   "slim"  → {"heading": ..., "price": ...}            (dropped 4 fields)
#   "full"  → {"offer_heading": ..., "offer_price": ...} (correct)
#
# We always use the full shape. Frontend receives consistent offer objects
# regardless of which search path produced the result.
# ─────────────────────────────────────────────────────────────────────────────

def _format_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "offer_heading": offer.get("offer_heading") or "",
        "offer_price":   offer.get("offer_price"),
        "actual_price":  offer.get("actual_price"),
        "start_date":    str(offer["start_date"]) if offer.get("start_date") else "",
        "end_date":      str(offer["end_date"])   if offer.get("end_date")   else "",
        "description":   offer.get("description") or "",
        "category_name": offer.get("category_name") or "",
        "offer_image":   offer.get("offer_image") or "",
        "product_img1":  offer.get("product_img1") or "",
        "product_img2":  offer.get("product_img2") or "",
        "product_img3":  offer.get("product_img3") or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Shop enrichment
#
# Attaches formatted offers to shop dicts. Fetches all offers in ONE DB query
# regardless of how many shops are in the list.
# ─────────────────────────────────────────────────────────────────────────────

def enrich_shops(shops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fetch offers for all shops in a single DB query and attach them.

    Args:
        shops: List of shop dicts from search.py (_build_shop output).

    Returns:
        Same list with an "offers" key added to each shop.
        Shops with no offers get offers=[].

    Usage (in async handler):
        enriched = await asyncio.to_thread(enrich_shops, shops)
    """
    if not shops:
        return []

    shop_ids    = [s["id"] for s in shops]
    batch       = get_batch_shop_offers(shop_ids)   # one DB call

    return [
        {
            **shop,
            "offers": [_format_offer(o) for o in batch.get(shop["id"], [])],
        }
        for shop in shops
    ]


def enrich_shop(shop: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch and attach offers for a single shop.
    Convenience wrapper around enrich_shops() for exact-match paths.

    Usage (in async handler):
        enriched = await asyncio.to_thread(enrich_shop, shop)
    """
    results = enrich_shops([shop])
    return results[0] if results else {**shop, "offers": []}


# ─────────────────────────────────────────────────────────────────────────────
# Smart fallback
#
# Used when product search or service search returns 0 results.
# Falls back to a shop search using the same keywords + category.
#
# Fixes two bugs from main.py:
#   BUG 1 — service fallback returned is_product_search=True and the wrong
#            intent_label ("🛒 Looking for products" on a service search).
#            Fixed: caller passes the correct flags, this function is neutral.
#
#   BUG 2 — relevance filter used substring matching:
#            any(kw in shop_text for kw in query_kw)
#            "it" matched "electrical", "in" matched "dining".
#            Fixed: uses _whole_word_match() — same logic as search.py.
# ─────────────────────────────────────────────────────────────────────────────

def _whole_word_match(word: str, text: str) -> bool:
    """
    Return True if word appears as a whole word in text.
    Prevents "in" matching "dining", "it" matching "electrical", etc.
    Mirrors the same function in search.py — single source of truth for this logic.
    """
    if not word or not text:
        return False
    pattern = r"\b" + re.escape(word.lower()) + r"\b"
    return bool(re.search(pattern, text.lower()))


def _shop_is_relevant_to_keywords(shop: Dict[str, Any], keywords: List[str]) -> bool:
    """
    Return True if the shop is relevant to at least one keyword.
    Checks shop name, category, and subcategory using whole-word matching.

    This is used only for the fallback path — in primary search, Typesense
    handles relevance. Here we re-check because we're using a broader shop
    search that may return shops unrelated to the original product/service query.

    Example:
        keywords=["plumber", "plumbing"]
        shop name="City Plumbing Works" → True  (name contains "plumbing")
        shop name="City Services" → False        (no word-level match)
    """
    shop_text_parts = [
        (shop.get("name")        or "").lower(),
        (shop.get("category")    or "").lower(),
        (shop.get("subcategory") or "").lower(),
    ]
    shop_text = " ".join(shop_text_parts)

    # Build word-level keyword set — split multi-word keywords into individual words
    # but only keep words that are meaningful (length > 2, not noise)
    _NOISE = {"the", "and", "or", "for", "of", "in", "at", "a", "an", "near", "me"}
    keyword_words: List[str] = []
    for kw in keywords:
        for word in kw.lower().split():
            if len(word) > 2 and word not in _NOISE:
                keyword_words.append(word)

    if not keyword_words:
        return True  # no meaningful words to filter on → don't reject

    return any(_whole_word_match(word, shop_text) for word in keyword_words)


class FallbackResult:
    """
    Return value from smart_fallback().
    Separates result data from the decision of what happened.
    """
    __slots__ = ("shops", "radius_used_km", "found")

    def __init__(
        self,
        shops: List[Dict[str, Any]],
        radius_used_km: int,
    ):
        self.shops          = shops
        self.radius_used_km = radius_used_km
        self.found          = len(shops) > 0


def smart_fallback(
    keywords:       List[str],
    category:       str,
    user_lat:       Optional[float],
    user_lng:       Optional[float],
    radius_km:      int,
    limit:          int = DEFAULT_FALLBACK_LIMIT,
) -> FallbackResult:
    """
    Shared fallback for product and service handlers when primary search finds nothing.

    Strategy:
      1. Run shop search with the same keywords + category
      2. Filter results by keyword relevance (whole-word match)
      3. Enrich matching shops with their offers
      4. Return enriched shops or empty result

    Args:
        keywords:  The same keywords passed to the primary product/service search.
        category:  The matched category from intent parsing.
        user_lat:  User latitude (None = no location).
        user_lng:  User longitude (None = no location).
        radius_km: Search radius in km.
        limit:     Max shops to return.

    Returns:
        FallbackResult with enriched shops and radius info.

    Usage (in async handler):
        fb = await asyncio.to_thread(
            smart_fallback, keywords, category, lat, lng, radius_km
        )
        if fb.found:
            return build_response(success=True, results=fb.shops, ...)
        else:
            return no_results_response(...)
    """
    if not keywords:
        keywords = ["*"]

    # ── Step 1: Shop search with same keywords + category ─────────────────────
    try:
        shop_result = search_shops_parallel(
            keywords  = tuple(keywords),
            category  = category,
            user_lat  = user_lat,
            user_lng  = user_lng,
            radius_km = radius_km,
            limit     = limit * 2,   # fetch extra — some will be filtered out
        )
    except Exception as exc:
        logger.error("smart_fallback: shop search failed: %s", exc)
        return FallbackResult(shops=[], radius_used_km=radius_km)

    candidate_shops = shop_result.get("shops", [])
    radius_used     = shop_result.get("radius_used_km", radius_km)

    if not candidate_shops:
        logger.info(
            "smart_fallback: shop search returned 0 results "
            "(keywords=%s category='%s')",
            keywords, category,
        )
        return FallbackResult(shops=[], radius_used_km=radius_used)

    # ── Step 2: Relevance filter — whole-word matching ────────────────────────
    relevant = [
        s for s in candidate_shops
        if _shop_is_relevant_to_keywords(s, keywords)
    ]

    logger.info(
        "smart_fallback: %d candidate shops → %d relevant after filter "
        "(keywords=%s)",
        len(candidate_shops), len(relevant), keywords,
    )

    if not relevant:
        return FallbackResult(shops=[], radius_used_km=radius_used)

    # ── Step 3: Enrich with offers ────────────────────────────────────────────
    enriched = enrich_shops(relevant[:limit])

    return FallbackResult(shops=enriched, radius_used_km=radius_used)


# ─────────────────────────────────────────────────────────────────────────────
# Result message builder
#
# Every search path in main.py built its own summary string inline.
# This function consolidates them into one place.
#
# Previous patterns seen in main.py:
#   f"{nearest} is {dist}km away — {n} result(s) found nearby."
#   f"{specific.capitalize()} available at {nearest} and {n-1} more place(s) nearby."
#   f"Found {n} offer(s) at {shop['name']}."
#   f"Top result: {nearest} and {n-1} more. Enable location for nearest results."
#
# All replaced by build_result_message() with a context parameter.
# ─────────────────────────────────────────────────────────────────────────────

def build_result_message(
    results:        List[Dict[str, Any]],
    context:        str = "shop",
    specific_term:  str = "",
    radius_used_km: int = 0,
    no_location:    bool = False,
) -> str:
    """
    Build a human-readable summary line for any search result set.

    Args:
        results:        The enriched result list (shops, jobs, products, services).
        context:        One of: "shop", "job", "product", "service",
                        "offer", "shop_offer", "exact_shop", "exact_job".
        specific_term:  The specific thing searched for (e.g. "biryani", "plumber").
                        Used in product/service messages. Falls back to first result name.
        radius_used_km: Used in geo messages.
        no_location:    True when results are rating-based (no geo).

    Returns:
        A single human-readable string. Never empty — always has a fallback.

    Examples:
        build_result_message(shops, "shop", radius_used_km=3)
        → "Aryan Sweets is 0.8km away — 3 results found nearby."

        build_result_message(products, "product", specific_term="biryani")
        → "Biryani is available at Hotel Sagar and 2 more place(s) nearby."

        build_result_message(jobs, "job")
        → "Software Developer at TechCorp and 4 more opening(s) found."
    """
    if not results:
        return "No results found."

    count   = len(results)
    first   = results[0]
    more    = count - 1

    # ── Exact match ───────────────────────────────────────────────────────────
    if context == "exact_shop":
        return f"Found {first.get('name', 'the shop')}."

    if context == "exact_job":
        position   = first.get("position", "the position")
        shop_name  = first.get("shop_name", "a shop")
        return f"Found {position} at {shop_name}."

    # ── Shop offer (specific shop) ────────────────────────────────────────────
    if context == "shop_offer":
        shop_name  = first.get("name", "the shop")
        offer_count = len(first.get("offers", []))
        if offer_count == 0:
            return f"No active offers at {shop_name} right now."
        return (
            f"Found {offer_count} offer{'s' if offer_count > 1 else ''} "
            f"at {shop_name}."
        )

    # ── General offer search ──────────────────────────────────────────────────
    if context == "offer":
        nearest = first.get("name", "a shop")
        suffix  = f" and {more} more shop{'s' if more > 1 else ''}" if more else ""
        radius_str = f" within {radius_used_km}km" if radius_used_km else ""
        return f"Found offers at {nearest}{suffix}{radius_str}."

    # ── Product ───────────────────────────────────────────────────────────────
    if context == "product":
        item    = (specific_term or first.get("product_name") or "This item").capitalize()
        nearest = first.get("name") or first.get("shop_name") or "a nearby shop"
        if more:
            return f"{item} available at {nearest} and {more} more place{'s' if more > 1 else ''} nearby."
        return f"{item} available at {nearest}."

    # ── Service ───────────────────────────────────────────────────────────────
    if context == "service":
        item    = (specific_term or first.get("service_name") or "This service").capitalize()
        nearest = first.get("name") or first.get("shop_name") or "a nearby provider"
        if more:
            return f"{item} available at {nearest} and {more} more provider{'s' if more > 1 else ''} nearby."
        return f"{item} available at {nearest}."

    # ── Product/service fallback (shop results shown for p/s query) ───────────
    if context == "product_fallback":
        item    = (specific_term or "").capitalize() or "Results"
        nearest = first.get("name", "a nearby shop")
        if more:
            return f"{item} found at {nearest} and {more} more shop{'s' if more > 1 else ''} nearby."
        return f"{item} found at {nearest}."

    if context == "service_fallback":
        item    = (specific_term or "").capitalize() or "Results"
        nearest = first.get("name", "a nearby shop")
        if more:
            return f"{item} shop found: {nearest} and {more} more nearby."
        return f"{item} shop found: {nearest}."

    # ── Job ───────────────────────────────────────────────────────────────────
    if context == "job":
        position  = first.get("position", "A vacancy")
        shop_name = first.get("shop_name", "a shop")
        if more:
            return f"{position} at {shop_name} and {more} more opening{'s' if more > 1 else ''} found."
        return f"{position} at {shop_name} vacancy found."

    # ── Shop — no location ────────────────────────────────────────────────────
    if context == "shop_no_location":
        nearest = first.get("name", "a shop")
        if more:
            return (
                f"Top result: {nearest} and {more} more. "
                f"Enable location for nearest results."
            )
        return f"Top result: {nearest}. Enable location for nearest results."

    # ── Shop — geo (default) ──────────────────────────────────────────────────
    nearest  = first.get("name", "a shop")
    dist     = first.get("distance_km")
    dist_str = f"{dist}km" if dist is not None else "nearby"

    if no_location:
        return build_result_message(results, "shop_no_location", specific_term, radius_used_km)

    if more:
        return f"{nearest} is {dist_str} away — {count} result{'s' if count > 1 else ''} found nearby."
    return f"{nearest} is {dist_str} away — nearest result."