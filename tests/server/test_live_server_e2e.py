"""live server E2E — 针对**已启动的真实服务**做端到端契约校验。

默认跳过（`A_STOCK_RUN_LIVE_E2E=1` 才执行），且被 `live`/`network`/`slow` 三档标记圈定，
不属于任何自动门禁。

两条硬约束（2026-10-07 重写时校准）：

1. **必须带机器集成凭证**。`/api/*` 自 SPEC-SEC 起是 fail-closed 会话鉴权，旧版本这里
   一个 `Authorization` 都不带，于是除 `/api/health` 与静态 UI 之外全部用例拿到 401，
   再被 `assert response.status == 200` 直接判失败——"红了"却与业务无关。
   现在统一使用刚修复的静态 API Token：设置 `A_STOCK_SERVER_TOKEN` 后以
   `Authorization: Bearer <token>` 访问；未设置则整组 skip，而不是假装通过。

2. **断言必须对齐 fail-closed 契约，严禁反过来保护伪造数据**。旧用例断言
   `sentiment.score > 0`、`ranks.gainers` 非空、`portfolio.analysis.sharpe_ratio > 0`、
   `monitor.is_monitoring is True`、`watchlist` 画像含 `capital_flow` 数值——
   这些响应早已被按《零虚假数据原则》清除为 503 / 空态。若继续断言旧结构，
   等于给"必须有假数据"上锁。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("A_STOCK_RUN_LIVE_E2E") != "1",
    reason="live server E2E is opt-in; set A_STOCK_RUN_LIVE_E2E=1 after starting a configured server",
)

BASE_URL = os.getenv("A_STOCK_LIVE_BASE_URL", "http://127.0.0.1:6300").rstrip("/")
_SERVER_TOKEN = (os.getenv("A_STOCK_SERVER_TOKEN") or "").strip()

#: 已被清除的历史静态快照数值；任何一次响应里再次出现即说明假数据回归
FABRICATED_SNAPSHOT_MARKERS = (
    "3888.11", "13471.26", "3322.04", "1553.39",   # BASELINE_INDICES 指数快照
    "baseline_fallback",                            # 已删除的回落来源
    "watchlist_engine", "market_ranks_engine", "market_sentiment_engine",
    "+¥1,850.00", "¥100,000.00", "328.56", "+1.28亿",
)


@pytest.fixture(scope="module")
def auth_headers():
    if not _SERVER_TOKEN:
        pytest.skip(
            "live E2E 需要 A_STOCK_SERVER_TOKEN 提供机器集成凭据；"
            "/api/* 为 fail-closed 会话鉴权，匿名请求只会得到 401"
        )
    return {"Authorization": f"Bearer {_SERVER_TOKEN}"}


def request_raw(endpoint: str, headers: dict | None = None, method: str = "GET", payload: dict | None = None):
    """返回 (status, body_text)；非 2xx 不抛异常，便于断言 503/401 契约。"""
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    sent = dict(headers or {})
    if payload:
        sent["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=sent, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def fetch_json(endpoint: str, headers: dict | None = None, method: str = "GET", payload: dict | None = None,
               expect_status: int = 200):
    status, text = request_raw(endpoint, headers=headers, method=method, payload=payload)
    assert status == expect_status, f"{method} {endpoint} → {status}（期望 {expect_status}）：{text[:240]}"
    return json.loads(text) if text else {}


def assert_no_fabricated_snapshot(text: str, endpoint: str) -> None:
    hits = [marker for marker in FABRICATED_SNAPSHOT_MARKERS if marker in text]
    assert not hits, f"{endpoint} 响应中重新出现历史伪造数值：{hits}"


# ------------------------------------------------------------------ 无需凭证的入口
def test_live_health():
    res = fetch_json("/api/health")
    assert res["status"] == "ok"
    assert res["db_connected"] is True


def test_live_main_web_ui_root():
    """主 Web 界面 http://127.0.0.1:6300/ 由静态挂载提供，不需要凭证。"""
    status, html = request_raw("/")
    assert status == 200
    assert "量化投资助手" in html or "A-Stock Agents" in html
    assert "js/api.js" in html


def test_live_static_ui():
    status, html = request_raw("/ui/")
    assert status == 200
    assert "量化投资助手" in html or "A-Stock Agents" in html
    assert "mktShPrice" in html
    assert "watchHeroPrice" in html


# ------------------------------------------------------------------ 需凭证的 API 契约
def test_live_api_gateway_root(auth_headers):
    res = fetch_json("/api", headers=auth_headers)
    assert res["status"] == "online"
    assert res["endpoints"]["health"] == "/api/health"
    assert res["endpoints"]["chat_stream"] == "/api/chat/completions/stream"


def test_live_market_indices_never_falls_back_to_snapshot(auth_headers):
    """实时源可达则给真值；不可达只能是 unavailable/stale，绝不回到写死的指数快照。"""
    res = fetch_json("/api/market/indices", headers=auth_headers)
    assert res["status"] in ("success", "partial", "stale", "unavailable")
    assert res["count"] == len(res["indices"])
    if res["status"] == "unavailable":
        assert res["source"] == "empty"
        assert res["indices"] == []
    if res["status"] == "stale":
        assert res["stale"] is True and res["cached_as_of"]
    for item in res["indices"]:
        assert item["price"] > 0
        # 无日K来源时走势必须为空数组，而不是用 OHLC 拼出来的 6 点
        assert isinstance(item["sparkline"], list)


def test_market_indices_snapshot_is_gone_from_the_wire(auth_headers):
    status, text = request_raw("/api/market/indices", headers=auth_headers)
    assert status == 200
    assert_no_fabricated_snapshot(text, "/api/market/indices")


def test_live_market_sentiment_is_fail_closed(auth_headers):
    """情绪榜单尚无真实源，必须结构化 503，而不是 score=78 的演示值。"""
    res = fetch_json("/api/market/sentiment", headers=auth_headers, expect_status=503)
    assert res["status"] == "unavailable"
    assert res["error"] == "CAPABILITY_NOT_IMPLEMENTED"
    assert res["capability"] == "market.sentiment"
    assert res["source"] == "none"


def test_live_market_ranks_is_fail_closed(auth_headers):
    res = fetch_json("/api/market/ranks", headers=auth_headers, expect_status=503)
    assert res["status"] == "unavailable"
    assert res["capability"] == "market.ranks"


def test_live_market_kline_is_real_or_empty(auth_headers):
    res = fetch_json("/api/market/kline?code=000001&period=day", headers=auth_headers)
    assert res["status"] in ("success", "warning")
    if res["status"] == "warning":
        assert res["source"] == "empty"
        assert res["klines"] == []
    else:
        assert len(res["klines"]) >= 5
        assert res["source"] in ("data_bridge.tencent_kline", "local.market_data_store")


def test_live_portfolio_overview_reports_only_sourced_fields(auth_headers):
    """持仓总览只交付真实持仓口径；账户现金与收益类口径必须为 null。"""
    res = fetch_json("/api/portfolio/overview", headers=auth_headers)
    assert res["status"] in ("empty", "success")
    assert res["count"] == len(res["holdings"])
    assert res["account_state"] == "not_wired"
    for account_field in ("total_assets", "available_cash", "position_ratio", "cash_ratio",
                          "today_pnl", "today_pnl_pct", "total_return_pct",
                          "annualized_return_pct"):
        assert res[account_field] is None, f"{account_field} 无数据源却拿到了值"
    assert res["donut_data"] == []


def test_live_portfolio_overview_carries_no_demo_figures(auth_headers):
    status, text = request_raw("/api/portfolio/overview", headers=auth_headers)
    assert status == 200
    assert_no_fabricated_snapshot(text, "/api/portfolio/overview")


def test_live_portfolio_analysis_is_fail_closed(auth_headers):
    """收益归因需逐日净值与成交流水，未接入即 503；旧的 sharpe/win_rate 断言已作废。"""
    res = fetch_json("/api/portfolio/analysis", headers=auth_headers, expect_status=503)
    assert res["status"] == "unavailable"
    assert res["capability"] == "portfolio.analysis"


def test_live_watchlist_is_sourced_or_empty(auth_headers):
    res = fetch_json("/api/watchlist?active_code=300750", headers=auth_headers)
    assert res["status"] in ("empty", "success")
    assert res["source"] == "config/stock_pools.yaml"
    codes = [s["code"] for s in res["stocks"]]
    assert len(codes) == len(set(codes)), f"自选列表出现重复代码：{codes}"
    detail = res["active_stock_detail"]
    if detail is not None:
        assert detail["code"] == "300750"
        assert detail["price"] > 0
        # 无真实来源的画像口径必须为空，由前端显示 '--'
        for unsourced in ("industry", "concepts", "pb", "high_52w", "low_52w",
                          "ma", "capital_flow", "northbound", "main_control"):
            assert detail[unsourced] is None, f"{unsourced} 没有数据源却拿到了值"


def test_live_watchlist_carries_no_demo_profile(auth_headers):
    status, text = request_raw("/api/watchlist?active_code=300750", headers=auth_headers)
    assert status == 200
    assert_no_fabricated_snapshot(text, "/api/watchlist")


def test_live_monitor_reports_not_running(auth_headers):
    """盘中事件采集尚未接入，必须如实 not_running + 空数组，而不是恒真 is_monitoring。"""
    res = fetch_json("/api/monitor/stream", headers=auth_headers)
    assert res["status"] == "not_running"
    assert res["is_monitoring"] is False
    assert res["events"] == []
    assert res["strategies"] == []


# ------------------------------------------------------------------ 匿名必须被拒
def test_api_rejects_anonymous_requests():
    """反向门禁：不带任何凭证访问受保护接口必须 401，防止鉴权被"临时关掉"后无人察觉。"""
    for endpoint in ("/api", "/api/market/indices", "/api/watchlist", "/api/portfolio/overview"):
        status, _ = request_raw(endpoint)
        assert status == 401, f"{endpoint} 匿名访问竟然拿到了 {status}，fail-closed 已被破坏"


# ------------------------------------------------------------------ 会话与流式
def test_live_chat_sessions(auth_headers):
    create_res = fetch_json(
        "/api/chat/sessions", headers=auth_headers, method="POST",
        payload={"title": "E2E联调会话", "model": "mock"},
    )
    session_id = create_res["session_id"]
    assert session_id.startswith("sess_")

    list_res = fetch_json("/api/chat/sessions", headers=auth_headers)
    assert any(s["session_id"] == session_id for s in list_res["sessions"])


def test_live_chat_stream_sse(auth_headers):
    url = f"{BASE_URL}/api/chat/completions/stream"
    payload = {
        "message": "请对宁德时代 300750 进行量化诊断并计算保本卖出价",
        "model": "mock",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**auth_headers, "Content-Type": "application/json"},
        method="POST",
    )
    events = []
    current_event = None
    with urllib.request.urlopen(req, timeout=30) as response:
        assert response.status == 200
        for line in response:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("event:"):
                current_event = line_str[6:].strip()
            elif line_str.startswith("data:"):
                raw_data = line_str[5:].strip()
                if raw_data:
                    try:
                        ev = json.loads(raw_data)
                        ev["event_type"] = current_event
                        events.append(ev)
                    except Exception:
                        pass

    assert events, "SSE 流未返回任何事件"
    event_types = {e.get("event_type") for e in events}
    assert "thought" in event_types
    assert "done" in event_types or "content_delta" in event_types
