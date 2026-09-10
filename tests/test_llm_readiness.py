from __future__ import annotations

import pytest

from server.agent.react_runner import AgentReActRunner
from server.config import server_settings
from server.llm.errors import LLMReadinessError
from server.llm.factory import LLMProviderFactory
from server.llm.mock_provider import MockLLMProvider


def _production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_settings, "runtime_mode", "production")


def test_production_rejects_explicit_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    _production(monkeypatch)
    with pytest.raises(RuntimeError) as caught:
        LLMProviderFactory.get_provider("mock")
    assert caught.value.code == "LLM_NOT_CONFIGURED"


def test_production_missing_provider_key_never_falls_back_to_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production(monkeypatch)
    monkeypatch.setattr(server_settings, "deepseek_api_key", None)
    with pytest.raises(RuntimeError) as caught:
        LLMProviderFactory.get_provider("deepseek-chat")
    assert caught.value.code == "LLM_NOT_CONFIGURED"


def test_production_unknown_model_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _production(monkeypatch)
    with pytest.raises(RuntimeError) as caught:
        LLMProviderFactory.get_provider("definitely-unknown-model")
    assert caught.value.code == "LLM_MODEL_UNAVAILABLE"


def test_test_mode_explicitly_allows_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_settings, "runtime_mode", "test")
    provider = LLMProviderFactory.get_provider("mock")
    assert isinstance(provider, MockLLMProvider)


@pytest.mark.asyncio
async def test_runner_gate_failure_emits_error_without_tool_or_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def reject_provider(*args, **kwargs):
        raise LLMReadinessError("LLM_AUTH_FAILED", "认证失败")

    async def forbidden_tool(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"status": "success"}

    monkeypatch.setattr(LLMProviderFactory, "get_provider", reject_provider)
    monkeypatch.setattr("server.agent.react_runner.execute_tool", forbidden_tool)

    events = []
    runner = AgentReActRunner(default_model="deepseek-chat")
    async for event in runner.run_chat(
        message="分析 600519",
        model="deepseek-chat",
        tools_enabled=True,
    ):
        events.append(event)

    assert calls == 0
    assert [event.event_type for event in events] == ["error"]
    assert events[0].code == "LLM_AUTH_FAILED"
