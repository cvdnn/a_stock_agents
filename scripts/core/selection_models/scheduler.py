# -*- coding: utf-8 -*-
"""选股调度器：内置 Tick 常驻循环 + 交易日历门控（B1 / O-01 / §10）。

调度契约（O-01）：

- **一个固定 Scheduler Tick + 配置决定阶段触发**：真实读取模型各阶段的 `schedule`
  窗口（如 `15:35-23:59` / `09:30-09:35` / `09:30-09:31` / `09:36-09:40`），
  窗口端点可配置（D-06），不写死；
- **交易日历门控**（§10.4 / 发布门禁 4）：非交易日（周末/法定节假日）**不执行早盘策略**，
  日历不可用时不猜测开市；
- **同分钟不重复执行**（§10.5 / 门禁 7）：分层幂等键
  `run-node:<model_id>:<version>:<stage>:<trade_date>:<minute>` 落盘去重（B2/B4）；
- **运行锁**：层级执行期持有 `model_id+trade_date` 排他锁（B2），多进程互斥；
- **Signal Latch**：`converge_at_window_end` 层级窗口内仅记待定、窗口末唯一终态（B3）；
- 优雅退出：`run_forever` 支持 `SIGINT/SIGTERM` 停机标志与 `max_ticks` 上限。

调度器不自行采集行情、不伪造候选：数据装配由 `DataAssembler` 注入（`records_provider`），
缺数据时按失败关闭返回 `WAITING_DATA` 且不标记该分钟为已执行（可在后续 Tick 重试）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

try:  # 中国无夏令时，UTC+8 与 Asia/Shanghai 等价
    from zoneinfo import ZoneInfo

    _SHANGHAI_TZ: Any = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    _SHANGHAI_TZ = timezone(timedelta(hours=8))

from core.data.sync_engine import DB_PATH, TradeCalendar
from core.selection_models.run_lock import RunLockManager
from core.selection_models.run_repository import RunRepository
from core.selection_models.signal_latch import SignalLatch, minute_of
from core.strategy.funnel_engine import FunnelEngine
from core.strategy.stock_funnel import build_stock_rule_registry

DEFAULT_TICK_INTERVAL_SECONDS = 60

STATUS_IDLE = "IDLE"
STATUS_SKIPPED_NON_TRADING_DAY = "SKIPPED_NON_TRADING_DAY"
STATUS_EXECUTED = "EXECUTED"
STATUS_WAITING_DATA = "WAITING_DATA"
STATUS_FAILED = "FAILED"

#: 视为「终态」并写入幂等键的阶段结果；`WAITING_DATA` 不标记，允许后续 Tick 重试。
_TERMINAL_STATUSES = frozenset({"PASSED", "NO_MATCH", "EMPTY", "BLOCKED", "SKIPPED"})


class ScheduleError(ValueError):
    code = "MODEL_SCHEDULE_INVALID"


@dataclass(frozen=True)
class ScheduleWindow:
    """单个阶段的时间窗（闭区间，`HH:MM` 语义）。"""

    stage_id: str
    scope: str
    start: str
    end: str
    start_minute: int
    end_minute: int
    enabled: bool = True

    def contains(self, minute: str) -> bool:
        current = minute_of(minute)
        return self.start_minute <= current <= self.end_minute


def parse_schedule(spec: Any, *, stage_id: str = "") -> tuple[str, str]:
    """解析 `HH:MM-HH:MM` 形态；非法即失败关闭（与 `stock_funnel` 校验同口径）。"""
    if not isinstance(spec, str) or spec.count("-") != 1:
        raise ScheduleError(f"stage {stage_id}: schedule 必须是 'HH:MM-HH:MM'，实际 {spec!r}")
    start, end = spec.split("-")
    for token in (start, end):
        if not (len(token) == 5 and token[2] == ":" and token[:2].isdigit() and token[3:].isdigit()):
            raise ScheduleError(f"stage {stage_id}: schedule 端点非法 {token!r}")
        if not (0 <= int(token[:2]) <= 23 and 0 <= int(token[3:]) <= 59):
            raise ScheduleError(f"stage {stage_id}: schedule 端点越界 {token!r}")
    if end <= start:
        raise ScheduleError(f"stage {stage_id}: schedule 结束不得早于或等于开始，实际 {spec!r}")
    return start, end


def _default_now() -> datetime:
    return datetime.now(_SHANGHAI_TZ)


class SelectionScheduler:
    """按 `schedule` 窗口与交易日历驱动阶段执行的 Tick 调度器。"""

    def __init__(
        self,
        plan: Any,
        *,
        db_path: Optional[Path] = None,
        engine: Optional[FunnelEngine] = None,
        run_repository: Optional[RunRepository] = None,
        lock_manager: Optional[RunLockManager] = None,
        signal_latch: Optional[SignalLatch] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
        tick_interval_s: int = DEFAULT_TICK_INTERVAL_SECONDS,
    ) -> None:
        self.plan = plan
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.engine = engine or FunnelEngine(build_stock_rule_registry())
        self.runs = run_repository or RunRepository()
        self.locks = lock_manager or RunLockManager()
        self.latch = signal_latch or SignalLatch()
        self._now = now_fn or _default_now
        self.tick_interval_s = int(tick_interval_s)
        model = dict(getattr(plan, "source_model", {}) or {})
        self.model_id = str(model.get("model_id") or "")
        self.model_version = int(model.get("model_version") or 0)
        if not self.model_id:
            raise ScheduleError("编译计划缺少 source_model.model_id，无法调度")
        self._windows = self._build_windows(plan)

    # ------------------------------------------------------------ 时间窗
    @staticmethod
    def _build_windows(plan: Any) -> List[ScheduleWindow]:
        windows: List[ScheduleWindow] = []
        for stage in getattr(plan, "stages", ()):  # type: ignore[union-attr]
            trigger = getattr(stage, "trigger", None)
            if not trigger:
                continue
            start, end = parse_schedule(trigger, stage_id=str(getattr(stage, "id", "")))
            windows.append(
                ScheduleWindow(
                    stage_id=str(stage.id),
                    scope=str(getattr(stage, "scope", "candidate_filter")),
                    start=start,
                    end=end,
                    start_minute=minute_of(start),
                    end_minute=minute_of(end),
                    enabled=bool(getattr(stage, "enabled", True)),
                )
            )
        return windows

    @property
    def windows(self) -> List[ScheduleWindow]:
        return list(self._windows)

    def due_windows(self, now: datetime) -> List[ScheduleWindow]:
        """当前分钟落在哪些启用阶段的时间窗内（闭区间）。"""
        minute = now.astimezone(_SHANGHAI_TZ).strftime("%H:%M")
        return [window for window in self._windows if window.enabled and window.contains(minute)]

    def next_run_at(self, now: datetime) -> Optional[str]:
        """今日下一个尚未到达的窗口开始时刻（供心跳/Web 显示）；无则 None。"""
        current = minute_of(now.astimezone(_SHANGHAI_TZ).strftime("%H:%M"))
        upcoming = sorted(window.start_minute for window in self._windows if window.enabled and window.start_minute > current)
        return f"{upcoming[0] // 60:02d}:{upcoming[0] % 60:02d}" if upcoming else None

    # ------------------------------------------------------------ Tick
    def is_trading_day(self, now: datetime) -> bool:
        return bool(TradeCalendar.is_trading_day(now.astimezone(_SHANGHAI_TZ), db_path=self.db_path))

    def tick(
        self,
        now: Optional[datetime] = None,
        *,
        records_provider: Optional[Callable[[ScheduleWindow], Optional[Sequence[Mapping[str, Any]]]]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行一次固定 Tick：门控 → 计算到期阶段 → 幂等/加锁 → 执行 → 落盘。"""
        moment = (now or self._now()).astimezone(_SHANGHAI_TZ)
        trade_date = moment.date().isoformat()
        minute = moment.strftime("%H:%M")
        heartbeat = {
            "tick_at": moment.isoformat(timespec="seconds"),
            "trade_date": trade_date,
            "minute": minute,
        }
        if not self.is_trading_day(moment):
            # §10.4：非交易日不得运行早盘策略；不猜测开市、不补跑
            return {
                "status": STATUS_SKIPPED_NON_TRADING_DAY,
                "reason_code": "NON_TRADING_DAY",
                "model_id": self.model_id,
                "model_version": self.model_version,
                "due_stages": [],
                "executed": [],
                "idempotent_skips": 0,
                "lock_contended": 0,
                "heartbeat": heartbeat,
                "next_run_at": None,
            }

        due = self.due_windows(moment)
        executed: List[Dict[str, Any]] = []
        idempotent_skips = 0
        lock_contended = 0
        for window in due:
            outcome = self._run_window(window, trade_date, minute, moment, records_provider, context)
            if outcome["status"] == "IDEMPOTENT_SKIP":
                idempotent_skips += 1
            elif outcome["status"] == "LOCK_CONTENDED":
                lock_contended += 1
            executed.append(outcome)

        if not due:
            status = STATUS_IDLE
        elif any(item["status"] == "FAILED" for item in executed):
            status = STATUS_FAILED
        elif executed and all(item["status"] == "IDEMPOTENT_SKIP" for item in executed):
            status = STATUS_IDLE
        else:
            status = STATUS_EXECUTED
        return {
            "status": status,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "due_stages": [window.stage_id for window in due],
            "executed": executed,
            "idempotent_skips": idempotent_skips,
            "lock_contended": lock_contended,
            "heartbeat": heartbeat,
            "next_run_at": self.next_run_at(moment),
            "signal_latch": self.latch.summary(self.model_id, self.model_version, trade_date),
        }

    def _run_window(
        self,
        window: ScheduleWindow,
        trade_date: str,
        minute: str,
        moment: datetime,
        records_provider: Optional[Callable[[ScheduleWindow], Optional[Sequence[Mapping[str, Any]]]]],
        context: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        key = f"run-node:{self.model_id}:{self.model_version}:{window.stage_id}:{trade_date}:{minute}"
        if self.runs.is_marked(self.model_id, trade_date, key):
            return {"stage_id": window.stage_id, "status": "IDEMPOTENT_SKIP", "idempotency_key": key}

        lock = self.locks.acquire(
            self.model_id,
            trade_date,
            run_id=key,
            stage_id=window.stage_id,
            timeout_s=0.0,
        )
        if lock is None:
            return {"stage_id": window.stage_id, "status": "LOCK_CONTENDED", "idempotency_key": key}
        try:
            return self._execute_window(window, trade_date, minute, moment, records_provider, context, key)
        finally:
            self.locks.release(self.model_id, trade_date)

    def _execute_window(
        self,
        window: ScheduleWindow,
        trade_date: str,
        minute: str,
        moment: datetime,
        records_provider: Optional[Callable[[ScheduleWindow], Optional[Sequence[Mapping[str, Any]]]]],
        context: Optional[Mapping[str, Any]],
        key: str,
    ) -> Dict[str, Any]:
        stage = self._stage(window.stage_id)
        records: Optional[Sequence[Mapping[str, Any]]] = None
        if records_provider is not None:
            records = records_provider(window)
        if records is None:
            # 失败关闭：不产码、不标记该分钟，允许后续 Tick 在水位就绪后重试
            self.runs.record_stage(self.model_id, trade_date, window.stage_id, {
                "status": STATUS_WAITING_DATA, "reason_code": "DATA_NOT_ASSEMBLED", "minute": minute,
            })
            return {"stage_id": window.stage_id, "status": STATUS_WAITING_DATA,
                    "reason_code": "DATA_NOT_ASSEMBLED", "selected_codes": [], "idempotency_key": key}

        result = self.engine.run_stage(stage.to_engine_stage(), records, dict(context or {}))
        selected = [str(item.get("code")) for item in result.passed_records if item.get("code")]
        run_payload = {
            "run_id": f"selection_{trade_date.replace('-', '')}_{key.rsplit(':', 1)[-1].replace(':', '')}_{window.stage_id}",
            "trigger_type": "scheduler",
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_type": str((getattr(self.plan, "source_model", {}) or {}).get("model_type") or ""),
            "stage_id": window.stage_id,
            "stage_status": result.status,
            "verdict": result.verdict,
            "signal_trade_date": trade_date,
            "started_at": moment.isoformat(timespec="seconds"),
            "input_count": result.input_count,
            "output_count": result.output_count,
            "selected_codes": selected,
            "plan_hash": getattr(self.plan, "plan_hash", None),
            "idempotency_key": key,
        }
        self.runs.save_run(run_payload)

        converged: Optional[Dict[str, Any]] = None
        if self._converges(stage):
            self.latch.register_pending(
                self.model_id, self.model_version, trade_date,
                run_id=run_payload["run_id"], codes=selected,
                window_end=window.end,
                hit_at=moment.isoformat(timespec="seconds"),
            )
            # 窗口末（含端点）一次性收敛为唯一终态
            if minute_of(minute) >= window.end_minute:
                converged = self.latch.converge(
                    self.model_id, self.model_version, trade_date,
                    now=moment.isoformat(timespec="seconds"), window_end=window.end,
                )

        terminal = result.status in _TERMINAL_STATUSES
        if terminal:
            self.runs.mark_once(self.model_id, trade_date, key)
        self.runs.record_stage(self.model_id, trade_date, window.stage_id, {
            "status": result.status, "minute": minute,
            "selected_codes": selected, "idempotency_key": key,
        })
        if selected:
            self.runs.save_candidates(trade_date, self.model_id, {
                "model_id": self.model_id, "model_version": self.model_version,
                "signal_trade_date": trade_date, "stage_id": window.stage_id,
                "run_id": run_payload["run_id"], "selected_codes": selected,
                "plan_hash": getattr(self.plan, "plan_hash", None),
            })
        return {
            "stage_id": window.stage_id,
            "status": result.status,
            "terminal": terminal,
            "selected_codes": selected,
            "output_count": result.output_count,
            "idempotency_key": key,
            "signal_latch": converged,
        }

    def _stage(self, stage_id: str) -> Any:
        for stage in getattr(self.plan, "stages", ()):  # type: ignore[union-attr]
            if str(stage.id) == stage_id:
                return stage
        raise ScheduleError(f"编译计划不存在阶段 {stage_id}")

    @staticmethod
    def _converges(stage: Any) -> bool:
        return any(
            str(rule.get("output_policy")) == "converge_at_window_end"
            for rule in getattr(stage, "rules", ())
        )

    # ------------------------------------------------------------ 常驻循环
    def run_forever(
        self,
        *,
        interval_s: Optional[int] = None,
        max_ticks: Optional[int] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        records_provider: Optional[Callable[[ScheduleWindow], Optional[Sequence[Mapping[str, Any]]]]] = None,
        context: Optional[Mapping[str, Any]] = None,
        install_signal_handlers: bool = True,
        on_tick: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """常驻 Tick 循环；`SIGINT/SIGTERM` 触发优雅退出，或达到 `max_ticks` 上限。"""
        import signal

        interval = int(interval_s or self.tick_interval_s)
        sleeper = sleep_fn or time.sleep
        stop = {"flag": False, "signal": None}

        def _handle(signum, _frame):  # pragma: no cover - 信号分支
            stop["flag"] = True
            stop["signal"] = signal.Signals(signum).name

        previous: Dict[int, Any] = {}
        if install_signal_handlers and hasattr(signal, "SIGINT"):  # pragma: no cover - 平台分支
            for name in ("SIGINT", "SIGTERM"):
                sig = getattr(signal, name, None)
                if sig is None:
                    continue
                try:
                    previous[int(sig)] = signal.getsignal(sig)
                    signal.signal(sig, _handle)
                except (ValueError, OSError):
                    pass

        ticks: List[Dict[str, Any]] = []
        try:
            while not stop["flag"]:
                result = self.tick(records_provider=records_provider, context=context)
                ticks.append(result)
                if on_tick is not None:
                    on_tick(result)
                if max_ticks is not None and len(ticks) >= int(max_ticks):
                    break
                sleeper(interval)
        except KeyboardInterrupt:  # pragma: no cover - 交互中断
            stop["flag"] = True
            stop["signal"] = stop["signal"] or "KeyboardInterrupt"
        finally:  # pragma: no cover - 平台分支
            if install_signal_handlers:
                for signum, handler in previous.items():
                    try:
                        signal.signal(signum, handler)
                    except (ValueError, OSError):
                        pass

        return {
            "status": "STOPPED",
            "stopped_by": stop["signal"],
            "tick_count": len(ticks),
            "ticks": ticks,
            "last_tick": ticks[-1] if ticks else None,
        }


__all__ = [
    "DEFAULT_TICK_INTERVAL_SECONDS",
    "STATUS_EXECUTED",
    "STATUS_IDLE",
    "STATUS_SKIPPED_NON_TRADING_DAY",
    "ScheduleError",
    "ScheduleWindow",
    "SelectionScheduler",
    "parse_schedule",
]