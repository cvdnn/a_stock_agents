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
    # P3 单任务互斥 + 不抢占 P0/P1：创建前预检，冲突直接 409，不产生垃圾任务记录
    timeout_seconds = req.timeout_seconds or 300
    if req.task_type == "data_sync_batch":
        manager = get_task_manager()
        active = next((task for task in manager.list_tasks(limit=50)
                       if task.task_type == "data_sync_batch" and task.status.value in ("pending", "running")), None)
        if active:
            raise HTTPException(status_code=409, detail=f"已有全部日线更新任务：{active.task_id}")
        timeout_seconds = 18000  # 3 个子任务各有独立超时，父任务只负责汇总
    if req.task_type == "data_sync" and str((req.params or {}).get("tier") or "").upper() == "P3":
        from core.data.sync_daemon import p3_conflict_reason

        conflict = p3_conflict_reason()
        if conflict:
            raise HTTPException(status_code=409, detail=conflict)
        # P3 市场级范围按分批同步计，300s 默认上限必然误杀；仅 selected 小任务保留原值
        if str((req.params or {}).get("scope") or "").lower() in ("full_market", "sh", "sz", "bj", ""):
            timeout_seconds = max(timeout_seconds, 7200)
    mgr = get_task_manager()
    return mgr.submit_task(
        task_type=req.task_type,
        params=req.params,
        timeout_seconds=timeout_seconds,
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
