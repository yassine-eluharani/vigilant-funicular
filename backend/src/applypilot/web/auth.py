"""JWT authentication utilities and FastAPI dependency."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

_JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_DAYS = 30

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_token(user_id: int, email: str, full_name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_JWT_EXPIRY_DAYS)
    return jwt.encode(
        {"exp": expire, "sub": str(user_id), "email": email, "name": full_name},
        os.environ.get("JWT_SECRET", _JWT_SECRET),
        algorithm=_JWT_ALGORITHM,
    )


# ── User CRUD ─────────────────────────────────────────────────────────────────

def create_user(email: str, password: str, full_name: str) -> dict:
    """Register a new user. Raises 409 if email already exists."""
    from applypilot.database import get_connection, init_db
    init_db()
    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email.lower(),)).fetchone()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, full_name, created_at) VALUES (?, ?, ?, ?)",
        (email.lower(), hash_password(password), full_name, now),
    )
    conn.commit()
    return {"id": cur.lastrowid, "email": email.lower(), "full_name": full_name}


def authenticate_user(email: str, password: str) -> dict:
    """Verify email + password. Raises 401 if invalid."""
    from applypilot.database import get_connection, init_db
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, password_hash, full_name FROM users WHERE email = ?",
        (email.lower(),),
    ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    # Update last_login
    conn.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), row["id"]),
    )
    conn.commit()
    return {"id": row["id"], "email": row["email"], "full_name": row["full_name"]}


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Validate Bearer JWT. Returns payload dict with id, email, name."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        secret = os.environ.get("JWT_SECRET", _JWT_SECRET)
        payload = jwt.decode(credentials.credentials, secret, algorithms=[_JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
