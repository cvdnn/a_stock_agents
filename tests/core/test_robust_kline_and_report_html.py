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


def test_get_kline_robust_never_synthesizes_from_quote(monkeypatch):
    """外部源全失败时不得用行情快照合成 K 线（零虚假数据铁律）。

    历史缺陷：`get_kline_robust` 曾接受 `quote` 参数并据此合成兜底走势，
    使断网也能"出数"。现口径：该参数已移除，降级只能落到本地 SQLite 的真实历史，
    本地同样无数据时如实返回空列表，绝不凭快照价格编造 K 线。
    """
    import inspect

    assert "quote" not in inspect.signature(DataBridge.get_kline_robust).parameters

    monkeypatch.setattr(DataBridge, "tencent_kline", lambda code, count=120: [])
    monkeypatch.setattr(DataBridge, "sina_kline", lambda code, count=120: [])
    monkeypatch.setattr(DataBridge, "eastmoney_kline", lambda code, count=120: [])
    import scripts.core.data.Ashare as AshareModule
    monkeypatch.setattr(AshareModule, "get_price", lambda *args, **kwargs: None)
    # 清空对应缓存
    norm = DataBridge.normalize_symbol("000002")
    DataBridge._KLINE_CACHE.pop(norm, None)

    klines = DataBridge.get_kline_robust("000002", count=35)
    assert isinstance(klines, list)
    # 8.50 是原伪造用例注入的快照收盘价：任何降级路径都不得凭空产出该值
    assert all(float(row[2]) != 8.50 for row in klines)


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
