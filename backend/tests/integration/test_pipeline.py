"""Pipeline-route integration tests (TST-013).

Covers the empty-queue short-circuit in `pipeline_run`:
when the user has no unscored jobs, the route must not start a background
task — it must return `{"task_id": null, "skipped": true}` so the frontend
can surface that nothing needed scoring without spinning a worker.

Conversely, when at least one unscored job exists for the user, the route
must hand back a task_id (we patch the actual `run_pipeline` call so the
test never executes a real LLM scoring run — the assertion is only that
the route reached the dispatch path).
"""

from __future__ import annotations

import datetime as _dt


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _seed_job(db_conn, url: str, *, with_description: bool = True) -> None:
    db_conn.execute(
        "INSERT INTO jobs (url, title, company, full_description, "
        "filtered_at, discovered_at, site) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            url,
            "Senior Engineer",
            "Acme",
            "A great role." if with_description else None,
            _now_iso(),
            _now_iso(),
            "indeed",
        ),
    )
    db_conn.commit()


# ---------------------------------------------------------------------------
# Empty-queue short-circuit
# ---------------------------------------------------------------------------


def test_pipeline_run_empty_queue_skipped(
    client, db_conn, make_user, auth_headers
):
    """No unscored jobs → POST /api/pipeline/run must NOT start a task.

    Response shape: `{"task_id": null, "skipped": true, "reason": "..."}`.
    Guards against the regression where the route enqueues a no-op scoring
    task for users with empty queues, churning the bounded executor and
    burning the score rate-limiter for no reason.
    """
    make_user("clerk-empty", "empty@example.com", "Empty")

    resp = client.post(
        "/api/pipeline/run",
        json={"stages": ["score"]},
        headers=auth_headers("clerk-empty", "empty@example.com", "Empty"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("task_id") is None, (
        f"empty-queue path leaked a task_id: {body!r}"
    )
    assert body.get("skipped") is True, (
        f"empty-queue path did not set skipped=true: {body!r}"
    )


# ---------------------------------------------------------------------------
# Unscored present → returns a task_id
# ---------------------------------------------------------------------------


def test_pipeline_run_with_unscored_returns_task(
    client, db_conn, make_user, auth_headers, monkeypatch
):
    """A job with a full description that's NOT scored for this user → task_id.

    We monkeypatch `run_pipeline` so we never actually invoke the LLM scoring
    pipeline — the assertion is purely about the dispatch path: the route
    saw unscored work and handed back a task_id.
    """
    make_user("clerk-with", "with@example.com", "WithJobs")

    # Seed a job; the user has no user_jobs row yet → unscored.
    _seed_job(db_conn, "https://jobs.example.com/role/score-me")

    # Stub the scoring entrypoint so the background thread doesn't run an
    # actual pipeline against the test DB.
    from applypilot import pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod, "run_pipeline",
        lambda **kwargs: {"scored": 0, "stub": True},
    )

    resp = client.post(
        "/api/pipeline/run",
        json={"stages": ["score"]},
        headers=auth_headers("clerk-with", "with@example.com", "WithJobs"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("task_id"), (
        f"expected a task_id when unscored work exists, got {body!r}"
    )
    assert body.get("skipped") is not True, (
        f"unexpected skipped=true when unscored work exists: {body!r}"
    )
