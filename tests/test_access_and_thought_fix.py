# -*- coding: utf-8 -*-
import pytest
from core.data.data_bridge import DataBridge
from core.config import infer_market_prefix, normalize_symbol
from server.agent.tools import _sync_astock_data_feed, _sync_astock_technical


def test_index_market_prefix_and_normalize():
    assert infer_market_prefix("000300") == "sh"
    assert infer_market_prefix("000905") == "sh"
    assert infer_market_prefix("000852") == "sh"
    assert infer_market_prefix("000016") == "sh"
    assert infer_market_prefix("399001") == "sz"
    assert infer_market_prefix("399006") == "sz"
    assert infer_market_prefix("999999") == "sh"
    assert infer_market_prefix("sh.000001") == "sh"
    assert infer_market_prefix("000001.SZ") == "sz"

    assert normalize_symbol("000300") == "sh000300"
    assert normalize_symbol("999999") == "sh000001"
    assert normalize_symbol("上证指数") == "sh000001"
    assert normalize_symbol("sh.000001") == "sh000001"
    assert normalize_symbol("000001.SZ") == "sz000001"


def test_index_quote_and_kline():
    bridge = DataBridge()
    # Test index quote
    q = bridge.get_realtime_quote("sh000001")
    assert q is not None
    assert "上证指数" in q.get("name", "")
    assert q.get("price", 0) > 0

    q300 = bridge.get_realtime_quote("000300")
    assert q300 is not None
    assert "300" in q300.get("name", "") or "沪深" in q300.get("name", "")
    assert q300.get("price", 0) > 0

    # Test index kline (day instead of qfqday)
    klines_sh = bridge.tencent_kline("sh000001", count=30)
    assert len(klines_sh) >= 15

    klines_cyb = bridge.tencent_kline("399006", count=30)
    assert len(klines_cyb) >= 15


def test_sync_astock_data_feed_history_and_tech():
    # Test action="history"
    feed_res = _sync_astock_data_feed(code="399001", action="history", count=20)
    assert feed_res.get("count", 0) >= 15
    assert "klines" in feed_res

    # Test technical indicators on index
    tech_res = _sync_astock_technical(code="sh000001", count=60)
    assert "error" not in tech_res
    assert tech_res.get("latest_close", 0) > 0
    assert "ma" in tech_res and "ma5" in tech_res["ma"]
    assert "macd" in tech_res and "dif" in tech_res["macd"]
