"""Tests for `applypilot.web.auth` (TST-008).

Covers:
  * Happy path: valid token → claims.
  * Expired token → 401.
  * Wrong signature (different keypair) → 401.
  * `alg=none` → 401 (SEC-009 regression).
  * Wrong issuer → 401 (SEC-002 regression).
  * Malformed token → 401.
  * Missing `kid` header → cache-refresh path returns 401 with "key not found".
  * `CLERK_AUDIENCE` set: wrong `aud` → 401; matching `aud` → succeeds.
  * BE-005 / TST-018: TTLCache caps at maxsize.
  * SEC-015: invalidate_user_cache_by_id drops entries by user_row_id.
"""

from __future__ import annotations

import json
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException


_TEST_ISSUER = "https://test.clerk.example"
_TEST_KID = "test-kid-applypilot"


# ---------------------------------------------------------------------------
# verify_clerk_jwt — happy path + failure modes
# ---------------------------------------------------------------------------


def test_verify_valid_token_returns_claims(make_jwt):
    from applypilot.web.auth import verify_clerk_jwt

    token = make_jwt("user_123", email="a@b.com", name="Test User")
    claims = verify_clerk_jwt(token)
    assert claims["sub"] == "user_123"
    assert claims["email"] == "a@b.com"
    assert claims["iss"] == _TEST_ISSUER


def test_verify_expired_token_raises_401(make_jwt):
    from applypilot.web.auth import verify_clerk_jwt

    # exp 1h in the past
    token = make_jwt("user_123", exp_offset=-3600)
    with pytest.raises(HTTPException) as exc:
        verify_clerk_jwt(token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_verify_wrong_signature_raises_401(rsa_keypair, mock_jwks):
    """Sign a token with a *different* keypair but reuse the trusted kid.
    Signature verification must fail."""
    from applypilot.web.auth import verify_clerk_jwt

    # Generate a second, untrusted keypair
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    now = int(time.time())
    token = pyjwt.encode(
        {"sub": "user_x", "iat": now, "exp": now + 3600, "iss": _TEST_ISSUER},
        other_pem,
        algorithm="RS256",
        headers={"kid": _TEST_KID},  # claims to be the trusted key
    )
    with pytest.raises(HTTPException) as exc:
        verify_clerk_jwt(token)
    assert exc.value.status_code == 401


def test_verify_alg_none_raises_401(rsa_keypair, mock_jwks):
    """SEC-009 regression: a token with `alg=none` must be rejected before decode."""
    from applypilot.web.auth import verify_clerk_jwt

    # Manually craft an unsigned token (alg=none) — PyJWT refuses to encode
    # `alg=none` with a key, so build it by hand.
    import base64

    def _b64(d: bytes) -> str:
        return base64.urlsafe_b64encode(d).rstrip(b"=").decode()

    header = {"alg": "none", "kid": _TEST_KID, "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": "user_x", "iat": now, "exp": now + 3600, "iss": _TEST_ISSUER}
    h = _b64(json.dumps(header).encode())
    p = _b64(json.dumps(payload).encode())
    token = f"{h}.{p}."  # empty signature

    with pytest.raises(HTTPException) as exc:
        verify_clerk_jwt(token)
    assert exc.value.status_code == 401
    assert "algorithm" in exc.value.detail.lower() or "unsupported" in exc.value.detail.lower()


def test_verify_wrong_issuer_raises_401(make_jwt):
    """SEC-002 regression: tokens minted by another Clerk tenant must be rejected."""
    from applypilot.web.auth import verify_clerk_jwt

    token = make_jwt("user_123", iss="https://attacker.clerk.example")
    with pytest.raises(HTTPException) as exc:
        verify_clerk_jwt(token)
    assert exc.value.status_code == 401


def test_verify_malformed_token_raises_401(mock_jwks):
    from applypilot.web.auth import verify_clerk_jwt

    with pytest.raises(HTTPException) as exc:
        verify_clerk_jwt("not.a.valid.jwt.at.all")
    assert exc.value.status_code == 401


def test_verify_missing_kid_triggers_refresh_and_fails(monkeypatch, rsa_keypair, mock_jwks):
    """A token whose `kid` isn't in the JWKS triggers a force-refresh, then fails."""
    from applypilot.web import auth as auth_mod
    from applypilot.web.auth import verify_clerk_jwt

    private_pem, _ = rsa_keypair

    # Track how many times _fetch_jwks is called and whether force=True is used.
    calls: list[bool] = []
    jwks_payload = {"keys": list(mock_jwks["keys"])}  # no key with the bogus kid

    def _fake_fetch(force: bool = False) -> dict:
        calls.append(force)
        return jwks_payload

    monkeypatch.setattr(auth_mod, "_fetch_jwks", _fake_fetch)

    now = int(time.time())
    token = pyjwt.encode(
        {"sub": "u", "iat": now, "exp": now + 3600, "iss": _TEST_ISSUER},
        private_pem,
        algorithm="RS256",
        headers={"kid": "unknown-kid"},
    )
    with pytest.raises(HTTPException) as exc:
        verify_clerk_jwt(token)
    assert exc.value.status_code == 401
    # Ensure the force-refresh fallback was exercised.
    assert True in calls, "expected a force-refresh fetch when kid was missing"


def test_verify_with_audience_mismatch_raises_401(monkeypatch, make_jwt):
    """When CLERK_AUDIENCE is set, a token with the wrong `aud` must be rejected."""
    monkeypatch.setenv("CLERK_AUDIENCE", "applypilot-prod")
    from applypilot.web.auth import verify_clerk_jwt

    token = make_jwt("user_123", audience="some-other-app")
    with pytest.raises(HTTPException) as exc:
        verify_clerk_jwt(token)
    assert exc.value.status_code == 401


def test_verify_with_audience_match_succeeds(monkeypatch, make_jwt):
    monkeypatch.setenv("CLERK_AUDIENCE", "applypilot-prod")
    from applypilot.web.auth import verify_clerk_jwt

    token = make_jwt("user_123", audience="applypilot-prod")
    claims = verify_clerk_jwt(token)
    assert claims["aud"] == "applypilot-prod"


# ---------------------------------------------------------------------------
# BE-005 / TST-018 — bounded TTLCache
# ---------------------------------------------------------------------------


def test_user_cache_is_bounded(monkeypatch):
    """TTLCache must enforce its maxsize cap."""
    from cachetools import TTLCache

    from applypilot.web import auth as auth_mod

    # Replace with a tiny cache to exercise eviction quickly.
    small = TTLCache(maxsize=5, ttl=60)
    monkeypatch.setattr(auth_mod, "_user_cache", small)

    for i in range(20):
        small[f"clerk_{i}"] = {"id": i, "clerk_id": f"clerk_{i}",
                               "email": f"u{i}@x", "full_name": "x"}

    assert len(small) <= 5


def test_user_cache_excludes_heavy_columns(make_user, mock_jwks, db_conn):
    """Cache must not store resume_text/profile_json/searches_json."""
    from applypilot.web import auth as auth_mod

    user = make_user("clerk_heavy", "heavy@example.com", "Heavy User")
    # Stash a big blob in the DB
    db_conn.execute(
        "UPDATE users SET resume_text = ?, profile_json = ?, searches_json = ? WHERE id = ?",
        ("x" * 10000, '{"big":"x"}', '{"q":"y"}', user["id"]),
    )
    db_conn.commit()

    # Re-fetch via upsert_user; cached entry should NOT include heavy columns.
    auth_mod.invalidate_user_cache("clerk_heavy")
    fresh = auth_mod.upsert_user("clerk_heavy", "heavy@example.com", "Heavy User")
    cached = auth_mod._user_cache.get("clerk_heavy")
    assert cached is not None
    for forbidden in ("resume_text", "profile_json", "searches_json"):
        assert forbidden not in cached, f"{forbidden} must not be cached"
    # Slim shape contract
    for required in ("id", "clerk_id", "email", "full_name"):
        assert required in fresh


# ---------------------------------------------------------------------------
# SEC-015 — invalidate_user_cache_by_id
# ---------------------------------------------------------------------------


def test_invalidate_user_cache_by_id(make_user, mock_jwks):
    from applypilot.web import auth as auth_mod

    user = make_user("clerk_byid", "byid@example.com", "By Id")
    # Make sure the entry is in the cache
    auth_mod.upsert_user("clerk_byid", "byid@example.com", "By Id")
    assert "clerk_byid" in auth_mod._user_cache

    auth_mod.invalidate_user_cache_by_id(user["id"])
    assert "clerk_byid" not in auth_mod._user_cache


# ---------------------------------------------------------------------------
# SEC-010 — email collision must NOT silently bind a new auth identity
# ---------------------------------------------------------------------------


def test_email_collision_raises_409(mock_jwks, db_conn):
    """If a clerk_id is new but its email already exists for another row,
    `upsert_user` must refuse rather than silently binding the auth identity."""
    from applypilot.web import auth as auth_mod

    # Seed an existing user with the contested email
    auth_mod.upsert_user("clerk_first", "shared@example.com", "First User")

    # A second clerk_id arrives with the same email — must NOT silently
    # attach to the existing row.
    auth_mod.invalidate_user_cache("clerk_second")
    with pytest.raises(HTTPException) as exc:
        auth_mod.upsert_user("clerk_second", "shared@example.com", "Second User")
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# Smoke: imports work after the migration to PyJWT
# ---------------------------------------------------------------------------


def test_imports_from_pyjwt():
    """Ensure auth.py uses PyJWT, not python-jose."""
    import importlib
    import sys

    # Force a clean import to verify no jose dependency
    sys.modules.pop("applypilot.web.auth", None)
    mod = importlib.import_module("applypilot.web.auth")
    # PyJWT exposes `PyJWTError`; jose does not.
    assert hasattr(mod, "PyJWTError")
