"""Tailor-flow ordering integration tests (TST-012).

The tailor route runs four guards in a strict order:

    1. `tailor_limiter.check`            — sliding-window per-user rate limit
    2. `_ensure_job_open_or_410`         — liveness check (skip dead jobs)
    3. `check_and_increment_usage`       — free-tier monthly cap
    4. `_start_task(tailor_job_by_url)`  — dispatch background work

Why the order matters:

  * If usage were incremented BEFORE the liveness check, a free user could
    burn their entire monthly tailor quota on jobs that have already been
    closed — they'd hit a 410 with no artifact and a debited counter. The
    test `test_tailor_closed_job_returns_410_and_doesnt_burn_quota` is the
    contract that prevents that regression.

  * The free-tier cap sits between liveness and dispatch so a quota-exhausted
    user gets a clear 402 (with an upgrade hint) rather than a silent task
    that might 500 or hang. `test_tailor_free_user_at_limit_returns_402`
    pins that.

  * Pro users skip the cap. `test_tailor_pro_user_returns_task_id` is the
    happy-path sanity check.

The `client` fixture in conftest already stubs `verify_job_open` to
`"unknown"` so the tailor route doesn't try to fetch the network — only
the closed-job test needs to override that, which it does indirectly by
seeding `closed_at` (which short-circuits the liveness check before
`verify_job_open` is even called).
"""

from __future__ import annotations

import base64
import datetime as _dt


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _encode_url(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def _seed_job(
    db_conn, url: str, *, closed_at: str | None = None
) -> None:
    db_conn.execute(
        "INSERT INTO jobs (url, title, company, full_description, "
        "filtered_at, discovered_at, site, closed_at, closed_reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            url,
            "Senior Engineer",
            "Acme",
            "A great role.",
            _now_iso(),
            _now_iso(),
            "indeed",
            closed_at,
            "verified_closed_test" if closed_at else None,
        ),
    )
    db_conn.commit()


def _stub_tailor(monkeypatch) -> None:
    """Replace the heavy tailor entrypoint so background tasks no-op."""
    from applypilot.scoring import tailor as tailor_mod

    monkeypatch.setattr(
        tailor_mod, "tailor_job_by_url",
        lambda job_url, user_id, validation_mode="normal": {
            "stub": True, "url": job_url, "user_id": user_id,
        },
    )


def _set_tailors_used(db_conn, user_id: int, n: int) -> None:
    # Pin usage_reset_at to "now" too — otherwise `maybe_reset_usage` (called
    # at the top of `check_and_increment_usage`) sees a NULL reset stamp and
    # zeroes the counters before the cap check, defeating the seed.
    now = _now_iso()
    db_conn.execute(
        "UPDATE users SET tailors_used = ?, usage_reset_at = ? WHERE id = ?",
        (n, now, user_id),
    )
    db_conn.commit()


def _get_tailors_used(db_conn, user_id: int) -> int:
    row = db_conn.execute(
        "SELECT tailors_used FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return row["tailors_used"] if row else -1


# ---------------------------------------------------------------------------
# Free user with quota exhausted → 402
# ---------------------------------------------------------------------------


def test_tailor_free_user_at_limit_returns_402(
    client, db_conn, make_user, auth_headers, monkeypatch
):
    """Free user with tailors_used == FREE_TAILOR_LIMIT → 402 Payment Required.

    The route's `check_and_increment_usage` raises 402 before dispatch when
    the monthly cap is reached. The exact status code is what the frontend
    keys off to surface the upgrade prompt.
    """
    _stub_tailor(monkeypatch)

    user = make_user("clerk-free-cap", "free-cap@example.com", "Capped")
    # Free tier monthly cap is 3 (see auth.FREE_TAILOR_LIMIT). Saturate it.
    _set_tailors_used(db_conn, user["id"], 3)

    job_url = "https://jobs.example.com/role/tailor-cap"
    _seed_job(db_conn, job_url)

    enc = _encode_url(job_url)
    resp = client.post(
        f"/api/jobs/{enc}/tailor",
        headers=auth_headers("clerk-free-cap", "free-cap@example.com", "Capped"),
    )
    assert resp.status_code == 402, (
        f"expected 402 for free user at cap, got {resp.status_code}: {resp.text}"
    )
    # Counter must still be at the cap — we don't double-debit on the failed call.
    assert _get_tailors_used(db_conn, user["id"]) == 3, (
        "free user at cap had their counter incremented past the limit"
    )


# ---------------------------------------------------------------------------
# Pro user → 200 with task_id
# ---------------------------------------------------------------------------


def test_tailor_pro_user_returns_task_id(
    client, db_conn, make_user, auth_headers, monkeypatch
):
    """Pro user (no monthly cap) → 200 with a task_id for the background tailor.

    Asserts the happy path: rate-limit OK → liveness OK (stubbed) → cap skipped
    for pro → task dispatched. We don't wait for the task to finish; the
    contract is that the route returns the id immediately.
    """
    _stub_tailor(monkeypatch)

    make_user("clerk-pro", "pro@example.com", "Pro", tier="pro")

    job_url = "https://jobs.example.com/role/tailor-pro"
    _seed_job(db_conn, job_url)

    enc = _encode_url(job_url)
    resp = client.post(
        f"/api/jobs/{enc}/tailor",
        headers=auth_headers("clerk-pro", "pro@example.com", "Pro"),
    )
    assert resp.status_code == 200, (
        f"expected 200 for pro user, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("task_id"), (
        f"pro tailor response missing task_id: {body!r}"
    )


# ---------------------------------------------------------------------------
# Closed job → 410 AND quota untouched (the load-bearing ordering test)
# ---------------------------------------------------------------------------


def test_tailor_closed_job_returns_410_and_doesnt_burn_quota(
    client, db_conn, make_user, auth_headers, monkeypatch
):
    """Closed job → 410, AND the user's tailors_used is NOT incremented.

    This is the regression test for the ordering invariant:
    `_ensure_job_open_or_410` MUST run BEFORE `check_and_increment_usage`,
    so a free user trying to tailor a dead listing doesn't have their
    monthly counter debited for a 410-without-artifact.
    """
    _stub_tailor(monkeypatch)

    user = make_user("clerk-free-closed", "closed@example.com", "ClosedJob")
    starting_used = _get_tailors_used(db_conn, user["id"])

    closed_url = "https://jobs.example.com/role/already-closed"
    # Seed with closed_at set — the route's pre-check sees this and short-circuits
    # to 410 without ever calling verify_job_open.
    _seed_job(db_conn, closed_url, closed_at=_now_iso())

    enc = _encode_url(closed_url)
    resp = client.post(
        f"/api/jobs/{enc}/tailor",
        headers=auth_headers("clerk-free-closed", "closed@example.com", "ClosedJob"),
    )
    assert resp.status_code == 410, (
        f"closed job should return 410 Gone, got {resp.status_code}: {resp.text}"
    )

    after_used = _get_tailors_used(db_conn, user["id"])
    assert after_used == starting_used, (
        f"ORDERING BUG: free-tier tailor quota was charged for a closed job. "
        f"tailors_used: {starting_used} → {after_used}. The closed-job 410 "
        f"path must run before check_and_increment_usage."
    )
