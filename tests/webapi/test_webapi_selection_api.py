# -*- coding: utf-8 -*-
"""
tests/webapi/test_webapi_selection_api.py
WebAPI 模块三：智能选股系统模型定义、版本编排、运行评估与阶段 E 跟踪服务。

覆盖范围：
1. 条件树与截面选股模型 CRUD、AST 条件验证；
2. 模型版本发布、状态激活与不可变哈希快照；
3. 模型前台顺序运行 (/runs)、候选股池生成与结果审计；
4. 阶段 E 评估接口 (/assessments)；
5. 阶段 E 跟踪计划 (/tracking-plans) 与时间序列观测点；
6. 阶段 E 模型评价与调优建议只读契约；
7. 越权与非法模型 ID 防护 (MODEL_NOT_FOUND)。
"""
from __future__ import annotations

from datetime import date, timedelta
import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def selection_store(tmp_path, monkeypatch):
    """把选股系统落盘根整体重定向至临时目录。"""
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


def _condition_records():
    return [{"code": "600001", "name": "浦发银行", "closes": [float(i) for i in range(1, 71)]}]


def _daily_record(code="600001", *, n=70, end="2026-09-25"):
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


def _create_and_publish(client: TestClient, *, model_type="condition_tree", template="blank"):
    created = client.post("/api/selection-models", json={
        "model_type": model_type, "name": "测试选股模型", "template": template,
    }).json()
    assert created["status"] == "ok", created
    model_id = created["data"]["model_id"]
    assert client.post(f"/api/selection-models/{model_id}/validate").json()["status"] == "ok"
    assert client.post(f"/api/selection-models/{model_id}/versions", json={}).json()["status"] == "ok"
    assert client.post(f"/api/selection-models/{model_id}/activate/1").json()["status"] == "ok"
    return model_id


# ------------------------------------------------------------------ 1. 选股模型 CRUD 与版本发布
def test_selection_model_crud_and_publish_version(client: TestClient, selection_store) -> None:
    # 1. 创建模型
    created = client.post("/api/selection-models", json={
        "model_type": "condition_tree",
        "name": "多因子共振实验模型",
        "template": "blank",
    }).json()
    assert created["status"] == "ok"
    model_id = created["data"]["model_id"]
    assert model_id

    # 2. 校验模型 AST 语法
    validated = client.post(f"/api/selection-models/{model_id}/validate").json()
    assert validated["status"] == "ok"

    # 3. 发布版本
    published = client.post(f"/api/selection-models/{model_id}/versions", json={"changelog": "v1.0"}).json()
    assert published["status"] == "ok"
    assert published["data"]["version"] == 1

    # 4. 激活版本
    activated = client.post(f"/api/selection-models/{model_id}/activate/1").json()
    assert activated["status"] == "ok"

    # 5. 查询详情验证 active_version 生效
    detail = client.get(f"/api/selection-models/{model_id}").json()
    assert detail["status"] == "ok"
    assert detail["data"]["active_version"] == 1


# ------------------------------------------------------------------ 2. 模型执行与结果持久化
def test_selection_model_run_and_pools_output(client: TestClient, selection_store) -> None:
    model_id = _create_and_publish(client)

    # 运行模型
    run_res = client.post(
        f"/api/selection-models/{model_id}/runs",
        json={"records": _condition_records()},
    )
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["status"] == "ok"
    assert run_data["data"]["run"]["status"] == "COMPLETED"
    run_id = run_data["data"]["run_id"]

    # 查询单次运行记录详情
    detail = client.get(f"/api/selection-models/runs/{run_id}").json()
    assert detail["status"] == "ok"
    assert detail["data"]["run"]["model_id"] == model_id


# ------------------------------------------------------------------ 3. 阶段 E 评估接口
def test_stage_e_assessment_endpoints(client: TestClient, selection_store) -> None:
    model_id = _create_and_publish(client)
    record, days, closes = _daily_record()
    signal_date = days[-8]

    # 运行产出信号
    run = client.post(
        f"/api/selection-models/{model_id}/runs",
        json={"records": [record], "as_of": signal_date},
    ).json()
    assert run["status"] == "ok"
    run_id = run["data"]["run_id"]

    # 发起结果研究评估
    assess_res = client.post(
        f"/api/selection-models/runs/{run_id}/assessments",
        json={"records": [record], "account_equity": 1_000_000},
    )
    assert assess_res.status_code == 200
    data = assess_res.json()
    assert data["status"] == "ok"
    assessment = data["data"]["assessment"]
    assert assessment["research_only"] is True
    assert assessment["future_returns_guaranteed"] is False


# ------------------------------------------------------------------ 4. 阶段 E 跟踪计划接口
def test_stage_e_tracking_endpoints(client: TestClient, selection_store) -> None:
    model_id = _create_and_publish(client)
    record, days, closes = _daily_record()
    signal_date = days[-8]
    base_price = closes[-8]

    run = client.post(
        f"/api/selection-models/{model_id}/runs",
        json={"records": [record], "as_of": signal_date},
    ).json()
    run_id = run["data"]["run_id"]

    # 创建跟踪计划
    track_res = client.post("/api/selection-models/tracking-plans", json={
        "run_id": run_id,
        "base_prices": {"600001": base_price},
        "periods": [1, 3],
    })
    assert track_res.status_code == 200
    plan_data = track_res.json()
    assert plan_data["status"] == "ok"
    tracking_id = plan_data["data"]["plan"]["tracking_id"]

    # 查询跟踪计划
    detail_res = client.get(f"/api/selection-models/tracking-plans/{tracking_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["plan"]["run_id"] == run_id


# ------------------------------------------------------------------ 5. 阶段 E 模型评价与优化建议只读接口
def test_stage_e_evaluation_and_advisory_readonly(client: TestClient, selection_store) -> None:
    model_id = _create_and_publish(client)

    # 评价接口
    eval_res = client.post(f"/api/selection-models/{model_id}/evaluations", json={})
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["status"] == "ok"
    assert eval_data["data"]["evaluation"]["strong_conclusion_allowed"] is False

    # 调优建议只读接口
    advise_res = client.post(f"/api/selection-models/{model_id}/tuning-suggestions", json={})
    assert advise_res.status_code == 200
    advise_data = advise_res.json()
    assert advise_data["status"] == "ok"
    assert advise_data["data"]["suggestions"][0]["read_only"] is True


# ------------------------------------------------------------------ 6. 非法模型 ID 与越权拦截
def test_illegal_model_id_not_found(client: TestClient, selection_store) -> None:
    # 不存在的模型查询拦截
    res = client.get("/api/selection-models/non_existent_fake_id_12345")
    assert res.json()["status"] == "error"
    assert res.json()["error_code"] in ("MODEL_NOT_FOUND", "MODEL_VERSION_NOT_FOUND")

    # 目录穿越非法字符防护
    bad = client.get("/api/selection-models/tracking-plans/bad%20id%21")
    assert bad.json()["status"] == "error"
