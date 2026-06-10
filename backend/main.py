"""
main.py
───────
Shop Chatbot API — FastAPI application entry point.

This file is intentionally thin. Its only jobs are:
  1. App setup   — FastAPI instance, middleware, exception handlers
  2. Lifespan    — scheduler start/stop, DB pool cleanup
  3. Routes      — parse request → call handler → return response
  4. Legacy      — backwards-compatible /api/* aliases

All business logic lives elsewhere:
  intent.py       → query parsing, casual guard, circuit breaker
  handlers.py     → one handler per intent, search dispatch
  search.py       → all Typesense queries
  enrichment.py   → offer attachment, smart fallback, result messages
  models.py       → request/response shapes, build_response()
  chat_context.py → data block builder for /chat endpoint
"""

import asyncio
import signal
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import os

from config import config
from database import close_async_pool, execute_query_async, fetch_all, get_pool_stats, health_check_async
from cache import get_cache_stats
from logging_config import configure_logging, get_logger
from sync_manage import get_queue_stats
from sync_routes import router as sync_router

from model import (
    ChatMessage, ChatRequest, ChatResponse,
    JobSearchRequest, SearchRequest, SearchResponse, SmartRequest,
    build_response, error_response, timeout_response,
)
from intent import get_intent
from handlers import handle_search
from chat_context import build_chat_context
from prompts import get_chat_system_prompt
from clients import groq_client
from search import search_jobs_typesense
from enrichment import build_result_message

# ── Logging ────────────────────────────────────────────────────────────────────
configure_logging()
logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# GROQ CHAT HELPER
# ═══════════════════════════════════════════════════════════════════════════════

async def _groq_chat(messages: list, max_tokens: int = 200) -> str:
    """Non-blocking Groq call. Hard timeout 12s. Raises on failure."""
    def _call():
        return groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0,
            timeout=10,
        ).choices[0].message.content.strip()

    return await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(None, _call),
        timeout=12.0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════════════════════

async def _job_sync_queue():
    try:
        result = await asyncio.to_thread(process_sync_queue)
        if result.get("processed", 0) > 0:
            logger.info(f"Sync queue: {result}")
    except Exception as e:
        logger.error(f"Sync queue job failed: {e}")

async def _job_full_sync():
    try:
        await asyncio.to_thread(sync_all_shops)
        await asyncio.to_thread(sync_all_jobs)
        await asyncio.to_thread(sync_all_products)
        await asyncio.to_thread(sync_all_services)
    except Exception as e:
        logger.error(f"Full sync failed: {e}")

async def _job_update_ratings():
    try:
        await asyncio.to_thread(update_all_ratings)
    except Exception as e:
        logger.error(f"Rating update failed: {e}")

async def _job_cleanup_queue():
    try:
        await execute_query_async(
            """
            DELETE FROM typesense_sync_queue
            WHERE status = 'synced'
              AND synced_at < DATE_SUB(NOW(), INTERVAL 7 DAY)
            """
        )
        logger.info("Sync queue cleanup done")
    except Exception as e:
        logger.error(f"Queue cleanup failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# LIFESPAN
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Backend starting — HTTP only")
    yield
    await close_async_pool()
    logger.info("Shutdown complete")


# ═══════════════════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title       = "Shop Chatbot API",
    version     = "3.0.0",
    description = "Local shop discovery with AI-powered intent routing",
    lifespan    = lifespan,
)


app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins     = config.ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["GET", "POST"],
    allow_headers     = ["Content-Type"],
)


ENV = os.getenv("APP_ENV", "production")
app.state.limiter = limiter = Limiter(key_func=get_remote_address)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"success": False, "message": "Too many requests. Please wait and try again."},
    )


@app.middleware("http")
async def _add_request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


app.include_router(sync_router)


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    db_ok = await health_check_async()
    return {
        "status":     "ok" if db_ok else "degraded",
        "database":   "connected" if db_ok else "disconnected",
        "pool":       get_pool_stats(),
        "sync_queue": get_queue_stats(),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }




@app.get("/metrics")
async def metrics():
    """Prometheus-style metrics for monitoring pool saturation, cache, etc."""
    pool   = get_pool_stats()
    cache  = await get_cache_stats()
    async_pool = pool.get("async", {})

    lines = [
        "# HELP db_pool_size Total async DB connections",
        "# TYPE db_pool_size gauge",
        f"db_pool_size {async_pool.get('size', 0)}",

        "# HELP db_pool_acquired Connections currently in use",
        "# TYPE db_pool_acquired gauge",
        f"db_pool_acquired {async_pool.get('acquired', 0)}",

        "# HELP db_pool_free Free connections in pool",
        "# TYPE db_pool_free gauge",
        f"db_pool_free {async_pool.get('free', 0)}",

        "# HELP db_pool_max Max pool size",
        "# TYPE db_pool_max gauge",
        f"db_pool_max {async_pool.get('max', 0)}",

        "# HELP cache_keys_total Total keys in Redis cache",
        "# TYPE cache_keys_total gauge",
        f"cache_keys_total {cache.get('keys_count', 0)}",

        "# HELP cache_evicted_keys_total Evicted keys (memory pressure indicator)",
        "# TYPE cache_evicted_keys_total counter",
        f"cache_evicted_keys_total {cache.get('evicted_keys', 0)}",
    ]

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines), media_type="text/plain; version=0.0.4")
# ═══════════════════════════════════════════════════════════════════════════════
# API v1 ROUTES
# Each route: parse → call → return. No business logic.
# ═══════════════════════════════════════════════════════════════════════════════

api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get("/categories")
@limiter.limit("100/minute")
async def list_categories(request: Request):
    try:
        cats = await asyncio.to_thread(
            fetch_all,
            "SELECT id, categoriesname, category_pic FROM categories WHERE visible_status = 1",
        )
        return {"success": True, "categories": cats or []}
    except Exception as e:
        logger.error(f"list_categories: {e}")
        return {"success": False, "categories": []}


@api_v1.get("/subcategories")
@limiter.limit("100/minute")
async def list_subcategories(request: Request, category_id: int):
    try:
        subs = await asyncio.to_thread(
            fetch_all,
            "SELECT id, subcategoryname, subcat_img FROM subcategories "
            "WHERE category_id = %s AND visible_status = 1",
            (category_id,),
        )
        return {"success": True, "subcategories": subs or []}
    except Exception as e:
        logger.error(f"list_subcategories: {e}")
        return {"success": False, "subcategories": []}


@api_v1.post("/search", response_model=SearchResponse)
@limiter.limit("30/second")

async def search(req: SearchRequest, request: Request):
    rid = request.state.request_id
    try:
        parsed = await get_intent(req.query)
        logger.info(
            "Search: intent=%s type=%s cat='%s' name='%s'",
            parsed.intent, parsed.search_type, parsed.category, parsed.name,
            extra={"request_id": rid},
        )
        return await handle_search(parsed, req)
    except asyncio.TimeoutError:
        return timeout_response()
    except Exception as e:
        logger.error(f"Search error: {e}", extra={"request_id": rid}, exc_info=True)
        return error_response()


@api_v1.post("/search/jobs")
@limiter.limit("20/minute")
async def search_jobs_endpoint(req: JobSearchRequest, request: Request):
    rid = request.state.request_id
    try:
        if req.query.strip():
            parsed   = await get_intent(req.query)
            keywords = parsed.keywords or [req.query.strip().lower()]
        else:
            keywords = ["*"]

        jobs = (await asyncio.wait_for(
            asyncio.to_thread(
                search_jobs_typesense,
                tuple(keywords), req.userLat, req.userLng, req.limit,
            ),
            timeout=10.0,
        ))["jobs"]

        if not jobs:
            suffix = f" for '{req.query}'" if req.query.strip() else ""
            return build_response(
                success       = False,
                message       = f"No active job openings found{suffix}.",
                is_job_search = True,
            )
        return build_response(
            success       = True,
            message       = build_result_message(jobs, context="job"),
            is_job_search = True,
            results       = jobs,
        )
    except asyncio.TimeoutError:
        return timeout_response()
    except Exception as e:
        logger.error(f"Job search error: {e}", extra={"request_id": rid}, exc_info=True)
        return error_response()


@api_v1.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(req: ChatRequest, request: Request):
    rid = request.state.request_id
    try:
        if not req.messages:
            return ChatResponse(success=False, reply="Say something — I'm here to help you find local shops.")

        last_msg   = req.messages[-1].content
        parsed     = await get_intent(last_msg)
        data_block = await build_chat_context(
            query=last_msg, parsed=parsed,
            user_lat=req.userLat, user_lng=req.userLng, radius_km=req.radiusKm,
        )

        messages = [{"role": "system", "content": get_chat_system_prompt()}]
        for i, m in enumerate(req.messages):
            is_last_user = (i == len(req.messages) - 1 and m.role == "user")
            messages.append({"role": m.role, "content": m.content + (data_block if is_last_user else "")})

        try:
            reply = await _groq_chat(messages, max_tokens=200)
        except Exception as e:
            logger.error(f"Groq chat error: {e}", extra={"request_id": rid})
            reply = "Sorry, I'm having trouble right now. Please try again."

        return ChatResponse(success=True, reply=reply)

    except Exception as e:
        logger.error(f"Chat error: {e}", extra={"request_id": rid}, exc_info=True)
        return ChatResponse(success=False, reply="An error occurred. Please try again.")





@api_v1.get("/sync/status")
async def sync_status():
    return {"success": True, "sync_stats": get_queue_stats()}


app.include_router(api_v1)


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY ROUTES — backwards compatibility only, delegate to v1
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/smart")
@limiter.limit("30/minute")
async def smart_legacy(req: SmartRequest, request: Request):
    return await smart(req, request)

@app.post("/api/search")
@limiter.limit("200/minute" if os.getenv("APP_ENV") != "production" else "100/minute")
async def search_legacy(req: SearchRequest, request: Request):
    return await search(req, request)

@app.post("/api/search/jobs")
@limiter.limit("20/minute")
async def search_jobs_legacy(req: JobSearchRequest, request: Request):
    return await search_jobs_endpoint(req, request)

@app.post("/api/chat")
@limiter.limit("30/minute")
async def chat_legacy(req: ChatRequest, request: Request):
    return await chat(req, request)

@app.get("/api/categories")
@limiter.limit("100/minute")
async def categories_legacy(request: Request):
    return await list_categories(request)

@app.get("/api/subcategories")
@limiter.limit("100/minute")
async def subcategories_legacy(request: Request, category_id: int):
    return await list_subcategories(request, category_id)


# ═══════════════════════════════════════════════════════════════════════════════
# SHUTDOWN
# ═══════════════════════════════════════════════════════════════════════════════

signal.signal(signal.SIGINT,  lambda s, f: logger.info(f"Signal {s} — shutting down"))
signal.signal(signal.SIGTERM, lambda s, f: logger.info(f"Signal {s} — shutting down"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host      = config.HOST,
        port      = config.PORT,
        workers   = config.WORKERS if not config.DEBUG else 1,
        reload    = config.DEBUG,
        log_level = config.LOG_LEVEL.lower(),
    )