# -*- coding: utf-8 -*-
"""
tests/server/test_data_sync_settings.py
SPEC-UI-003 必验清单后端回归：设置白名单校验、local/ 持久化与重启回读、
P3 交易日定时调度判定、P3 单任务互斥与不抢占 P0/P1、概览与盯盘流零伪造。
"""
from __future__ import annotations

import json
import os
import stat
from datetime import datetime, time as dt_time

import pytest
from starlette.testclient import TestClient

from server.app import app
from server.db import create_auth_token
from server.services import data_sync_settings as svc


def test_full_market_update_can_include_core_indices_without_pool_filter():
    from server.tasks import task_manager

    class Engine:
        DEFAULT_INDICES = ("sh000001", "sz399001")

        def list_market_symbols(self, scope):
            assert scope == "full_market"
            return ["sh600519", "sz000001", "sh000001"]

    assert hasattr(task_manager, "resolve_p3_symbols")
    assert task_manager.resolve_p3_symbols(Engine(), "full_market", True) == [
        "sh600519", "sz000001", "sh000001", "sz399001",
    ]

    class EmptyEngine(Engine):
        def list_market_symbols(self, scope):
            return []

    assert task_manager.resolve_p3_symbols(EmptyEngine(), "full_market", True) == []


def test_batch_update_creates_separate_index_shanghai_and_shenzhen_tasks(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from server.tasks.task_manager import TaskManager

    submitted = []
    monkeypatch.setattr("server.tasks.task_manager.update_task_record", lambda **_kwargs: None)

    class Manager(TaskManager):
        def submit_task(self, task_type, params, timeout_seconds=300):
            task_id = f"child-{len(submitted) + 1}"
            submitted.append((task_type, params, timeout_seconds))
            self._running_tasks[task_id] = asyncio.create_task(asyncio.sleep(0))
            return SimpleNamespace(task_id=task_id)

        def get_task(self, task_id):
            index = int(task_id[-1])
            return SimpleNamespace(
                task_id=task_id,
                status="failed" if index == 2 else "completed",
                result={"success_count": 10, "failed_count": 2 if index == 1 else 0},
                error="上游不可用" if index == 2 else None,
            )

    result = asyncio.run(Manager()._run_data_sync_batch("parent-1", {"trigger": "manual"}))
    assert [(kind, params["tier"], params.get("scope")) for kind, params, _ in submitted] == [
        ("data_sync", "P2", "indices"),
        ("data_sync", "P3", "sh"),
        ("data_sync", "P3", "sz"),
    ]
    assert all(params["parent_task_id"] == "parent-1" for _, params, _ in submitted)
    assert [timeout for _, _, timeout in submitted] == [1800, 7200, 7200]
    assert result["status"] == "degraded"
    assert result["failed_tasks"] == 2
    assert len(result["children"]) == 3


def test_p3_child_publishes_live_symbol_progress_during_sync(monkeypatch):
    """一键更新执行期间必须实时落库 当前完成数/全部股票数，供前端进度条与计数消费。"""
    import asyncio
    from server.tasks.task_manager import TaskManager

    written = []

    class FakeEngine:
        def list_market_symbols(self, _scope):
            return [f"sh60{i:04d}" for i in range(5)]

        def sync_batch(self, symbols, **kwargs):
            on_progress = kwargs.get("on_progress")
            assert callable(on_progress), "P3 必须把逐标的进度回调透传给同步引擎"
            for index, symbol in enumerate(symbols, start=1):
                on_progress({"processed": index, "total": len(symbols),
                             "success_count": index, "failed_count": 0, "symbol": symbol})
            return {"success_count": len(symbols), "failed_count": 0, "failed_symbols": [], "details": []}

    class DirectLoop:
        async def run_in_executor(self, _executor, fn):
            return fn()

    def fake_update(**kwargs):
        result = kwargs.get("result") or {}
        detail = result.get("progress_detail")
        if detail:
            written.append((detail["phase"], detail["processed"], detail["total"], kwargs.get("status_message")))

    monkeypatch.setattr("core.data.sync_daemon.try_acquire_p3", lambda _task_id: (True, None))
    monkeypatch.setattr("core.data.sync_daemon.release_p3", lambda _task_id: None)
    monkeypatch.setattr("server.services.data_sync_settings.effective_settings",
                        lambda: {"p3": {"batch_size": 2, "concurrency": 1}})
    monkeypatch.setattr("server.tasks.task_manager.update_task_record", fake_update)

    result = asyncio.run(TaskManager()._run_p3_sync(
        "p3-live", FakeEngine(), DirectLoop(), {"tier": "P3", "scope": "sh"}, "sh", "incremental", []))

    assert result["total_requested"] == 5
    assert result["progress_detail"]["processed"] == 5
    assert result["progress_detail"]["total"] == 5
    live = [item for item in written if item[0] == "syncing"]
    assert live, "P3 运行期间未落库任何实时进度"
    assert all(item[2] == 5 for item in live), "全部股票数必须在解析清单后立即确定"
    assert [item[1] for item in live] == sorted(item[1] for item in live), "完成数不得回退"
    assert max(item[1] for item in live) > 0, "完成数必须随同步推进而增长"
    assert any("已完成 2/5" in (item[3] or "") for item in live), "进度文案需直接给出 完成数/全部股票数"
    assert any(item[0] == "preparing" for item in written), "解析清单阶段也要有可见状态"


def test_batch_parent_mirrors_child_live_progress_for_one_click_update(monkeypatch):
    """父任务必须把子任务的实时完成数聚合进 children，前端才能不依赖子任务列表渲染进度。"""
    import asyncio
    import copy
    from types import SimpleNamespace
    from server.tasks import task_manager as tm
    from server.tasks.task_manager import TaskManager

    monkeypatch.setattr(tm, "BATCH_CHILD_POLL_SECONDS", 0.01)
    updates = []
    monkeypatch.setattr("server.tasks.task_manager.update_task_record",
                        lambda **kwargs: updates.append(copy.deepcopy(kwargs)))

    class Manager(TaskManager):
        def submit_task(self, task_type, params, timeout_seconds=300):
            task_id = f"child-{len(self._running_tasks) + 1}"
            self._running_tasks[task_id] = asyncio.ensure_future(asyncio.sleep(0.08))
            return SimpleNamespace(task_id=task_id)

        def get_task(self, task_id):
            pending = self._running_tasks.get(task_id)
            if pending is not None and not pending.done():
                return SimpleNamespace(
                    task_id=task_id, status="running", status_message="沪市日 K：已完成 120/2319 只（成功 118，失败 2）",
                    result={"status": "running", "total_requested": 2319, "success_count": 118, "failed_count": 2,
                            "progress_detail": {"stage": "沪市日 K", "phase": "syncing", "processed": 120,
                                                 "total": 2319, "success_count": 118, "failed_count": 2,
                                                 "batch": 1, "batches": 4, "eta_seconds": 90}},
                    error=None,
                )
            return SimpleNamespace(
                task_id=task_id, status="completed", status_message="Task completed successfully",
                result={"status": "success", "total_requested": 2319, "success_count": 2319, "failed_count": 0},
                error=None,
            )

    result = asyncio.run(Manager()._run_data_sync_batch("parent-live", {"trigger": "manual"}))

    first = updates[0]["result"]
    assert [item["status"] for item in first["children"]] == ["running", "pending", "pending"], \
        "三个分项必须在提交即刻列出，未开始的标记为等待中"
    live_updates = [
        item for item in updates
        if ((item.get("result") or {}).get("progress_detail") or {}).get("processed") == 120
    ]
    assert live_updates, "父任务未把子任务的实时完成数落库"
    detail = live_updates[0]["result"]["progress_detail"]
    assert detail["total"] == 2319
    assert detail["stages"] == 3 and 1 <= detail["stage_index"] <= 3
    assert "120/2319" in live_updates[0]["status_message"]
    child = live_updates[0]["result"]["children"][detail["stage_index"] - 1]
    assert child["processed"] == 120 and child["total"] == 2319
    assert result["progress_detail"]["processed"] == 2319 * 3
    assert [item["processed"] for item in result["children"]] == [2319, 2319, 2319]


def test_batch_update_uses_dedicated_dispatch_instead_of_skill_registry(monkeypatch):
    """Regression: the batch parent must not be treated as a skill id."""
    import asyncio
    from server.tasks.task_manager import TaskManager

    manager = TaskManager()
    calls = []

    async def run_batch(task_id, params):
        calls.append((task_id, params))
        return {"status": "success", "children": []}

    monkeypatch.setattr(manager, "_run_data_sync_batch", run_batch)

    result = asyncio.run(manager._run_specialized_task(
        "parent-1", "data_sync_batch", {"trigger": "manual"},
    ))

    assert result == {"status": "success", "children": []}
    assert calls == [("parent-1", {"trigger": "manual"})]


@pytest.fixture
def auth_headers():
    tok = create_auth_token(1, 3600)
    return {"Authorization": f"Bearer {tok['token']}"}


@pytest.fixture
def isolated_settings_file(tmp_path, monkeypatch):
    """每个测试独立的设置文件路径，避免相互污染。"""
    target = tmp_path / "settings" / "data_sync.json"
    monkeypatch.setenv("A_STOCK_DATA_SYNC_SETTINGS_FILE", str(target))
    return target


# ---------------------------------------------------------------------------
# 白名单与范围校验（清单：设置字段经过白名单和范围校验）
# ---------------------------------------------------------------------------

def test_validate_rejects_unknown_domain_and_fields():
    errors, _ = svc.validate_patch({"hacked": 1, "base": {"concurrency": 4, "evil": 2}})
    fields = {e["field"] for e in errors}
    assert "hacked" in fields and "base.evil" in fields


def test_validate_rejects_out_of_range_values():
    errors, _ = svc.validate_patch({
        "base": {"concurrency": 99, "retries": -1},
        "p3": {"batch_size": 10},
    })
    fields = {e["field"] for e in errors}
    assert {"base.concurrency", "base.retries", "p3.batch_size"} <= fields
    # 拒绝而非静默夹紧
    assert all("范围" in e["reason"] for e in errors if e["field"] in ("base.concurrency", "p3.batch_size"))


def test_validate_rejects_bad_time_format_and_ordering():
    errors, _ = svc.validate_patch({"daemon": {"p0_time": "25:99", "p1_time": "9:40"}})
    assert any(e["field"] == "daemon.p0_time" for e in errors)
    errors2, _ = svc.validate_patch({"daemon": {"p0_time": "16:00", "p1_time": "15:40"}})
    assert any(e["field"] == "daemon.p0_time" and "晚于" in e["reason"] for e in errors2)


def test_validate_requires_at_least_one_external_source():
    errors, _ = svc.validate_patch({
        "external_sources": {"enabled": {"tencent": False, "sina": False, "eastmoney": False}},
    })
    assert any(e["field"] == "external_sources.enabled" and "至少" in e["reason"] for e in errors)


def test_validate_external_order_must_be_full_permutation():
    errors, _ = svc.validate_patch({"external_sources": {"order": ["tencent", "sina"]}})
    assert any(e["field"] == "external_sources.order" for e in errors)


def test_workspace_settings_validate_nested_fields_and_preserve_previous_save(isolated_settings_file):
    errors, _ = svc.validate_patch({"workspace": {
        "common": {"markets": [], "mode": "overwrite", "unexpected": True},
        "history": {"start_mode": "custom", "start_date": ""},
    }})
    assert {"workspace.common.markets", "workspace.common.mode", "workspace.common.unexpected",
            "workspace.history.start_date"} <= {error["field"] for error in errors}

    errors, _ = svc.save_settings({"workspace": {"common": {"minute_days": 60}}})
    assert errors == []
    errors, effective = svc.save_settings({"workspace": {"quality": {"retry_max": 5}}})
    assert errors == []
    assert effective["workspace"]["common"]["minute_days"] == 60
    assert effective["workspace"]["quality"]["retry_max"] == 5


# ---------------------------------------------------------------------------
# 持久化：local/ 落盘、权限、原子写、重启回读、损坏回退（清单第 2/5 条）
# ---------------------------------------------------------------------------

def test_save_persists_under_local_with_owner_only_permissions(isolated_settings_file):
    errors, effective = svc.save_settings({"p3": {"time": "16:30", "batch_size": 800}})
    assert errors == []
    path = isolated_settings_file
    assert path.is_file()
    mode = stat.S_IMODE(path.stat().st_mode)
    if os.name != "nt":
        assert mode & 0o077 == 0, f"设置文件权限必须仅当前用户可读写，实为 {oct(mode)}"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["p3"]["time"] == "16:30" and saved["p3"]["batch_size"] == 800
    assert effective["p3"]["batch_size"] == 800


def test_settings_path_resolves_via_workspace_local_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("A_STOCK_DATA_SYNC_SETTINGS_FILE", raising=False)
    from core.workspace import LOCAL_DIR
    assert svc.settings_file_path() == LOCAL_DIR / "settings" / "data_sync.json"


def test_reload_effective_after_reimport(isolated_settings_file):
    """模拟服务重启：直接重新读取文件合并默认值，验证持久化真实生效。"""
    errors, _ = svc.save_settings({"base": {"concurrency": 7}})
    assert errors == []
    reloaded, status = svc.read_persisted()
    assert status == "ok" and reloaded["base"]["concurrency"] == 7
    eff = svc.effective_settings()
    assert eff["base"]["concurrency"] == 7
    # 默认域不受影响（部分更新语义）
    assert eff["p3"]["batch_size"] == svc.DEFAULTS["p3"]["batch_size"]


def test_invalid_save_does_not_touch_file(isolated_settings_file):
    errors, _ = svc.save_settings({"base": {"concurrency": 0}})
    assert errors and not isolated_settings_file.exists()


def test_corrupt_file_falls_back_to_defaults_with_honest_status(isolated_settings_file):
    isolated_settings_file.parent.mkdir(parents=True, exist_ok=True)
    isolated_settings_file.write_text("{ not-json", encoding="utf-8")
    _data, status = svc.read_persisted()
    assert status == "corrupt"
    summary = svc.settings_summary_for_ui()
    assert summary["persisted_status"] == "corrupt"
    assert summary["settings"] == svc.DEFAULTS


def test_apply_to_runtime_bridges_settings_to_cron_state(isolated_settings_file):
    from core.data.sync_daemon import SERVER_SYNC_RUNTIME
    svc.save_settings({"daemon": {"enabled": False, "interval_seconds": 90}, "base": {"concurrency": 6}})
    snapshot = svc.apply_to_runtime()
    assert SERVER_SYNC_RUNTIME["enabled"] is False
    assert SERVER_SYNC_RUNTIME["interval"] == 90
    assert SERVER_SYNC_RUNTIME["workers"] == 6
    assert snapshot["enabled"] is False


# ---------------------------------------------------------------------------
# REST 端点契约（SPEC-UI-003 §7.2）
# ---------------------------------------------------------------------------

def test_get_settings_endpoint_returns_effective_and_independent_local_layer(auth_headers, isolated_settings_file):
    with TestClient(app) as client:
        resp = client.get("/api/data-sync/settings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert set(data["settings"]) >= {"base", "daemon", "p3", "external_sources", "integrity"}
        # 外部行情源优先级与本地 SQLite 层相互独立：两个顶层结构，本地层只读
        local_layer = data["local_layer"]
        assert "db_relative_path" in local_layer and "journal_mode" in local_layer
        assert "order" not in local_layer


def test_put_settings_endpoint_rejects_invalid_with_field_errors(auth_headers, isolated_settings_file):
    with TestClient(app) as client:
        resp = client.put("/api/data-sync/settings", json={"base": {"concurrency": 200}}, headers=auth_headers)
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "SETTINGS_VALIDATION_FAILED"
        assert any(e["field"] == "base.concurrency" for e in detail["errors"])


def test_put_settings_endpoint_persists_and_applies(auth_headers, isolated_settings_file):
    with TestClient(app) as client:
        resp = client.put("/api/data-sync/settings", json={
            "daemon": {"enabled": True, "p0_time": "15:35", "p1_time": "15:40"},
            "p3": {"enabled": True, "time": "16:15", "concurrency": 10, "batch_size": 500},
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["settings"]["p3"]["time"] == "16:15"
        assert data["applied_to_runtime"]["workers"] == 4  # base.concurrency 未被本补丁修改
        assert isolated_settings_file.is_file()
        # 回读刷新：GET 返回与 PUT 一致
        got = client.get("/api/data-sync/settings", headers=auth_headers).json()
        assert got["settings"]["p3"]["batch_size"] == 500


def test_overview_endpoint_only_real_aggregates(auth_headers, isolated_settings_file):
    with TestClient(app) as client:
        resp = client.get("/api/data-sync/overview", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert {"market_phase", "daemon", "settings_summary", "pools", "recent_sync_tasks",
                "latest_p3_task", "availability", "arbiter", "daily_health", "last_audit",
                "dataset_coverage"} <= set(data)
        # D1–D12 登记册（SPEC-DATA §5.1）：12 行与控制台覆盖表一一对应
        assert len(data["dataset_coverage"]) == 12
        assert all(entry["connected"] in (True, False) for entry in data["dataset_coverage"])
        assert set(data["daily_health"]["tiers"]) == {"P0", "P1", "P2"}
        assert data["daily_health"]["target_date"] <= data["market_phase"]["date"]
        assert isinstance(data["recent_sync_tasks"], list)
        # 无 P3 任务时必须为 null，不得伪造演示任务
        assert data["latest_p3_task"] is None or data["latest_p3_task"]["tier"] == "P3"
        assert data["settings_summary"]["p3"]["batch_size"] in (500, 600, 800)  # 默认或测试补丁值


def test_daily_health_uses_settled_target_and_real_meta(tmp_path):
    import sqlite3
    from server.services.data_sync_overview import build_daily_health

    db = tmp_path / "market.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE sync_meta (symbol TEXT PRIMARY KEY, max_date TEXT, is_settled INTEGER)")
        conn.executemany("INSERT INTO sync_meta VALUES (?, ?, ?)", [
            ("sh600519", "2026-09-30", 1),
            ("sz000001", "2026-09-29", 1),
            ("sh000001", "2026-09-30", 1),
        ])
    phase = {"date_str": "2026-10-08", "is_trading_day": True, "is_settled": False}
    health = build_daily_health(
        phase, {"holdings": ["600519"], "watchlist": ["000001"], "focus": ["600519"]},
        ["sh000001"], db,
    )
    assert health["target_date"] == "2026-09-30"
    assert health["target_note"] == "今日未定盘，按上一交易日判断"
    assert health["registered"]["total"] == 3
    assert health["registered"]["fresh"] == 2
    assert health["registered"]["pending"] == 1
    assert health["registered"]["without_data"] == 0
    assert health["tiers"]["P1"]["total"] == 2
    assert health["tiers"]["P1"]["pending"] == 1


def test_daily_health_missing_database_is_not_reported_as_complete(tmp_path):
    from server.services.data_sync_overview import build_daily_health

    phase = {"date_str": "2026-10-08", "is_trading_day": True, "is_settled": True}
    health = build_daily_health(
        phase, {"holdings": ["600519"], "watchlist": [], "focus": []},
        [], tmp_path / "absent.db",
    )
    assert health["target_date"] == "2026-10-08"
    assert health["registered"]["total"] == 1
    assert health["registered"]["without_data"] == 1
    assert health["registered"]["pending"] == 1
    assert health["registered"]["state"] == "no_data"
    assert health["availability"]["local_meta"] is False


def test_dataset_coverage_marks_unconnected_datasets_explicitly():
    from server.services.data_sync_overview import build_dataset_coverage

    entries = build_dataset_coverage(None, None)
    # D1–D12 登记册（SPEC-DATA §5.1）：12 行与控制台覆盖表一一对应
    assert len(entries) == 12
    assert [entry["key"] for entry in entries][:2] == ["base_calendar", "daily_kline"]
    unconnected = [entry for entry in entries if not entry["connected"]]
    assert len(unconnected) == 10
    for entry in unconnected:
        assert entry["as_of"] is None
        assert entry["batch"] is None
        assert entry["completeness"]["state"] == "undetected"
        assert "未接入" in entry["scope"]
    daily = next(entry for entry in entries if entry["key"] == "daily_kline")
    assert daily["completeness"]["state"] == "undetected"
    assert daily["state"] == "unknown"

    audited = build_dataset_coverage(
        {"registered": {"total": 3, "watermark_min": "2026-09-29", "watermark_max": "2026-09-30", "state": "pending"}},
        {"scope": "registered_pools_and_indices", "missing_gaps": 8},
    )
    daily = next(entry for entry in audited if entry["key"] == "daily_kline")
    assert daily["completeness"] == {"state": "missing", "missing": 8, "label": "缺漏 8 处"}
    assert daily["as_of"] == "2026-09-30"


def test_overview_does_not_claim_pool_coverage_when_pool_read_fails(auth_headers, isolated_settings_file, monkeypatch):
    from core.strategy.pool_manager import PoolManager

    with TestClient(app) as client:
        monkeypatch.setattr(PoolManager, "get_pool", lambda self, name: (_ for _ in ()).throw(OSError("pool offline")))
        data = client.get("/api/data-sync/overview", headers=auth_headers).json()
    assert data["pools"] == {"holdings": None, "watchlist": None, "focus": None}
    assert data["daily_health"] is None


def test_monitor_stream_no_fabricated_events(auth_headers):
    with TestClient(app) as client:
        resp = client.get("/api/monitor/stream", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_running" and data["source"] == "server_runtime"
        assert data["events"] == [] and data["strategies"] == []
        assert data["is_monitoring"] is False and data["latency_ms"] is None
        assert data["availability"]["event_feed"] is False
        # 跨层防回归：monitor/stream 端点定义体内不得再内联任何示例盯盘事件与伪造延迟
        # （同文件其他端点的排行榜演示数据由各自整改计划跟踪，不在此断言范围）
        market_path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "server", "api", "market_data.py")
        with open(market_path, encoding="utf-8") as fh:
            market_source = fh.read()
        start = market_source.index("async def get_monitor_stream")
        body = market_source[start:market_source.index("@router", start)]
        for fake in ("中芯国际", "北方华创", "latency_ms\": 12", "is_monitoring\": True"):
            assert fake not in body, f"fabricated monitor payload remains in stream endpoint: {fake}"


# ---------------------------------------------------------------------------
# P3 调度判定与互斥/不抢占（清单：P3 交易日定时 + 单任务互斥）
# ---------------------------------------------------------------------------

def _settings(*overrides):
    """按 "domain.field=value" 覆盖默认设置（仅测试判定用）。"""
    merged = json.loads(json.dumps(svc.DEFAULTS))
    for item in overrides:
        path, raw = item.split("=", 1)
        domain, field = path.split(".", 1)
        value = {"True": True, "False": False}.get(raw, raw if not raw.isdigit() else int(raw))
        merged[domain][field] = value
    return merged


def test_is_auto_tier_due_trading_window_rules():
    late = datetime(2026, 10, 8, 16, 5)  # 交易日时间点示例（纯判定不看交易日）
    done: dict = {}
    from core.data.sync_daemon import is_auto_tier_due
    # 默认 P0 15:35：16:05 已过时点 → 到期
    assert is_auto_tier_due(late, "P0", _settings(), done) is True
    # 总开关关闭 → 一切不触发
    assert is_auto_tier_due(late, "P0", _settings("daemon.enabled=False"), done) is False
    assert is_auto_tier_due(late, "P3", _settings("daemon.enabled=False"), done) is False
    # P3 单独开关
    assert is_auto_tier_due(late, "P3", _settings("p3.enabled=False"), done) is False
    # 未到时间不触发
    early = datetime(2026, 10, 8, 15, 30)
    assert is_auto_tier_due(early, "P0", _settings(), done) is False
    # 当日已执行不重复
    done["P0"] = "2026-10-08"
    assert is_auto_tier_due(late, "P0", _settings(), done) is False
    # 非法时间配置不触发（设置层已白名单拦截，判定层防御）
    assert is_auto_tier_due(late, "P1", _settings("daemon.p1_time=bad"), done) is False


def test_p3_arbiter_mutex_and_no_preempt():
    from core.data.sync_daemon import (
        SYNC_ARBITER, p3_conflict_reason, release_p3, set_core_sync_active, try_acquire_p3,
    )
    SYNC_ARBITER["p3_task"] = None
    SYNC_ARBITER["core_active"] = False
    ok, _ = try_acquire_p3("task-a")
    assert ok is True
    ok2, reason = try_acquire_p3("task-b")
    assert ok2 is False and "task-a" in reason
    assert p3_conflict_reason() is not None
    release_p3("task-b")  # 非持有者不得误清
    assert SYNC_ARBITER["p3_task"] == "task-a"
    release_p3("task-a")
    assert SYNC_ARBITER["p3_task"] is None
    # P0/P1 进行中：P3 必须让路（不抢占）
    set_core_sync_active(True)
    ok3, reason3 = try_acquire_p3("task-c")
    assert ok3 is False and "抢占" in reason3
    set_core_sync_active(False)
    assert p3_conflict_reason() is None


def test_p3_result_retains_all_failed_symbols_across_batches(monkeypatch):
    import asyncio
    from server.tasks.task_manager import TaskManager

    class FakeEngine:
        def list_market_symbols(self, _scope):
            return ["sh600519", "sz000001", "sh600000"]

        def sync_batch(self, symbols, **_kwargs):
            failed = [symbol for symbol in symbols if symbol != "sh600519"]
            return {"success_count": len(symbols) - len(failed), "failed_count": len(failed),
                    "failed_symbols": failed, "details": []}

    class DirectLoop:
        async def run_in_executor(self, _executor, fn):
            return fn()

    monkeypatch.setattr("core.data.sync_daemon.try_acquire_p3", lambda _task_id: (True, None))
    monkeypatch.setattr("core.data.sync_daemon.release_p3", lambda _task_id: None)
    monkeypatch.setattr("server.services.data_sync_settings.effective_settings",
                        lambda: {"p3": {"batch_size": 2, "concurrency": 1}})
    monkeypatch.setattr("server.tasks.task_manager.update_task_record", lambda **_kwargs: None)
    result = asyncio.run(TaskManager()._run_p3_sync(
        "batch-test", FakeEngine(), DirectLoop(), {}, "full_market", "incremental", []))
    assert result["failed_count"] == 2
    assert result["failed_symbols"] == ["sz000001", "sh600000"]


def test_p3_task_creation_rejected_with_409_when_active(auth_headers, isolated_settings_file):
    from core.data.sync_daemon import release_p3, try_acquire_p3
    acquired, _ = try_acquire_p3("blocking-task")
    assert acquired
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/tasks",
                json={"task_type": "data_sync", "params": {"tier": "P3", "scope": "full_market", "mode": "incremental"}},
                headers=auth_headers,
            )
            assert resp.status_code == 409
            assert "blocking-task" in resp.json()["detail"]
    finally:
        release_p3("blocking-task")


def test_p3_bj_scope_fails_honestly_without_network(isolated_settings_file):
    """北交所无权威清单源：任务必须以失败如实收口，不得伪造清单执行。"""
    import time
    from starlette.testclient import TestClient
    with TestClient(app) as client:
        tok = create_auth_token(1, 3600)
        headers = {"Authorization": f"Bearer {tok['token']}"}
        resp = client.post("/api/tasks", json={
            "task_type": "data_sync",
            "params": {"tier": "P3", "scope": "bj", "mode": "incremental"},
        }, headers=headers)
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]
        final = None
        for _ in range(30):
            time.sleep(0.1)
            final = client.get(f"/api/tasks/{task_id}", headers=headers).json()
            if final.get("status") in ("failed", "completed"):
                break
        assert final is not None and final["status"] == "failed"
        assert "北交所" in json.dumps(final, ensure_ascii=False)


def test_p3_full_market_audit_rejected_before_execution(isolated_settings_file):
    import time
    with TestClient(app) as client:
        tok = create_auth_token(1, 3600)
        headers = {"Authorization": f"Bearer {tok['token']}"}
        resp = client.post("/api/tasks", json={
            "task_type": "data_sync",
            "params": {"tier": "P3", "scope": "full_market", "mode": "audit"},
        }, headers=headers)
        task_id = resp.json()["task_id"]
        final = None
        for _ in range(30):
            time.sleep(0.1)
            final = client.get(f"/api/tasks/{task_id}", headers=headers).json()
            if final.get("status") in ("failed", "completed"):
                break
        assert final["status"] == "failed"
        assert "增量" in json.dumps(final, ensure_ascii=False)


def test_datafeed_legacy_endpoint_persists_concurrency(auth_headers, isolated_settings_file):
    with TestClient(app) as client:
        resp = client.post("/api/settings/datafeed", json={"sync_max_workers": 7}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] and data["sync_max_workers"] == 7 and data["persisted"] is True
        persisted, _ = svc.read_persisted()
        assert persisted["base"]["concurrency"] == 7
        bad = client.post("/api/settings/datafeed", json={"sync_max_workers": 0}, headers=auth_headers)
        assert bad.status_code == 400


def test_daemon_control_stop_survives_reload(auth_headers, isolated_settings_file):
    """守护开关写穿持久化：stop 后重启（重新读设置回灌）不得回跳为启用。"""
    with TestClient(app) as client:
        resp = client.post("/api/market_data/daemon/control", json={"action": "stop"}, headers=auth_headers)
        assert resp.status_code == 200 and resp.json()["daemon_running"] is False
        persisted, _status = svc.read_persisted()
        assert persisted["daemon"]["enabled"] is False
        reloaded = svc.apply_to_runtime(svc.effective_settings())
        assert reloaded["enabled"] is False
        client.post("/api/market_data/daemon/control", json={"action": "start"}, headers=auth_headers)


def test_every_setting_is_classified_as_wired_or_persist_only():
    """每项设置都必须在 EXECUTION_WIRING 中如实归类，杜绝新增"可保存但不生效"的静默死配置。

    历史缺陷：external_sources 排序、base.timeout_seconds、cooperation.tdx_target_pool 等
    多份设置只被校验与持久化，执行层从不消费，用户保存后毫无效果却无任何提示。
    """
    def leaves(node, prefix=""):
        for key, value in node.items():
            path = f"{prefix}{key}"
            if isinstance(value, dict):
                yield from leaves(value, path + ".")
            else:
                yield path

    declared = set(svc.EXECUTION_WIRING["wired"]) | set(svc.EXECUTION_WIRING["persist_only"])
    wildcard_prefixes = tuple(p[:-1] for p in declared if p.endswith(".*"))
    actual = set(leaves(svc.DEFAULTS))

    unclassified = {p for p in actual if p not in declared and not p.startswith(wildcard_prefixes)}
    assert not unclassified, f"以下设置项未登记生效范围: {sorted(unclassified)}"

    stale = {p for p in declared if not p.endswith(".*") and p not in actual}
    assert not stale, f"EXECUTION_WIRING 登记了 DEFAULTS 中不存在的设置项: {sorted(stale)}"

    # 两分类不得重叠：同一项不能既"已接线"又"仅持久化"
    overlap = set(svc.EXECUTION_WIRING["wired"]) & set(svc.EXECUTION_WIRING["persist_only"])
    assert not overlap, f"生效范围归类自相矛盾: {sorted(overlap)}"


def test_settings_summary_exposes_execution_wiring(isolated_settings_file):
    """设置接口必须对外披露各项是否真正接线，供前端如实标注"保存后是否生效"。"""
    summary = svc.settings_summary_for_ui()
    wiring = summary["execution_wiring"]
    assert "external_sources.order" in wiring["wired"]
    assert "daemon.p0_time" in wiring["wired"]
    assert "base.timeout_seconds" in wiring["wired"]
    assert "cooperation.tdx_target_pool" in wiring["wired"]
    assert any(p.startswith("workspace.") for p in wiring["persist_only"])


def test_every_setting_is_classified_as_wired_or_persist_only():
    """每项设置都必须在 EXECUTION_WIRING 中如实归类，杜绝新增"可保存但不生效"的静默死配置。

    历史缺陷：external_sources 排序、base.timeout_seconds、cooperation.tdx_target_pool 等
    多份设置只被校验与持久化，执行层从不消费，用户保存后毫无效果却无任何提示。
    """
    def leaves(node, prefix=""):
        for key, value in node.items():
            path = f"{prefix}{key}"
            if isinstance(value, dict):
                yield from leaves(value, path + ".")
            else:
                yield path

    declared = set(svc.EXECUTION_WIRING["wired"]) | set(svc.EXECUTION_WIRING["persist_only"])
    wildcard_prefixes = tuple(p[:-1] for p in declared if p.endswith(".*"))
    actual = set(leaves(svc.DEFAULTS))

    unclassified = {p for p in actual if p not in declared and not p.startswith(wildcard_prefixes)}
    assert not unclassified, f"以下设置项未登记生效范围: {sorted(unclassified)}"

    stale = {p for p in declared if not p.endswith(".*") and p not in actual}
    assert not stale, f"EXECUTION_WIRING 登记了 DEFAULTS 中不存在的设置项: {sorted(stale)}"

    # 两分类不得重叠：同一项不能既"已接线"又"仅持久化"
    overlap = set(svc.EXECUTION_WIRING["wired"]) & set(svc.EXECUTION_WIRING["persist_only"])
    assert not overlap, f"生效范围归类自相矛盾: {sorted(overlap)}"


def test_settings_summary_exposes_execution_wiring(isolated_settings_file):
    """设置接口必须对外披露各项是否真正接线，供前端如实标注"保存后是否生效"。"""
    summary = svc.settings_summary_for_ui()
    wiring = summary["execution_wiring"]
    assert "external_sources.order" in wiring["wired"]
    assert "daemon.p0_time" in wiring["wired"]
    assert "base.timeout_seconds" in wiring["wired"]
    assert "cooperation.tdx_target_pool" in wiring["wired"]
    assert any(p.startswith("workspace.") for p in wiring["persist_only"])
