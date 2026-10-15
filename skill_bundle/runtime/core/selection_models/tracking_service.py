# -*- coding: utf-8 -*-
"""实时 / T+N 持续跟踪：`TrackingPlan` 与 `TrackingObservation` 存储（E3 / SSOT §12.4 / §13.8）。

契约：

- 每次正式选股运行可按配置创建 `TrackingPlan`，也允许只跟踪部分候选（§12.4）；
- `TrackingPlan` 保存来源 `run_id`、`model_version`、模式、观察周期、频率、**基准价格**、
  比较基准、到期点与状态；
- `TrackingObservation` **以追加方式**保存每个观察点的价格路径、收益、MFE/MAE、相对收益、
  事件与数据版本；**补数只能追加新观察，绝不覆盖已用于评估的历史记录**（发布门禁 14）；
- 跟踪失败不改写原始选股结果；跟踪任务与选股运行使用**不同幂等键与状态机**。

状态机（§12.4）：`CREATED` / `ACTIVE` / `WAITING_DATA` / `COMPLETED` / `EXPIRED` /
`CANCELLED` / `FAILED`。

本模块只做跟踪状态的装配与持久化，不读取行情、不产出选股结论；观察值的计算由
`tracker_scheduler` 在水位就绪后注入。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.selection_models import paths
from core.selection_models.definition_repository import atomic_write_text, validate_model_id
from core.selection_models.hash import digest, short_hash
from core.selection_models.market_view import market_config

MODE_REALTIME = "realtime"
MODE_TPN = "t_plus_n"
MODE_EVENT = "event"
MODES = (MODE_REALTIME, MODE_TPN, MODE_EVENT)

STATUS_CREATED = "CREATED"
STATUS_ACTIVE = "ACTIVE"
STATUS_WAITING_DATA = "WAITING_DATA"
STATUS_COMPLETED = "COMPLETED"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELLED = "CANCELLED"
STATUS_FAILED = "FAILED"
TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_EXPIRED, STATUS_CANCELLED, STATUS_FAILED})

#: 默认 T+N 观察点（D-13 建议值：T+1/T+3/T+5/T+10/T+20）。
DEFAULT_PERIODS = (1, 3, 5, 10, 20)


class TrackingError(ValueError):
    """跟踪相关错误；`code` 为稳定错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class TrackingService:
    """`TrackingPlan` 与不可变 `TrackingObservation` 序列的持久化仓库。"""

    def __init__(self, *, root: Optional[Path] = None) -> None:
        # `root` 为**缓存根**（`output/cache/selection-models`）；跟踪目录由其派生。
        self.cache_root = Path(root) if root else paths.CACHE_ROOT

    @property
    def root(self) -> Path:
        """跟踪目录 `output/cache/selection-models/tracking/`（§13.10）。"""
        return paths.tracking_dir(root=self.cache_root)

    # ------------------------------------------------------------ 路径
    def plan_dir(self, tracking_id: str) -> Path:
        return paths.tracking_plan_dir(tracking_id, root=self.cache_root)

    def plan_path(self, tracking_id: str) -> Path:
        return paths.tracking_plan_path(tracking_id, root=self.cache_root)

    def observations_path(self, tracking_id: str) -> Path:
        return paths.tracking_observations_path(tracking_id, root=self.cache_root)

    # ------------------------------------------------------------ 计划
    @staticmethod
    def make_tracking_id(*, run_id: str, mode: str, signal_date: str, codes: Sequence[str]) -> str:
        payload = {"run_id": str(run_id), "mode": str(mode), "signal_date": str(signal_date)[:10],
                   "codes": sorted(str(c) for c in codes)}
        return f"track_{short_hash(digest(payload))}"

    def create_plan(
        self,
        *,
        run_id: str,
        model_id: str,
        model_version: int,
        signal_date: str,
        codes: Sequence[str],
        base_prices: Mapping[str, float],
        mode: str = MODE_TPN,
        periods: Sequence[int] = DEFAULT_PERIODS,
        benchmark: Optional[str] = None,
        frequency: Optional[str] = None,
        industry: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        """创建跟踪计划（同一 run/mode/日期/代码集合幂等）；缺基准价即失败关闭。"""
        if mode not in MODES:
            raise TrackingError("MODEL_TRIGGER_INVALID", f"未知跟踪模式: {mode}")
        model_id = validate_model_id(model_id)
        code_list = [str(c).strip() for c in codes if str(c).strip()]
        if not code_list:
            raise TrackingError("MODEL_CONFIG_INVALID", "跟踪计划至少需要一个候选代码")
        missing = [c for c in code_list if not base_prices.get(c)]
        if missing:
            raise TrackingError("MODEL_DATA_MISSING", f"缺少基准价格，无法建立跟踪计划: {missing}")
        period_list = sorted({int(p) for p in periods if int(p) > 0})
        if not period_list:
            raise TrackingError("MODEL_CONFIG_INVALID", "观察周期不能为空")

        tracking_id = self.make_tracking_id(
            run_id=run_id, mode=mode, signal_date=str(signal_date)[:10], codes=code_list
        )
        existing = self.get_plan(tracking_id, required=False)
        if existing is not None:
            return existing

        fee_cfg = market_config()
        plan = {
            "tracking_id": tracking_id,
            "run_id": str(run_id),
            "model_id": model_id,
            "model_version": int(model_version),
            "signal_date": str(signal_date)[:10],
            "mode": mode,
            "periods": period_list,
            "frequency": frequency,
            "benchmark": benchmark or fee_cfg.get("default_benchmark", "sh000001"),
            "base_prices": {str(c): float(base_prices[c]) for c in code_list},
            "codes": code_list,
            "industry": {str(k): v for k, v in (industry or {}).items()},
            "status": STATUS_CREATED,
            "due_trade_date": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        atomic_write_text(self.plan_path(tracking_id), json.dumps(plan, ensure_ascii=False, indent=2))
        atomic_write_text(self.observations_path(tracking_id), json.dumps({"tracking_id": tracking_id, "observations": []},
                                                                          ensure_ascii=False, indent=2))
        return plan

    def get_plan(self, tracking_id: str, *, required: bool = True) -> Optional[Dict[str, Any]]:
        payload = _read_json(self.plan_path(tracking_id))
        if payload is None and required:
            raise TrackingError("TRACKING_PLAN_NOT_FOUND", f"跟踪计划不存在: {tracking_id}")
        return payload

    def list_plans(
        self,
        *,
        run_id: Optional[str] = None,
        model_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        plans: List[Dict[str, Any]] = []
        if not self.root.is_dir():
            return plans
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            plan = _read_json(child / "plan.json")
            if not plan:
                continue
            if run_id and str(plan.get("run_id")) != str(run_id):
                continue
            if model_id and str(plan.get("model_id")) != str(model_id):
                continue
            if status and str(plan.get("status")) != str(status):
                continue
            plans.append(plan)
        plans.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return plans

    def update_plan(self, tracking_id: str, patch: Mapping[str, Any]) -> Dict[str, Any]:
        plan = self.get_plan(tracking_id)
        plan.update({k: v for k, v in dict(patch).items() if v is not None})
        plan["updated_at"] = _now()
        atomic_write_text(self.plan_path(tracking_id), json.dumps(plan, ensure_ascii=False, indent=2))
        return plan

    def set_status(self, tracking_id: str, status: str) -> Dict[str, Any]:
        if status not in {
            STATUS_CREATED, STATUS_ACTIVE, STATUS_WAITING_DATA, STATUS_COMPLETED,
            STATUS_EXPIRED, STATUS_CANCELLED, STATUS_FAILED,
        }:
            raise TrackingError("MODEL_CONFIG_INVALID", f"未知跟踪状态: {status}")
        return self.update_plan(tracking_id, {"status": status})

    # ------------------------------------------------------------ 观察序列（只追加）
    def load_observations(self, tracking_id: str) -> List[Dict[str, Any]]:
        payload = _read_json(self.observations_path(tracking_id)) or {}
        return list(payload.get("observations") or [])

    def append_observation(self, tracking_id: str, observation: Mapping[str, Any]) -> Dict[str, Any]:
        """追加一个观察点；同一 `(code, period)` 已存在时**幂等跳过**，绝不覆盖历史。"""
        self.get_plan(tracking_id)
        record = dict(observation)
        code = str(record.get("code") or "")
        period = int(record.get("period") or 0)
        if not code or period <= 0:
            raise TrackingError("MODEL_CONFIG_INVALID", "观察点必须包含 code 与 period")
        observations = self.load_observations(tracking_id)
        for existing in observations:
            if str(existing.get("code")) == code and int(existing.get("period") or 0) == period:
                return {"appended": False, "idempotent": True, "observation": existing}
        record.setdefault("tracking_id", tracking_id)
        record.setdefault("recorded_at", _now())
        observations.append(record)
        observations.sort(key=lambda item: (int(item.get("period") or 0), str(item.get("code") or "")))
        atomic_write_text(
            self.observations_path(tracking_id),
            json.dumps({"tracking_id": tracking_id, "observations": observations}, ensure_ascii=False, indent=2),
        )
        return {"appended": True, "idempotent": False, "observation": record}

    def summary(self, tracking_id: str) -> Dict[str, Any]:
        plan = self.get_plan(tracking_id)
        return {"plan": plan, "observations": self.load_observations(tracking_id)}


__all__ = [
    "DEFAULT_PERIODS",
    "MODES",
    "MODE_EVENT",
    "MODE_REALTIME",
    "MODE_TPN",
    "STATUS_ACTIVE",
    "STATUS_COMPLETED",
    "STATUS_CREATED",
    "STATUS_EXPIRED",
    "STATUS_FAILED",
    "STATUS_WAITING_DATA",
    "TERMINAL_STATUSES",
    "TrackingError",
    "TrackingService",
]