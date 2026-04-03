"""
routes/papers.py — Paper listing and download endpoints for the Research Portal.

Provides paginated paper listing, single paper detail, and PDF file streaming.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import ELASTICSEARCH_INDEX, PAPERS_FOLDER
from indexer import get_es_client
from models.paper import APIResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/papers", tags=["papers"])


@router.get("", response_model=APIResponse)
async def list_papers(page: int = 1, size: int = 20):
    """List all indexed papers with pagination."""
    try:
        es = get_es_client()
        page = max(1, page)
        size = min(100, max(1, size))
        from_offset = (page - 1) * size

        result = await es.search(
            index=ELASTICSEARCH_INDEX,
            body={
                "query": {"match_all": {}},
                "sort": [{"date_indexed": {"order": "desc"}}],
                "from": from_offset,
                "size": size,
                "_source": {
                    "excludes": ["full_text"],  # Don't send full text in list
                },
            },
        )

        hits = result["hits"]["hits"]
        total = result["hits"]["total"]["value"]

        papers = []
        for hit in hits:
            src = hit["_source"]
            src["id"] = hit["_id"]
            src["download_url"] = f"/api/papers/download/{hit['_id']}"
            papers.append(src)

        return APIResponse(
            success=True,
            data=papers,
            total=total,
            message=f"Showing {len(papers)} of {total} papers (page {page})",
        )

    except Exception as e:
        logger.error(f"Error listing papers: {e}", exc_info=True)
        return APIResponse(success=False, message=f"Error: {str(e)}")


@router.get("/{paper_id}")
async def get_paper(paper_id: str):
    """Get full metadata of a single paper by its ID (sha256 hash)."""
    try:
        es = get_es_client()
        result = await es.get(index=ELASTICSEARCH_INDEX, id=paper_id)

        paper = result["_source"]
        paper["id"] = result["_id"]
        paper["download_url"] = f"/api/papers/download/{result['_id']}"

        return APIResponse(
            success=True,
            data=paper,
            message="Paper details retrieved",
        )

    except Exception as e:
        logger.error(f"Error getting paper {paper_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")


@router.get("/download/{paper_id}")
async def download_paper(paper_id: str):
    """Stream a PDF file as a forced download by its ES document ID."""
    try:
        es = get_es_client()
        result = await es.get(
            index=ELASTICSEARCH_INDEX,
            id=paper_id,
            _source=["file_name", "file_path"],
        )

        file_name = result["_source"]["file_name"]
        file_path = PAPERS_FOLDER / file_name

        if not file_path.exists():
            rel_path = result["_source"].get("file_path", "")
            alt_path = PAPERS_FOLDER.parent / rel_path
            if alt_path.exists():
                file_path = alt_path
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"PDF file not found on disk: {file_name}",
                )

        # content_disposition_type="attachment" → browser downloads the file
        return FileResponse(
            path=str(file_path),
            filename=file_name,
            media_type="application/pdf",
            content_disposition_type="attachment",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading paper {paper_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")


@router.get("/view/{paper_id}")
async def view_paper(paper_id: str):
    """Serve a PDF file for inline browser rendering (no download prompt)."""
    try:
        es = get_es_client()
        result = await es.get(
            index=ELASTICSEARCH_INDEX,
            id=paper_id,
            _source=["file_name", "file_path"],
        )

        file_name = result["_source"]["file_name"]
        file_path = PAPERS_FOLDER / file_name

        if not file_path.exists():
            rel_path = result["_source"].get("file_path", "")
            alt_path = PAPERS_FOLDER.parent / rel_path
            if alt_path.exists():
                file_path = alt_path
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"PDF file not found on disk: {file_name}",
                )

        # content_disposition_type="inline" → browser renders the PDF in-page
        return FileResponse(
            path=str(file_path),
            filename=file_name,
            media_type="application/pdf",
            content_disposition_type="inline",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing paper {paper_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")
