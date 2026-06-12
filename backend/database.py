import threading
"""
Database connection pool management
Handles MySQL connections with pooling for production scalability.

Architecture for 10,000 concurrent users:
- Async path  (FastAPI request handlers): aiomysql pool, maxsize=100
  One event-loop thread serves all concurrent requests; no thread overhead.

- Sync path   (APScheduler background jobs, sync_manage.py): mysql.connector
  pool, pool_size=10. Background jobs are low-frequency, so a small sync
  pool is sufficient and doesn't waste MySQL connections.

- Both pools are lazy-initialized on first use, so import never touches
  MySQL. This fixes the Docker startup race condition where the API container
  starts before MySQL is fully accepting remote connections.

- Exponential-backoff retry on pool creation so a slow MySQL start doesn't
  permanently break the API ΓÇö it just waits and retries.

MySQL server must be configured to allow enough connections:
    max_connections = 200   (async pool 100 + sync pool 10 + headroom)
    wait_timeout    = 600
    interactive_timeout = 600
This is already set in docker-compose.yml (--max_connections=300).
"""

import os
import asyncio
import logging
import time
from contextlib import contextmanager
from typing import Optional
from constants import DB_POOL_ACQUIRE_TIMEOUT, DB_QUERY_TIMEOUT

import aiomysql
from mysql.connector import pooling, Error as MySQLError
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

_DB_HOST     = os.getenv("DB_HOST", "localhost")
_DB_PORT     = int(os.getenv("DB_PORT", 3306))
_DB_USER     = os.getenv("DB_USER", "root")
_DB_PASSWORD = os.getenv("DB_PASSWORD", "")
_DB_NAME     = os.getenv("DB_NAME", "shop_db")

# Async pool: handles all FastAPI request-time queries.
# Rule of thumb: ~1 connection per 100 concurrent users at typical query
# latency (5-20 ms). 10 k users with p95 latency ~10 ms ΓåÆ ~100 connections.
ASYNC_POOL_MIN  = 10
ASYNC_POOL_MAX  = 100

# Sync pool: only used by background jobs (APScheduler / sync_manage.py).
# These are infrequent, so a small pool avoids wasting MySQL connections.
SYNC_POOL_SIZE  = 10

# Retry settings for pool initialization
_MAX_RETRIES    = 10
_RETRY_BASE     = 1.0   # seconds ΓÇö doubles each attempt (1, 2, 4 ΓÇª 512)
_RETRY_CAP      = 30.0  # maximum wait between retries

_aiomysql_pool: Optional[aiomysql.Pool] = None
# Lock is created lazily inside the running event loop to avoid the
# "attached to a different loop" error that occurs when asyncio.Lock()
# is called at module level (Python < 3.10 issue).
_pool_create_lock: Optional[asyncio.Lock] = None






def _get_pool_lock() -> asyncio.Lock:
    """Return the module-level lock, creating it inside the running loop."""
    global _pool_create_lock
    if _pool_create_lock is None:
        _pool_create_lock = asyncio.Lock()
    return _pool_create_lock


async def _create_aiomysql_pool() -> aiomysql.Pool:
    """
    Create the aiomysql pool with exponential-backoff retry.
    Retries up to _MAX_RETRIES times so a slow MySQL startup doesn't
    permanently break the API.
    """
    attempt = 0
    delay = _RETRY_BASE
    while True:
        try:
            pool = await aiomysql.create_pool(
                host=_DB_HOST,
                port=_DB_PORT,
                user=_DB_USER,
                password=_DB_PASSWORD,
                db=_DB_NAME,
                autocommit=True,
                connect_timeout=10,
                # Keep idle connections alive; MySQL default wait_timeout=28800s
                # so pinging every 300 s is safe.
                echo=False,
                minsize=ASYNC_POOL_MIN,
                maxsize=ASYNC_POOL_MAX,
            )
            logger.info(
                "Γ£à aiomysql pool ready "
                f"(min={ASYNC_POOL_MIN}, max={ASYNC_POOL_MAX})"
            )
            return pool
        except Exception as exc:
            attempt += 1
            if attempt >= _MAX_RETRIES:
                logger.critical(
                    f"Γ¥î Could not connect to MySQL after {_MAX_RETRIES} "
                    f"attempts: {exc}"
                )
                raise
            logger.warning(
                f"ΓÜá∩╕Å  MySQL not ready (attempt {attempt}/{_MAX_RETRIES}): "
                f"{exc} ΓÇö retrying in {delay:.0f}s"
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, _RETRY_CAP)




async def get_async_pool() -> aiomysql.Pool:
    """Return the shared aiomysql pool, initializing it on the first call."""
    global _aiomysql_pool
    if _aiomysql_pool is not None and not _aiomysql_pool._closing:
        return _aiomysql_pool
    async with _get_pool_lock():
        if _aiomysql_pool is None or _aiomysql_pool._closing:
            _aiomysql_pool = await _create_aiomysql_pool()
    return _aiomysql_pool


async def _validate_async_connection(conn) -> bool:
    """Check if async connection is alive. Returns True if connected."""
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1")
        return True
    except Exception as e:
        logger.warning(f"Connection validation failed: {e}")
        return False



async def close_async_pool() -> None:
    """Gracefully close the async pool. Call from app shutdown handler."""
    global _aiomysql_pool
    if _aiomysql_pool is not None:
        _aiomysql_pool.close()
        await _aiomysql_pool.wait_closed()
        _aiomysql_pool = None
        logger.info("Γ£à aiomysql pool closed")


_sync_pool: Optional[pooling.MySQLConnectionPool] = None
_sync_pool_lock = None  # threading.Lock ΓÇö created lazily


_sync_pool_lock = threading.Lock()
def _get_sync_lock():
    return _sync_pool_lock


def _create_sync_pool() -> pooling.MySQLConnectionPool:
    """Create the sync mysql.connector pool with retry."""
    attempt = 0
    delay = _RETRY_BASE
    while True:
        try:
            pool = pooling.MySQLConnectionPool(
                pool_name="shop_sync_pool",
                pool_size=SYNC_POOL_SIZE,
                pool_reset_session=True,
                host=_DB_HOST,
                port=_DB_PORT,
                user=_DB_USER,
                password=_DB_PASSWORD,
                database=_DB_NAME,
                autocommit=True,
                connection_timeout=10,
                auth_plugin="mysql_native_password",
            )
            logger.info(f"Γ£à Sync MySQL pool ready (size={SYNC_POOL_SIZE})")
            return pool
        except MySQLError as exc:
            attempt += 1
            if attempt >= _MAX_RETRIES:
                logger.critical(
                    f"Γ¥î Could not create sync MySQL pool after "
                    f"{_MAX_RETRIES} attempts: {exc}"
                )
                raise
            logger.warning(
                f"ΓÜá∩╕Å  Sync pool creation failed (attempt {attempt}/"
                f"{_MAX_RETRIES}): {exc} ΓÇö retrying in {delay:.0f}s"
            )
            time.sleep(delay)
            delay = min(delay * 2, _RETRY_CAP)


def get_sync_pool() -> pooling.MySQLConnectionPool:
    """Return the shared sync pool, initializing it on the first call."""
    global _sync_pool
    if _sync_pool is not None:
        return _sync_pool
    with _get_sync_lock():
        if _sync_pool is None:
            _sync_pool = _create_sync_pool()
    return _sync_pool


@contextmanager
def get_db_connection():
    """
    Yield a validated sync connection from the pool.
    Ensures the connection is live before handing it to the caller.
    Always returns the connection to the pool on exit.
    """
    conn = None
    try:
        conn = get_sync_pool().get_connection()
        # Validate the connection is still alive (guards against stale
        # connections that stayed idle past MySQL's wait_timeout).
        if not conn.is_connected():
            conn.reconnect(attempts=3, delay=1)
        yield conn
    except MySQLError as exc:
        logger.error(f"Database connection error: {exc}")
        raise
    finally:
        try:
            if conn is not None and conn.is_connected():
                conn.close()  # returns to pool
        except Exception:
            pass


def fetch_one(query: str, params: tuple = None):
    """Fetch a single row (synchronous). For background jobs only."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(query, params or ())
                result = cursor.fetchone()
                # ✅ FIX: Consume all remaining rows to prevent "Unread result found" error
                while cursor.fetchone():
                    pass
                return result
    except MySQLError as exc:
        logger.error(f"fetch_one error: {exc} | query={query}")
        raise


def fetch_all(query: str, params: tuple = None):
    """Fetch all rows (synchronous). For background jobs only."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(query, params or ())
                return cursor.fetchall()
    except MySQLError as exc:
        logger.error(f"fetch_all error: {exc} | query={query}")
        raise


def execute_query(query: str, params: tuple = None) -> int:
    """
    Execute an INSERT / UPDATE / DELETE (synchronous).
    Returns the number of affected rows.
    For background jobs only.
    """
    try:
        with get_db_connection() as conn:
            conn.start_transaction()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, params or ())
                    affected = cursor.rowcount
                conn.commit()
                logger.debug(f"execute_query: {affected} rows affected")
                return affected
            except MySQLError:
                conn.rollback()
                raise
    except MySQLError as exc:
        logger.error(f"execute_query error: {exc} | query={query}")
        raise


async def fetch_one_async(query: str, params: tuple = None):
    """
    Async fetch of a single row via aiomysql.
    FIX: Now validates connection is alive before using it.
    """
    pool = await get_async_pool()
    try:
        async with asyncio.timeout(DB_POOL_ACQUIRE_TIMEOUT):
            async with pool.acquire() as conn:
                # FIX: Validate connection is alive
                if not await _validate_async_connection(conn):
                    logger.warning("Connection invalid, reconnecting...")
                    # Get a fresh connection
                    async with pool.acquire() as conn2:
                        async with asyncio.timeout(DB_QUERY_TIMEOUT):
                            async with conn2.cursor(aiomysql.DictCursor) as cursor:
                                await cursor.execute(query, params or ())
                                return await cursor.fetchone()
                
                async with asyncio.timeout(DB_QUERY_TIMEOUT):
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(query, params or ())
                        return await cursor.fetchone()
    except asyncio.TimeoutError:
        logger.error(f"fetch_one_async timeout: {query[:50]}")
        raise

async def fetch_all_async(query: str, params: tuple = None):
    """
    Async fetch of all rows via aiomysql.
    FIX: Now validates connection is alive before using it.
    """
    pool = await get_async_pool()
    try:
        async with asyncio.timeout(DB_POOL_ACQUIRE_TIMEOUT):
            async with pool.acquire() as conn:
                # FIX: Validate connection is alive
                if not await _validate_async_connection(conn):
                    logger.warning("Connection invalid, reconnecting...")
                    async with pool.acquire() as conn2:
                        async with asyncio.timeout(DB_QUERY_TIMEOUT):
                            async with conn2.cursor(aiomysql.DictCursor) as cursor:
                                await cursor.execute(query, params or ())
                                return await cursor.fetchall()
                
                async with asyncio.timeout(DB_QUERY_TIMEOUT):
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(query, params or ())
                        return await cursor.fetchall()
    except asyncio.TimeoutError:
        logger.error(f"fetch_all_async timeout: {query[:50]}")
        raise


async def execute_query_async(query: str, params: tuple = None) -> int:
    """
    Async INSERT / UPDATE / DELETE via aiomysql.
    FIX: Now validates connection is alive before using it.
    """
    pool = await get_async_pool()
    try:
        async with asyncio.timeout(DB_POOL_ACQUIRE_TIMEOUT):
            async with pool.acquire() as conn:
                # FIX: Validate connection is alive
                if not await _validate_async_connection(conn):
                    logger.warning("Connection invalid, reconnecting...")
                    async with pool.acquire() as conn2:
                        await conn2.begin()
                        try:
                            async with asyncio.timeout(DB_QUERY_TIMEOUT):
                                async with conn2.cursor() as cursor:
                                    await cursor.execute(query, params or ())
                                    affected = cursor.rowcount
                            await conn2.commit()
                            logger.debug(f"execute_query_async: {affected} rows affected")
                            return affected
                        except Exception:
                            await conn2.rollback()
                            raise
                
                async with asyncio.timeout(DB_QUERY_TIMEOUT):
                    await conn.begin()
                    try:
                        async with conn.cursor() as cursor:
                            await cursor.execute(query, params or ())
                            affected = cursor.rowcount
                        await conn.commit()
                        logger.debug(f"execute_query_async: {affected} rows affected")
                        return affected
                    except Exception:
                        await conn.rollback()
                        raise
    except asyncio.TimeoutError:
        logger.error(f"execute_query_async timeout: {query[:50]}")
        raise


async def bulk_insert_async(query: str, params_list: list) -> int:
    """
    Execute a batch INSERT using executemany.
    FIX: Now validates connection is alive before using it.
    """
    if not params_list:
        return 0
    pool = await get_async_pool()
    try:
        async with asyncio.timeout(DB_POOL_ACQUIRE_TIMEOUT):
            async with pool.acquire() as conn:
                # CORRECT — conn2 branch should be
                if not await _validate_async_connection(conn):
                    async with pool.acquire() as conn2:
                        await conn2.begin()
                        try:
                            async with asyncio.timeout(max(DB_QUERY_TIMEOUT, DB_QUERY_TIMEOUT * len(params_list) / 100)):
                                async with conn2.cursor() as cursor:    # ← define cursor
                                    await cursor.executemany(query, params_list)
                                    affected = cursor.rowcount
                            await conn2.commit()
                            logger.debug(f"bulk_insert_async: {affected} rows affected")
                            return affected
                        except Exception:
                            await conn2.rollback()
                            raise
                
                async with asyncio.timeout(max(DB_QUERY_TIMEOUT, DB_QUERY_TIMEOUT * len(params_list) / 100)):
                    await conn.begin()
                    try:
                        async with conn.cursor() as cursor:
                            await cursor.executemany(query, params_list)
                            affected = cursor.rowcount
                        await conn.commit()
                        logger.debug(f"bulk_insert_async: {affected} rows affected")
                        return affected
                    except Exception:
                        await conn.rollback()
                        raise
    except asyncio.TimeoutError:
        logger.error(f"bulk_insert_async timeout: {len(params_list)} rows")
        raise


def health_check() -> bool:
    """Sync health check for the /health endpoint."""
    try:
        result = fetch_one("SELECT 1 AS status")
        return result is not None
    except Exception as exc:
        logger.error(f"Sync DB health check failed: {exc}")
        return False


async def health_check_async() -> bool:
    """Async health check ΓÇö use this from async /health handlers."""
    try:
        result = await fetch_one_async("SELECT 1 AS status")
        return result is not None
    except Exception as exc:
        logger.error(f"Async DB health check failed: {exc}")
        return False


def get_pool_stats() -> dict:
    """
    Return current pool utilization. Wire this into your /metrics endpoint
    so you can see if the pool is saturated under load.
    """
    stats = {}
    if _aiomysql_pool is not None:
        stats["async"] = {
            "size":      _aiomysql_pool.size,
            "free":      _aiomysql_pool.freesize,
            "acquired":  _aiomysql_pool.size - _aiomysql_pool.freesize,
            "max":       ASYNC_POOL_MAX,
        }
    if _sync_pool is not None:
        stats["sync"] = {"pool_size": SYNC_POOL_SIZE}
    return stats
