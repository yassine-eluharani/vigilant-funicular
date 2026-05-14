"""Auth routes — /me. User sync happens on every request via get_current_user().

BE-002: this router is async because the DB helpers it calls (``get_user_record``)
do sync I/O (Turso HTTP / sqlite3). They're offloaded to the FastAPI threadpool
via ``asyncio.to_thread`` so the event loop stays free. See ``web/auth.py`` for
the full rationale.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from applypilot.web.auth import get_current_user, get_user_record
from applypilot.web.schemas import MeResponse

router = APIRouter()


def _build_me_response(user_id: int) -> MeResponse:
    record = get_user_record(user_id)
    return MeResponse(
        id=record["id"],
        email=record["email"],
        full_name=record["full_name"],
        has_profile=bool(record.get("profile_json")),
    )


@router.get("/api/auth/me", response_model=MeResponse)
async def me(user: dict = Depends(get_current_user)) -> MeResponse:
    user_id = int(user["sub"])
    return await asyncio.to_thread(_build_me_response, user_id)
