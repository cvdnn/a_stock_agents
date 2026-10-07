# -*- coding: utf-8 -*-
"""批次四（阶段 E）选股 API 集成测试（§15.3 / §22.3 / 发布门禁 12、14、16、17、19）。

覆盖：个股评估接口、跟踪计划与观察序列接口、模型评价接口、优化建议只读与状态标记、
跟踪/评价/激活权限相互独立、非法标识符不产生越权路径。
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.fixture()
def stage_e_api_store(tmp_path, monkeypatch):
    """把选股系统全部落盘根（含阶段 E 的 reports/backtest）重定向到临时目录。"""
    from core.selection_models import (
        catalog,
        definition_repository,
        model_evaluator,
        optimization_advisor,
        paths,
        result_assessment,
        run_repository,
        signal_latch,
        tracking_service,
        version_repository,
    )

    config_root = tmp_path / "config"
    cache_root = tmp_path / "cache"
    pools_root = tmp_path / "pools"
    lock_root = tmp_path / "locks"
    reports_root = tmp_path / "reports"
    backtest_root = tmp_path / "backtest"
    monkeypatch.setattr(definition_repository, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(definition_repository, "DEFAULT_LOCK_DIR", lock_root)
    monkeypatch.setattr(version_repository, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(run_repository, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(run_repository, "POOLS_ROOT", pools_root)
    monkeypatch.setattr(catalog, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(signal_latch, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(tracking_service.paths, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(paths, "REPORTS_ROOT", reports_root)
    monkeypatch.setattr(paths, "BACKTEST_ROOT", backtest_root)
    monkeypatch.setattr(result_assessment, "REPORTS_ROOT", reports_root)
    monkeypatch.setattr(model_evaluator, "REPORTS_ROOT", reports_root)
    monkeypatch.setattr(optimization_advisor, "REPORTS_ROOT", reports_root)
    return tmp_path


def _daily_record(code="600001", *, n=70, end="2026-09-25"):
    """构造 n 个交易日的行情切片（日期经交易日历过滤），返回 (record, days, closes)。"""
    from core.data.sync_engine import TradeCalendar

    day = date.fromisoformat(end)
    days = []
    while len(days) < n:
        if day.weekday() < 5 and TradeCalendar.is_trading_day(day):
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.sort()
    closes = [round(10.0 + 0.05 * i, 4) for i in range(n)]
    record = {
        "code": code, "name": "测试股", "dates": days, "closes": closes,
        "opens": [round(c - 0.02, 4) for c in closes],
        "highs": [round(c * 1.01, 4) for c in closes],
        "lows": [round(c * 0.99, 4) for c in closes],
        "volumes": [1_000_000.0 + i * 100 for i in range(n)],
    }
    return record, days, closes


def _create_publish_activate(client, *, model_type="condition_tree", template="blank"):
    created = client.post("/api/selection-models", json={
        "model_type": model_type, "name": "阶段E模型", "template": template,
    }).json()
    assert created["status"] == "ok", created
    model_id = created["data"]["model_id"]
    assert client.post(f"/api/selection-models/{model_id}/validate").json()["status"] == "ok"
    assert client.post(f"/api/selection-models/{model_id}/versions", json={}).json()["status"] == "ok"
    assert client.post(f"/api/selection-models/{model_id}/activate/1").json()["status"] == "ok"
    return model_id


def _run_with_signal(client, model_id):
    record, days, closes = _daily_record()
    signal_date = days[-8]
    run = client.post(f"/api/selection-models/{model_id}/runs",
                      json={"records": [record], "as_of": signal_date}).json()
    assert run["status"] == "ok", run
    assert run["data"]["run"]["selected_codes"] == ["600001"]
    return record, days, closes, signal_date, run["data"]["run_id"]


# ------------------------------------------------------------------ E1 结果研究（门禁 12/17）
def test_assessment_endpoints_are_research_only(client, stage_e_api_store):
    model_id = _create_publish_activate(client)
    record, days, closes, signal_date, run_id = _run_with_signal(client, model_id)

    generated = client.post(
        f"/api/selection-models/runs/{run_id}/assessments",
        json={"records": [record], "account_equity": 1_000_000},
    ).json()
    assert generated["status"] == "ok", generated
    assessment = generated["data"]["assessment"]
    assert assessment["research_only"] is True
    assert assessment["future_returns_guaranteed"] is False  # 门禁 12
    item = assessment["assessments"][0]
    assert item["signal_id"] == f"{run_id}:600001"
    assert item["position_policy"]["research_only"] is True  # 门禁 17
    assert item["selection_evidence"]["evidence_link"]["run_id"] == run_id

    fetched = client.get(f"/api/selection-models/runs/{run_id}/assessments").json()
    assert fetched["data"]["assessment"]["assessments"][0]["code"] == "600001"

    # 缺行情切片即失败关闭，不伪造数值
    empty = client.post(f"/api/selection-models/runs/{run_id}/assessments", json={"records": []}).json()
    assert empty["error_code"] == "MODEL_DATA_MISSING"
    assert empty["watermark"]["eligible_for_signal"] is False


# ------------------------------------------------------------------ E3 跟踪（门禁 14）
def test_tracking_plan_and_observation_endpoints(client, stage_e_api_store):
    model_id = _create_publish_activate(client)
    record, days, closes, signal_date, run_id = _run_with_signal(client, model_id)
    base_price = closes[-8]

    created = client.post("/api/selection-models/tracking-plans", json={
        "run_id": run_id, "base_prices": {"600001": base_price}, "periods": [1, 3],
    }).json()
    assert created["status"] == "ok", created
    tracking_id = created["data"]["plan"]["tracking_id"]
    assert created["data"]["plan"]["run_id"] == run_id

    plan = client.get(f"/api/selection-models/tracking-plans/{tracking_id}").json()
    assert plan["data"]["plan"]["base_prices"]["600001"] == base_price
    observations = client.get(f"/api/selection-models/tracking-plans/{tracking_id}/observations").json()
    assert observations["data"]["observations"] == []

    # 缺基准价 → 失败关闭，不接受虚构基准
    missing = client.post("/api/selection-models/tracking-plans",
                          json={"run_id": run_id, "base_prices": {}}).json()
    assert missing["error_code"] == "MODEL_DATA_MISSING"

    # 非法标识符不产生越权路径（目录穿越防护）
    bad = client.get("/api/selection-models/tracking-plans/bad%20id%21").json()
    assert bad["status"] == "error"


# ------------------------------------------------------------------ E4/E5 评价与调优（门禁 16/19）
def test_evaluation_and_tuning_endpoints(client, stage_e_api_store):
    model_id = _create_publish_activate(client)
    _run_with_signal(client, model_id)

    evaluation = client.post(f"/api/selection-models/{model_id}/evaluations", json={}).json()
    assert evaluation["status"] == "ok"
    assert evaluation["data"]["evaluation"]["status"] == "EVALUATION_SAMPLE_INSUFFICIENT"
    assert evaluation["data"]["evaluation"]["strong_conclusion_allowed"] is False  # 门禁 16
    assert evaluation["watermark"]["eligible_for_signal"] is False
    evaluation_id = evaluation["data"]["evaluation"]["evaluation_id"]

    fetched = client.get(f"/api/selection-models/{model_id}/evaluations/{evaluation_id}").json()
    assert fetched["data"]["evaluation"]["model_version"] == 1

    tuning = client.post(f"/api/selection-models/{model_id}/tuning-suggestions", json={}).json()
    assert tuning["status"] == "ok"
    suggestion = tuning["data"]["suggestions"][0]
    assert suggestion["suggestion_type"] == "continue_observation"
    assert suggestion["auto_apply"] is False and suggestion["read_only"] is True  # 门禁 16

    marked = client.post(
        f"/api/selection-models/{model_id}/tuning-suggestions/{suggestion['suggestion_id']}/status",
        json={"status": "accepted"},
    ).json()
    assert marked["data"]["suggestion"]["status"] == "accepted"

    listed = client.get(f"/api/selection-models/{model_id}/tuning-suggestions").json()
    assert listed["data"]["suggestions"][0]["status"] == "accepted"

    # 不允许越权到发布：标记状态只接受 accepted / ignored
    rejected = client.post(
        f"/api/selection-models/{model_id}/tuning-suggestions/{suggestion['suggestion_id']}/status",
        json={"status": "published"},
    ).json()
    assert rejected["error_code"] == "MODEL_CONFIG_INVALID"


# ------------------------------------------------------------------ 权限（§22.3）
def test_stage_e_permissions_are_independent(client, anon_client, stage_e_api_store):
    model_id = _create_publish_activate(client)
    record, days, closes, signal_date, run_id = _run_with_signal(client, model_id)

    # 匿名一律 401
    assert anon_client.post(f"/api/selection-models/runs/{run_id}/assessments", json={}).status_code == 401
    assert anon_client.post("/api/selection-models/tracking-plans", json={"run_id": run_id}).status_code == 401
    assert anon_client.post(f"/api/selection-models/{model_id}/evaluations", json={}).status_code == 401
    assert anon_client.post(f"/api/selection-models/{model_id}/tuning-suggestions", json={}).status_code == 401

    # 投研用户（researcher）：仅有 selection.view + selection.track
    from server.db import create_auth_token, create_user, get_role_by_code

    role = get_role_by_code("researcher")
    assert role is not None
    uid = create_user("researcher_e", "投研", "pw12345678", int(role["id"]))
    headers = {"Authorization": f"Bearer {create_auth_token(uid, 3600)['token']}"}

    # 可跟踪（track）
    track = client.post("/api/selection-models/tracking-plans", headers=headers,
                        json={"run_id": run_id, "base_prices": {"600001": closes[-8]}})
    assert track.status_code == 200 and track.json()["status"] == "ok"
    # 不可评价（无 evaluate）
    assert client.post(f"/api/selection-models/{model_id}/evaluations", json={}, headers=headers).status_code == 403
    assert client.post(f"/api/selection-models/{model_id}/tuning-suggestions", json={}, headers=headers).status_code == 403
    # 不可激活生产版本（无 activate）
    assert client.post(f"/api/selection-models/{model_id}/activate/1", headers=headers).status_code == 403
    # 可查看评估（view）
    assert client.get(f"/api/selection-models/runs/{run_id}/assessments", headers=headers).status_code == 200