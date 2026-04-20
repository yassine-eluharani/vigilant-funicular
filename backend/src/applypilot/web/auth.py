"""JWT authentication utilities and FastAPI dependency."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt

_JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_DAYS = 30

_bearer = HTTPBearer(auto_error=False)

# ── Tier limits ───────────────────────────────────────────────────────────────

FREE_TAILOR_LIMIT = 3       # tailored resumes per month
FREE_COVER_LIMIT = 1        # cover letters per month
BLUR_SCORE_THRESHOLD = 8    # jobs scoring >= this are locked for free users


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


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


# ── Tier / usage helpers ──────────────────────────────────────────────────────

def get_user_record(user_id: int) -> dict:
    """Fetch full user row including tier + usage counters."""
    from applypilot.database import get_connection, init_db
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, full_name, tier, tailors_used, covers_used, usage_reset_at "
        "FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


def maybe_reset_usage(conn, user_id: int) -> None:
    """Reset monthly usage counters when the calendar month turns over."""
    row = conn.execute(
        "SELECT usage_reset_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        return
    now = datetime.now(timezone.utc)
    reset_at = row["usage_reset_at"]
    if reset_at:
        last = datetime.fromisoformat(reset_at)
        if last.year == now.year and last.month == now.month:
            return  # same month — nothing to reset
    conn.execute(
        "UPDATE users SET tailors_used = 0, covers_used = 0, usage_reset_at = ? WHERE id = ?",
        (now.isoformat(), user_id),
    )
    conn.commit()


def check_and_increment_usage(user_id: int, kind: str) -> None:
    """Check the free-tier monthly limit and increment the counter.

    Raises HTTP 402 if the limit is reached.
    kind: 'tailor' | 'cover'
    """
    from applypilot.database import get_connection
    conn = get_connection()
    maybe_reset_usage(conn, user_id)
    row = conn.execute(
        "SELECT tier, tailors_used, covers_used FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row or row["tier"] == "pro":
        return  # pro users have no limits

    if kind == "tailor" and row["tailors_used"] >= FREE_TAILOR_LIMIT:
        raise HTTPException(
            status_code=402,
            detail=f"Free plan limit: {FREE_TAILOR_LIMIT} tailored resumes per month. Upgrade to Pro for unlimited.",
        )
    if kind == "cover" and row["covers_used"] >= FREE_COVER_LIMIT:
        raise HTTPException(
            status_code=402,
            detail=f"Free plan limit: {FREE_COVER_LIMIT} cover letter per month. Upgrade to Pro for unlimited.",
        )

    field = "tailors_used" if kind == "tailor" else "covers_used"
    conn.execute(f"UPDATE users SET {field} = {field} + 1 WHERE id = ?", (user_id,))
    conn.commit()


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
