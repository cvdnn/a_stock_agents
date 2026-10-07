from __future__ import annotations

import pytest

from server.api import market_data as market_module


@pytest.mark.parametrize(
    "path,capability",
    [
        ("/api/market/sentiment", "market.sentiment"),
        ("/api/market/ranks", "market.ranks"),
    ],
)
def test_unconnected_dashboard_routes_return_structured_503(client, path: str, capability: str) -> None:
    """情绪与榜单无真实数据源，必须 fail-closed 返回结构化 503。

    历史缺陷：两端点整块写死 score=78 / total_turnover="1.28万亿" / 三张榜单，
    并把 source 标为 market_sentiment_engine、market_ranks_engine（均不存在），
    谎称来自某个并不存在的"引擎"。
    """
    response = client.get(path)
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "error": "CAPABILITY_NOT_IMPLEMENTED",
        "capability": capability,
        "source": "none",
    }


def test_market_kline_is_implemented_and_never_synthesizes(client) -> None:
    """/api/market/kline 已真实接入（腾讯 → 本地 SQLite），不再属于未实现能力。

    无数据时必须显式 warning + source=empty + 空 klines，严禁合成走势。
    """
    response = client.get("/api/market/kline", params={"code": "000001", "period": "day"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in ("success", "warning")
    if payload["status"] == "warning":
        assert payload["source"] == "empty"
        assert payload["klines"] == []
        assert "禁用合成虚拟数据" in payload["message"]
    else:
        assert payload["source"] in ("data_bridge.tencent_kline", "local.market_data_store")
        assert len(payload["klines"]) >= 5


def test_market_indices_returns_live_or_fallback_data(client) -> None:
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


def test_empty_portfolio_is_a_sourced_empty_state(client, monkeypatch) -> None:
    monkeypatch.setattr(market_module, "get_open_positions", lambda enrich_quote=False: [])
    response = client.get("/api/portfolio/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "empty"
    assert data["source"] == "core.strategy.position_manager.get_open_positions"
    assert data["holdings"] == []
    assert data["count"] == 0
    assert data["as_of"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "生产缺陷（非用例问题）：GET /api/watchlist 在池为空时捏造数据——回填 8 只硬编码自选股"
        "（宁德时代/贵州茅台…），并对 price=0 兜底成 328.56、change_pct 兜底成 2.77、"
        "net_inflow 写死 '+1.28亿'，active_detail 更写死 volume/amount/industry/pe/pb/ma 等全套画像。"
        "违反项目《零虚假数据原则》。该端点改为如实返回 sourced-empty 后本用例会自动转 PASS，"
        "strict 保证届时以 XPASS 失败提醒移除本标记，绝不允许静默放行假数据。"
    ),
)
def test_empty_watchlist_is_a_sourced_empty_state(client, monkeypatch) -> None:
    """空自选池必须如实标注来源与空状态，严禁回落到硬编码假自选股。"""
    monkeypatch.setattr(market_module, "load_stock_pools", lambda: {})
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "empty"
    assert data["source"] == "config/stock_pools.yaml"
    assert data["stocks"] == []
    assert data["as_of"]


def test_monitor_reports_not_running_instead_of_synthetic_events(client) -> None:
    response = client.get("/api/monitor/stream")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_running"
    assert data["source"] == "server_runtime"
    assert data["is_monitoring"] is False
    assert data["events"] == []
    assert data["strategies"] == []
    assert data["as_of"]
