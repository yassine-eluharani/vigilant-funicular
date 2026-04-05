"""Pipeline routes — run stages and manage background tasks."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from applypilot.web.core import _tasks, _start_task

router = APIRouter()


def _do_run_pipeline(stages: list[str], min_score: int, workers: int,
                     validation: str, stream: bool) -> dict:
    from applypilot.pipeline import run_pipeline
    return run_pipeline(
        stages=stages,
        min_score=min_score,
        workers=workers,
        validation_mode=validation,
        stream=stream,
    )


@router.post("/api/pipeline/run")
async def pipeline_run(request: Request) -> JSONResponse:
    body = await request.json()
    stages = body.get("stages", ["discover", "enrich", "score"])
    min_score = int(body.get("min_score", 7))
    workers = int(body.get("workers", 1))
    validation = body.get("validation", "normal")
    stream = bool(body.get("stream", False))
    task_id = _start_task(_do_run_pipeline, stages, min_score, workers, validation, stream)
    return JSONResponse({"task_id": task_id})


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str, since: int = Query(0, ge=0)) -> JSONResponse:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    all_lines = task.get("log_lines", [])
    return JSONResponse({
        "status": task["status"],
        "result": task.get("result"),
        "error": task.get("error"),
        "log_lines": all_lines[since:],
        "log_total": len(all_lines),
    })
