"""
worker.py
─────────
Background job runner — scheduler only.
Runs as a separate process from gunicorn.
One instance only — no duplicate job execution.
"""

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from logging_config import configure_logging, get_logger
from database import close_async_pool, execute_query_async
from sync_manage import (
    process_sync_queue,
    sync_all_jobs, sync_all_products,
    sync_all_services, sync_all_shops,
    update_all_ratings,
)

configure_logging()
logger = get_logger(__name__)


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


async def main():
    logger.info("Worker starting — scheduler only")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(_job_sync_queue,     IntervalTrigger(minutes=1),  id="sync_queue",  replace_existing=True)
    scheduler.add_job(_job_full_sync,      IntervalTrigger(hours=1),    id="full_sync",   replace_existing=True)
    scheduler.add_job(_job_update_ratings, IntervalTrigger(hours=1),    id="ratings",     replace_existing=True)
    scheduler.add_job(_job_cleanup_queue,  "cron", hour=2, minute=0,    id="cleanup",     replace_existing=True)
    scheduler.start()

    logger.info("Scheduler started — running forever")

    try:
        await asyncio.Event().wait()  # run forever
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker shutting down")
        scheduler.shutdown()
        await close_async_pool()


if __name__ == "__main__":
    asyncio.run(main())