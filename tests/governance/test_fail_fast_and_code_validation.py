# -*- coding: utf-8 -*-
"""
Fail-fast 契约：上游取不到真实数据时，各工具必须显式报 DATA_UNAVAILABLE，
严禁回落到合成价格、默认值或"看起来成功"的空结果（项目《零虚假数据原则》）。

原实现直接对 000222 这类不存在代码打真实网络，让 DataBridge 逐级重试腾讯/新浪/东财，
4 个用例合计 ~6.7s 且结果随网络状况漂移；把"上游无数据"这一前提桩住之后，
同一契约可以离线、毫秒级、且必然地验证。
"""
import pytest
from core.data.data_bridge import DataBridge
from server.agent.tools import (
    _sync_astock_data_feed,
    _sync_astock_evaluate,
    _sync_astock_pool_dashboard,
    _sync_astock_quote,
    _sync_astock_strategy_macd,
    _sync_astock_technical,
)

NO_DATA_CODE = "000222"


@pytest.fixture()
def upstream_silent(monkeypatch):
    """让所有上游渠道一律取不到数据（等价于标的不存在 / 已退市 / 全渠道断网）。"""
    monkeypatch.setattr(DataBridge, "get_realtime_quote", lambda self, code, **kw: {})
    monkeypatch.setattr(DataBridge, "get_kline_robust", staticmethod(lambda code, **kw: []))


@pytest.mark.parametrize("tool_name,call", [
    ("quote", lambda: _sync_astock_quote(NO_DATA_CODE)),
    ("technical", lambda: _sync_astock_technical(NO_DATA_CODE)),
    ("data_feed.history", lambda: _sync_astock_data_feed(code=NO_DATA_CODE, action="history")),
    ("evaluate", lambda: _sync_astock_evaluate(NO_DATA_CODE)),
    ("strategy_macd", lambda: _sync_astock_strategy_macd(NO_DATA_CODE)),
])
def test_tool_reports_data_unavailable_when_upstream_has_nothing(tool_name, call, upstream_silent):
    """无数据必须报 error/DATA_UNAVAILABLE，且 message 点名代码——不得伪造任何数值。"""
    res = call()
    assert res.get("status") == "error", f"{tool_name} 在无数据时未 fail-fast: {res}"
    assert res.get("error") == "DATA_UNAVAILABLE", f"{tool_name} 错误码不标准: {res}"
    assert res.get("code") == NO_DATA_CODE
    assert NO_DATA_CODE in res.get("message", "")


def test_empty_pool_guidance_never_suggests_invalid_sample_code(isolated_user_pools):
    """空池引导必须给出可登记的合法示例，且严禁出现不存在的 000222。

    原实现写作 `if res.get("is_empty"): ...`，当开发者本机池非空时整个断言被跳过 ——
    一个永远不会失败的用例。此处把股池显式隔离为空，让断言必然执行。
    """
    res = _sync_astock_pool_dashboard(pool_type="holding", action="list")
    assert res.get("is_empty") is True, f"隔离后持仓池应为空: {res}"
    msg = res.get("message", "")
    assert "000222" not in msg
    assert "000001" in msg
    assert "股票:股数@成本价" in msg


def test_quote_success_shape_is_coerced_to_floats(monkeypatch):
    """取到真实报价时，价格字段必须是 float，供下游精算与比较直接使用。

    原用例写作 `if res.get("status") == "success": ...`，网络抖动即整体空跑。
    这里用确定桩替代，断言必然执行。
    """
    monkeypatch.setattr(
        DataBridge, "get_realtime_quote",
        lambda self, code, **kw: {
            "code": "000001", "name": "平安银行", "price": "11.52", "change_pct": "1.2",
            "high": "11.80", "low": "11.30", "open": "11.40", "prev_close": "11.38",
        },
    )
    res = _sync_astock_quote("000001")
    assert res["status"] == "success"
    assert res["code"] == "000001"
    assert res["price"] == 11.52 and isinstance(res["price"], float)
    assert res["change_pct"] == pytest.approx(1.2)
    assert res["prev_close"] == pytest.approx(11.38)


def test_quote_rejects_priceless_payload_as_unavailable(monkeypatch):
    """上游返回了对象但没有 price，等同无数据，严禁把 0.0 当现价交付下游。"""
    monkeypatch.setattr(
        DataBridge, "get_realtime_quote",
        lambda self, code, **kw: {"code": code, "name": "停牌股", "price": 0},
    )
    res = _sync_astock_quote("000001")
    assert res.get("status") == "error"
    assert res.get("error") == "DATA_UNAVAILABLE"
