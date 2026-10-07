# -*- coding: utf-8 -*-
"""编排器：按依赖执行整条层级漏斗（`run-all`，A8 / SSOT §9.3）。

- 只执行**已编译**的 `CompiledSelectionPlan`（正式运行只加载已发布且已激活的版本，§9.3 第2条）；
- 层级顺序由 `input` 依赖图 + `order` 决定，**不依赖 YAML 物理顺序**；
- 上游通过层级的候选作为下游输入；大盘门控失败进入 `BLOCKED`（非系统异常），
  候选耗尽进入 `EMPTY`，等待水位进入 `WAITING_DATA`；
- 每个层级的结果独立留痕，`run_id` 内容派生（T-03），**不伪造**任何行情或候选。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.selection_models.hash import short_hash
from core.strategy.funnel_engine import (
    VERDICT_UNKNOWN,
    FunnelEngine,
    RuleRegistry,
)
from core.strategy.stock_funnel import build_stock_rule_registry

ROOT_BINDING = "market.daily_universe"
CANDIDATE_SUFFIX = ".candidates"

STATUS_COMPLETED = "COMPLETED"
STATUS_EMPTY = "EMPTY"
STATUS_BLOCKED = "BLOCKED"
STATUS_WAITING_DATA = "WAITING_DATA"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"


class OrchestrationError(ValueError):
    """编排失败（依赖环、未知依赖等）；`code` 为稳定错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class StageOutcome:
    stage_id: str
    name: str
    kind: str
    status: str
    verdict: str
    input_count: int
    output_count: int
    missing_data_policy: str
    result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "verdict": self.verdict,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "missing_data_policy": self.missing_data_policy,
            "result": self.result,
        }


class SelectionModelOrchestrator:
    """按依赖顺序执行整条层级计划并汇总运行结果。"""

    def __init__(
        self,
        engine: Optional[FunnelEngine] = None,
        registry: Optional[RuleRegistry] = None,
    ) -> None:
        self.engine = engine or FunnelEngine(registry or build_stock_rule_registry())

    # ------------------------------------------------------------ 依赖排序
    @staticmethod
    def order_stages(plan: Any) -> List[Any]:
        stages = list(plan.stages)
        stage_ids = {stage.id for stage in stages}
        deps: Dict[str, Optional[str]] = {}
        for stage in stages:
            deps[stage.id] = _dependency_of(stage.input, stage_ids)
        resolved: List[Any] = []
        done: set = set()
        remaining = {stage.id: stage for stage in stages}
        while remaining:
            ready = [
                stage
                for stage_id, stage in remaining.items()
                if deps[stage_id] is None or deps[stage_id] in done
            ]
            if not ready:
                raise OrchestrationError(
                    "MODEL_CONFIG_INVALID", f"层级依赖存在环或未解析依赖: {sorted(remaining)}"
                )
            ready.sort(key=lambda item: (item.order, item.id))
            for stage in ready:
                resolved.append(stage)
                done.add(stage.id)
                remaining.pop(stage.id)
        return resolved

    # ------------------------------------------------------------ 执行
    def run_all(
        self,
        plan: Any,
        records: Sequence[Mapping[str, Any]],
        context: Optional[Mapping[str, Any]] = None,
        *,
        run_id: Optional[str] = None,
        trigger_type: str = "manual",
        triggered_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        ctx: Mapping[str, Any] = context or {}
        ordered = self.order_stages(plan)
        identifier = run_id or self._derive_run_id(plan)
        seed = [dict(item) for item in records]
        outputs: Dict[str, List[Dict[str, Any]]] = {}
        outcomes: List[StageOutcome] = []
        status = STATUS_COMPLETED
        final_stage: Optional[str] = None
        selections: List[str] = []
        current_stage: Optional[str] = None

        for stage in ordered:
            current_stage = stage.id
            dependency = _dependency_of(stage.input, {item.id for item in ordered})
            stage_inputs = outputs.get(dependency, seed) if dependency else seed

            if not stage.enabled:
                outputs[stage.id] = stage_inputs
                outcomes.append(
                    StageOutcome(
                        stage_id=stage.id,
                        name=stage.name,
                        kind=stage.kind,
                        status=STATUS_SKIPPED,
                        verdict=VERDICT_UNKNOWN,
                        input_count=len(stage_inputs),
                        output_count=len(stage_inputs),
                        missing_data_policy=stage.missing_data_policy,
                    )
                )
                continue

            result = self.engine.run_stage(stage.to_engine_stage(), stage_inputs, ctx)
            outputs[stage.id] = list(result.passed_records)
            outcomes.append(
                StageOutcome(
                    stage_id=stage.id,
                    name=stage.name,
                    kind=stage.kind,
                    status=result.status,
                    verdict=result.verdict,
                    input_count=result.input_count,
                    output_count=result.output_count,
                    missing_data_policy=stage.missing_data_policy,
                    result=result.to_dict(),
                )
            )
            if stage.scope == "universe_gate" and result.status == "BLOCKED":
                status, final_stage, selections = STATUS_BLOCKED, stage.id, []
                break
            if result.verdict == VERDICT_UNKNOWN and stage.missing_data_policy == "wait":
                status, final_stage, selections = STATUS_WAITING_DATA, stage.id, []
                break
            if result.output_count == 0:
                status, final_stage = STATUS_EMPTY, stage.id
                selections = []
                break
            final_stage = stage.id
            selections = [
                str(item.get("code"))
                for item in result.passed_records
                if item.get("code")
            ]

        payload = {
            "run_id": identifier,
            "status": status,
            "trigger_type": trigger_type,
            "triggered_by": triggered_by,
            "plan_hash": getattr(plan, "plan_hash", None),
            "compiler_version": getattr(plan, "compiler_version", None),
            "source_model": dict(getattr(plan, "source_model", {}) or {}),
            "current_stage": current_stage,
            "final_stage": final_stage,
            "stage_count": len(outcomes),
            "selected_codes": selections,
            "selected_count": len(selections),
            "stages": [outcome.to_dict() for outcome in outcomes],
            "run_metadata": {
                "calendar_version": ctx.get("calendar_version"),
                "calendar_available": ctx.get("calendar_available"),
            },
        }
        if ctx.get("data_snapshots") is not None:
            payload["run_metadata"]["data_snapshots"] = ctx["data_snapshots"]
        if ctx.get("data_gate") is not None:
            payload["run_metadata"]["data_gate"] = ctx["data_gate"]
        return payload

    @staticmethod
    def _derive_run_id(plan: Any) -> str:
        """内容派生 `run_id`：触发时间戳 + `plan_hash` 短哈希（T-03）。"""
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"selection_{stamp}_{short_hash(str(getattr(plan, 'plan_hash', '') or 'nohash'))}"


def _dependency_of(binding: Optional[str], stage_ids: set) -> Optional[str]:
    if not binding:
        return None
    text = str(binding)
    if text == ROOT_BINDING:
        return None
    if text.endswith(CANDIDATE_SUFFIX):
        candidate = text[: -len(CANDIDATE_SUFFIX)]
        if candidate in stage_ids:
            return candidate
    return None


__all__ = [
    "OrchestrationError",
    "SelectionModelOrchestrator",
    "StageOutcome",
    "STATUS_BLOCKED",
    "STATUS_COMPLETED",
    "STATUS_EMPTY",
    "STATUS_WAITING_DATA",
]