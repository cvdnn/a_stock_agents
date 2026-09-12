# -*- coding: utf-8 -*-
import asyncio
import pytest

from server.agent import tools as tools_module
from core.strategy.pool_manager import PoolManager
from core.paper_trading.account_manager import AccountManager
from core.strategy.daily_decisions import DailyDecisionEngine


def test_pool_manager_instantiation_and_query():
    pm = PoolManager()
    holding = pm.get_pool("holding")
    assert isinstance(holding, list)
    selected = pm.get_pool("selected")
    assert isinstance(selected, list)
    watch = pm.get_pool("watch")
    assert isinstance(watch, list)


def test_account_manager_instantiation_and_balance():
    am = AccountManager()
    acc = am.get_account()
    assert isinstance(acc, dict)
    assert "cash" in acc
    assert "total_assets" in acc
    assert acc["cash"] >= 0.0
    assert acc["total_assets"] >= 0.0


def test_daily_decision_engine_instantiation():
    engine = DailyDecisionEngine()
    assert engine.provider is not None


@pytest.mark.asyncio
async def test_execute_tool_astock_pool_dashboard_success():
    res = await tools_module.execute_tool("astock_pool_dashboard", {"pool_type": "holding"})
    assert res["status"] == "success"
    assert res["pool_type"] == "holding"
    assert "stocks" in res
    assert "count" in res
    assert "error" not in res


@pytest.mark.asyncio
async def test_execute_tool_astock_trade_paper_balance_success():
    res = await tools_module.execute_tool("astock_trade_paper", {"action": "balance"})
    assert res["status"] == "success"
    assert res["action"] == "balance"
    assert "cash" in res
    assert "total_assets" in res
    assert "error" not in res


@pytest.mark.asyncio
async def test_execute_tool_astock_strategy_mainboard_candidates_success():
    res = await tools_module.execute_tool("astock_strategy_mainboard", {"action": "candidates"})
    assert res["status"] == "success"
    assert "candidates" in res


@pytest.mark.asyncio
async def test_execute_tool_astock_pool_dashboard_flexibility():
    # Extra unexpected arguments should not crash
    res = await tools_module.execute_tool(
        "astock_pool_dashboard",
        {"pool": "holding", "unexpected_param": 123, "code": "601899"}
    )
    assert res["status"] == "success"
    assert res["pool_type"] == "holding"
    assert "in_pool" in res
    assert res["in_pool"] is False

    # Action all
    res_all = await tools_module.execute_tool("astock_pool_dashboard", {"action": "all"})
    assert res_all["status"] == "success"
    assert "pools" in res_all


@pytest.mark.asyncio
async def test_execute_tool_astock_pool_audit():
    res = await tools_module.execute_tool("astock_pool_audit", {"fix": False})
    assert res["status"] == "success"
    assert "total_pools" in res
    assert "total_stocks" in res
