"""Authentication routes — login and session check."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from applypilot.web.auth import create_token, get_current_user, verify_password

router = APIRouter()


@router.post("/api/auth/login")
async def login(request: Request) -> JSONResponse:
    body = await request.json()
    password = body.get("password", "")
    if not verify_password(password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    token = create_token()
    return JSONResponse({"access_token": token, "token_type": "bearer"})


@router.get("/api/auth/me")
def me(_user: dict = Depends(get_current_user)) -> JSONResponse:
    """Validate token — used by frontend to check if session is still valid."""
    return JSONResponse({"ok": True})
