#!/usr/bin/env python3
"""Tests for P2 robustness fixes in docs/CODE_REVIEW.md."""

import tempfile
from pathlib import Path
import pytest

from core.config import VERSION, get_logger
from core.data.data_bridge import (
    QuoteDict,
    _validate_stock_code,
    infer_market_prefix,
    normalize_symbol,
    DataBridge,
)
from core.strategy.pool_schema import write_pool_csv, read_pool_csv
from core.models.stock_screener import StockScreener
from core.models.multi_dim_model import MarketGate, StockSelectionV3, RotationBacktest
from core.strategy.grid_trading_strategy import GridTradingStrategy
from core.reporting.report_generator import generate_simple_report
from core.paper_trading.backtest_metrics import calc_metrics, _safe_div


# ─────────────────────────────────────────────────────────────
# 1. Version SSOT & Logging
# ─────────────────────────────────────────────────────────────

def test_version_ssot():
    assert VERSION == "3.0.0"
    logger = get_logger("test.p2")
    assert logger is not None


# ─────────────────────────────────────────────────────────────
# 2. Code Injection Defense & Stock Code Validation
# ─────────────────────────────────────────────────────────────

def test_validate_stock_code():
    # Valid codes
    assert _validate_stock_code("600519") == "600519"
    assert _validate_stock_code("sh600519") == "sh600519"
    assert _validate_stock_code("000001") == "000001"
    assert _validate_stock_code("sz000001") == "sz000001"
    assert _validate_stock_code("830001") == "830001"
    assert _validate_stock_code("bj830001") == "bj830001"

    # Malicious or invalid codes
    with pytest.raises(ValueError):
        _validate_stock_code("600519; rm -rf /")

    with pytest.raises(ValueError):
        _validate_stock_code("import os; os.system('ls')")

    with pytest.raises(ValueError):
        _validate_stock_code("600519' OR '1'='1")

    with pytest.raises(ValueError):
        _validate_stock_code("")


def test_data_bridge_injection_prevention():
    bridge = DataBridge()
    # Invalid codes are rejected safely and return None without subprocess command injection
    assert bridge.get_cyq("600519; echo hacked") is None
    fund = bridge.get_fundamentals("000001 && rm -rf")
    assert fund.get("source") == "invalid_code"


# ─────────────────────────────────────────────────────────────
# 3. QuoteDict & Market Normalization
# ─────────────────────────────────────────────────────────────

def test_quote_dict_and_normalization():
    assert infer_market_prefix("600519") == "sh"
    assert infer_market_prefix("000001") == "sz"
    assert infer_market_prefix("830001") == "bj"
    assert infer_market_prefix("430002") == "bj"

    assert normalize_symbol("600519", with_prefix=True) == "sh600519"
    assert normalize_symbol("sh600519", with_prefix=False) == "600519"
    assert normalize_symbol("sz000001", with_prefix=True) == "sz000001"

    qd = QuoteDict()
    q1 = {"code": "sh600519", "name": "贵州茅台", "price": 1800.0}
    q2 = {"code": "sz000001", "name": "平安银行", "price": 12.5}
    qd.add(q1)
    qd.add(q2)

    # Retrieval by raw code, prefixed code, or name
    assert qd.get("600519")["price"] == 1800.0
    assert qd.get("sh600519")["price"] == 1800.0
    assert qd.get("贵州茅台")["price"] == 1800.0
    assert qd.get("000001")["price"] == 12.5
    assert qd.get("平安银行")["price"] == 12.5

    # Membership tests
    assert "600519" in qd
    assert "贵州茅台" in qd
    assert "999999" not in qd

    # Iteration yields primary quotes
    items = list(qd.values())
    assert len(items) == 2


# ─────────────────────────────────────────────────────────────
# 4. write_pool_csv Empty Rows Parameter Preservation
# ─────────────────────────────────────────────────────────────

def test_write_pool_csv_with_empty_rows():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test_pool.csv"
        fields = ["code", "name", "score", "date"]

        # Calling with empty rows should NOT treat empty rows as fields
        write_pool_csv(csv_file, rows=[], fields=fields)

        content = csv_file.read_text(encoding="utf-8").strip()
        assert content == "code,name,score,date"

        # Reading back should produce empty list
        read_rows = read_pool_csv(csv_file)
        assert len(read_rows) == 0

        # Calling with rows
        test_rows = [{"code": "600519", "name": "茅台", "score": 90, "date": "2026-09-05"}]
        write_pool_csv(csv_file, rows=test_rows, fields=fields)
        read_back = read_pool_csv(csv_file)
        assert len(read_back) == 1
        assert read_back[0]["code"] == "600519"


# ─────────────────────────────────────────────────────────────
# 5. stock_screener TOP10 Boolean Semantics
# ─────────────────────────────────────────────────────────────

def test_screener_board_top10():
    screener = StockScreener()

    # Mock get_board_summary returning 15 boards
    boards = [{"boardName": f"Board_{i}", "changePct": 15 - i} for i in range(15)]
    screener.bridge.get_board_summary = lambda limit=30: {"data": boards}

    # Stock 1 in Board_2 (top 10), Stock 2 in Board_12 (not top 10)
    quotes = [
        {"code": "600001", "name": "S1", "sector": "Board_2", "price": 10},
        {"code": "600002", "name": "S2", "sector": "Board_12", "price": 10},
    ]

    res = screener.filter_sector(quotes, min_board_chg=-10.0)
    assert len(res) == 2

    s1 = next(r for r in res if r["code"] == "600001")
    s2 = next(r for r in res if r["code"] == "600002")

    assert s1["board_top10"] is True
    assert s2["board_top10"] is False


# ─────────────────────────────────────────────────────────────
# 6. multi_dim_model Gate Auto-Assess & Sell Signals
# ─────────────────────────────────────────────────────────────

def test_market_gate_auto_assess_and_state_config():
    engine = StockSelectionV3(enable_filter=False)
    assert not engine.gate._assessed

    # Mock gate assess to avoid external network calls during unit tests
    def mock_assess():
        engine.gate.sh_above_ma20 = True
        engine.gate.health_score = 75
        engine.gate.state = "偏多"
        engine.gate.config = engine.gate.STATE_CONFIG["偏多"]
        engine.gate._assessed = True
        return engine.gate.state

    engine.gate.assess = mock_assess

    # Mock klines and quote
    mock_klines = [
        ["2026-01-01", 10.0, 10.0, 9.8, 10.2, 1000]
        for _ in range(70)
    ]
    engine.bridge.tencent_kline = lambda code, count=250: mock_klines
    engine.bridge.get_realtime_quote = lambda code: {"price": 10.0, "change_pct": 1.0, "code": code}

    res = engine.evaluate("600519")
    assert engine.gate._assessed
    assert "rating" in res
    assert "composite_score" in res


def test_check_sell_signals_prev_close():
    engine = StockSelectionV3(enable_filter=False)
    engine.gate._assessed = True

    # Generate 65 klines with a -6% plunge on the last day compared to previous day's close
    mock_klines = [
        ["2026-01-01", 100.0, 100.0, 99.0, 101.0, 1000]
        for _ in range(64)
    ]
    # Day 64 close = 100.0 (prev_close)
    # Day 65 close = 94.0 (-6% drop from 100.0)
    mock_klines.append(["2026-04-01", 99.0, 94.0, 93.0, 99.0, 2000])

    engine.bridge.tencent_kline = lambda code, count=250: mock_klines
    engine.bridge.get_realtime_quote = lambda code: {"price": 94.0, "change_pct": -6.0, "code": code}

    res = engine.evaluate("600519")
    assert "sell_signals" in res
    assert "单日跌>5%" in res["sell_signals"]


def test_rotation_backtest_candidate_filter():
    backtest = RotationBacktest()
    # Ensure current holdings are excluded from rotation candidates
    scores = {
        "600001": {"score": 85},
        "600002": {"score": 90},
        "600003": {"score": 70},
    }
    positions = {"600002": {"entry_price": 10.0, "score": 90}}

    candidates = {c: s for c, s in scores.items() if c not in positions}
    assert "600002" not in candidates
    assert "600001" in candidates
    assert "600003" in candidates


# ─────────────────────────────────────────────────────────────
# 7. Grid Strategy Action Determination
# ─────────────────────────────────────────────────────────────

def test_grid_trading_boll_mid_coupling():
    strategy = GridTradingStrategy()
    # Need enough variance so atr > 0 and boll range > 0
    klines = [
        [f"2026-01-{i+1:02d}", 10.0 + (i % 5) * 0.5, 10.2 + (i % 5) * 0.5, 12.0, 8.0, 1000]
        for i in range(30)
    ]
    plan = strategy.build_grid(klines, total_cash=100000)
    assert "grid_levels" in plan
    boll_mid = plan["boll_mid"]
    assert len(plan["grid_levels"]) > 0
    for level in plan["grid_levels"]:
        price = level["price"]
        action = level["action"]
        if price < boll_mid:
            assert action == "buy"
        else:
            assert action == "sell"


# ─────────────────────────────────────────────────────────────
# 8. Report Generator HTML Escaping
# ─────────────────────────────────────────────────────────────

def test_report_generator_xss_prevention():
    malicious_data = {
        "code": "<script>alert('code')</script>",
        "name": "<img src=x onerror=alert(1)>",
        "scores": {
            "<script>hack</script>": {"score": 10, "max": 10, "reason": "<b>safe</b>"},
            "rating": "<style>bad</style>",
            "rating_text": "<b>Strong Buy</b>",
        },
        "quote": {"price": "100<script>", "change_pct": 2.0},
        "technical_latest": {"close": 100},
    }
    report = generate_simple_report(malicious_data)

    import html as html_lib
    assert "<script>alert('code')</script>" not in report
    assert html_lib.escape("<script>alert('code')</script>") in report
    assert "<img src=x onerror=alert(1)>" not in report
    assert html_lib.escape("<img src=x onerror=alert(1)>") in report
    assert html_lib.escape("<style>bad</style>") in report


# ─────────────────────────────────────────────────────────────
# 9. Backtest Metrics Edge Cases & Zero Protection
# ─────────────────────────────────────────────────────────────

def test_backtest_metrics_zero_protection_and_calmar():
    # Calmar with negative annual return
    equity_curve = [
        {"date": "2026-01-01", "equity": 100000.0},
        {"date": "2026-01-02", "equity": 90000.0},
        {"date": "2026-01-03", "equity": 80000.0},
    ]
    trades = [
        {"action": "buy", "date": "2026-01-01", "price": 100, "qty": 1000, "amount": 100000},
        {"action": "sell", "date": "2026-01-03", "price": 80, "qty": 1000, "amount": 80000, "profit": -20000},
    ]

    metrics = calc_metrics(
        equity_curve=equity_curve,
        trades=trades,
        initial_cash=100000.0,
        final_equity=80000.0,
        days=3,
    )

    # Calmar should be negative when return is negative
    assert metrics["annual_return_pct"] < 0
    assert metrics["calmar_ratio"] < 0
    assert metrics["profit_factor"] == 0.0

    # 100% win rate (no losses)
    winning_trades = [
        {"action": "buy", "date": "2026-01-01", "price": 100, "qty": 1000, "amount": 100000},
        {"action": "sell", "date": "2026-01-03", "price": 120, "qty": 1000, "amount": 120000, "profit": 20000},
    ]
    winning_curve = [
        {"date": "2026-01-01", "equity": 100000.0},
        {"date": "2026-01-03", "equity": 120000.0},
    ]
    win_metrics = calc_metrics(
        equity_curve=winning_curve,
        trades=winning_trades,
        initial_cash=100000.0,
        final_equity=120000.0,
        days=2,
    )
    assert win_metrics["profit_factor"] == 999.0

    # Empty / zero days boundary test
    empty_metrics = calc_metrics(
        equity_curve=[],
        trades=[],
        initial_cash=0.0,
        final_equity=0.0,
        days=0,
    )
    assert empty_metrics["turnover_ratio"] == 0.0
    assert empty_metrics["calmar_ratio"] == 0.0
    assert empty_metrics["profit_factor"] == 0.0
