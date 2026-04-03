"""
scheduler.py — APScheduler periodic sync for the Research Portal.

Runs a full folder scan every SYNC_INTERVAL_MINUTES minutes using AsyncIOScheduler.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import SYNC_INTERVAL_MINUTES

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_last_sync_time: str | None = None


def get_last_sync_time() -> str | None:
    """Return the ISO timestamp of the last successful sync."""
    return _last_sync_time


async def _periodic_sync():
    """Run full folder scan and index new PDFs."""
    global _last_sync_time
    try:
        from indexer import scan_and_index_folder

        logger.info("⏰ Periodic sync started")
        stats = await scan_and_index_folder()
        _last_sync_time = datetime.now(timezone.utc).isoformat()

        logger.info(
            f"⏰ Periodic sync complete: {stats['new_indexed']} new, "
            f"{stats['duplicates_skipped']} skipped, {stats['errors']} errors"
        )
    except Exception as e:
        logger.error(f"❌ Periodic sync failed: {e}", exc_info=True)


def start_scheduler() -> AsyncIOScheduler:
    """Start the APScheduler for periodic folder syncing."""
    global _scheduler

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _periodic_sync,
        trigger="interval",
        minutes=SYNC_INTERVAL_MINUTES,
        id="periodic_sync",
        name=f"Folder sync every {SYNC_INTERVAL_MINUTES} min",
        replace_existing=True,
    )
    _scheduler.start()

    logger.info(f"⏰ Scheduler started — syncing every {SYNC_INTERVAL_MINUTES} minutes")
    return _scheduler


def stop_scheduler():
    """Shut down the scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
