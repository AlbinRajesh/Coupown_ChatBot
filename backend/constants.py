"""
Unified constants for the entire application.
Single source of truth prevents mismatches between modules.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# STOP WORDS / NOISE WORDS — UNIFIED
# Used by: intent.py (keyword extraction), search.py (relevance filtering)
# Rule: If a word is in this set, it's filtered when extracting meaningful keywords
# ═══════════════════════════════════════════════════════════════════════════════

STOP_WORDS = frozenset({
    # Articles
    "a", "an", "the",
    
    # Prepositions
    "in", "on", "at", "to", "for", "of", "from", "with", "by",
    
    # Location modifiers (intent extraction ignores these)
    "near", "me", "nearby", "around", "here", "there", "close",
    
    # Generic verbs / actions
    "find", "search", "show", "get", "give", "tell", "need", "want",
    
    # Generic modifiers
    "good", "best", "top", "cheap", "affordable", "nice", "new", "old",
    
    # Generic nouns
    "something", "anything", "everything", "nothing", "place", "shop",
    
    # Pronouns
    "i", "me", "you", "us", "them", "it", "one", "any", "some",
    
    # Conjunctions
    "and", "or", "but",
    
    # Auxiliaries
    "is", "are", "was", "be", "can", "could", "should", "would",
    
    # Additional noise
    "please", "kindly", "thanks", "hello", "hi",
})

# ═══════════════════════════════════════════════════════════════════════════════
# INTENT-SPECIFIC WORDS
# Used by: intent.py for fast intent detection without LLM
# ═══════════════════════════════════════════════════════════════════════════════

JOB_KEYWORDS = frozenset({
    "job", "jobs", "vacancy", "vacancies", "hiring",
    "career", "opening", "employment", "opportunity", "recruiter",
    "fresher", "internship", "position", "posted",
})

OFFER_KEYWORDS = frozenset({
    "offer", "offers", "deal", "deals", "discount", "discounts",
    "sale", "promo", "promotion", "coupon", "code", "save",
})

PRODUCT_KEYWORDS = frozenset({
    # Original
    "buy", "price", "cost", "product", "item", "sell", "selling",
    "available", "stock", "purchase", "order", "deliver", "shipped",
    # Food items (specific buyable things)
    "biryani", "honey", "juice", "milk", "rose", "banana", "chips",
    "muruku", "cake", "snack", "snacks", "dosa", "idly", "parota",
    "chicken", "mutton", "fish", "meat", "egg", "bread", "rice",
    "coffee", "tea", "lassi", "shake", "pizza", "burger", "noodles",
    # Clothing / goods
    "shirt", "jeans", "dress", "shoes", "saree", "kurta", "trouser",
    # Other specific products
    "mobile", "laptop", "phone", "tablet", "watch", "bag",
})
SERVICE_KEYWORDS = frozenset({
    # Original
    "service", "services", "repair", "fix", "clean", "install",
    "plumber", "electrician", "carpenter", "painter", "driver",
    "cleaner", "mechanic", "technician", "professional",
    "security", "camera",
    # Missing service types (all 4 failed tests)
    "haircut", "cutting", "trim", "shave", "makeup", "bridal",
    "development", "developer", "designing", "design", "coding",
    "catering", "construction", "contractor", "civil", "building",
    "welding", "fabrication", "pest", "shifting", "moving",
    "photography", "event", "ac", "cctv", "pump", "plumbing",
    "tailoring", "laundry", "courier", "delivery", "massage",
    "yoga", "coaching", "tuition", "acting",
})

# ═══════════════════════════════════════════════════════════════════════════════
# RELEVANCE SCORING THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════════

# Exact name match (shop/job lookup) — minimum similarity to avoid wrong results
NAME_MATCH_THRESHOLD = 0.60

# Fuzzy match in relevance scoring (shop against category)
FUZZY_MATCH_THRESHOLD = 0.75

# ═══════════════════════════════════════════════════════════════════════════════
# TIMEOUT CONSTANTS
# All timeouts in seconds. Keep these in ONE place so they stay consistent.
# ═══════════════════════════════════════════════════════════════════════════════

# Database
DB_POOL_ACQUIRE_TIMEOUT = 30.0      # Max time to get a connection from pool
DB_QUERY_TIMEOUT = 15.0              # Max time for a single query

# Search / Typesense
TYPESENSE_SEARCH_TIMEOUT = 10.0      # Soft timeout for individual searches
TYPESENSE_HARD_TIMEOUT = 15.0        # Absolute maximum before abort

# Intent parsing (Groq LLM)
GROQ_TIMEOUT = 5.0                   # Groq API call timeout
INTENT_PARSE_HARD_TIMEOUT = 7.0      # Total with overhead + retry

# Chat context building
CHAT_CONTEXT_TIMEOUT = 12.0          # Should be less than response timeout
CHAT_RESPONSE_HARD_TIMEOUT = 15.0    # Absolute max for entire /chat endpoint

# Job search (no radius filter, so longer timeout OK)
JOB_SEARCH_TIMEOUT = 10.0

# Product/Service search
PRODUCT_SERVICE_TIMEOUT = 10.0

# Offer search
OFFER_SEARCH_TIMEOUT = 10.0

# ═══════════════════════════════════════════════════════════════════════════════
# CACHE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Default cache TTL (seconds)
CACHE_DEFAULT_TTL = 300

# Category data rarely changes — cache longer
CACHE_CATEGORY_TTL = 3600  # 1 hour

# Intent results are query-specific, moderate TTL
CACHE_INTENT_TTL = 600  # 10 minutes

# Search results change frequently but queries repeat
CACHE_SEARCH_TTL = 180  # 3 minutes

# Job listings change less frequently
CACHE_JOB_SEARCH_TTL = 300  # 5 minutes

# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH LIMITS
# ═══════════════════════════════════════════════════════════════════════════════

# Chat context — how many results to show LLM
CHAT_CONTEXT_LIMIT_SHOP = 8
CHAT_CONTEXT_LIMIT_OFFER = 6
CHAT_CONTEXT_LIMIT_PRODUCT = 6
CHAT_CONTEXT_LIMIT_SERVICE = 6
CHAT_CONTEXT_LIMIT_JOB = 5

# Handler search limits
HANDLER_RESULT_LIMIT_SHOP = 5
HANDLER_RESULT_LIMIT_JOB = 10
HANDLER_RESULT_LIMIT_PRODUCT = 6
HANDLER_RESULT_LIMIT_SERVICE = 10
HANDLER_RESULT_LIMIT_OFFER = 5

# Search defaults
DEFAULT_RADIUS_KM = 25
MAX_RADIUS_KM = 500

# ═══════════════════════════════════════════════════════════════════════════════
# CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════════════════════

# Groq circuit breaker
GROQ_CIRCUIT_FAILURE_THRESHOLD = 3
GROQ_CIRCUIT_COOLDOWN = 30.0

# Redis circuit breaker
REDIS_CIRCUIT_FAILURE_THRESHOLD = 3
REDIS_CIRCUIT_COOLDOWN = 30.0