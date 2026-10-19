# -*- coding: utf-8 -*-
"""
tests/skills/test_skill_tools_execution.py
End-to-End tools execution verification gate for 1+6 production skills architecture:
1. a-stock-agents (Anchor): 意图识别与踩坑指南 (meta-routing & knowledge-tips)
2. astock-market-data: 实时行情与技术指标 (吸收 astock-data-feed)
3. astock-smart-screener: 动态选股与热点筛选 (吸收 astock-screener-5a, quant-engine)
4. astock-tactical-signals: 战法形态与250日胜率锚 (吸收 macd, tuige, chenxiaoqun, mainboard)
5. astock-deep-diagnose: 穿透体检与多空对抗 (吸收 evaluate, debate, report-html)
6. astock-portfolio-action: 保本价向上进位、三级止损阶梯与空池拦截 (吸收 action-execution, pool-dashboard, pool-audit)
7. astock-paper-backtest: 模拟盘账户与样本外检验 (吸收 trade-paper, model-validation)
"""
from __future__ import annotations

import pytest
from core.execution.tools import execute_tool, extract_risk_card

pytestmark = pytest.mark.core


@pytest.fixture(autouse=True)
def mock_external_network_io(monkeypatch):
    """纯内存完全隔离外部网络，保障毫秒级同步执行。"""
    def fake_quote(self, code: str):
        clean = str(code).replace("sh", "").replace("sz", "").replace("bj", "")
        return {
            "code": clean,
            "name": "贵州茅台" if clean == "600519" else "平安银行",
            "price": 100.0,
            "change_pct": 2.5,
            "open": 98.0,
            "high": 102.0,
            "low": 97.5,
            "prev_close": 97.5,
            "turnover_pct": 1.5,
            "pe": 20.0,
            "time": "2026-10-19 15:00:00",
        }

    def fake_kline(self_or_cls, code: str, count: int = 120):
        res = []
        base = 100.0
        for i in range(1, 61):
            p = base + i * 0.2
            res.append([f"2026-01-{i:02d}", str(p - 0.5), str(p), str(p + 1.0), str(p - 1.0), "50000"])
        return res

    def fake_tencent_quote(codes):
        from core.data.data_bridge import QuoteDict
        qd = QuoteDict()
        for c in codes:
            clean = str(c).replace("sh", "").replace("sz", "").replace("bj", "")
            qd[c] = {
                "code": clean,
                "name": "贵州茅台" if clean == "600519" else "平安银行",
                "price": 100.0,
                "change_pct": 2.5,
                "high": 102.0,
                "low": 97.5,
                "open": 98.0,
                "prev_close": 97.5,
                "turnover_pct": 1.5,
                "pe": 20.0,
                "time": "2026-10-19 15:00:00",
            }
        return qd

    monkeypatch.setattr("core.data.data_bridge.DataBridge.get_realtime_quote", fake_quote)
    monkeypatch.setattr("core.data.data_bridge.DataBridge.get_kline_robust", fake_kline)
    monkeypatch.setattr("core.data.data_bridge.DataBridge.tencent_kline", fake_kline)
    monkeypatch.setattr("core.data.data_bridge.DataBridge.tencent_quote", fake_tencent_quote)

    # 桩化动态选股与漏斗生成
    monkeypatch.setattr(
        "core.strategy.dynamic_universe.DynamicUniverseEngine.generate_dynamic_universe",
        lambda self, mode, size: {"stocks": ["600519", "000001"], "rationale": "动态热点板块轮动"},
    )
    monkeypatch.setattr(
        "core.models.stock_screener.StockScreener.screen",
        lambda self, codes, fetch_cyq=False: {
            "results": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "total_score": 88.0,
                    "price": 100.0,
                    "change_pct": 2.5,
                    "board": "主板",
                    "rating": "A",
                }
            ],
            "total_input": len(codes),
        },
    )


@pytest.mark.asyncio
async def test_exec_anchor_a_stock_agents():
    """验证总控锚点 a-stock-agents 执行（意图路由与实战避坑指南）。"""
    # 1. 意图路由
    res_intent = await execute_tool("a_stock_agents", {"task_description": "请帮我诊断茅台并计算保本价"})
    assert res_intent.get("status") == "success"

    # 2. 知识避坑指南
    res_tips = await execute_tool("a-stock-agents", {"action": "tips"})
    assert res_tips.get("status") == "success"

    # 3. 旧别名透明映射
    res_meta = await execute_tool("astock_meta_routing", {"task_description": "选股"})
    assert res_meta.get("status") == "success"


@pytest.mark.asyncio
async def test_exec_skill_market_data():
    """验证 ① 看盘知势 astock-market-data 真实行情与降级链。"""
    # 1. 新技能名称调用
    res = await execute_tool("astock_market_data", {"code": "600519", "action": "quote"})
    assert res.get("status") == "success"
    assert "price" in res
    assert "change_pct" in res
    assert res.get("code") == "600519"

    # 2. 旧别名 astock_data_feed 调用
    res_legacy = await execute_tool("astock_data_feed", {"code": "000001", "action": "quote"})
    assert res_legacy.get("status") == "success"
    assert res_legacy.get("code") == "000001"


@pytest.mark.asyncio
async def test_exec_skill_smart_screener():
    """验证 ② 选股立池 astock-smart-screener 选股引擎。"""
    res = await execute_tool("astock_smart_screener", {"limit": 3})
    assert res.get("selected_count") >= 1
    assert len(res.get("top_stocks", [])) >= 1

    # 旧别名 astock_screener_5a
    res_legacy = await execute_tool("astock_screener_5a", {"limit": 3})
    assert res_legacy.get("selected_count") >= 1


@pytest.mark.asyncio
async def test_exec_skill_tactical_signals():
    """验证 ③ 择时定买 astock-tactical-signals 战法信号与胜率锚。"""
    # 1. MACD 信号
    res = await execute_tool("astock_tactical_signals", {"code": "600519", "action": "macd"})
    assert res.get("status") == "success"

    # 2. 旧别名 astock_strategy_macd
    res_macd = await execute_tool("astock_strategy_macd", {"code": "600519"})
    assert res_macd.get("code") == "600519"

    # 3. 旧别名 astock_strategy_tuige
    res_tuige = await execute_tool("astock_strategy_tuige", {"code": "600519"})
    assert res_tuige.get("code") == "600519"


@pytest.mark.asyncio
async def test_exec_skill_deep_diagnose():
    """验证 ④ 穿透体检 astock-deep-diagnose 综合评分与多空诊断。"""
    res = await execute_tool("astock_deep_diagnose", {"code": "600519"})
    assert res.get("status") == "success"
    assert "evaluation" in res
    assert "action_plan" in res

    # 旧别名 astock_platform_evaluate
    res_legacy = await execute_tool("astock_platform_evaluate", {"code": "600519"})
    assert res_legacy.get("status") == "success"
    assert "total_score" in res_legacy


@pytest.mark.asyncio
async def test_exec_skill_portfolio_action_and_risk_card():
    """验证 ⑤ 仓位风控 astock-portfolio-action 实战三原则与 RiskCard 提取。"""
    cost = 100.0
    shares = 1000
    res = await execute_tool("astock_portfolio_action", {"code": "600519", "cost": cost, "shares": shares})
    assert "breakeven_price" in res
    # 实战交易三原则核验：
    # 1. 向上取整保本价
    assert res["breakeven_price"] > cost
    # 2. 三级止损
    assert "stop_t0" in res and "stop_t1" in res and "stop_t2" in res
    assert res["stop_t0"] > 0
    assert res["stop_t1"] > 0
    assert res["stop_t2"] > 0

    # 3. 提取 RiskCardData
    card = extract_risk_card(res)
    assert card is not None
    assert card["breakeven_price"] == res["breakeven_price"]

    # 旧别名 astock_action_execution
    res_action = await execute_tool("astock_action_execution", {"code": "600519", "cost": cost, "shares": shares})
    assert "breakeven_price" in res_action


@pytest.mark.asyncio
async def test_exec_skill_paper_backtest():
    """验证 ⑥ 回测验证 astock-paper-backtest 模拟交易与账户资金查询。"""
    res = await execute_tool("astock_paper_backtest", {"action": "balance"})
    assert "cash" in res or "positions" in res or res.get("status") == "success"

    # 旧别名 astock_trade_paper
    res_legacy = await execute_tool("astock_trade_paper", {"action": "balance"})
    assert "cash" in res_legacy or "positions" in res_legacy or res_legacy.get("status") == "success"
