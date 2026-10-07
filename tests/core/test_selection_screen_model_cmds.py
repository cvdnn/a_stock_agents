# -*- coding: utf-8 -*-
"""ISS「screen-model」阶段 E CLI 契约测试（assess / track / evaluate / tune）。

覆盖：
- 解析器接受各规范 argv；
- 缺输入即失败关闭（`MODEL_RUN_NOT_FOUND` / `MODEL_DATA_MISSING` / `MODEL_VERSION_NOT_FOUND`），
  不产出任何伪造的候选、价格或指标；
- 样本不足返回 `degraded` + `EVALUATION_SAMPLE_INSUFFICIENT`（不出强结论）；
- 跟踪 Tick 水位未就绪报 `WAITING_DATA` 且不写伪观察值；
- 一条离线 happy path（临时 RunRepository / TrackingService / VersionRepository）。

隔离策略：全部落盘根重定向到 `tmp_path`，且 tracker 日历库指向不存在的临时路径，
保证**完全离线、可重复**。
"""
from __future__ import annotations

import json

import pytest


# ------------------------------------------------------------------ fixture / helpers
@pytest.fixture()
def screen_model_store(tmp_path, monkeypatch):
    """把阶段 E 全部落盘根重定向到临时目录，并让交易日历库缺失（走静态兜底）。"""
    from core.selection_models import (
        model_evaluator,
        optimization_advisor,
        paths,
        result_assessment,
        run_repository,
        tracker_scheduler,
        version_repository,
    )

    cache_root = tmp_path / "cache"
    monkeypatch.setattr(run_repository, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(run_repository, "POOLS_ROOT", tmp_path / "pools")
    monkeypatch.setattr(paths, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(paths, "REPORTS_ROOT", tmp_path / "reports")
    monkeypatch.setattr(result_assessment, "REPORTS_ROOT", tmp_path / "reports")
    monkeypatch.setattr(model_evaluator, "REPORTS_ROOT", tmp_path / "reports")
    monkeypatch.setattr(optimization_advisor, "REPORTS_ROOT", tmp_path / "reports")
    monkeypatch.setattr(version_repository, "DEFAULT_BASE_DIR", tmp_path / "config")
    monkeypatch.setattr(tracker_scheduler, "DB_PATH", tmp_path / "missing.db")
    return tmp_path


def _parse(argv):
    from core.cli import build_parser

    return build_parser().parse_args(argv)


def _cmd(argv):
    from core.commands.screen_model_cmds import cmd_screen_model

    return cmd_screen_model(_parse(argv))


def _record(code="600001", *, n=25, start_close=10.0, step=0.1, start="2026-09-01"):
    """构造连续 N 个交易日的行情切片（含 OHLC 与成交量）。"""
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


def _save_run(run_id="run_cli_1", *, codes=("600001",), signal_date="2026-09-18", model_id="m1", version=1):
    from core.selection_models.run_repository import RunRepository

    repo = RunRepository()
    repo.save_run({
        "run_id": run_id, "model_id": model_id, "model_version": version, "status": "COMPLETED",
        "signal_trade_date": signal_date, "selected_codes": list(codes),
    })
    return repo


def _assert_fail_closed(exit_info, code, capsys):
    assert exit_info.value.code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["error_code"] == code
    return payload


# ------------------------------------------------------------------ 解析器
def test_parser_accepts_canonical_argv():
    a = _parse([
        "screen-model", "assess", "--run", "r1", "--records", "rec.json",
        "--account-equity", "1000000", "--risk-per-trade-pct", "1.0", "--initial-cash", "1000000",
        "--as-of", "2026-09-18", "--horizons", "1,3,5,10,20", "--json",
    ])
    assert a.command == "screen-model" and a.screen_model_cmd == "assess"
    assert a.run == "r1" and a.horizons == "1,3,5,10,20" and a.json is True

    b = _parse([
        "screen-model", "track", "create", "--run", "r1", "--codes", "600001",
        "--mode", "realtime", "--periods", "1,3", "--benchmark", "sh000001",
        "--base-prices-json", '{"600001": 10.0}', "--json",
    ])
    assert b.screen_model_cmd == "track" and b.screen_model_track_cmd == "create"
    assert b.mode == "realtime" and b.base_prices_json == '{"600001": 10.0}'

    c = _parse(["screen-model", "track", "status", "--tracking-id", "track_abc", "--json"])
    assert c.screen_model_track_cmd == "status" and c.tracking_id == "track_abc"

    d = _parse(["screen-model", "track", "tick", "--json"])
    assert d.screen_model_track_cmd == "tick"

    e = _parse([
        "screen-model", "evaluate", "--model", "m1", "--version", "2", "--period", "5",
        "--min-samples", "30", "--min-observation-days", "20", "--benchmark", "沪深300", "--json",
    ])
    assert e.screen_model_cmd == "evaluate" and e.version == 2 and e.min_samples == 30

    f = _parse(["screen-model", "tune", "--model", "m1", "--version", "2", "--period", "5", "--json"])
    assert f.screen_model_cmd == "tune" and f.model == "m1" and f.period == 5


def test_dispatch_without_subcommand_fails_closed(capsys):
    from core.commands.screen_model_cmds import cmd_screen_model

    with pytest.raises(SystemExit) as exit_info:
        cmd_screen_model(_parse(["screen-model", "--json"]))
    assert exit_info.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "MODEL_CONFIG_INVALID"


# ------------------------------------------------------------------ assess
def test_assess_fails_closed_without_run(screen_model_store, capsys):
    with pytest.raises(SystemExit) as exit_info:
        _cmd(["screen-model", "assess", "--run", "missing_run", "--json"])
    payload = _assert_fail_closed(exit_info, "MODEL_RUN_NOT_FOUND", capsys)
    assert payload["data"] is None  # 不产出任何评估数值


def test_assess_fails_closed_without_records(screen_model_store, capsys):
    _save_run("run_assess_no_records")
    with pytest.raises(SystemExit) as exit_info:
        _cmd(["screen-model", "assess", "--run", "run_assess_no_records", "--json"])
    payload = _assert_fail_closed(exit_info, "MODEL_DATA_MISSING", capsys)
    assert payload["data"] is None


def test_assess_happy_path_is_research_only(screen_model_store, capsys):  # noqa: ARG001
    record = _record(start="2026-09-01", n=25)
    run_id = "run_assess_ok"
    _save_run(run_id, signal_date=record["dates"][-8], codes=(record["code"],))
    records_file = screen_model_store / "records.json"
    records_file.write_text(json.dumps([record]), encoding="utf-8")

    _cmd([
        "screen-model", "assess", "--run", run_id,
        "--records", str(records_file), "--account-equity", "1000000", "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assessment = payload["data"]["assessment"]
    assert assessment["research_only"] is True
    assert assessment["future_returns_guaranteed"] is False
    assert assessment["price_caliber"] == "close"
    assert payload["data"]["assessment"]["assessments"][0]["code"] == record["code"]


# ------------------------------------------------------------------ track
def test_track_create_fails_closed_without_run(screen_model_store, capsys):
    with pytest.raises(SystemExit) as exit_info:
        _cmd(["screen-model", "track", "create", "--run", "missing_run", "--json"])
    _assert_fail_closed(exit_info, "MODEL_RUN_NOT_FOUND", capsys)


def test_track_create_fails_closed_without_base_prices(screen_model_store, capsys):
    _save_run("run_track_no_price")
    with pytest.raises(SystemExit) as exit_info:
        _cmd(["screen-model", "track", "create", "--run", "run_track_no_price", "--json"])
    _assert_fail_closed(exit_info, "MODEL_DATA_MISSING", capsys)


def test_track_create_and_status_happy_path(screen_model_store, capsys):
    _save_run("run_track_ok", codes=("600001",))
    _cmd([
        "screen-model", "track", "create", "--run", "run_track_ok",
        "--base-prices-json", '{"600001": 10.0}', "--json",
    ])
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "ok"
    tracking_id = created["data"]["plan"]["tracking_id"]
    assert created["data"]["plan"]["base_prices"] == {"600001": 10.0}

    _cmd(["screen-model", "track", "status", "--tracking-id", tracking_id, "--json"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "ok"
    assert summary["data"]["plan"]["tracking_id"] == tracking_id
    assert summary["data"]["observations"] == []


def test_track_status_fails_closed_for_unknown_plan(screen_model_store, capsys):
    with pytest.raises(SystemExit) as exit_info:
        _cmd(["screen-model", "track", "status", "--tracking-id", "track_missing", "--json"])
    _assert_fail_closed(exit_info, "TRACKING_PLAN_NOT_FOUND", capsys)


def test_track_tick_waiting_data_writes_no_observation(screen_model_store, capsys):
    from core.selection_models.tracking_service import TrackingService

    service = TrackingService()
    plan = service.create_plan(
        run_id="run_tick_1", model_id="m1", model_version=1, signal_date="2020-01-02",
        codes=["600001"], base_prices={"600001": 10.0}, periods=[1],
    )
    # 水位未就绪：tick 无行情来源 → 只报等待，不落任何观察值
    _cmd(["screen-model", "track", "tick", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "WAITING_DATA"
    assert payload["error_code"] == "TRACKING_WAITING_DATA"
    assert payload["data"]["appended"] == 0
    assert service.load_observations(plan["tracking_id"]) == []


# ------------------------------------------------------------------ evaluate
def test_evaluate_fails_closed_without_active_version(screen_model_store, capsys):
    with pytest.raises(SystemExit) as exit_info:
        _cmd(["screen-model", "evaluate", "--model", "m1", "--json"])
    _assert_fail_closed(exit_info, "MODEL_VERSION_NOT_FOUND", capsys)


def test_evaluate_sample_insufficient_is_degraded(screen_model_store, capsys):
    _cmd(["screen-model", "evaluate", "--model", "m1", "--version", "1", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "degraded"
    assert payload["error_code"] == "EVALUATION_SAMPLE_INSUFFICIENT"
    evaluation = payload["data"]["evaluation"]
    assert evaluation["strong_conclusion_allowed"] is False
    assert evaluation["conclusion"] == "CONTINUE_OBSERVATION"
    # 不臆造任何指标：样本不足时评价体不携带收益均值等结论性数值
    assert "mean_return_pct" not in evaluation
    assert evaluation["selection_model_evaluation"]["available"] is False


# ------------------------------------------------------------------ tune
def test_tune_fails_closed_without_active_version(screen_model_store, capsys):
    with pytest.raises(SystemExit) as exit_info:
        _cmd(["screen-model", "tune", "--model", "m1", "--json"])
    _assert_fail_closed(exit_info, "MODEL_VERSION_NOT_FOUND", capsys)


def test_tune_returns_read_only_suggestions(screen_model_store, capsys):
    _cmd(["screen-model", "tune", "--model", "m1", "--version", "1", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    result = payload["data"]
    assert result["read_only"] is True and result["auto_apply"] is False
    suggestion = result["suggestions"][0]
    assert suggestion["suggestion_type"] == "continue_observation"
    assert suggestion["suggested_value"] is None
    assert suggestion["auto_apply"] is False