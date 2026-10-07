# -*- coding: utf-8 -*-
"""阶段 E 核心契约测试（E1～E5 / 发布门禁 12、14、15、16、17、19）。

覆盖：结果研究评估、信号标记 vs 交易策略回测分离、T+1/涨跌停/摩擦成本、未来数据检测、
跟踪观察只追加且重复 Tick 幂等、样本不足不出强结论、建议只读且活动版本变化后 STALE。

隔离策略：全部落盘根重定向到 `tmp_path`（config/cache/pools/reports/backtest），
不触碰真实用户目录。
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def stage_e_store(tmp_path, monkeypatch):
    """把阶段 E 全部落盘根重定向到临时目录。"""
    from core.selection_models import (
        model_evaluator,
        optimization_advisor,
        paths,
        result_assessment,
        run_repository,
    )

    cache_root = tmp_path / "cache"
    pools_root = tmp_path / "pools"
    reports_root = tmp_path / "reports"
    backtest_root = tmp_path / "backtest"
    monkeypatch.setattr(run_repository, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(run_repository, "POOLS_ROOT", pools_root)
    monkeypatch.setattr(paths, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(paths, "REPORTS_ROOT", reports_root)
    monkeypatch.setattr(paths, "BACKTEST_ROOT", backtest_root)
    monkeypatch.setattr(result_assessment, "REPORTS_ROOT", reports_root)
    monkeypatch.setattr(model_evaluator, "REPORTS_ROOT", reports_root)
    monkeypatch.setattr(optimization_advisor, "REPORTS_ROOT", reports_root)
    return tmp_path


def _record(code="600001", *, n=25, start_close=10.0, step=0.1, start="2026-09-01"):
    """构造连续 25 个**交易日**的行情切片（含 OHLC，供 ATR/止损计算）。

    日期序列用 `TradeCalendar` 过滤，保证与 T+N 交易日历一致（跳过周末与法定节假日）。
    """
    from datetime import date, timedelta

    from core.data.sync_engine import TradeCalendar

    day = date.fromisoformat(start)
    dates, closes, opens, highs, lows, volumes = [], [], [], [], [], []
    close = start_close
    while len(dates) < n:
        if day.weekday() < 5 and TradeCalendar.is_trading_day(day):
            prev = close
            close = round(close + step, 4)
            dates.append(day.isoformat())
            opens.append(prev)
            closes.append(close)
            highs.append(round(max(prev, close) * 1.01, 4))
            lows.append(round(min(prev, close) * 0.99, 4))
            volumes.append(1_000_000.0 + len(dates) * 1000)
        day = day + timedelta(days=1)
    return {
        "code": code, "name": "测试股", "dates": dates, "closes": closes,
        "opens": opens, "highs": highs, "lows": lows, "volumes": volumes,
    }


# ------------------------------------------------------------------ E2 基元
def test_normalize_bars_rejects_missing_closes():
    from core.selection_models.market_view import MarketViewError, normalize_bars

    with pytest.raises(MarketViewError):
        normalize_bars({"dates": ["2026-09-01"]})


def test_limit_prices_and_trading_day_shift():
    from core.selection_models.market_view import limit_prices, nth_trading_date

    up, down = limit_prices("300001", 10.0)
    assert (up, down) == (12.0, 8.0)  # 创业板 20%
    # 2026-09-18 为周五，T+1 必须跳过周末落到 2026-09-21（周一）
    assert nth_trading_date("2026-09-18", 1) == "2026-09-21"


def test_detect_future_data_flags_bars_after_as_of():
    from core.selection_models.market_view import detect_future_data, normalize_bars

    bars = normalize_bars(_record())
    future = detect_future_data(bars, bars[5].date)
    assert future and all(day > bars[5].date for day in future)


# ------------------------------------------------------------------ E2 PositionPolicy
def test_position_policy_marks_missing_inputs_without_fake_precision():
    from core.selection_models.position_policy import build_position_policy

    policy = build_position_policy(code="600001", bars=None)  # 无账户规模/成交价/ATR
    assert policy["position"]["shares"] is None
    assert policy["breakeven_price"] is None
    assert set(policy["missing_inputs"]) == {"account_equity", "planned_entry_price", "atr"}
    assert policy["research_only"] is True
    assert policy["risk"]["stop_levels"]["stop_source"]  # D-23 口径来源显式登记


def test_position_policy_sizes_lots_and_breakeven_is_ceiled():
    from core.selection_models.market_view import normalize_bars
    from core.selection_models.position_policy import build_position_policy

    bars = normalize_bars(_record())
    policy = build_position_policy(
        code="600001", bars=bars, account_equity=1_000_000, planned_entry_price=bars[-1].close,
    )
    shares = policy["position"]["shares"]
    assert shares and shares % 100 == 0
    assert policy["position"]["initial_weight"] <= policy["position"]["max_weight"]
    # 保本价向上进位至分位且不低于成交价
    assert policy["breakeven_price"] >= bars[-1].close
    assert round(policy["breakeven_price"], 2) == policy["breakeven_price"]


# ------------------------------------------------------------------ E2 回测（门禁 15）
def test_markout_and_trading_backtest_are_separated():
    from core.selection_models.backtest_service import event_backtest, markout_analysis
    from core.selection_models.market_view import normalize_bars
    from core.selection_models.position_policy import build_position_policy

    bars = normalize_bars(_record(start="2026-09-01", n=25))
    signal_date = bars[-8].date
    policy = build_position_policy(
        code="600001", bars=bars, account_equity=1_000_000, planned_entry_price=bars[-8].close,
    )
    markout = markout_analysis(bars, signal_date=signal_date, horizons=(1, 3))
    assert markout["caliber"] == "close"
    assert {point["horizon"] for point in markout["horizons"]} == {1, 3}
    assert "trading_backtest" not in markout  # 口径严格分离

    backtest = event_backtest(bars, policy, code="600001", signal_date=signal_date)
    assert backtest["trade_history"][0]["action"] == "BUY"
    # T+1：建仓当日不得出现卖出
    assert all(t["date"] != backtest["entry_date"] for t in backtest["trade_history"] if t["action"] == "SELL")
    # 摩擦成本计入：费用参数齐全且换手率为正
    assert backtest["fee_profile"]["commission_rate"] > 0
    assert backtest["metrics"]["turnover_ratio"] > 0


def test_event_backtest_rejects_future_data():
    from core.selection_models.backtest_service import BacktestServiceError, markout_analysis
    from core.selection_models.market_view import normalize_bars

    bars = normalize_bars(_record())
    with pytest.raises(BacktestServiceError):
        markout_analysis(bars, signal_date=bars[0].date, as_of=bars[3].date)


def test_event_backtest_blocks_limit_up_entry():
    from core.selection_models.backtest_service import event_backtest
    from core.selection_models.market_view import normalize_bars
    from core.selection_models.position_policy import build_position_policy

    record = _record()
    record["opens"] = list(record["opens"])
    record["closes"] = list(record["closes"])
    # 令 T+1 开盘一字涨停（= 前收 10%），无法成交
    bars = normalize_bars(record)
    signal_idx = 10
    prev_close = bars[signal_idx].close
    record["dates"] = list(record["dates"])
    # 用重排后的极值构造：把信号日次日的开盘价抬到涨停
    entry_open = round(prev_close * 1.10, 2)
    record["opens"][signal_idx + 1] = entry_open
    record["highs"][signal_idx + 1] = max(entry_open, record["highs"][signal_idx + 1])
    record["closes"][signal_idx + 1] = entry_open
    bars = normalize_bars(record)
    policy = build_position_policy(
        code="600001", bars=bars, account_equity=1_000_000, planned_entry_price=prev_close,
    )
    result = event_backtest(bars, policy, code="600001", signal_date=bars[signal_idx].date)
    assert result["tradable"] is False
    assert result["reason_code"] == "ENTRY_LIMIT_UP_UNFILLABLE"


# ------------------------------------------------------------------ E1 结果研究（门禁 12/17）
def test_result_assessment_research_only_and_traceable(stage_e_store):
    from core.selection_models.market_view import normalize_bars
    from core.selection_models.result_assessment import ResultAssessmentService
    from core.selection_models.run_repository import RunRepository

    repo = RunRepository()
    record = _record(start="2026-09-01", n=25)
    bars = normalize_bars(record)
    run_id = "selection_test_assess_1"
    repo.save_run({
        "run_id": run_id, "model_id": "m1", "model_version": 1, "status": "COMPLETED",
        "signal_trade_date": bars[-8].date, "selected_codes": ["600001"],
    })
    repo.save_run_stages(run_id, [{
        "stage_id": "condition_filter", "input_count": 1, "output_count": 1,
        "result": {"passed_records": [{
            "code": "600001",
            "_funnel": {"stage": "condition_filter", "verdict": "PASS",
                        "rules": [{"rule_id": "r_above_ma", "verdict": "PASS", "observed": 12.0, "expected": ">ma"}]},
        }]},
    }])
    repo.save_run_candidates(run_id, [{"stage_id": "condition_filter", "code": "600001", "verdict": "PASS"}])

    payload = ResultAssessmentService().generate(
        run_id, records_by_code={"600001": record}, account_equity=1_000_000,
    )
    assert payload["research_only"] is True
    assert payload["future_returns_guaranteed"] is False  # 门禁 12
    assert payload["price_caliber"] == "close"

    assessment = payload["assessments"][0]
    assert assessment["signal_id"] == f"{run_id}:600001"
    assert assessment["selection_evidence"]["hit_stages"] == ["condition_filter"]
    assert assessment["selection_evidence"]["evidence_link"]["run_id"] == run_id
    assert assessment["position_policy"]["research_only"] is True  # 门禁 17
    assert assessment["markout_analysis"]["available"] is True
    assert assessment["trading_backtest"]["available"] is True


def test_result_assessment_marks_unavailable_data(stage_e_store):
    from core.selection_models.result_assessment import ResultAssessmentService
    from core.selection_models.run_repository import RunRepository

    repo = RunRepository()
    run_id = "selection_test_assess_2"
    repo.save_run({"run_id": run_id, "model_id": "m1", "model_version": 1, "status": "COMPLETED",
                   "signal_trade_date": "2026-09-18", "selected_codes": ["600001"]})
    payload = ResultAssessmentService().generate(run_id, records_by_code={})
    assessment = payload["assessments"][0]
    assert assessment["data_available"] is False
    assert assessment["markout_analysis"]["available"] is False
    assert assessment["position_policy"]["breakeven_price"] is None


# ------------------------------------------------------------------ E3 跟踪（门禁 14）
def test_tracker_tick_appends_once_and_is_idempotent(stage_e_store):
    from datetime import datetime, timedelta, timezone

    from core.selection_models.market_view import normalize_bars
    from core.selection_models.tracker_scheduler import TrackerScheduler
    from core.selection_models.tracking_service import STATUS_COMPLETED, TrackingService

    shanghai = timezone(timedelta(hours=8))

    def _at(day: str):
        return datetime.fromisoformat(f"{day}T15:00:00").replace(tzinfo=shanghai)

    record = _record(start="2026-09-01", n=25)
    bars = normalize_bars(record)
    signal_date = bars[-8].date
    t1 = bars[-8 + 1].date   # T+1
    t3 = bars[-8 + 3].date   # T+3
    service = TrackingService()
    plan = service.create_plan(
        run_id="run_track_1", model_id="m1", model_version=1, signal_date=signal_date,
        codes=["600001"], base_prices={"600001": bars[-8].close}, periods=[1, 3],
    )
    scheduler = TrackerScheduler(service=service)
    provider = lambda code, target: record  # noqa: E731 - 返回完整切片，观察点自取

    # T+1 到期：仅追加 1 条观察
    first = scheduler.tick(now=_at(t1), records_provider=provider)
    assert first["appended"] == 1
    observations = service.load_observations(plan["tracking_id"])
    assert len(observations) == 1
    assert observations[0]["run_id"] == "run_track_1" and observations[0]["signal_id"]
    assert observations[0]["target_trade_date"] == t1

    # 同一观察点重复 Tick：幂等跳过，不产生重复观察（门禁 14）
    second = scheduler.tick(now=_at(t1), records_provider=provider)
    assert second["appended"] == 0
    assert second["idempotent_skips"] >= 1
    assert len(service.load_observations(plan["tracking_id"])) == 1

    # T+3 到期后补齐；全部周期完成 → COMPLETED
    third = scheduler.tick(now=_at(t3), records_provider=provider)
    assert third["appended"] == 1
    assert len(service.load_observations(plan["tracking_id"])) == 2
    assert service.get_plan(plan["tracking_id"])["status"] == STATUS_COMPLETED


def test_tracker_waits_without_writing_fake_observation(stage_e_store):
    from core.selection_models.tracker_scheduler import TrackerScheduler
    from core.selection_models.tracking_service import TrackingService

    service = TrackingService()
    plan = service.create_plan(
        run_id="run_track_2", model_id="m1", model_version=1, signal_date="2026-09-18",
        codes=["600001"], base_prices={"600001": 10.0}, periods=[1],
    )
    scheduler = TrackerScheduler(service=service)
    result = scheduler.tick(records_provider=lambda code, target: None)  # 水位未就绪
    assert result["appended"] == 0
    assert result["waiting_data"] >= 1
    assert service.load_observations(plan["tracking_id"]) == []


# ------------------------------------------------------------------ E4 模型评价（门禁 16）
def test_evaluation_reports_insufficient_samples(stage_e_store):
    from core.selection_models.model_evaluator import CODE_SAMPLE_INSUFFICIENT, ModelEvaluator

    evaluation = ModelEvaluator().evaluate("m1", 1)
    assert evaluation["status"] == CODE_SAMPLE_INSUFFICIENT
    assert evaluation["strong_conclusion_allowed"] is False
    assert evaluation["conclusion"] == "CONTINUE_OBSERVATION"


def test_evaluation_isolates_versions(stage_e_store):
    from core.selection_models.model_evaluator import ModelEvaluator
    from core.selection_models.tracking_service import TrackingService

    service = TrackingService()
    for version, codes in ((1, ["600001"]), (2, ["600002"])):
        plan = service.create_plan(
            run_id=f"run_v{version}", model_id="m1", model_version=version, signal_date="2026-09-18",
            codes=codes, base_prices={codes[0]: 10.0}, periods=[1],
        )
        service.append_observation(plan["tracking_id"], {
            "code": codes[0], "period": 1, "raw_return_pct": 3.0 if version == 1 else 99.0,
            "target_trade_date": "2026-09-21", "mfe_pct": 1.0, "mae_pct": -1.0,
        })
    evaluation = ModelEvaluator().evaluate("m1", 1)
    assert evaluation["tracked_sample_count"] == 1  # 不混入 v2 样本


# ------------------------------------------------------------------ E5 优化建议（门禁 16/19）
def test_optimization_suggestion_is_read_only_and_stale_on_version_change(stage_e_store):
    from core.selection_models.optimization_advisor import OptimizationAdvisor

    advisor = OptimizationAdvisor()
    low = advisor.suggest("m1", 1)  # 无样本 → 只登记继续观察
    assert low["auto_apply"] is False and low["read_only"] is True
    assert low["suggestions"][0]["suggestion_type"] == "continue_observation"
    assert low["suggestions"][0]["suggested_value"] is None

    fake_eval = {
        "status": "OK",
        "selection_model_evaluation": {"sample_count": 120, "mean_return_pct": -1.5, "up_ratio": 0.3},
        "layer_attrition": {"layers": {"layer_a": {"input_count": 40, "attrition_rate": 0.98}}},
    }
    result = advisor.suggest("m1", 1, evaluation=fake_eval)
    suggestion = result["suggestions"][0]
    assert suggestion["status"] == "pending"
    assert suggestion["source_model_version"] == 1
    assert suggestion["risk_notice"]
    assert suggestion["auto_apply"] is False  # 门禁 16：不得自动改版

    marked = advisor.mark_status("m1", suggestion["suggestion_id"], "accepted", operator="tester")
    assert marked["status"] == "accepted"

    # 活动版本切换后，来源旧版本的建议重新判定 STALE（§22.1）
    stale = advisor.list_suggestions("m1", active_version=2)
    assert stale["suggestions"][0]["status"] == "stale"


def test_optimization_suggestion_mark_rejects_unknown(stage_e_store):
    from core.selection_models.optimization_advisor import OptimizationAdvisor, OptimizationAdvisorError

    advisor = OptimizationAdvisor()
    with pytest.raises(OptimizationAdvisorError):
        advisor.mark_status("m1", "nope", "accepted")
    with pytest.raises(OptimizationAdvisorError):
        advisor.mark_status("m1", "nope", "published")  # 不允许越权到发布