"""Authentication routes — register, login, session check."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from applypilot.web.auth import (
    authenticate_user,
    create_token,
    create_user,
    get_current_user,
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
    return JSONResponse({
        "id": user.get("sub"),
        "email": user.get("email"),
        "full_name": user.get("name"),
    })
