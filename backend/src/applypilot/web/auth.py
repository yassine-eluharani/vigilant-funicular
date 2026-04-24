"""Clerk JWT authentication utilities and FastAPI dependency."""

from __future__ import annotations

import base64
import os
import time as _monotime
from datetime import datetime, timezone

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

_bearer = HTTPBearer(auto_error=False)

# ── Tier limits ───────────────────────────────────────────────────────────────

FREE_TAILOR_LIMIT = 3
FREE_COVER_LIMIT = 1
BLUR_SCORE_THRESHOLD = 8


# ── Clerk JWKS verification ───────────────────────────────────────────────────

_jwks_cache: dict | None = None
_jwks_cached_at: float = 0
_JWKS_TTL = 3600  # re-fetch JWKS every hour


def _get_jwks_url() -> str:
    url = os.environ.get("CLERK_JWKS_URL", "")
    if url:
        return url
    pk = (
        os.environ.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")
        or os.environ.get("CLERK_PUBLISHABLE_KEY", "")
    )
    if pk:
        try:
            b64 = pk.split("_", 2)[-1]
            padded = b64 + "=" * (-len(b64) % 4)
            frontend_api = base64.b64decode(padded).decode().rstrip("$")
            return f"https://{frontend_api}/.well-known/jwks.json"
        except Exception:
            pass
    raise RuntimeError(
        "Clerk not configured. Set NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY or CLERK_JWKS_URL."
    )


def _fetch_jwks(force: bool = False) -> dict:
    global _jwks_cache, _jwks_cached_at
    if not force and _jwks_cache and (_monotime.time() - _jwks_cached_at) < _JWKS_TTL:
        return _jwks_cache
    resp = httpx.get(_get_jwks_url(), timeout=10)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_cached_at = _monotime.time()
    return _jwks_cache


def verify_clerk_jwt(token: str) -> dict:
    """Verify a Clerk session JWT (RS256). Returns decoded payload."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Malformed token: {e}")

    kid = header.get("kid")

    def _find_key(jwks: dict):
        return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    key = _find_key(_fetch_jwks())
    if not key:
        # JWKS may be stale — refresh once
        key = _find_key(_fetch_jwks(force=True))
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token signing key not found")

    try:
        return jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")


# ── Clerk API fallback (fetch email/name when JWT lacks them) ─────────────────

def _fetch_clerk_user(clerk_id: str) -> dict | None:
    secret_key = os.environ.get("CLERK_SECRET_KEY", "")
    if not secret_key:
        return None
    try:
        resp = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_id}",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        emails = data.get("email_addresses", [])
        primary_id = data.get("primary_email_address_id")
        email = next((e["email_address"] for e in emails if e["id"] == primary_id), None)
        if not email and emails:
            email = emails[0]["email_address"]
        first = data.get("first_name") or ""
        last = data.get("last_name") or ""
        return {"email": email, "full_name": f"{first} {last}".strip() or None}
    except Exception:
        return None


# ── User upsert / sync ────────────────────────────────────────────────────────

# In-process cache: clerk_id → (monotonic_time, user_dict)
# Prevents 4 Turso HTTP calls per request for the same user.
_user_cache: dict[str, tuple[float, dict]] = {}
_USER_CACHE_TTL = 60.0  # seconds


def invalidate_user_cache(clerk_id: str) -> None:
    """Drop a user from the cache — call after profile/tier updates."""
    _user_cache.pop(clerk_id, None)


def upsert_user(clerk_id: str, email: str | None, full_name: str | None) -> dict:
    """Create or update a local user row from Clerk identity. Returns the full DB row.

    Result is cached per clerk_id for _USER_CACHE_TTL seconds to avoid hitting
    the DB on every request for the same user.
    """
    cached = _user_cache.get(clerk_id)
    if cached and (_monotime.monotonic() - cached[0]) < _USER_CACHE_TTL:
        return cached[1].copy()

    from applypilot.database import get_connection, init_db
    init_db()
    conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute("SELECT * FROM users WHERE clerk_id = ?", (clerk_id,)).fetchone()

    if existing:
        if email or full_name:
            conn.execute(
                "UPDATE users SET "
                "email = COALESCE(?, email), "
                "full_name = COALESCE(?, full_name), "
                "last_login = ? "
                "WHERE clerk_id = ?",
                (email, full_name, now, clerk_id),
            )
            conn.commit()
        row = conn.execute("SELECT * FROM users WHERE clerk_id = ?", (clerk_id,)).fetchone()
        result = dict(row)
        _user_cache[clerk_id] = (_monotime.monotonic(), result.copy())
        return result

    # New user — fall back to Clerk API if JWT didn't carry email/name
    if not email or not full_name:
        clerk_data = _fetch_clerk_user(clerk_id)
        if clerk_data:
            email = email or clerk_data.get("email")
            full_name = full_name or clerk_data.get("full_name")

    conn.execute(
        "INSERT OR IGNORE INTO users (clerk_id, email, full_name, created_at) "
        "VALUES (?, ?, ?, ?)",
        (clerk_id, email or f"{clerk_id}@unknown.clerk", full_name or "Unknown", now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE clerk_id = ?", (clerk_id,)).fetchone()
    result = dict(row)
    _user_cache[clerk_id] = (_monotime.monotonic(), result.copy())
    return result


def _sync_clerk_user(clerk_id: str, email: str | None, full_name: str | None) -> None:
    """Called by the Clerk webhook to proactively sync a user."""
    upsert_user(clerk_id, email, full_name)


def _delete_clerk_user(clerk_id: str) -> None:
    """Remove a local user when Clerk fires user.deleted."""
    from applypilot.database import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE clerk_id = ?", (clerk_id,))
    conn.commit()


# ── Tier / usage helpers ──────────────────────────────────────────────────────

def get_user_record(user_id: int) -> dict:
    """Fetch full user row including tier + usage counters."""
    from applypilot.database import get_connection
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
    row = conn.execute("SELECT usage_reset_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return
    now = datetime.now(timezone.utc)
    reset_at = row["usage_reset_at"]
    if reset_at:
        last = datetime.fromisoformat(reset_at)
        if last.year == now.year and last.month == now.month:
            return
    conn.execute(
        "UPDATE users SET tailors_used = 0, covers_used = 0, usage_reset_at = ? WHERE id = ?",
        (now.isoformat(), user_id),
    )
    conn.commit()


def check_and_increment_usage(user_id: int, kind: str) -> None:
    """Check the free-tier monthly limit and increment the counter. Raises 402 if exceeded."""
    from applypilot.database import get_connection
    conn = get_connection()
    maybe_reset_usage(conn, user_id)
    row = conn.execute(
        "SELECT tier, tailors_used, covers_used FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row or row["tier"] == "pro":
        return
    if kind == "tailor" and row["tailors_used"] >= FREE_TAILOR_LIMIT:
        raise HTTPException(
            status_code=402,
            detail=f"Free plan limit: {FREE_TAILOR_LIMIT} tailored resumes per month. Upgrade to Pro.",
        )
    if kind == "cover" and row["covers_used"] >= FREE_COVER_LIMIT:
        raise HTTPException(
            status_code=402,
            detail=f"Free plan limit: {FREE_COVER_LIMIT} cover letter per month. Upgrade to Pro.",
        )
    field = "tailors_used" if kind == "tailor" else "covers_used"
    conn.execute(f"UPDATE users SET {field} = {field} + 1 WHERE id = ?", (user_id,))
    conn.commit()


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Verify Clerk Bearer JWT. Upserts the user in local DB. Returns the DB row.

    Adds a 'sub' key (= str(id)) for backward compat with callers that do int(user["sub"]).
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_clerk_jwt(credentials.credentials)
    clerk_id: str = payload.get("sub", "")
    # JWT template claims (optional — configure in Clerk dashboard)
    email: str | None = payload.get("email")
    name: str | None = payload.get("name") or payload.get("full_name")

    user = upsert_user(clerk_id, email, name)
    user["sub"] = str(user["id"])  # backward compat for int(user["sub"]) callers
    return user
