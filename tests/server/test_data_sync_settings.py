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


# ---------------------------------------------------------------------------
# 持久化：local/ 落盘、权限、原子写、重启回读、损坏回退（清单第 2/5 条）
# ---------------------------------------------------------------------------

def test_save_persists_under_local_with_owner_only_permissions(isolated_settings_file):
    errors, effective = svc.save_settings({"p3": {"time": "16:30", "batch_size": 800}})
    assert errors == []
    path = isolated_settings_file
    assert path.is_file()
    mode = stat.S_IMODE(path.stat().st_mode)
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
                "latest_p3_task", "availability", "arbiter"} <= set(data)
        assert isinstance(data["recent_sync_tasks"], list)
        # 无 P3 任务时必须为 null，不得伪造演示任务
        assert data["latest_p3_task"] is None or data["latest_p3_task"]["tier"] == "P3"
        assert data["settings_summary"]["p3"]["batch_size"] in (500, 600, 800)  # 默认或测试补丁值


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
