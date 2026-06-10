"""
intent.py — PHASE 1 FIXED
─────────
Intent extraction from user queries.
"""

import asyncio
import json
import re
import time
import logging
from typing import Any, Dict, List, Optional

# ── CONSTANTS (all at top, no scattered imports)
from constants import (
    STOP_WORDS,
    JOB_KEYWORDS,
    OFFER_KEYWORDS,
    PRODUCT_KEYWORDS,
    SERVICE_KEYWORDS,
)

# ── LOCAL IMPORTS
from model import ParsedIntent
from cache import cache_result_async, cache_result
from config import config
from clients import groq_client
from database import fetch_all
from prompts import get_intent_system_prompt
from category_mapper import get_semantic_category_two_level

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CASUAL QUERY GUARD
# Catches greetings/abstract queries BEFORE the LLM call.
# Saves ~300ms latency and prevents wrong intent routing.
# ═══════════════════════════════════════════════════════════════════════════════

_CASUAL_EXACT = {
    "hi", "hello", "hey", "ok", "okay", "yes", "no", "nope", "yep",
    "thanks", "thank you", "thank u", "ty", "bye", "goodbye", "good bye",
    "good morning", "good evening", "good night", "good afternoon",
    "how are you", "how r u", "what's up", "whats up", "sup",
    "sure", "alright", "fine", "great", "nice", "cool", "wow",
    "lol", "haha", "hmm", "ok ok", "got it",
    "what can you do", "what do you do", "who are you", "what is this",
    "what is this app", "help", "help me", "i need help",
    "i am ok", "i am okay", "i am good", "i am fine", "i am bad",
    "i am tired", "i am bored", "i am busy", "i am happy", "i am sad",
    "i need rest", "i need a break", "i need it", "i need time",
    "i need something", "i need anything", "i need everything",
    "i need a minute", "i need money", "i need cash", "i need support",
    "show me", "give me", "tell me", "tell me more",
    "what do you have", "not good", "not bad",
}

# "i need X" where X is abstract — not a shop search
_ABSTRACT_NEED = {
    "help", "rest", "break", "it", "something", "anything", "everything",
    "nothing", "time", "minute", "second", "money", "cash", "support",
    "attention", "love", "friend", "you", "company", "space", "air",
    "water", "sleep", "peace", "quiet",
}

# Single-word queries that ARE valid shop/service searches
_VALID_SINGLE_WORDS = {
    # Food & Dining
    "food", "juice", "biryani", "pizza", "coffee", "tea", "milk",
    "vegetables", "fruits", "chicken", "fish", "meat", "cake",
    "sweets", "sweet", "snack", "snacks", "hotel", "restaurant",
    "restaruent", "restaurent", "bakery", "cafe", "grocery",
    "honey", "muruku", "lassi", "biryani","biriyani", "briyani", "biriryani", "birriyani",
    "pizza", "burger","cake", "chips", "rice", "bread", "egg", "meat",
    "caterer", "catering",   "packers", "movers","jcb",

    # ADD THESE:
    "shawarma", "dosa", "idly", "idli", "parota", "parotta",
    "chapati", "chappati", "falooda", "faloda",
    "supermarket", "wine", "beer",
    # Transport
    "taxi", "auto", "cab", "cabs", "bus", "bike",
    # Jobs
    "job", "jobs", "vacancy", "hiring", "fresher",
    # Services
    "salon", "spa", "massage", "yoga", "fitness", "gym",
    "doctor", "hospital", "pharmacy", "clinic",
    "plumber", "plumbing", "electrician", "carpenter", "painter",
    "mechanic", "tailor", "cleaner", "cleaning", "repair",
    "service", "services", "driver", "cook", "nurse",
    "security", "accountant", "designer", "developer",
    "technician", "welding", "fabrication", "pest",
    # Retail / Products
    "mobile", "phone", "laptop", "ac", "tv", "fridge",
    "clothes", "shirt", "dress", "shoes", "jewellery",
    "gold", "silver", "flower", "flowers", "hardware",
    "petrol", "courier", "delivery", "laundry", "printer",
    # Offers
    "offers", "offer", "deals", "deal", "discount", "discounts", "sale",
    # Professional
    "lawyer", "ca", "chartered", "interior", "architect",
    "tutor", "coaching", "photographer", "caterer",
    "packers", "movers",
    # Misc
    "atm", "bank", "school",
    # Retail / Products
    "mobile", "phone", "laptop", "ac", "tv", "fridge",
    "clothes", "shirt", "dress", "shoes", "jewellery",
    "gold", "silver", "flower", "flowers", "hardware",
    # Food products
    "honey", "muruku", "lassi", "biryani", "pizza", "burger",
    "cake", "chips", "rice", "bread", "egg", "meat",
}

_COMPOUND_SKILL_WORDS = {
    "barista", "driver", "cook", "chef", "nurse", "accountant", "cashier",
    "security", "cleaner", "painter", "carpenter", "electrician", "plumber",
    "mechanic", "tailor", "designer", "developer", "teacher", "tutor",
    "pharmacist", "receptionist", "manager", "supervisor", "helper",
    "packer", "loader", "welder", "technician", "operator", "engineer",
}


def is_casual_query(query: str) -> bool:
    """
    Returns True if query is a greeting or abstract phrase.
    
    Casual queries never trigger a shop/job search. Used as a quick guard
    before calling Groq LLM to save ~300ms latency on common greetings.
    
    Args:
        query (str): User's input query.
    
    Returns:
        bool: True if query matches greeting patterns, False otherwise.
    
    Detected patterns:
        - Exact matches: "hi", "hello", "bye", "thanks", etc. (see _CASUAL_EXACT)
        - Single non-valid words: Random alphabetic word not in _VALID_SINGLE_WORDS
        - Abstract needs: "i need <abstract_word>" where word is generic (rest, help, time, etc.)
    
    Example:
        >>> is_casual_query("hi")
        True
        >>> is_casual_query("i need rest")
        True
        >>> is_casual_query("i need biryani")
        False
    """
    q = query.strip().lower()

    if q in _CASUAL_EXACT:
        return True

    words = q.split()

    # Single non-shop word
    if len(words) == 1 and q.isalpha() and q not in _VALID_SINGLE_WORDS:
        return True
    
    if len(words) == 1 and not q.isalpha() and len(q) <= 5:
         pass

    # "i need <abstract word>"
    if q.startswith("i need ") and len(words) >= 3:
        third_word = words[2]
        if third_word in _ABSTRACT_NEED:
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# NAME VALIDATION
# Prevents abstract phrases from triggering exact shop/job lookups
# ═══════════════════════════════════════════════════════════════════════════════

_UNSAFE_NAME_WORDS = {
    "something", "anything", "everything", "nothing", "someone",
    "features", "app", "this", "that", "here", "there", "help",
    "more", "details", "info", "about", "tell", "show", "find",
    "me", "you", "us", "them", "it", "one", "some", "any",
}


def is_valid_name(name: str) -> bool:
    """
    Returns True only if the extracted name looks like a real business/job name.
    
    Rejects abstract or filler phrases to prevent false "exact shop" lookups.
    For example, "something" or "features" should never be treated as business names.
    
    Args:
        name (str): Proposed business/job name to validate.
    
    Returns:
        bool: True if name is non-empty (3+ chars) and contains at least one
              non-generic word; False otherwise.
    
    Example:
        >>> is_valid_name("Royal Bakery")
        True
        >>> is_valid_name("something")
        False
        >>> is_valid_name("XYZ")  # 3 chars but generic
        False
    """
    if not name or len(name.strip()) < 3:
        return False
    words = set(name.lower().split())
    # All words are generic/unsafe → not a real name
    if words.issubset(_UNSAFE_NAME_WORDS):
        return False
    return True

_COMPOUND_PATTERNS = [
    r"^(.+?)\s+(?:at|in|for|with|from)\s+(.+)$",   # "barista at Royal Cafe"
    r"^(.+?)\s+(?:vacancy|job|work)\s+(?:at|in)\s+(.+)$",  # "driver job at XYZ"
]



def _resolve_compound_intent(query: str) -> Optional[tuple]:
    """
    Detect compound queries like "barista at Royal Cafe".
    
    Compound queries combine a skill/role with a location, allowing users to
    search for specific job roles at specific places.
    
    Args:
        query (str): User query to parse.
    
    Returns:
        Optional[tuple]: (skill_part, place_part) if compound pattern found, else None.
            Only triggers when skill_part contains a known job or service keyword
            or matches a known single-word job role (_COMPOUND_SKILL_WORDS).
    
    Patterns matched:
        - "<skill> at <place>"
        - "<skill> in <place>"
        - "<skill> for <place>"
        - "<skill> vacancy/job at <place>"
    
    Example:
        >>> _resolve_compound_intent("barista at Royal Cafe")
        ('barista', 'Royal Cafe')
        >>> _resolve_compound_intent("find a shop")
        None  # Not a compound pattern
    """
    q = query.strip().lower()
    
    for pattern in _COMPOUND_PATTERNS:
        m = re.match(pattern, q)
        if not m:
            continue
        
        skill_part = m.group(1).strip()
        place_part = m.group(2).strip()
        
        # Skill part must contain a job or service keyword to qualify
        skill_words = set(skill_part.split())
        if skill_words & JOB_KEYWORDS or skill_words & SERVICE_KEYWORDS:
            return (skill_part, place_part)
        
        # Also check if skill_part itself is a known single-word role
        if skill_part in _COMPOUND_SKILL_WORDS:
            return (skill_part, place_part)
    
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# CIRCUIT BREAKER
# Stops calling Groq when it's consistently failing.
# After 3 failures → skip Groq for 30s → use keyword_fallback instead.
# Resets automatically when the cooldown expires.
# ═══════════════════════════════════════════════════════════════════════════════

class _CircuitBreaker:
    FAILURE_THRESHOLD = 5    # tolerate burst failures before opening
    COOLDOWN_SECONDS  = 60   # longer window — Groq rate limit resets per minute

    def __init__(self):
        self._failures   = 0
        self._opened_at  = 0.0
        self._state      = "CLOSED"
        self._half_open_in_flight = False   # ← only ONE test request at a time

    @property
    def is_open(self) -> bool:
        if self._state == "OPEN":
            if time.monotonic() - self._opened_at > self.COOLDOWN_SECONDS:
                if not self._half_open_in_flight:
                    self._state = "HALF_OPEN"
                    self._half_open_in_flight = True
                    logger.info("Circuit breaker: HALF_OPEN — sending one test request")
                    return False   # only the first concurrent request gets through
                return True        # rest stay blocked during half-open test
            return True
        return False

    def record_success(self):
        self._failures            = 0
        self._half_open_in_flight = False
        self._state               = "CLOSED"

    def record_failure(self):
        self._half_open_in_flight = False
        self._failures += 1
        if self._failures >= self.FAILURE_THRESHOLD:
            self._state     = "OPEN"
            self._opened_at = time.monotonic()
            logger.warning(
                f"Circuit breaker: OPEN — Groq skipped for {self.COOLDOWN_SECONDS}s"
            )                                       

_groq_breaker = _CircuitBreaker()


# ═══════════════════════════════════════════════════════════════════════════════
# KEYWORD FALLBACK
# Used when Groq is down or times out.
# Extracts intent purely from query words — no LLM.
# Always returns a usable ParsedIntent so search never fails.
# ═══════════════════════════════════════════════════════════════════════════════

def keyword_fallback(query: str, category_names: List[str] = []) -> ParsedIntent:
    q      = query.strip().lower()
    words  = set(q.split())
    tokens = [w for w in q.split() if w not in STOP_WORDS and len(w) > 2]


    # ── Early name detection: 2+ capitalized words → exact shop, skip keyword matching
    query_words = query.strip().split()
    capitalized = [w for w in query_words if w and w[0].isupper()]
    if (
        len(capitalized) >= 2
        and len(query_words) <= 4
        and not (words & JOB_KEYWORDS)
        and not (words & OFFER_KEYWORDS)
    ):
        logger.info(f"Fallback early name detection: '{query}'")
        return ParsedIntent(
            intent="shop", search_type="specific",
            keywords=tokens[:3] if tokens else [q],
            category="", category_names=category_names,
            name=query.strip(), radius_km=0, sort_by_rating=False,
        )
    compound = _resolve_compound_intent(query)
    if compound:
        skill_part, place_part = compound
        skill_tokens = [w for w in skill_part.split() if w not in STOP_WORDS and len(w) > 2]
        logger.info(f"Compound intent: skill='{skill_part}' place='{place_part}'")
        category_data  = _load_category_data()
        category_names = [c["name"] for c in category_data.get("categories", [])]
        return ParsedIntent(
            intent         = "job",
            search_type    = "general",
            keywords       = skill_tokens[:3] if skill_tokens else [skill_part],
            category       = "",
            category_names = category_names,
            name           = "",
            radius_km      = 0,
            sort_by_rating = False,
        )

    # Load category data (cached)
    category_data     = _load_category_data()
    category_names    = [c["name"] for c in category_data.get("categories", [])]
    subcategory_names = [s["name"] for s in category_data.get("subcategories", [])]

    # ── Determine intent ──────────────────────────────────────────────────────
    # "shop"/"store" suffix overrides service/product keywords → always shop
    _SHOP_SUFFIX_WORDS = {"shop", "store", "center", "centre", "mart", "showroom"}

    # Short alphanumeric queries (e.g. "f12", "abc1") with no keyword match
    # → treat as exact name lookup, never general shop search
    _is_short_alphanumeric = (
        len(q.split()) == 1
        and not q.isalpha()
        and len(q) <= 6
        and not (words & JOB_KEYWORDS)
        and not (words & OFFER_KEYWORDS)
        and not (words & SERVICE_KEYWORDS)
        and not (words & PRODUCT_KEYWORDS)
    )
    if _is_short_alphanumeric:
        logger.info(f"Short alphanumeric query '{q}' → exact name lookup")
        return ParsedIntent(
            intent="shop", search_type="specific",
            keywords=[q],
            category="", category_names=category_names,
            name=q, radius_km=0, sort_by_rating=False,
        )

    # ── Determine intent ──────────────────────────────────────────────────────
    if words & JOB_KEYWORDS:
        intent = "job"
    elif words & OFFER_KEYWORDS:
        intent = "offer"
    elif words & _SHOP_SUFFIX_WORDS:
        intent = "shop"
    elif words & SERVICE_KEYWORDS:
        intent = "service"
    elif words & PRODUCT_KEYWORDS:
        intent = "product"
    else:
        intent = "shop"

    keywords = tokens[:3] if tokens else [q]

    # ── Category matching for single/short queries ────────────────────────────
    matched_category = ""
    if keywords:
        primary = keywords[0].lower()
        category_data = _load_category_data()
        all_cats = (
            [s["name"] for s in category_data.get("subcategories", [])] +
            [c["name"] for c in category_data.get("categories", [])]
        )
        for cat in all_cats:
            if cat.lower() == primary or primary in cat.lower() or cat.lower() in primary:
                matched_category = cat
                break

    # ── Name detection: does this look like a specific business name? ─────────
    # Heuristic: 2+ meaningful words, no generic action verbs, shop intent
    name = ""
    search_type = "general"
    generic_verbs = {"find", "search", "show", "get", "need", "want",
                     "looking", "any", "where", "which", "nearest", "nearby"}

    # These are never business names — they are product/service descriptors
    _NON_NAME_PHRASES = {
        "biryani", "honey", "rose milk", "fresh juice", "banana chips",
        "muruku", "shirt", "jeans", "dress", "juice", "lassi",
        "haircut", "mens haircut", "web development", "coconut cutting",
        "construction work", "tourist bus", "auto rickshaw", "plumber",
        "ac repair", "tv repair", "catering", "fresh juice",
        "chicken", "mutton", "fish", "cake", "snacks", "dosa", "idly",
         "call taxi", "water leakage", "tempo traveller", "security camera",
        "pipe repair", "pipe leak", "water pipe",
    }

    query_meaningful_words = [w for w in q.split() if w not in STOP_WORDS and len(w) > 1]

    if (
        intent == "shop"
        and len(query_meaningful_words) >= 2
        and not (words & generic_verbs)
        and not matched_category
        and q.strip().lower() not in _NON_NAME_PHRASES          # ← NEW
        and not any(q.strip().lower().startswith(p)              # ← NEW
                    for p in _NON_NAME_PHRASES)
    ):
        name        = query.strip()
        search_type = "specific"
        logger.info(f"Fallback name detected: '{name}'")

    logger.info(
        f"Keyword fallback: '{query[:40]}' → intent={intent} kw={keywords} "
        f"cat='{matched_category}' name='{name}'"
    )

    return ParsedIntent(
        intent=intent, search_type=search_type,
        keywords=keywords, category=matched_category,
        category_names=category_names,
        name=name, radius_km=0, sort_by_rating=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY DATA LOADER
# Loads categories + subcategories from DB (cached 1hr).
# ═══════════════════════════════════════════════════════════════════════════════

@cache_result(ttl=3600, prefix="db_category_data")
def _load_category_data() -> Dict[str, Any]:
    """
    Load categories + subcategories from DB.
    Noise subcategories (All, More, Other) excluded.
    Returns empty lists on failure — intent still works, just no category matching.
    """
    NOISE = {"more", "all", "other", "others", "miscellaneous"}
    try:
        cat_rows = fetch_all(
            "SELECT id, categoriesname FROM categories ORDER BY categoriesname"
        )
        categories = [
            {"id": r["id"], "name": r["categoriesname"].strip()}
            for r in (cat_rows or [])
            if r.get("categoriesname") and r["categoriesname"].strip()
        ]

        sub_rows = fetch_all(
            """
            SELECT s.id, s.subcategoryname, c.categoriesname AS parent
            FROM   subcategories s
            JOIN   categories c ON c.id = s.category_id
            ORDER  BY s.subcategoryname
            """
        )
        subcategories = [
            {
                "id":     r["id"],
                "name":   r["subcategoryname"].strip(),
                "parent": r["parent"].strip(),
            }
            for r in (sub_rows or [])
            if r.get("subcategoryname")
            and r["subcategoryname"].strip().lower() not in NOISE
        ]

        logger.info(
            f"Category data loaded: {len(categories)} categories, "
            f"{len(subcategories)} subcategories"
        )
        return {"categories": categories, "subcategories": subcategories}

    except Exception as e:
        logger.warning(f"Category data load failed: {e}")
        return {"categories": [], "subcategories": []}


# ═══════════════════════════════════════════════════════════════════════════════
# GROQ CALL
# Isolated async wrapper. Raises on timeout/error — caller handles fallback.
# ═══════════════════════════════════════════════════════════════════════════════

async def _call_groq(system_prompt: str, query: str) -> str:
    """
    Make a single Groq API call. Returns raw content string.
    Raises asyncio.TimeoutError or Exception on failure.
    Timeout is 5s (reduced from 10s) — fail fast, fall back faster.
    """
    def _sync_call():
        return groq_client.chat.completions.create(
            model = "llama-3.3-70b-versatile",
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": query.strip()},
            ],
            max_tokens  = 200,
            temperature = 0,
            timeout     = 10,
        ).choices[0].message.content.strip()

    return await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(None, _sync_call),
        timeout=7.0,   # 5s Groq + 2s buffer
    )


# ═══════════════════════════════════════════════════════════════════════════════
# INTENT PARSING HELPERS
# Small focused functions instead of one 120-line monster
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_intent_field(raw: str) -> str:
    """Validate and normalize intent field from LLM response."""
    valid = {"shop", "job", "product", "service", "offer", "other"}
    value = str(raw).strip().lower()
    return value if value in valid else "shop"


def _parse_search_type(raw: str) -> str:
    """Validate and normalize search type field."""
    valid = {"general", "specific", "category"}
    value = str(raw).strip().lower()
    return value if value in valid else "general"


def _extract_keywords(parsed: Dict, fallback_query: str) -> List[str]:
    """
    Extract keywords from LLM response. Always returns a non-empty list.

    Priority:
      1. parsed["keywords"] list
      2. parsed["keyword"] string
      3. fallback_query as single keyword
      4. ["*"] as last resort
    """
    # Try list field
    raw = parsed.get("keywords")
    if isinstance(raw, list) and raw:
        cleaned = [
            k.strip().lower()
            for k in raw
            if isinstance(k, str) and k.strip()
        ]
        if cleaned:
            return cleaned[:4]

    # Try singular field
    single = parsed.get("keyword")
    if isinstance(single, str) and single.strip():
        return [single.strip().lower()]

    # Fallback to query
    if fallback_query and fallback_query.strip():
        q = fallback_query.strip().lower()
        tokens = [w for w in q.split() if w not in STOP_WORDS and len(w) > 2]
        return tokens[:3] if tokens else [q]

    return ["*"]


def _prioritize_keywords(keywords: List[str], specific_type: str) -> List[str]:
    """
    Put specific_type (e.g. "biryani", "plumber") first in keyword list.
    This ensures Typesense searches the most specific term first.
    """
    if not specific_type:
        return keywords
    st = specific_type.strip().lower()
    if st in keywords:
        return [st] + [k for k in keywords if k != st][:2]
    return [st] + keywords[:2]


# Build once at module load — keyword → canonical category name
# Covers the 90% case without any LLM call
def _build_category_keyword_map(
    subcategory_names: List[str],
    category_names: List[str],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for name in subcategory_names + category_names:
        # map the full name and each word in the name
        mapping[name.lower().strip()] = name
        for word in name.lower().split():
            if len(word) > 3 and word not in STOP_WORDS:
                if word not in mapping:
                    mapping[word] = name
    return mapping


async def _match_category(
    user_category: str,
    subcategory_names: List[str],
    category_names: List[str],
) -> str:
    if not user_category:
        return ""

    user_lower = user_category.lower().strip()
    all_names  = subcategory_names + category_names

    # 1. Exact match — fastest, no LLM
    direct = next(
        (name for name in all_names if name.lower().strip() == user_lower),
        None,
    )
    if direct:
        return direct

    # 2. Local keyword map — handles "restaurant"→"Restaurent", "salon"→"Beautician"
    kw_map = _build_category_keyword_map(subcategory_names, category_names)
    local  = kw_map.get(user_lower)
    if local:
        logger.debug(f"Category local-kw match: '{user_category}' → '{local}'")
        return local

    # 3. Substring scan — "mobile repair" → "Mobiles & Electronics"
    for name in all_names:
        if user_lower in name.lower() or name.lower() in user_lower:
            logger.debug(f"Category substring match: '{user_category}' → '{name}'")
            return name

    # 4. Groq semantic match — only if all local methods fail
    #    Skip entirely if circuit breaker is open (saves the quota)
    if _groq_breaker.is_open:
        logger.debug("Category semantic match skipped — circuit open")
        return ""

    try:
        matched = await asyncio.get_running_loop().run_in_executor(
            None,
            get_semantic_category_two_level,
            user_category,
            subcategory_names,
            category_names,
            groq_client,
        )
        if matched:
            logger.debug(f"Category semantic match: '{user_category}' → '{matched}'")
        return matched or ""
    except Exception as e:
        logger.warning(f"Category semantic match failed: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN INTENT FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

_NORMALIZE_STRIP = re.compile(
    r"\b(near me|nearby|near by|close to me|around me|around here|"
    r"in my area|close by|closest|nearest)\b",
    re.IGNORECASE,
)

def _normalize_query(query: str) -> str:
    """
    Strip location filler so 'biryani near me' and 'biryani nearby'
    hit the same cache key. Lowercases and collapses whitespace.
    """
    q = query.strip().lower()
    q = _NORMALIZE_STRIP.sub("", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q

@cache_result_async(ttl=600, prefix="intent", return_type=ParsedIntent)
async def get_intent(query: str) -> ParsedIntent:
    original_query = query               # ← save original casing first
    query = _normalize_query(query)      # ← now lowercase

    if not query or not query.strip():
        return ParsedIntent(intent="other")

    if is_casual_query(query.strip()):
        logger.info(f"Casual fast-path: '{query[:40]}'")
        return ParsedIntent(intent="other")

    _SERVICE_EXACT_GUARD = {
        "call taxi", "water leakage", "pipe repair", "water pipe",
        "tempo traveller", "security camera", "ac repair", "tv repair",
        "house shifting", "home shifting", "coconut cutting",
    }
    _query_words = original_query.strip().split()   # ← original casing
    _capitalized = [w for w in _query_words if w and w[0].isupper()]
    if (
        len(_capitalized) >= 2
        and len(_query_words) <= 4
        and not set(query.lower().split()) & JOB_KEYWORDS
        and not set(query.lower().split()) & OFFER_KEYWORDS
        and original_query.strip().lower() not in _SERVICE_EXACT_GUARD
    ):
        category_data  = _load_category_data()
        category_names = [c["name"] for c in category_data.get("categories", [])]
        tokens = [w for w in query.lower().split() if w not in STOP_WORDS and len(w) > 2]
        logger.info(f"Early name detection (pre-Groq): '{original_query}'")
        return ParsedIntent(
            intent="shop", search_type="specific",
            keywords=tokens[:3] if tokens else [query.lower()],
            category="", category_names=category_names,
            name=original_query.strip(),
            radius_km=0, sort_by_rating=False,
        )

    compound = _resolve_compound_intent(query)
    if compound:
        skill_part, place_part = compound
        skill_tokens = [w for w in skill_part.split() if w not in STOP_WORDS and len(w) > 2]
        logger.info(f"Compound intent: skill='{skill_part}' place='{place_part}'")
        category_data  = _load_category_data()
        category_names = [c["name"] for c in category_data.get("categories", [])]
        return ParsedIntent(
            intent         = "job",
            search_type    = "general",
            keywords       = skill_tokens[:3] if skill_tokens else [skill_part],
            category       = "",
            category_names = category_names,
            name           = "",
            radius_km      = 0,
            sort_by_rating = False,
        )

    # Load category data (cached)
    category_data     = _load_category_data()
    category_names    = [c["name"] for c in category_data.get("categories", [])]
    subcategory_names = [s["name"] for s in category_data.get("subcategories", [])]
    # Circuit breaker open → skip Groq
    if _groq_breaker.is_open:
        logger.warning("Circuit breaker OPEN — using keyword fallback")
        return keyword_fallback(query, category_names)

    # Call Groq
    try:
        system_prompt = get_intent_system_prompt(category_data)
        raw           = await _call_groq(system_prompt, query)

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$",           "", raw)

        parsed = json.loads(raw)
        _groq_breaker.record_success()

    except asyncio.TimeoutError:
        logger.warning(f"Groq timeout for '{query[:40]}'")
        _groq_breaker.record_failure()
        return keyword_fallback(query, category_names)

    except json.JSONDecodeError:
        logger.warning(f"Groq JSON parse failed for '{query[:40]}'")
        _groq_breaker.record_failure()
        return keyword_fallback(query, category_names)

    except Exception as exc:
        logger.warning(f"Groq call failed: {exc}")
        _groq_breaker.record_failure()
        return keyword_fallback(query, category_names)

    # Parse fields from Groq response
    intent      = _parse_intent_field(parsed.get("intent", "shop"))
    search_type = _parse_search_type(parsed.get("type", "general"))

    # Build keyword list with specific_type prioritized
    keywords      = _extract_keywords(parsed, query)
    specific_type = str(parsed.get("specific_type", "")).strip().lower()
    keywords      = _prioritize_keywords(keywords, specific_type)

    # Extract name for exact lookups
    name = str(parsed.get("name", "")).strip()

    # Radius
    try:
        radius_km = max(0, int(parsed.get("radius_km", 0) or 0))
    except (ValueError, TypeError):
        radius_km = 0

    # Sort preference
    sort_by_rating = bool(parsed.get("sort_by_rating", False))

    # Match category to DB name
    user_category    = str(parsed.get("category", "")).strip()
    matched_category = await _match_category(
        user_category, subcategory_names, category_names
    )

    result = ParsedIntent(
        intent         = intent,
        search_type    = search_type,
        keywords       = keywords,
        category       = matched_category,
        category_names = category_names,
        name           = name,
        radius_km      = radius_km,
        sort_by_rating = sort_by_rating,
    )

    logger.info(
        f"Intent: {intent} | {search_type} | kw={keywords} | "
        f"cat='{matched_category}' | name='{name}'"
    )
    return result