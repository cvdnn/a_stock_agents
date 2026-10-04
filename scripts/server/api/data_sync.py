# -*- coding: utf-8 -*-
"""server.api.data_sync - 数据同步控制台概览与设置 REST 端点（SPEC-UI-003 §7.2）。

- GET  /api/data-sync/overview   市场阶段、守护运行时、有效设置、股池数量与最近同步任务（全部真实聚合）
- GET  /api/data-sync/settings   服务端默认值与持久化合并后的有效设置 + 本地层只读观测
- PUT  /api/data-sync/settings   白名单校验并原子落盘，回读后返回最终有效值
- POST /api/data-sync/settings/reset  恢复默认（前端负责二次确认交互）

无数据一律返回 null / 空数组 / 明确可用性字段，严禁演示数据。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from server.services import data_sync_settings as settings_service

router = APIRouter(prefix="/api/data-sync", tags=["Data Sync Console"])

_SYNC_TASK_TYPES = ("data_sync", "sync")


@router.get("/settings")
async def get_data_sync_settings() -> Dict[str, Any]:
    """返回服务端默认值合并持久化后的有效设置（含本地层只读观测与持久化状态）。"""
    return {"status": "success", "source": "server.services.data_sync_settings", **settings_service.settings_summary_for_ui()}


@router.put("/settings")
async def put_data_sync_settings(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """白名单校验并保存设置；无效字段逐项拒绝（400），成功后以文件回读值刷新。"""
    errors, effective = settings_service.save_settings(payload or {})
    if errors:
        raise HTTPException(status_code=400, detail={
            "error": "SETTINGS_VALIDATION_FAILED",
            "errors": errors,
            "settings": effective,
        })
    applied = settings_service.apply_to_runtime(effective)
    return {
        "status": "success",
        "settings": effective,
        "persisted_to": str(settings_service.settings_file_path()),
        "applied_to_runtime": {
            "enabled": applied["enabled"],
            "interval": applied["interval"],
            "workers": applied["workers"],
        },
        "message": "设置已校验落盘并回灌服务内自动巡检（仅影响后续任务，不中断运行中任务）",
    }


@router.post("/settings/reset")
async def reset_data_sync_settings() -> Dict[str, Any]:
    """恢复默认设置（全局影响操作；前端必须先二次确认再调用）。"""
    errors, effective = settings_service.reset_to_defaults()
    if errors:
        raise HTTPException(status_code=400, detail={"error": "SETTINGS_VALIDATION_FAILED", "errors": errors})
    settings_service.apply_to_runtime(effective)
    return {"status": "success", "settings": effective, "message": "已恢复服务端默认设置"}


@router.get("/overview")
async def get_data_sync_overview() -> Dict[str, Any]:
    """运行控制页概览：只聚合真实运行时、真实任务与真实股池数据。"""
    from core.data.sync_daemon import SYNC_ARBITER, sync_runtime_snapshot
    from core.data.sync_engine import TradeCalendar
    from core.strategy.pool_manager import PoolManager
    from server.tasks.task_manager import get_task_manager

    phase = TradeCalendar.get_market_phase()
    summary = settings_service.settings_summary_for_ui()

    pools: Dict[str, Any] = {}
    try:
        pm = PoolManager()
        for name in ("holdings", "watchlist", "focus"):
            pools[name] = len(pm.get_pool(name) or [])
    except Exception:
        pools = {"holdings": None, "watchlist": None, "focus": None}

    recent_tasks = []
    latest_p3 = None
    try:
        tasks = get_task_manager().list_tasks(status=None, limit=50)
        for task in tasks:
            raw = task.model_dump() if hasattr(task, "model_dump") else dict(task)
            if raw.get("task_type") not in _SYNC_TASK_TYPES:
                continue
            item = {
                "task_id": raw.get("task_id"),
                "task_type": raw.get("task_type"),
                "status": raw.get("status"),
                "tier": (raw.get("params") or {}).get("tier"),
                "scope": (raw.get("params") or {}).get("scope"),
                "mode": (raw.get("params") or {}).get("mode"),
                "created_at": raw.get("created_at"),
                "elapsed_ms": raw.get("elapsed_ms"),
            }
            recent_tasks.append(item)
            if item["tier"] == "P3" and latest_p3 is None:
                latest_p3 = item
    except Exception:
        recent_tasks = []

    return {
        "status": "success",
        "source": "server.api.data_sync",
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_phase": {
            "date": phase["date_str"],
            "time": phase["time_str"],
            "is_trading_day": phase["is_trading_day"],
            "is_market_open": phase["is_market_open"],
            "is_settled": phase.get("is_settled", False),
            "phase": phase["phase"],
            "phase_label": phase["phase_label"],
        },
        "daemon": sync_runtime_snapshot(),
        "arbiter": {"p3_task": SYNC_ARBITER["p3_task"], "core_active": SYNC_ARBITER["core_active"]},
        "settings_summary": {
            "daemon_enabled": summary["settings"]["daemon"]["enabled"],
            "p0_time": summary["settings"]["daemon"]["p0_time"],
            "p1_time": summary["settings"]["daemon"]["p1_time"],
            "p3": summary["settings"]["p3"],
            "persisted_status": summary["persisted_status"],
        },
        "local_layer": summary["local_layer"],
        "pools": pools,
        "recent_sync_tasks": recent_tasks[:10],
        "latest_p3_task": latest_p3,
        "availability": {
            "settings_persisted": summary["persisted_status"] == "ok",
            "tasks_available": bool(recent_tasks),
        },
    }
