# -*- coding: utf-8 -*-
"""
tests/webapi/test_webapi_auth_and_session.py
WebAPI 模块一：会话管理、鉴权认证、RBAC 权限与安全审计。

覆盖范围：
1. SQLite 数据库健康度、会话与消息生命周期（外键级联删除）；
2. 会话任务记忆提取与动态标题生成；
3. API 网关根目录与健康检查；
4. CORS 来源白名单与安全响应头；
5. 回环绑定安全约束与运行时目录隔离；
6. 匿名/伪造凭证 Fail-Closed 401 拦截；
7. RBAC 菜单权限隔离（403 越权防护）；
8. 模型管理 API 凭据脱敏与 has_api_key 保护。
"""
from __future__ import annotations

from pathlib import Path
import uuid
import pytest
from starlette.testclient import TestClient

from server.agent.memory import SessionMemoryManager
from server.config import load_server_settings, ensure_safe_test_bind
from server.db import (
    add_message,
    add_session_memory,
    check_db_health,
    create_auth_token,
    create_session,
    delete_provider,
    delete_session,
    delete_session_memories,
    get_messages,
    get_provider_by_id,
    get_session,
    get_session_memories,
    init_db,
    list_sessions,
    update_session_title,
)


@pytest.fixture
def temp_db(tmp_path: Path):
    """提供独立的临时 SQLite 测试库。"""
    db_file = tmp_path / "test_auth_session.db"
    init_db(db_file)
    return db_file


def _create_isolated_user(client: TestClient, menu_codes: set[str]) -> dict[str, str]:
    """辅助函数：创建仅具备指定菜单权限的隔离用户，并返回其登录凭证。"""
    menus_response = client.get("/api/menus")
    assert menus_response.status_code == 200
    menu_ids = [
        item["id"] for item in menus_response.json()["menus"]
        if item["code"] in menu_codes
    ]
    assert len(menu_ids) == len(menu_codes)

    suffix = uuid.uuid4().hex[:8]
    role_response = client.post(
        "/api/roles",
        json={
            "code": f"rbac_{suffix}",
            "name": f"RBAC {suffix}",
            "description": "temporary authorization test",
            "menu_ids": menu_ids,
        },
    )
    assert role_response.status_code == 200, role_response.text

    username = f"176{int(suffix, 16) % 100_000_000:08d}"
    password = "RbacAuth!123"
    user_response = client.post(
        "/api/users",
        json={
            "username": username,
            "name": "RBAC Test User",
            "password": password,
            "role_id": role_response.json()["id"],
        },
    )
    assert user_response.status_code == 200, user_response.text

    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    return {"Authorization": f"Bearer {login_response.json()['token']}"}


# ------------------------------------------------------------------ 1. 数据库与会话 CRUD
def test_db_init_and_session_message_lifecycle(temp_db: Path) -> None:
    assert check_db_health(temp_db) is True

    # 1. 创建会话
    sess = create_session(title="投研对话测试", model="mock", meta={"tag": "quant"}, db_path=temp_db)
    sid = sess["session_id"]
    assert sid.startswith("sess_")
    assert sess["title"] == "投研对话测试"

    # 2. 查询与更新标题
    assert get_session(sid, db_path=temp_db)["model"] == "mock"
    assert update_session_title(sid, "重命名投研会话", db_path=temp_db) is True
    assert get_session(sid, db_path=temp_db)["title"] == "重命名投研会话"

    # 3. 添加消息
    m1 = add_message(session_id=sid, role="user", content="查询茅台现价", db_path=temp_db)
    assert m1["id"] is not None

    risk_info = {"breakeven_price": 1425.50, "stop_t0": 1380.0}
    add_message(
        session_id=sid,
        role="tool",
        content='{"price": 1425.0}',
        tool_call_id="call_99",
        tool_name="astock_quote",
        risk_card=risk_info,
        db_path=temp_db,
    )

    history = get_messages(sid, db_path=temp_db)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["risk_card"] == risk_info

    # 4. 删除会话级联清理消息
    assert delete_session(sid, db_path=temp_db) is True
    assert get_session(sid, db_path=temp_db) is None
    assert len(get_messages(sid, db_path=temp_db)) == 0


# ------------------------------------------------------------------ 2. 会话记忆与标题提取
def test_session_memory_and_title_extraction(temp_db: Path) -> None:
    # 标题模式提取
    t1 = SessionMemoryManager.extract_session_title("计算 600519 最低保本价与止损")
    assert "600519" in t1 and "保本价" in t1

    t2 = SessionMemoryManager.extract_session_title("运行5a多因子选股模型，找出主线龙头")
    assert "5A" in t2 or "选股" in t2

    # 记忆存储与查询
    sess = create_session(title="记忆测试", db_path=temp_db)
    sid = sess["session_id"]

    add_session_memory(
        session_id=sid,
        memory_type="task_result",
        content="保本价 1520.35 (止损T0: 1480.00)",
        key="astock-portfolio-action",
        meta={"status": "success", "facts": {"breakeven_price": 1520.35}},
        db_path=temp_db,
    )

    mems = get_session_memories(sid, memory_type="task_result", db_path=temp_db)
    assert len(mems) == 1
    assert mems[0]["key"] == "astock-portfolio-action"
    assert mems[0]["meta"]["facts"]["breakeven_price"] == 1520.35

    assert delete_session_memories(sid, db_path=temp_db) == 1
    assert len(get_session_memories(sid, db_path=temp_db)) == 0


# ------------------------------------------------------------------ 3. REST 会话端点契约
def test_api_session_endpoints_crud(client: TestClient) -> None:
    # 1. 创建
    create_res = client.post("/api/chat/sessions", json={"title": "WebAPI端点测试", "model": "mock"})
    assert create_res.status_code == 200
    sid = create_res.json()["session_id"]

    # 2. 详情
    detail_res = client.get(f"/api/chat/sessions/{sid}")
    assert detail_res.status_code == 200
    assert detail_res.json()["session"]["session_id"] == sid

    # 3. 列表
    list_res = client.get("/api/chat/sessions")
    assert list_res.status_code == 200
    assert any(s["session_id"] == sid for s in list_res.json()["sessions"])

    # 4. 更新标题
    put_res = client.put(f"/api/chat/sessions/{sid}/title", json={"title": "更新后的标题"})
    assert put_res.status_code == 200
    assert put_res.json()["title"] == "更新后的标题"

    # 5. 删除
    del_res = client.delete(f"/api/chat/sessions/{sid}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


# ------------------------------------------------------------------ 4. 网关与健康端点
def test_api_gateway_and_health_endpoints(client: TestClient) -> None:
    # 根入口
    r_root = client.get("/")
    assert r_root.status_code == 200
    assert any(k in r_root.text for k in ("GC量化投资助手", "AI量化投资助手", "A-Stock Agents"))

    r_api = client.get("/api")
    assert r_api.status_code == 200
    assert r_api.json()["name"] == "A-Stock Agents Web API Gateway"

    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    assert r_health.json()["db_connected"] is True

    r_config = client.get("/api/config")
    assert r_config.status_code == 200
    assert "default_model" in r_config.json()


# ------------------------------------------------------------------ 5. CORS 安全控制
def test_cors_headers_and_origin_policy(monkeypatch, app) -> None:
    monkeypatch.delenv("A_STOCK_CORS_ORIGINS", raising=False)
    settings = load_server_settings()
    assert "*" not in settings.cors_origins

    with TestClient(app) as test_client:
        allowed = test_client.options(
            "/api/health",
            headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET"},
        )
        assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
        assert allowed.headers.get("access-control-allow-credentials") is None

        denied = test_client.options(
            "/api/health",
            headers={"Origin": "https://malicious.attacker.com", "Access-Control-Request-Method": "GET"},
        )
        assert denied.headers.get("access-control-allow-origin") is None


# ------------------------------------------------------------------ 6. 回环绑定与目录安全
def test_runtime_bind_loopback_security() -> None:
    for allowed in ("127.0.0.1", "::1", "localhost"):
        ensure_safe_test_bind(allowed, "test")

    for exposed in ("0.0.0.0", "192.168.1.10", "public.corp.com", ""):
        with pytest.raises(ValueError, match="loopback"):
            ensure_safe_test_bind(exposed, "test")

    ensure_safe_test_bind("0.0.0.0", "production")


# ------------------------------------------------------------------ 7. 匿名与伪造凭据 401 拦截
@pytest.mark.parametrize(
    "headers,params",
    [
        ({"X-Test-User": "1"}, None),
        ({"X-Debug-Admin": "true"}, None),
        ({}, {"bypass_auth": "1"}),
        ({"Authorization": "Bearer forged-invalid-token"}, None),
    ],
)
def test_anonymous_and_forged_identity_fails_closed(anon_client: TestClient, headers, params) -> None:
    res = anon_client.get("/api/auth/me", headers=headers, params=params)
    assert res.status_code == 401
    assert res.json()["detail"]["error"] in {"unauthorized", "invalid_token"}


# ------------------------------------------------------------------ 8. RBAC 菜单权限校验
def test_rbac_menu_permission_enforcement(client: TestClient) -> None:
    # 仅有 dashboard 权限的用户，访问 data-sync 设置必须被 403 拒绝
    ordinary_headers = _create_isolated_user(client, {"dashboard"})
    denied_read = client.get("/api/data-sync/settings", headers=ordinary_headers)
    assert denied_read.status_code == 403
    assert denied_read.json()["detail"]["error"] == "forbidden"

    # 分配了 datasync 权限的用户允许访问
    datasync_headers = _create_isolated_user(client, {"dashboard", "datasync"})
    allowed = client.get("/api/data-sync/settings", headers=datasync_headers)
    assert allowed.status_code == 200


# ------------------------------------------------------------------ 9. 模型管理凭据脱敏安全
def test_models_provider_credentials_redaction_and_clear(client: TestClient) -> None:
    prov_id = f"prov_{uuid.uuid4().hex[:8]}"
    payload = {
        "provider_id": prov_id,
        "name": "安全脱敏测试源",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-secret-token-12345",
        "enabled": True,
        "models": [{"id": "gpt-4o"}],
        "custom_headers": {"Authorization": "Bearer secret-header", "X-Trace": "safe-id"},
    }
    try:
        # 1. 创建并断言响应脱敏
        created = client.post("/api/models/providers", json=payload)
        assert created.status_code == 200
        text = created.text
        assert "sk-secret-token-12345" not in text
        assert "secret-header" not in text

        data = created.json()["provider"]
        assert data["has_api_key"] is True
        assert data["custom_headers"] == {"X-Trace": "safe-id"}

        # 2. 数据库内部真实留存
        assert get_provider_by_id(prov_id)["api_key"] == "sk-secret-token-12345"

        # 3. 显式清空密钥
        clear_payload = dict(payload)
        clear_payload["api_key"] = ""
        clear_payload["clear_api_key"] = True
        cleared = client.post("/api/models/providers", json=clear_payload)
        assert cleared.status_code == 200
        assert cleared.json()["provider"]["has_api_key"] is False
        assert get_provider_by_id(prov_id)["api_key"] == ""
    finally:
        delete_provider(prov_id)
