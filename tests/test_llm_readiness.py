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


def test_sanitize_history_drops_orphaned_tools():
    from server.agent.react_runner import sanitize_history_for_llm

    history = [
        {"role": "user", "content": "问题1"},
        {"role": "tool", "tool_call_id": "call_orphan_1", "tool_name": "tool_a", "content": "{}"},
        {"role": "tool", "tool_call_id": "call_orphan_2", "tool_name": "tool_b", "content": "{}"},
        {"role": "user", "content": "问题2"},
    ]
    cleaned = sanitize_history_for_llm(history)
    assert len(cleaned) == 2
    assert [m["role"] for m in cleaned] == ["user", "user"]
    assert cleaned[0]["content"] == "问题1"
    assert cleaned[1]["content"] == "问题2"


def test_sanitize_history_preserves_valid_tool_calling_pairs():
    from server.agent.react_runner import sanitize_history_for_llm

    history = [
        {"role": "user", "content": "查数据"},
        {
            "role": "assistant",
            "content": "正在查询...",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "query_quote", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "query_tech", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "tool_name": "query_quote", "content": '{"price": 10}'},
        {"role": "tool", "tool_call_id": "call_2", "tool_name": "query_tech", "content": '{"macd": 0.5}'},
        {"role": "assistant", "content": "现价10元，MACD金叉。"},
        {"role": "user", "content": "下一步策略"},
    ]
    cleaned = sanitize_history_for_llm(history)
    assert len(cleaned) == 6
    assert [m["role"] for m in cleaned] == ["user", "assistant", "tool", "tool", "assistant", "user"]
    assert len(cleaned[1]["tool_calls"]) == 2
    assert cleaned[2]["tool_call_id"] == "call_1"
    assert cleaned[3]["tool_call_id"] == "call_2"


def test_factory_parses_model_with_provider_parentheses(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "server.db.list_providers",
        lambda: [
            {
                "provider_id": "prov_sophnet",
                "name": "Sophnet",
                "base_url": "https://api.sophnet.com/v1",
                "api_key": "test_key",
                "enabled": 1,
                "models": [{"id": "DeepSeek-V4-Flash-0731", "name": "DeepSeek-V4-Flash-0731"}],
            }
        ],
    )
    provider = LLMProviderFactory.get_provider("DeepSeek-V4-Flash-0731(Sophnet)")
    assert provider.model_name == "DeepSeek-V4-Flash-0731"
    assert provider.base_url == "https://api.sophnet.com/v1"


def test_factory_matches_model_case_insensitively_and_prefix(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "server.db.list_providers",
        lambda: [
            {
                "provider_id": "prov_sophnet",
                "name": "Sophnet",
                "base_url": "https://api.sophnet.com/v1",
                "api_key": "test_key",
                "enabled": 1,
                "models": [{"id": "DeepSeek-V4-Flash-0731", "name": "DeepSeek-V4-Flash-0731"}],
            }
        ],
    )
    # Test openrouter style prefix: deepseek/deepseek-v4-flash-0731
    provider = LLMProviderFactory.get_provider("deepseek/deepseek-v4-flash-0731")
    assert provider.model_name == "DeepSeek-V4-Flash-0731"
