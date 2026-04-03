"""
watcher.py — Folder watcher using watchdog for the Research Portal.

Monitors the papers/ directory for new, modified, or deleted PDF files
and triggers indexing accordingly. Runs in a background thread.
"""

import asyncio
import logging
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent

from config import PAPERS_FOLDER
from extractor import _compute_sha256

logger = logging.getLogger(__name__)


class PDFEventHandler(FileSystemEventHandler):
    """Handle file system events for PDF files in the papers folder."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self._loop = loop
        self._known_hashes: dict[str, str] = {}  # file_path -> sha256
        logger.info("PDF watcher event handler initialized")

    def _is_pdf(self, path: str) -> bool:
        """Check if the file is a PDF."""
        return Path(path).suffix.lower() == ".pdf"

    def on_created(self, event):
        """Handle new PDF file creation."""
        if event.is_directory or not self._is_pdf(event.src_path):
            return
        logger.info(f"📄 New PDF detected: {Path(event.src_path).name}")
        self._schedule_index(event.src_path)

    def on_modified(self, event):
        """Handle PDF file modification — recheck hash, skip if unchanged."""
        if event.is_directory or not self._is_pdf(event.src_path):
            return

        new_hash = _compute_sha256(event.src_path)
        old_hash = self._known_hashes.get(event.src_path)

        if new_hash and new_hash != old_hash:
            logger.info(f"📝 PDF modified: {Path(event.src_path).name}")
            self._known_hashes[event.src_path] = new_hash
            self._schedule_index(event.src_path)
        else:
            logger.debug(f"PDF unchanged (same hash): {Path(event.src_path).name}")

    def on_deleted(self, event):
        """Handle PDF file deletion — remove from ES."""
        if event.is_directory or not self._is_pdf(event.src_path):
            return
        logger.info(f"🗑️  PDF deleted: {Path(event.src_path).name}")
        self._known_hashes.pop(event.src_path, None)
        self._schedule_delete(event.src_path)

    def _schedule_index(self, file_path: str):
        """Schedule async indexing on the event loop."""
        try:
            asyncio.run_coroutine_threadsafe(
                self._async_index(file_path), self._loop
            )
        except Exception as e:
            logger.error(f"Error scheduling index for {file_path}: {e}")

    def _schedule_delete(self, file_path: str):
        """Schedule async deletion on the event loop."""
        try:
            asyncio.run_coroutine_threadsafe(
                self._async_delete(file_path), self._loop
            )
        except Exception as e:
            logger.error(f"Error scheduling delete for {file_path}: {e}")

    async def _async_index(self, file_path: str):
        """Async wrapper to index a single file."""
        try:
            # Import here to avoid circular imports
            from indexer import index_single_file
            await index_single_file(file_path)
        except Exception as e:
            logger.error(f"Error indexing {file_path}: {e}")

    async def _async_delete(self, file_path: str):
        """Async wrapper to delete a document."""
        try:
            from indexer import delete_document_by_path
            await delete_document_by_path(file_path)
        except Exception as e:
            logger.error(f"Error deleting document for {file_path}: {e}")


# ── Watcher lifecycle ────────────────────────────────────────────────────────

_observer: Observer | None = None


def start_watcher(loop: asyncio.AbstractEventLoop) -> Observer:
    """Start the watchdog observer in a background thread."""
    global _observer

    watch_path = str(PAPERS_FOLDER)
    # Ensure folder exists
    PAPERS_FOLDER.mkdir(parents=True, exist_ok=True)

    handler = PDFEventHandler(loop)
    _observer = Observer()
    _observer.schedule(handler, watch_path, recursive=False)
    _observer.daemon = True
    _observer.start()

    logger.info(f"👁️  File watcher started — monitoring: {watch_path}")
    return _observer


def stop_watcher():
    """Stop the watchdog observer."""
    global _observer
    if _observer is not None:
        _observer.stop()
        _observer.join(timeout=5)
        _observer = None
        logger.info("File watcher stopped")