"""Tests for `applypilot.enrichment.liveness.verify_job_open` (TST-002).

The module owns a single, process-wide ``httpx.Client`` reused across calls
(BE-017). To exercise its branches deterministically — without hitting the
network — we swap the ``_CLIENT`` for one built atop ``httpx.MockTransport``
and assert the function's three-valued return (``open`` / ``closed`` /
``unknown``) on each scenario.

We also assert the SSRF guard (``_is_safe_external_url``) raises
``UnsafeUrlError`` for loopback / link-local / private targets — that's the
SEC-006 regression.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from applypilot.enrichment import liveness as liveness_mod
from applypilot.enrichment.liveness import UnsafeUrlError, verify_job_open


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    """Build an httpx.Client backed by MockTransport with the same defaults
    as the real module-level client (UA + redirect-follow)."""
    transport = httpx.MockTransport(handler)
    return httpx.Client(
        transport=transport,
        timeout=5.0,
        follow_redirects=True,
        headers={"User-Agent": "test-ua"},
    )


@pytest.fixture
def patch_client(monkeypatch: pytest.MonkeyPatch) -> Callable[[Callable], None]:
    """Replace the module-level ``_CLIENT`` AND bypass DNS in the SSRF guard
    for the duration of the test.

    The SSRF guard's hostname path resolves DNS via ``socket.gethostbyname_ex``
    — that's CI-flaky and not what these tests are about. We swap the guard
    for a permissive replacement that only enforces the http(s) scheme check.
    Returns a closure: ``patch_client(handler)`` swaps in a MockTransport
    backed client; the monkeypatch fixture restores the original on teardown.

    SSRF-specific tests (loopback, link-local, etc.) do NOT use this fixture —
    they call `verify_job_open` directly with inputs whose literal-IP fast
    path triggers the guard before any DNS lookup.
    """

    def _allow_external(url: str) -> bool:
        from urllib.parse import urlparse

        scheme = urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise UnsafeUrlError(f"disallowed scheme: {scheme!r}")
        return True

    def _apply(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        client = _make_client(handler)
        monkeypatch.setattr(liveness_mod, "_CLIENT", client)
        monkeypatch.setattr(liveness_mod, "_is_safe_external_url", _allow_external)

    return _apply


# ---------------------------------------------------------------------------
# Closure phrases on a 200 response → "closed"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "no longer accepting applications",
        "this position has been filled",
        "this job has expired",
        "applications are now closed",
    ],
)
def test_closure_phrase_on_200_returns_closed(
    patch_client: Callable[[Callable], None], phrase: str
) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        body = f"<html><body>Update: {phrase.upper()} for this role.</body></html>"
        return httpx.Response(200, text=body)

    patch_client(handler)
    assert verify_job_open("https://example.com/job/1") == "closed"


def test_200_without_closure_phrase_returns_open(
    patch_client: Callable[[Callable], None],
) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        body = "<html><body><h1>We're hiring!</h1>Apply today.</body></html>"
        return httpx.Response(200, text=body)

    patch_client(handler)
    assert verify_job_open("https://example.com/job/2") == "open"


# ---------------------------------------------------------------------------
# Dead HTTP statuses → "closed"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [404, 410])
def test_dead_status_returns_closed(
    patch_client: Callable[[Callable], None], status: int
) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="Gone")

    patch_client(handler)
    assert verify_job_open("https://example.com/job/dead") == "closed"


# ---------------------------------------------------------------------------
# Anti-bot / transient errors → "unknown" (preserve the job)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [403, 500, 502, 503])
def test_transient_or_blocked_status_returns_unknown(
    patch_client: Callable[[Callable], None], status: int
) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="Service unavailable")

    patch_client(handler)
    assert verify_job_open("https://example.com/job/blocked") == "unknown"


def test_timeout_returns_unknown(patch_client: Callable[[Callable], None]) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout")

    patch_client(handler)
    assert verify_job_open("https://example.com/job/slow") == "unknown"


def test_connect_error_returns_unknown(
    patch_client: Callable[[Callable], None],
) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    patch_client(handler)
    assert verify_job_open("https://example.com/job/down") == "unknown"


# ---------------------------------------------------------------------------
# Empty / falsy URL → "unknown" without contacting transport
# ---------------------------------------------------------------------------


def test_empty_url_returns_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """`if not url: return "unknown"` short-circuit. Must not call the
    transport — we use a poisoned _CLIENT to assert that."""

    def _explode(_req: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("transport must not be called for empty url")

    client = _make_client(_explode)
    monkeypatch.setattr(liveness_mod, "_CLIENT", client)
    assert verify_job_open("") == "unknown"


# ---------------------------------------------------------------------------
# SSRF guard regression (SEC-006) — must raise, not return.
#
# These tests do NOT use the `patch_client` fixture: they hit the real
# `_is_safe_external_url` and rely on the literal-IP fast path so no DNS
# lookup happens.
# ---------------------------------------------------------------------------


def test_ssrf_guard_raises_for_loopback() -> None:
    """Loopback IP literals must be rejected by the SSRF guard."""
    with pytest.raises(UnsafeUrlError):
        verify_job_open("http://127.0.0.1/admin")


def test_ssrf_guard_raises_for_link_local_metadata() -> None:
    """AWS/GCP metadata endpoint at 169.254.169.254 must be blocked."""
    with pytest.raises(UnsafeUrlError):
        verify_job_open("http://169.254.169.254/latest/meta-data/")


def test_ssrf_guard_raises_for_private_ip() -> None:
    with pytest.raises(UnsafeUrlError):
        verify_job_open("http://10.0.0.1/")


def test_ssrf_guard_raises_for_non_http_scheme() -> None:
    with pytest.raises(UnsafeUrlError):
        verify_job_open("file:///etc/passwd")


# ---------------------------------------------------------------------------
# Sanity: passing a string-typed URL never returns None / non-Literal value.
# ---------------------------------------------------------------------------


def test_return_value_is_one_of_three_literals(
    patch_client: Callable[[Callable], None],
) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="hello")

    patch_client(handler)
    out: Any = verify_job_open("https://example.com/x")
    assert out in ("open", "closed", "unknown")
