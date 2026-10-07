# -*- coding: utf-8 -*-
"""
tests/server/test_debate_and_quant_tools.py
校验 astock_agent_debate 与 astock_quant_engine 真实可执行，且绝不返回假的 "unavailable"。

原实现让 3 个用例各自完整跑一遍 7 分析师辩论流水线（合计 ~6.8s），其中"无效代码"用例
还要等 DataBridge 逐级重试腾讯/新浪/东财超时，结果随网络状况漂移。此处改为：
用一份 canned 行情喂**真实**辩论装配逻辑（分析师名册、评分、风险动作仍是被测主体），
只跑一次并复用；无数据分支用显式空桩触发，离线、确定、毫秒级。
"""
import pytest
from core.data.data_bridge import DataBridge
from server.agent.tools import (
    _sync_astock_agent_debate,
    _sync_astock_quant_engine,
    execute_tool,
)

CANDIDATE_CODE = "600519"
DEAD_CODE = "000222"


def _canned_quote(code: str) -> dict:
    return {
        "code": code, "name": "贵州茅台", "price": 1425.50, "change_pct": 1.24,
        "high": 1438.00, "low": 1408.60, "open": 1412.00, "prev_close": 1408.10,
        "volume": 31500, "amount": 4.48e9, "turnover_pct": 0.25, "pe": 22.6,
        "circulating_market_cap": 1.79e12, "total_market_cap": 1.79e12,
    }


def _canned_klines(count: int = 120) -> list:
    """构造 120 个交易日的稳定上升序列，保证指标层不会因样本不足而降级。"""
    from datetime import date, timedelta

    start = date(2026, 4, 1)
    rows = []
    for i in range(count):
        close = 1380.0 + i * 0.4
        rows.append([
            (start + timedelta(days=i)).isoformat(),
            f"{close - 1:.2f}", f"{close:.2f}", f"{close + 6:.2f}", f"{close - 8:.2f}",
            "31500", "448000.0",
        ])
    return rows


@pytest.fixture(scope="module")
def debate_result():
    """一次真实辩论装配，供"结构完整"与"分发链路"两处断言复用。"""
    original_quote, original_kline = DataBridge.get_realtime_quote, DataBridge.tencent_kline
    DataBridge.get_realtime_quote = lambda self, code, **kw: _canned_quote(code)
    DataBridge.tencent_kline = staticmethod(lambda code, count=120, **kw: _canned_klines(count))
    try:
        yield _sync_astock_agent_debate(code=CANDIDATE_CODE)
    finally:
        DataBridge.get_realtime_quote = original_quote
        DataBridge.tencent_kline = original_kline


def test_agent_debate_returns_seven_analysts_and_breakeven(debate_result):
    """辩论必须产出 7 位分析师、共识结论与可用的风险动作（含正数保本价）。"""
    assert debate_result.get("status") == "success", debate_result
    assert "consensus" in debate_result
    assert len(debate_result["analysts"]) == 7
    assert debate_result["risk_action"].get("breakeven_price", 0) > 0


def test_agent_debate_reports_unavailable_for_dead_code(debate_result, monkeypatch):
    """标的不存在时必须 fail-closed 报 DATA_UNAVAILABLE，不得用假数据凑出一份辩论。"""
    monkeypatch.setattr(DataBridge, "get_realtime_quote", lambda self, code, **kw: {})
    monkeypatch.setattr(DataBridge, "tencent_kline", staticmethod(lambda code, **kw: []))
    res = _sync_astock_agent_debate(code=DEAD_CODE)
    assert res.get("status") == "error"
    assert res.get("error") == "DATA_UNAVAILABLE"


def test_quant_engine_macro_target_weight():
    """省略 code 时量化引擎给出组合级目标仓位，不得伪造个股结论。"""
    res = _sync_astock_quant_engine(action="pipeline")
    assert res.get("status") == "success"
    assert res.get("portfolio_target_weight", 0) > 0
    assert "standard_board_cap" in res


def test_quant_engine_stock_allocation_board_cap():
    """个股分支必须给出建仓股数与板块仓位上限（主板 15%）。"""
    res = _sync_astock_quant_engine(action="pipeline", code=CANDIDATE_CODE)
    assert res.get("status") == "success"
    alloc = res["allocation"]
    assert alloc["shares"] >= 0
    assert alloc["board_cap"] == 0.15


@pytest.mark.asyncio
async def test_execute_tool_dispatches_debate_and_quant(monkeypatch):
    """execute_tool 必须正确路由到两个技能并回填 skill_id。

    路由与被测流水线是两个独立契约：此前本用例又完整跑了一遍辩论（+2.4s），
    只为一模一样地再断言一次 `status == success`。这里把 TOOL_MAP 条目换成 canned
    handler，用例回归它本来的职责——分发链路。注意 `execute_tool` 取的是
    `TOOL_MAP.get(name)` 持有的**函数对象引用**，因此必须 patch 字典本身，
    patch 模块级同名属性是不会生效的。
    """
    import server.agent.tools as tools_module

    def fake_debate(code=None, **kw):
        return {"status": "success", "code": code, "analysts": [], "consensus": {}}

    def fake_quant(action="pipeline", code=None, **kw):
        return {"status": "success", "action": action, "code": code}

    monkeypatch.setitem(tools_module.TOOL_MAP, "astock_agent_debate", fake_debate)
    monkeypatch.setitem(tools_module.TOOL_MAP, "astock_quant_engine", fake_quant)

    res_debate = await execute_tool("astock_agent_debate", {"code": CANDIDATE_CODE})
    assert res_debate["status"] == "success"
    assert res_debate["skill_id"] == "astock_agent_debate"

    res_quant = await execute_tool("astock_quant_engine", {"code": CANDIDATE_CODE})
    assert res_quant["status"] == "success"
    assert res_quant["skill_id"] == "astock_quant_engine"
