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

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from applypilot.web.auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter()


def _stripe_client():
    import stripe as _stripe
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    _stripe.api_key = key
    return _stripe


@router.post("/api/stripe/create-checkout")
def create_checkout(user: dict = Depends(get_current_user)) -> JSONResponse:
    """Create a Stripe Checkout Session and return the redirect URL."""
    stripe = _stripe_client()

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
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(user["id"]),
            customer_email=user.get("email"),
            metadata={"user_id": str(user["id"])},
        )
        return JSONResponse({"checkout_url": session.url})
    except Exception as e:
        log.error("Stripe checkout creation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    """Handle Stripe webhook events.

    Verifies the Stripe-Signature header and upgrades the user on
    checkout.session.completed.
    """
    stripe = _stripe_client()

    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="STRIPE_WEBHOOK_SECRET not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        detail = "Invalid signature" if "SignatureVerification" in type(e).__name__ else str(e)
        raise HTTPException(status_code=400, detail=detail)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id") or session.get("client_reference_id")
        if user_id:
            try:
                from applypilot.database import get_connection
                conn = get_connection()
                conn.execute("UPDATE users SET tier = 'pro' WHERE id = ?", (int(user_id),))
                conn.commit()
                log.info("Upgraded user %s to pro via Stripe webhook", user_id)
            except Exception as e:
                log.error("Failed to upgrade user %s: %s", user_id, e)

    return JSONResponse({"received": True})
