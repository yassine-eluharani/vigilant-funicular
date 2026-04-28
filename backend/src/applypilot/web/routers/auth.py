"""Auth routes — /me. User sync happens on every request via get_current_user().

BE-002: this router is async because the DB helpers it calls
(``maybe_reset_usage``, ``get_user_record``) do sync I/O (Turso HTTP /
sqlite3). They're offloaded to the FastAPI threadpool via
``asyncio.to_thread`` so the event loop stays free. See ``web/auth.py`` for
the full rationale.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from applypilot.web.auth import (
    FREE_COVER_LIMIT,
    FREE_TAILOR_LIMIT,
    get_current_user,
    get_user_record,
    maybe_reset_usage,
)
from applypilot.web.schemas import MeResponse

router = APIRouter()


def _build_me_response(user_id: int) -> MeResponse:
    """Sync helper: reset usage + fetch the user record + assemble the payload.

    Bundled into a single threadpool hop (BE-002) so we don't bounce between
    the event loop and worker threads on each individual DB call.
    """
    from applypilot.database import get_connection
    conn = get_connection()
    maybe_reset_usage(conn, user_id)
    record = get_user_record(user_id)
    is_free = record["tier"] == "free"
    return MeResponse(
        id=record["id"],
        email=record["email"],
        full_name=record["full_name"],
        tier=record["tier"],
        has_profile=bool(record.get("profile_json")),
        tailors_used=record["tailors_used"],
        covers_used=record["covers_used"],
        tailor_limit=FREE_TAILOR_LIMIT if is_free else None,
        cover_limit=FREE_COVER_LIMIT if is_free else None,
    )


@router.get("/api/auth/me", response_model=MeResponse)
async def me(user: dict = Depends(get_current_user)) -> MeResponse:
    user_id = int(user["sub"])
    return await asyncio.to_thread(_build_me_response, user_id)
