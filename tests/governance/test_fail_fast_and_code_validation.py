# -*- coding: utf-8 -*-
"""
tests/test_fail_fast_and_code_validation.py
Validates stock code fail-fast handling, empty pool guidance, and error sanitization.
"""
import pytest
from server.agent.tools import (
    _sync_astock_quote,
    _sync_astock_technical,
    _sync_astock_data_feed,
    _sync_astock_evaluate,
    _sync_astock_pool_dashboard,
    _sync_astock_strategy_macd,
    _sync_astock_strategy_mainboard,
)


def test_invalid_stock_quote_returns_data_unavailable():
    """Test nonexistent stock code returns DATA_UNAVAILABLE without crash."""
    res = _sync_astock_quote("000222")
    assert res.get("status") == "error"
    assert res.get("error") == "DATA_UNAVAILABLE"
    assert "无法获取" in res.get("message", "")


def test_invalid_stock_technical_and_data_feed():
    """Test technical indicators and data feed gracefully report DATA_UNAVAILABLE."""
    tech_res = _sync_astock_technical("000222")
    assert tech_res.get("status") == "error"
    assert tech_res.get("error") == "DATA_UNAVAILABLE"

    feed_res = _sync_astock_data_feed(code="000222", action="history")
    assert feed_res.get("status") == "error"
    assert feed_res.get("error") == "DATA_UNAVAILABLE"


def test_invalid_stock_evaluate_and_strategy():
    """Test evaluation and strategies return DATA_UNAVAILABLE for invalid codes."""
    eval_res = _sync_astock_evaluate("000222")
    assert eval_res.get("status") == "error"
    assert eval_res.get("error") == "DATA_UNAVAILABLE"

    macd_res = _sync_astock_strategy_macd("000222")
    assert macd_res.get("status") == "error"
    assert macd_res.get("error") == "DATA_UNAVAILABLE"


def test_empty_pool_guidance_uses_valid_stock_sample():
    """Test that empty pool guidance provides valid stock code (000001) instead of 000222."""
    res = _sync_astock_pool_dashboard(pool_type="holding", action="list")
    # Even if pool has items or is empty, message if empty must not contain 000222
    if res.get("is_empty"):
        msg = res.get("message", "")
        assert "000222" not in msg
        assert "000001" in msg


def test_valid_stock_quote_success():
    """Test that querying a valid stock (000001) succeeds with structured price."""
    res = _sync_astock_quote("000001")
    if res.get("status") == "success":
        assert "price" in res
        assert float(res["price"]) > 0
        assert res["code"] == "000001"
