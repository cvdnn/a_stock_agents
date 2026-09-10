# -*- coding: utf-8 -*-
"""
tests/test_governance_suite.py - Comprehensive test suite for Phase 2:
Skill Governance Subsystem, Decoupled Domain Events, Async Tasks, and Port Hunting.
"""
import asyncio
import json
import os
import pytest
from pathlib import Path
from starlette.testclient import TestClient

from core.governance import (
    SkillAuditStats,
    SkillMeta,
    SkillRegistry,
    SkillRiskLevel,
    get_skill_registry,
)
from server.agent.events import (
    AgentEvent,
    ContentDeltaEvent,
    ConversationStartEvent,
    DoneEvent,
    RiskCardEvent,
    ThoughtEvent,
    ToolCallCompleteEvent,
    ToolCallStartEvent,
    sse_format,
)
from server.agent.react_runner import AgentReActRunner
from server.app import app
from server.port_utils import (
    find_free_port,
    read_server_lockfile,
    remove_server_lockfile,
    write_server_lockfile,
)
from server.tasks.task_manager import TaskManager, TaskStatus, get_task_manager


@pytest.fixture
def registry():
    """Returns singleton SkillRegistry instance."""
    return get_skill_registry()


class TestSkillRegistryCore:
    """Test 17 skills loading, schema generation, validation, and execution gates."""

    def test_all_17_skills_loaded(self, registry: SkillRegistry):
        skills = registry.list_skills()
        assert len(skills) == 17, f"Expected 17 skills, found {len(skills)}"

        skill_ids = [s.id for s in skills]
        assert "astock-data-feed" in skill_ids
        assert "astock-platform-evaluate" in skill_ids
        assert "astock-screener-5a" in skill_ids
        assert "astock-action-execution" in skill_ids
        assert "astock-trade-paper" in skill_ids
        assert "astock-strategy-macd" in skill_ids
        assert "astock-strategy-tuige" in skill_ids
        assert "astock-strategy-mainboard" in skill_ids
        assert "astock-pool-dashboard" in skill_ids
        assert "astock-pool-audit" in skill_ids
        assert "astock-quant-engine" in skill_ids
        assert "astock-agent-debate" in skill_ids
        assert "astock-report-html" in skill_ids
        assert "astock-report-archive" in skill_ids
        assert "astock-knowledge-tips" in skill_ids
        assert "astock-model-validation" in skill_ids
        assert "astock-meta-routing" in skill_ids

    def test_openai_tool_schemas_generation(self, registry: SkillRegistry):
        tools = registry.to_openai_tools(enabled_only=True)
        assert len(tools) >= 1
        for t in tools:
            assert t["type"] == "function"
            fn = t["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert fn["parameters"].get("type") == "object"

    def test_dynamic_enable_disable_filter(self, registry: SkillRegistry):
        target_id = "astock-knowledge-tips"
        original = registry.get_skill(target_id)
        assert original is not None

        # Disable
        registry.update_skill(target_id, enabled=False)
        assert registry.get_skill(target_id).enabled is False
        enabled_tools = registry.to_openai_tools(enabled_only=True)
        assert not any(t["function"]["name"] == "astock_knowledge_tips" for t in enabled_tools)

        # Re-enable
        registry.update_skill(target_id, enabled=True)
        assert registry.get_skill(target_id).enabled is True
        enabled_tools2 = registry.to_openai_tools(enabled_only=True)
        assert any(t["function"]["name"] == "astock_knowledge_tips" for t in enabled_tools2)

    def test_parameter_schema_validation(self, registry: SkillRegistry):
        # Missing required parameter 'code' in astock-data-feed
        valid, err = registry.validate_parameters("astock-data-feed", {})
        assert valid is False
        assert "code" in err

        # Valid parameters
        valid2, err2 = registry.validate_parameters("astock-data-feed", {"code": "600519", "action": "quote"})
        assert valid2 is True
        assert err2 is None

    @pytest.mark.asyncio
    async def test_security_gate_confirmation(self, registry: SkillRegistry):
        # astock-trade-paper requires confirmation
        skill = registry.get_skill("astock-trade-paper")
        assert skill.require_confirmation is True

        # Unconfirmed execution should be intercepted
        res = await registry.execute_skill(
            skill_id="astock-trade-paper",
            params={"action": "buy", "code": "600519", "shares": 100},
            confirmed=False,
        )
        assert res.status == "confirmation_required"
        assert res.message is not None

        # Confirmed execution should pass through
        res_conf = await registry.execute_skill(
            skill_id="astock-trade-paper",
            params={"action": "balance"},
            confirmed=True,
        )
        assert res_conf.status in ("success", "error", "unavailable")

    @pytest.mark.asyncio
    async def test_execution_timeout_fuse(self, registry: SkillRegistry):
        # Register slow dummy handler
        registry.register_handler("test_timeout_skill", lambda **kw: asyncio.sleep(2.0))
        skill = registry.get_skill("astock-meta-routing")
        orig_timeout = skill.timeout_seconds
        try:
            # Set tiny timeout
            registry.update_skill("astock-meta-routing", timeout_seconds=1)
            # Override handler to sleep 2s
            async def slow_handler(**kw):
                await asyncio.sleep(2.0)
                return {"done": True}
            registry.register_handler("astock-meta-routing", slow_handler)

            res = await registry.execute_skill(
                "astock-meta-routing",
                {"task_description": "test timeout"},
            )
            assert res.status == "timeout"
            assert "超时熔断" in res.error
        finally:
            registry.update_skill("astock-meta-routing", timeout_seconds=orig_timeout)


class TestUniversalAgentEvents:
    """Test decoupled typed AgentEvent generation and SSE format serialization."""

    @pytest.mark.asyncio
    async def test_typed_agent_events_emission(self):
        runner = AgentReActRunner(default_model="mock")
        events = []
        async for ev in runner.run_chat(
            message="帮我查询 600519 现价并制定保本动作单",
            model="mock",
            tools_enabled=True,
        ):
            events.append(ev)

        assert len(events) >= 3
        assert all(isinstance(e, AgentEvent) for e in events)

        types = [e.event_type for e in events]
        assert "conversation_start" in types
        assert "thought" in types
        assert "done" in types

        # Check RiskCardEvent precision logic
        risk_events = [e for e in events if isinstance(e, RiskCardEvent)]
        if risk_events:
            rc = risk_events[0]
            assert rc.breakeven_price > 0
            assert rc.stop_t0 > 0
            assert rc.stop_t1 > 0
            assert rc.stop_t2 > 0

    def test_sse_format_serializer(self):
        ev = ThoughtEvent(content="正在分析量价多空...")
        formatted = sse_format(ev)
        assert formatted.startswith("event: thought\n")
        assert 'data: {"content": "正在分析量价多空..."}\n\n' in formatted

        done_ev = DoneEvent(total_tokens=150, elapsed_ms=300)
        formatted_done = sse_format(done_ev)
        assert formatted_done.startswith("event: done\n")
        assert '"total_tokens": 150' in formatted_done


class TestGovernanceRESTEndpoints:
    """Test /api/skills and /api/skills/audit/stats endpoints."""

    def test_list_skills_api(self):
        with TestClient(app) as client:
            resp = client.get("/api/skills")
            assert resp.status_code == 200
            skills = resp.json()
            assert len(skills) == 17

            # Filter by category
            resp_data = client.get("/api/skills?category=data")
            assert resp_data.status_code == 200
            data_skills = resp_data.json()
            assert all(s["category"] == "data" for s in data_skills)

    def test_skill_detail_and_patch(self):
        with TestClient(app) as client:
            # Detail
            r_get = client.get("/api/skills/astock-screener-5a")
            assert r_get.status_code == 200
            meta = r_get.json()
            assert meta["id"] == "astock-screener-5a"

            # Patch
            r_patch = client.patch(
                "/api/skills/astock-screener-5a",
                json={"timeout_seconds": 45, "enabled": True},
            )
            assert r_patch.status_code == 200
            updated = r_patch.json()
            assert updated["timeout_seconds"] == 45

            # Revert
            client.patch("/api/skills/astock-screener-5a", json={"timeout_seconds": 60})

    def test_skill_test_endpoint(self):
        with TestClient(app) as client:
            payload = {
                "parameters": {"topic": "auction"},
                "confirmed": True,
            }
            resp = client.post("/api/skills/astock-knowledge-tips/test", json=payload)
            assert resp.status_code == 200
            res = resp.json()
            assert res["status"] == "success"
            assert res["result"]["type"] == "reference"
            assert res["latency_ms"] >= 0

            unavailable = client.post(
                "/api/skills/astock-report-html/test",
                json={"parameters": {"code": "600519"}, "confirmed": True},
            )
            assert unavailable.status_code == 200
            unavailable_data = unavailable.json()
            assert unavailable_data["status"] == "unavailable"
            assert unavailable_data["error"] == "CAPABILITY_NOT_IMPLEMENTED"

    def test_audit_stats_endpoint(self):
        with TestClient(app) as client:
            resp = client.get("/api/skills/audit/stats")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_calls" in data
            assert "error_rate" in data
            assert "avg_latency_ms" in data
            assert "by_skill" in data


class TestAsyncTaskQueue:
    """Test asynchronous background task submission, polling, and circuit-breakers."""

    def test_task_lifecycle_rest(self):
        with TestClient(app) as client:
            # 1. Create task
            req_payload = {
                "task_type": "quant_pipeline",
                "params": {"action": "pipeline"},
                "timeout_seconds": 60,
            }
            resp = client.post("/api/tasks", json=req_payload)
            assert resp.status_code == 200
            t_data = resp.json()
            task_id = t_data["task_id"]
            assert task_id.startswith("task_")
            assert t_data["status"] in ("pending", "running")

            # 2. Poll task status
            import time
            for _ in range(10):
                time.sleep(0.3)
                r_poll = client.get(f"/api/tasks/{task_id}")
                assert r_poll.status_code == 200
                st = r_poll.json()["status"]
                if st in ("completed", "failed"):
                    break
            assert st == "failed"
            assert r_poll.json()["result"]["status"] == "unavailable"

            # 3. List tasks
            r_list = client.get("/api/tasks")
            assert r_list.status_code == 200
            tasks = r_list.json()
            assert any(t["task_id"] == task_id for t in tasks)


class TestPortHuntingAndLockfile:
    """Test dynamic port finding and runtime lockfile for Desktop/TUI clients."""

    def test_find_free_port(self):
        port = find_free_port()
        assert isinstance(port, int)
        assert 1024 < port < 65535

    def test_lockfile_write_read_remove(self, tmp_path: Path):
        test_lock = tmp_path / ".server.port"
        written = write_server_lockfile(port=9123, host="127.0.0.1", pid=1234, lockfile_path=test_lock)
        assert written.exists()

        data = read_server_lockfile(lockfile_path=test_lock)
        assert data is not None
        assert data["port"] == 9123
        assert data["host"] == "127.0.0.1"
        assert data["pid"] == 1234
        assert "http://127.0.0.1:9123" in data["url"]

        removed = remove_server_lockfile(lockfile_path=test_lock)
        assert removed is True
        assert not test_lock.exists()
