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
_JWT_EXPIRY_DAYS = 7

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def _get_app_password() -> str:
    """Read APP_PASSWORD from environment or data/.env file."""
    pw = os.environ.get("APP_PASSWORD", "")
    if pw:
        return pw
    # Try reading from APPLYPILOT_DIR/.env at runtime
    from applypilot.config import APP_DIR
    env_file = APP_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("APP_PASSWORD="):
                return line.partition("=")[2].strip().strip('"').strip("'")
    return ""


def create_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_JWT_EXPIRY_DAYS)
    return jwt.encode({"exp": expire, "sub": "user"}, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def verify_password(plain: str) -> bool:
    expected = _get_app_password()
    if not expected:
        # No password set — allow access (dev / first-run)
        return True
    # Support both plain-text and bcrypt-hashed passwords
    if expected.startswith("$2b$") or expected.startswith("$2a$"):
        return _pwd_context.verify(plain, expected)
    return plain == expected


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI dependency — validates Bearer JWT, raises 401 if invalid."""
    secret = os.environ.get("JWT_SECRET", _JWT_SECRET)
    if not _get_app_password():
        # No password configured — open access (useful for local-only installs)
        return {"sub": "user"}
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, secret, algorithms=[_JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
