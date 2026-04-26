"""ApplyPilot Pipeline Orchestrator.

The main platform runs a single user-scoped stage: score.
Discovery (discover → enrich → filter → index) is handled by the
separate applypilot-discovery worker that writes to the shared DB.
"""

from __future__ import annotations

import logging
import time

from applypilot.config import load_env, ensure_dirs
from applypilot.database import init_db, get_connection

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

STAGE_ORDER = ("score",)

STAGE_META: dict[str, dict] = {
    "score": {"desc": "LLM scoring — compute fit 1–10 against your profile"},
}


def _run_score(user_id: int | None = None) -> dict:
    """Stage: two-phase scoring — rule pre-filter + heuristic rank + top-N LLM.

    Cuts per-user LLM cost from O(jobs) to O(top_N=100) by reusing the
    per-job metadata indexed once by the discovery worker.
    """
    if user_id is None:
        return {"status": "error: user_id required for two-phase scoring"}
    try:
        from applypilot.scoring.filter_and_score import run_two_phase_scoring
        result = run_two_phase_scoring(user_id=user_id)
        return {"status": "ok", **result}
    except Exception as e:
        log.error("Scoring failed: %s", e)
        return {"status": f"error: {e}"}


_STAGE_RUNNERS: dict[str, callable] = {
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
