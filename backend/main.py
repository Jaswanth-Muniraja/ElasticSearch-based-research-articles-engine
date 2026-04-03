"""
main.py — FastAPI application entry point for the Research Portal.

Manages application lifecycle: ES connection, index creation, initial folder scan,
file watcher, and periodic scheduler. Exposes health endpoint and mounts all routes.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS, API_HOST, API_PORT, PAPERS_FOLDER

# ── Configure logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)-20s │ %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ── Application lifespan ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup & shutdown lifecycle for the FastAPI app.

    On startup:
      1. Connect to Elasticsearch, verify connection (retry 3x with backoff)
      2. Create research_papers index with full mapping if it doesn't exist
      3. Run initial full folder scan → index any PDFs not yet in ES
      4. Start watchdog file watcher in background thread
      5. Start APScheduler for periodic 5-minute syncs
      6. Log ready message
    """
    from indexer import get_es_client, ensure_index_exists, scan_and_index_folder, close_es_client
    from watcher import start_watcher, stop_watcher
    from scheduler import start_scheduler, stop_scheduler

    logger.info("=" * 60)
    logger.info("🚀 Research Portal Backend — Starting Up")
    logger.info("=" * 60)

    # Step 1: Connect to Elasticsearch with retry
    es = get_es_client()
    connected = False
    for attempt in range(1, 4):
        try:
            info = await es.info()
            cluster_name = info.get("cluster_name", "unknown")
            version = info.get("version", {}).get("number", "unknown")
            logger.info(f"✅ Elasticsearch connected: cluster={cluster_name}, version={version}")
            connected = True
            break
        except Exception as e:
            logger.warning(f"⚠️  ES connection attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)  # exponential backoff

    if not connected:
        logger.error("❌ Could not connect to Elasticsearch after 3 attempts!")
        logger.error("   Make sure Elasticsearch is running at the configured URL.")
        # Continue anyway — endpoints will fail gracefully

    # Step 2: Create index if not exists
    try:
        await ensure_index_exists()
    except Exception as e:
        logger.error(f"❌ Index creation failed: {e}")

    # Step 3: Ensure papers folder exists
    PAPERS_FOLDER.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 Papers folder: {PAPERS_FOLDER}")

    # Step 4: Initial folder scan
    try:
        stats = await scan_and_index_folder()
        total_indexed = stats["new_indexed"] + stats["duplicates_skipped"]
        logger.info(f"📊 Initial scan: {total_indexed} papers total ({stats['new_indexed']} newly indexed)")
    except Exception as e:
        logger.error(f"❌ Initial scan failed: {e}")

    # Step 5: Start file watcher
    loop = asyncio.get_event_loop()
    try:
        start_watcher(loop)
    except Exception as e:
        logger.error(f"❌ Watcher start failed: {e}")

    # Step 6: Start scheduler
    try:
        start_scheduler()
    except Exception as e:
        logger.error(f"❌ Scheduler start failed: {e}")

    logger.info("=" * 60)
    logger.info(f"✅ Research Portal Backend Ready | http://{API_HOST}:{API_PORT}")
    logger.info("=" * 60)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down...")
    stop_watcher()
    stop_scheduler()
    await close_es_client()
    logger.info("Goodbye! 👋")


# ── Create app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Research Portal API",
    description="University Research Paper Portal — Search, Index, and Manage Academic PDFs",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS middleware ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routes ─────────────────────────────────────────────────────────────
from routes.search import router as search_router
from routes.papers import router as papers_router
from routes.admin import router as admin_router

app.include_router(search_router)
app.include_router(papers_router)
app.include_router(admin_router)


# ── Health endpoint ──────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    from indexer import get_es_client
    from models.paper import HealthResponse

    es_connected = False
    try:
        es = get_es_client()
        await es.ping()
        es_connected = True
    except Exception:
        pass

    return HealthResponse(status="ok", es_connected=es_connected)


# ── Run with uvicorn ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info",
    )
