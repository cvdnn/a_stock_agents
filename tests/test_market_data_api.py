from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from server.api import market_data as market_module
from server.app import app


@pytest.mark.parametrize(
    "path,capability",
    [
        ("/api/market/indices", "market.indices"),
        ("/api/market/sentiment", "market.sentiment"),
        ("/api/market/kline?code=000001&period=day", "market.kline"),
        ("/api/market/ranks", "market.ranks"),
        ("/api/portfolio/analysis", "portfolio.analysis"),
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
