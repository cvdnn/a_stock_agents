# -*- coding: utf-8 -*-
"""
tests/server/test_market_data_sync_api.py
Regression tests for Market Data Sync & Hub REST APIs and Task Manager integration.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from server.app import app
from server.db import create_auth_token


@pytest.fixture
def auth_headers():
    tok = create_auth_token(1, 3600)
    return {"Authorization": f"Bearer {tok['token']}"}


def test_market_data_clock_endpoint(auth_headers):
    with TestClient(app) as client:
        resp = client.get("/api/market_data/clock", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "date" in data
        assert "time" in data
        assert "is_trading_day" in data
        assert "is_settled" in data
        assert "phase" in data
        assert "phase_label" in data


def test_market_data_ping_endpoint(auth_headers):
    with TestClient(app) as client:
        resp = client.get("/api/market_data/ping", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "local_db" in data
        assert "local_ms" in data
        assert "tencent_ms" in data
        assert "sina_ms" in data
        assert "eastmoney_ms" in data

        # 诚实性约束：探测失败的源必须为 None，不得回落成伪造延迟常量；
        # online 必须由真实可达源推导，local_ms 与 local_db 状态一致。
        external = ("tencent_ms", "sina_ms", "eastmoney_ms")
        reachable = [k for k in external if data[k] is not None]
        assert all(isinstance(data[k], int) and data[k] >= 1 for k in reachable)
        assert data["online"] == bool(reachable), "online 必须由真实可达源推导"
        assert (data["local_ms"] is None) == (not data["local_db"]), "不可达时 local_ms 不得返回数值"


def test_market_data_daemon_control_and_logs(auth_headers):
    with TestClient(app) as client:
        # 1. Query status
        r_status = client.post("/api/market_data/daemon/control", json={"action": "status"}, headers=auth_headers)
        assert r_status.status_code == 200
        assert "daemon_running" in r_status.json()

        # 2. Start daemon
        r_start = client.post("/api/market_data/daemon/control", json={"action": "start", "interval": 45, "workers": 6}, headers=auth_headers)
        assert r_start.status_code == 200
        d_start = r_start.json()
        assert d_start["daemon_running"] is True
        assert d_start["interval"] == 45
        assert d_start["workers"] == 6

        # 3. Query logs
        r_logs = client.get("/api/market_data/daemon/logs?tail=20", headers=auth_headers)
        assert r_logs.status_code == 200
        d_logs = r_logs.json()
        assert d_logs["status"] == "success"
        assert len(d_logs["lines"]) > 0

        # 4. Stop daemon
        r_stop = client.post("/api/market_data/daemon/control", json={"action": "stop"}, headers=auth_headers)
        assert r_stop.status_code == 200
        assert r_stop.json()["daemon_running"] is False


def test_settings_datafeed_endpoint(auth_headers):
    with TestClient(app) as client:
        resp = client.post("/api/settings/datafeed", json={"sync_max_workers": 8}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["sync_max_workers"] == 8


def test_pools_import_tdx_endpoint(auth_headers):
    with TestClient(app) as client:
        sample_text = "600519 贵州茅台\n000001 平安银行\n300750 宁德时代"
        resp = client.post("/api/pools/import_tdx", json={"pool": "watchlist", "content": sample_text}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["imported_count"] + data["duplicates"] == 3
        assert len(data["stocks"]) == 3


def test_data_sync_task_integration(auth_headers):
    import time
    with TestClient(app) as client:
        # Submit audit check task
        resp = client.post(
            "/api/tasks",
            json={"task_type": "data_sync", "params": {"check": True, "codes": ["600519"]}},
            headers=auth_headers
        )
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]
        assert task_id

        # Poll status
        completed = False
        for _ in range(10):
            time.sleep(0.1)
            t_res = client.get(f"/api/tasks/{task_id}", headers=auth_headers).json()
            if t_res.get("status") == "completed":
                completed = True
                result = t_res.get("result", {})
                assert result.get("action") == "check"
                assert result.get("total_codes") == 1
                assert "health_rate" in result
                break
        assert completed is True
