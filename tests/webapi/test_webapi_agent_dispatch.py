# -*- coding: utf-8 -*-
"""
tests/webapi/test_webapi_agent_dispatch.py
WebAPI 模块四：Web Agent 工具分发调度、ReAct 思考流与 LLM 就绪性守卫。

覆盖范围：
1. Web Agent 对投研工具分发执行（行情、保本动作单、股池审计、7分析师辩论、量化流水线）；
2. 空股池即刻终止与登记引导提示契约；
3. `<think>` 标签增量清洗与前言思考隔离（不泄露到 ContentDeltaEvent）；
4. 聊天补全 SSE 流式端点 (/api/chat/completions/stream)；
5. LLM 就绪性生产守卫（生产模式严禁 mock、未配密钥报 LLM_NOT_CONFIGURED）；
6. 上下文历史中孤儿 tool 消息清洗与完整调用对保留；
7. 市场前缀推导与代码归一化（normalize_symbol）。
"""
from __future__ import annotations

import json
import pytest
from starlette.testclient import TestClient

from core.config import infer_market_prefix, normalize_symbol
from core.data.data_bridge import DataBridge
from server.agent.events import ContentDeltaEvent, ThoughtEvent
from server.agent.react_runner import AgentReActRunner, process_delta_think_tags, sanitize_history_for_llm
from server.agent.tools import (
    TOOLS_DEFINITIONS,
    _extract_latest_tech_summary,
    _sync_astock_agent_debate,
    _sync_astock_quant_engine,
    execute_tool,
    extract_risk_card,
)
from server.config import server_settings
from server.llm.base import LLMStreamChunk
from server.llm.factory import LLMProviderFactory
from server.llm.mock_provider import MockLLMProvider


# ------------------------------------------------------------------ 1. 代码归一化与技术摘要
def test_symbol_normalize_and_tech_summary() -> None:
    assert infer_market_prefix("000300") == "sh"
    assert infer_market_prefix("399001") == "sz"
    assert normalize_symbol("000300") == "sh000300"
    assert normalize_symbol("上证指数") == "sh000001"

    summary_flat = _extract_latest_tech_summary({
        "ma5": 1275.1, "ma10": 1284.2, "ma20": 1298.23,
        "macd_bar": -2.31, "rsi": 41.88,
    })
    assert summary_flat["macd_hist"] == -2.31
    assert summary_flat["ma5"] == 1275.1

    summary_nested = _extract_latest_tech_summary({
        "ma": {"ma5": 1275.1, "ma10": 1284.2, "ma20": 1298.23},
        "macd": {"hist": -2.31},
        "rsi": {"rsi6": 41.88},
    })
    assert summary_nested["macd_hist"] == -2.31
    assert summary_nested["rsi6"] == 41.88


# ------------------------------------------------------------------ 2. 核心投研工具分发与实战三原则
@pytest.fixture()
def canned_quote(monkeypatch):
    quote = {
        "code": "600519", "name": "贵州茅台", "price": 1425.50, "change_pct": 1.24,
        "high": 1438.00, "low": 1408.60, "open": 1412.00, "prev_close": 1408.10,
        "volume": 31500, "amount": 4.48e9, "turnover_pct": 0.25, "pe": 22.6,
        "circulating_market_cap": 1.79e12, "total_market_cap": 1.79e12,
    }
    monkeypatch.setattr(DataBridge, "get_realtime_quote", lambda self, code, **kw: dict(quote))
    return quote


@pytest.mark.asyncio
async def test_agent_tool_quote_and_action_plan(canned_quote) -> None:
    # 现价
    res_q = await execute_tool("astock_quote", {"code": "600519"})
    assert res_q["status"] == "success"
    assert res_q["price"] == 1425.50

    # 动作单
    res_a = await execute_tool("astock_action_plan", {"code": "600519", "cost": 1330.0, "shares": 100})
    assert res_a["breakeven_price"] >= 1330.0  # math.ceil 向上进位
    assert "stop_t0" in res_a
    assert "stop_t1" in res_a
    assert "stop_t2" in res_a

    card = extract_risk_card(res_a)
    assert card is not None
    assert card["breakeven_price"] == res_a["breakeven_price"]


@pytest.mark.asyncio
async def test_agent_tool_empty_pool_guidance() -> None:
    res = await execute_tool("astock_pool_dashboard", {"pool_type": "nonexistent_empty_pool"})
    assert res["status"] == "success"
    assert res.get("is_empty") is True
    assert "000001:1000@12.50" in res.get("message", "")
    assert "股票:股数@成本价" in res.get("message", "")


@pytest.mark.asyncio
async def test_agent_tool_debate_and_quant(monkeypatch) -> None:
    # 辩论无数据 fail-closed
    monkeypatch.setattr(DataBridge, "get_realtime_quote", lambda self, code, **kw: {})
    monkeypatch.setattr(DataBridge, "tencent_kline", staticmethod(lambda code, **kw: []))
    res_debate = _sync_astock_agent_debate(code="000222")
    assert res_debate["status"] == "error"
    assert res_debate["error"] == "DATA_UNAVAILABLE"

    # 量化宏观仓位
    res_quant = _sync_astock_quant_engine(action="pipeline")
    assert res_quant["status"] == "success"
    assert res_quant["portfolio_target_weight"] > 0
    assert "standard_board_cap" in res_quant


# ------------------------------------------------------------------ 3. ReAct 思考流与前言隔离
def test_process_delta_think_tags() -> None:
    # 1. 普通正文
    c, th, in_tag, buf = process_delta_think_tags("普通正文", False, "")
    assert c == "普通正文" and th == ""

    # 2. 完整思考标签
    c2, th2, in_tag2, buf2 = process_delta_think_tags("<think>思考逻辑</think>正式回复", False, "")
    assert c2 == "正式回复" and th2 == "思考逻辑"

    # 3. 跨 chunk 流式思考
    c3a, th3a, in3a, buf3a = process_delta_think_tags("<think>分段思考", False, "")
    assert c3a == "" and th3a == "分段思考" and in3a is True
    c3b, th3b, in3b, buf3b = process_delta_think_tags("继续思考</think>最终回复", in3a, buf3a)
    assert c3b == "最终回复" and th3b == "继续思考" and in3b is False


@pytest.mark.asyncio
async def test_tool_calling_preamble_does_not_leak_to_content(monkeypatch) -> None:
    from server.llm.base import BaseLLMProvider

    class PreambleMockProvider(BaseLLMProvider):
        async def stream_chat(self, messages, tools=None, temperature=0.2, **kwargs):
            last_msg = messages[-1] if messages else {}
            if last_msg.get("role") == "tool":
                yield LLMStreamChunk(delta_text="# 💼 投资组合全景报告\n核查完成。")
                yield LLMStreamChunk(finish_reason="stop")
            else:
                yield LLMStreamChunk(delta_text="我将先核查投资组合数据。")
                yield LLMStreamChunk(
                    tool_calls=[{
                        "id": "call_m1",
                        "type": "function",
                        "function": {"name": "astock_quote", "arguments": json.dumps({"code": "600519"})},
                    }],
                    finish_reason="tool_calls",
                )

    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *a, **kw: PreambleMockProvider("mock-preamble"))
    runner = AgentReActRunner(default_model="mock-preamble")
    thought_events, content_events = [], []

    async for event in runner.run_chat(message="请核查数据", tools_enabled=True):
        if isinstance(event, ThoughtEvent):
            thought_events.append(event.content)
        elif isinstance(event, ContentDeltaEvent):
            content_events.append(event.text)

    full_th = "".join(thought_events)
    full_ct = "".join(content_events)
    assert "我将先核查投资组合数据" in full_th
    assert "我将先核查投资组合数据" not in full_ct
    assert "投资组合全景报告" in full_ct


# ------------------------------------------------------------------ 4. 聊天补全 SSE 流式端点
def test_chat_completions_stream_endpoint(client: TestClient) -> None:
    payload = {
        "message": "你好，请简要介绍 A-Stock Agents 实战三原则",
        "model": "mock",
        "tools_enabled": False,
    }
    resp = client.post("/api/chat/completions/stream", json=payload)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "event: conversation_start" in body
    assert "event: content_delta" in body
    assert "event: done" in body


# ------------------------------------------------------------------ 5. LLM 就绪性守卫与历史清洗
def test_llm_production_guard_rejects_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_settings, "runtime_mode", "production")
    with pytest.raises(RuntimeError) as caught:
        LLMProviderFactory.get_provider("mock")
    assert caught.value.code == "LLM_NOT_CONFIGURED"

    monkeypatch.setattr(server_settings, "runtime_mode", "test")
    p = LLMProviderFactory.get_provider("mock")
    assert isinstance(p, MockLLMProvider)


def test_sanitize_history_drops_orphaned_tools() -> None:
    history = [
        {"role": "user", "content": "问题1"},
        {"role": "tool", "tool_call_id": "orphan_1", "tool_name": "tool_a", "content": "{}"},
        {"role": "user", "content": "问题2"},
    ]
    cleaned = sanitize_history_for_llm(history)
    assert len(cleaned) == 2
    assert [m["content"] for m in cleaned] == ["问题1", "问题2"]


def test_llm_stream_chunk_usage_tokens() -> None:
    usage = {
        "completion_tokens": 46, "prompt_tokens": 65, "total_tokens": 111,
        "completion_tokens_details": {"reasoning_tokens": 21},
    }
    chunk = LLMStreamChunk(usage=usage)
    assert chunk.usage["total_tokens"] == 111
