"""
models/paper.py — Pydantic models for the Research Portal.
Defines data shapes for PDF documents, search requests/responses, and API outputs.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Document model (what gets stored in Elasticsearch) ───────────────────────

class PaperDocument(BaseModel):
    """Full representation of an indexed research paper."""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    ner_entities: list[str] = Field(default_factory=list)
    full_text: str = ""
    file_name: str = ""
    file_path: str = ""
    file_size_bytes: int = 0
    file_size_human: str = ""
    page_count: int = 0
    sha256_hash: str = ""
    date_indexed: str = ""          # ISO 8601 UTC
    last_modified: str = ""         # ISO 8601 UTC


# ── Search request/response models ──────────────────────────────────────────

class RangeFilter(BaseModel):
    """Generic numeric range with optional from/to."""
    from_: Optional[float] = Field(None, alias="from")
    to: Optional[float] = None

    class Config:
        populate_by_name = True


class SearchFilters(BaseModel):
    """Filter criteria sent from the frontend."""
    subjects: list[str] = Field(default_factory=list)
    yearRange: Optional[RangeFilter] = None
    sizeRange: Optional[RangeFilter] = None
    authors: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """POST body for /api/search."""
    query: str = ""
    filters: Optional[SearchFilters] = None
    page: int = 1
    size: int = 10


class FacetBucket(BaseModel):
    """Single facet bucket returned in aggregation results."""
    key: str
    doc_count: int


class SearchResultItem(BaseModel):
    """Single search result returned to the frontend."""
    id: str = ""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    abstract_preview: str = ""
    keywords: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    file_name: str = ""
    file_size_human: str = ""
    size_mb: Optional[str] = None
    page_count: int = 0
    score: float = 0.0
    highlights: dict = Field(default_factory=dict)
    fileUrl: str = ""
    year: Optional[str] = None
    publisher: Optional[str] = None


class SearchFacets(BaseModel):
    """Facets returned alongside search results."""
    subjects: list[FacetBucket] = Field(default_factory=list)
    year: list[FacetBucket] = Field(default_factory=list)
    size_mb: list[FacetBucket] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Full response for the /api/search endpoint."""
    success: bool = True
    results: list[SearchResultItem] = Field(default_factory=list)
    total: int = 0
    facets: SearchFacets = Field(default_factory=SearchFacets)
    message: str = ""


# ── Admin / stats models ────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    """Response for /api/admin/stats."""
    success: bool = True
    data: dict = Field(default_factory=dict)
    message: str = ""


class HealthResponse(BaseModel):
    """Response for /api/health."""
    status: str = "ok"
    es_connected: bool = False


class APIResponse(BaseModel):
    """Generic API response wrapper."""
    success: bool = True
    data: Optional[dict | list] = None
    message: str = ""
    total: Optional[int] = None


# ── Admin auth models ───────────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    """POST body for /api/admin/login."""
    email: str
    password: str


class AdminLoginResponse(BaseModel):
    """Response for /api/admin/login."""
    success: bool = False
    token: Optional[str] = None
    message: str = ""


class EditPaperRequest(BaseModel):
    """PUT body for /api/admin/papers/{paper_id}. All fields optional."""
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    abstract: Optional[str] = None
    keywords: Optional[list[str]] = None
    domain_keywords: Optional[list[str]] = None

