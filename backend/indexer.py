"""
indexer.py — Elasticsearch indexing logic for the Research Portal.

Handles index creation, duplicate detection via SHA-256, single-file indexing,
and full-folder scan. All operations are idempotent.
"""

import logging
import ssl
from pathlib import Path

from elasticsearch import AsyncElasticsearch, NotFoundError

from config import (
    ELASTICSEARCH_URL,
    ELASTICSEARCH_INDEX,
    ELASTICSEARCH_USERNAME,
    ELASTICSEARCH_PASSWORD,
    INDEX_MAPPING,
    PAPERS_FOLDER,
)
from extractor import extract_paper_metadata, _compute_sha256

logger = logging.getLogger(__name__)

# ── Shared async ES client (created once, reused) ────────────────────────────
_es_client: AsyncElasticsearch | None = None


def get_es_client() -> AsyncElasticsearch:
    """Get or create the async Elasticsearch client."""
    global _es_client
    if _es_client is None:
        # Create SSL context that doesn't verify self-signed certs (dev mode)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        _es_client = AsyncElasticsearch(
            hosts=[ELASTICSEARCH_URL],
            basic_auth=(ELASTICSEARCH_USERNAME, ELASTICSEARCH_PASSWORD),
            ssl_context=ssl_context,
            request_timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )
    return _es_client


async def close_es_client():
    """Close the ES client connection."""
    global _es_client
    if _es_client is not None:
        await _es_client.close()
        _es_client = None
        logger.info("Elasticsearch client closed")


# ── Index management ─────────────────────────────────────────────────────────

async def ensure_index_exists():
    """Create the research_papers index with full mapping if it doesn't exist."""
    es = get_es_client()
    try:
        exists = await es.indices.exists(index=ELASTICSEARCH_INDEX)
        if not exists:
            await es.indices.create(index=ELASTICSEARCH_INDEX, body=INDEX_MAPPING)
            logger.info(f"✅ Created Elasticsearch index: {ELASTICSEARCH_INDEX}")
        else:
            logger.info(f"Index '{ELASTICSEARCH_INDEX}' already exists")
    except Exception as e:
        logger.error(f"❌ Failed to create index: {e}", exc_info=True)
        raise


# ── Duplicate detection ──────────────────────────────────────────────────────

async def is_duplicate(sha256_hash: str) -> bool:
    """
    Check if a document with this SHA-256 hash already exists in the index.
    Returns True if duplicate found.
    """
    es = get_es_client()
    try:
        result = await es.search(
            index=ELASTICSEARCH_INDEX,
            body={
                "query": {"term": {"sha256_hash": sha256_hash}},
                "size": 1,
                "_source": False,
            },
        )
        return result["hits"]["total"]["value"] > 0
    except NotFoundError:
        return False
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}")
        return False


# ── Single-file indexing ─────────────────────────────────────────────────────

async def index_single_file(file_path: str) -> bool:
    """
    Index a single PDF file into Elasticsearch.
    1. Compute SHA-256 hash
    2. Check for duplicate → skip if exists
    3. Extract metadata → index with id=sha256_hash (idempotent)
    Returns True if indexed, False if skipped or failed.
    """
    file_path = str(Path(file_path).resolve())
    file_name = Path(file_path).name

    try:
        # Step 1: Compute hash
        sha256_hash = _compute_sha256(file_path)
        if not sha256_hash:
            logger.error(f"Could not compute hash for {file_name}")
            return False

        # Step 2: Check for duplicate
        if await is_duplicate(sha256_hash):
            logger.info(f"⏭️  Duplicate detected: {file_name} (hash: {sha256_hash[:12]}...)")
            return False

        # Step 3: Extract metadata
        metadata = extract_paper_metadata(file_path)
        if metadata is None:
            logger.error(f"Failed to extract metadata from {file_name}")
            return False

        # Step 4: Index with id=sha256_hash for idempotent upsert
        es = get_es_client()
        await es.index(
            index=ELASTICSEARCH_INDEX,
            id=sha256_hash,
            document=metadata,
        )

        logger.info(f"✅ Indexed: {metadata.get('title', file_name)} ({sha256_hash[:12]}...)")
        return True

    except Exception as e:
        logger.error(f"❌ Error indexing {file_name}: {e}", exc_info=True)
        return False


# ── Full folder scan ─────────────────────────────────────────────────────────

async def scan_and_index_folder(folder_path: str | None = None) -> dict:
    """
    Scan all PDF files in the folder and index new ones.
    Returns summary: { total_scanned, new_indexed, duplicates_skipped, errors }
    """
    folder = Path(folder_path) if folder_path else PAPERS_FOLDER
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Created papers folder: {folder}")

    # Use a set to avoid double-counting on case-insensitive filesystems (Windows)
    pdf_files = list({p.resolve() for p in folder.glob("*.pdf")} | {p.resolve() for p in folder.glob("*.PDF")})
    logger.info(f"📂 Scanning folder: {folder} — found {len(pdf_files)} PDF files")

    stats = {
        "total_scanned": len(pdf_files),
        "new_indexed": 0,
        "duplicates_skipped": 0,
        "errors": 0,
    }

    for pdf_file in pdf_files:
        try:
            sha256_hash = _compute_sha256(str(pdf_file))
            if await is_duplicate(sha256_hash):
                stats["duplicates_skipped"] += 1
                continue

            success = await index_single_file(str(pdf_file))
            if success:
                stats["new_indexed"] += 1
            else:
                stats["errors"] += 1

        except Exception as e:
            logger.error(f"Error processing {pdf_file.name}: {e}")
            stats["errors"] += 1

    logger.info(
        f"📊 Scan complete: {stats['total_scanned']} scanned, "
        f"{stats['new_indexed']} new, {stats['duplicates_skipped']} duplicates, "
        f"{stats['errors']} errors"
    )
    return stats


# ── Delete document ──────────────────────────────────────────────────────────

async def delete_document_by_path(file_path: str) -> bool:
    """Soft-delete a document from ES by its file_path field."""
    es = get_es_client()
    try:
        result = await es.delete_by_query(
            index=ELASTICSEARCH_INDEX,
            body={
                "query": {"term": {"file_name": Path(file_path).name}},
            },
        )
        deleted = result.get("deleted", 0)
        if deleted > 0:
            logger.info(f"🗑️  Deleted {deleted} document(s) for {Path(file_path).name}")
        return deleted > 0
    except Exception as e:
        logger.error(f"Error deleting document for {file_path}: {e}")
        return False


# ── Get index stats ──────────────────────────────────────────────────────────

async def get_index_stats() -> dict:
    """Get stats about the research_papers index."""
    es = get_es_client()
    try:
        count_result = await es.count(index=ELASTICSEARCH_INDEX)
        stats_result = await es.indices.stats(index=ELASTICSEARCH_INDEX)

        total_size = stats_result["indices"][ELASTICSEARCH_INDEX]["total"]["store"]["size_in_bytes"]

        return {
            "total_papers": count_result["count"],
            "index_size_bytes": total_size,
            "index_size_human": _format_bytes(total_size),
        }
    except NotFoundError:
        return {"total_papers": 0, "index_size_bytes": 0, "index_size_human": "0 B"}
    except Exception as e:
        logger.error(f"Error getting index stats: {e}")
        return {"total_papers": 0, "index_size_bytes": 0, "index_size_human": "0 B"}


def _format_bytes(size_bytes: int) -> str:
    """Format bytes to human-readable."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"
