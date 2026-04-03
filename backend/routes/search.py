"""
routes/search.py — Search endpoint for the Research Portal.

Implements multi-field boosted Elasticsearch queries with fuzzy matching,
highlighting, faceted aggregations, and filter support.
Returns response shapes compatible with the existing React frontend.
"""

import logging
import math

from fastapi import APIRouter, Request

from config import ELASTICSEARCH_INDEX
from indexer import get_es_client
from models.paper import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchFacets,
    FacetBucket,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_papers(req: SearchRequest):
    """
    Search research papers with boosted multi-field query.
    Supports filters: subjects (domain_keywords), yearRange, sizeRange, authors.
    Returns paginated results with facets for the sidebar.
    """
    try:
        es = get_es_client()
        q = req.query.strip()
        page = max(1, req.page)
        size = min(50, max(1, req.size))
        from_offset = (page - 1) * size

        # ── Build the main query ─────────────────────────────────────────
        if q:
            must_query = {
                "bool": {
                    "should": [
                        {"match": {"title":    {"query": q, "boost": 5, "fuzziness": "AUTO"}}},
                        {"match": {"keywords": {"query": q, "boost": 4, "fuzziness": "AUTO"}}},
                        {"match": {"abstract": {"query": q, "boost": 3}}},
                        {"match": {"authors":  {"query": q, "boost": 2}}},
                        {"match": {"full_text": {"query": q, "boost": 1}}},
                        {"match": {"ner_entities": {"query": q, "boost": 2}}},
                        {"match": {"domain_keywords": {"query": q, "boost": 3}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        else:
            must_query = {"match_all": {}}

        # ── Build filters ────────────────────────────────────────────────
        filter_clauses = []
        filters = req.filters

        if filters:
            # Subject / domain_keywords filter
            if filters.subjects:
                filter_clauses.append({
                    "terms": {"domain_keywords.keyword": filters.subjects}
                })

            # Author filter
            if filters.authors:
                should_author = [
                    {"match_phrase": {"authors": author}}
                    for author in filters.authors
                ]
                filter_clauses.append({
                    "bool": {"should": should_author, "minimum_should_match": 1}
                })

            # Year range filter (on date_indexed year)
            if filters.yearRange:
                year_filter = {"range": {"date_indexed": {}}}
                if filters.yearRange.from_:
                    year_filter["range"]["date_indexed"]["gte"] = f"{int(filters.yearRange.from_)}-01-01"
                if filters.yearRange.to:
                    year_filter["range"]["date_indexed"]["lte"] = f"{int(filters.yearRange.to)}-12-31"
                filter_clauses.append(year_filter)

            # Size range filter (in MB, stored as bytes)
            if filters.sizeRange:
                size_filter = {"range": {"file_size_bytes": {}}}
                if filters.sizeRange.from_ is not None:
                    size_filter["range"]["file_size_bytes"]["gte"] = int(filters.sizeRange.from_ * 1024 * 1024)
                if filters.sizeRange.to is not None:
                    size_filter["range"]["file_size_bytes"]["lte"] = int(filters.sizeRange.to * 1024 * 1024)
                filter_clauses.append(size_filter)

        # ── Combine into bool query ──────────────────────────────────────
        body = {
            "query": {
                "bool": {
                    "must": [must_query],
                    "filter": filter_clauses,
                }
            },
            "highlight": {
                "fields": {
                    "title": {},
                    "abstract": {"fragment_size": 200, "number_of_fragments": 1},
                    "keywords": {},
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
            "from": from_offset,
            "size": size,
            # ── Aggregations for facets ──────────────────────────────────
            "aggs": {
                "subjects": {
                    "terms": {"field": "domain_keywords.keyword", "size": 30}
                },
                "year_agg": {
                    "date_histogram": {
                        "field": "date_indexed",
                        "calendar_interval": "year",
                        "format": "yyyy",
                        "min_doc_count": 1,
                    }
                },
                "size_mb_agg": {
                    "histogram": {
                        "field": "file_size_bytes",
                        "interval": 1048576,  # 1 MB
                        "min_doc_count": 1,
                    }
                },
            },
        }

        result = await es.search(index=ELASTICSEARCH_INDEX, body=body)

        # ── Parse results ────────────────────────────────────────────────
        hits = result["hits"]["hits"]
        total = result["hits"]["total"]["value"]

        items = []
        for hit in hits:
            src = hit["_source"]
            highlights = hit.get("highlight", {})

            # Build abstract preview: ~300 chars, truncated at last complete word
            abstract_full = src.get("abstract", "")
            if len(abstract_full) > 300:
                abstract_preview = abstract_full[:300].rsplit(" ", 1)[0] + "..."
            else:
                abstract_preview = abstract_full

            # Compute size in MB for frontend display
            size_bytes = src.get("file_size_bytes", 0)
            size_mb = f"{size_bytes / (1024 * 1024):.1f}" if size_bytes else None

            # Extract year from date_indexed
            date_indexed = src.get("date_indexed", "")
            year = date_indexed[:4] if date_indexed else None

            item = SearchResultItem(
                id=hit["_id"],
                title=src.get("title", ""),
                authors=src.get("authors", []),
                abstract=abstract_full,
                abstract_preview=abstract_preview,
                keywords=src.get("keywords", []),
                domain_keywords=src.get("domain_keywords", []),
                file_name=src.get("file_name", ""),
                file_size_human=src.get("file_size_human", ""),
                size_mb=size_mb,
                page_count=src.get("page_count", 0),
                score=round(hit.get("_score", 0) or 0, 2),
                highlights=highlights,
                fileUrl=f"http://localhost:8000/api/papers/download/{hit['_id']}",
                year=year,
                publisher=None,  # Could be extracted from metadata in future
            )
            items.append(item)

        # ── Parse facets ─────────────────────────────────────────────────
        aggs = result.get("aggregations", {})

        subjects_buckets = [
            FacetBucket(key=b["key"], doc_count=b["doc_count"])
            for b in aggs.get("subjects", {}).get("buckets", [])
        ]

        year_buckets = [
            FacetBucket(key=b["key_as_string"], doc_count=b["doc_count"])
            for b in aggs.get("year_agg", {}).get("buckets", [])
        ]

        size_mb_buckets = [
            FacetBucket(
                key=str(int(b["key"] / 1048576)),  # Convert bytes back to MB
                doc_count=b["doc_count"],
            )
            for b in aggs.get("size_mb_agg", {}).get("buckets", [])
        ]

        facets = SearchFacets(
            subjects=subjects_buckets,
            year=year_buckets,
            size_mb=size_mb_buckets,
        )

        return SearchResponse(
            success=True,
            results=items,
            total=total,
            facets=facets,
            message=f"Found {total} results for '{q}'" if q else f"Showing {total} papers",
        )

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return SearchResponse(
            success=False,
            results=[],
            total=0,
            message=f"Search failed: {str(e)}",
        )
