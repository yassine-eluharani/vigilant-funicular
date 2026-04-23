"""Pipeline routes — run stages and manage background tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from applypilot.web.auth import get_current_user
from applypilot.web.core import _tasks, _start_task

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


@router.post("/api/pipeline/run")
async def pipeline_run(request: Request, user: dict = Depends(get_current_user)) -> JSONResponse:
    body = await request.json()
    stages = body.get("stages", ["score"])
    workers = int(body.get("workers", 1))
    stream = bool(body.get("stream", False))
    task_id = _start_task(_do_run_pipeline, stages, workers, stream, user["id"])
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
