"""Shared test fixtures for ApplyPilot backend tests.

Provides:
  - tmp_db:      fresh SQLite DB in a temp dir (per-test).
  - rsa_keypair: RSA-2048 keypair (session-scoped).
  - mock_jwks:   monkeypatches _fetch_jwks + CLERK env vars.
  - make_jwt:    factory that mints RS256 JWTs signed with the test key.
  - client:      FastAPI TestClient bound to the temp DB and mocked auth.
  - make_user:   factory that creates a DB user via upsert_user.

The fixtures intentionally avoid importing applypilot modules at module
load time — `APPLYPILOT_DIR` must be set before `applypilot.config` resolves
`DB_PATH`, otherwise the production DB path would be used.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


# ---------------------------------------------------------------------------
# RSA keypair (session-scoped) and JWKS
# ---------------------------------------------------------------------------

_TEST_KID = "test-kid-applypilot"
_TEST_JWKS_URL = "https://test.clerk.example/.well-known/jwks.json"
_TEST_ISSUER = "https://test.clerk.example"


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[bytes, dict]:
    """Generate an RSA-2048 keypair. Returns (private_pem_bytes, public_jwk_dict)."""
    import json

    from jwt.algorithms import RSAAlgorithm

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()

    # PyJWT's RSAAlgorithm.to_jwk yields a JSON string; parse it for the dict.
    public_jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    public_jwk["kid"] = _TEST_KID
    public_jwk["use"] = "sig"
    public_jwk["alg"] = "RS256"

    return private_pem, public_jwk


# ---------------------------------------------------------------------------
# Per-test temp DB + env wiring
# ---------------------------------------------------------------------------


def _reset_applypilot_modules() -> None:
    """Drop applypilot modules from sys.modules so they pick up the new env vars.

    This is necessary because `applypilot.config.DB_PATH` is a module-level
    constant evaluated at import time — once imported, it's frozen.
    """
    for name in list(sys.modules.keys()):
        if name == "applypilot" or name.startswith("applypilot."):
            del sys.modules[name]


@pytest.fixture
def tmp_db(monkeypatch, rsa_keypair):
    """Set up a fresh per-test SQLite DB and wire all env vars.

    Yields the DB path. Tears down by clearing module state so the next
    test starts from a clean slate.
    """
    tmp_dir = tempfile.mkdtemp(prefix="applypilot-test-")
    monkeypatch.setenv("APPLYPILOT_DIR", tmp_dir)

    # Auth: point JWKS at our fake URL — _fetch_jwks is monkeypatched below
    # in the `mock_jwks` fixture, but _get_expected_issuer reads the env var
    # directly so we set it here.
    monkeypatch.setenv("CLERK_JWKS_URL", _TEST_JWKS_URL)
    # Ensure no real Clerk publishable key bleeds in via .env
    monkeypatch.delenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("CLERK_AUDIENCE", raising=False)
    # Prevent any production DB_URL from being picked up — force local SQLite.
    # We set to empty string (instead of delenv) because applypilot.web.server
    # calls load_env() at import time which would otherwise re-populate from
    # .env. python-dotenv won't override an existing env var (even an empty
    # one) by default, so this pin sticks.
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_TOKEN", "")

    _reset_applypilot_modules()

    # Now import + initialize against the temp dir
    from applypilot.database import init_db  # noqa: E402

    init_db()

    yield Path(tmp_dir) / "applypilot.db"

    # Best-effort cleanup
    _reset_applypilot_modules()


@pytest.fixture
def mock_jwks(monkeypatch, rsa_keypair, tmp_db):
    """Force `_fetch_jwks` to return our test JWKS, never hitting the network."""
    _, public_jwk = rsa_keypair
    jwks_payload = {"keys": [public_jwk]}

    from applypilot.web import auth as auth_mod

    # Pre-populate the cache so any call path returns instantly.
    auth_mod._jwks_cache = jwks_payload
    auth_mod._jwks_cached_at = time.time()
    monkeypatch.setattr(auth_mod, "_fetch_jwks", lambda force=False: jwks_payload)
    # Drop any stale per-clerk_id user cache entries between tests.
    auth_mod._user_cache.clear()
    return jwks_payload


@pytest.fixture
def make_jwt(rsa_keypair, mock_jwks):
    """Factory: make_jwt(sub, email='..@x', name='...') → signed RS256 JWT string."""
    private_pem, _ = rsa_keypair

    def _make(sub: str, email: str | None = None, name: str | None = None,
              exp_offset: int = 3600, iss: str | None = None,
              audience: str | None = None) -> str:
        import jwt as pyjwt
        now = int(time.time())
        claims: dict = {
            "sub": sub,
            "iat": now,
            "exp": now + exp_offset,
            "iss": iss if iss is not None else _TEST_ISSUER,
        }
        if email is not None:
            claims["email"] = email
        if name is not None:
            claims["name"] = name
        if audience is not None:
            claims["aud"] = audience
        return pyjwt.encode(
            claims,
            private_pem,
            algorithm="RS256",
            headers={"kid": "test-kid-applypilot"},
        )

    return _make


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_db, mock_jwks, monkeypatch):
    """A TestClient with the FastAPI app loaded against the temp DB.

    Also stubs out `verify_job_open` so job-detail / tailor flows don't try
    to hit the real network during isolation tests.
    """
    # Stub liveness check — return "unknown" so the route doesn't mark closed
    # or call out to the network.
    from applypilot.enrichment import liveness as liveness_mod

    monkeypatch.setattr(liveness_mod, "verify_job_open", lambda url, timeout=5.0: "unknown")
    # The jobs router imports the symbol at module load time — patch there too.
    from applypilot.web.routers import jobs as jobs_router

    monkeypatch.setattr(jobs_router, "verify_job_open", lambda url, timeout=5.0: "unknown")

    from fastapi.testclient import TestClient
    from applypilot.web.server import app

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# User factory
# ---------------------------------------------------------------------------


@pytest.fixture
def make_user(tmp_db):
    """Factory: make_user(clerk_id, email, full_name, tier='free') → user dict."""

    def _make(clerk_id: str, email: str, full_name: str = "Test User",
              tier: str = "free") -> dict:
        from applypilot.database import get_connection
        from applypilot.web.auth import upsert_user, invalidate_user_cache

        invalidate_user_cache(clerk_id)
        user = upsert_user(clerk_id, email, full_name)
        if tier != "free":
            conn = get_connection()
            conn.execute("UPDATE users SET tier = ? WHERE id = ?", (tier, user["id"]))
            conn.commit()
            invalidate_user_cache(clerk_id)
            user = upsert_user(clerk_id, email, full_name)
        return user

    return _make


# ---------------------------------------------------------------------------
# Direct DB connection helper
# ---------------------------------------------------------------------------


@pytest.fixture
def db_conn(tmp_db):
    """A raw sqlite3 connection to the temp DB (commits/rollbacks at test end)."""
    from applypilot.database import get_connection
    return get_connection()


# ---------------------------------------------------------------------------
# Auth header helper
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_headers(make_jwt):
    """Factory: auth_headers(clerk_id, email='...', name='...') → {'Authorization': 'Bearer ...'}."""

    def _make(clerk_id: str, email: str | None = None, name: str | None = None) -> dict:
        token = make_jwt(clerk_id, email=email, name=name)
        return {"Authorization": f"Bearer {token}"}

    return _make
