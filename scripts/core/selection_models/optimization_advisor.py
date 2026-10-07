# -*- coding: utf-8 -*-
"""基于历史跟踪的简单调优建议 `OptimizationSuggestion`（E5 / SSOT §12.6 / §13.9）。

首期调优**只读取**已完成的历史 `SelectionModelRun`、对应最终候选以及后续
`TrackingObservation`，不引入自动寻参、实验版本、压力测试或影子运行编排。

首期建议类型（§12.6）：规则过严/过松、层级流失异常、运行时间段偏弱、规则通过组与未通过组
差异不明显、行业/市值/市场环境分化、数据新鲜度关联。每条建议必须包含：来源模型及版本、
统计区间、运行次数、跟踪样本数、适用 T+N 周期、对比指标、涉及层级/规则、建议修改项、
建议值或方向、依据、风险提示与置信等级；**样本不足时只显示"继续观察"，不得生成强建议**。

铁律（发布门禁 16/19，研究治理 §3.2）：

- 建议**只读保存**：不自动创建草稿、不修改参数、不发布、不激活；
- 建议必须可追溯到具体 `run_id` 与观察样本；
- 活动版本变化后，来源旧版本的既有建议重新判定为 `STALE`；
- 首期仅支持查看与标记处理状态：`pending → accepted | ignored`。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.selection_models.definition_repository import atomic_write_text, validate_model_id
from core.selection_models.model_evaluator import (
    CODE_SAMPLE_INSUFFICIENT,
    DEFAULT_BENCHMARK,
    DEFAULT_MIN_OBSERVATION_DAYS,
    DEFAULT_MIN_SAMPLES,
    ModelEvaluator,
)
from core.selection_models.paths import REPORTS_ROOT, suggestions_path
from core.selection_models.run_repository import RunRepository

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_IGNORED = "ignored"
STATUS_STALE = "stale"
_MARKABLE = {STATUS_ACCEPTED, STATUS_IGNORED}

SUGGESTION_TYPES = (
    "rule_threshold",
    "layer_attrition",
    "time_window",
    "rule_priority",
    "scope",
    "data_freshness",
    "continue_observation",
)

_RISK_NOTICE = (
    "本建议仅基于历史样本统计，不代表未来收益；采纳与否由人工决定，系统不会自动改版。"
)


class OptimizationAdvisorError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class OptimizationAdvisor:
    """只读优化建议生成与状态标记（不触碰模型定义/版本）。"""

    def __init__(
        self,
        *,
        reports_root: Optional[Path] = None,
        run_repository: Optional[RunRepository] = None,
        evaluator: Optional[ModelEvaluator] = None,
    ) -> None:
        self.reports_root = Path(reports_root) if reports_root else REPORTS_ROOT
        self.runs = run_repository or RunRepository()
        self.evaluator = evaluator or ModelEvaluator(run_repository=self.runs)

    def path(self, model_id: str) -> Path:
        return suggestions_path(model_id, root=self.reports_root)

    def _load(self, model_id: str) -> Dict[str, Any]:
        path = self.path(model_id)
        if not path.is_file():
            return {"model_id": model_id, "suggestions": [], "generated_at": None}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"model_id": model_id, "suggestions": [], "generated_at": None}

    def list_suggestions(self, model_id: str, *, active_version: Optional[int] = None) -> Dict[str, Any]:
        """列出建议；来源版本与当前活动版本不一致时，重新判定为 `STALE`。"""
        payload = self._load(model_id)
        suggestions = []
        for item in payload.get("suggestions") or []:
            entry = dict(item)
            if (
                active_version is not None
                and int(entry.get("source_model_version") or 0) != int(active_version)
                and entry.get("status") in {STATUS_PENDING, STATUS_ACCEPTED, STATUS_IGNORED}
            ):
                entry["status"] = STATUS_STALE
                entry["stale_reason"] = (
                    f"活动版本已切换为 v{active_version}，来源 v{entry.get('source_model_version')} 的建议失效"
                )
            suggestions.append(entry)
        return {
            "model_id": model_id,
            "active_version": active_version,
            "suggestions": suggestions,
            "total": len(suggestions),
            "generated_at": payload.get("generated_at"),
            "read_only": True,
            "auto_apply": False,
        }

    # ------------------------------------------------------------ 生成
    def suggest(
        self,
        model_id: str,
        version: int,
        *,
        period: Optional[int] = None,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        min_observation_days: int = DEFAULT_MIN_OBSERVATION_DAYS,
        benchmark: str = DEFAULT_BENCHMARK,
        evaluation: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        model_id = validate_model_id(model_id)
        version = int(version)
        evaluation = dict(evaluation) if evaluation is not None else self.evaluator.evaluate(
            model_id, version, period=period, min_samples=min_samples,
            min_observation_days=min_observation_days, benchmark=benchmark,
        )
        run_list = self.runs.list_runs(model_id, version=version)
        run_ids = [str(run.get("run_id")) for run in run_list]
        window = _statistical_window(run_list)

        if str(evaluation.get("status")) == CODE_SAMPLE_INSUFFICIENT:
            generated = [_continue_observation(evaluation, version, period, window, run_ids)]
        else:
            generated = self._derive(evaluation, version, period, window, run_ids)

        # 保留既有处理状态（建议只读；重新生成不覆盖人工标记）
        existing = {str(item.get("suggestion_id")): item for item in self._load(model_id).get("suggestions") or []}
        for item in generated:
            prior = existing.get(str(item["suggestion_id"]))
            if prior and prior.get("status") in {STATUS_ACCEPTED, STATUS_IGNORED}:
                item["status"] = prior["status"]
                item["handled_by"] = prior.get("handled_by")
                item["handled_at"] = prior.get("handled_at")

        payload = {
            "model_id": model_id,
            "source_model_version": version,
            "read_only": True,
            "auto_apply": False,
            "generated_at": _now(),
            "suggestions": generated,
        }
        atomic_write_text(self.path(model_id), json.dumps(payload, ensure_ascii=False, indent=2))
        return {**payload, "total": len(generated), "evidence_run_ids": run_ids}

    def _derive(
        self,
        evaluation: Mapping[str, Any],
        version: int,
        period: Optional[int],
        window: Dict[str, Any],
        run_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        selection = dict(evaluation.get("selection_model_evaluation") or {})
        suggestions: List[Dict[str, Any]] = []
        sample_count = int(selection.get("sample_count") or 0)
        confidence = "high" if sample_count >= 100 else ("medium" if sample_count >= 60 else "low")

        mean_return = selection.get("mean_return_pct")
        up_ratio = selection.get("up_ratio")
        if mean_return is not None and mean_return < 0:
            suggestions.append(_suggestion(
                index=len(suggestions), version=version, period=period, window=window, run_ids=run_ids,
                suggestion_type="rule_threshold",
                comparison_metric="mean_return_pct", observed=mean_return,
                layer=None, rule=None,
                suggested_change="复核入池阈值是否过松，建议收紧关键过滤条件后重新观察",
                direction="tighten", confidence=confidence, sample_count=sample_count,
            ))
        if up_ratio is not None and up_ratio < 0.4:
            suggestions.append(_suggestion(
                index=len(suggestions), version=version, period=period, window=window, run_ids=run_ids,
                suggestion_type="rule_priority",
                comparison_metric="up_ratio", observed=up_ratio,
                layer=None, rule=None,
                suggested_change="上涨比例偏低，建议降低区分度不足规则的优先级或停用观察",
                direction="deprioritize", confidence=confidence, sample_count=sample_count,
            ))

        layers = dict((evaluation.get("layer_attrition") or {}).get("layers") or {})
        for stage_id, stats in layers.items():
            if float(stats.get("attrition_rate") or 0) >= 0.95 and int(stats.get("input_count") or 0) >= 10:
                suggestions.append(_suggestion(
                    index=len(suggestions), version=version, period=period, window=window, run_ids=run_ids,
                    suggestion_type="layer_attrition",
                    comparison_metric="layer_attrition_rate", observed=stats.get("attrition_rate"),
                    layer=stage_id, rule=None,
                    suggested_change=f"层级 {stage_id} 候选流失异常，建议检查规则组合或缺失数据策略",
                    direction="investigate", confidence=confidence, sample_count=sample_count,
                ))

        excess = selection.get("mean_excess_return_pct")
        if excess is not None and excess < 0:
            suggestions.append(_suggestion(
                index=len(suggestions), version=version, period=period, window=window, run_ids=run_ids,
                suggestion_type="scope",
                comparison_metric="mean_excess_return_pct", observed=excess,
                layer=None, rule=None,
                suggested_change="相对基准超额为负，建议复核适用范围或增加市场门控",
                direction="restrict_scope", confidence=confidence, sample_count=sample_count,
            ))

        return suggestions

    # ------------------------------------------------------------ 状态标记
    def mark_status(
        self,
        model_id: str,
        suggestion_id: str,
        status: str,
        *,
        operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        """标记建议处理状态；仅 `pending → accepted | ignored`，绝不修改模型定义。"""
        if status not in _MARKABLE:
            raise OptimizationAdvisorError("MODEL_CONFIG_INVALID", f"不支持的建议状态: {status}")
        payload = self._load(model_id)
        found = None
        for item in payload.get("suggestions") or []:
            if str(item.get("suggestion_id")) == str(suggestion_id):
                found = item
                break
        if found is None:
            raise OptimizationAdvisorError("OPTIMIZATION_SUGGESTION_NOT_FOUND", f"建议不存在: {suggestion_id}")
        found["status"] = status
        found["handled_by"] = operator
        found["handled_at"] = _now()
        atomic_write_text(self.path(model_id), json.dumps(payload, ensure_ascii=False, indent=2))
        return found


# ------------------------------------------------------------------ 组装辅助
def _statistical_window(run_list: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    started = sorted(str(run.get("started_at") or run.get("created_at") or "") for run in run_list)
    return {
        "start": started[0] if started else None,
        "end": started[-1] if started else None,
        "run_count": len(run_list),
    }


def _continue_observation(
    evaluation: Mapping[str, Any], version: int, period: Optional[int], window: Dict[str, Any], run_ids: Sequence[str]
) -> Dict[str, Any]:
    return _suggestion(
        index=0, version=version, period=period, window=window, run_ids=run_ids,
        suggestion_type="continue_observation",
        comparison_metric="sample_count", observed=evaluation.get("tracked_sample_count"),
        layer=None, rule=None,
        suggested_change="样本不足，仅登记为继续观察，不生成强优化建议",
        direction="observe", confidence="low",
        sample_count=int(evaluation.get("tracked_sample_count") or 0),
    )


def _suggestion(
    *,
    index: int,
    version: int,
    period: Optional[int],
    window: Mapping[str, Any],
    run_ids: Sequence[str],
    suggestion_type: str,
    comparison_metric: str,
    observed: Any,
    layer: Optional[str],
    rule: Optional[str],
    suggested_change: str,
    direction: str,
    confidence: str,
    sample_count: int,
) -> Dict[str, Any]:
    return {
        "suggestion_id": f"sug_v{version}_p{period if period is not None else 'all'}_{suggestion_type}_{index}",
        "suggestion_type": suggestion_type,
        "source_model_version": int(version),
        "applicable_period": period,
        "statistical_window": dict(window),
        "run_count": int(window.get("run_count") or len(run_ids)),
        "sample_count": int(sample_count),
        "comparison_metric": comparison_metric,
        "observed_value": observed,
        "layer": layer,
        "rule": rule,
        "suggested_change": suggested_change,
        "direction": direction,
        "suggested_value": None,  # 首期不给出可直接套用的精确补丁值
        "evidence_run_ids": list(run_ids),
        "risk_notice": _RISK_NOTICE,
        "confidence": confidence,
        "status": STATUS_PENDING,
        "read_only": True,
        "auto_apply": False,
        "created_at": _now(),
    }


__all__ = [
    "OptimizationAdvisor",
    "OptimizationAdvisorError",
    "STATUS_ACCEPTED",
    "STATUS_IGNORED",
    "STATUS_PENDING",
    "STATUS_STALE",
    "SUGGESTION_TYPES",
]