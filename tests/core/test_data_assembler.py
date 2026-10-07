# -*- coding: utf-8 -*-
"""DataAssembler（选股规范 §11.3/§11.4/§11.5/§11.7）与 funnel run 水位门禁接线测试。

覆盖评估报告 `assessment_smart-stock-selection_20261007.md` 处置建议 2（P0-1 + P0-2）：
- `finalized_local` 单模式装配 + `date <= as_of` 硬截断；
- 不可变快照清单与内容哈希（重复装配内容寻址稳定）；
- 缺失字段标 `field_status` 且不填 0（§11.6）；
- `check_post_close_ready` 进门禁：未达标 `WAITING_DATA` 失败关闭，不产出代码；
- 分钟归档 → `minute_points` 适配器：时间戳归一化、进行中 Bar 标 `not_ready`、
  tick 主动买卖量仅在有覆盖的分钟给出。
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.data.data_assembler import (
    GATE_OBSERVATION,
    GATE_PASS,
    GATE_WAITING_DATA,
    STATUS_OK,
    DataAssembler,
)
from core.data.dataset_sync import POST_CLOSE_WATERMARK_KEYS, write_universe_watermark
from core.data.sync_engine import MarketDataStore
from core.strategy.stock_funnel import StockFunnelPipeline

AS_OF = "2026-09-30"


# ------------------------------------------------------------------ 装配脚手架
def weekday_dates(end: str, count: int):
    """以 `end`（含）为最后一个业务日，向前取 `count` 个工作日。"""
    days = []
    cursor = datetime.strptime(end, "%Y-%m-%d")
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor.strftime("%Y-%m-%d"))
        cursor -= timedelta(days=1)
    return list(reversed(days))


TRADE_DAYS = weekday_dates(AS_OF, 7)


def _execute(db, sql, rows=None):
    with closing(sqlite3.connect(str(db))) as conn:
        if rows:
            conn.executemany(sql, rows)
        else:
            conn.execute(sql)
        conn.commit()


def seed_klines(db, symbol, dates, start_price=10.0, unsettled_dates=()):
    rows = []
    for index, day in enumerate(dates):
        price = round(start_price + index * 0.05, 4)
        rows.append((symbol, day, price, round(price + 0.2, 4), round(price + 0.3, 4),
                     round(price - 0.1, 4), 1000 + index * 100, 0.0,
                     0 if day in set(unsettled_dates) else 1))
    _execute(
        db,
        "INSERT OR REPLACE INTO daily_kline (symbol, date, open, high, low, close, volume, amount, is_settled)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def finalize_watermarks(db, keys=POST_CLOSE_WATERMARK_KEYS, covered=10, total=10):
    store = MarketDataStore(db_path=Path(str(db)))
    for key in keys:
        write_universe_watermark(store, key, covered, total, availability="finalized",
                                 trade_date=AS_OF, note=f"test {key}")


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "astock_data.db"
    MarketDataStore(db_path=path)
    return path


@pytest.fixture()
def assembler(db, tmp_path):
    """默认让收盘水位门禁达标，使装配层测试专注装配本身。"""
    finalize_watermarks(db)
    return DataAssembler(db_path=db, snapshot_root=tmp_path / "snapshots",
                         intraday_root=tmp_path / "intraday")


def eligible_universe(db):
    """构造一份能让 post_close 全部规则 PASS 的最小本地库。"""
    seed_klines(db, "sh600001", weekday_dates(AS_OF, 75), start_price=11.9)
    _execute(db, "INSERT OR REPLACE INTO stock_basic (symbol, name, market, list_date, updated_at)"
                 " VALUES (?, ?, ?, ?, ?)",
             [("sh600001", "示例股份", "sh", "2010-01-01", f"{AS_OF} 15:40:00")])
    _execute(db, "INSERT OR REPLACE INTO capital_snapshot (symbol, date, total_shares, float_shares,"
                 " total_market_cap, float_market_cap, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
             [("sh600001", AS_OF, 1e9, 8e8, 1.2e10, 9.5e9, "tencent_snapshot_derived_yuan")])


def _run_args(**overrides):
    base = dict(
        funnel_cmd="run", stage="post_close", input=None, assemble=False, assemble_intraday=False,
        codes=None, all_market=False, as_of=AS_OF, intraday_date=None, lookback=70,
        allow_degraded=False, db=None, context=None, config=None, save=False, trade_date=None,
        intraday_root=None, snapshot_root=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ------------------------------------------------------------------ §11.3 / §11.4 装配
def test_assemble_daily_truncates_every_row_after_as_of(assembler, db):
    """§11.3：一致性只读事务内禁止读取 as_of 之后的数据。"""
    seed_klines(db, "sh600001", TRADE_DAYS + ["2026-10-08", "2026-10-09"])
    out = assembler.assemble_daily(["sh600001"], as_of=AS_OF)
    assert out["status"] == STATUS_OK
    record = out["records"][0]
    assert record["dates"][-1] == AS_OF
    assert "2026-10-08" not in record["dates"] and "2026-10-09" not in record["dates"]
    assert len(record["closes"]) == len(TRADE_DAYS)
    assert record["field_status"]["daily_kline"] == "present"


def test_assemble_daily_reads_only_settled_rows(assembler, db):
    """§11.6：仅统计定盘行；未定盘行不得进入装配，末位非 as_of 当日须如实标 stale。"""
    seed_klines(db, "sh600001", TRADE_DAYS, unsettled_dates=[AS_OF])
    record = assembler.assemble_daily(["sh600001"], as_of=AS_OF)["records"][0]
    assert AS_OF not in record["dates"]
    assert record["dates"][-1] == TRADE_DAYS[-2]
    assert record["field_status"]["daily_kline"] == "stale"


def test_assemble_daily_lookback_bounds_window(assembler, db):
    seed_klines(db, "sh600001", TRADE_DAYS)
    record = assembler.assemble_daily(["sh600001"], as_of=AS_OF, lookback=3)["records"][0]
    assert record["dates"] == TRADE_DAYS[-3:]


def test_missing_fields_are_labelled_and_never_zero_filled(assembler, db):
    """§11.6：缺失 ≠ 0；主数据与流通市值缺失时只标状态，键不写入记录。"""
    seed_klines(db, "sh600002", TRADE_DAYS)
    record = assembler.assemble_daily(["sh600002"], as_of=AS_OF)["records"][0]
    assert record["field_status"]["security_master"] == "missing"
    assert record["field_status"]["circulating_market_cap"] == "missing"
    assert record["field_status"]["main_net_inflow"] == "missing"
    assert "name" not in record
    assert "circulating_market_cap" not in record
    assert "main_net_inflow" not in record

    result = StockFunnelPipeline().run_stage("post_close", [record])
    assert result["output_count"] == 0
    evidence = result["rejected_records"][0]
    assert evidence["candidate_verdict"] == "UNKNOWN"
    assert any(item["rule_id"] == "minimum_float_market_cap" for item in evidence["unknown_rules"])
    assert evidence["failed_rules"] == []


def test_proxy_capital_flow_is_marked_unsupported_not_passed_through(assembler, db):
    """裁定 W-07：资金流代理档不得传给正式规则，标 unsupported 且不写入数值。"""
    seed_klines(db, "sh600001", TRADE_DAYS)
    _execute(db, "INSERT OR REPLACE INTO capital_flow_daily (symbol, date, main_net_inflow, flow_source)"
                 " VALUES (?, ?, ?, ?)", [("sh600001", AS_OF, 12345.0, "tencent_proxy")])
    record = assembler.assemble_daily(["sh600001"], as_of=AS_OF)["records"][0]
    assert record["field_status"]["main_net_inflow"] == "unsupported"
    assert "main_net_inflow" not in record


def test_exact_capital_flow_is_passed_through(assembler, db):
    seed_klines(db, "sh600001", TRADE_DAYS)
    _execute(db, "INSERT OR REPLACE INTO capital_flow_daily (symbol, date, main_net_inflow, flow_source)"
                 " VALUES (?, ?, ?, ?)", [("sh600001", AS_OF, 12345.0, "eastmoney_exact")])
    record = assembler.assemble_daily(["sh600001"], as_of=AS_OF)["records"][0]
    assert record["field_status"]["main_net_inflow"] == "present"
    assert record["main_net_inflow"] == 12345.0


def test_stale_valuation_snapshot_is_flagged_and_business_time_recorded(assembler, db):
    """§11.6：存在记录但业务时间超过阈值 → stale；业务时间随清单可追溯，不混入状态词汇。"""
    seed_klines(db, "sh600001", TRADE_DAYS)
    stale_date = weekday_dates("2026-09-10", 1)[0]
    _execute(db, "INSERT OR REPLACE INTO capital_snapshot (symbol, date, total_shares, float_shares,"
                 " total_market_cap, float_market_cap, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
             [("sh600001", stale_date, 1e9, 8e8, 1.2e10, 9.5e9, "tencent_snapshot_derived_yuan")])
    record = assembler.assemble_daily(["sh600001"], as_of=AS_OF)["records"][0]
    assert record["field_status"]["circulating_market_cap"] == "stale"
    assert record["field_business_time"]["circulating_market_cap"] == stale_date
    assert record["circulating_market_cap"] == 9.5e9
    slice_entry = assembler.assemble_daily(["sh600001"], as_of=AS_OF)["manifest"]["input_slices"][0]
    assert slice_entry["field_business_time"]["daily_kline"] == AS_OF


def test_record_data_meta_carries_snapshot_identity(assembler, db):
    """§11.4：记录级 data_meta 须携带快照标识、口径、水位与清单哈希。"""
    seed_klines(db, "sh600001", TRADE_DAYS)
    out = assembler.assemble_daily(["sh600001"], as_of=AS_OF)
    meta = out["records"][0]["data_meta"]
    manifest = out["manifest"]
    assert meta["access_mode"] == "finalized_local"
    assert meta["adjustment"] == "qfq"
    assert meta["data_snapshot_id"] == manifest["data_snapshot_id"]
    assert meta["snapshot_manifest_hash"] == manifest["snapshot_manifest_hash"]
    assert "daily_kline" in meta["physical_tables"] and "sync_meta" in meta["physical_tables"]
    assert meta["as_of"].startswith(AS_OF)
    assert meta["input_hash"].startswith("sha256:")


def test_snapshot_manifest_is_content_addressed_and_persisted(assembler, db):
    """§11.7：同一份定盘数据重复装配 → 同一快照 ID 与清单哈希；内容变化必然改变哈希。"""
    seed_klines(db, "sh600001", TRADE_DAYS)
    first = assembler.assemble_daily(["sh600001"], as_of=AS_OF)["manifest"]
    second = assembler.assemble_daily(["sh600001"], as_of=AS_OF)["manifest"]
    assert first["data_snapshot_id"] == second["data_snapshot_id"]
    assert first["snapshot_manifest_hash"] == second["snapshot_manifest_hash"]

    snapshot_dir = Path(first["snapshot_path"])
    assert (snapshot_dir / "manifest.json").is_file()
    lines = (snapshot_dir / "records.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0])["code"] == "sh600001"

    seed_klines(db, "sh600009", TRADE_DAYS)
    changed = assembler.assemble_daily(["sh600001", "sh600009"], as_of=AS_OF)["manifest"]
    assert changed["snapshot_manifest_hash"] != first["snapshot_manifest_hash"]
    assert changed["data_snapshot_id"] != first["data_snapshot_id"]


def test_manifest_records_sync_meta_and_universe_watermark(assembler, db):
    """§11.7：清单须记录 sync_meta 同步口径与 UniverseWatermark。"""
    seed_klines(db, "sh600001", TRADE_DAYS)
    _execute(db, "INSERT OR REPLACE INTO sync_meta (symbol, last_sync_date, row_count, min_date, max_date,"
                 " integrity_status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
             [("sh600001", AS_OF, 7, TRADE_DAYS[0], AS_OF, "synced", f"{AS_OF} 15:40:00")])
    manifest = assembler.assemble_daily(["sh600001"], as_of=AS_OF)["manifest"]
    assert manifest["sync_meta"]["symbols_with_meta"] == 1
    assert manifest["sync_meta"]["integrity_status_counts"] == {"synced": 1}
    assert manifest["integrity_status"] == "watermark_finalized"
    assert set(manifest["universe_watermark"]) == set(POST_CLOSE_WATERMARK_KEYS)
    assert manifest["calendar_version"]


def test_universe_coverage_gap_is_disclosed_not_silently_accepted(assembler, db):
    """§11.4：水位分母小于本次装配 Universe 时必须披露缺口，不得把"批次达标"当成全市场达标。"""
    wide = [f"sh60{i:04d}" for i in range(12)]
    out = assembler.assemble_daily(wide, as_of=AS_OF)
    assert set(out["gate"]["universe_coverage_gap"]) == set(POST_CLOSE_WATERMARK_KEYS)
    assert out["manifest"]["universe_coverage"]["watermark_coverage_gap"]
    assert out["manifest"]["universe_coverage"]["missing_daily_kline"] == wide

    narrow = assembler.assemble_daily(["sh600001"], as_of=AS_OF)
    assert "universe_coverage_gap" not in narrow["gate"]


# ------------------------------------------------------------------ §11.4 水位门禁
def test_gate_waits_when_watermarks_absent(assembler, db):
    _execute(db, "DELETE FROM dataset_audit")
    gate = assembler.evaluate_data_gate(as_of=AS_OF)
    assert gate["state"] == GATE_WAITING_DATA
    assert set(gate["missing"]) == set(POST_CLOSE_WATERMARK_KEYS)


def test_gate_passes_only_when_every_required_dataset_finalized(assembler, db):
    _execute(db, "DELETE FROM dataset_audit")
    finalize_watermarks(db, keys=POST_CLOSE_WATERMARK_KEYS[:-1])
    assert assembler.evaluate_data_gate(as_of=AS_OF)["state"] == GATE_WAITING_DATA
    finalize_watermarks(db)
    assert assembler.evaluate_data_gate(as_of=AS_OF)["state"] == GATE_PASS


def test_degraded_run_requires_explicit_opt_in(assembler, db):
    _execute(db, "DELETE FROM dataset_audit")
    finalize_watermarks(db, covered=8, total=10)
    assert assembler.evaluate_data_gate(as_of=AS_OF)["state"] == GATE_WAITING_DATA
    gate = assembler.evaluate_data_gate(as_of=AS_OF, allow_degraded=True)
    assert gate["state"] == GATE_OBSERVATION
    assert gate["not_finalized"] == list(POST_CLOSE_WATERMARK_KEYS)


def test_assemble_daily_refuses_to_emit_records_before_gate_passes(assembler, db):
    seed_klines(db, "sh600001", TRADE_DAYS)
    _execute(db, "DELETE FROM dataset_audit")
    out = assembler.assemble_daily(["sh600001"], as_of=AS_OF)
    assert out["status"] == "WAITING_DATA"
    assert out["records"] == []
    assert out["manifest"] is None


# ------------------------------------------------------------------ CLI 接线
def eligible_hand_record():
    closes = [10 + i * 0.02 for i in range(69)] + [12.5]
    return {
        "code": "sh600001",
        "name": "示例股份",
        "circulating_market_cap": 5_000_000_000,
        "change_pct": 4.0,
        "closes": closes,
        "volumes": [1000] * 68 + [1200, 1800],
    }


def test_funnel_run_post_close_is_blocked_by_watermark_gate(tmp_path, db, capsys):
    """P0-2：水位缺失/未达标时 `funnel run` 必须失败关闭——手工喂 stdin 亦不豁免。"""
    from core.commands.funnel_cmds import cmd_funnel

    seed_klines(db, "sh600001", TRADE_DAYS)
    payload_file = tmp_path / "records.json"
    payload_file.write_text(json.dumps([eligible_hand_record()]), encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        cmd_funnel(_run_args(db=str(db), input=str(payload_file)))
    assert exit_info.value.code == 3
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["status"] == "WAITING_DATA"
    assert emitted["selected_codes"] == []
    assert emitted["data_gate"]["state"] == GATE_WAITING_DATA


def test_funnel_run_assemble_emits_candidates_with_snapshot_trace(tmp_path, db, capsys):
    from core.commands.funnel_cmds import cmd_funnel

    eligible_universe(db)
    finalize_watermarks(db)

    cmd_funnel(_run_args(db=str(db), assemble=True, codes="sh600001",
                         snapshot_root=str(tmp_path / "snapshots")))
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASSED"
    assert payload["selected_codes"] == ["sh600001"]
    # P0-4：收盘初筛无代理口径，候选同时进入正式候选清单且输出不带降级标记
    assert payload["eligible_signal_codes"] == ["sh600001"]
    assert payload["not_eligible_for_signal"] is False
    assert payload["run_metadata"]["data_gate"]["state"] == GATE_PASS
    snapshots = payload["run_metadata"]["data_snapshots"]
    assert snapshots[0]["access_mode"] == "finalized_local"
    assert snapshots[0]["snapshot_manifest_hash"].startswith("sha256:")
    assert (Path(snapshots[0]["snapshot_path"]) / "manifest.json").is_file()
    assert payload["passed_records"][0]["data_meta"]["data_snapshot_id"] == snapshots[0]["data_snapshot_id"]


def test_funnel_run_degraded_gate_is_visible_in_run_metadata(tmp_path, db, capsys):
    from core.commands.funnel_cmds import cmd_funnel

    eligible_universe(db)
    _execute(db, "DELETE FROM dataset_audit")
    finalize_watermarks(db, covered=8, total=10)

    cmd_funnel(_run_args(db=str(db), input=None, assemble=True, codes="sh600001",
                         allow_degraded=True, snapshot_root=str(tmp_path / "snapshots")))
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_metadata"]["data_gate"]["state"] == GATE_OBSERVATION


def test_source_error_is_never_reported_as_an_empty_result(monkeypatch, db, tmp_path, capsys):
    """§11.6：本地库不可读属 `source_error`，不得伪装成"已运行且无候选"。"""
    from core.commands import funnel_cmds
    from core.data import data_assembler as da_module

    eligible_universe(db)
    finalize_watermarks(db)

    def unreadable(self):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(da_module.DataAssembler, "_read_conn", unreadable)
    with pytest.raises(SystemExit) as exit_info:
        funnel_cmds.cmd_funnel(_run_args(db=str(db), assemble=True, codes="sh600001",
                                          snapshot_root=str(tmp_path / "snapshots")))
    assert exit_info.value.code == 3
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["status"] == "SOURCE_ERROR"
    assert emitted["selected_codes"] == []
    assert emitted["detail"]["assembler"]["reason_code"] == "LOCAL_STORE_UNREADABLE"


def test_funnel_run_requires_input_or_assemble(db):
    from core.commands.funnel_cmds import cmd_funnel

    with pytest.raises(ValueError):
        cmd_funnel(_run_args(db=str(db), input=None, assemble=False))


# ------------------------------------------------------------------ §11.5 捕获适配器
def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _archive(assembler, minute_rows, tick_rows=(), snapshot_rows=()):
    day_dir = assembler.intraday_root / AS_OF
    _write_jsonl(day_dir / "minute_1m.jsonl", minute_rows)
    _write_jsonl(day_dir / "tick.jsonl", list(tick_rows))
    _write_jsonl(day_dir / "snapshot.jsonl", list(snapshot_rows))


def bar(ts, symbol, close, volume=500):
    return {"ts": ts, "symbol": symbol, "open": close, "close": close,
            "high": max(close, 9.9), "low": min(close, 10.9), "volume": volume}


def test_minute_adapter_normalizes_timestamps_and_drops_other_days(assembler):
    _archive(assembler, [
        bar(f"{AS_OF} 09:30", "sh600001", 10.2),
        bar(f"{AS_OF} 09:31", "sh600001", 10.3),
        # 归档器一次拉取多日分钟线：明确属于另一交易日的行必须剔除
        bar("2026-09-29 14:59", "sh600001", 9.0),
    ])
    out = assembler.assemble_intraday(["sh600001"], trade_date=AS_OF,
                                      now=datetime(2026, 9, 30, 10, 0, 0))
    record = out["records"][0]
    assert [p["time"] for p in record["minute_points"]] == ["09:30", "09:31"]
    assert record["minute_points"][0]["price"] == 10.2
    assert record["field_status"]["minute_points"] == "present"
    assert record["data_meta"]["dropped_points"] == []
    assert record["data_meta"]["access_mode"] == "intraday_capture"


def test_minute_adapter_flags_in_progress_bar_as_not_ready(assembler):
    _archive(assembler, [bar(f"{AS_OF} 09:{m:02d}", "sh600001", 10.0 + m / 100)
                         for m in range(30, 41)])
    # 09:40 起点 Bar 在 09:40:30 尚未收满 60 秒 → not_ready，由规则层计入 dropped_point_count
    out = assembler.assemble_intraday(["sh600001"], trade_date=AS_OF,
                                      now=datetime(2026, 9, 30, 9, 40, 30))
    points = out["records"][0]["minute_points"]
    assert points[-1]["time"] == "09:40"
    assert points[-1]["field_status"] == "not_ready"
    assert points[-2].get("field_status") is None
    assert points[-2].get("buy_volume") is None


def test_minute_adapter_unparsable_timestamp_is_recorded_not_silently_dropped(assembler):
    _archive(assembler, [
        bar(f"{AS_OF} 09:30", "sh600001", 10.0),
        bar("not-a-time", "sh600001", 10.1),
    ])
    out = assembler.assemble_intraday(["sh600001"], trade_date=AS_OF,
                                      now=datetime(2026, 9, 30, 10, 0, 0))
    dropped = out["records"][0]["data_meta"]["dropped_points"]
    assert len(dropped) == 1
    assert dropped[0]["field_status"] == "missing"
    assert dropped[0]["reason_code"] == "MINUTE_TIMESTAMP_UNPARSABLE"
    assert out["manifest"]["dropped_point_count_total"] == 1


def test_minute_adapter_tick_flow_only_for_covered_minutes(assembler):
    _archive(
        assembler,
        [bar(f"{AS_OF} 09:30", "sh600001", 10.0), bar(f"{AS_OF} 09:31", "sh600001", 10.0)],
        tick_rows=[
            {"seq": 1, "time": "093000", "symbol": "sh600001", "price": 10.0, "volume": 300,
             "amount": 3000, "direction": "B"},
            {"seq": 2, "time": "093010", "symbol": "sh600001", "price": 10.0, "volume": 100,
             "amount": 1000, "direction": "S"},
            {"seq": 3, "time": "093020", "symbol": "sh600001", "price": 10.0, "volume": 50,
             "amount": 500, "direction": "M"},
        ],
    )
    points = assembler.assemble_intraday(
        ["sh600001"], trade_date=AS_OF, now=datetime(2026, 9, 30, 10, 0, 0)
    )["records"][0]["minute_points"]
    assert points[0]["buy_volume"] == 300 and points[0]["sell_volume"] == 100
    # 09:31 无分笔覆盖：不得用 0 填充，交由规则层走 §11.5 价格方向代理口径
    assert "buy_volume" not in points[1] and "sell_volume" not in points[1]


def test_minute_adapter_waits_when_archive_absent(assembler):
    out = assembler.assemble_intraday(["sh600001"], trade_date=AS_OF)
    assert out["status"] == "WAITING_DATA"
    assert out["reason_code"] == "INTRADAY_ARCHIVE_ABSENT"
    assert out["records"] == []


def test_funnel_run_attaches_minute_points_without_fabricating_signals(tmp_path, db, capsys):
    """端到端：归档数据 → 适配器 → turning_point 规则；时间戳必须已被装配层归一化。"""
    from core.commands.funnel_cmds import cmd_funnel

    local = DataAssembler(db_path=db, snapshot_root=tmp_path / "snapshots",
                          intraday_root=tmp_path / "intraday")
    prices = [10.20, 10.30, 10.25, 10.20, 10.18, 10.17, 10.18, 10.21]
    _archive(local, [bar(f"{AS_OF} 09:{30 + i:02d}", "sh600001", price)
                     for i, price in enumerate(prices)])

    upstream = tmp_path / "upstream.json"
    upstream.write_text(json.dumps([{"code": "sh600001"}, {"code": "sh600002"}]), encoding="utf-8")

    cmd_funnel(_run_args(db=str(db), stage="turning_point", input=str(upstream),
                         assemble_intraday=True, intraday_date=AS_OF,
                         intraday_root=str(tmp_path / "intraday"),
                         snapshot_root=str(tmp_path / "snapshots")))
    payload = json.loads(capsys.readouterr().out)

    assert payload["passed_records"], payload["rejected_records"]
    metrics = payload["passed_records"][0]["_funnel"]["rules"][0]["metrics"]
    # 归一化在装配层完成：规则层不得再报"全部点未归一化"
    assert metrics["dropped_point_count"] == 0
    assert metrics["minute_points_field_status"] == "present"
    # 无归档的标的必须留痕为 UNKNOWN（输入不足），而不是被判为"条件不成立"
    unmatched = [item for item in payload["rejected_records"]
                 if item["candidate"]["code"] == "sh600002"]
    assert unmatched and unmatched[0]["candidate_verdict"] == "UNKNOWN"
    assert payload["run_metadata"]["data_snapshots"][-1]["access_mode"] == "intraday_capture"
