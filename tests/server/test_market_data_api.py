from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from server.api import market_data as market_module
from server.app import app


@pytest.mark.parametrize(
    "path,capability",
    [
        ("/api/market/sentiment", "market.sentiment"),
        ("/api/market/ranks", "market.ranks"),
    ],
)
def test_unconnected_dashboard_routes_return_structured_503(path: str, capability: str) -> None:
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "error": "CAPABILITY_NOT_IMPLEMENTED",
        "capability": capability,
        "source": "none",
    }


def test_unconnected_sentiment_and_ranks_never_fabricate_a_market_engine() -> None:
    """情绪与榜单无真实数据源，必须 fail-closed，不得谎称来自某个"引擎"。

    历史缺陷：两端点整块写死 score=78 / total_turnover="1.28万亿" / 三张榜单，
    并把 source 标为 market_sentiment_engine、market_ranks_engine（均不存在）。
    本用例直接调用端点协程，绕开鉴权中间件，确保断言落在业务返回体本身。
    """
    import asyncio

    for coro, capability in (
        (market_module.get_market_sentiment(), "market.sentiment"),
        (market_module.get_market_ranks(), "market.ranks"),
    ):
        response = asyncio.run(coro)
        assert response.status_code == 503
        import json as _json
        payload = _json.loads(response.body.decode("utf-8"))
        assert payload == {
            "status": "unavailable",
            "error": "CAPABILITY_NOT_IMPLEMENTED",
            "capability": capability,
            "source": "none",
        }


def test_market_kline_is_implemented_and_never_synthesizes() -> None:
    """/api/market/kline 已真实接入（腾讯 → 本地 SQLite），不再属于未实现能力。

    无数据时必须显式 warning + source=empty + 空 klines，严禁合成走势。
    """
    import asyncio

    payload = asyncio.run(market_module.get_market_kline(code="000001", period="day"))
    assert payload["status"] in ("success", "warning")
    if payload["status"] == "warning":
        assert payload["source"] == "empty"
        assert payload["klines"] == []
        assert "禁用合成虚拟数据" in payload["message"]
    else:
        assert payload["source"] in ("data_bridge.tencent_kline", "local.market_data_store")
        assert len(payload["klines"]) >= 5


def test_market_indices_returns_live_or_fallback_data() -> None:
    with TestClient(app) as client:
        response = client.get("/api/market/indices")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "indices" in data
    assert len(data["indices"]) >= 4
    sh = next(i for i in data["indices"] if i["code"] == "000001")
    assert sh["name"] == "上证指数"
    assert sh["price"] > 3000
    assert len(sh["sparkline"]) > 0


def test_empty_portfolio_is_a_sourced_empty_state(monkeypatch) -> None:
    monkeypatch.setattr(market_module, "get_open_positions", lambda enrich_quote=False: [])
    with TestClient(app) as client:
        response = client.get("/api/portfolio/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "empty"
    assert data["source"] == "core.strategy.position_manager.get_open_positions"
    assert data["holdings"] == []
    assert data["count"] == 0
    assert data["as_of"]


def test_empty_watchlist_is_a_sourced_empty_state(monkeypatch) -> None:
    monkeypatch.setattr(market_module, "load_stock_pools", lambda: {})
    with TestClient(app) as client:
        response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "empty"
    assert data["source"] == "config/stock_pools.yaml"
    assert data["stocks"] == []
    assert data["as_of"]


def test_monitor_reports_not_running_instead_of_synthetic_events() -> None:
    with TestClient(app) as client:
        response = client.get("/api/monitor/stream")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_running"
    assert data["source"] == "server_runtime"
    assert data["is_monitoring"] is False
    assert data["events"] == []
    assert data["strategies"] == []
    assert data["as_of"]
