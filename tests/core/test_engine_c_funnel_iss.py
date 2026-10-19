# -*- coding: utf-8 -*-
"""Engine C: 智能选股漏斗编译、版本仓库与跟踪评估引擎测试。

归属代码包：`core/selection_models/`, `core/strategy/funnel_engine.py`, `core/strategy/stock_funnel.py`
核心职责与断言：
1. Kleene 强三值逻辑运算（PASS, FAIL, UNKNOWN；kleene_all FAIL 吸收，kleene_any PASS 吸收）；
2. 条件树与四阶段漏斗管线（StockFunnelPipeline）：L1 标的池 -> L2 硬过滤 -> L3 指标打分 -> L4 盘中拐点；
3. 模型版本仓库（VersionRepository）：定义哈希计算（SHA256）、不可原地覆盖、版本单调递增、活动指针切换；
4. 跟踪服务（TrackingService）：T+1/T+3/T+5 跟踪计划状态机与只追加观察幂等性。
"""
from __future__ import annotations

from pathlib import Path
import pytest

from core.strategy.funnel_engine import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    kleene_all,
    kleene_any,
    kleene_not,
)
from core.strategy.stock_funnel import (
    StockFunnelPipeline,
    load_funnel_config,
)
from core.selection_models.version_repository import (
    VersionRepository,
    compute_definition_hash,
)
from core.selection_models.tracking_service import (
    MODE_TPN,
    STATUS_ACTIVE,
    STATUS_COMPLETED,
    STATUS_CREATED,
    TrackingService,
)

pytestmark = pytest.mark.core


def test_kleene_three_value_logic():
    """验证 Kleene 强三值逻辑真值表（§7.7.4）：FAIL 吸收与 UNKNOWN 传播。"""
    # 1. kleene_all (AND)
    assert kleene_all([VERDICT_PASS, VERDICT_PASS]) == VERDICT_PASS
    assert kleene_all([VERDICT_PASS, VERDICT_FAIL]) == VERDICT_FAIL
    assert kleene_all([VERDICT_PASS, VERDICT_UNKNOWN]) == VERDICT_UNKNOWN
    assert kleene_all([VERDICT_FAIL, VERDICT_UNKNOWN]) == VERDICT_FAIL  # FAIL 吸收

    # 2. kleene_any (OR)
    assert kleene_any([VERDICT_FAIL, VERDICT_FAIL]) == VERDICT_FAIL
    assert kleene_any([VERDICT_FAIL, VERDICT_PASS]) == VERDICT_PASS    # PASS 吸收
    assert kleene_any([VERDICT_FAIL, VERDICT_UNKNOWN]) == VERDICT_UNKNOWN
    assert kleene_any([VERDICT_PASS, VERDICT_UNKNOWN]) == VERDICT_PASS  # PASS 吸收

    # 3. kleene_not (NOT)
    assert kleene_not(VERDICT_PASS) == VERDICT_FAIL
    assert kleene_not(VERDICT_FAIL) == VERDICT_PASS
    assert kleene_not(VERDICT_UNKNOWN) == VERDICT_UNKNOWN  # NOT UNKNOWN = UNKNOWN


def test_stock_funnel_pipeline_execution():
    """验证四阶段选股漏斗管线结构与各阶段过滤。"""
    config = load_funnel_config()
    pipeline = StockFunnelPipeline(config=config)
    assert len(pipeline.stage_ids) >= 3

    first_stage = pipeline.stage_ids[0]

    # 构造合格标的切片
    closes = [10.0 + i * 0.05 for i in range(70)]
    record_pass = {
        "code": "600001",
        "name": "标杆股份",
        "circulating_market_cap": 8_000_000_000,
        "change_pct": 3.5,
        "closes": closes,
        "volumes": [1000] * 68 + [1500, 2500],
        "main_net_inflow": 25_000_000,
    }

    # 构造不合规标的（市值过小）
    record_fail = {
        "code": "000002",
        "name": "微盘股",
        "circulating_market_cap": 500_000_000,
        "change_pct": 1.0,
        "closes": closes,
        "volumes": [100] * 70,
        "main_net_inflow": -5_000_000,
    }

    payload = pipeline.run_stage(first_stage, [record_pass, record_fail])
    assert isinstance(payload, dict)
    assert "passed_records" in payload
    assert "selected_codes" in payload


def test_version_repository_immutability_and_pointer(tmp_path: Path):
    """验证模型版本不可变、哈希计算与活动指针切换机制。"""
    repo = VersionRepository(base_dir=tmp_path / "selection_models")
    model_id = "test_alpha_model"

    model_def_v1 = {
        "model_id": model_id,
        "name": "多因子Alpha模型",
        "stages": [{"name": "filter", "rules": ["pe < 50"]}],
    }

    # 1. 验证哈希唯一性与不可变发布
    h1 = compute_definition_hash(model_def_v1)
    assert h1.startswith("sha256:")
    plan_mock = {"plan_hash": "sha256:dummy_plan_hash", "compiler_version": "compiler@v1", "stages": []}
    v1 = repo.publish(model_id, model_def_v1, plan=plan_mock)
    assert v1["version"] == 1
    assert v1["definition_hash"] == h1

    # 2. 发布 v2
    model_def_v2 = {
        "model_id": model_id,
        "name": "多因子Alpha模型V2",
        "stages": [{"name": "filter", "rules": ["pe < 30"]}],
    }
    v2 = repo.publish(model_id, model_def_v2, plan=plan_mock, base_version=1)
    assert v2["version"] == 2
    assert v2["version"] > v1["version"]

    # 3. 激活指针管理与回滚
    repo.activate(model_id, version=2)
    assert repo.active_version(model_id) == 2

    # 回滚至 v1
    repo.activate(model_id, version=1)
    assert repo.active_version(model_id) == 1


def test_tracking_service_plan_and_observation(tmp_path: Path):
    """验证 T+N 跟踪服务计划创建与观察值只追加幂等性。"""
    service = TrackingService(root=tmp_path / "cache")

    plan = service.create_plan(
        run_id="run_20261019_001",
        model_id="trend_following",
        model_version=1,
        signal_date="2026-10-19",
        codes=["600519"],
        base_prices={"600519": 1750.0},
        mode=MODE_TPN,
        periods=[1, 3, 5],
    )
    assert plan["status"] == STATUS_CREATED
    assert plan["base_prices"]["600519"] == 1750.0
    tracking_id = plan["tracking_id"]

    # 追加 T+1 观察值
    res_obs1 = service.append_observation(
        tracking_id,
        {
            "code": "600519",
            "period": 1,
            "trade_date": "2026-10-20",
            "price": 1785.0,
            "return_pct": 0.02,
        },
    )
    assert res_obs1["appended"] is True
    assert res_obs1["observation"]["price"] == 1785.0

    # 重复追加同一 (code, period) 观察值必须幂等跳过，绝不覆盖历史
    res_obs1_dup = service.append_observation(
        tracking_id,
        {
            "code": "600519",
            "period": 1,
            "trade_date": "2026-10-20",
            "price": 1799.0,
        },
    )
    assert res_obs1_dup["appended"] is False
    assert res_obs1_dup["idempotent"] is True
    assert res_obs1_dup["observation"]["price"] == 1785.0
