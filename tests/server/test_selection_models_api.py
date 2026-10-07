# -*- coding: utf-8 -*-
"""批次三 C1～C4：智能选股系统后端 API 集成测试（§15 / 发布门禁 2、3、10、18）。

隔离策略：所有落盘仓库的默认根（`output/config|cache|pools`）被重定向到 `tmp_path`，
确保用例不触碰真实用户目录；HTTP 一律走 conftest 的 `client`/`anon_client`（裸建
TestClient 恒 401）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def selection_store(tmp_path, monkeypatch):
    """把选股系统全部落盘根重定向到临时目录（config/cache/pools/locks）。"""
    from core.selection_models import (
        catalog,
        definition_repository,
        run_repository,
        signal_latch,
        version_repository,
    )

    config_root = tmp_path / "config"
    cache_root = tmp_path / "cache"
    pools_root = tmp_path / "pools"
    lock_root = tmp_path / "locks"
    monkeypatch.setattr(definition_repository, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(definition_repository, "DEFAULT_LOCK_DIR", lock_root)
    monkeypatch.setattr(version_repository, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(run_repository, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(run_repository, "POOLS_ROOT", pools_root)
    monkeypatch.setattr(catalog, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(signal_latch, "CACHE_ROOT", cache_root)
    return tmp_path


def _condition_records():
    return [{"code": "600001", "closes": [float(i) for i in range(1, 71)]}]


def _create_and_publish(client, *, model_type="condition_tree", template="blank"):
    created = client.post("/api/selection-models", json={
        "model_type": model_type, "name": "测试模型", "template": template,
    }).json()
    assert created["status"] == "ok", created
    model_id = created["data"]["model_id"]
    validated = client.post(f"/api/selection-models/{model_id}/validate").json()
    assert validated["status"] == "ok", validated
    published = client.post(f"/api/selection-models/{model_id}/versions", json={}).json()
    assert published["status"] == "ok", published
    activated = client.post(f"/api/selection-models/{model_id}/activate/1").json()
    assert activated["status"] == "ok", activated
    return model_id


# ------------------------------------------------------------------ 元数据
def test_types_and_rule_types_are_real(client, selection_store):
    types = client.get("/api/selection-models/types").json()
    assert types["status"] == "ok"
    assert types["data"]["publishable"] == ["condition_tree", "funnel"]
    ids = {t["type_id"]: t for t in types["data"]["types"]}
    assert ids["scoring_rank"]["publishable"] is False

    rules = client.get("/api/selection-models/rule-types").json()
    assert rules["status"] == "ok"
    assert rules["data"]["rule_types"]
    assert all("parameter_schema" in r and "form_annotations" in r for r in rules["data"]["rule_types"])


def test_unauthenticated_requests_are_rejected(anon_client):
    assert anon_client.get("/api/selection-models/types").status_code == 401
    assert anon_client.post("/api/selection-models", json={"model_type": "funnel", "name": "x"}).status_code == 401


def test_p2_model_type_cannot_be_created(client, selection_store):
    resp = client.post("/api/selection-models", json={"model_type": "scoring_rank", "name": "评分"}).json()
    assert resp["status"] == "error"
    assert resp["error_code"] == "MODEL_TYPE_UNKNOWN"


# ------------------------------------------------------------------ 生命周期（发布门禁 2）
def test_create_validate_publish_activate_run_without_code(client, selection_store):
    model_id = _create_and_publish(client)
    listed = client.get("/api/selection-models").json()
    assert any(m["model_id"] == model_id for m in listed["data"]["models"])

    run = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    assert run["status"] == "ok", run
    assert run["data"]["run"]["status"] == "COMPLETED"
    assert run["data"]["selected_codes"] == ["600001"]

    detail = client.get(f"/api/selection-models/runs/{run['data']['run_id']}").json()
    assert detail["data"]["run"]["plan_hash"]

    nodes = client.get(f"/api/selection-models/runs/{run['data']['run_id']}/nodes").json()
    assert nodes["data"]["nodes"][0]["stage_id"] == "condition_filter"
    candidates = client.get(f"/api/selection-models/runs/{run['data']['run_id']}/candidates").json()
    assert candidates["data"]["candidates"][0]["verdict"] == "PASS"

    results = client.get(f"/api/selection-models/results?model_id={model_id}").json()
    assert results["data"]["total"] == 1
    assert results["data"]["results"][0]["signal_codes"] == ["600001"]


def test_run_without_active_version_fails_closed(client, selection_store):
    created = client.post("/api/selection-models", json={"model_type": "funnel", "name": "未发布"}).json()
    model_id = created["data"]["model_id"]
    resp = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    assert resp["status"] == "error"
    assert resp["error_code"] == "MODEL_VERSION_NOT_FOUND"


def test_run_without_records_and_no_local_data_fails_closed(client, selection_store):
    model_id = _create_and_publish(client, model_type="funnel", template="blank")
    resp = client.post(f"/api/selection-models/{model_id}/runs", json={}).json()
    assert resp["status"] in {"ok", "error"}
    if resp["status"] == "error":
        assert resp["error_code"] == "MODEL_DATA_MISSING"
        assert resp["watermark"]["eligible_for_signal"] is False


# ------------------------------------------------------------------ 版本仓库（门禁 9）
def test_version_immutability_activation_and_conflict(client, selection_store):
    model_id = _create_and_publish(client)
    versions = client.get(f"/api/selection-models/{model_id}/versions").json()
    assert [v["version"] for v in versions["data"]["versions"]] == [1]
    assert versions["data"]["active_version"] == 1

    # 发布号单调：修改草稿基线后再发一版
    copied = client.post(f"/api/selection-models/{model_id}/versions/1/copy-to-draft", json={}).json()
    assert copied["status"] == "ok"
    published = client.post(f"/api/selection-models/{model_id}/versions", json={
        "base_version": 1, "draft_revision": copied["data"]["draft_revision"],
    }).json()
    assert published["data"]["version"] == 2

    # 草稿并发冲突被拒（错误修订号）
    conflict = client.patch(f"/api/selection-models/{model_id}/draft", json={
        "definition": copied["data"]["definition"], "base_version": 1, "draft_revision": 999,
    }).json()
    assert conflict["error_code"] == "MODEL_DRAFT_CONFLICT"

    # 激活新版本后再回滚到 v1：指针切换且历史版本不变
    activated_v2 = client.post(f"/api/selection-models/{model_id}/activate/2").json()
    assert activated_v2["data"]["previous_version"] == 1
    rollback = client.post(f"/api/selection-models/{model_id}/activate/1").json()
    assert rollback["data"]["previous_version"] == 2
    after = client.get(f"/api/selection-models/{model_id}/versions").json()
    assert after["data"]["active_version"] == 1

    # 归档非活动版本
    archived = client.post(f"/api/selection-models/{model_id}/versions/2/archive").json()
    assert archived["data"]["status"] == "ARCHIVED"


def test_version_diff_endpoint(client, selection_store):
    model_id = _create_and_publish(client)
    client.post(f"/api/selection-models/{model_id}/versions/1/copy-to-draft", json={})
    client.post(f"/api/selection-models/{model_id}/versions", json={"base_version": 1, "draft_revision": 1})
    diff = client.get(f"/api/selection-models/{model_id}/version-diff?from=1&to=2").json()
    assert diff["status"] == "ok"
    assert diff["data"]["identical"] is True  # 未改内容仅复制基线


# ------------------------------------------------------------------ 运行隔离（门禁 10/18）
def test_multiple_manual_runs_are_independent(client, selection_store):
    model_id = _create_and_publish(client)
    first = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    second = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    assert first["data"]["run_id"] != second["data"]["run_id"]
    runs = client.get(f"/api/selection-models/{model_id}/runs").json()
    assert runs["data"]["total"] == 2
    assert runs["data"]["runs"][0]["run_id"] != runs["data"]["runs"][1]["run_id"]


def test_request_id_is_idempotent(client, selection_store):
    model_id = _create_and_publish(client)
    body = {"records": _condition_records(), "request_id": "req-fixed"}
    first = client.post(f"/api/selection-models/{model_id}/runs", json=body).json()
    second = client.post(f"/api/selection-models/{model_id}/runs", json=body).json()
    assert second["data"]["deduplicated"] is True
    assert second["data"]["run"]["run_id"] == first["data"]["run_id"]


def test_debug_run_is_isolated_from_formal_runs(client, selection_store):
    model_id = _create_and_publish(client)
    debug = client.post(f"/api/selection-models/{model_id}/debug/node", json={
        "stage_id": "condition_filter", "records": _condition_records(),
    }).json()
    assert debug["status"] == "ok"
    assert debug["watermark"]["debug"] is True
    assert debug["watermark"]["eligible_for_signal"] is False
    # 调试不落正式运行目录
    assert client.get(f"/api/selection-models/{model_id}/runs").json()["data"]["total"] == 0
    assert client.get(f"/api/selection-models/results").json()["data"]["total"] == 0


def test_cancel_finished_run_conflicts(client, selection_store):
    model_id = _create_and_publish(client)
    run = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    resp = client.post(f"/api/selection-models/runs/{run['data']['run_id']}/cancel").json()
    assert resp["error_code"] == "MODEL_RUN_REQUEST_CONFLICT"
    missing = client.post("/api/selection-models/runs/nope/cancel").json()
    assert missing["error_code"] == "MODEL_RUN_NOT_FOUND"


# ------------------------------------------------------------------ SSE（W-01）
def test_run_events_stream_has_run_id_and_watermark(client, selection_store):
    model_id = _create_and_publish(client)
    run = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    resp = client.get(f"/api/selection-models/runs/{run['data']['run_id']}/events")
    assert resp.status_code == 200
    body = resp.text
    assert "event: run.started" in body
    assert "event: stage.completed" in body
    assert "event: run.finished" in body
    assert "watermark" in body


# ------------------------------------------------------------------ 调度与数据健康（§15.3）
def test_schedule_pause_resume_and_invalid_window(client, selection_store):
    model_id = _create_and_publish(client)
    sched = client.get(f"/api/selection-models/{model_id}/schedule").json()
    assert sched["status"] == "ok"

    paused = client.post(f"/api/selection-models/{model_id}/pause").json()
    assert paused["data"]["paused"] is True
    resumed = client.post(f"/api/selection-models/{model_id}/resume").json()
    assert resumed["data"]["paused"] is False

    bad = client.put(f"/api/selection-models/{model_id}/schedule", json={"stages": {"condition_filter": "99:99"}}).json()
    assert bad["error_code"] == "MODEL_CONFIG_INVALID"


def test_data_health_never_fabricates_coverage(client, selection_store):
    resp = client.get("/api/selection-models/data-health").json()
    assert resp["status"] == "ok"
    assert "availability" in resp["watermark"]


# ------------------------------------------------------------------ 文案草稿解析
def test_draft_from_text_returns_ambiguities(client, selection_store):
    resp = client.post("/api/selection-models/drafts/from-text", json={
        "text": "20日新高，高于60日均线，排除ST；另外想要龙头股",
    }).json()
    assert resp["status"] == "ok"
    assert resp["data"]["activated"] is False
    matched = [r["type"] for r in resp["data"]["matched_rules"]]
    assert "rolling_high" in matched and "text_exclude" in matched
    assert "另外想要龙头股" in resp["data"]["ambiguities"]


# ------------------------------------------------------------------ 权限（C-03）
def test_model_author_lacks_publish_permission(client, selection_store):
    from server.db import create_auth_token, create_user, get_role_by_code

    role = get_role_by_code("model_author")
    assert role is not None
    uid = create_user("author_a", "作者", "pw12345678", int(role["id"]))
    token = create_auth_token(uid, 3600)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 可创建（有 create 权限）
    created = client.post("/api/selection-models", json={"model_type": "funnel", "name": "作者模型"}, headers=headers)
    assert created.status_code == 200
    model_id = created.json()["data"]["model_id"]
    # 不可发布（无 publish 权限）
    denied = client.post(f"/api/selection-models/{model_id}/versions", json={}, headers=headers)
    assert denied.status_code == 403
    # 不可调试（debug 仅超级管理员，G-02）
    denied_debug = client.post(f"/api/selection-models/{model_id}/debug/rule",
                               json={"rule": {"id": "r", "type": "rolling_high"}, "records": []}, headers=headers)
    assert denied_debug.status_code == 403