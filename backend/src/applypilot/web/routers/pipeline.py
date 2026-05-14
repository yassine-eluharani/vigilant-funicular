"""Tasks routes — read background-task progress.

Pipeline orchestration moved to the discovery worker
(applypilot-discovery/worker.py), so this router only exposes the
in-memory task registry that on-demand tailor/cover endpoints write to.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from applypilot.web.auth import get_current_user
from applypilot.web.core import _tasks
from applypilot.web.schemas import TaskStatusResponse

router = APIRouter(dependencies=[Depends(get_current_user)])


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
