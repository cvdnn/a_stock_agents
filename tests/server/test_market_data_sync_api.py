# -*- coding: utf-8 -*-
"""
tests/server/test_market_data_sync_api.py
Regression tests for Market Data Sync & Hub REST APIs and Task Manager integration.

`auth_headers` / `client` 由 tests/conftest.py 统一供给，本文件不再各自建 fixture。
"""
from __future__ import annotations

import io
import time
import urllib.parse
import urllib.request

import pytest


def test_market_data_clock_endpoint(client):
    resp = client.get("/api/market_data/clock")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    for key in ("date", "time", "is_trading_day", "is_settled", "phase", "phase_label"):
        assert key in data


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture()
def fake_probe(monkeypatch):
    """桩化 4 级链路测速的真实外网探测。

    `/api/market_data/ping` 会对腾讯/新浪/东财各发一次 `urlopen(timeout=1.5)`，
    直接跑既拖慢套件又让结果随网络状况漂移（离线时 online=False，用例语义随之改变）。
    本 fixture 由用例指定"哪些源可达"，从而确定性地校验其诚实性契约：
    不可达源必须返回 None，绝不回落成假延迟常量。
    """
    def install(reachable: set[str]):
        def fake_urlopen(req, timeout=None, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            host = urllib.parse.urlparse(url).hostname or ""
            if not any(token in host for token in reachable):
                raise OSError(f"stubbed unreachable: {host}")
            time.sleep(0.002)  # 保证测得非零耗时，贴近真实探针行为
            return _FakeResponse(b"v=1;")

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        # 本地 SQLite 探测与外网无关，保持真实执行

    return install


def test_market_data_ping_reports_only_reachable_sources(client, fake_probe):
    """诚实性约束：可达源给出真实毫秒数，不可达源必须为 None，online 由可达集合推导。"""
    fake_probe({"gtimg"})
    resp = client.get("/api/market_data/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"

    assert isinstance(data["tencent_ms"], int) and data["tencent_ms"] >= 1
    assert data["sina_ms"] is None, "不可达的新浪源被回落成了数值 → 伪造延迟"
    assert data["eastmoney_ms"] is None, "不可达的东财源被回落成了数值 → 伪造延迟"
    assert data["online"] is True
    assert (data["local_ms"] is None) == (not data["local_db"]), "不可达时 local_ms 不得返回数值"


def test_market_data_ping_is_honest_when_fully_offline(client, fake_probe):
    """全源不可达（断网）时严禁显示"链路全部就绪"，三源必须全部 None 且 online=False。"""
    fake_probe(set())
    data = client.get("/api/market_data/ping").json()
    assert data["tencent_ms"] is None
    assert data["sina_ms"] is None
    assert data["eastmoney_ms"] is None
    assert data["online"] is False


def test_market_data_daemon_control_and_logs(client):
    # 1. Query status
    r_status = client.post("/api/market_data/daemon/control", json={"action": "status"})
    assert r_status.status_code == 200
    assert "daemon_running" in r_status.json()

    # 2. Start daemon
    r_start = client.post(
        "/api/market_data/daemon/control",
        json={"action": "start", "interval": 45, "workers": 6},
    )
    assert r_start.status_code == 200
    d_start = r_start.json()
    assert d_start["daemon_running"] is True
    assert d_start["interval"] == 45
    assert d_start["workers"] == 6

    # 3. Query logs
    r_logs = client.get("/api/market_data/daemon/logs?tail=20")
    assert r_logs.status_code == 200
    d_logs = r_logs.json()
    assert d_logs["status"] == "success"
    assert len(d_logs["lines"]) > 0

    # 4. Stop daemon
    r_stop = client.post("/api/market_data/daemon/control", json={"action": "stop"})
    assert r_stop.status_code == 200
    assert r_stop.json()["daemon_running"] is False


def test_settings_datafeed_endpoint(client):
    resp = client.post("/api/settings/datafeed", json={"sync_max_workers": 8})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["sync_max_workers"] == 8


def test_pools_import_tdx_endpoint(client, isolated_user_pools):
    """通达信文本导入必须落在隔离股池，严禁写进用户真实自选池。"""
    sample_text = "600519 贵州茅台\n000001 平安银行\n300750 宁德时代"
    resp = client.post("/api/pools/import_tdx", json={"pool": "watchlist", "content": sample_text})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["imported_count"] + data["duplicates"] == 3
    assert len(data["stocks"]) == 3
    # 前端 pool 名 `watchlist` 经 pool_type_map 映射到落盘池 `selected`
    assert data["pool"] == "watchlist"
    landing = (isolated_user_pools / "selected_pool.csv").read_text(encoding="utf-8")
    for code in ("600519", "000001", "300750"):
        assert code in landing, f"{code} 未落入隔离自选池"


def test_data_sync_task_integration(client):
    """任务提交后须能被轮询到 completed，且回传真实的稽核聚合结果。"""
    resp = client.post(
        "/api/tasks",
        json={"task_type": "data_sync", "params": {"check": True, "codes": ["600519"]}},
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]
    assert task_id

    # 后台任务真正完成前，以 20ms 步进快速轮询（原实现固定 100ms × 10 次，白等）
    deadline = time.monotonic() + 10.0
    completed = False
    while time.monotonic() < deadline and not completed:
        time.sleep(0.02)
        t_res = client.get(f"/api/tasks/{task_id}").json()
        if t_res.get("status") == "completed":
            completed = True
            result = t_res.get("result", {})
            assert result.get("action") == "check"
            assert result.get("total_codes") == 1
            assert "health_rate" in result
    assert completed is True
