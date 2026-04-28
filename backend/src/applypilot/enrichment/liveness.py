"""Lightweight job-posting liveness check.

Used before tailor / cover_letter to avoid wasting LLM calls and the user's
monthly quota on dead postings, and on detail-drawer open to surface stale
listings before the user sinks effort into them.

Intentionally cheap: one httpx GET, regex on the response body. We don't spin
up Chromium — for the common boards (LinkedIn, Indeed, Workday, Greenhouse,
Lever, etc.) the closure marker is in the initial HTML or comes back as a 4xx.
"""

from __future__ import annotations

import atexit
import ipaddress
import logging
import socket
from typing import Literal
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

LivenessStatus = Literal["open", "closed", "unknown"]


class UnsafeUrlError(ValueError):
    """Raised when a URL fails safety validation (SSRF guard).

    Indicates the URL targets an unsafe scheme, a private/loopback/link-local
    address, or otherwise resolves to an internal-network destination. Callers
    should treat this as equivalent to "the posting can't be fetched" — i.e.
    don't blindly let it bubble up as a 500.
    """


# Substrings that strongly indicate the posting is closed. Lowercased; we match
# against a lowercased response body. Keep these specific — we'd rather return
# "unknown" and preserve a job than false-positive on unrelated text.
_CLOSED_PHRASES: tuple[str, ...] = (
    "no longer accepting applications",
    "this job is no longer accepting",
    "this job has expired",
    "this job is no longer available",
    "this job has been removed",
    "this position is no longer available",
    "this position has been filled",
    "the role has been filled",
    "this opportunity has closed",
    "this job is no longer open",
    "applications are now closed",
    "this listing has expired",
    "we are no longer accepting applications",
    "the job you are looking for is not available",
)

_DEAD_HTTP_STATUSES: frozenset[int] = frozenset({404, 410})

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_DEFAULT_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# Module-level client reused across calls (BE-017). Configured for keep-alive
# pooling and follow-redirects. Closed at process exit via atexit.
_CLIENT: httpx.Client = httpx.Client(
    timeout=5.0,
    follow_redirects=True,
    headers=_DEFAULT_HEADERS,
)


@atexit.register
def _close_client() -> None:
    try:
        _CLIENT.close()
    except Exception:  # pragma: no cover — best-effort shutdown
        pass


def _ip_is_unsafe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP address points at an internal/non-routable target."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _is_safe_external_url(url: str) -> bool:
    """SSRF guard: validate that ``url`` targets a public, http(s) destination.

    Raises:
        UnsafeUrlError: if the scheme is not http/https, the URL is malformed,
            or the host resolves to an internal/loopback/link-local address.

    Returns:
        True if the URL passed all checks. (We return rather than just raising
        so callers can use this as a predicate-style guard if they wish — but
        the raising path is the primary contract.)
    """
    if not url or not isinstance(url, str):
        raise UnsafeUrlError("empty or non-string url")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise UnsafeUrlError(f"unparseable url: {e}") from e

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"disallowed scheme: {scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("missing hostname")

    # Strip IPv6 brackets if urlparse left them in (it usually doesn't, but
    # belt-and-suspenders). hostname from urlparse is already lowercased.
    host = hostname.strip("[]")

    # 1) Literal IP fast-path.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None:
        if _ip_is_unsafe(ip):
            raise UnsafeUrlError(f"ip address is internal/non-routable: {host}")
        return True

    # 2) Hostname — resolve and check ALL returned addresses.
    # DNS-rebinding caveat: httpx will resolve again on the actual GET, so this
    # check is best-effort. In production we additionally rely on outbound
    # network policy. But this catches the obvious naive bypass cases.
    try:
        _, _, addrs = socket.gethostbyname_ex(host)
    except (socket.gaierror, socket.herror, UnicodeError) as e:
        raise UnsafeUrlError(f"dns resolution failed for {host}: {e}") from e

    if not addrs:
        raise UnsafeUrlError(f"no addresses for hostname: {host}")

    for addr in addrs:
        try:
            resolved = ipaddress.ip_address(addr)
        except ValueError:
            # Should not happen — gethostbyname_ex returns dotted-quad strings.
            raise UnsafeUrlError(f"unparseable resolved address: {addr!r}")
        if _ip_is_unsafe(resolved):
            raise UnsafeUrlError(
                f"hostname {host} resolves to internal address {addr}"
            )

    return True


def verify_job_open(url: str, *, timeout: float = 6.0) -> LivenessStatus:
    """Single-shot liveness check.

    Returns:
        "closed"  — strong signal the posting is gone (404/410 or known phrase).
        "open"    — fetched 2xx, no closure marker found.
        "unknown" — transient error, 5xx, anti-bot block, or non-2xx redirect.
                    Caller should treat this as "probably still open" and not
                    block the user.

    Raises:
        UnsafeUrlError: if the URL fails the SSRF guard. Callers should treat
            this as equivalent to "closed" (we can't verify, and we won't try).
    """
    if not url:
        return "unknown"

    # SSRF guard — raises UnsafeUrlError for non-http(s), private, loopback,
    # link-local, multicast, or reserved targets. The caller is expected to
    # catch this and short-circuit (e.g. return 410), not to surface as 500.
    _is_safe_external_url(url)

    try:
        resp = _CLIENT.get(url, timeout=timeout)
    except Exception as e:
        log.info("liveness fetch error for %s: %s", url, e)
        return "unknown"

    if resp.status_code in _DEAD_HTTP_STATUSES:
        return "closed"
    if resp.status_code != 200:
        # 5xx, 403 anti-bot, 3xx loops — preserve the job.
        return "unknown"

    body_lower = resp.text.lower()
    for phrase in _CLOSED_PHRASES:
        if phrase in body_lower:
            return "closed"

    return "open"
