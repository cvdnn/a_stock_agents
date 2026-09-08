# -*- coding: utf-8 -*-
"""
tests/test_market_data_api.py - Unit & Integration tests for Market, Portfolio, Watchlist & Monitor APIs.
"""
from starlette.testclient import TestClient
from server.app import app

client = TestClient(app)


def test_market_indices_api():
    resp = client.get("/api/market/indices")
    assert resp.status_code == 200
    data = resp.json()
    assert "indices" in data
    assert len(data["indices"]) == 4
    names = [idx["name"] for idx in data["indices"]]
    assert "上证指数" in names
    assert "深证成指" in names
    assert "创业板指" in names
    assert "科创50" in names
    for item in data["indices"]:
        assert len(item["sparkline"]) > 0
        assert item["price"] > 0


def test_market_sentiment_api():
    resp = client.get("/api/market/sentiment")
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 78
    assert "亢温" in data["status_text"]
    assert data["up_count"] > 0
    assert data["down_count"] > 0
    assert len(data["sectors"]) >= 3


def test_market_kline_api():
    resp = client.get("/api/market/kline?code=000001&period=day")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "000001"
    assert len(data["klines"]) >= 20
    assert data["ma5"] > 0


def test_market_ranks_api():
    resp = client.get("/api/market/ranks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["gainers"]) == 5
    assert len(data["losers"]) == 5
    assert len(data["northbound"]) == 5
    assert len(data["news"]) >= 5
    assert len(data["hot_concepts"]) >= 5


def test_portfolio_overview_api():
    resp = client.get("/api/portfolio/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "454.24万" in data["total_assets"]
    assert "328.56万" in data["position_market_value"]
    assert data["position_ratio"] == 72.3
    assert len(data["holdings"]) == 3
    assert len(data["donut_data"]) == 2


def test_portfolio_analysis_api():
    resp = client.get("/api/portfolio/analysis")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sharpe_ratio"] == 1.84
    assert data["win_rate"] == 68.5
    assert data["max_drawdown"] == -8.24
    assert len(data["attributions"]) >= 4
    assert len(data["positions"]) >= 4


def test_watchlist_api():
    resp = client.get("/api/watchlist?active_code=300750")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["stocks"]) >= 10
    assert len(data["custom_indices"]) >= 2
    detail = data["active_stock_detail"]
    assert detail["code"] == "300750"
    assert detail["name"] == "宁德时代"
    assert len(detail["events"]) >= 4
    assert "donut" in detail["capital_flow"]


def test_monitor_stream_api():
    resp = client.get("/api/monitor/stream")
    assert resp.status_code == 200
    data = resp.json()
    assert data["latency_ms"] == 28
    assert data["is_monitoring"] is True
    assert len(data["events"]) >= 3
    assert len(data["strategies"]) == 4
