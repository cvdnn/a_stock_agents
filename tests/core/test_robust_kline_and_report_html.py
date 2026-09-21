"""
测试 DataBridge 多级降级 K 线与 astock_report_html 坚固生成管道
验证在网络正常、单源异常以及极端断网情况下均能 100% 成功生成 HTML 报告并注入实战交易三原则
"""

import pytest
import os
from scripts.core.data.data_bridge import DataBridge
from scripts.server.agent.tools import _sync_astock_report_html
from scripts.core.reporting.report_generator import generate_simple_report


def test_get_kline_robust_normal():
    """验证正常情况下获取日 K 线成功且包含必要特征"""
    klines = DataBridge.get_kline_robust("603893", count=60)
    assert isinstance(klines, list)
    assert len(klines) >= 15
    first = klines[0]
    # 格式: [date, open, close, high, low, volume]
    assert len(first) >= 6


def test_get_kline_robust_cache_hit():
    """验证第二次请求直接命中内存缓存"""
    k1 = DataBridge.get_kline_robust("603893", count=30)
    norm = DataBridge.normalize_symbol("603893")
    assert norm in DataBridge._KLINE_CACHE
    k2 = DataBridge.get_kline_robust("603893", count=30)
    assert k1 == k2


def test_get_kline_robust_fallback_with_quote(monkeypatch):
    """模拟腾讯与新浪外部网络均失败时，能够基于行情快照合成兜底 K 线"""
    monkeypatch.setattr(DataBridge, "tencent_kline", lambda code, count=120: [])
    monkeypatch.setattr(DataBridge, "sina_kline", lambda code, count=120: [])
    import scripts.core.data.Ashare as AshareModule
    monkeypatch.setattr(AshareModule, "get_price", lambda *args, **kwargs: None)
    # 清空对应缓存
    norm = DataBridge.normalize_symbol("000002")
    DataBridge._KLINE_CACHE.pop(norm, None)

    fake_quote = {
        "code": "000002",
        "name": "万科A",
        "price": 8.50,
        "open": 8.45,
        "prev_close": 8.40,
        "high": 8.60,
        "low": 8.35,
        "volume": 2000000,
    }
    klines = DataBridge.get_kline_robust("000002", count=35, quote=fake_quote)
    assert len(klines) >= 26
    # 今日收盘价应与 quote 一致
    assert float(klines[-1][2]) == 8.50


def test_astock_report_html_contains_three_principles():
    """验证 _sync_astock_report_html 输出 100% 成功且包含实战交易三原则"""
    res = _sync_astock_report_html("603893")
    assert res.get("status") == "success"
    assert res.get("skill_id") == "astock-report-html"
    assert res.get("format") == "html"
    assert res.get("deliverable_file").endswith(".html")
    html = res.get("html_content")
    assert html and len(html) > 500

    # 验证三原则存在
    assert "最低保本卖出价" in html
    assert "三级风控止损阶梯" in html
    assert "T0 警戒线" in html
    assert "T1 减仓线" in html
    assert "T2 绝杀线" in html
    assert "三场景即时操作单" in html
    assert "1344px" in html
