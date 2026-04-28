"""Clerk JWT authentication utilities and FastAPI dependency.

BE-002 — Sync I/O off the event loop (Option B):
The DB helpers (``upsert_user``, ``get_user_record``, ``maybe_reset_usage``,
``check_and_increment_usage``, ``decrement_usage``) and the JWT verifier
(``verify_clerk_jwt``) all use sync ``httpx.Client`` / ``sqlite3`` under the
hood. Rather than rewrite them as async (which would propagate ``async`` up
through every caller and require an ``httpx.AsyncClient``-based Turso
wrapper), we keep them sync and offload to the FastAPI threadpool at the
async call sites via ``await asyncio.to_thread(...)``. This is the minimum
change that unblocks the event loop while preserving all existing tests and
sync call paths (e.g. background ``_run_task`` workers in ``web/core.py``).

A future BE-002b could convert the helpers themselves to ``async def`` and
swap to ``httpx.AsyncClient`` — but that's a much larger refactor for
marginal additional benefit beyond what the threadpool already absorbs.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time as _monotime
from datetime import datetime, timezone

import httpx
import jwt
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
    PyJWTError,
)
from jwt.algorithms import RSAAlgorithm

log = logging.getLogger(__name__)

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


def _get_expected_issuer() -> str:
    """Derive the expected JWT `iss` claim from the JWKS URL.

    Clerk issues tokens with `iss` set to the Frontend API origin
    (i.e. the JWKS URL minus `/.well-known/jwks.json`).
    """
    jwks_url = _get_jwks_url()
    suffix = "/.well-known/jwks.json"
    if jwks_url.endswith(suffix):
        return jwks_url[: -len(suffix)]
    # Fallback: strip any trailing slash
    return jwks_url.rstrip("/")


_audience_warning_logged = False


def _get_expected_audience() -> str | None:
    """Optional audience pin via `CLERK_AUDIENCE`.

    Clerk JWTs use `azp` rather than standard `aud` by default, so audience
    validation is opt-in. If unset, we skip `aud` verification and log a
    one-time startup warning.
    """
    global _audience_warning_logged
    aud = os.environ.get("CLERK_AUDIENCE", "").strip()
    if aud:
        return aud
    if not _audience_warning_logged:
        log.warning(
            "CLERK_AUDIENCE is not set — JWT audience claim will not be validated. "
            "Issuer pinning still protects against cross-tenant tokens, but consider "
            "setting CLERK_AUDIENCE for defense in depth."
        )
        _audience_warning_logged = True
    return None


def _fetch_jwks(force: bool = False) -> dict:
    global _jwks_cache, _jwks_cached_at
    if not force and _jwks_cache and (_monotime.time() - _jwks_cached_at) < _JWKS_TTL:
        return _jwks_cache
    resp = httpx.get(_get_jwks_url(), timeout=10)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_cached_at = _monotime.time()
    return _jwks_cache


def _jwk_to_public_key(jwk: dict):
    """Convert a JWK dict to a PyJWT-acceptable public key (RSA public key object).

    PyJWT's `jwt.decode` accepts the public key as either PEM bytes/str or a
    cryptography public key object. `RSAAlgorithm.from_jwk` returns the latter.
    """
    return RSAAlgorithm.from_jwk(json.dumps(jwk))


def verify_clerk_jwt(token: str) -> dict:
    """Verify a Clerk session JWT (RS256). Returns decoded payload.

    Hardening (SEC-002 / SEC-009):
      * Reject any token whose header `alg` is not exactly `RS256` BEFORE
        invoking `jwt.decode` (defense in depth against alg-confusion /
        `none` attacks even though `algorithms=["RS256"]` is also pinned).
      * Pin the expected issuer derived from the configured Clerk Frontend
        API host, so tokens minted by other Clerk tenants are rejected.
      * Optionally pin the audience when `CLERK_AUDIENCE` is set.
    """
    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Malformed token: {e}")

    # Defense in depth: reject anything other than RS256 before decode.
    if header.get("alg") != "RS256":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: unsupported signing algorithm",
        )

    kid = header.get("kid")

    def _find_key(jwks: dict):
        return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    jwk = _find_key(_fetch_jwks())
    if not jwk:
        # JWKS may be stale — refresh once
        jwk = _find_key(_fetch_jwks(force=True))
    if not jwk:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token signing key not found")

    try:
        public_key = _jwk_to_public_key(jwk)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token signing key: {e}",
        )

    expected_issuer = _get_expected_issuer()
    expected_audience = _get_expected_audience()

    decode_kwargs: dict = {
        "algorithms": ["RS256"],
        "issuer": expected_issuer,
    }
    if expected_audience is not None:
        decode_kwargs["audience"] = expected_audience
    else:
        # Disable aud verification when no audience is pinned. PyJWT verifies
        # `aud` by default if the token contains the claim — opt out explicitly.
        decode_kwargs["options"] = {"verify_aud": False}

    try:
        return jwt.decode(token, public_key, **decode_kwargs)
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except InvalidIssuerError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    except InvalidAudienceError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    except InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    except PyJWTError as e:
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

# Bounded LRU+TTL cache: clerk_id → minimal user dict
# (BE-005) Prevents unbounded growth and avoids holding large columns
# (resume_text / profile_json / searches_json) in memory. Callers that need
# those fields must call `get_user_record` or query the DB directly.
_USER_CACHE_TTL = 60.0  # seconds
_USER_CACHE_MAX = 10_000  # hard cap (TST-018)
_user_cache: TTLCache[str, dict] = TTLCache(maxsize=_USER_CACHE_MAX, ttl=_USER_CACHE_TTL)

# Columns that are safe + small enough to cache. Anything else (resume_text,
# profile_json, searches_json, etc.) must NOT be cached — we re-query on demand.
_CACHED_USER_COLUMNS = ("id", "clerk_id", "email", "full_name", "tier")


def _slim_user(row: dict) -> dict:
    """Project a full users row down to the cached subset."""
    return {k: row.get(k) for k in _CACHED_USER_COLUMNS}


def invalidate_user_cache(clerk_id: str) -> None:
    """Drop a user from the cache — call after profile/tier updates."""
    if not clerk_id:
        return
    _user_cache.pop(clerk_id, None)


def invalidate_user_cache_by_id(user_row_id: int) -> None:
    """Drop cache entries whose stored user `id` matches.

    Used by webhook code paths that don't have a clerk_id readily available
    (e.g. downgrade-by-subscription_id) — without this, an entry keyed on
    NULL/unknown clerk_id would be no-op'd. (SEC-015)
    """
    if user_row_id is None:
        return
    # TTLCache is dict-like; iterate over a snapshot of keys to allow mutation.
    for clerk_id in list(_user_cache.keys()):
        entry = _user_cache.get(clerk_id)
        if entry and entry.get("id") == user_row_id:
            _user_cache.pop(clerk_id, None)


def upsert_user(clerk_id: str, email: str | None, full_name: str | None) -> dict:
    """Create or update a local user row from Clerk identity.

    Returns a SLIM user dict (id, clerk_id, email, full_name, tier).
    Callers that need profile_json / resume_text / searches_json must call
    `get_user_record` or query the DB directly.

    Result is cached per clerk_id for `_USER_CACHE_TTL` seconds (TTLCache,
    capped at `_USER_CACHE_MAX` entries) to avoid hitting the DB on every
    request for the same user.
    """
    cached = _user_cache.get(clerk_id)
    if cached is not None:
        return cached.copy()

    from applypilot.database import get_connection, init_db
    init_db()
    conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT id, clerk_id, email, full_name, tier FROM users WHERE clerk_id = ?",
        (clerk_id,),
    ).fetchone()

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
        row = conn.execute(
            "SELECT id, clerk_id, email, full_name, tier FROM users WHERE clerk_id = ?",
            (clerk_id,),
        ).fetchone()
        result = _slim_user(dict(row))
        _user_cache[clerk_id] = result.copy()
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

    row = conn.execute(
        "SELECT id, clerk_id, email, full_name, tier FROM users WHERE clerk_id = ?",
        (clerk_id,),
    ).fetchone()

    if row is None:
        # SEC-010: INSERT OR IGNORE silently swallowed a UNIQUE collision. If
        # the SELECT-by-clerk_id misses, the only way INSERT can have been
        # ignored is an email collision (clerk_id is also UNIQUE but if it
        # already existed we'd have hit the `existing` branch above). Refuse
        # to silently bind a new auth identity to a pre-existing email row.
        collision = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email or f"{clerk_id}@unknown.clerk",),
        ).fetchone()
        if collision:
            log.error(
                "Email collision on user upsert: clerk_id=%s email=%s collides with user_id=%s",
                clerk_id, email, collision["id"],
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    "An account with this email already exists. "
                    "Please contact support to recover your account."
                ),
            )
        # Truly absent (race or DB issue) — surface as 500 so it's visible.
        log.error(
            "User upsert produced no row and no email collision: clerk_id=%s email=%s",
            clerk_id, email,
        )
        raise HTTPException(status_code=500, detail="User provisioning failed")

    result = _slim_user(dict(row))
    _user_cache[clerk_id] = result.copy()
    return result


# BE-013: `_sync_clerk_user` and `_delete_clerk_user` were defined here but
# never wired up — no router imported them and no /api/clerk/webhook route
# existed to call them. Deleted in favor of dead-code removal. If we later
# want to react to Clerk's user.created / user.deleted webhooks (e.g. to
# scrub local rows when a user deletes their Clerk account), reintroduce them
# alongside a new router that verifies the Svix signature and dispatches by
# event type. The existing `upsert_user` / `invalidate_user_cache` helpers
# already cover what those functions did.


# ── Tier / usage helpers ──────────────────────────────────────────────────────

def get_user_record(user_id: int) -> dict:
    """Fetch full user row including tier + usage counters."""
    from applypilot.database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, full_name, tier, tailors_used, covers_used, usage_reset_at, profile_json "
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
    """Atomically check the free-tier monthly limit and increment the counter.

    BE-011: Previously this was a read-then-write pair, so two concurrent
    tailor calls at `tailors_used = 2` could both pass the cap check before
    either UPDATE landed, allowing a single user to silently exceed the cap.

    The fix collapses the check + bump into a single UPDATE whose WHERE clause
    enforces the cap. We rely on `cursor.rowcount` (works for both sqlite3 and
    the libsql HTTP wrapper, which sets `affected_row_count` from the
    response): if 0 rows were updated, the user is at the cap and we raise
    402. Pro users always pass via the `tier = 'pro'` branch in the WHERE.

    The counter is debited before the LLM task starts. If the task fails,
    `_run_task` (web/core.py) calls `decrement_usage` to roll back so the
    user isn't charged for an artifact they never received.
    """
    from applypilot.database import get_connection
    conn = get_connection()
    maybe_reset_usage(conn, user_id)

    if kind == "tailor":
        column = "tailors_used"
        limit = FREE_TAILOR_LIMIT
        detail = (
            f"Free plan limit: {FREE_TAILOR_LIMIT} tailored resumes per month. "
            "Upgrade to Pro."
        )
    elif kind == "cover":
        column = "covers_used"
        limit = FREE_COVER_LIMIT
        detail = (
            f"Free plan limit: {FREE_COVER_LIMIT} cover letter per month. "
            "Upgrade to Pro."
        )
    else:
        raise ValueError(f"unknown usage kind: {kind!r}")

    # Single atomic UPDATE: bumps the counter only if the user is pro OR
    # currently under the cap. If the user doesn't exist or is at the cap,
    # rowcount comes back as 0 and we raise 402.
    cursor = conn.execute(
        f"UPDATE users SET {column} = {column} + 1 "
        f"WHERE id = ? AND (tier = 'pro' OR {column} < ?)",
        (user_id, limit),
    )
    conn.commit()

    if cursor.rowcount == 0:
        # Either the user is missing or they hit the cap. Distinguish so we
        # don't mask a "user not found" as a quota error.
        row = conn.execute(
            "SELECT id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        raise HTTPException(status_code=402, detail=detail)


def decrement_usage(user_id: int, kind: str) -> None:
    """Roll back a usage counter increment when an LLM task fails (BE-011).

    Called by `_run_task` in `web/core.py` when a tailor/cover task ends in
    `error` state. Idempotent: clamped at 0 via MAX so a double-call (or a
    rollback for a pro user whose counter was 0 to begin with) never produces
    a negative balance.
    """
    if kind == "tailor":
        column = "tailors_used"
    elif kind == "cover":
        column = "covers_used"
    else:
        return  # silently ignore non-quota'd task kinds (e.g. score)
    from applypilot.database import get_connection
    conn = get_connection()
    conn.execute(
        f"UPDATE users SET {column} = MAX(0, {column} - 1) WHERE id = ?",
        (user_id,),
    )
    conn.commit()


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Verify Clerk Bearer JWT. Upserts the user in local DB. Returns the slim user dict.

    Adds a 'sub' key (= str(id)) for backward compat with callers that do int(user["sub"]).

    BE-002: This dependency is invoked on every authed request, and previously
    blocked the event loop on (a) sync ``httpx`` JWKS / Clerk-API fetches
    inside ``verify_clerk_jwt`` and (b) sync DB writes inside ``upsert_user``.
    Both calls are now offloaded to the threadpool via ``asyncio.to_thread``.
    The TTL-cache hit path inside ``upsert_user`` is in-memory and returns
    almost instantly, but routing it through the threadpool keeps the
    semantics uniform (and avoids surprising thread-locality issues).
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await asyncio.to_thread(verify_clerk_jwt, credentials.credentials)
    clerk_id: str = payload.get("sub", "")
    # JWT template claims (optional — configure in Clerk dashboard)
    email: str | None = payload.get("email")
    name: str | None = payload.get("name") or payload.get("full_name")

    user = await asyncio.to_thread(upsert_user, clerk_id, email, name)
    user["sub"] = str(user["id"])  # backward compat for int(user["sub"]) callers
    return user
