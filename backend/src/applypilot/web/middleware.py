"""Request-ID middleware and logging filter for ApplyPilot.

Generates (or accepts) an ``X-Request-ID`` per HTTP request, exposes it via a
:class:`contextvars.ContextVar`, echoes it on the response, and injects it into
every log record so logs emitted during a request are easy to correlate.
"""

from __future__ import annotations

import contextvars
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ContextVar holding the current request's ID. Default ``"-"`` so logs emitted
# outside any request still format cleanly.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def get_request_id() -> str:
    """Return the current request ID (``"-"`` if no request is active)."""
    return request_id_var.get("-")


class RequestIdFilter(logging.Filter):
    """Logging filter that attaches ``request_id`` to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.request_id = request_id_var.get("-")
        return True


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a request ID to ``request_id_var`` for the lifetime of the request."""

    header_name = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(self.header_name) or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[self.header_name] = rid
        return response


def install_request_id_logging() -> None:
    """Attach :class:`RequestIdFilter` to the root logger handlers (idempotent)."""
    flt = RequestIdFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        # Avoid stacking duplicate filters on hot reload.
        if not any(isinstance(f, RequestIdFilter) for f in handler.filters):
            handler.addFilter(flt)
