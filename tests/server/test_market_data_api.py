from __future__ import annotations

import pytest

from server.api import market_data as market_module


@pytest.fixture
def indices_cache_isolated():
    """隔离指数模块级缓存：5s TTL 与 stale 分支会跨用例串味，必须进出各清一次。"""
    cache = market_module._indices_cache
    snapshot = dict(cache)
    cache.update({"data": None, "last_updated": 0.0, "sparklines": {}, "sparklines_updated": 0.0})
    yield cache
    cache.clear()
    cache.update(snapshot)


def _stub_index_quotes(monkeypatch, quotes, sparklines=None):
    """桩化指数实时源与日K源，让端点在离线条件下走确定分支。"""
    monkeypatch.setattr(market_module.DataBridge, "tencent_quote", staticmethod(lambda codes: quotes))
    monkeypatch.setattr(market_module, "_get_index_sparklines", lambda: dict(sparklines or {}))


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


def test_market_indices_fails_closed_without_snapshot_fallback(
    client, monkeypatch, indices_cache_isolated
) -> None:
    """行情源不可达且无缓存时必须如实空态，严禁回落任何静态指数快照。

    生产缺陷（本次修复）：曾整块回落 BASELINE_INDICES 冻结快照（上证 3888.11 /
    深证 13471.26 / 创业板 3322.04 / 科创50 1553.39 及其写死 sparkline），
    还标 status="success" + source="baseline_fallback"，把某一天的收盘画面
    当成"今日实时行情"喂给前端渲染。
    """
    _stub_index_quotes(monkeypatch, {})
    response = client.get("/api/market/indices")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["source"] == "empty"
    assert data["indices"] == []
    assert data["count"] == 0
    assert "零虚假数据" in data["message"]
    # 快照残留检查：整份响应体不得再出现任何被写死的指数数值
    for fabricated in ("3888.11", "13471.26", "3322.04", "1553.39", "baseline"):
        assert fabricated not in response.text


def test_market_indices_delivers_only_stubbed_quotes_and_never_synthesizes_sparkline(
    client, monkeypatch, indices_cache_isolated
) -> None:
    """四路报价齐备时逐项取自桩值；无日K则走势必须为空，不得拼一条假曲线。

    生产缺陷（本次修复）：缺日K时用 [昨收, 今开, 最低, (今开+最高)/2, 最高, 现价]
    合成 6 点"分时走势"，前端据此绘制 sparkline 并被当成真实盘中轨迹。
    """
    quotes = {
        "sh000001": {"price": 3901.5, "change": 13.39, "change_pct": 0.34,
                      "open": 3895.0, "high": 3915.2, "low": 3888.4, "prev_close": 3889.02,
                      "amount_wan": 452100000.0, "volume_hands": 579000000},
        "sz399001": {"price": 13500.0, "change": 28.74, "change_pct": 0.21,
                     "open": 13480.0, "high": 13520.0, "low": 13470.0, "prev_close": 13471.9,
                     "amount_wan": 0, "volume_hands": 0},
        "sz399006": {"price": 3340.0, "change": 17.96, "change_pct": 0.54,
                     "open": 3330.0, "high": 3345.0, "low": 3325.0, "prev_close": 3322.6,
                     "amount_wan": 1200000.0, "volume_hands": 165000000},
        "sh000688": {"price": 1560.0, "change": 6.61, "change_pct": 0.43,
                     "open": 1555.0, "high": 1565.0, "low": 1550.0, "prev_close": 1553.9,
                     "amount_wan": 77900.0, "volume_hands": 100000000},
    }
    _stub_index_quotes(monkeypatch, quotes)
    data = client.get("/api/market/indices").json()
    assert data["status"] == "success"
    assert data["source"] == "data_bridge.tencent_quote"
    assert data["count"] == 4
    sh = next(i for i in data["indices"] if i["code"] == "000001")
    assert sh["price"] == 3901.5
    assert sh["pre_close"] == 3889.02
    assert sh["sparkline"] == []          # 无日K来源 → 空，而不是拼出来的 6 点
    sz = next(i for i in data["indices"] if i["code"] == "399001")
    assert sz["turnover_amount"] == "--"  # 成交额为 0 即无来源，不得换算成数字
    assert sz["volume"] == "--"


def test_market_indices_appends_live_price_to_real_kline_series(
    client, monkeypatch, indices_cache_isolated
) -> None:
    """有真实日K时，走势 = 真实收盘序列末点替换为现价，不得虚构任何点位。"""
    quotes = {
        sym: {"price": 100.0, "change": 1.0, "change_pct": 1.0, "open": 99.0,
              "high": 101.0, "low": 98.0, "prev_close": 99.0, "amount_wan": 10.0,
              "volume_hands": 1000}
        for sym in ("sh000001", "sz399001", "sz399006", "sh000688")
    }
    _stub_index_quotes(
        monkeypatch,
        quotes,
        sparklines={"000001": [90.0, 92.0, 95.0, 97.0]},
    )
    data = client.get("/api/market/indices").json()
    sh = next(i for i in data["indices"] if i["code"] == "000001")
    assert sh["sparkline"] == [90.0, 92.0, 95.0, 100.0]


def test_market_indices_reuses_cache_only_as_labelled_stale(
    client, monkeypatch, indices_cache_isolated
) -> None:
    """源不可达但有真实缓存时可复用，但必须降级标注 stale，不得仍称 success/实时。"""
    quotes = {
        sym: {"price": 100.0, "change": 1.0, "change_pct": 1.0, "open": 99.0,
              "high": 101.0, "low": 98.0, "prev_close": 99.0, "amount_wan": 10.0,
              "volume_hands": 1000}
        for sym in ("sh000001", "sz399001", "sz399006", "sh000688")
    }
    _stub_index_quotes(monkeypatch, quotes)
    assert client.get("/api/market/indices").json()["status"] == "success"

    # 缓存已过期（绕过 5s TTL）且源转为不可达
    indices_cache_isolated["last_updated"] = 0.0
    monkeypatch.setattr(market_module.DataBridge, "tencent_quote", staticmethod(lambda codes: {}))
    data = client.get("/api/market/indices").json()
    assert data["status"] == "stale"
    assert data["stale"] is True
    assert data["cached_as_of"]
    assert data["cache_age_seconds"] >= 0


def test_market_indices_marks_partial_instead_of_throwing_away_real_quotes(
    client, monkeypatch, indices_cache_isolated
) -> None:
    """只取到部分指数时如实标 partial，不得因不足 4 路而丢弃真数据去换假快照。"""
    quotes = {
        "sh000001": {"price": 3901.5, "change": 13.39, "change_pct": 0.34, "open": 3895.0,
                     "high": 3915.2, "low": 3888.4, "prev_close": 3889.02,
                     "amount_wan": 1000.0, "volume_hands": 1000},
    }
    _stub_index_quotes(monkeypatch, quotes)
    data = client.get("/api/market/indices").json()
    assert data["status"] == "partial"
    assert data["count"] == 1
    assert [i["code"] for i in data["indices"]] == ["000001"]


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
    # 生产缺陷（本次修复）：空仓分支曾照样报"总资产 ¥100,000.00 / 可用现金 100%"
    assert data["total_assets"] is None
    assert data["available_cash"] is None
    assert data["donut_data"] == []
    assert "100,000" not in response.text


def test_portfolio_overview_aggregates_real_position_fields(client, monkeypatch) -> None:
    """持仓汇总必须走 position_manager 的真实字段，账户级不可知口径一律留 None。

    生产缺陷（本次修复）：汇总读 `h["price"] / h["shares"]`（真实键是 cur_price/qty/market_value），
    键名不匹配使持仓市值恒为 ¥0.00；同时今日盈亏写死 +¥1,850.00、总收益 18.5%、年化 22.3%。
    """
    monkeypatch.setattr(market_module, "get_open_positions", lambda enrich_quote=False: [
        {"code": "600519", "name": "贵州茅台", "qty": 100, "buy_price": 1500.0,
         "cost": 150000.0, "cur_price": 1600.0, "market_value": 160000.0,
         "pnl": 10000.0, "pnl_pct": 6.67},
        {"code": "000001", "name": "平安银行", "qty": 1000, "buy_price": 12.0,
         "cost": 12000.0, "cur_price": 11.0, "market_value": 11000.0,
         "pnl": -1000.0, "pnl_pct": -8.33},
    ])
    data = client.get("/api/portfolio/overview").json()
    assert data["status"] == "success"
    assert data["count"] == 2
    assert data["position_cost"] == "¥162,000.00"
    assert data["position_market_value"] == "¥171,000.00"
    assert data["floating_pnl"] == 9000.0
    assert data["floating_pnl_pct"] == pytest.approx(5.56)
    assert data["account_state"] == "not_wired"
    for unsourceable in ("total_assets", "available_cash", "position_ratio", "cash_ratio",
                         "today_pnl", "today_pnl_pct", "total_return_pct",
                         "annualized_return_pct", "risk_status"):
        assert data[unsourceable] is None
    assert "1,850" not in client.get("/api/portfolio/overview").text


def test_empty_watchlist_is_a_sourced_empty_state(client, monkeypatch) -> None:
    """空自选池必须如实标注来源与空状态，严禁回落到硬编码假自选股。

    回归自生产缺陷档案：该端点曾回填 8 只硬编码自选股（宁德时代/贵州茅台…），
    并对 price=0 兜底成 328.56、change_pct 兜底成 2.77、net_inflow 写死 '+1.28亿'，
    active_detail 更写死 volume/amount/industry/pe/pb/ma 全套画像（违反《零虚假数据原则》）。
    """
    monkeypatch.setattr(market_module, "load_stock_pools", lambda: {})
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "empty"
    assert data["source"] == "config/stock_pools.yaml"
    assert data["stocks"] == []
    assert data["count"] == 0
    assert data["active_stock_detail"] is None
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
