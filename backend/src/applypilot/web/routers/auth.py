"""Auth routes — /me, /upgrade. User sync happens on every request via get_current_user()."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from applypilot.web.auth import (
    FREE_COVER_LIMIT,
    FREE_TAILOR_LIMIT,
    get_current_user,
    get_user_record,
    maybe_reset_usage,
)

router = APIRouter()


@router.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)) -> JSONResponse:
    from applypilot.database import get_connection
    user_id = int(user["sub"])
    conn = get_connection()
    maybe_reset_usage(conn, user_id)
    record = get_user_record(user_id)
    is_free = record["tier"] == "free"
    return JSONResponse({
        "id": record["id"],
        "email": record["email"],
        "full_name": record["full_name"],
        "tier": record["tier"],
        "tailors_used": record["tailors_used"],
        "covers_used": record["covers_used"],
        "tailor_limit": FREE_TAILOR_LIMIT if is_free else None,
        "cover_limit": FREE_COVER_LIMIT if is_free else None,
    })


@router.post("/api/auth/upgrade")
def upgrade(user: dict = Depends(get_current_user)) -> JSONResponse:
    """Upgrade user to Pro. Placeholder — replace with Stripe webhook in production."""
    from applypilot.database import get_connection
    user_id = int(user["sub"])
    conn = get_connection()
    conn.execute("UPDATE users SET tier = 'pro' WHERE id = ?", (user_id,))
    conn.commit()
    return JSONResponse({"ok": True, "tier": "pro"})
