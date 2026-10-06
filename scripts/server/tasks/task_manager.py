# -*- coding: utf-8 -*-
"""
server.tasks.task_manager - Long-running asynchronous Task Queue and Worker.
Handles long-running quantitative tasks (5A screening, 7-analyst debate, backtests)
with status tracking, progress updates, cancellation, and timeout circuit-breakers.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional
from pydantic import BaseModel, Field

from core.config import get_logger
from server.db import (
    get_task_record,
    list_task_records,
    save_task_record,
    update_task_record,
)

logger = get_logger("server.tasks.task_manager")


def resolve_p3_symbols(engine, scope: str, include_indices: bool = False) -> List[str]:
    """Resolve a market batch, optionally including the supported core indices."""
    if include_indices and scope != "full_market":
        raise ValueError("核心指数只能与全市场范围一起更新")
    symbols = list(dict.fromkeys(engine.list_market_symbols(scope)))
    if not symbols:
        return []
    if include_indices:
        symbols.extend(index for index in engine.DEFAULT_INDICES if index not in symbols)
    return symbols


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


# 实时进度落库节流（秒）与父任务轮询子任务进度的节奏（秒）
SYNC_PROGRESS_FLUSH_INTERVAL = 1.0
BATCH_CHILD_POLL_SECONDS = 1.0

SYNC_SCOPE_LABELS = {
    "full_market": "沪深全市场",
    "sh": "沪市",
    "sz": "深市",
    "indices": "核心指数",
    "selected": "指定标的",
}


def sync_stage_label(params: Dict[str, Any]) -> str:
    """把任务参数翻译成分项进度里的阶段名，供前端实时进度文案直接使用。"""
    tier = str(params.get("tier") or "").upper()
    scope = str(params.get("scope") or "").lower()
    if tier in ("P0", "P1", "P0-P2"):
        return {"P0": "持仓池日 K", "P1": "自选关注池日 K", "P0-P2": "持仓与自选关注池日 K"}[tier]
    if tier == "P2" or scope == "indices" or params.get("indices"):
        return "核心指数日 K"
    label = SYNC_SCOPE_LABELS.get(scope)
    if label:
        return f"{label}日 K"
    if params.get("all"):
        return "已登记标的日 K"
    return "标的日 K"


class SyncProgressReporter:
    """把 sync_batch 的逐标的回调聚合成可落库的实时进度（当前完成数 / 全部股票数）。

    回调在同步线程池内被高频触发，这里按时间节流写 task_records，避免 SQLite 写放大；
    运行中间态写进 result.progress_detail，任务结束时由 _execute_task_wrapper 用最终
    result 覆盖，因此不会污染最终契约。
    """

    def __init__(
        self,
        task_id: str,
        stage: str,
        total: int = 0,
        *,
        batches: int = 1,
        batch_size: int = 0,
        context: Optional[Dict[str, Any]] = None,
        progress_floor: float = 0.1,
        progress_span: float = 0.85,
        interval: float = SYNC_PROGRESS_FLUSH_INTERVAL,
    ) -> None:
        self.task_id = task_id
        self.stage = stage
        self.context = dict(context or {})
        self.progress_floor = progress_floor
        self.progress_span = progress_span
        self.interval = interval
        self._lock = threading.Lock()
        self._last_flush = 0.0
        self._started = time.time()
        self._base_processed = 0
        self._base_success = 0
        self._base_failed = 0
        self.total = int(total or 0)
        self.batches = max(1, int(batches or 1))
        self.batch_size = int(batch_size or 0)
        self.batch = 1
        self.phase = "preparing"
        self.processed = 0
        self.success_count = 0
        self.failed_count = 0
        self.current_symbol = ""

    def on_progress(self, snapshot: Dict[str, Any]) -> None:
        """sync_batch 每完成一个标的调用一次；内部按 interval 节流落库。"""
        with self._lock:
            self.processed = self._base_processed + int(snapshot.get("processed") or 0)
            self.success_count = self._base_success + int(snapshot.get("success_count") or 0)
            self.failed_count = self._base_failed + int(snapshot.get("failed_count") or 0)
            self.phase = "syncing"
            symbol = snapshot.get("symbol")
            if symbol:
                self.current_symbol = str(symbol)
            due = time.time() - self._last_flush >= self.interval
        if due:
            self.write()

    def start_batch(
        self, batch: int, *, processed: int, success: int, failed: int,
        batches: Optional[int] = None,
    ) -> None:
        with self._lock:
            self.batch = int(batch)
            if batches is not None:
                self.batches = max(1, int(batches))
            self._base_processed = int(processed)
            self._base_success = int(success)
            self._base_failed = int(failed)
            self.phase = "syncing"

    def configure(
        self, *, phase: Optional[str] = None, total: Optional[int] = None,
        batches: Optional[int] = None, batch_size: Optional[int] = None,
    ) -> None:
        with self._lock:
            if phase is not None:
                self.phase = phase
            if total is not None:
                self.total = int(total)
            if batches is not None:
                self.batches = max(1, int(batches))
            if batch_size is not None:
                self.batch_size = int(batch_size)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def finalize(self, *, success: int, failed: int, total: Optional[int] = None) -> Dict[str, Any]:
        """以真实同步结果收口进度快照（回调可能因节流而落后于最终计数）。"""
        with self._lock:
            self.success_count = int(success or 0)
            self.failed_count = int(failed or 0)
            self.processed = self.success_count + self.failed_count
            if total is not None:
                self.total = int(total)
            self.phase = "finished"
            return self._snapshot_locked()

    def write(self, *, force: bool = False) -> None:
        with self._lock:
            now = time.time()
            if not force and now - self._last_flush < self.interval:
                return
            self._last_flush = now
            snap = self._snapshot_locked()
        update_task_record(
            task_id=self.task_id,
            progress=self._progress(snap),
            status_message=self._message(snap),
            result=self._payload(snap),
        )

    # --- internals ---------------------------------------------------------
    def _snapshot_locked(self) -> Dict[str, Any]:
        total = self.total
        processed = self.processed
        ratio = processed / total if total else 0.0
        elapsed = max(0.0, time.time() - self._started)
        remaining = max(0, total - processed)
        return {
            "stage": self.stage,
            "phase": self.phase,
            "processed": processed,
            "total": total,
            "remaining": remaining,
            "ratio": round(min(1.0, ratio), 4),
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "batch": self.batch,
            "batches": self.batches,
            "batch_size": self.batch_size,
            "current_symbol": self.current_symbol,
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": round(elapsed / ratio * (1 - ratio), 1) if 0 < ratio < 1 else None,
        }

    def _progress(self, snap: Dict[str, Any]) -> float:
        return round(min(0.95, self.progress_floor + self.progress_span * snap["ratio"]), 4)

    def _message(self, snap: Dict[str, Any]) -> str:
        stage, counts = snap["stage"], f"成功 {snap['success_count']}，失败 {snap['failed_count']}"
        if snap["phase"] == "preparing":
            return f"{stage}：正在解析标的清单"
        if snap["phase"] == "finished":
            return f"{stage}：已完成 {snap['processed']}/{snap['total']} 只（{counts}）"
        if not snap["total"]:
            return f"{stage}：同步中（标的清单暂不可知）"
        batch_note = f" · 批次 {snap['batch']}/{snap['batches']}" if snap["batches"] > 1 else ""
        return f"{stage}：已完成 {snap['processed']}/{snap['total']} 只（{counts}）{batch_note}"

    def _payload(self, snap: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **self.context,
            "status": "running",
            "total_requested": snap["total"],
            "success_count": snap["success_count"],
            "failed_count": snap["failed_count"],
            "progress_detail": snap,
        }


class TaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: TaskStatus
    progress: float = 0.0
    status_message: str = ""
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    elapsed_ms: int = 0
    params: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskCreateRequest(BaseModel):
    task_type: str = Field(..., description="Type of task: screen_5a, debate, backtest, quant_pipeline, skill")
    params: Dict[str, Any] = Field(default_factory=dict, description="Task execution arguments")
    timeout_seconds: Optional[int] = Field(default=300, ge=5, le=1800, description="Task timeout fuse in seconds")


class TaskManager:
    """Central Task Manager orchestrating async workers and task state machines."""

    _instance: Optional[TaskManager] = None

    def __init__(self) -> None:
        self._running_tasks: Dict[str, asyncio.Task[Any]] = {}

    @classmethod
    def get_instance(cls) -> TaskManager:
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    def submit_task(
        self,
        task_type: str,
        params: Dict[str, Any],
        timeout_seconds: int = 300,
    ) -> TaskResponse:
        """Create and enqueue an asynchronous long-running task."""
        task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        rec = save_task_record(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING.value,
            params=params,
        )

        # Spawn background coroutine
        async_task = asyncio.create_task(
            self._execute_task_wrapper(
                task_id=task_id,
                task_type=task_type,
                params=params,
                timeout_seconds=timeout_seconds,
            )
        )
        self._running_tasks[task_id] = async_task

        return TaskResponse(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            progress=0.0,
            status_message="Task enqueued",
            created_at=rec["created_at"],
            params=params,
        )

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        """Query task state and result from SQLite."""
        data = get_task_record(task_id)
        if not data:
            return None
        return TaskResponse(
            task_id=data["task_id"],
            task_type=data["task_type"],
            status=TaskStatus(data["status"]),
            progress=data["progress"],
            status_message=data["status_message"],
            created_at=data["created_at"],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            elapsed_ms=data["elapsed_ms"],
            params=data["params"],
            result=data["result"],
            error=data["error"],
        )

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[TaskResponse]:
        """List tasks ordered chronologically."""
        rows = list_task_records(status=status, limit=limit)
        res = []
        for r in rows:
            res.append(
                TaskResponse(
                    task_id=r["task_id"],
                    task_type=r["task_type"],
                    status=TaskStatus(r["status"]),
                    progress=r["progress"],
                    status_message=r["status_message"],
                    created_at=r["created_at"],
                    started_at=r["started_at"],
                    completed_at=r["completed_at"],
                    elapsed_ms=r["elapsed_ms"],
                    params=r["params"],
                    result=r["result"],
                    error=r["error"],
                )
            )
        return res

    def cancel_task(self, task_id: str) -> bool:
        """Cancel an in-flight background task."""
        async_task = self._running_tasks.get(task_id)
        if async_task and not async_task.done():
            async_task.cancel()
            now_iso = datetime.now(timezone.utc).isoformat()
            update_task_record(
                task_id=task_id,
                status=TaskStatus.CANCELLED.value,
                status_message="Task cancelled by user",
                completed_at=now_iso,
            )
            return True
        return False

    async def _execute_task_wrapper(
        self,
        task_id: str,
        task_type: str,
        params: Dict[str, Any],
        timeout_seconds: int,
    ) -> None:
        """Worker lifecycle runner with progress reporting and circuit breaker."""
        start_t = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        update_task_record(
            task_id=task_id,
            status=TaskStatus.RUNNING.value,
            progress=0.1,
            status_message="Task started",
            started_at=now_iso,
        )

        try:
            # Delegate to specialized runner with timeout fuse
            coro = self._run_specialized_task(task_id, task_type, params)
            result = await asyncio.wait_for(coro, timeout=timeout_seconds)

            elapsed = int((time.time() - start_t) * 1000)
            comp_iso = datetime.now(timezone.utc).isoformat()
            result_status = result.get("status") if isinstance(result, dict) else None
            failed_result = result_status in {"error", "unavailable", "timeout"}
            update_task_record(
                task_id=task_id,
                status=TaskStatus.FAILED.value if failed_result else TaskStatus.COMPLETED.value,
                progress=1.0,
                status_message="Task capability unavailable or failed" if failed_result else "Task completed successfully",
                result=result,
                error=result.get("error") if failed_result else None,
                completed_at=comp_iso,
                elapsed_ms=elapsed,
            )
        except asyncio.CancelledError:
            elapsed = int((time.time() - start_t) * 1000)
            comp_iso = datetime.now(timezone.utc).isoformat()
            update_task_record(
                task_id=task_id,
                status=TaskStatus.CANCELLED.value,
                status_message="Task execution cancelled",
                completed_at=comp_iso,
                elapsed_ms=elapsed,
            )
        except asyncio.TimeoutError:
            elapsed = int((time.time() - start_t) * 1000)
            comp_iso = datetime.now(timezone.utc).isoformat()
            update_task_record(
                task_id=task_id,
                status=TaskStatus.TIMED_OUT.value,
                status_message=f"Task timed out after {timeout_seconds} seconds",
                error=f"Timeout fuse triggered ({timeout_seconds}s)",
                completed_at=comp_iso,
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            logger.error(f"Task {task_id} failed: {exc}", exc_info=True)
            elapsed = int((time.time() - start_t) * 1000)
            comp_iso = datetime.now(timezone.utc).isoformat()
            update_task_record(
                task_id=task_id,
                status=TaskStatus.FAILED.value,
                status_message="Task failed with exception",
                error=str(exc),
                completed_at=comp_iso,
                elapsed_ms=elapsed,
            )
        finally:
            self._running_tasks.pop(task_id, None)

    async def _run_specialized_task(
        self,
        task_id: str,
        task_type: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute task logic depending on task_type."""
        loop = asyncio.get_running_loop()

        if task_type == "data_sync_batch":
            return await self._run_data_sync_batch(task_id, params)

        if task_type in ("screen_5a", "screener"):
            update_task_record(task_id=task_id, progress=0.3, status_message="Scanning market sectors")
            from server.agent.tools import _sync_astock_screen_5a
            limit = params.get("limit", 10)
            mode = params.get("dynamic_mode")
            res = await loop.run_in_executor(None, lambda: _sync_astock_screen_5a(limit=limit, dynamic_mode=mode))
            update_task_record(task_id=task_id, progress=0.8, status_message="Scoring multi-factor candidates")
            return res

        elif task_type in ("debate", "agent_debate"):
            code = params.get("code", "600519")
            rounds = params.get("rounds", 2)
            update_task_record(task_id=task_id, progress=0.3, status_message="Convening 7 analysts")
            from server.agent.tools import _sync_astock_agent_debate
            res = await loop.run_in_executor(None, lambda: _sync_astock_agent_debate(code=code, rounds=rounds))
            update_task_record(task_id=task_id, progress=0.8, status_message="Formulating debate consensus")
            return res

        elif task_type in ("quant_pipeline", "quant"):
            action = params.get("action", "pipeline")
            code = params.get("code")
            update_task_record(task_id=task_id, progress=0.4, status_message="Extracting cross-sectional factors")
            from server.agent.tools import _sync_astock_quant_engine
            res = await loop.run_in_executor(None, lambda: _sync_astock_quant_engine(action=action, code=code))
            return res

        elif task_type in ("data_sync", "sync"):
            update_task_record(task_id=task_id, progress=0.2, status_message="Initializing data sync engine")
            from core.data.sync_engine import DataSyncEngine
            engine = DataSyncEngine()
            raw_codes = params.get("codes") or ([params["code"]] if "code" in params else None)
            codes = []
            if raw_codes:
                if isinstance(raw_codes, list):
                    codes = raw_codes
                else:
                    codes = [c.strip() for c in str(raw_codes).split(",") if c.strip()]
            pool = params.get("pool")
            indices = params.get("indices", False)
            all_pool = params.get("all", False)
            mode = params.get("mode", "incremental")
            count = params.get("count", 250)
            start_date = params.get("start")
            end_date = params.get("end")

            tier = str(params.get("tier") or "").upper()
            scope = str(params.get("scope") or "").lower()

            # P0/P1/P2 定盘/池同步期间置核心活跃标记：P3 启动前据此让路（不抢占）
            if tier in ("P0", "P1", "P2", "P0-P2"):
                from core.data.sync_daemon import set_core_sync_active
                set_core_sync_active(True)
                try:
                    return await self._run_data_sync_core(
                        task_id, engine, loop, params, codes, pool, indices, all_pool,
                        mode, count, start_date, end_date,
                        int(params.get("workers") or params.get("concurrency") or 4),
                    )
                finally:
                    set_core_sync_active(False)

            if tier == "P3":
                return await self._run_p3_sync(task_id, engine, loop, params, scope, mode, codes)

            # 未标层级的历史任务保持原有行为，不进入仲裁
            return await self._run_data_sync_core(
                task_id, engine, loop, params, codes, pool, indices, all_pool,
                mode, count, start_date, end_date,
                int(params.get("workers") or params.get("concurrency") or 4),
            )

        elif task_type in ("backtest", "combo_backtest"):
            return {
                "status": "unavailable",
                "error": "CAPABILITY_NOT_IMPLEMENTED",
                "skill_id": "astock-trade-paper",
            }

        else:
            # Generic skill dispatch
            from core.governance.skill_registry import get_skill_registry
            registry = get_skill_registry()
            test_resp = await registry.execute_skill(
                skill_id=task_type,
                params=params,
                confirmed=params.get("confirmed", True),
            )
            return test_resp.model_dump()

    async def _run_data_sync_batch(self, task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run supported daily-K datasets as separate, sequential child tasks."""
        steps = (
            ("核心指数日 K", {"tier": "P2", "scope": "indices", "indices": True}, 1800),
            ("沪市日 K", {"tier": "P3", "scope": "sh"}, 7200),
            ("深市日 K", {"tier": "P3", "scope": "sz"}, 7200),
        )
        children: List[Dict[str, Any]] = [
            {"task_id": "", "label": step_label, "stage": step_label, "status": "pending",
             "phase": "waiting", "processed": 0, "total": 0, "success_count": 0, "failed_count": 0}
            for step_label, _step, _timeout in steps
        ]
        for index, (label, step, timeout) in enumerate(steps):
            child_params = {
                **step, "mode": "incremental", "trigger": params.get("trigger", "manual"),
                "parent_task_id": task_id,
            }
            child = self.submit_task("data_sync", child_params, timeout_seconds=timeout)
            children[index] = {
                "task_id": child.task_id, "label": label, "stage": label, "status": "running",
                "phase": "preparing", "processed": 0, "total": 0,
                "success_count": 0, "failed_count": 0,
            }
            self._publish_batch_progress(task_id, children, index, len(steps))
            running = self._running_tasks.get(child.task_id)
            while running is not None and not running.done():
                done, _ = await asyncio.wait({running}, timeout=BATCH_CHILD_POLL_SECONDS)
                if done:
                    break
                self._refresh_batch_child(children[index])
                self._publish_batch_progress(task_id, children, index, len(steps))
            finished = self.get_task(child.task_id)
            child_status = getattr(finished, "status", "failed")
            child_status = child_status.value if hasattr(child_status, "value") else str(child_status)
            child_result = getattr(finished, "result", None) or {}
            child_detail = child_result.get("progress_detail") or {}
            success_count = int(child_result.get("success_count") or 0)
            failed_count = int(child_result.get("failed_count") or 0)
            children[index] = {
                "task_id": child.task_id,
                "label": label,
                "stage": child_detail.get("stage") or label,
                "status": child_status,
                "result_status": child_result.get("status"),
                "success_count": success_count,
                "failed_count": failed_count,
                "processed": int(child_result.get("total_requested") or child_detail.get("processed")
                                 or (success_count + failed_count)),
                "total": int(child_result.get("total_requested") or child_detail.get("total") or 0),
                "phase": "finished",
                "error": getattr(finished, "error", None),
            }
            update_task_record(
                task_id=task_id, progress=0.05 + 0.9 * (index + 1) / len(steps),
                status_message=f"已完成 {label}（{index + 1}/{len(steps)}）",
                result={
                    "status": "running",
                    "children": children,
                    "total_tasks": len(steps),
                    "completed_tasks": index + 1,
                    "progress_detail": self._batch_progress_detail(children, index, len(steps), phase="stage_done"),
                },
            )
        failed_tasks = sum(
            child["status"] != "completed"
            or child["result_status"] in ("degraded", "error")
            or child["failed_count"] > 0
            for child in children
        )
        success_count = sum(child["success_count"] for child in children)
        status = "success" if not failed_tasks else "degraded" if success_count else "error"
        return {
            "status": status,
            "children": children,
            "total_tasks": len(steps),
            "failed_tasks": failed_tasks,
            "success_count": success_count,
            "failed_count": sum(child["failed_count"] for child in children),
            "progress_detail": self._batch_progress_detail(children, len(steps) - 1, len(steps), phase="finished"),
        }

    def _refresh_batch_child(self, entry: Dict[str, Any]) -> None:
        """把子任务落库的实时进度合并进父任务 children，供前端展示 当前完成数/全部股票数。"""
        live = self.get_task(entry["task_id"])
        if live is None:
            return
        result = getattr(live, "result", None) or {}
        detail = result.get("progress_detail") or {}
        if not detail:
            return
        status = getattr(live.status, "value", None) or str(live.status)
        entry["status"] = status if status != "running" else "running"
        entry["stage"] = detail.get("stage") or entry["stage"]
        entry["phase"] = detail.get("phase") or "syncing"
        entry["processed"] = int(detail.get("processed") or 0)
        entry["total"] = int(detail.get("total") or 0)
        entry["success_count"] = int(detail.get("success_count") or 0)
        entry["failed_count"] = int(detail.get("failed_count") or 0)
        entry["batch"] = detail.get("batch")
        entry["batches"] = detail.get("batches")
        entry["eta_seconds"] = detail.get("eta_seconds")
        entry["current_symbol"] = detail.get("current_symbol")

    def _batch_progress_detail(
        self, children: List[Dict[str, Any]], index: int, steps: int, *, phase: str,
    ) -> Dict[str, Any]:
        current = children[min(index, len(children) - 1)]
        total = int(current.get("total") or 0)
        processed = int(current.get("processed") or 0)
        aggregated = phase == "finished"
        success = sum(int(item.get("success_count") or 0) for item in children) if aggregated \
            else int(current.get("success_count") or 0)
        failed = sum(int(item.get("failed_count") or 0) for item in children) if aggregated \
            else int(current.get("failed_count") or 0)
        return {
            "stage": current.get("stage") or current["label"],
            "phase": phase,
            "stage_index": min(index + 1, steps),
            "stages": steps,
            "processed": sum(int(item.get("processed") or 0) for item in children) if aggregated else processed,
            "total": sum(int(item.get("total") or 0) for item in children) if aggregated else total,
            "success_count": success,
            "failed_count": failed,
            "batch": current.get("batch"),
            "batches": current.get("batches"),
            "eta_seconds": current.get("eta_seconds"),
            "current_symbol": current.get("current_symbol"),
            "ratio": round(min(1.0, processed / total), 4) if total else 0.0,
        }

    def _publish_batch_progress(
        self, task_id: str, children: List[Dict[str, Any]], index: int, steps: int,
    ) -> None:
        """父任务实时落库分项进度：整体按 3 项加权，当前项按 已同步只数/全部股票数 插值。"""
        detail = self._batch_progress_detail(children, index, steps, phase=children[index].get("phase") or "preparing")
        if detail["total"]:
            message = (f"{detail['stage']}：已完成 {detail['processed']}/{detail['total']} 只"
                       f"（成功 {detail['success_count']}，失败 {detail['failed_count']}）"
                       f" · 第 {index + 1}/{steps} 项")
        else:
            message = f"正在准备 {detail['stage']} · 第 {index + 1}/{steps} 项"
        update_task_record(
            task_id=task_id,
            progress=round(0.05 + 0.9 * (index + detail["ratio"]) / steps, 4),
            status_message=message,
            result={
                "status": "running",
                "children": children,
                "total_tasks": steps,
                "completed_tasks": index,
                "progress_detail": detail,
            },
        )

    async def _run_data_sync_core(
        self, task_id: str, engine: Any, loop: Any, params: Dict[str, Any],
        codes: List[str], pool: Optional[str], indices: bool, all_pool: bool,
        mode: str, count: int, start_date: Optional[str], end_date: Optional[str],
        workers: int,
    ) -> Dict[str, Any]:
        """data_sync 四模式执行体：完整性审计 / 靶向修复 / 当日快照 / 批量增量-全量。"""
        symbols = engine.resolve_symbols(
            codes=codes or None, pool=pool, include_indices=indices, all_pool=all_pool,
            pools=params.get("pools"),
        )

        # 1. 数据完整性体检
        if params.get("check"):
            update_task_record(task_id=task_id, progress=0.5, status_message=f"Auditing data integrity for {len(symbols)} symbols")
            res = await loop.run_in_executor(
                None,
                lambda: engine.audit_integrity(symbols, start_date=start_date, end_date=end_date)
            )
            update_task_record(task_id=task_id, progress=1.0, status_message="Integrity audit completed")
            healthy_count = sum(1 for r in res if r.get("status") == "healthy")
            missing_total = sum(r.get("missing_count", 0) for r in res)
            suspended_total = sum(r.get("suspended_count", 0) for r in res)
            return {
                "status": "success",
                "action": "check",
                "total_codes": len(symbols),
                "healthy_codes": healthy_count,
                "degraded_codes": len(symbols) - healthy_count,
                "missing_gaps": missing_total,
                "suspended_gaps": suspended_total,
                "health_rate": round(healthy_count / len(symbols) * 100, 1) if symbols else None,
                "audit_results": res,
            }

        # 2. 缺漏数据靶向自愈回补
        if params.get("repair"):
            update_task_record(task_id=task_id, progress=0.5, status_message=f"Repairing data gaps for {len(symbols)} symbols")
            res = await loop.run_in_executor(
                None,
                lambda: engine.repair_gaps(symbols)
            )
            update_task_record(task_id=task_id, progress=1.0, status_message="Data repair completed")
            repaired_count = sum(1 for r in res if r.get("repaired"))
            return {
                "status": "success",
                "action": "repair",
                "total_codes": len(symbols),
                "repaired_count": repaired_count,
                "repair_results": res,
            }

        # 3. 当日行情快照落盘
        if params.get("today"):
            update_task_record(task_id=task_id, progress=0.5, status_message=f"Syncing today snapshot for {len(symbols)} symbols")
            res = await loop.run_in_executor(
                None,
                lambda: engine.sync_today_snapshot(symbols)
            )
            update_task_record(task_id=task_id, progress=1.0, status_message="Today snapshot synced")
            return {
                "status": "success",
                "action": "today_snapshot",
                **res,
            }

        # 4. 常规增量/全量批量同步
        reporter = SyncProgressReporter(
            task_id, sync_stage_label(params), len(symbols),
            batch_size=len(symbols), context={"mode": mode},
        )
        reporter.configure(phase="syncing")
        reporter.write(force=True)
        res = await loop.run_in_executor(
            None,
            lambda: engine.sync_batch(
                symbols, mode=mode, count=count, start_date=start_date, end_date=end_date,
                max_workers=workers, on_progress=reporter.on_progress,
            )
        )
        update_task_record(task_id=task_id, progress=0.9, status_message="Finishing sync and updating metadata")
        return {
            **res,
            "progress_detail": reporter.finalize(
                success=res.get("success_count") or 0,
                failed=res.get("failed_count") or 0,
                total=res.get("total_requested"),
            ),
        }

    async def _run_p3_sync(
        self, task_id: str, engine: Any, loop: Any, params: Dict[str, Any],
        scope: str, mode: str, codes: List[str],
    ) -> Dict[str, Any]:
        """P3 全市场同步：单任务互斥 + 不抢占 P0/P1 + 按有效设置分批并发 + 真实批次进度。

        批次大小与并发数只取服务端白名单校验后的有效设置（SSOT §4.3-6），
        不接受请求参数覆盖；市场清单上游不可用时如实失败，绝不伪造清单空跑。
        """
        from core.data.sync_daemon import release_p3, try_acquire_p3
        from server.services.data_sync_settings import effective_settings

        if scope not in ("full_market", "sh", "sz", "bj", "selected", ""):
            raise ValueError(f"P3 同步范围无效：{scope}")
        if scope in ("bj",):
            raise ValueError("北交所暂无权威股票清单数据源，P3 拒绝以猜测清单执行同步")

        wants_audit = bool(params.get("check")) or mode == "audit"
        wants_repair = bool(params.get("repair")) or mode == "repair"
        if scope in ("full_market", "sh", "sz") and (wants_audit or wants_repair or mode == "full"):
            raise ValueError(
                "P3 市场级范围当前仅支持增量同步；完整性审计与缺漏修复请使用运行控制面板的全库体检入口"
            )

        p3_cfg = effective_settings()["p3"]
        batch_size = int(p3_cfg["batch_size"])
        workers = int(p3_cfg["concurrency"])

        acquired, reason = try_acquire_p3(task_id)
        if not acquired:
            raise ValueError(reason)
        reporter = SyncProgressReporter(
            task_id, sync_stage_label(params), 0, batch_size=batch_size,
            context={"tier": "P3", "scope": scope or "selected", "mode": mode},
        )
        try:
            if scope in ("selected", ""):
                symbols = engine.resolve_symbols(codes=codes)
                if not symbols:
                    raise ValueError("P3 指定代码模式需要至少一个有效股票代码")
                if wants_audit or wants_repair:
                    delegate_params = dict(params)
                    delegate_params["check"] = True if wants_audit else params.get("check", False)
                    delegate_params["repair"] = True if wants_repair else params.get("repair", False)
                    if wants_audit:
                        delegate_params.pop("repair", None)
                    else:
                        delegate_params.pop("check", None)
                    return await self._run_data_sync_core(
                        task_id, engine, loop, delegate_params, symbols, None, False, False,
                        "incremental", int(params.get("count", 250)), None, None, workers,
                    )
                sync_mode = mode if mode in ("incremental", "full", "snapshot") else "incremental"
                batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
            else:
                reporter.write(force=True)
                symbols = await loop.run_in_executor(
                    None, lambda: resolve_p3_symbols(engine, scope, bool(params.get("include_indices")))
                )
                if not symbols:
                    raise ValueError("市场清单上游暂不可用（degraded），已拒绝以伪造或缓存清单执行同步")
                batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
                sync_mode = "incremental"

            total = len(symbols)
            reporter.configure(phase="syncing", total=total, batches=len(batches), batch_size=batch_size)
            success_count = 0
            failed_count = 0
            failed_symbols: List[str] = []
            details: List[Dict[str, Any]] = []
            for batch_index, chunk in enumerate(batches, start=1):
                reporter.start_batch(batch_index, processed=success_count + failed_count,
                                     success=success_count, failed=failed_count, batches=len(batches))
                reporter.write(force=True)
                res = await loop.run_in_executor(
                    None,
                    lambda c=chunk: engine.sync_batch(
                        c, mode=sync_mode,
                        count=int(params.get("count", 250)),
                        start_date=params.get("start"), end_date=params.get("end"),
                        max_workers=workers, on_progress=reporter.on_progress,
                    ),
                )
                success_count += res.get("success_count", 0)
                failed_count += res.get("failed_count", 0)
                failed_symbols.extend(res.get("failed_symbols") or [])
                details.extend((res.get("details") or [])[:200])
                reporter.write(force=True)

            # 局部失败如实 degraded，不伪装全部成功（SSOT §4.3 进度契约）
            status = "success" if failed_count == 0 and success_count > 0 else (
                "degraded" if success_count > 0 else "error"
            )
            progress_detail = reporter.finalize(success=success_count, failed=failed_count, total=total)
            update_task_record(task_id=task_id, progress=1.0, status_message=f"P3 finished: {success_count} ok / {failed_count} failed")
            return {
                "status": status,
                "tier": "P3",
                "scope": scope or "selected",
                "mode": sync_mode,
                "total_requested": total,
                "success_count": success_count,
                "failed_count": failed_count,
                "failed_symbols": failed_symbols,
                "batches": len(batches),
                "batch_size": batch_size,
                "workers": workers,
                "details": details,
                "progress_detail": progress_detail,
            }
        finally:
            release_p3(task_id)


def get_task_manager() -> TaskManager:
    """Helper returning the singleton TaskManager instance."""
    return TaskManager.get_instance()
