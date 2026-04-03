"""
routes/admin.py — Admin endpoints for the Research Portal.

Provides admin authentication (login/verify), manual re-indexing trigger,
index statistics, and paper metadata editing.
"""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Header, HTTPException

from config import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    JWT_SECRET,
    ELASTICSEARCH_INDEX,
)
from indexer import scan_and_index_folder, get_index_stats, get_es_client
from scheduler import get_last_sync_time
from models.paper import (
    APIResponse,
    StatsResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    EditPaperRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_token(email: str) -> str:
    """Create a JWT token for an authenticated admin."""
    payload = {
        "sub": email,
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _verify_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not an admin token")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Auth endpoints ───────────────────────────────────────────────────────────

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(req: AdminLoginRequest):
    """Authenticate admin with email + password, return JWT."""
    if req.email == ADMIN_EMAIL and req.password == ADMIN_PASSWORD:
        token = _create_token(req.email)
        logger.info(f"✅ Admin login successful: {req.email}")
        return AdminLoginResponse(
            success=True,
            token=token,
            message="Login successful",
        )

    logger.warning(f"⚠️ Failed admin login attempt: {req.email}")
    return AdminLoginResponse(
        success=False,
        message="Invalid email or password",
    )


@router.get("/verify")
async def verify_admin(authorization: str = Header(default="")):
    """Verify that the provided JWT is still valid."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[7:]  # strip "Bearer "
    payload = _verify_token(token)
    return {"success": True, "email": payload["sub"], "message": "Token is valid"}


# ── Paper editing endpoint ───────────────────────────────────────────────────

@router.put("/papers/{paper_id}")
async def edit_paper(
    paper_id: str,
    req: EditPaperRequest,
    authorization: str = Header(default=""),
):
    """
    Update editable fields of a paper in Elasticsearch.
    Only authenticated admins can call this.
    Uses ES partial update — preserves all non-edited fields.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[7:]
    payload = _verify_token(token)
    admin_email = payload["sub"]

    # Build the partial doc with only provided (non-None) fields
    update_fields = {}
    for field_name in ("title", "authors", "abstract", "keywords", "domain_keywords"):
        value = getattr(req, field_name)
        if value is not None:
            update_fields[field_name] = value

    if not update_fields:
        return APIResponse(success=False, message="No fields to update")

    # Add edit-tracking metadata
    update_fields["edited"] = True
    update_fields["last_edited_by"] = admin_email
    update_fields["last_edited_at"] = datetime.now(timezone.utc).isoformat()

    try:
        es = get_es_client()
        await es.update(
            index=ELASTICSEARCH_INDEX,
            id=paper_id,
            body={"doc": update_fields},
        )

        logger.info(f"✅ Paper {paper_id[:12]}... edited by {admin_email}: {list(update_fields.keys())}")
        return APIResponse(
            success=True,
            data=update_fields,
            message="Paper updated successfully",
        )

    except Exception as e:
        logger.error(f"❌ Error editing paper {paper_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update paper: {str(e)}")


# ── Existing admin endpoints (unchanged) ─────────────────────────────────────

@router.post("/index", response_model=APIResponse)
async def trigger_reindex():
    """Manually trigger a full folder re-index."""
    try:
        logger.info("🔄 Manual re-index triggered")
        stats = await scan_and_index_folder()

        return APIResponse(
            success=True,
            data=stats,
            message=(
                f"Re-index complete: {stats['new_indexed']} new, "
                f"{stats['duplicates_skipped']} skipped, {stats['errors']} errors"
            ),
        )

    except Exception as e:
        logger.error(f"Re-index error: {e}", exc_info=True)
        return APIResponse(success=False, message=f"Re-index failed: {str(e)}")


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get index statistics: total papers, index size, last sync time."""
    try:
        stats = await get_index_stats()
        stats["last_sync"] = get_last_sync_time()

        return StatsResponse(
            success=True,
            data=stats,
            message="Stats retrieved",
        )

    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        return StatsResponse(success=False, message=f"Stats failed: {str(e)}")
