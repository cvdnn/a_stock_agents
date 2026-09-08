import json
import urllib.request
import urllib.parse
import pytest

BASE_URL = "http://127.0.0.1:6300"

def fetch_json(endpoint: str, method: str = "GET", payload: dict = None):
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))

def test_live_health():
    res = fetch_json("/api/health")
    assert res["status"] == "ok"
    assert res["db_connected"] is True

def test_live_main_web_ui_root():
    """验证主 Web 界面: http://127.0.0.1:6300"""
    url = f"{BASE_URL}/"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        html = response.read().decode("utf-8")
        assert "AI量化投资助手" in html
        assert "ovTotalAssets" in html
        assert "js/api.js" in html

def test_live_api_gateway_root():
    """验证对外 API 接口导航: http://127.0.0.1:6300/api"""
    res = fetch_json("/api")
    assert res["status"] == "online"
    assert "endpoints" in res
    assert res["endpoints"]["health"] == "/api/health"
    assert res["endpoints"]["chat_stream"] == "/api/chat/completions/stream"

def test_live_static_ui():
    url = f"{BASE_URL}/ui/"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=5) as response:
        assert response.status == 200
        html = response.read().decode("utf-8")
        assert "AI量化投资助手" in html or "A-Stock Agents" in html
        assert "ovTotalAssets" in html
        assert "mktShPrice" in html
        assert "watchHeroPrice" in html
        assert "retAccumReturnVal" in html
        assert "js/api.js" in html

def test_live_market_indices():
    res = fetch_json("/api/market/indices")
    assert "indices" in res
    assert len(res["indices"]) >= 4
    sh = next(i for i in res["indices"] if i["code"] == "000001")
    assert sh["price"] > 3000
    assert len(sh["sparkline"]) > 0

def test_live_market_sentiment():
    res = fetch_json("/api/market/sentiment")
    assert res["score"] > 0
    assert "limit_up_count" in res
    assert "total_turnover" in res
    assert len(res["sectors"]) > 0

def test_live_market_kline():
    res = fetch_json("/api/market/kline?code=000001&period=day")
    assert len(res["klines"]) > 0
    assert res["ma5"] > 0
    assert res["ma10"] > 0
    assert res["ma20"] > 0

def test_live_market_ranks():
    res = fetch_json("/api/market/ranks")
    assert len(res["gainers"]) > 0
    assert len(res["losers"]) > 0
    assert len(res["northbound"]) > 0
    assert len(res["sectors_rank"]) > 0
    assert len(res["news"]) > 0
    assert len(res["hot_concepts"]) > 0

def test_live_portfolio_overview():
    res = fetch_json("/api/portfolio/overview")
    assert "total_assets" in res
    assert "position_market_value" in res
    assert "available_cash" in res
    assert len(res["donut_data"]) > 0
    assert len(res["holdings"]) > 0

def test_live_portfolio_analysis():
    res = fetch_json("/api/portfolio/analysis")
    assert res["sharpe_ratio"] > 0
    assert res["win_rate"] > 50
    assert len(res["attributions"]) > 0
    assert len(res["positions"]) > 0
    # Verify ceil breakeven rule in positions
    for pos in res["positions"]:
        assert pos["breakeven_price"] >= pos["cost"]

def test_live_watchlist():
    res = fetch_json("/api/watchlist?active_code=300750")
    assert len(res["stocks"]) > 0
    assert "active_stock_detail" in res
    stock_detail = res["active_stock_detail"]
    assert stock_detail["code"] == "300750"
    assert stock_detail["price"] > 0
    assert "capital_flow" in stock_detail
    assert "main_control" in stock_detail

def test_live_monitor_stream():
    res = fetch_json("/api/monitor/stream")
    assert res["is_monitoring"] is True
    assert len(res["events"]) > 0

def test_live_chat_sessions():
    # 1. Create Session
    create_res = fetch_json("/api/chat/sessions", method="POST", payload={"title": "E2E联调会话", "model": "mock"})
    session_id = create_res["session_id"]
    assert session_id.startswith("sess_")
    
    # 2. List Sessions
    list_res = fetch_json("/api/chat/sessions")
    assert any(s["session_id"] == session_id for s in list_res["sessions"])

def test_live_chat_stream_sse():
    # Test SSE stream endpoint
    url = f"{BASE_URL}/api/chat/completions/stream"
    payload = {
        "message": "请对宁德时代 300750 进行量化诊断并计算保本卖出价",
        "model": "mock"
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    events = []
    current_event = None
    with urllib.request.urlopen(req, timeout=10) as response:
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

    assert len(events) > 0
    event_types = {e.get("event_type") for e in events}
    assert "thought" in event_types
    assert "done" in event_types or "content_delta" in event_types
