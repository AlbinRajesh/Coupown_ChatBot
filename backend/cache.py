"""
Redis caching layer with fixes:
1. No double-Redis-call on falsy values (returns tuple)
2. Safe Request object detection (uses isinstance)
3. Clear cache key generation
"""

import redis.asyncio as aioredis
import json
import logging
import time
import asyncio
from functools import wraps
from typing import Optional, Any, Tuple
from config import config
from constants import CACHE_DEFAULT_TTL
import redis as _redis_sync

# Sane defaults and limits
MAX_CACHE_KEY_LENGTH = 200
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 0.2

_sync_redis_pool = _redis_sync.Redis(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    db=config.REDIS_DB,
    decode_responses=True,
    socket_connect_timeout=5,
    connection_pool=_redis_sync.ConnectionPool(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        decode_responses=True,
        max_connections=30,    # ← sync gets its own 30
    )
)
logger = logging.getLogger(__name__)

# In-memory circuit breaker to avoid hammering Redis when it's down
_redis_consecutive_failures = 0
_redis_circuit_open_until = 0.0
REDIS_CIRCUIT_COOLDOWN = 30.0  # seconds

# ── Redis Connection (Async) ────────────────────────────────
redis_client = None

async def get_redis_client():
    """Get or create async Redis client"""
    global redis_client
    if redis_client is None:
        # Circuit-breaker: if Redis has been failing recently, skip attempts
        global _redis_consecutive_failures, _redis_circuit_open_until
        now = time.time()
        if _redis_consecutive_failures >= 3 and now < _redis_circuit_open_until:
            logger.debug("Redis circuit open — skipping connection attempt")
            return None

        backoff = RETRY_BACKOFF_BASE
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                redis_client = aioredis.Redis(
                    host=config.REDIS_HOST,
                    port=config.REDIS_PORT,
                    db=config.REDIS_DB,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    health_check_interval=30,
                    max_connections=50,        # ← async gets 50 (handles concurrent requests)
                )

                await redis_client.ping()
                logger.info(f"✅ Redis connected (async): {config.get_redis_url()}")
                _redis_consecutive_failures = 0
                _redis_circuit_open_until = 0.0
                break
            except Exception as e:
                logger.warning(f"Redis connection attempt {attempt} failed: {e}")
                redis_client = None
                _redis_consecutive_failures += 1
                backoff *= 2
                await asyncio.sleep(backoff)

        # If still not connected, open circuit for cooldown
        if redis_client is None:
            _redis_circuit_open_until = time.time() + REDIS_CIRCUIT_COOLDOWN
            logger.warning(f"⚠️ Redis unavailable after {RETRY_ATTEMPTS} attempts. Caching disabled for {REDIS_CIRCUIT_COOLDOWN}s.")
    return redis_client


# ── Cache Key Generation ────────────────────────────────
def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate a cache key from function arguments.

    FIX 1: Uses isinstance() for safe Request detection instead of string matching
    FIX 2: Request objects always excluded (prevents cache key collisions)
    
    Args:
        prefix: Cache key prefix (e.g., "search", "categories")
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Cache key string
    """
    from starlette.requests import Request
    
    key_parts = [prefix]

    # Add positional arguments
    for arg in args:
        # FIX: Safe Request detection using isinstance
        if isinstance(arg, Request):
            continue

        if arg is not None:
            # Convert objects to string representation
            if isinstance(arg, (dict, list)):
                arg = json.dumps(arg, sort_keys=True, default=str)
            key_parts.append(str(arg))

    # Add keyword arguments (sorted for consistency)
    for k, v in sorted(kwargs.items()):
        # FIX: Also skip Request objects passed as kwargs
        if isinstance(v, Request):
            continue

        if v is not None:
            if isinstance(v, (dict, list)):
                v = json.dumps(v, sort_keys=True, default=str)
            key_parts.append(f"{k}:{v}")

    raw = "|".join(key_parts)
    # sanitize whitespace and limit length to avoid excessively long keys
    raw = raw.replace("\n", " ").replace("\r", " ")
    if len(raw) > MAX_CACHE_KEY_LENGTH:
        # Truncate and append hash fragment for uniqueness
        import hashlib
        h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        raw = raw[: (MAX_CACHE_KEY_LENGTH - 9)].rstrip() + "~" + h
    return raw


# ── Async Cache Operations ────────────────────────────────

async def _cache_get_with_flag(key: str) -> Tuple[bool, Optional[Any]]:
    """
    Get value from cache AND check if key exists.
    
    FIX: Returns tuple (exists, value) to avoid double-Redis-call
    This solves the problem where falsy values ([], 0, False, "")
    would trigger an extra cache_exists() call.
    
    Args:
        key: Cache key
        
    Returns:
        (exists: bool, value: Any | None)
        - exists=True, value=None: Key exists but value is None
        - exists=False, value=None: Key doesn't exist
        - exists=True, value=X: Key exists, deserialized value
    """
    if not config.ENABLE_CACHE:
        return (False, None)

    client = await get_redis_client()
    if not client:
        return (False, None)

    backoff = RETRY_BACKOFF_BASE
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            cached = await client.get(key)
            if cached is not None:
                logger.debug(f"Cache HIT: {key}")
                return (True, json.loads(cached))
            # Key doesn't exist
            return (False, None)
        except Exception as e:
            logger.debug(f"Cache read attempt {attempt} failed: {e}")
            await asyncio.sleep(backoff)
            backoff *= 2

    logger.warning(f"Cache read failed after {RETRY_ATTEMPTS} attempts: {key}")
    return (False, None)


async def cache_set(key: str, value: Any, ttl: int = CACHE_DEFAULT_TTL) -> bool:
    """
    Set value in cache (async)
    
    Args:
        key: Cache key
        value: Value to cache (must be JSON serializable)
        ttl: Time to live in seconds
        
    Returns:
        True if successful
    """
    if not config.ENABLE_CACHE:
        return False

    client = await get_redis_client()
    if not client:
        return False

    backoff = RETRY_BACKOFF_BASE
    if hasattr(value, "dict"):
        value = value.dict()
    payload = json.dumps(value, default=str, separators=(",", ":"))
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            await client.setex(key, int(ttl or CACHE_DEFAULT_TTL), payload)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.debug(f"Cache write attempt {attempt} failed: {e}")
            await asyncio.sleep(backoff)
            backoff *= 2

    logger.warning(f"Cache write failed after {RETRY_ATTEMPTS} attempts: {key}")
    return False


async def cache_delete(key: str) -> bool:
    """
    Delete value from cache (async)
    
    Args:
        key: Cache key
        
    Returns:
        True if successful
    """
    try:
        client = await get_redis_client()
        if not client:
            return False

        result = await client.delete(key)
        logger.debug(f"Cache DELETE: {key}")
        return result > 0
    except Exception as e:
        logger.warning(f"Cache delete failed: {e}")
        return False


async def cache_invalidate_pattern(pattern: str) -> int:
    """
    Delete all keys matching pattern (async)
    
    Uses SCAN instead of KEYS to avoid blocking Redis on large keyspace.
    KEYS is O(N) blocking scan; SCAN is lazy iterator.
    
    Args:
        pattern: Pattern to match (e.g., "search|*")
        
    Returns:
        Number of keys deleted
    """
    try:
        client = await get_redis_client()
        if not client:
            return 0

        keys = []
        async for key in client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            # chunk deletes to avoid too large multi-delete calls
            deleted_total = 0
            chunk = 100
            for i in range(0, len(keys), chunk):
                batch = keys[i:i+chunk]
                deleted = await client.delete(*batch)
                deleted_total += deleted or 0
            logger.info(f"Cache invalidated: {deleted_total} keys matching '{pattern}'")
            return deleted_total
    except Exception as e:
        logger.warning(f"Cache invalidation failed: {e}")

    return 0


# ── Cache Decorators ────────────────────────────────

def cache_result(ttl: int = CACHE_DEFAULT_TTL, prefix: str = "cache"):
    """Sync version of cache decorator"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not config.ENABLE_CACHE:
                return func(*args, **kwargs)
            
            cache_key = generate_cache_key(prefix, *args, **kwargs)
            
            try:
                cached = None
                try:
                    cached = _sync_redis_pool.get(cache_key)
                except Exception as e:
                    logger.debug(f"Sync cache read failed: {e}")

                if cached is not None:
                    logger.debug(f"Cache HIT: {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Cache read failed (sync, decode): {e}")

            logger.debug(f"Cache MISS: {cache_key}")
            result = func(*args, **kwargs)

            try:
                try:
                    _sync_redis_pool.setex(cache_key, int(ttl or CACHE_DEFAULT_TTL), json.dumps(result, default=str, separators=(",", ":")))
                    logger.debug(f"Cache SET: {cache_key} (TTL: {ttl}s)")
                except Exception as e:
                    logger.debug(f"Sync cache write failed: {e}")
            except Exception as e:
                logger.warning(f"Cache write failed (sync, encode): {e}")

            return result
        
        return wrapper
    
    return decorator


def cache_result_async(ttl: int = CACHE_DEFAULT_TTL, prefix: str = "cache", return_type=None):
    """
    Async cache decorator.
    
    FIX: Uses the tuple-returning _cache_get_with_flag() to avoid
    double-Redis-call on falsy values ([], 0, False, "").
    
    Usage:
        @cache_result_async(ttl=600, prefix="search")
        async def get_search_results(query, lat, lng):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not config.ENABLE_CACHE:
                return await func(*args, **kwargs)

            cache_key = generate_cache_key(prefix, *args, **kwargs)
            exists, cached_result = await _cache_get_with_flag(cache_key)

            if exists:
                logger.debug(f"Cache HIT: {cache_key}")
                # ← Reconstruct the model if return_type given
                if return_type and isinstance(cached_result, dict):
                    return return_type(**cached_result)
                return cached_result

            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)
            # Store as dict so it's JSON-serializable
            await cache_set(
                cache_key,
                result.dict() if hasattr(result, "dict") else result,
                ttl
            )
            return result

        return wrapper
    return decorator


# ── Cache Statistics ────────────────────────────────
async def get_cache_stats() -> dict:
    """Get cache statistics (async)"""
    try:
        client = await get_redis_client()
        if not client:
            return {"status": "disabled"}
        
        info = await client.info()
        dbsize = await client.dbsize()
        return {
            "status": "connected",
            "memory_used_mb": info.get("used_memory_human", "unknown"),
            "keys_count": dbsize,
            "evicted_keys": info.get("evicted_keys", 0),
        }
    except Exception as e:
        logger.warning(f"Failed to get cache stats: {e}")
        return {"status": "error", "error": str(e)}