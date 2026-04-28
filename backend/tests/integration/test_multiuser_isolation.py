"""Multi-user isolation invariants (TST-011).

These tests verify that a join in any per-user query path that forgets the
`user_id` filter would leak data cross-tenant. Each test creates two users
A and B, seeds shared `jobs` rows, and gives each user their own
`user_jobs` row with distinct values — then makes API calls authenticated
as one user and asserts the other user's data is NOT visible.

The guard is the LEFT JOIN ON `uj.user_id = ?` pattern — these tests fail
loudly the moment that filter is dropped or replaced with a foreign key
mistake.
"""

from __future__ import annotations

import base64
import datetime as _dt


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _encode_url(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def _seed_job(db_conn, url: str, title: str = "Senior Engineer",
              company: str = "Acme") -> None:
    db_conn.execute(
        "INSERT INTO jobs (url, title, company, full_description, "
        "filtered_at, discovered_at, site) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (url, title, company, "A great role.", _now_iso(), _now_iso(), "indeed"),
    )
    db_conn.commit()


def _seed_user_job(db_conn, user_id: int, job_url: str, **fields) -> None:
    cols = ["user_id", "job_url", *fields.keys()]
    placeholders = ", ".join("?" for _ in cols)
    db_conn.execute(
        f"INSERT INTO user_jobs ({', '.join(cols)}) VALUES ({placeholders})",
        [user_id, job_url, *fields.values()],
    )
    db_conn.commit()


# ---------------------------------------------------------------------------
# Test 1: Each user only sees their own fit_score on /api/jobs
# ---------------------------------------------------------------------------


def test_user_cannot_see_other_users_jobs(
    client, db_conn, make_user, auth_headers
):
    """User A scores a job 9 with a tailored resume; user B has 3 with no resume.
    GET /api/jobs as A must return score=9; as B must return score=3.
    Crucially, neither user must see the other's score / resume metadata.
    """
    user_a = make_user("clerk-A", "a@example.com", "Alice")
    user_b = make_user("clerk-B", "b@example.com", "Bob")

    job_url = "https://jobs.example.com/role/123"
    _seed_job(db_conn, job_url)

    _seed_user_job(
        db_conn, user_a["id"], job_url,
        fit_score=9,
        tailored_resume_path="/tmp/A/resume.pdf",
        tailored_resume_text="Alice's bespoke resume — confidential.",
        tailored_at=_now_iso(),
    )
    _seed_user_job(
        db_conn, user_b["id"], job_url,
        fit_score=3,
        # No tailored resume for B.
    )

    # ── Alice's view ────────────────────────────────────────────────
    # status=pending requires tailored_resume_path IS NOT NULL for the
    # default endpoint behavior; user A meets that, user B does not.
    resp_a = client.get(
        "/api/jobs",
        params={"min_score": 1, "max_score": 10, "status": "pending"},
        headers=auth_headers("clerk-A", "a@example.com", "Alice"),
    )
    assert resp_a.status_code == 200, resp_a.text
    body_a = resp_a.json()
    urls_a = [j["url"] for j in body_a["jobs"]]
    assert job_url in urls_a, "Alice should see her own scored+tailored job"
    job_for_a = next(j for j in body_a["jobs"] if j["url"] == job_url)
    assert job_for_a["fit_score"] == 9, (
        f"Alice's view leaked Bob's score: got {job_for_a['fit_score']!r}"
    )

    # ── Bob's view ──────────────────────────────────────────────────
    # Bob has no tailored resume, so the default `pending` filter excludes
    # the job for him. Use `status=scored` to see all scored jobs.
    resp_b = client.get(
        "/api/jobs",
        params={"min_score": 1, "max_score": 10, "status": "scored"},
        headers=auth_headers("clerk-B", "b@example.com", "Bob"),
    )
    assert resp_b.status_code == 200, resp_b.text
    body_b = resp_b.json()
    job_for_b = next((j for j in body_b["jobs"] if j["url"] == job_url), None)
    assert job_for_b is not None, "Bob should see his own scored job"
    assert job_for_b["fit_score"] == 3, (
        f"Bob's view leaked Alice's score: got {job_for_b['fit_score']!r}"
    )
    assert job_for_b.get("tailored_resume_path") in (None, ""), (
        f"Bob's view leaked Alice's tailored_resume_path: "
        f"{job_for_b.get('tailored_resume_path')!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: One user's tailored resume is not readable by another user
# ---------------------------------------------------------------------------


def test_user_cannot_read_foreign_resume(
    client, db_conn, make_user, auth_headers
):
    """Alice has a tailored resume on job X; Bob has scored it but no resume.
    Bob's GET /api/resume/<encoded(X)> must 404 — Alice's PDF must not leak.
    """
    user_a = make_user("clerk-A", "a@example.com", "Alice")
    user_b = make_user("clerk-B", "b@example.com", "Bob")

    job_url = "https://jobs.example.com/role/secret"
    _seed_job(db_conn, job_url)

    _seed_user_job(
        db_conn, user_a["id"], job_url,
        fit_score=9,
        tailored_resume_path="/tmp/A/resume.pdf",
        tailored_resume_text="Alice's confidential tailored resume body.",
        tailored_at=_now_iso(),
    )
    _seed_user_job(
        db_conn, user_b["id"], job_url,
        fit_score=3,
    )

    enc = _encode_url(job_url)

    # Alice can read her own resume — sanity check.
    resp_a = client.get(
        f"/api/resume/{enc}",
        headers=auth_headers("clerk-A", "a@example.com", "Alice"),
    )
    assert resp_a.status_code == 200, (
        f"Alice should be able to read her own resume; got {resp_a.status_code} "
        f"{resp_a.text}"
    )

    # Bob must NOT — and the response body must not contain Alice's text.
    resp_b = client.get(
        f"/api/resume/{enc}",
        headers=auth_headers("clerk-B", "b@example.com", "Bob"),
    )
    assert resp_b.status_code == 404, (
        f"ISOLATION LEAK: Bob got {resp_b.status_code} reading Alice's resume — "
        f"endpoint failed to filter user_jobs by user_id. Body: {resp_b.text!r}"
    )
    assert "confidential" not in resp_b.text.lower(), (
        f"ISOLATION LEAK: Bob's response includes Alice's resume text: "
        f"{resp_b.text!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: Status mutation by one user must not leak into another's view
# ---------------------------------------------------------------------------


def test_user_cannot_dismiss_foreign_status(
    client, db_conn, make_user, auth_headers
):
    """Alice dismisses job X; Bob's view of X must show no apply_status.
    A bug that joins user_jobs without user_id would surface Alice's
    'dismissed' to Bob and hide the job from his pending list.
    """
    user_a = make_user("clerk-A", "a@example.com", "Alice")
    user_b = make_user("clerk-B", "b@example.com", "Bob")

    job_url = "https://jobs.example.com/role/dismiss"
    _seed_job(db_conn, job_url)

    # Both users have the job scored highly with a tailored resume (so it
    # qualifies for the default `pending` list).
    _seed_user_job(
        db_conn, user_a["id"], job_url,
        fit_score=9,
        tailored_resume_path="/tmp/A/resume.pdf",
        tailored_resume_text="Alice's resume.",
        tailored_at=_now_iso(),
    )
    _seed_user_job(
        db_conn, user_b["id"], job_url,
        fit_score=9,
        tailored_resume_path="/tmp/B/resume.pdf",
        tailored_resume_text="Bob's resume.",
        tailored_at=_now_iso(),
    )

    enc = _encode_url(job_url)

    # Alice dismisses
    resp_dismiss = client.post(
        f"/api/jobs/{enc}/dismiss",
        headers=auth_headers("clerk-A", "a@example.com", "Alice"),
    )
    assert resp_dismiss.status_code == 200, resp_dismiss.text

    # Bob's pending list should still contain the job.
    resp_b = client.get(
        "/api/jobs",
        params={"min_score": 1, "max_score": 10, "status": "pending"},
        headers=auth_headers("clerk-B", "b@example.com", "Bob"),
    )
    assert resp_b.status_code == 200, resp_b.text
    urls_b = [j["url"] for j in resp_b.json()["jobs"]]
    assert job_url in urls_b, (
        f"ISOLATION LEAK: Alice's dismissal hid the job from Bob's pending list. "
        f"Bob saw URLs: {urls_b!r}"
    )
    job_for_b = next(j for j in resp_b.json()["jobs"] if j["url"] == job_url)
    assert job_for_b.get("apply_status") in (None, "", "pending"), (
        f"ISOLATION LEAK: Bob's view shows Alice's apply_status="
        f"{job_for_b.get('apply_status')!r}"
    )

    # Alice's dismissed list should contain the job.
    resp_a = client.get(
        "/api/jobs",
        params={"min_score": 1, "max_score": 10, "status": "dismissed"},
        headers=auth_headers("clerk-A", "a@example.com", "Alice"),
    )
    assert resp_a.status_code == 200, resp_a.text
    urls_a = [j["url"] for j in resp_a.json()["jobs"]]
    assert job_url in urls_a, "Alice should see her dismissed job in dismissed list"


# ---------------------------------------------------------------------------
# Bonus: missing/invalid auth must 401, not 500
# ---------------------------------------------------------------------------


def test_jobs_endpoint_requires_auth(client):
    """Sanity check: no Authorization header → 401."""
    resp = client.get("/api/jobs")
    assert resp.status_code == 401, (
        f"Expected 401 without auth header, got {resp.status_code}: {resp.text}"
    )
