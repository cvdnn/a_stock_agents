# -*- coding: utf-8 -*-
"""
server.api.tasks - REST API endpoints for asynchronous long-running task jobs.
Provides task submission, status polling, cancellation, and result inspection.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from server.tasks.task_manager import (
    TaskCreateRequest,
    TaskResponse,
    get_task_manager,
)

router = APIRouter(prefix="/api/tasks", tags=["Async Tasks"])


@router.post("", response_model=TaskResponse)
async def create_task(req: TaskCreateRequest):
    """Enqueue a long-running quantitative research or debate task."""
    mgr = get_task_manager()
    return mgr.submit_task(
        task_type=req.task_type,
        params=req.params,
        timeout_seconds=req.timeout_seconds or 300,
    )


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status (pending, running, completed, failed)"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
):
    """List recent tasks and their statuses."""
    mgr = get_task_manager()
    return mgr.list_tasks(status=status, limit=limit)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """Query progress and results of an async task by task_id."""
    mgr = get_task_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return task


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """Cancel an active or running background task."""
    mgr = get_task_manager()
    success = mgr.cancel_task(task_id)
    if not success:
        task = mgr.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return {"status": "not_running", "message": f"Task '{task_id}' is already in state '{task.status}'"}
    return {"status": "cancelled", "task_id": task_id}
