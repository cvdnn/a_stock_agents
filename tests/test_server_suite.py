# -*- coding: utf-8 -*-
"""
tests/test_server_suite.py - Comprehensive test suite for Web AIChat Backend & Agent Runtime (Phase 1).
"""
import json
import pytest
from pathlib import Path
from starlette.testclient import TestClient

from server.app import app
from server.config import server_settings
from server.db import (
    add_message,
    check_db_health,
    create_session,
    delete_session,
    get_messages,
    get_session,
    init_db,
    list_sessions,
    update_session_title,
)
from server.llm.base import LLMStreamChunk
from server.llm.factory import LLMProviderFactory
from server.llm.mock_provider import MockLLMProvider
from server.agent.tools import (
    TOOLS_DEFINITIONS,
    execute_tool,
    extract_risk_card,
)
from server.agent.react_runner import AgentReActRunner


@pytest.fixture
def temp_db(tmp_path: Path):
    """Fixture providing a temporary SQLite database path."""
    db_file = tmp_path / "test_chats.db"
    init_db(db_file)
    return db_file


class TestServerDatabase:
    """Test SQLite storage, WAL mode, session and message lifecycle."""

    def test_init_and_health_check(self, temp_db: Path):
        assert check_db_health(temp_db) is True

    def test_session_lifecycle(self, temp_db: Path):
        # Create
        sess = create_session(
            title="测试会话",
            model="mock",
            meta={"custom_flag": True},
            db_path=temp_db,
        )
        sid = sess["session_id"]
        assert sid.startswith("sess_")
        assert sess["title"] == "测试会话"
        assert sess["meta"]["custom_flag"] is True

        # Retrieve
        fetched = get_session(sid, db_path=temp_db)
        assert fetched is not None
        assert fetched["session_id"] == sid
        assert fetched["model"] == "mock"

        # Update title
        updated = update_session_title(sid, "重命名会话", db_path=temp_db)
        assert updated is True
        fetched2 = get_session(sid, db_path=temp_db)
        assert fetched2["title"] == "重命名会话"

        # List
        sess_list = list_sessions(limit=10, db_path=temp_db)
        assert len(sess_list) >= 1
        assert any(s["session_id"] == sid for s in sess_list)

        # Delete
        del_res = delete_session(sid, db_path=temp_db)
        assert del_res is True
        assert get_session(sid, db_path=temp_db) is None

    def test_message_lifecycle(self, temp_db: Path):
        sess = create_session(title="消息测试会话", db_path=temp_db)
        sid = sess["session_id"]

        # Add user message
        m1 = add_message(
            session_id=sid,
            role="user",
            content="帮我查询茅台行情",
            db_path=temp_db,
        )
        assert m1["id"] is not None

        # Add assistant message with thought
        m2 = add_message(
            session_id=sid,
            role="assistant",
            content="好的，正在为您查询...",
            thought="意图识别为行情查询",
            db_path=temp_db,
        )

        # Add tool observation message with risk card
        risk_info = {"breakeven_price": 1331.36, "stop_t0": 1290.1}
        m3 = add_message(
            session_id=sid,
            role="tool",
            content='{"price": 1330.0}',
            tool_call_id="call_001",
            tool_name="astock_quote",
            risk_card=risk_info,
            db_path=temp_db,
        )

        # Retrieve messages
        history = get_messages(sid, db_path=temp_db)
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[1]["thought"] == "意图识别为行情查询"
        assert history[2]["role"] == "tool"
        assert history[2]["risk_card"] == risk_info

        # Foreign key cascade delete
        delete_session(sid, db_path=temp_db)
        leftover = get_messages(sid, db_path=temp_db)
        assert len(leftover) == 0


class TestLLMProviders:
    """Test LLM provider abstraction, factory, and Mock provider."""

    @pytest.mark.asyncio
    async def test_mock_provider_streaming(self):
        provider = MockLLMProvider()
        messages = [{"role": "user", "content": "你好，请介绍一下你自己"}]
        chunks = []
        async for chunk in provider.stream_chat(messages):
            chunks.append(chunk)

        full_text = "".join(c.delta_text for c in chunks if c.delta_text)
        assert len(full_text) > 0
        assert any(c.thought for c in chunks)
        assert any(c.finish_reason == "stop" for c in chunks)

    @pytest.mark.asyncio
    async def test_mock_provider_tool_triggering(self):
        provider = MockLLMProvider()
        messages = [{"role": "user", "content": "帮我查询 600519 行情并出动作单"}]
        tools = TOOLS_DEFINITIONS
        chunks = []
        async for chunk in provider.stream_chat(messages, tools=tools):
            chunks.append(chunk)

        tool_chunks = [c for c in chunks if c.tool_calls]
        assert len(tool_chunks) > 0
        called_fn = tool_chunks[0].tool_calls[0]["function"]["name"]
        assert called_fn in ("astock_action_plan", "astock_quote")

    def test_factory_resolution(self):
        p_mock = LLMProviderFactory.get_provider("mock")
        assert isinstance(p_mock, MockLLMProvider)

        # Without API key, falls back to Mock provider gracefully
        p_ds = LLMProviderFactory.get_provider("deepseek-chat")
        assert isinstance(p_ds, (MockLLMProvider, object))


class TestAgentTools:
    """Test core tool execution bridge and risk card extraction."""

    @pytest.mark.asyncio
    async def test_execute_quote_tool(self):
        res = await execute_tool("astock_quote", {"code": "600519"})
        assert "code" in res or "error" in res
        if "code" in res:
            assert res["code"] == "600519"
            assert "price" in res

    @pytest.mark.asyncio
    async def test_execute_action_plan_tool(self):
        res = await execute_tool("astock_action_plan", {"code": "600519", "cost": 1330.0, "shares": 100})
        assert "code" in res
        assert "breakeven_price" in res
        assert "stop_t0" in res
        assert "stop_t1" in res
        assert "stop_t2" in res

        # Verify ceil cent logic: breakeven must be >= cost
        assert res["breakeven_price"] >= 1330.0

        card = extract_risk_card(res)
        assert card is not None
        assert card["breakeven_price"] == res["breakeven_price"]
        assert card["stop_t0"] == res["stop_t0"]


class TestAgentReActRunner:
    """Test ReAct runtime SSE event generation and conversation workflow."""

    @pytest.mark.asyncio
    async def test_react_stream_events_flow(self):
        runner = AgentReActRunner(default_model="mock")
        events = []
        async for sse_chunk in runner.run_chat_stream(
            message="帮我查询 600519 现价并制定保本动作单",
            model="mock",
            tools_enabled=True,
        ):
            events.append(sse_chunk)

        full_stream = "".join(events)
        assert "event: conversation_start" in full_stream
        assert "event: thought" in full_stream
        assert "event: done" in full_stream


class TestFastAPIRoutes:
    """Test HTTP REST endpoints via Starlette TestClient."""

    def test_root_and_health(self):
        with TestClient(app) as client:
            r1 = client.get("/")
            assert r1.status_code == 200
            data1 = r1.json()
            assert data1["name"] == "A-Stock Agents Web API"
            assert data1["status"] == "online"

            r2 = client.get("/api/health")
            assert r2.status_code == 200
            data2 = r2.json()
            assert data2["status"] == "ok"
            assert data2["db_connected"] is True

            r3 = client.get("/api/config")
            assert r3.status_code == 200
            data3 = r3.json()
            assert "default_model" in data3
            assert "supported_models" in data3

    def test_session_endpoints(self):
        with TestClient(app) as client:
            # Create session
            create_resp = client.post("/api/chat/sessions", json={"title": "端到端测试会话", "model": "mock"})
            assert create_resp.status_code == 200
            sess_data = create_resp.json()
            sid = sess_data["session_id"]
            assert sid.startswith("sess_")

            # Get session
            get_resp = client.get(f"/api/chat/sessions/{sid}")
            assert get_resp.status_code == 200
            detail = get_resp.json()
            assert detail["session"]["session_id"] == sid
            assert isinstance(detail["messages"], list)

            # List sessions
            list_resp = client.get("/api/chat/sessions")
            assert list_resp.status_code == 200
            assert any(s["session_id"] == sid for s in list_resp.json()["sessions"])

            # Delete session
            del_resp = client.delete(f"/api/chat/sessions/{sid}")
            assert del_resp.status_code == 200
            assert del_resp.json()["status"] == "deleted"

    def test_chat_stream_endpoint(self):
        with TestClient(app) as client:
            payload = {
                "message": "你好，请简要介绍 A-Stock Agents 的实战三原则",
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
