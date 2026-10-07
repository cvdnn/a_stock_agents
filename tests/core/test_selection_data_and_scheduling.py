# -*- coding: utf-8 -*-
"""批次二（M-03 数据与调度）核心契约测试：B1～B7。

覆盖：Scheduler Tick + 交易日历门控、运行锁（`model_id+trade_date`）、分层幂等键、
Signal Latch 窗口收敛锁存、跨交易日状态恢复、落盘目录规范与淘汰、
`UniverseWatermark` 分层分母 + 覆盖率硬门禁、W-09/W-10 市值单位与缺失置零。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

try:
    from zoneinfo import ZoneInfo

    _SHANGHAI = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    _SHANGHAI = timezone(timedelta(hours=8))

from core.data.data_assembler import (
    COVERAGE_REQUIRED_FIELDS,
    build_universe_watermark,
    layer_denominator,
)
from core.selection_models import schemas
from core.selection_models.model_compiler import compile_definition
from core.selection_models.paths import (
    CACHE_ROOT,
    LOG_ROOT,
    POOLS_ROOT,
    TEMP_ROOT,
    run_inputs_dir,
    signal_date_dir,
)
from core.selection_models.run_lock import RunLockManager
from core.selection_models.run_repository import RunRepository
from core.selection_models.scheduler import (
    STATUS_IDLE,
    STATUS_SKIPPED_NON_TRADING_DAY,
    SelectionScheduler,
    parse_schedule,
)
from core.selection_models.signal_latch import STATUS_LATCHED, STATUS_PENDING, SignalLatch
from core.strategy.stock_funnel import DEFAULT_CONFIG_PATH

TRADING_DAY = "2026-09-21"
WEEKEND = "2026-09-19"
HOLIDAY = "2026-10-07"


def _plan():
    definition, _warnings = schemas.load_definition(DEFAULT_CONFIG_PATH)
    return compile_definition(definition)


def _moment(day, hour, minute):
    year, month, date_ = (int(part) for part in day.split("-"))
    return datetime(year, month, date_, hour, minute, tzinfo=_SHANGHAI)


def _scheduler(tmp_path, now_fn=None):
    return SelectionScheduler(
        _plan(),
        db_path=tmp_path / "absent.db",
        now_fn=now_fn,
        run_repository=RunRepository(cache_root=tmp_path / "cache", pools_root=tmp_path / "pools"),
        lock_manager=RunLockManager(root=tmp_path / "locks"),
        signal_latch=SignalLatch(root=tmp_path / "cache"),
    )


# ================================================================== B1 调度
def test_scheduler_reads_all_configured_schedule_windows():
    """O-01：真实读取 YAML 4 处 schedule 窗口，端点由配置决定、不写死。"""
    windows = {w.stage_id: (w.start, w.end) for w in SelectionScheduler._build_windows(_plan())}
    assert windows == {
        "post_close": ("15:35", "23:59"),
        "market_gate": ("09:30", "09:35"),
        "opening_gap": ("09:30", "09:31"),
        "turning_point": ("09:36", "09:40"),
    }
    assert parse_schedule("09:36-09:40", stage_id="turning_point") == ("09:36", "09:40")
    with pytest.raises(ValueError, match="schedule"):
        parse_schedule("99:00-10:00", stage_id="bad")


def test_scheduler_skips_non_trading_day(tmp_path):
    """§10.4 / 发布门禁 4：周末与法定节假日不得运行早盘策略。"""
    scheduler = _scheduler(tmp_path)
    for day in (WEEKEND, HOLIDAY):
        result = scheduler.tick(now=_moment(day, 9, 36), records_provider=lambda _w: [{"code": "x"}])
        assert result["status"] == STATUS_SKIPPED_NON_TRADING_DAY
        assert result["due_stages"] == [] and result["executed"] == []


def test_scheduler_idle_outside_any_window(tmp_path):
    scheduler = _scheduler(tmp_path)
    result = scheduler.tick(now=_moment(TRADING_DAY, 12, 0))
    assert result["status"] == STATUS_IDLE
    assert result["due_stages"] == []


def test_scheduler_executes_due_stage_then_dedupes_same_minute(tmp_path):
    """发布门禁 7：同一分钟重复 Tick 不重复执行（分层幂等键）。"""
    scheduler = _scheduler(tmp_path)
    now = _moment(TRADING_DAY, 15, 36)

    def provider(_w):
        return [{"code": "sh600001"}]

    first = scheduler.tick(now=now, records_provider=provider)
    assert first["status"] == "EXECUTED"
    assert first["due_stages"] == ["post_close"]
    assert first["executed"][0]["terminal"] is True

    second = scheduler.tick(now=now, records_provider=provider)
    assert second["executed"][0]["status"] == "IDEMPOTENT_SKIP"
    assert second["idempotent_skips"] == 1
    assert second["status"] == STATUS_IDLE

    later = scheduler.tick(now=_moment(TRADING_DAY, 15, 37), records_provider=provider)
    assert later["executed"][0]["status"] != "IDEMPOTENT_SKIP"


def test_scheduler_waiting_data_is_fail_closed_and_retriable(tmp_path):
    """§11.4 / 发布门禁 5：数据不足不产码，且不占用该分钟幂等键，后续可重试。"""
    scheduler = _scheduler(tmp_path)
    now = _moment(TRADING_DAY, 15, 36)
    waiting = scheduler.tick(now=now, records_provider=lambda _w: None)
    assert waiting["executed"][0]["status"] == "WAITING_DATA"
    assert waiting["executed"][0]["selected_codes"] == []

    retry = scheduler.tick(now=now, records_provider=lambda _w: [{"code": "sh600001"}])
    assert retry["executed"][0]["status"] != "IDEMPOTENT_SKIP"
    assert retry["executed"][0]["terminal"] is True


def test_scheduler_daemon_stops_gracefully_by_max_ticks(tmp_path):
    """O-01：优雅退出（以 max_ticks 上限路径覆盖停机分支）。"""
    scheduler = _scheduler(tmp_path, now_fn=lambda: _moment(TRADING_DAY, 15, 36))
    summary = scheduler.run_forever(
        interval_s=0,
        max_ticks=3,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
        records_provider=lambda _w: None,
    )
    assert summary["status"] == "STOPPED"
    assert summary["tick_count"] == 3
    assert summary["last_tick"]["heartbeat"]["trade_date"] == TRADING_DAY


# ================================================================== B2 运行锁
def test_run_lock_is_exclusive_with_holder_visibility(tmp_path):
    """O-02：粒度 model_id+trade_date，多进程互斥 + 持有者可见 + 超时释放。"""
    # 两个 manager 模拟两个进程对同一锁文件的竞争
    process_a = RunLockManager(root=tmp_path / "locks", timeout_s=0.05)
    process_b = RunLockManager(root=tmp_path / "locks", timeout_s=0.05)
    held = process_a.acquire("demo_model", TRADING_DAY, operator="u1", run_id="r1")
    assert held is not None and held.held
    holder = process_a.status("demo_model", TRADING_DAY)
    assert holder["operator"] == "u1" and holder["trade_date"] == TRADING_DAY

    # 同模型同交易日：第二个进程超时拿不到锁（互斥）
    assert process_b.acquire("demo_model", TRADING_DAY, operator="u2", timeout_s=0.05) is None
    # 不同交易日不互斥（粒度含 trade_date）
    assert process_b.acquire("demo_model", "2026-09-22", operator="u2", timeout_s=0.05) is not None

    assert process_a.release("demo_model", TRADING_DAY) is True
    assert process_a.status("demo_model", TRADING_DAY) is None
    assert process_b.acquire("demo_model", TRADING_DAY, operator="u3", timeout_s=0.05) is not None


# ================================================================== B3 Signal Latch
def test_signal_latch_pending_until_window_end_then_unique_terminal(tmp_path):
    """§9.2/§22.1：窗口内仅待定，窗口末唯一终态。"""
    latch = SignalLatch(root=tmp_path / "cache")
    latch.register_pending("m1", 1, TRADING_DAY, run_id="run-a", codes=["600001", "600002"],
                           window_end="09:40", hit_at="2026-09-21T09:37:00+08:00")
    summary = latch.summary("m1", 1, TRADING_DAY)
    assert summary["pending_codes"] == ["600001", "600002"]
    assert summary["latched_codes"] == []
    assert latch.status("m1", 1, TRADING_DAY, "600001") == STATUS_PENDING

    early = latch.converge("m1", 1, TRADING_DAY, now="09:39")
    assert early["converged"] is False
    assert latch.status("m1", 1, TRADING_DAY, "600001") == STATUS_PENDING

    done = latch.converge("m1", 1, TRADING_DAY, now="09:40")
    assert done["converged"] is True
    assert done["latched_codes"] == ["600001", "600002"]
    assert latch.status("m1", 1, TRADING_DAY, "600001") == STATUS_LATCHED
    assert latch.converge("m1", 1, TRADING_DAY, now="09:41")["latched_codes"] == ["600001", "600002"]


def test_signal_latch_appends_latched_by_run_id_without_losing_terminal(tmp_path):
    """§10.5：收敛后第二次命中不得丢弃，追加 latched_by_run_id，终态保持唯一。"""
    latch = SignalLatch(root=tmp_path / "cache")
    latch.register_pending("m1", 1, TRADING_DAY, run_id="run-a", codes=["600001"], window_end="09:40")
    latch.converge("m1", 1, TRADING_DAY, now="09:40")
    latch.register_pending("m1", 1, TRADING_DAY, run_id="run-b", codes=["600001"], window_end="09:40")
    assert latch.status("m1", 1, TRADING_DAY, "600001") == STATUS_LATCHED
    assert latch.latched_by("m1", 1, TRADING_DAY, "600001") == ["run-a", "run-b"]
    latch.register_pending("m1", 1, TRADING_DAY, run_id="run-b", codes=["600001"], window_end="09:40")
    assert latch.latched_by("m1", 1, TRADING_DAY, "600001") == ["run-a", "run-b"]


# ================================================================== B4 状态恢复
def test_run_state_restores_same_day_and_expires_cross_day(tmp_path):
    """发布门禁 6 / O-04：重启后当日状态可恢复；跨日快照标记过期不恢复。"""
    repo = RunRepository(cache_root=tmp_path / "cache", pools_root=tmp_path / "pools")
    assert repo.mark_once("m1", TRADING_DAY, "key-1") is True
    assert repo.mark_once("m1", TRADING_DAY, "key-1") is False

    restored = RunRepository(cache_root=tmp_path / "cache").load_state("m1", TRADING_DAY)
    assert restored["executed_keys"] == ["key-1"]
    assert "expired_snapshot_from" not in restored

    expired = repo.load_state("m1", "2026-09-22")
    assert expired["executed_keys"] == []
    assert expired["expired_snapshot_from"] == TRADING_DAY


def test_run_repository_keeps_multiple_runs_and_candidates(tmp_path):
    """发布门禁 18：同一模型多次运行分别保存，互不覆盖。"""
    repo = RunRepository(cache_root=tmp_path / "cache", pools_root=tmp_path / "pools")
    repo.save_run({"run_id": "selection_a", "model_id": "m1", "started_at": "2026-09-21T15:36:00+08:00"})
    repo.save_run({"run_id": "selection_b", "model_id": "m1", "started_at": "2026-09-21T15:37:00+08:00"})
    runs = repo.list_runs("m1")
    assert [item["run_id"] for item in runs] == ["selection_b", "selection_a"]

    target = repo.save_candidates(TRADING_DAY, "m1", {"selected_codes": ["600001"]})
    assert target.is_file()
    assert repo.load_candidates(TRADING_DAY, "m1")["selected_codes"] == ["600001"]
    assert repo.signal_dates() == [TRADING_DAY]


# ================================================================== B6 路径与淘汰
def test_canonical_paths_follow_ssot_1310():
    assert CACHE_ROOT.parts[-2:] == ("cache", "selection-models")
    assert POOLS_ROOT.parts[-2:] == ("pools", "selection-models")
    assert LOG_ROOT.parts[-2:] == ("log", "selection-models")
    assert TEMP_ROOT.parts[-2:] == ("temp", "selection-models")
    assert str(signal_date_dir(TRADING_DAY)).endswith("cache/selection-models/" + TRADING_DAY)
    assert str(run_inputs_dir("selection_x")).endswith("selection_x/inputs")


def test_prune_removes_stale_cache_but_protects_signal_dates(tmp_path):
    repo = RunRepository(cache_root=tmp_path / "cache", pools_root=tmp_path / "pools")
    old = tmp_path / "cache" / "2026-01-01"
    old.mkdir(parents=True)
    (old / "run-state.json").write_text("{}", encoding="utf-8")
    protected = tmp_path / "cache" / "2026-01-02"
    protected.mkdir(parents=True)
    fresh = tmp_path / "cache" / "2026-09-21"
    fresh.mkdir(parents=True)
    repo.save_candidates("2026-01-02", "m1", {"selected_codes": ["600001"]})

    result = repo.prune(cutoff_days=90, today="2026-09-21")
    assert str(old) in result["removed"]
    assert not old.exists()
    assert protected.exists()
    assert fresh.exists()


# ================================================================== B5 覆盖率门禁
def test_universe_watermark_main_caliber_and_mv_reference():
    records = [
        {"code": "sh600001", "field_status": {"daily_kline": "present", "circulating_market_cap": "present"},
         "circulating_market_cap": 9e9},
        {"code": "sh600002", "field_status": {"daily_kline": "missing"}},
    ]
    watermark = build_universe_watermark(records, ["sh600001", "sh600002"], required_fields=COVERAGE_REQUIRED_FIELDS)
    assert watermark["expected"] == 2 and watermark["healthy"] == 1
    assert watermark["coverage"] == 0.5
    assert watermark["passed"] is False
    assert watermark["missing_codes"] == ["sh600002"]
    assert watermark["coverage_mv_weighted"] == 1.0
    assert watermark["mv_weighted_role"] == "reference_only"


def test_layer_denominator_follows_a05():
    assert layer_denominator("universe_gate", ["a", "b", "c"], upstream_codes=["a"]) == ["a", "b", "c"]
    assert layer_denominator("candidate_filter", ["a", "b", "c"], upstream_codes=["a", "b"]) == ["a", "b"]
    assert layer_denominator("candidate_filter", ["a", "b"]) == ["a", "b"]


# ================================================================== B7 W-09/W-10
class _FakeResponse:
    def read(self) -> bytes:
        return b"v_sh600001=1~sample~10.00~0.10~1.00~9.90~10.00~10.20~9.80"


def test_tencent_quote_missing_market_cap_is_none_not_zero(monkeypatch):
    """W-10：市值缺失一律 None，不得以 0 参与比较；W-09：本层保持腾讯原始单位（亿元）。"""
    from core.data import data_bridge as bridge

    parsed = {
        "code_raw": "sh600001", "name": "示例", "price": 10.0, "change": 0.1, "change_pct": 1.0,
        "prev_close": 9.9, "open": 10.0, "high": 10.2, "low": 9.8, "volume_hands": 1000,
        "outer": 500, "inner": 500, "order_book": None, "amount": 1e6, "amount_wan": 100.0,
        "vol_ratio": None, "turnover_pct": None, "pe": None, "pb": None,
        "circulating_market_cap": None, "total_market_cap": None, "amplitude": None, "time": "15:00",
    }
    monkeypatch.setattr(bridge, "parse_tencent_quote", lambda _line: parsed)
    monkeypatch.setattr(bridge.urllib.request, "urlopen", lambda _req, timeout=10: _FakeResponse())

    item = bridge.DataBridge.tencent_quote(["sh600001"])["sh600001"]
    assert item["circulating_market_cap"] is None
    assert item["total_market_cap"] is None

    parsed_present = {**parsed, "circulating_market_cap": 212.0, "total_market_cap": 21205.0}
    monkeypatch.setattr(bridge, "parse_tencent_quote", lambda _line: parsed_present)
    item2 = bridge.DataBridge.tencent_quote(["sh600001"])["sh600001"]
    assert item2["circulating_market_cap"] == 212.0
    assert item2["total_market_cap"] == 21205.0
