"""Pipeline routes — run stages and manage background tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from applypilot.web.auth import get_current_user
from applypilot.web.core import _tasks, _start_task, score_limiter
from applypilot.web.schemas import (
    MaybeScoreResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    TaskStatusResponse,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


def _do_run_pipeline(stages: list[str], workers: int,
                     stream: bool, user_id: int | None = None) -> dict:
    from applypilot.pipeline import run_pipeline
    return run_pipeline(
        stages=stages,
        workers=workers,
        stream=stream,
        user_id=user_id,
    )


@router.post("/api/pipeline/run", response_model=PipelineRunResponse)
def pipeline_run(
    payload: PipelineRunRequest,
    user: dict = Depends(get_current_user),
) -> PipelineRunResponse:
    score_limiter.check(user["id"])
    stages = payload.stages
    workers = int(payload.workers)
    stream = bool(payload.stream)

    # Guard: don't start a scoring task when there's nothing to score
    if stages == ["score"]:
        from applypilot.database import get_connection
        conn = get_connection()
        unscored = conn.execute(
            "SELECT COUNT(*) FROM jobs j WHERE j.full_description IS NOT NULL "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM user_jobs uj "
            "  WHERE uj.job_url = j.url AND uj.user_id = ? AND uj.fit_score IS NOT NULL"
            ")",
            (user["id"],),
        ).fetchone()[0]
        if not unscored:
            return PipelineRunResponse(task_id=None, skipped=True, reason="no unscored jobs")

    task_id = _start_task(_do_run_pipeline, stages, workers, stream, user["id"])
    return PipelineRunResponse(task_id=task_id)


@router.post("/api/pipeline/maybe-score", response_model=MaybeScoreResponse)
def maybe_score(user: dict = Depends(get_current_user)) -> MaybeScoreResponse:
    """Start a scoring task if this user has unscored jobs. Idempotent.

    Safe to call on every page load — returns immediately if scoring is already
    running or if there are no unscored jobs.
    """
    from applypilot.web.core import trigger_score_for_user
    task_id = trigger_score_for_user(user["id"])
    if task_id:
        return MaybeScoreResponse(started=True, task_id=task_id)
    return MaybeScoreResponse(started=False, reason="no unscored jobs")


@router.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str, since: int = Query(0, ge=0)) -> TaskStatusResponse:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    all_lines = task.get("log_lines", [])
    return TaskStatusResponse(
        status=task["status"],
        result=task.get("result"),
        error=task.get("error"),
        log_lines=all_lines[since:],
        log_total=len(all_lines),
    )
