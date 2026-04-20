"""Authentication routes — register, login, session check."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from applypilot.web.auth import (
    authenticate_user,
    create_token,
    create_user,
    get_current_user,
    get_user_record,
    maybe_reset_usage,
    FREE_TAILOR_LIMIT,
    FREE_COVER_LIMIT,
)

router = APIRouter()


@router.post("/api/auth/register")
async def register(request: Request) -> JSONResponse:
    body = await request.json()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    full_name = (body.get("full_name") or "").strip()

    if not email or not password or not full_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="email, password, and full_name are required")
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Password must be at least 8 characters")

    user = create_user(email, password, full_name)
    token = create_token(user["id"], user["email"], user["full_name"])
    return JSONResponse({"access_token": token, "token_type": "bearer", "user": {
        "id": user["id"], "email": user["email"], "full_name": user["full_name"],
    }})


@router.post("/api/auth/login")
async def login(request: Request) -> JSONResponse:
    body = await request.json()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="email and password are required")

    user = authenticate_user(email, password)
    token = create_token(user["id"], user["email"], user["full_name"])
    return JSONResponse({"access_token": token, "token_type": "bearer", "user": {
        "id": user["id"], "email": user["email"], "full_name": user["full_name"],
    }})


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
