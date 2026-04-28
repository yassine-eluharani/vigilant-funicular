"""Stripe Checkout and webhook routes.

Environment variables required:
  STRIPE_SECRET_KEY      — sk_live_... or sk_test_...
  STRIPE_WEBHOOK_SECRET  — whsec_... (from Stripe dashboard → Webhooks)
  STRIPE_PRICE_ID        — price_... (the Pro plan price ID)
  STRIPE_SUCCESS_URL     — full URL to redirect after payment (default: /jobs?upgraded=true)
  STRIPE_CANCEL_URL      — full URL to redirect on cancel (default: /pricing)

When STRIPE_SECRET_KEY is not set the checkout endpoint returns 503 so the
frontend can fall back to the dev-only direct upgrade.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from applypilot.web.auth import get_current_user
from applypilot.web.schemas import (
    CreateBillingPortalResponse,
    CreateCheckoutResponse,
    StripeWebhookResponse,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ── Stripe client (instance, not module global) ─────────────────────────────
# BE-009: We previously mutated `stripe.api_key` per request, which races
# across worker threads. We now hold a single `StripeClient` instance with
# a bounded HTTP timeout so a slow Stripe doesn't hang request threads
# indefinitely (TST-017).

_STRIPE_HTTP_TIMEOUT = 10.0  # seconds — per-call cap for any Stripe SDK call
_stripe_instance = None
_stripe_instance_lock = threading.Lock()
_stripe_instance_key: str | None = None


def _get_stripe_client():
    """Return a process-wide ``stripe.StripeClient``, lazily initialized.

    Raises HTTPException(503) when STRIPE_SECRET_KEY is not configured so
    the frontend can fall back to the dev-only direct upgrade path.
    """
    global _stripe_instance, _stripe_instance_key

    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    # Fast-path: already built and the secret hasn't been swapped under us.
    if _stripe_instance is not None and _stripe_instance_key == key:
        return _stripe_instance

    with _stripe_instance_lock:
        if _stripe_instance is not None and _stripe_instance_key == key:
            return _stripe_instance
        import stripe as _stripe
        from stripe._http_client import RequestsClient

        http_client = RequestsClient(timeout=_STRIPE_HTTP_TIMEOUT)
        _stripe_instance = _stripe.StripeClient(api_key=key, http_client=http_client)
        _stripe_instance_key = key
        return _stripe_instance


# ── StripeObject helpers ────────────────────────────────────────────────────
# Stripe's response objects override __getattr__ to look up dict keys, so
# `obj.get(...)` raises AttributeError. Use bracket access with try/except.

def _get(obj, key, default=None):
    try:
        v = obj[key]
        return default if v is None else v
    except (KeyError, AttributeError, TypeError):
        return default


def _stripe_call_with_retry(fn, *, op: str):
    """Run a Stripe SDK call once, retry exactly once after 1s on transient
    failure, raise HTTPException(503) on persistent failure (TST-017).

    ``fn`` is a zero-arg callable that performs the Stripe call. Per-call
    timeouts are enforced by the StripeClient's HTTP client (10s).
    """
    try:
        return fn()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Stripe %s failed (attempt 1/2): %s", op, e)
        time.sleep(1.0)
        try:
            return fn()
        except Exception as e2:
            log.exception("Stripe %s failed (attempt 2/2): %s", op, e2)
            raise HTTPException(
                status_code=503,
                detail="Billing portal temporarily unavailable",
            )


def _downgrade_user_by_subscription(stripe_subscription_id: str, reason: str) -> None:
    """Flip a user back to `free` based on their stored stripe_subscription_id."""
    if not stripe_subscription_id:
        return
    from applypilot.database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT id, clerk_id FROM users WHERE stripe_subscription_id = ?",
        (stripe_subscription_id,),
    ).fetchone()
    if not row:
        log.warning("Stripe webhook %s: no user found for subscription %s",
                    reason, stripe_subscription_id)
        return
    conn.execute("UPDATE users SET tier = 'free' WHERE id = ?", (row["id"],))
    conn.commit()
    if row["clerk_id"]:
        from applypilot.web.auth import invalidate_user_cache
        invalidate_user_cache(row["clerk_id"])
    log.info("Downgraded user %s to free (%s, sub=%s)", row["id"], reason, stripe_subscription_id)


def _claim_event(event_id: str, event_type: str) -> bool:
    """Idempotency guard: returns True if this is the first time we've seen this event.
    Returns False on duplicate (already processed)."""
    from applypilot.database import get_connection
    conn = get_connection()
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT OR IGNORE INTO stripe_processed_events (event_id, event_type, processed_at) "
        "VALUES (?, ?, ?)",
        (event_id, event_type, now),
    )
    conn.commit()
    return getattr(cur, "rowcount", 1) > 0


def _event_already_processed(event_id: str) -> bool:
    """Check (without claiming) whether we've already processed this event.
    Used to short-circuit replays so we don't re-run handlers."""
    if not event_id:
        return False
    from applypilot.database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM stripe_processed_events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    return row is not None


@router.post("/api/stripe/create-checkout", response_model=CreateCheckoutResponse)
def create_checkout(user: dict = Depends(get_current_user)) -> CreateCheckoutResponse:
    """Create a Stripe Checkout Session and return the redirect URL."""
    stripe_client = _get_stripe_client()

    price_id = os.environ.get("STRIPE_PRICE_ID", "")
    if not price_id:
        raise HTTPException(status_code=503, detail="STRIPE_PRICE_ID not configured")

    success_url = os.environ.get("STRIPE_SUCCESS_URL", "")
    cancel_url = os.environ.get("STRIPE_CANCEL_URL", "")
    if not success_url or not cancel_url:
        raise HTTPException(
            status_code=503,
            detail="STRIPE_SUCCESS_URL and STRIPE_CANCEL_URL must be set",
        )

    try:
        session = stripe_client.v1.checkout.sessions.create(
            params={
                "mode": "subscription",
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "client_reference_id": str(user["id"]),
                "customer_email": user.get("email"),
                "metadata": {"user_id": str(user["id"])},
            },
        )
        return CreateCheckoutResponse(checkout_url=session.url)
    except Exception:
        log.exception("Stripe checkout creation failed")
        raise HTTPException(status_code=500, detail="Stripe error — please try again")


@router.post("/api/stripe/billing-portal", response_model=CreateBillingPortalResponse)
def create_billing_portal(user: dict = Depends(get_current_user)) -> CreateBillingPortalResponse:
    """Create a Stripe Billing Portal session so the user can self-serve cancel,
    update their card, view invoices, etc. Stripe hosts the entire UI.

    Requires the user to have a stripe_customer_id (set when they first checked out).
    Cancellations made in the portal flow back through the webhook.
    """
    stripe_client = _get_stripe_client()

    from applypilot.database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT stripe_customer_id FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    customer_id = row["stripe_customer_id"] if row else None

    # Backfill: users upgraded before stripe_customer_id was being persisted
    # (or via fallback paths) won't have a customer ID. Look them up in Stripe
    # by email and store the result so future calls are fast.
    #
    # TST-017: every Stripe call here is wrapped in a 10s-timeout client and
    # a single retry-with-backoff so a Stripe outage can't pin a request
    # thread. On second failure we surface 503.
    if not customer_id and user.get("email"):
        try:
            customers = _stripe_call_with_retry(
                lambda: stripe_client.v1.customers.list(
                    params={"email": user["email"], "limit": 1},
                ),
                op="customers.list",
            )
            data = _get(customers, "data", []) or []
            if data:
                customer_id = _get(data[0], "id")
        except HTTPException:
            raise
        except Exception as e:
            log.warning("Stripe customer lookup by email failed: %s", e)

        # Also try to find their active subscription so cancellations can map back
        subscription_id = None
        if customer_id:
            try:
                subs = _stripe_call_with_retry(
                    lambda: stripe_client.v1.subscriptions.list(
                        params={"customer": customer_id, "status": "all", "limit": 1},
                    ),
                    op="subscriptions.list",
                )
                sdata = _get(subs, "data", []) or []
                if sdata:
                    subscription_id = _get(sdata[0], "id")
            except HTTPException:
                raise
            except Exception as e:
                log.warning("Stripe subscription lookup failed: %s", e)

            conn.execute(
                "UPDATE users SET stripe_customer_id = ?, stripe_subscription_id = ? "
                "WHERE id = ?",
                (customer_id, subscription_id, user["id"]),
            )
            conn.commit()
            log.info("Backfilled Stripe IDs for user %s (customer=%s sub=%s)",
                     user["id"], customer_id, subscription_id)

    if not customer_id:
        raise HTTPException(
            status_code=400,
            detail=("No Stripe customer found for your email. "
                    "If you just subscribed, wait a moment and try again."),
        )

    return_url = os.environ.get("STRIPE_PORTAL_RETURN_URL") \
        or os.environ.get("FRONTEND_ORIGIN") \
        or os.environ.get("STRIPE_CANCEL_URL", "").rsplit("/", 1)[0] \
        or "http://localhost:3000"
    # Send users back to the profile page's billing tab
    if "/profile" not in return_url:
        return_url = return_url.rstrip("/") + "/profile?tab=billing"

    try:
        session = stripe_client.v1.billing_portal.sessions.create(
            params={"customer": customer_id, "return_url": return_url},
        )
        return CreateBillingPortalResponse(portal_url=session.url)
    except Exception as e:
        msg = str(e)
        log.exception("Stripe billing portal creation failed")
        # Most common cause: portal not yet activated in Stripe Dashboard
        if "configuration" in msg.lower() or "no configuration" in msg.lower():
            raise HTTPException(
                status_code=503,
                detail=("Stripe billing portal is not yet configured. "
                        "Activate it in Stripe Dashboard → Settings → Billing → Customer portal."),
            )
        raise HTTPException(status_code=500, detail="Stripe error — please try again")


@router.post("/api/stripe/webhook", response_model=StripeWebhookResponse)
async def stripe_webhook(request: Request) -> StripeWebhookResponse:
    """Handle Stripe webhook events.

    Verifies the Stripe-Signature header and upgrades the user on
    checkout.session.completed.
    """
    # Touch the client so misconfiguration (no STRIPE_SECRET_KEY) returns 503
    # consistently with the rest of the router. ``stripe.Webhook.construct_event``
    # is itself a static method that doesn't need the client.
    _get_stripe_client()
    import stripe as _stripe

    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="STRIPE_WEBHOOK_SECRET not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = _stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        detail = "Invalid signature" if "SignatureVerification" in type(e).__name__ else str(e)
        raise HTTPException(status_code=400, detail=detail)

    event_type = event["type"]
    event_id = _get(event, "id", "")

    # Idempotency short-circuit: if we've already successfully processed this
    # event, return 200 without re-running the handler. We check here (without
    # claiming) so that a handler failure on a previous delivery does NOT block
    # Stripe's retry — we'll reach the handler below and try again.
    if await asyncio.to_thread(_event_already_processed, event_id):
        log.info("Stripe webhook duplicate event ignored: %s (%s)", event_id, event_type)
        return StripeWebhookResponse(received=True, duplicate=True)

    # Run the handler FIRST. Our handlers are idempotent (UPDATEs keyed on
    # subscription_id/customer_id/user_id), so the rare race where Stripe
    # redelivers before we claim the event is safe — the second pass will
    # produce the same DB state and then `_claim_event` will return False.
    try:
        if event_type == "checkout.session.completed":
            await asyncio.to_thread(_handle_checkout_completed, event["data"]["object"])
        elif event_type == "customer.subscription.deleted":
            await asyncio.to_thread(_handle_subscription_deleted, event["data"]["object"])
        elif event_type == "customer.subscription.updated":
            await asyncio.to_thread(_handle_subscription_updated, event["data"]["object"])
        elif event_type == "invoice.payment_failed":
            await asyncio.to_thread(_handle_invoice_payment_failed, event["data"]["object"])
    except Exception:
        # Do NOT claim the event. Returning 5xx tells Stripe to retry with
        # exponential backoff so the user's tier eventually flips even if we
        # had a transient DB hiccup. Log with full context for monitoring.
        log.exception(
            "Stripe webhook handler failed for event_type=%s event_id=%s",
            event_type, event_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Webhook handler failed — please retry",
        )

    # Handler succeeded — now claim the event so future redeliveries are
    # short-circuited above. If the claim itself fails (network/DB), we still
    # return 200: the handler already mutated state, and a redelivery would
    # just be a no-op against our idempotent UPDATEs.
    if event_id:
        try:
            claimed = await asyncio.to_thread(_claim_event, event_id, event_type)
            if not claimed:
                log.info(
                    "Stripe webhook event %s (%s) was already claimed during "
                    "concurrent processing", event_id, event_type,
                )
        except Exception:
            log.exception(
                "Failed to record processed Stripe event %s (%s); handler already ran",
                event_id, event_type,
            )

    return StripeWebhookResponse(received=True)


# ── Event handlers ──────────────────────────────────────────────────────────

def _handle_checkout_completed(session) -> None:
    metadata = _get(session, "metadata", {}) or {}
    user_id = _get(metadata, "user_id") or _get(session, "client_reference_id")
    if not user_id:
        log.error("checkout.session.completed missing user_id and client_reference_id")
        return

    customer_id = _get(session, "customer")
    subscription_id = _get(session, "subscription")

    from applypilot.database import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE users SET tier = 'pro', stripe_customer_id = ?, stripe_subscription_id = ? "
        "WHERE id = ?",
        (customer_id, subscription_id, int(user_id)),
    )
    conn.commit()
    clerk_row = conn.execute(
        "SELECT clerk_id FROM users WHERE id = ?", (int(user_id),)
    ).fetchone()
    if clerk_row and clerk_row["clerk_id"]:
        from applypilot.web.auth import invalidate_user_cache
        invalidate_user_cache(clerk_row["clerk_id"])
    log.info("Upgraded user %s to pro (customer=%s sub=%s)",
             user_id, customer_id, subscription_id)


def _handle_subscription_deleted(subscription) -> None:
    """Subscription fully ended (after dunning, immediate cancel, or end of period)."""
    sub_id = _get(subscription, "id", "")
    _downgrade_user_by_subscription(sub_id, reason="subscription.deleted")


def _handle_subscription_updated(subscription) -> None:
    """A subscription changed state — only downgrade on terminal/non-paying states."""
    sub_id = _get(subscription, "id", "")
    status = _get(subscription, "status", "")
    # Stripe statuses: incomplete, incomplete_expired, trialing, active,
    # past_due, canceled, unpaid, paused
    terminal_or_unpaid = {"canceled", "unpaid", "incomplete_expired"}
    if status in terminal_or_unpaid:
        _downgrade_user_by_subscription(sub_id, reason=f"subscription.updated[{status}]")
    elif status == "past_due":
        # Stripe is retrying. Keep Pro for now; we'll downgrade if it eventually
        # becomes `unpaid` or `canceled`. Just log so it shows up in monitoring.
        log.warning("Subscription %s is past_due (user remains Pro pending retry)", sub_id)


def _handle_invoice_payment_failed(invoice) -> None:
    """A recurring charge failed. Stripe will retry per dunning settings; we just log
    until the subscription transitions to `unpaid`/`canceled` and we get the update."""
    sub_id = _get(invoice, "subscription", "")
    customer_id = _get(invoice, "customer", "")
    amount_due = _get(invoice, "amount_due", 0)
    log.warning("invoice.payment_failed sub=%s customer=%s amount_due=%s",
                sub_id, customer_id, amount_due)
