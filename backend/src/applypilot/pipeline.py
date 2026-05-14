"""ApplyPilot Pipeline Orchestrator.

The main platform runs a single user-scoped stage: score.
Discovery (discover → enrich → filter → index) is handled by the
separate applypilot-discovery worker that writes to the shared DB.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from applypilot.config import load_env, ensure_dirs
from applypilot.database import init_db
from applypilot.scoring.filter_and_score import run_two_phase_scoring

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

STAGE_ORDER = ("score",)

STAGE_META: dict[str, dict] = {
    "score": {"desc": "LLM scoring — compute fit 1–10 against your profile"},
}


# Cap the number of jobs that auto-generate docs per scoring run. Each job
# triggers two LLM calls (tailor + cover), so 5 jobs = up to 10 background
# tasks. Bounds LLM cost without starving the 8-worker thread pool.
MAX_AUTO_GENS_PER_RUN = 5


def _run_score(user_id: int | None = None) -> dict:
    """Stage: two-phase scoring — rule pre-filter + heuristic rank + top-N LLM.

    Cuts per-user LLM cost from O(jobs) to O(top_N=100) by reusing the
    per-job metadata indexed once by the discovery worker.

    Side effect: after scoring completes, enqueues background tailor +
    cover-letter tasks for any newly-scored job with ``fit_score >= 9`` that
    doesn't already have docs. Capped at ``MAX_AUTO_GENS_PER_RUN`` jobs.
    """
    if user_id is None:
        return {"status": "error: user_id required for two-phase scoring"}
    try:
        result = run_two_phase_scoring(user_id=user_id)
    except Exception as e:
        log.error("Scoring failed: %s", e)
        return {"status": f"error: {e}"}

    try:
        enqueued = _enqueue_auto_docs(user_id, MAX_AUTO_GENS_PER_RUN)
    except Exception:
        # Auto-gen is a best-effort post-step; never let it fail the score run.
        log.exception("auto-doc enqueue failed for user_id=%s", user_id)
        enqueued = 0

    return {"status": "ok", "auto_docs_enqueued": enqueued, **result}


def _enqueue_auto_docs(user_id: int, max_jobs: int) -> int:
    """Find recently-scored ≥9 jobs missing docs and enqueue tailor + cover.

    Idempotent: ``_start_task_unique`` keyed by ``(kind, user_id, job_url)``
    de-duplicates against any in-flight manual click for the same job.
    Returns the number of (kind, job) tasks enqueued (≤ ``max_jobs * 2``).
    """
    # Lazy imports keep `pipeline` independent of the FastAPI surface (avoids
    # an import cycle: pipeline → web.core → web.routers.* → pipeline).
    from applypilot.web.core import _start_task_unique
    from applypilot.scoring.tailor import tailor_job_by_url
    from applypilot.scoring.cover_letter import cover_letter_by_url
    from applypilot.database import get_connection

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT j.url AS url,
               uj.tailored_resume_text AS tailored,
               uj.cover_letter_text    AS cover
        FROM jobs j
        JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ?
        WHERE uj.fit_score >= 9
          AND (uj.tailored_resume_text IS NULL OR uj.cover_letter_text IS NULL)
          AND uj.dismissed_at IS NULL
          AND j.closed_at IS NULL
        ORDER BY uj.fit_score DESC, uj.scored_at DESC
        LIMIT ?
        """,
        (user_id, max_jobs),
    ).fetchall()

    enqueued = 0
    for row in rows:
        job_url = row["url"]
        if not row["tailored"]:
            _start_task_unique(
                ("tailor", user_id, job_url),
                tailor_job_by_url, job_url, user_id, "normal",
            )
            enqueued += 1
        if not row["cover"]:
            _start_task_unique(
                ("cover", user_id, job_url),
                cover_letter_by_url, job_url, user_id, "normal",
            )
            enqueued += 1

    if enqueued:
        log.info("Auto-docs enqueued: user_id=%s jobs=%d tasks=%d",
                 user_id, len(rows), enqueued)
    return enqueued


# BE-025: was `dict[str, callable]` — `callable` is the builtin function, not a
# type annotation. `Callable[..., dict]` correctly types each stage runner as
# a function returning a dict (matching `_run_score` above).
_STAGE_RUNNERS: dict[str, Callable[..., dict]] = {
    "score": _run_score,
}


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(
    stages: list[str] | None = None,
    dry_run: bool = False,
    stream: bool = False,
    workers: int = 1,
    user_id: int | None = None,
) -> dict:
    """Run pipeline stages.

    Args:
        stages: List of stage names, or None / ["all"] for the full pipeline.
                Only "score" is valid on the main platform.
        dry_run: If True, preview stages without executing.
        stream:  Ignored (kept for API compatibility).
        workers: Ignored (kept for API compatibility).
        user_id: Scope scoring to this user.

    Returns:
        Dict with keys: stages (list of result dicts), errors (dict), elapsed (float).
    """
    load_env()
    ensure_dirs()
    init_db()

    if stages is None or stages == ["all"]:
        stages = list(STAGE_ORDER)

    # Validate
    unknown = [s for s in stages if s not in STAGE_META]
    if unknown:
        return {
            "stages": [],
            "errors": {s: "unknown stage" for s in unknown},
            "elapsed": 0.0,
        }

    ordered = [s for s in STAGE_ORDER if s in stages]

    if dry_run:
        return {
            "stages": [{"stage": s, "status": "dry_run", "elapsed": 0.0} for s in ordered],
            "errors": {},
            "elapsed": 0.0,
        }

    results: list[dict] = []
    errors: dict[str, str] = {}
    pipeline_start = time.time()

    for name in ordered:
        t0 = time.time()
        runner = _STAGE_RUNNERS[name]
        log.info("=== Stage: %s ===", name)

        kwargs: dict = {}
        if name == "score":
            kwargs["user_id"] = user_id

        try:
            result = runner(**kwargs)
            elapsed = time.time() - t0
            status = result.get("status", "ok") if isinstance(result, dict) else "ok"
        except Exception as e:
            elapsed = time.time() - t0
            status = f"error: {e}"
            log.exception("Stage '%s' crashed", name)

        results.append({"stage": name, "status": status, "elapsed": elapsed})
        if status not in ("ok", "partial"):
            errors[name] = status

    return {"stages": results, "errors": errors, "elapsed": time.time() - pipeline_start}
