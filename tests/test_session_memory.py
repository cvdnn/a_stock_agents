# -*- coding: utf-8 -*-
"""
tests/test_session_memory.py - Unit and Integration tests for Session Memory System,
dynamic Title extraction, and task execution persistence.
"""
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from server.app import app
from server.agent.memory import SessionMemoryManager
from server.db import (
    add_session_memory,
    create_session,
    get_session,
    get_session_memories,
    delete_session_memories,
    init_db,
)


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_memory.db"
    init_db(db_file)
    return db_file


class TestSessionMemoryAndTitle:
    """Test session memory management and title synthesis."""

    def test_title_extraction_patterns(self):
        # 1. Code + Intent
        t1 = SessionMemoryManager.extract_session_title("请帮我算一下 600519 贵州茅台的最低保本价和止损位")
        assert "600519" in t1
        assert "保本价" in t1

        # 2. Intent only
        t2 = SessionMemoryManager.extract_session_title("分析今日大盘行情与市场动向")
        assert "大盘" in t2

        # 3. 5A screener
        t3 = SessionMemoryManager.extract_session_title("运行5a多因子选股模型，找出主线龙头")
        assert "5A" in t3 or "选股" in t3

        # 4. MACD pattern
        t4 = SessionMemoryManager.extract_session_title("检查 000001 平安银行是否有水下二次金叉或底背离")
        assert "000001" in t4
        assert "金叉" in t4 or "MACD" in t4

        # 5. Fallback clean
        t5 = SessionMemoryManager.extract_session_title("你好啊，今天天气真不错，聊聊未来科技")
        assert len(t5) <= 22
        assert len(t5) > 0

    def test_memory_storage_and_query(self, temp_db: Path):
        sess = create_session(title="新建投研对话", db_path=temp_db)
        sid = sess["session_id"]
        assert sid.startswith("sess_")

        # Add task result memory
        m1 = add_session_memory(
            session_id=sid,
            memory_type="task_result",
            content="保本价 1520.35 (止损T0: 1480.00)",
            key="astock-action-execution",
            meta={
                "tool_name": "astock-action-execution",
                "args": {"code": "600519", "cost": 1500, "shares": 100},
                "status": "success",
                "facts": {"code": "600519", "breakeven_price": 1520.35, "stop_t0": 1480.00},
                "elapsed_ms": 120,
            },
            db_path=temp_db,
        )
        assert m1["id"] is not None
        assert m1["session_id"] == sid
        assert m1["memory_type"] == "task_result"

        # Query memories
        memories = get_session_memories(sid, db_path=temp_db)
        assert len(memories) == 1
        assert memories[0]["content"] == "保本价 1520.35 (止损T0: 1480.00)"
        assert memories[0]["meta"]["facts"]["breakeven_price"] == 1520.35

        # Query by memory_type
        task_mems = get_session_memories(sid, memory_type="task_result", db_path=temp_db)
        assert len(task_mems) == 1
        other_mems = get_session_memories(sid, memory_type="dialogue_summary", db_path=temp_db)
        assert len(other_mems) == 0

        # Delete memories
        del_count = delete_session_memories(sid, db_path=temp_db)
        assert del_count == 1
        assert len(get_session_memories(sid, db_path=temp_db)) == 0

    def test_api_session_detail_with_memories(self, monkeypatch, temp_db: Path):
        from server.config import server_settings
        monkeypatch.setattr(server_settings, "db_path", temp_db)

        client = TestClient(app)

        # 1. Create session
        res = client.post("/api/chat/sessions", json={"title": "新建投研对话"})
        assert res.status_code == 200
        sid = res.json()["session_id"]

        # 2. Add memory via SessionMemoryManager
        SessionMemoryManager.record_task_result(
            session_id=sid,
            tool_name="astock-screener-5a",
            args={},
            status="success",
            summary="初选入围 5 只标的",
            data={"selected_count": 5, "total_score": 88.5},
            elapsed_ms=350,
        )

        # 3. GET session detail
        detail_res = client.get(f"/api/chat/sessions/{sid}")
        assert detail_res.status_code == 200
        data = detail_res.json()
        assert data["session"]["session_id"] == sid
        assert "memories" in data
        assert len(data["memories"]) == 1
        assert data["memories"][0]["key"] == "astock-screener-5a"
        assert "初选入围 5 只标的" in data["memories"][0]["content"]

        # 4. PUT update title
        put_res = client.put(f"/api/chat/sessions/{sid}/title", json={"title": "600519 保本价精算"})
        assert put_res.status_code == 200
        assert put_res.json()["title"] == "600519 保本价精算"
