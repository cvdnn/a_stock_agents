from __future__ import annotations

from pathlib import Path

import pytest

from server.agent import react_runner as runner_module
from server.agent import tools as tools_module
from server.agent.events import DoneEvent, RiskCardEvent, ToolCallCompleteEvent
from server.agent.react_runner import AgentReActRunner
from server.llm.base import BaseLLMProvider, LLMStreamChunk


ROOT = Path(__file__).resolve().parent.parent


def test_production_tool_source_contains_no_fabricated_success_literals() -> None:
    source = (ROOT / "scripts/server/agent/tools.py").read_text(encoding="utf-8")
    forbidden = (
        '"status": "simulated"',
        '"status": "active"',
        '"status": "archived"',
        '"status": "ready"',
        '"validation_status": "passed"',
        '"rolling_ic": 0.065',
        '"bull_bear_ratio": "52% 多头 vs 48% 空头"',
        '"cs": 65',
        "1000000.0",
    )
    for literal in forbidden:
        assert literal not in source


@pytest.mark.asyncio
async def test_unknown_and_raising_handlers_are_explicit_failures(monkeypatch) -> None:
    unknown = await tools_module.execute_tool("not-a-skill", {})
    assert unknown == {
        "status": "unavailable",
        "error": "CAPABILITY_NOT_IMPLEMENTED",
        "skill_id": "not-a-skill",
    }

    def explode() -> dict:
        raise RuntimeError("secret upstream detail")

    monkeypatch.setitem(tools_module.TOOL_MAP, "astock-explodes", explode)
    failed = await tools_module.execute_tool("astock-explodes", {})
    assert failed["status"] == "error"
    assert failed["error"] == "CAPABILITY_EXECUTION_FAILED"
    assert failed["skill_id"] == "astock-explodes"
    assert "secret upstream detail" not in str(failed)


class _ScriptedProvider(BaseLLMProvider):
    def __init__(self) -> None:
        super().__init__("truthful-test-model")
        self.calls = 0

    async def stream_chat(self, messages, tools=None, temperature=0.3, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield LLMStreamChunk(tool_calls=[{
                "id": "call_unavailable",
                "function": {"name": "astock_report_html", "arguments": '{"code":"600519"}'},
            }])
        else:
            yield LLMStreamChunk(delta_text="该能力当前不可用。", finish_reason="stop")


@pytest.mark.asyncio
async def test_runner_preserves_unavailable_without_success_artifacts(monkeypatch) -> None:
    provider = _ScriptedProvider()
    monkeypatch.setattr(
        runner_module.LLMProviderFactory,
        "get_provider",
        staticmethod(lambda **kwargs: provider),
    )

    async def unavailable_tool(name, args):
        return {
            "status": "unavailable",
            "error": "CAPABILITY_NOT_IMPLEMENTED",
            "skill_id": name,
            "breakeven_price": 10.0,
            "stop_t0": 9.7,
            "stop_t1": 9.5,
            "stop_t2": 9.2,
        }

    monkeypatch.setattr(runner_module, "execute_tool", unavailable_tool)

    events = []
    async for event in AgentReActRunner().run_chat("生成报告", tools_enabled=True):
        events.append(event)

    complete = next(event for event in events if isinstance(event, ToolCallCompleteEvent))
    assert complete.status == "unavailable"
    assert "完成调用" not in complete.summary
    assert not any(isinstance(event, RiskCardEvent) for event in events)

    done = next(event for event in events if isinstance(event, DoneEvent))
    assert done.total_tokens == 0
    assert done.finish_reason == "tool_failure"
