"""Stripe webhook tests (TST-010).

Covers the webhook contract end-to-end at the FastAPI route boundary:
  * happy path: ``checkout.session.completed`` upgrades the user to ``pro``.
  * idempotent replay: same event delivered twice — the second call short-circuits.
  * bad signature: garbage body without monkeypatching ``construct_event`` → 400.
  * handler exception: a handler raising must NOT mark the event processed
    (this is the SEC-003 invariant — the previous bug claimed the event before
    running the handler, so a transient DB hiccup would silently drop the
    upgrade).
  * subscription deletion: ``customer.subscription.deleted`` flips the user to
    ``free`` based on ``stripe_subscription_id``.

Stripe's signature verification is replaced with a monkeypatch on
``stripe.Webhook.construct_event`` so we don't need to compute HMACs against
a real secret. ``construct_event`` is a static method on the ``stripe``
package; the router refers to it as ``_stripe.Webhook.construct_event`` (it
imports stripe locally inside the handler), so we patch the canonical
location.
"""

from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# Env wiring + canned events
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stripe_env(monkeypatch):
    """Make ``_get_stripe_client`` happy. The webhook handler calls it for
    consistent 503 behavior when Stripe is unconfigured, so without these
    vars every test would 503 before the handler runs."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy")


def _checkout_completed_event(user_id: int, *, event_id: str = "evt_chk_1",
                              subscription_id: str = "sub_test_1",
                              customer_id: str = "cus_test_1") -> dict:
    """Build a minimal ``checkout.session.completed`` event payload."""
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "client_reference_id": str(user_id),
                "customer": customer_id,
                "subscription": subscription_id,
                "metadata": {"user_id": str(user_id)},
            }
        },
    }


def _subscription_deleted_event(subscription_id: str,
                                *, event_id: str = "evt_sub_del_1") -> dict:
    return {
        "id": event_id,
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": subscription_id,
                "status": "canceled",
            }
        },
    }


def _patch_construct_event(monkeypatch, event: dict) -> None:
    """Force ``stripe.Webhook.construct_event`` to return ``event``."""
    import stripe as _stripe

    monkeypatch.setattr(
        _stripe.Webhook,
        "construct_event",
        lambda payload, sig_header, secret, tolerance=300, api_key=None: event,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_webhook_valid_checkout_completed_upgrades_user(
    client, db_conn, make_user, monkeypatch
):
    """A valid ``checkout.session.completed`` event flips tier=pro and
    stores the customer/subscription IDs."""
    user = make_user("clerk_chk_1", "chk1@example.com", "Checkout User")

    event = _checkout_completed_event(
        user["id"], subscription_id="sub_chk_ok", customer_id="cus_chk_ok"
    )
    _patch_construct_event(monkeypatch, event)

    resp = client.post(
        "/api/stripe/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "test", "content-type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("received") is True
    assert body.get("duplicate") is not True

    row = db_conn.execute(
        "SELECT tier, stripe_customer_id, stripe_subscription_id FROM users WHERE id = ?",
        (user["id"],),
    ).fetchone()
    assert row["tier"] == "pro"
    assert row["stripe_customer_id"] == "cus_chk_ok"
    assert row["stripe_subscription_id"] == "sub_chk_ok"


def test_webhook_replay_is_idempotent(
    client, db_conn, make_user, monkeypatch
):
    """Re-delivering the same event_id must short-circuit with
    ``duplicate: True`` and not mutate state again."""
    user = make_user("clerk_chk_2", "chk2@example.com", "Replay User")

    event = _checkout_completed_event(
        user["id"], event_id="evt_replay", subscription_id="sub_replay",
        customer_id="cus_replay",
    )
    _patch_construct_event(monkeypatch, event)

    # First delivery
    r1 = client.post(
        "/api/stripe/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "test"},
    )
    assert r1.status_code == 200
    assert r1.json().get("duplicate") is not True

    # Capture state after first delivery
    after_first = db_conn.execute(
        "SELECT tier, stripe_subscription_id FROM users WHERE id = ?",
        (user["id"],),
    ).fetchone()
    assert after_first["tier"] == "pro"
    assert after_first["stripe_subscription_id"] == "sub_replay"

    # Tamper with state to prove the handler does NOT re-run on replay.
    db_conn.execute(
        "UPDATE users SET tier = 'free' WHERE id = ?", (user["id"],)
    )
    db_conn.commit()

    # Second delivery (same event_id) — must be a no-op
    r2 = client.post(
        "/api/stripe/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "test"},
    )
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True

    after_second = db_conn.execute(
        "SELECT tier FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    # The replay must NOT have re-run the upgrade — the user remains 'free'
    # because the handler was short-circuited.
    assert after_second["tier"] == "free"


def test_webhook_bad_signature_returns_400(client):
    """Without monkeypatching ``construct_event``, a garbage body and a
    bogus signature must surface as 400 — the real Stripe SDK will raise
    ``SignatureVerificationError`` which our handler maps to 400."""
    resp = client.post(
        "/api/stripe/webhook",
        content=b"this is not a real stripe payload",
        headers={"stripe-signature": "t=1,v1=garbage"},
    )
    assert resp.status_code == 400, resp.text


def test_webhook_handler_exception_returns_500_and_event_not_processed(
    client, db_conn, make_user, monkeypatch
):
    """SEC-003 regression: when a handler raises, the response must NOT be 200
    AND we must NOT have marked the event as processed (otherwise Stripe's
    retries silently no-op and the user's tier never flips)."""
    user = make_user("clerk_chk_err", "err@example.com", "Err User")

    event = _checkout_completed_event(
        user["id"], event_id="evt_handler_err",
        subscription_id="sub_err", customer_id="cus_err",
    )
    _patch_construct_event(monkeypatch, event)

    # Force the handler to blow up
    from applypilot.web.routers import stripe_router

    def _boom(_session):
        raise RuntimeError("simulated DB hiccup")

    monkeypatch.setattr(stripe_router, "_handle_checkout_completed", _boom)

    resp = client.post(
        "/api/stripe/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "test"},
    )
    # 5xx — we want Stripe to retry.
    assert 500 <= resp.status_code < 600, resp.text

    # And the event must NOT be in the processed table — otherwise the retry
    # would be silently dropped.
    row = db_conn.execute(
        "SELECT 1 FROM stripe_processed_events WHERE event_id = ?",
        ("evt_handler_err",),
    ).fetchone()
    assert row is None, (
        "SEC-003 regression: event marked processed despite handler failure"
    )


def test_subscription_deleted_downgrades_user(
    client, db_conn, make_user, monkeypatch
):
    """``customer.subscription.deleted`` must downgrade the matching user
    to ``free`` based on ``stripe_subscription_id``."""
    user = make_user("clerk_dn", "dn@example.com", "Downgrade User", tier="pro")
    # Persist the subscription mapping that the webhook keys off.
    db_conn.execute(
        "UPDATE users SET stripe_subscription_id = ? WHERE id = ?",
        ("sub_to_delete", user["id"]),
    )
    db_conn.commit()

    event = _subscription_deleted_event("sub_to_delete", event_id="evt_sub_del")
    _patch_construct_event(monkeypatch, event)

    resp = client.post(
        "/api/stripe/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "test"},
    )
    assert resp.status_code == 200, resp.text

    row = db_conn.execute(
        "SELECT tier FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    assert row["tier"] == "free"
