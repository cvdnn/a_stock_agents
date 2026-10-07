# -*- coding: utf-8 -*-
"""CLI commands for the configurable close-to-open stock funnel."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.data.data_assembler import GATE_WAITING_DATA, STATUS_OK, DataAssembler
from core.data.sync_engine import DB_PATH, TradeCalendar
from core.selection_models.model_compiler import compile_definition
from core.selection_models.run_lock import RunLockManager
from core.selection_models.run_repository import RunRepository
from core.selection_models.paths import log_dir
from core.selection_models.scheduler import SelectionScheduler
from core.selection_models.schemas import load_definition
from core.selection_models.signal_latch import SignalLatch
from core.strategy.stock_funnel import (
    DEFAULT_CONFIG_PATH,
    StockFunnelPipeline,
    derive_open_gap,
)

#: 消费收盘定盘数据的阶段：一律前置 §11.4 水位门禁（手工喂 stdin 亦不豁免）
WATERMARK_GATED_STAGES = ("post_close",)

#: 记录级 data_meta 向运行快照清单汇聚的键（§11.7）
_MERGE_META_KEYS = ("minute_points", "order_book", "open", "previous_close", "current_price")


def _read_json(path_value: str) -> Any:
    if path_value == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path_value).read_text(encoding="utf-8"))


def _split_codes(value: Optional[str]) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _algorithm_version(pipeline: StockFunnelPipeline) -> str:
    strategy = pipeline.config.get("strategy") or {}
    return f"{strategy.get('id', 'funnel')}@v{pipeline.config.get('version', 1)}"


def _waiting_data(
    stage: str,
    gate: Optional[Mapping[str, Any]],
    detail: Optional[Mapping[str, Any]] = None,
    status: str = "WAITING_DATA",
) -> None:
    """§11.4 失败关闭：数据未定盘/未达标只交付等待原因，不生成任何代码。

    `status` 如实区分 `WAITING_DATA`（等待水位/捕获）与 `SOURCE_ERROR`（本地库不可读），
    二者都不得被伪装成"已运行且无候选"（§11.6）。
    """
    _emit({
        "status": status,
        "stage_id": stage,
        "input_count": 0,
        "output_count": 0,
        "selected_codes": [],
        "eligible_signal_codes": [],
        "not_eligible_for_signal": False,
        "passed_records": [],
        "rejected_records": [],
        "data_gate": gate,
        "detail": detail or {},
        "note": "数据水位或运行捕获未达标即失败关闭，不产出候选（§11.4；发布门禁「数据不足不生成代码」）。",
    })
    raise SystemExit(3)


def _snapshot_entries(manifests: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "data_snapshot_id": item.get("data_snapshot_id"),
            "access_mode": item.get("access_mode"),
            "as_of": item.get("as_of"),
            "snapshot_manifest_hash": item.get("snapshot_manifest_hash"),
            "snapshot_path": item.get("snapshot_path"),
        }
        for item in manifests
        if item
    ]


def _attach_intraday(
    records: List[Mapping[str, Any]],
    attached: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """把捕获适配器交付的盘中字段并入既有记录（不覆盖收盘字段）。"""
    by_code = {str(item.get("code") or ""): item for item in attached}
    merged: List[Dict[str, Any]] = []
    for raw in records:
        record = dict(raw)
        capture = by_code.get(str(record.get("code") or ""))
        if capture is None:
            record.setdefault("field_status", {})["intraday_capture"] = "missing"
            merged.append(record)
            continue
        for key in _MERGE_META_KEYS:
            if key in capture:
                record[key] = capture[key]
        record["field_status"] = {
            **dict(record.get("field_status") or {}),
            **dict(capture.get("field_status") or {}),
        }
        record["data_meta"] = {
            **dict(record.get("data_meta") or {}),
            **dict(capture.get("data_meta") or {}),
        }
        merged.append(record)
    return merged


def _cmd_funnel_run_or_validate(args) -> None:
    config_path = Path(args.config).resolve() if getattr(args, "config", None) else None
    pipeline = StockFunnelPipeline(config_path=config_path)
    action = getattr(args, "funnel_cmd", None)

    if action == "validate":
        payload = {
            "status": "valid",
            "config": str(config_path or "config/funnel_strategy.yaml"),
            "stages": pipeline.stage_ids,
            "registered_rule_types": pipeline.registry.names,
            # 编译期输出：earliest_possible_hit_time 由规则参数推导，Web 不得手工填写（§5.5/§11.5）
            "earliest_possible_hit_time": pipeline.earliest_possible_hit_times,
            # 声明即可见：阶段时间窗与声明态参数块（ranking/risk_exit）均被真实读取，供配置端展示与校验
            "stage_schedules": pipeline.stage_schedules,
            "declared_blocks": pipeline.declared_blocks,
        }
        _emit(payload)
        return

    if action != "run":
        raise ValueError("funnel requires either validate or run")

    assembler = DataAssembler(
        db_path=Path(getattr(args, "db", None) or DB_PATH),
        snapshot_root=Path(args.snapshot_root) if getattr(args, "snapshot_root", None) else None,
        intraday_root=Path(args.intraday_root) if getattr(args, "intraday_root", None) else None,
    )
    allow_degraded = bool(getattr(args, "allow_degraded", False))
    as_of = getattr(args, "as_of", None)
    use_local = bool(getattr(args, "assemble", False))
    use_capture = bool(getattr(args, "assemble_intraday", False))
    algorithm_version = _algorithm_version(pipeline)
    gate: Optional[Dict[str, Any]] = None
    manifests: List[Dict[str, Any]] = []

    if use_local and getattr(args, "input", None):
        raise ValueError("--assemble 与 --input 互斥：--assemble 由 DataAssembler 交付本地定盘输入")
    if not use_local and not getattr(args, "input", None):
        raise ValueError("funnel run 需要 --input（手工/上游阶段输入）或 --assemble（本地定盘装配）")

    # 门禁一（§11.4）：收盘水位未 finalized 即失败关闭，degraded 只允许显式观察运行。
    if args.stage in WATERMARK_GATED_STAGES or use_local:
        gate = assembler.evaluate_data_gate(as_of=as_of, allow_degraded=allow_degraded)
        if gate["state"] == GATE_WAITING_DATA:
            _waiting_data(args.stage, gate)

    records: List[Mapping[str, Any]]
    embedded_context: Dict[str, Any] = {}
    if use_local:
        codes = assembler.resolve_universe(
            codes=_split_codes(getattr(args, "codes", None)),
            all_market=bool(getattr(args, "all_market", False)),
        )
        built = assembler.assemble_daily(
            codes,
            as_of=as_of,
            lookback=int(getattr(args, "lookback", 70) or 70),
            allow_degraded=allow_degraded,
            algorithm_version=algorithm_version,
        )
        if built["status"] != STATUS_OK:
            _waiting_data(args.stage, built.get("gate") or gate, {"assembler": built},
                          status=str(built["status"]))
        records = built["records"]
        manifests.append(built["manifest"])
    else:
        source = _read_json(args.input)
        if isinstance(source, list):
            records = source
        elif isinstance(source, dict):
            # A stage result can be fed directly to the next stage.
            records = source.get("records", source.get("passed_records", []))
            embedded_context = source.get("context", {}) or {}
        else:
            raise ValueError("input JSON must be a list or an object with records/context")

    # 门禁二（§11.5/D3）：盘中阶段须经捕获适配器取得 minute_points/snapshot，不得临时补数。
    if use_capture:
        codes = [str(item.get("code") or "") for item in records if item.get("code")]
        attached = assembler.assemble_intraday(
            codes,
            trade_date=getattr(args, "intraday_date", None) or as_of,
            gate=gate,
            algorithm_version=algorithm_version,
        )
        if attached["status"] != STATUS_OK:
            _waiting_data(args.stage, gate, {"assembler": attached})
        records = _attach_intraday(records, attached["records"])
        manifests.append(attached["manifest"])

    context = embedded_context
    if getattr(args, "context", None):
        loaded_context = _read_json(args.context)
        if not isinstance(loaded_context, dict):
            raise ValueError("context JSON must be an object")
        context = loaded_context

    if args.stage == "opening_gap":
        records = derive_open_gap(records)

    # 运行元数据（§11.2/§11.7）：记录本地已同步区间的日历版本，显式 --context 优先。
    # calendar_version 只进入运行元数据与快照清单，不进入 plan_hash。
    # 本地库无覆盖时仅如实标记 calendar_available=False，不在此处失败关闭——
    # §10.4 的失败关闭针对盘中自动任务的调度判断，手动 CLI 运行须留痕而非静默中断。
    calendar_meta = TradeCalendar.local_calendar_version(assembler.db_path)
    run_context = dict(context)
    run_context.setdefault("calendar_version", calendar_meta["calendar_version"])
    run_context.setdefault("calendar_available", calendar_meta["calendar_available"])
    if manifests:
        run_context.setdefault("data_snapshots", _snapshot_entries(manifests))
    if gate is not None:
        run_context.setdefault("data_gate", gate)

    payload = pipeline.run_stage(args.stage, records, run_context)
    if getattr(args, "save", False):
        target = pipeline.save_result(payload, trade_date=getattr(args, "trade_date", None))
        payload["saved_to"] = str(target)
    _emit(payload)


# ---------------------------------------------------------------- 调度（B1：tick / daemon）
def _compile_funnel_plan(config_path: Optional[Path]) -> Any:
    """把漏斗 YAML 编译为 `CompiledSelectionPlan`（调度只执行已编译计划）。"""
    definition, _warnings = load_definition(config_path or DEFAULT_CONFIG_PATH)
    return compile_definition(definition)


def _load_run_context(args) -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    if getattr(args, "context", None):
        loaded = _read_json(args.context)
        if not isinstance(loaded, dict):
            raise ValueError("context JSON must be an object")
        context = loaded
    return context


def _build_records_provider(assembler: DataAssembler, pipeline: StockFunnelPipeline, args):
    """调度 Tick 的按阶段输入装配器；数据不足返回 `None`（失败关闭，不产码）。

    收盘阶段（schedule 起点 ≥ 15:00）取 `finalized_local` 定盘日线；早盘阶段在同一批
    记录上（可选）叠加 `intraday_capture` 分钟/盘口，`opening_gap` 额外派生 `gap_pct`。
    """
    if not getattr(args, "assemble", False):
        return None
    as_of = getattr(args, "as_of", None)
    allow_degraded = bool(getattr(args, "allow_degraded", False))
    use_capture = bool(getattr(args, "assemble_intraday", False))
    lookback = int(getattr(args, "lookback", 70) or 70)
    codes = _split_codes(getattr(args, "codes", None))
    all_market = bool(getattr(args, "all_market", False))
    algorithm_version = _algorithm_version(pipeline)

    def provider(window) -> Optional[List[Dict[str, Any]]]:
        universe = assembler.resolve_universe(codes=codes, all_market=all_market)
        built = assembler.assemble_daily(
            universe, as_of=as_of, lookback=lookback,
            allow_degraded=allow_degraded, algorithm_version=algorithm_version,
        )
        if built["status"] != STATUS_OK:
            return None
        records: List[Dict[str, Any]] = list(built["records"])
        if str(window.start) < "15:00":  # 早盘阶段
            if use_capture:
                ids = [str(item.get("code")) for item in records if item.get("code")]
                attached = assembler.assemble_intraday(
                    ids, trade_date=getattr(args, "intraday_date", None) or as_of,
                    algorithm_version=algorithm_version,
                )
                if attached["status"] != STATUS_OK:
                    return None
                records = _attach_intraday(records, attached["records"])
            if window.stage_id == "opening_gap":
                records = derive_open_gap(records)
        return records

    return provider


def _cmd_funnel_schedule(args, *, once: bool) -> None:
    config_path = Path(args.config).resolve() if getattr(args, "config", None) else None
    pipeline = StockFunnelPipeline(config_path=config_path)
    plan = _compile_funnel_plan(config_path)
    db_path = Path(getattr(args, "db", None) or DB_PATH)
    assembler = DataAssembler(
        db_path=db_path,
        snapshot_root=Path(args.snapshot_root) if getattr(args, "snapshot_root", None) else None,
        intraday_root=Path(args.intraday_root) if getattr(args, "intraday_root", None) else None,
    )
    provider = _build_records_provider(assembler, pipeline, args)
    context = _load_run_context(args)
    calendar_meta = TradeCalendar.local_calendar_version(db_path)
    context.setdefault("calendar_version", calendar_meta["calendar_version"])
    context.setdefault("calendar_available", calendar_meta["calendar_available"])

    scheduler = SelectionScheduler(
        plan,
        db_path=db_path,
        run_repository=RunRepository(),
        lock_manager=RunLockManager(),
        signal_latch=SignalLatch(),
    )
    if once:
        _emit(scheduler.tick(records_provider=provider, context=context))
        return

    def _log_tick(result: Mapping[str, Any]) -> None:
        heartbeat = result.get("heartbeat") or {}
        line = (
            f"[selection-scheduler] {heartbeat.get('tick_at')} minute={heartbeat.get('minute')} "
            f"status={result.get('status')} due={result.get('due_stages')}\n"
        )
        sys.stderr.write(line)
        # §21.2：调度日志按交易日沉淀到 log/selection-models/<date>/scheduler.log，不只在 stderr
        try:
            target = log_dir(str(heartbeat.get("trade_date") or "")) / "scheduler.log"
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(line)
        except (OSError, ValueError):
            pass

    summary = scheduler.run_forever(
        interval_s=getattr(args, "interval", None),
        max_ticks=getattr(args, "tick_max", None),
        records_provider=provider,
        context=context,
        on_tick=_log_tick,
    )
    _emit(summary)


def cmd_funnel(args) -> None:
    action = getattr(args, "funnel_cmd", None)
    if action in ("tick", "daemon"):
        _cmd_funnel_schedule(args, once=(action == "tick") or bool(getattr(args, "once", False)))
        return
    _cmd_funnel_run_or_validate(args)


__all__ = ["cmd_funnel"]
