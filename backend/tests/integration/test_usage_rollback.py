"""Free-tier usage counter rollback on LLM failure (TST-009 / BE-011).

The tailor / cover routes pre-charge the user's monthly quota *before*
dispatching the LLM job. That ordering is required to fix the BE-011 race
(two concurrent tailors at `tailors_used = 2` both passing the cap check).
Pre-charging means we owe the user a refund when the LLM job blows up —
otherwise a free user with a flaky network spends their entire monthly
allowance on errors.

The refund path lives in `web/core.py::_run_task`'s exception handler. It
calls `auth.decrement_usage(user_id, kind)` with the kind inferred from the
dispatched function's `__name__`. This test seeds a free user at
`tailors_used = 0`, swaps the LLM entrypoint for one that raises, hits
`/api/jobs/{id}/tailor`, waits for the task to error out, and asserts the
counter went `0 → 1 → 0`.
"""

from __future__ import annotations

import base64
import datetime as _dt
import time
from typing import Any


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _encode_url(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def _seed_job(db_conn, url: str) -> None:
    db_conn.execute(
        "INSERT INTO jobs (url, title, company, full_description, "
        "filtered_at, discovered_at, site) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (url, "Senior Engineer", "Acme", "A great role.",
         _now_iso(), _now_iso(), "indeed"),
    )
    db_conn.commit()


def _get_used(db_conn, user_id: int, column: str) -> int:
    row = db_conn.execute(
        f"SELECT {column} FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return row[column] if row else -1


def _wait_for_task(task_id: str, timeout: float = 5.0) -> dict:
    """Block until the in-memory task entry settles in `done`/`error`.

    We read the internal `_tasks` registry directly rather than polling an
    HTTP route — keeps the test focused on the rollback contract instead of
    coupling to a specific status endpoint.
    """
    from applypilot.web.core import _tasks

    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        entry = _tasks.get(task_id)
        if entry and entry.get("status") in ("done", "error"):
            return entry
        if entry:
            last = entry
        time.sleep(0.05)
    raise AssertionError(
        f"task {task_id} did not finish within {timeout}s; last={last!r}"
    )


# ---------------------------------------------------------------------------
# BE-011 rollback — tailor task fails → counter rolls back to 0
# ---------------------------------------------------------------------------


def test_tailor_failure_rolls_back_counter(
    client, db_conn, make_user, auth_headers, monkeypatch
) -> None:
    """Free user at `tailors_used = 0`. Swap the LLM entrypoint to raise.
    POST tailor → counter is debited to 1, then refunded to 0 when the
    background task settles in `error` state."""
    user = make_user("clerk-rollback", "rollback@example.com", "Roll Back")
    assert _get_used(db_conn, user["id"], "tailors_used") == 0

    # Make the tailor function blow up. The route imports the symbol
    # at call time (`from applypilot.scoring.tailor import tailor_job_by_url`),
    # so we patch the module attribute. We must preserve the function's
    # `__name__` so the rollback dispatcher in `_run_task` recognizes it as
    # a tailor task.
    def _boom(job_url, user_id, validation_mode="normal"):
        raise RuntimeError("simulated LLM failure")

    _boom.__name__ = "tailor_job_by_url"  # ensure rollback kind inference works
    from applypilot.scoring import tailor as tailor_mod

    monkeypatch.setattr(tailor_mod, "tailor_job_by_url", _boom)

    job_url = "https://jobs.example.com/role/rollback"
    _seed_job(db_conn, job_url)

    enc = _encode_url(job_url)
    resp = client.post(
        f"/api/jobs/{enc}/tailor",
        headers=auth_headers("clerk-rollback", "rollback@example.com", "Roll Back"),
    )
    assert resp.status_code == 200, (
        f"tailor dispatch should return 200 with task_id even though the "
        f"task is destined to fail; got {resp.status_code}: {resp.text}"
    )
    task_id = resp.json()["task_id"]

    # Counter was debited synchronously by the route before dispatch.
    # Don't assert =1 here unconditionally — there's a race with the executor
    # thread completing very quickly. Instead just wait for completion.
    entry = _wait_for_task(task_id)
    assert entry["status"] == "error", (
        f"task should have settled as error; got {entry.get('status')!r}"
    )

    # The rollback path must refund the counter back to 0.
    after = _get_used(db_conn, user["id"], "tailors_used")
    assert after == 0, (
        f"BE-011 rollback failed: tailors_used went 0 → 1 → {after}, "
        f"expected 0. Free users would lose quota to LLM errors."
    )


# ---------------------------------------------------------------------------
# Cover-letter parallel of the same regression
# ---------------------------------------------------------------------------


def test_cover_failure_rolls_back_counter(
    client, db_conn, make_user, auth_headers, monkeypatch
) -> None:
    """Same contract as the tailor variant, but for cover letters."""
    user = make_user("clerk-cover-rb", "cover-rb@example.com", "Cover RB")
    assert _get_used(db_conn, user["id"], "covers_used") == 0

    def _boom(job_url, user_id, validation_mode="normal"):
        raise RuntimeError("simulated LLM failure (cover)")

    _boom.__name__ = "cover_letter_by_url"
    from applypilot.scoring import cover_letter as cover_mod

    monkeypatch.setattr(cover_mod, "cover_letter_by_url", _boom)

    job_url = "https://jobs.example.com/role/rollback-cover"
    _seed_job(db_conn, job_url)

    enc = _encode_url(job_url)
    resp = client.post(
        f"/api/jobs/{enc}/cover",
        headers=auth_headers("clerk-cover-rb", "cover-rb@example.com", "Cover RB"),
    )
    assert resp.status_code == 200, (
        f"cover dispatch should return 200; got {resp.status_code}: {resp.text}"
    )
    task_id = resp.json()["task_id"]

    entry = _wait_for_task(task_id)
    assert entry["status"] == "error"

    after = _get_used(db_conn, user["id"], "covers_used")
    assert after == 0, (
        f"BE-011 rollback failed for cover: covers_used went 0 → 1 → {after}"
    )


# ---------------------------------------------------------------------------
# Successful tailor must NOT roll back (otherwise the counter would always
# end at 0 and free users could tailor without limit).
# ---------------------------------------------------------------------------


def test_tailor_success_keeps_counter_incremented(
    client, db_conn, make_user, auth_headers, monkeypatch
) -> None:
    user = make_user("clerk-keep", "keep@example.com", "Keep It")

    def _ok(job_url, user_id, validation_mode="normal"):
        return {"ok": True, "url": job_url, "user_id": user_id}

    _ok.__name__ = "tailor_job_by_url"
    from applypilot.scoring import tailor as tailor_mod

    monkeypatch.setattr(tailor_mod, "tailor_job_by_url", _ok)

    job_url = "https://jobs.example.com/role/keep"
    _seed_job(db_conn, job_url)

    enc = _encode_url(job_url)
    resp = client.post(
        f"/api/jobs/{enc}/tailor",
        headers=auth_headers("clerk-keep", "keep@example.com", "Keep It"),
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    entry = _wait_for_task(task_id)
    assert entry["status"] == "done"
    assert _get_used(db_conn, user["id"], "tailors_used") == 1, (
        "successful tailor must leave the counter incremented"
    )


# ---------------------------------------------------------------------------
# Atomic UPDATE: concurrent calls at the cap can't both pass.
# ---------------------------------------------------------------------------


def test_concurrent_increment_respects_cap(db_conn, make_user) -> None:
    """Two concurrent `check_and_increment_usage` calls at `tailors_used = 2`
    (one slot left of the FREE_TAILOR_LIMIT=3 cap) must produce exactly one
    success and one 402 — never two successes. Validates BE-011's atomic
    UPDATE-with-WHERE pattern."""
    import threading

    from fastapi import HTTPException

    from applypilot.web.auth import FREE_TAILOR_LIMIT, check_and_increment_usage

    user = make_user("clerk-cc", "cc@example.com", "Concurrent")
    # Pin to one slot below the cap and stamp usage_reset_at so
    # `maybe_reset_usage` doesn't zero the counter on us.
    db_conn.execute(
        "UPDATE users SET tailors_used = ?, usage_reset_at = ? WHERE id = ?",
        (FREE_TAILOR_LIMIT - 1, _now_iso(), user["id"]),
    )
    db_conn.commit()

    results: list[str] = []
    barrier = threading.Barrier(2)

    def _hit() -> None:
        barrier.wait()
        try:
            check_and_increment_usage(user["id"], "tailor")
            results.append("ok")
        except HTTPException as e:
            results.append(f"http-{e.status_code}")
        except Exception as e:  # pragma: no cover
            results.append(f"err-{e!r}")

    threads = [threading.Thread(target=_hit) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Read final counter — must be exactly FREE_TAILOR_LIMIT (= cap), never
    # one above. SQLite's row-level locking serializes the two UPDATEs, so
    # one of them sees `tailors_used < limit` and bumps to `limit`; the
    # other sees `tailors_used == limit` and rowcount=0 → 402.
    final = _get_used(db_conn, user["id"], "tailors_used")
    assert final == FREE_TAILOR_LIMIT, (
        f"concurrent increments overshot the cap: tailors_used = {final}, "
        f"limit = {FREE_TAILOR_LIMIT}"
    )
    # Exactly one ok and one 402.
    assert sorted(results) == ["http-402", "ok"], (
        f"expected one success + one 402; got {results!r}"
    )
