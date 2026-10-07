# -*- coding: utf-8 -*-
"""Tracker Tick：执行到期的实时 / T+N 观察任务（E3 / SSOT §12.4、§12.7 / §22.2）。

契约：

- **独立 Tracker Tick** 驱动观察，与选股运行使用**不同幂等键和状态机**，不阻塞下一次选股（§12.7）；
- T+N 观察点由**证券交易日历**计算到期日（§12.4：N 按交易日，不按自然日）；
- **只执行到期观察**：未到期的周期不产生观察；
- **重复 Tick 幂等**：同一 `(code, period)` 已存在观察即跳过，绝不重复落盘（发布门禁 14）；
- **本地数据水位未就绪时不写伪观察值**：目标交易日缺 bar 时进入 `WAITING_DATA` 且不落盘，允许后续 Tick 重试；
- 每个观察绑定原始 `run_id`、`signal_id`、模型版本、基准价格、`as_of` 与数据版本（可完整追溯）。

调度器不自行采集行情：`records_provider` 由数据装配层注入，缺数据一律失败关闭。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

try:  # 中国无夏令时，UTC+8 与 Asia/Shanghai 等价
    from zoneinfo import ZoneInfo

    _SHANGHAI_TZ: Any = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    _SHANGHAI_TZ = timezone(timedelta(hours=8))

from core.data.sync_engine import DB_PATH, TradeCalendar
from core.selection_models.market_view import (
    Bar,
    MarketViewError,
    annualized_volatility_pct,
    max_drawdown_pct,
    mfe_mae_pct,
    normalize_bars,
    nth_trading_date,
)
from core.selection_models.tracking_service import (
    STATUS_ACTIVE,
    STATUS_COMPLETED,
    STATUS_CREATED,
    STATUS_WAITING_DATA,
    TERMINAL_STATUSES,
    TrackingService,
)

RecordsProvider = Callable[[str, str], Optional[Any]]


def _default_now() -> datetime:
    return datetime.now(_SHANGHAI_TZ)


class TrackerScheduler:
    """按交易日历执行到期跟踪观察的 Tick 调度器。"""

    def __init__(
        self,
        *,
        service: Optional[TrackingService] = None,
        db_path: Optional[Any] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.service = service or TrackingService()
        self.db_path = db_path or DB_PATH
        self._now = now_fn or _default_now

    def is_trading_day(self, day: str) -> bool:
        return bool(TradeCalendar.is_trading_day(day, db_path=self.db_path))

    def _bars(self, record: Any) -> Optional[Sequence[Bar]]:
        if record is None:
            return None
        try:
            return normalize_bars(record)
        except MarketViewError:
            return None

    def tick(
        self,
        now: Optional[datetime] = None,
        *,
        records_provider: Optional[RecordsProvider] = None,
        benchmark_provider: Optional[RecordsProvider] = None,
    ) -> Dict[str, Any]:
        """执行一次 Tracker Tick：只处理到期且未记录的观察点。"""
        moment = (now or self._now()).astimezone(_SHANGHAI_TZ)
        today = moment.date().isoformat()
        appended = 0
        idempotent_skips = 0
        waiting = 0
        not_due = 0
        processed: list = []

        for plan in self.service.list_plans():
            if str(plan.get("status")) in TERMINAL_STATUSES:
                continue
            tracking_id = str(plan["tracking_id"])
            signal_date = str(plan.get("signal_date"))
            recorded = {
                (str(o.get("code")), int(o.get("period") or 0))
                for o in self.service.load_observations(tracking_id)
            }
            plan_waiting = False
            plan_appended = False
            for code in plan.get("codes") or []:
                base_price = float((plan.get("base_prices") or {}).get(code) or 0.0)
                for period in plan.get("periods") or []:
                    key = (str(code), int(period))
                    target_date = nth_trading_date(signal_date, int(period), db_path=self.db_path)
                    if target_date is None or target_date > today:
                        not_due += 1
                        continue
                    if key in recorded:
                        idempotent_skips += 1
                        continue
                    record = records_provider(str(code), target_date) if records_provider else None
                    bars = self._bars(record)
                    if not bars:
                        plan_waiting = True
                        waiting += 1
                        continue
                    observation = self._build_observation(
                        plan, code, int(period), target_date, base_price, bars,
                        benchmark_provider=benchmark_provider, today=today,
                    )
                    if observation is None:
                        plan_waiting = True
                        waiting += 1
                        continue
                    outcome = self.service.append_observation(tracking_id, observation)
                    if outcome["appended"]:
                        appended += 1
                        plan_appended = True
                        processed.append(observation)
                    else:
                        idempotent_skips += 1

            # 状态收敛：全部周期已记录 → COMPLETED；有到期但缺数据 → WAITING_DATA；否则 ACTIVE
            existing = self.service.load_observations(tracking_id)
            total = len(plan.get("codes") or []) * len(plan.get("periods") or [])
            if total and len(existing) >= total:
                self.service.set_status(tracking_id, STATUS_COMPLETED)
            elif plan_waiting:
                self.service.set_status(tracking_id, STATUS_WAITING_DATA)
            elif plan_appended or str(plan.get("status")) == STATUS_CREATED:
                self.service.set_status(tracking_id, STATUS_ACTIVE)

        return {
            "status": "TICKED",
            "tick_at": moment.isoformat(timespec="seconds"),
            "trade_date": today,
            "appended": appended,
            "idempotent_skips": idempotent_skips,
            "waiting_data": waiting,
            "not_due": not_due,
            "observations": processed,
        }

    def _build_observation(
        self,
        plan: Mapping[str, Any],
        code: str,
        period: int,
        target_date: str,
        base_price: float,
        bars: Sequence[Bar],
        *,
        benchmark_provider: Optional[RecordsProvider],
        today: str,
    ) -> Optional[Dict[str, Any]]:
        target_bar = next((bar for bar in bars if bar.date == target_date), None)
        if target_bar is None:
            return None  # 目标交易日无 bar（停牌/未同步）：等待，不写伪观察
        if base_price <= 0:
            return None
        window = [bar for bar in bars if bar.date <= target_date]
        if not window:
            return None
        base = base_price
        profile = mfe_mae_pct(window, base_price=base)
        closes = [bar.close for bar in window]
        rel_index = None
        if benchmark_provider is not None:
            bench = self._bars(benchmark_provider(str(plan.get("benchmark") or ""), target_date))
            if bench:
                bench_base = next((bar for bar in bench if bar.date <= str(plan.get("signal_date"))), None)
                bench_target = next((bar for bar in bench if bar.date == target_date), None)
                if bench_base and bench_target and bench_base.close:
                    index_return = (bench_target.close / bench_base.close - 1.0) * 100.0
                    raw_return = (target_bar.close / base - 1.0) * 100.0
                    rel_index = round(raw_return - index_return, 4)
        industry = (plan.get("industry") or {}).get(code)
        return {
            "tracking_id": str(plan.get("tracking_id")),
            "run_id": str(plan.get("run_id")),
            "signal_id": f"{plan.get('run_id')}:{code}",
            "model_id": str(plan.get("model_id")),
            "model_version": int(plan.get("model_version") or 0),
            "code": code,
            "period": int(period),
            "signal_date": str(plan.get("signal_date")),
            "target_trade_date": target_date,
            "as_of": f"{target_date}T15:00:00+08:00",
            "observed_at": datetime.now(_SHANGHAI_TZ).isoformat(timespec="seconds"),
            "base_price": round(base, 4),
            "close": round(target_bar.close, 4),
            "raw_return_pct": round((target_bar.close / base - 1.0) * 100.0, 4),
            "adj_return_pct": None,  # 无复权数据时不伪造（§12.4 需复权收益时另行补数）
            "rel_index_return_pct": rel_index,
            "rel_industry_return_pct": None,
            "mfe_pct": profile["mfe_pct"],
            "mae_pct": profile["mae_pct"],
            "max_drawdown_pct": max_drawdown_pct(closes),
            "volatility_pct": annualized_volatility_pct(closes),
            "trade_status": "tradable",
            "events": [],
            "industry": industry,
            "data_version": str((plan.get("signal_date") or today)) + "|" + target_date,
            "caliber": "close",
        }


__all__ = ["TrackerScheduler"]