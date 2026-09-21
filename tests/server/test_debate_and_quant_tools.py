# -*- coding: utf-8 -*-
"""
tests/test_debate_and_quant_tools.py
Verifies that astock_agent_debate and astock_quant_engine are fully operational,
production-ready, and never return fake 'unavailable' status.
"""
import pytest
from server.agent.tools import (
    _sync_astock_agent_debate,
    _sync_astock_quant_engine,
    execute_tool,
)


def test_sync_astock_agent_debate_success():
    """Verify that astock_agent_debate returns 7 analysts and risk action."""
    res = _sync_astock_agent_debate(code="600519")
    assert res.get("status") == "success"
    assert "consensus" in res
    assert "analysts" in res
    assert len(res["analysts"]) == 7
    assert "risk_action" in res
    assert res["risk_action"].get("breakeven_price", 0) > 0


def test_sync_astock_agent_debate_invalid_code():
    """Verify invalid code returns DATA_UNAVAILABLE gracefully."""
    res = _sync_astock_agent_debate(code="000222")
    assert res.get("status") == "error"
    assert res.get("error") == "DATA_UNAVAILABLE"


def test_sync_astock_quant_engine_macro():
    """Verify quant engine returns portfolio target weight when code is omitted."""
    res = _sync_astock_quant_engine(action="pipeline")
    assert res.get("status") == "success"
    assert res.get("portfolio_target_weight", 0) > 0
    assert "standard_board_cap" in res


def test_sync_astock_quant_engine_stock_allocation():
    """Verify quant engine calculates shares and board limits for valid stock."""
    res = _sync_astock_quant_engine(action="pipeline", code="600519")
    assert res.get("status") == "success"
    assert "allocation" in res
    alloc = res["allocation"]
    assert "shares" in alloc
    assert alloc["shares"] >= 0
    assert alloc["board_cap"] == 0.15  # Mainboard cap 15%


@pytest.mark.asyncio
async def test_execute_tool_debate_and_quant():
    """Verify async dispatch through execute_tool returns success without unavailable."""
    res_debate = await execute_tool("astock_agent_debate", {"code": "600519"})
    assert res_debate["status"] == "success"
    assert res_debate["skill_id"] == "astock_agent_debate"

    res_quant = await execute_tool("astock_quant_engine", {"code": "600519"})
    assert res_quant["status"] == "success"
    assert res_quant["skill_id"] == "astock_quant_engine"
