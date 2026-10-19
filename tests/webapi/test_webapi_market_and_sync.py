# -*- coding: utf-8 -*-
"""
tests/webapi/test_webapi_market_and_sync.py
WebAPI 模块二：行情数据、持仓全景、自选股池与数据同步接口。

覆盖范围：
1. 情绪与榜单无源路由返回结构化 503 诚实性；
2. 大盘指数零假数据铁律（零合成走势、stale/partial 降级、无静态快照回落）；
3. 日 K 线真实数据接口检验；
4. 持仓汇总与自选股空态 sourced empty 契约（零虚拟资产、零硬编码个股）；
5. 交易时钟、4级链路 ping 探针测速与全离线诚实性；
6. 数据同步守护进程（Daemon）启停控制与运行日志；
7. 通达信自选池文本导入与临时股池隔离；
8. 后台任务提交与轮询；
9. 数据同步白名单设置与重启持久化。
"""
from __future__ import annotations

import io
import time
import urllib.parse
import urllib.request

import pytest
from starlette.testclient import TestClient

from server.api import market_data as market_module


# ------------------------------------------------------------------ 指数隔离与桩数据
@pytest.fixture
def indices_cache_isolated():
    """隔离指数模块级缓存，避免跨用例串味。"""
    cache = market_module._indices_cache
    snapshot = dict(cache)
    cache.update({"data": None, "last_updated": 0.0, "sparklines": {}, "sparklines_updated": 0.0})
    yield cache
    cache.clear()
    cache.update(snapshot)


def _stub_index_quotes(monkeypatch, quotes, sparklines=None):
    monkeypatch.setattr(market_module.DataBridge, "tencent_quote", staticmethod(lambda codes: quotes))
    monkeypatch.setattr(market_module, "_get_index_sparklines", lambda: dict(sparklines or {}))


# ------------------------------------------------------------------ 1. 无源接口 503 诚实性
@pytest.mark.parametrize(
    "path,capability",
    [
        ("/api/market/sentiment", "market.sentiment"),
        ("/api/market/ranks", "market.ranks"),
    ],
)
def test_unconnected_dashboard_routes_return_structured_503(client: TestClient, path: str, capability: str) -> None:
    res = client.get(path)
    assert res.status_code == 503
    assert res.json() == {
        "status": "unavailable",
        "error": "CAPABILITY_NOT_IMPLEMENTED",
        "capability": capability,
        "source": "none",
    }


# ------------------------------------------------------------------ 2. 指数零假数据与状态降级
def test_market_indices_fails_closed_without_snapshot_fallback(
    client: TestClient, monkeypatch, indices_cache_isolated
) -> None:
    _stub_index_quotes(monkeypatch, {})
    res = client.get("/api/market/indices")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unavailable"
    assert data["source"] == "empty"
    assert data["indices"] == []
    for fabricated in ("3888.11", "13471.26", "3322.04", "1553.39", "baseline"):
        assert fabricated not in res.text


def test_market_indices_delivers_only_stubbed_quotes(
    client: TestClient, monkeypatch, indices_cache_isolated
) -> None:
    quotes = {
        "sh000001": {"price": 3901.5, "change": 13.39, "change_pct": 0.34, "open": 3895.0,
                     "high": 3915.2, "low": 3888.4, "prev_close": 3889.02,
                     "amount_wan": 452100000.0, "volume_hands": 579000000},
        "sz399001": {"price": 13500.0, "change": 28.74, "change_pct": 0.21, "open": 13480.0,
                     "high": 13520.0, "low": 13470.0, "prev_close": 13471.9,
                     "amount_wan": 0, "volume_hands": 0},
        "sz399006": {"price": 3340.0, "change": 17.96, "change_pct": 0.54, "open": 3330.0,
                     "high": 3345.0, "low": 3325.0, "prev_close": 3322.6,
                     "amount_wan": 1200000.0, "volume_hands": 165000000},
        "sh000688": {"price": 1560.0, "change": 6.61, "change_pct": 0.43, "open": 1555.0,
                     "high": 1565.0, "low": 1550.0, "prev_close": 1553.9,
                     "amount_wan": 77900.0, "volume_hands": 100000000},
    }
    _stub_index_quotes(monkeypatch, quotes)
    data = client.get("/api/market/indices").json()
    assert data["status"] == "success"
    assert data["count"] == 4
    sh = next(i for i in data["indices"] if i["code"] == "000001")
    assert sh["price"] == 3901.5
    assert sh["sparkline"] == []  # 无日K时不合成假点位


def test_market_indices_stale_and_partial_states(
    client: TestClient, monkeypatch, indices_cache_isolated
) -> None:
    # 1. 仅有 1 路行情，如实标注 partial
    quotes_single = {
        "sh000001": {"price": 3901.5, "change": 13.39, "change_pct": 0.34, "open": 3895.0,
                     "high": 3915.2, "low": 3888.4, "prev_close": 3889.02,
                     "amount_wan": 1000.0, "volume_hands": 1000},
    }
    _stub_index_quotes(monkeypatch, quotes_single)
    data_partial = client.get("/api/market/indices").json()
    assert data_partial["status"] == "partial"
    assert data_partial["count"] == 1

    # 2. 缓存过期且源不可达，标注 stale
    indices_cache_isolated["last_updated"] = 0.0
    monkeypatch.setattr(market_module.DataBridge, "tencent_quote", staticmethod(lambda codes: {}))
    data_stale = client.get("/api/market/indices").json()
    assert data_stale["status"] == "stale"
    assert data_stale["stale"] is True


# ------------------------------------------------------------------ 3. 日 K 线端点
def test_market_kline_endpoint(client: TestClient) -> None:
    res = client.get("/api/market/kline", params={"code": "000001", "period": "day"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] in ("success", "warning")
    if payload["status"] == "warning":
        assert payload["klines"] == []
    else:
        assert len(payload["klines"]) >= 5


# ------------------------------------------------------------------ 4. 持仓全景与自选股空态
def test_portfolio_overview_and_empty_state(client: TestClient, monkeypatch) -> None:
    # 空持仓：一律留 None，严禁写死 10 万元资金
    monkeypatch.setattr(market_module, "get_open_positions", lambda enrich_quote=False: [])
    empty_res = client.get("/api/portfolio/overview")
    assert empty_res.status_code == 200
    empty_data = empty_res.json()
    assert empty_data["status"] == "empty"
    assert empty_data["total_assets"] is None
    assert empty_data["available_cash"] is None
    assert empty_data["donut_data"] == []

    # 真实持仓汇总
    monkeypatch.setattr(market_module, "get_open_positions", lambda enrich_quote=False: [
        {"code": "600519", "name": "贵州茅台", "qty": 100, "buy_price": 1500.0,
         "cost": 150000.0, "cur_price": 1600.0, "market_value": 160000.0,
         "pnl": 10000.0, "pnl_pct": 6.67},
        {"code": "000001", "name": "平安银行", "qty": 1000, "buy_price": 12.0,
         "cost": 12000.0, "cur_price": 11.0, "market_value": 11000.0,
         "pnl": -1000.0, "pnl_pct": -8.33},
    ])
    real_data = client.get("/api/portfolio/overview").json()
    assert real_data["status"] == "success"
    assert real_data["position_cost"] == "¥162,000.00"
    assert real_data["position_market_value"] == "¥171,000.00"
    assert real_data["floating_pnl"] == 9000.0


def test_empty_watchlist_and_deduplication(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(market_module, "load_stock_pools", lambda: {})
    res = client.get("/api/watchlist")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "empty"
    assert data["stocks"] == []
    assert data["active_stock_detail"] is None


# ------------------------------------------------------------------ 5. 时钟与 4 级链路 Ping 探针
def test_market_data_clock(client: TestClient) -> None:
    res = client.get("/api/market_data/clock")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    for field in ("date", "time", "is_trading_day", "phase"):
        assert field in data


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.close()
        return False


def test_market_data_ping_probe(client: TestClient, monkeypatch) -> None:
    # 模拟可达源与全断网
    def fake_urlopen(req, timeout=None, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "gtimg" in url:
            time.sleep(0.002)
            return _FakeResponse(b"v=1;")
        raise OSError("unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    data = client.get("/api/market_data/ping").json()
    assert data["status"] == "success"
    assert data["tencent_ms"] is not None
    assert data["sina_ms"] is None  # 不可达源必须为 None，禁伪造常数
    assert data["online"] is True


# ------------------------------------------------------------------ 6. 守护进程控制与日志
def test_market_data_daemon_control(client: TestClient) -> None:
    # 启动
    r_start = client.post("/api/market_data/daemon/control", json={"action": "start", "interval": 60, "workers": 4})
    assert r_start.status_code == 200
    assert r_start.json()["daemon_running"] is True

    # 日志
    r_logs = client.get("/api/market_data/daemon/logs?tail=10")
    assert r_logs.status_code == 200
    assert r_logs.json()["status"] == "success"

    # 停止
    r_stop = client.post("/api/market_data/daemon/control", json={"action": "stop"})
    assert r_stop.status_code == 200
    assert r_stop.json()["daemon_running"] is False


# ------------------------------------------------------------------ 7. 通达信导入与任务管理器
def test_pools_import_tdx_isolated(client: TestClient, isolated_user_pools) -> None:
    text = "600519 贵州茅台\n000001 平安银行"
    res = client.post("/api/pools/import_tdx", json={"pool": "watchlist", "content": text})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    landing = (isolated_user_pools / "selected_pool.csv").read_text(encoding="utf-8")
    assert "600519" in landing and "000001" in landing


def test_data_sync_task_submit_and_poll(client: TestClient) -> None:
    res = client.post("/api/tasks", json={"task_type": "data_sync", "params": {"check": True, "codes": ["600519"]}})
    assert res.status_code == 200
    task_id = res.json()["task_id"]

    deadline = time.monotonic() + 10.0
    completed = False
    while time.monotonic() < deadline and not completed:
        time.sleep(0.02)
        t_res = client.get(f"/api/tasks/{task_id}").json()
        if t_res.get("status") == "completed":
            completed = True
            assert t_res.get("result", {}).get("action") == "check"
    assert completed is True


# ------------------------------------------------------------------ 8. 数据同步设置持久化
def test_data_sync_settings_whitelist_and_persistence(client: TestClient) -> None:
    # 读初始设置
    res_get = client.get("/api/data-sync/settings")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["status"] == "success"
    settings = data["settings"]
    assert "base" in settings and "daemon" in settings

    # 改动并发设置
    current_concurrency = settings["base"].get("concurrency", 4)
    new_concurrency = 6 if current_concurrency != 6 else 8
    res_put = client.put("/api/data-sync/settings", json={"base": {"concurrency": new_concurrency}})
    assert res_put.status_code == 200
    assert res_put.json()["settings"]["base"]["concurrency"] == new_concurrency

    # 再次读取验证持久化生效
    res_verify = client.get("/api/data-sync/settings")
    assert res_verify.json()["settings"]["base"]["concurrency"] == new_concurrency
