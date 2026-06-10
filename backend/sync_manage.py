"""
sync_manage.py
──────────────
Typesense sync layer.

All SQL queries and document builders are imported from typesense_setup.py
to avoid duplication and schema mismatches.

Sync paths:
  Fast   → webhook  POST /internal/sync/{entity}/{id}   (<1 s)
  Safety → APScheduler every 60 s  process_sync_queue()
  Full   → APScheduler every 1 h   sync_all_*()
  Orphan → inside sync_all_*(), uses export() not search()
"""

from __future__ import annotations

import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import typesense.exceptions

# ── Import everything from typesense_setup — single source of truth ──────────
from typesense_setup import (
    client as ts_client,
    build_shop_doc,
    build_job_doc,
    build_product_doc,
    build_service_doc,
    SHOP_JOIN_SQL,
    SHOP_JOIN_BY_ID_SQL,
    JOB_JOIN_SQL,
    JOB_JOIN_BY_ID_SQL,
    PRODUCT_JOIN_SQL,
    PRODUCT_JOIN_BY_ID_SQL,
    SERVICE_JOIN_SQL,
    SERVICE_JOIN_BY_ID_SQL,
)

from cache import cache_invalidate_pattern
from database import execute_query, fetch_all, fetch_one, get_db_connection
from resilience import retry_with_backoff

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

MAX_RETRY_COUNT  = 5
QUEUE_BATCH_SIZE = 100


# ═══════════════════════════════════════════════════════════════════════════════
# DELETE HELPERS  (idempotent — ObjectNotFound is not an error)
# ═══════════════════════════════════════════════════════════════════════════════

def _invalidate_all_search_caches() -> None:
    """Invalidate all search cache prefixes. Called after every webhook sync."""
    try:
        loop = asyncio.get_running_loop()
        for p in (
            "geo_search|*", "product_search|*",
            "service_search|*", "job_search|*", "rated_search|*",
        ):
            loop.create_task(cache_invalidate_pattern(p))
    except RuntimeError:
        pass
    except Exception as e:
        logger.warning(f"Cache invalidation failed: {e}")


def _delete_doc(collection: str, doc_id: int) -> bool:
    """Delete one document. Returns True even if already absent."""
    try:
        ts_client.collections[collection].documents[str(doc_id)].delete()
        logger.info(f"Deleted {collection}/{doc_id}")
        return True
    except typesense.exceptions.ObjectNotFound:
        logger.debug(f"{collection}/{doc_id} already absent — OK")
        return True
    except Exception as e:
        logger.error(f"Delete {collection}/{doc_id} failed: {e}")
        return False


def _delete_product_docs(identifier: int) -> bool:
    try:
        # Try shop_id first (cascade from shop deletion)
        result = ts_client.collections["products"].documents.delete({
            "filter_by": f"shop_id:={identifier}"
        })
        deleted_count = result.get("num_deleted", 0)
        logger.info(f"Deleted {deleted_count} products by shop_id={identifier}")

        # Also try direct composite IDs (when called with product_id from queue)
        # Export and filter manually since Typesense can't prefix-filter on id
        raw = ts_client.collections["products"].documents.export()
        for line in (raw or "").strip().split("\n"):
            if not line:
                continue
            try:
                doc = json.loads(line)
                if doc.get("id", "").startswith(f"p_{identifier}_"):
                    ts_client.collections["products"].documents[doc["id"]].delete()
                    deleted_count += 1
                    logger.info(f"Deleted product doc {doc['id']}")
            except Exception:
                pass

        logger.info(f"Product cleanup for identifier={identifier}: {deleted_count} total deleted")
        return True
    except Exception as e:
        logger.error(f"Error during product deletion for identifier={identifier}: {e}")
        return False

def _delete_service_docs(identifier: int) -> bool:
    try:
        # Try shop_id first (cascade from shop deletion)
        result = ts_client.collections["services"].documents.delete({
            "filter_by": f"shop_id:={identifier}"
        })
        deleted_count = result.get("num_deleted", 0)
        logger.info(f"Deleted {deleted_count} services by shop_id={identifier}")

        # Fallback: match by composite id prefix (when called with service_id from queue)
        raw = ts_client.collections["services"].documents.export()
        for line in (raw or "").strip().split("\n"):
            if not line:
                continue
            try:
                doc = json.loads(line)
                if doc.get("id", "").startswith(f"s_{identifier}_"):
                    ts_client.collections["services"].documents[doc["id"]].delete()
                    deleted_count += 1
                    logger.info(f"Deleted service doc {doc['id']}")
            except Exception:
                pass

        logger.info(f"Service cleanup for identifier={identifier}: {deleted_count} total deleted")

        try:
            loop = asyncio.get_running_loop()
            _invalidate_all_search_caches()
        except RuntimeError:
            pass

        return True
    except Exception as e:
        logger.error(f"Delete service docs for identifier={identifier} failed: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# INSTANT SYNC  (fast path — called by webhooks, <1 s)
# ═══════════════════════════════════════════════════════════════════════════════

@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(Exception,))
def sync_single_shop(shop_id: int) -> bool:
    row = fetch_one(SHOP_JOIN_BY_ID_SQL, (shop_id,))
    
    # ── PATH A: INACTIVE / UNSUBSCRIBED ──────────────────────────────────────
    if not row or int(row.get("status") or 0) != 1:  
        logger.info(f"Shop {shop_id} inactive/unsubscribed → triggering cascading removal")
        
        # 1. Purge dependent items from other collections first
        _delete_product_docs(shop_id)  # Clears out Jeyaseelan's biryani!
        _delete_service_docs(shop_id)  # Clears out services
        
        # 2. Clear the shop itself and exit early
        return _delete_doc("shops", shop_id)

    # ── PATH B: ACTIVE SUBSCRIBER ───────────────────────────────────────────
    # We only build and upsert the document if the shop successfully passed 
    # the active check above.
    doc = build_shop_doc(row)
    if not doc:
        return False

    try:
        ts_client.collections["shops"].documents.upsert(doc)
        logger.info(f"Synced shop {shop_id}")
        _invalidate_all_search_caches()  # ← add
        return True
    except Exception as e:
        logger.error(f"Upsert shop {shop_id} failed: {e}")
        raise   # Let retry_with_backoff handle it
@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(Exception,))
def sync_single_job(job_id: int) -> bool:
    """Upsert or delete one job. Idempotent."""
    row = fetch_one(JOB_JOIN_BY_ID_SQL, (job_id,))
    if not row:
        logger.info(f"Job {job_id} inactive/unsubscribed → removing from Typesense")
        return _delete_doc("jobs", job_id)

    doc = build_job_doc(row)
    if not doc:
        return False

    try:
        ts_client.collections["jobs"].documents.upsert(doc)
        logger.info(f"Synced job {job_id}")
        return True
    except Exception as e:
        logger.error(f"Upsert job {job_id} failed: {e}")
        raise


@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(Exception,))
def sync_single_product(product_id: int) -> bool:
    rows = fetch_all(PRODUCT_JOIN_BY_ID_SQL, (product_id,))
    if not rows:
        logger.info(f"Product {product_id} inactive/unsubscribed → removing")
        return _delete_product_docs(product_id)

    docs = [build_product_doc(r) for r in rows]
    docs = [d for d in docs if d]  # only filter out None, not has_offer=False
    if not docs:
        logger.info(f"Product {product_id} has no docs → removing")
        return _delete_product_docs(product_id)

    try:
        for doc in docs:
            ts_client.collections["products"].documents.upsert(doc)
        logger.info(f"Synced product {product_id} ({len(docs)} docs)")
        _invalidate_all_search_caches()  # ← add
        return True
    except Exception as e:
        logger.error(f"Upsert product {product_id} failed: {e}")
        raise


@retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(Exception,))
def sync_single_service(service_id: int) -> bool:
    """Upsert or delete all offer docs for a service. Idempotent."""
    rows = fetch_all(SERVICE_JOIN_BY_ID_SQL, (service_id,))
    if not rows:
        return _delete_service_docs(service_id)

    docs = [build_service_doc(r) for r in rows]   # ← this line is missing, add it
    docs = [d for d in docs if d]
    if not docs:
        return _delete_service_docs(service_id)

    docs = [d for d in docs if d.get("has_offer")]
    if not docs:
        return _delete_service_docs(service_id) 

    try:
        for doc in docs:
            ts_client.collections["services"].documents.upsert(doc)
        logger.info(f"Synced service {service_id} ({len(docs)} docs)")
        _invalidate_all_search_caches()  # ← add
        return True
    except Exception as e:
        logger.error(f"Upsert service {service_id} failed: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# QUEUE PROCESSOR  (APScheduler every 60 s)
# ═══════════════════════════════════════════════════════════════════════════════

def process_sync_queue() -> Dict[str, int]:
    """
    Drain pending items from typesense_sync_queue.

    Guarantees:
      - Deduplication by (entity_type, shop_id) — last action wins
      - Row locks released before Typesense I/O (no long transactions)
      - Atomic bulk status update after all I/O completes
      - Cache invalidated once per batch, not per item
      - Exponential backoff via retry_with_backoff on individual syncs
    """
    empty = {
        "processed": 0, "success": 0, "failed": 0,
        "permanently_failed": 0, "skipped": 0,
    }

    try:
        # ── 1. Claim batch (FOR UPDATE SKIP LOCKED prevents double-processing)
        with get_db_connection() as conn:
            conn.autocommit = False
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT id, shop_id, action, entity_type, retry_count
                FROM   typesense_sync_queue
                WHERE  status = 'pending'
                  AND  retry_count < %s
                ORDER  BY created_at ASC
                LIMIT  %s
                FOR UPDATE SKIP LOCKED
                """,
                (MAX_RETRY_COUNT, QUEUE_BATCH_SIZE),
            )
            pending = cur.fetchall()
            cur.close()
            conn.commit()   # release locks before any I/O

        if not pending:
            return empty

        # ── 2. Deduplicate: (entity_type, entity_id) — keep latest action
        seen:        Dict[Tuple[str, int], Dict] = {}
        skipped_ids: List[int] = []

        for item in pending:
            key = (item.get("entity_type", "shop"), item["shop_id"])
            if key in seen:
                skipped_ids.append(seen[key]["id"])
            seen[key] = item

        unique_items = list(seen.values())

        # ── 3. Process each unique item
        _SYNC_FN = {
            "shop":    sync_single_shop,
            "job":     sync_single_job,
            "product": sync_single_product,
            "service": sync_single_service,
        }

        results: List[Tuple[int, int, bool, Optional[str]]] = []

        for item in unique_items:
            queue_id    = item["id"]
            entity_id   = item["shop_id"]
            action      = item["action"]
            entity_type = item.get("entity_type", "shop")
            retry_count = int(item["retry_count"])
            ok          = False
            error_msg   = None

            try:
                if action == "delete":
                    if entity_type == "product":
                        ok = _delete_product_docs(entity_id)
                    elif entity_type == "service":
                        ok = _delete_service_docs(entity_id)
                    elif entity_type == "job":
                        ok = _delete_doc("jobs", entity_id)
                    else:  # shop — cascade everything
                        _delete_product_docs(entity_id)
                        _delete_service_docs(entity_id)
                        try:
                            result = ts_client.collections["jobs"].documents.delete({
                                "filter_by": f"shop_id:={entity_id}"
                            })
                            logger.info(f"Cascade deleted {result.get('num_deleted', 0)} jobs for shop {entity_id}")
                        except Exception as e:
                            logger.warning(f"Job cascade delete for shop {entity_id} failed: {e}")
                        ok = _delete_doc("shops", entity_id)
                else:
                    fn = _SYNC_FN.get(entity_type)
                    if fn:
                        ok = fn(entity_id)
                    else:
                        logger.warning(f"Unknown entity_type '{entity_type}' in queue")
                        ok = False

            except Exception as e:
                error_msg = str(e)[:500]
                ok = False

            results.append((queue_id, retry_count, ok, error_msg))

        # ── 4. Atomic bulk status update
        success = failed = permanently_failed = skipped = 0

        with get_db_connection() as conn:
            conn.autocommit = False
            cur = conn.cursor()

            if skipped_ids:
                placeholders = ",".join(["%s"] * len(skipped_ids))
                cur.execute(
                    f"""
                    UPDATE typesense_sync_queue
                    SET    status        = 'skipped',
                           synced_at     = NOW(),
                           error_message = 'Superseded by newer action'
                    WHERE  id IN ({placeholders})
                    """,
                    tuple(skipped_ids),
                )
                skipped = len(skipped_ids)

            for queue_id, retry_count, ok, error_msg in results:
                if ok:
                    cur.execute(
                        """
                        UPDATE typesense_sync_queue
                        SET status = 'synced', synced_at = NOW()
                        WHERE id = %s
                        """,
                        (queue_id,),
                    )
                    success += 1
                else:
                    new_retry = retry_count + 1
                    msg       = error_msg or "Unknown error"

                    if new_retry >= MAX_RETRY_COUNT:
                        cur.execute(
                            """
                            UPDATE typesense_sync_queue
                            SET status        = 'permanently_failed',
                                retry_count   = %s,
                                error_message = %s
                            WHERE id = %s
                            """,
                            (new_retry, msg, queue_id),
                        )
                        permanently_failed += 1
                        logger.warning(
                            f"Queue item {queue_id} permanently failed: {msg}"
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE typesense_sync_queue
                            SET retry_count   = %s,
                                error_message = %s
                            WHERE id = %s
                            """,
                            (new_retry, msg, queue_id),
                        )
                        failed += 1

            cur.close()
            conn.commit()

        # ── 5. Invalidate search cache once per batch
        if success > 0:
            try:
                loop = asyncio.get_running_loop()
                for pattern in (
                    "geo_search|*",
                    "product_search|*",
                    "service_search|*",
                    "job_search|*",
                    "rated_search|*",
                ):
                    loop.create_task(cache_invalidate_pattern(pattern))
            except RuntimeError:
                pass
            except Exception as e:
                logger.warning(f"Cache invalidation failed: {e}")

        processed = success + failed + permanently_failed + skipped
        logger.info(
            "Queue processed: %d total | %d synced | %d retrying | "
            "%d perm-failed | %d skipped",
            processed, success, failed, permanently_failed, skipped,
        )
        return {
            "processed":          processed,
            "success":            success,
            "failed":             failed,
            "permanently_failed": permanently_failed,
            "skipped":            skipped,
        }

    except Exception as e:
        logger.error(f"process_sync_queue crashed: {e}", exc_info=True)
        return empty


# ═══════════════════════════════════════════════════════════════════════════════
# FULL SYNC  (APScheduler every 1 h — rebuild + orphan removal)
# ═══════════════════════════════════════════════════════════════════════════════

def _bulk_upsert(collection: str, docs: List[Dict], batch_size: int = 1000) -> int:
    """Import docs in batches. Returns count of successfully imported docs."""
    imported = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        try:
            results = ts_client.collections[collection].documents.import_(
                batch, {"action": "upsert"}
            )
            success = sum(1 for r in results if r.get("success", False))
            imported += success
            failures = [r for r in results if not r.get("success")]
            for f in failures[:3]:
                logger.warning(f"Upsert failed in {collection}: {f}")
        except Exception as e:
            logger.error(
                f"Batch import failed for {collection} "
                f"(batch {i}–{i + len(batch)}): {e}"
            )
    return imported


def _remove_orphans(collection: str, active_ids: set) -> int:
    """
    Remove Typesense documents not present in active_ids.
    Uses export() (no 2500-doc ceiling) instead of search().
    """
    deleted = 0
    try:
        raw = ts_client.collections[collection].documents.export()
        for line in (raw or "").strip().split("\n"):
            if not line:
                continue
            try:
                doc_id = json.loads(line).get("id")
                if doc_id and doc_id not in active_ids:
                    try:
                        ts_client.collections[collection].documents[doc_id].delete()
                        deleted += 1
                    except typesense.exceptions.ObjectNotFound:
                        pass
            except json.JSONDecodeError:
                logger.warning(
                    f"Invalid JSON in {collection} export: {line[:80]}"
                )
    except Exception as e:
        logger.error(f"Orphan cleanup failed for {collection}: {e}", exc_info=True)

    if deleted:
        logger.info(f"Removed {deleted} orphan docs from {collection}")
    return deleted


def sync_all_shops(batch_size: int = 1000) -> bool:
    """Full shop sync: upsert all active + remove orphans."""
    logger.info("Full shop sync starting…")
    try:
        rows = fetch_all(SHOP_JOIN_SQL) or []
        docs = [build_shop_doc(r) for r in rows]
        docs = [d for d in docs if d]

        imported = _bulk_upsert("shops", docs, batch_size)
        active_ids = {str(r["id"]) for r in rows if r and "id" in r}
        _remove_orphans("shops", active_ids)

        logger.info(f"Full shop sync done: {imported}/{len(docs)} upserted")
        return True
    except Exception as e:
        logger.error(f"Full shop sync failed: {e}", exc_info=True)
        return False


def sync_all_jobs(batch_size: int = 1000) -> bool:
    """Full job sync: upsert all active + remove orphans."""
    logger.info("Full job sync starting…")
    try:
        # 1. This now automatically excludes rows where users.subscriber_status != 1
        rows = fetch_all(JOB_JOIN_SQL) or []
        docs = [build_job_doc(r) for r in rows]
        docs = [d for d in docs if d]

        imported = _bulk_upsert("jobs", docs, batch_size)
        
        # 2. Because un-subscribed jobs are excluded from 'rows', 
        # their IDs will NOT be in 'active_ids'.
        active_ids = {str(r["id"]) for r in rows if r and "id" in r}
        
        # 3. _remove_orphans will now automatically delete those expired subscription jobs from Typesense!
        _remove_orphans("jobs", active_ids)

        logger.info(f"Full job sync done: {imported}/{len(docs)} upserted")
        return True
    except Exception as e:
        logger.error(f"Full job sync failed: {e}", exc_info=True)
        return False

def sync_all_products(batch_size: int = 1000) -> bool:
    """Full product sync: upsert all active + remove orphans."""
    logger.info("Full product sync starting…")
    try:
        rows = fetch_all(PRODUCT_JOIN_SQL) or []
        docs = [build_product_doc(r) for r in rows]
        docs = [d for d in docs if d]

        imported = _bulk_upsert("products", docs, batch_size)
        active_ids = {d["id"] for d in docs}
        _remove_orphans("products", active_ids)

        logger.info(f"Full product sync done: {imported}/{len(docs)} upserted")
        return True
    except Exception as e:
        logger.error(f"Full product sync failed: {e}", exc_info=True)
        return False


def sync_all_services(batch_size: int = 1000) -> bool:
    """Full service sync: upsert all active + remove orphans."""
    logger.info("Full service sync starting…")
    try:
        rows = fetch_all(SERVICE_JOIN_SQL) or []
        docs = [build_service_doc(r) for r in rows]
        docs = [d for d in docs if d]

        imported = _bulk_upsert("services", docs, batch_size)
        active_ids = {d["id"] for d in docs}
        _remove_orphans("services", active_ids)

        logger.info(f"Full service sync done: {imported}/{len(docs)} upserted")
        return True
    except Exception as e:
        logger.error(f"Full service sync failed: {e}", exc_info=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# RATINGS
# shop_details has no average_rating column — full shop re-sync keeps
# Typesense fresh. Reviews trigger already queues the shop every 60 s,
# so this hourly call is a safety net only.
# ═══════════════════════════════════════════════════════════════════════════════

def update_all_ratings() -> bool:
    logger.info("Rating update: delegating to full shop sync")
    return sync_all_shops()


# ═══════════════════════════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════════════════════════

def get_queue_stats() -> Dict[str, Any]:
    """Return queue statistics for /sync/status."""
    try:
        row = fetch_one(
            """
            SELECT
                COUNT(*)                           AS total,
                SUM(status = 'pending')            AS pending,
                SUM(status = 'synced')             AS synced,
                SUM(status = 'skipped')            AS skipped,
                SUM(status = 'permanently_failed') AS permanently_failed,
                MAX(created_at)                    AS last_created
            FROM typesense_sync_queue
            """
        )
        return row or {}
    except Exception as e:
        logger.error(f"get_queue_stats failed: {e}")
        return {}


def retry_permanently_failed() -> int:
    """
    Reset all permanently_failed items back to pending.
    Call after fixing data or configuration issues.
    """
    try:
        n = execute_query(
            """
            UPDATE typesense_sync_queue
            SET    status        = 'pending',
                   retry_count   = 0,
                   error_message = NULL
            WHERE  status = 'permanently_failed'
            """
        )
        logger.info(f"Reset {n} permanently-failed items to pending")
        return n or 0
    except Exception as e:
        logger.error(f"retry_permanently_failed failed: {e}")
        return 0