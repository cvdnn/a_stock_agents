# -*- coding: utf-8 -*-
"""模型综合评估 `ModelEvaluation`（E4 / SSOT §12.5 / §13.9）。

以「模型ID + 模型版本 + T+N 观察周期」形成批次，只统计**能由历史运行与已完成跟踪直接得到**
的指标（不引入参数敏感性、截面 IC、复杂漂移检测等后续研究能力）：

- 纳入分析的运行次数、完成跟踪的候选数与数据完整率；
- 各 T+N 周期的收益均值/中位数、上涨比例、MFE、MAE 与最大回撤；
- 相对大盘/行业的平均超额收益；
- 各层输入/淘汰/通过与候选流失率；
- 规则通过组与未通过组的后续表现差异（**仅在历史轨迹数据完整时计算**）；
- 按运行时间、行业或市场门控状态的简单分组对比；
- 不同模型版本在相同观察口径下的结果对比。

铁律：

- **单版本评价不得混入其他版本的运行与跟踪样本**（§22.1）；
- 评价主口径固定为**收盘价**（D-14），多口径仅旁证；
- 触发阈值由研究治理规则书面确定（D-16）：`样本≥30`、`最短观察周期≥20 交易日`、
  基准=沪深300；**样本不足时返回 `EVALUATION_SAMPLE_INSUFFICIENT`，不出强结论**（发布门禁 16）；
- 分别给出「选股模型评价」与「PositionPolicy 评价」，避免把建仓/止损问题错误归因到选股层级。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.selection_models.definition_repository import atomic_write_text, validate_model_id
from core.selection_models.paths import REPORTS_ROOT, evaluation_path
from core.selection_models.run_repository import RunRepository
from core.selection_models.tracking_service import TrackingService

#: D-16 研究治理阈值（默认值；参数可在配置中编辑，均纳入 definition_hash）。
DEFAULT_MIN_SAMPLES = 30
DEFAULT_MIN_OBSERVATION_DAYS = 20
DEFAULT_BENCHMARK = "沪深300"

CODE_SAMPLE_INSUFFICIENT = "EVALUATION_SAMPLE_INSUFFICIENT"


class ModelEvaluatorError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _median(values: Sequence[float]) -> Optional[float]:
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[len(ordered) // 2]


def _mean(values: Sequence[float]) -> Optional[float]:
    return round(sum(values) / len(values), 4) if values else None


class ModelEvaluator:
    """按模型版本汇总历史运行与跟踪观察，产出可追溯的 `ModelEvaluation`。"""

    def __init__(
        self,
        *,
        reports_root: Optional[Path] = None,
        run_repository: Optional[RunRepository] = None,
        tracking_service: Optional[TrackingService] = None,
    ) -> None:
        self.reports_root = Path(reports_root) if reports_root else REPORTS_ROOT
        self.runs = run_repository or RunRepository()
        self.tracking = tracking_service or TrackingService()

    def path(self, model_id: str, evaluation_id: str) -> Path:
        return evaluation_path(model_id, evaluation_id, root=self.reports_root)

    def load(self, model_id: str, evaluation_id: str) -> Dict[str, Any]:
        path = self.path(model_id, evaluation_id)
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def list_evaluations(self, model_id: str) -> List[Dict[str, Any]]:
        root = self.path(model_id, "_").parent
        if not root.is_dir():
            return []
        items: List[Dict[str, Any]] = []
        for path in sorted(root.glob("*.json")):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return items

    # ------------------------------------------------------------ 评估
    def evaluate(
        self,
        model_id: str,
        version: int,
        *,
        period: Optional[int] = None,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        min_observation_days: int = DEFAULT_MIN_OBSERVATION_DAYS,
        benchmark: str = DEFAULT_BENCHMARK,
        runs: Optional[Sequence[Mapping[str, Any]]] = None,
        observations: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        model_id = validate_model_id(model_id)
        version = int(version)
        run_list = list(runs) if runs is not None else self.runs.list_runs(model_id, version=version)
        obs = list(observations) if observations is not None else self._collect_observations(model_id, version)
        if period is not None:
            obs = [item for item in obs if int(item.get("period") or 0) == int(period)]

        samples = [item for item in obs if item.get("raw_return_pct") is not None]
        observation_days = len({str(item.get("target_trade_date")) for item in samples})
        evaluation_id = f"eval_v{version}_p{period if period is not None else 'all'}"
        base = {
            "evaluation_id": evaluation_id,
            "model_id": model_id,
            "model_version": version,
            "period": period,
            "benchmark": benchmark,
            "thresholds": {"min_samples": int(min_samples), "min_observation_days": int(min_observation_days)},
            "run_count": len(run_list),
            "completed_run_count": sum(1 for run in run_list if str(run.get("status")) == "COMPLETED"),
            "tracked_sample_count": len(samples),
            "observation_days": observation_days,
            "created_at": _now(),
        }

        if len(samples) < int(min_samples) or observation_days < int(min_observation_days):
            payload = {
                **base,
                "status": CODE_SAMPLE_INSUFFICIENT,
                "conclusion": "CONTINUE_OBSERVATION",
                "strong_conclusion_allowed": False,
                "reason": (
                    f"跟踪样本 {len(samples)} 少于下限 {min_samples} 或观察周期 {observation_days} 少于下限 "
                    f"{min_observation_days} 交易日；按 D-16 不触发强结论"
                ),
                "selection_model_evaluation": {"available": False, "reason_code": CODE_SAMPLE_INSUFFICIENT},
                "position_policy_evaluation": {"available": False, "reason_code": CODE_SAMPLE_INSUFFICIENT},
            }
            atomic_write_text(self.path(model_id, evaluation_id), json.dumps(payload, ensure_ascii=False, indent=2))
            return payload

        payload = {
            **base,
            "status": "OK",
            "conclusion": "OBSERVED",
            "strong_conclusion_allowed": True,
            "selection_model_evaluation": self._selection_evaluation(samples),
            "position_policy_evaluation": self._position_policy_evaluation(run_list),
            "layer_attrition": self._layer_attrition(run_list),
            "rule_group_comparison": self._rule_group_comparison(model_id, version, samples),
            "market_gate_grouping": self._market_gate_grouping(run_list, obs),
            "version_comparison": self._version_comparison(model_id, version, period),
            "caliber": "close",
        }
        atomic_write_text(self.path(model_id, evaluation_id), json.dumps(payload, ensure_ascii=False, indent=2))
        return payload

    # ------------------------------------------------------------ 采集
    def _collect_observations(self, model_id: str, version: int) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        for plan in self.tracking.list_plans(model_id=model_id):
            if int(plan.get("model_version") or 0) != int(version):
                continue  # 单版本评价不混入其他版本样本（§22.1）
            collected.extend(self.tracking.load_observations(str(plan.get("tracking_id"))))
        return collected

    # ------------------------------------------------------------ 指标
    @staticmethod
    def _selection_evaluation(samples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        returns = [float(item["raw_return_pct"]) for item in samples]
        mfes = [float(item["mfe_pct"]) for item in samples if item.get("mfe_pct") is not None]
        maes = [float(item["mae_pct"]) for item in samples if item.get("mae_pct") is not None]
        dds = [float(item["max_drawdown_pct"]) for item in samples if item.get("max_drawdown_pct") is not None]
        excess = [
            float(item["rel_index_return_pct"]) for item in samples
            if item.get("rel_index_return_pct") is not None
        ]
        up = [r for r in returns if r > 0]
        by_period: Dict[str, Dict[str, Any]] = {}
        for item in samples:
            key = str(int(item.get("period") or 0))
            bucket = by_period.setdefault(key, {"returns": [], "mfes": [], "maes": []})
            bucket["returns"].append(float(item["raw_return_pct"]))
            if item.get("mfe_pct") is not None:
                bucket["mfes"].append(float(item["mfe_pct"]))
            if item.get("mae_pct") is not None:
                bucket["maes"].append(float(item["mae_pct"]))
        period_metrics = {
            key: {
                "sample_count": len(bucket["returns"]),
                "mean_return_pct": _mean(bucket["returns"]),
                "median_return_pct": _median(bucket["returns"]),
                "up_ratio": round(len([r for r in bucket["returns"] if r > 0]) / len(bucket["returns"]), 4)
                if bucket["returns"] else None,
                "mean_mfe_pct": _mean(bucket["mfes"]),
                "mean_mae_pct": _mean(bucket["maes"]),
            }
            for key, bucket in sorted(by_period.items(), key=lambda kv: int(kv[0]))
        }
        return {
            "available": True,
            "sample_count": len(returns),
            "mean_return_pct": _mean(returns),
            "median_return_pct": _median(returns),
            "up_ratio": round(len(up) / len(returns), 4) if returns else None,
            "mean_mfe_pct": _mean(mfes),
            "mean_mae_pct": _mean(maes),
            "mean_max_drawdown_pct": _mean(dds),
            "mean_excess_return_pct": _mean(excess),
            "period_metrics": period_metrics,
        }

    @staticmethod
    def _position_policy_evaluation(run_list: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        """PositionPolicy 评价：仅当存在回测摘要时汇总，否则如实标记不可用。"""
        metrics = [dict(run.get("backtest_summary") or {}) for run in run_list if run.get("backtest_summary")]
        if not metrics:
            return {"available": False, "reason_code": "NO_POSITION_POLICY_BACKTESTS"}

        def _collect(key: str) -> List[float]:
            return [float(item[key]) for item in metrics if item.get(key) is not None]

        return {
            "available": True,
            "sample_count": len(metrics),
            "mean_cagr_pct": _mean(_collect("annualized_cagr_pct")),
            "mean_max_drawdown_pct": _mean(_collect("max_drawdown_pct")),
            "mean_sharpe": _mean(_collect("sharpe_ratio")),
            "mean_win_rate_pct": _mean(_collect("win_rate_pct")),
            "note": "PositionPolicy 评价与选股模型评价分列，避免将建仓/止损问题归因到选股层级",
        }

    def _layer_attrition(self, run_list: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        aggregated: Dict[str, Dict[str, int]] = {}
        for run in run_list:
            for stage in self.runs.load_run_stages(str(run.get("run_id"))):
                stage_id = str(stage.get("stage_id") or "")
                if not stage_id:
                    continue
                bucket = aggregated.setdefault(stage_id, {"input": 0, "output": 0})
                bucket["input"] += int(stage.get("input_count") or 0)
                bucket["output"] += int(stage.get("output_count") or 0)
        layers = {}
        for stage_id, bucket in aggregated.items():
            eliminated = max(bucket["input"] - bucket["output"], 0)
            layers[stage_id] = {
                "input_count": bucket["input"],
                "passed_count": bucket["output"],
                "eliminated_count": eliminated,
                "attrition_rate": round(eliminated / bucket["input"], 4) if bucket["input"] else 0.0,
            }
        return {"available": bool(layers), "layers": layers}

    def _rule_group_comparison(
        self, model_id: str, version: int, samples: Sequence[Mapping[str, Any]]
    ) -> Dict[str, Any]:
        """规则通过组/未通过组后续表现差异；历史轨迹不完整时不计算（§12.5）。"""
        observed_codes = {str(item.get("code")) for item in samples}
        failed_by_code: Dict[str, List[str]] = {}
        for run in self.runs.list_runs(model_id, version=version):
            for trace in self.runs.load_run_candidates(str(run.get("run_id"))):
                for rule in trace.get("failed_rules") or []:
                    failed_by_code.setdefault(str(trace.get("code")), []).append(str(rule))
        if not failed_by_code:
            return {
                "available": False,
                "reason_code": "NO_FAILED_GROUP_OBSERVATIONS",
                "note": "未通过组无跟踪样本，无法对比通过/未通过组表现（不得臆造差异）",
            }
        # 未通过组需有跟踪样本才可对比；当前跟踪仅覆盖最终候选，故如实标记不可用。
        failed_tracked = [code for code in failed_by_code if code in observed_codes]
        if not failed_tracked:
            return {
                "available": False,
                "reason_code": "NO_FAILED_GROUP_OBSERVATIONS",
                "failed_rule_codes": len(failed_by_code),
            }
        return {"available": True, "failed_tracked_codes": failed_tracked}

    @staticmethod
    def _market_gate_grouping(
        run_list: Sequence[Mapping[str, Any]], samples: Sequence[Mapping[str, Any]]
    ) -> Dict[str, Any]:
        states: Dict[str, int] = {}
        for run in run_list:
            gate = dict((run.get("run_metadata") or {}).get("data_gate") or {})
            state = str(gate.get("state") or "UNKNOWN")
            states[state] = states.get(state, 0) + 1
        return {"available": bool(states), "run_gate_distribution": states, "sample_count": len(samples)}

    def _version_comparison(self, model_id: str, version: int, period: Optional[int]) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        for item in self.list_evaluations(model_id):
            if int(item.get("model_version") or 0) == int(version):
                continue
            if item.get("period") != period:
                continue
            selection = dict(item.get("selection_model_evaluation") or {})
            rows.append(
                {
                    "model_version": item.get("model_version"),
                    "status": item.get("status"),
                    "mean_return_pct": selection.get("mean_return_pct"),
                    "sample_count": selection.get("sample_count"),
                }
            )
        return {"available": bool(rows), "other_versions": rows}


__all__ = [
    "CODE_SAMPLE_INSUFFICIENT",
    "DEFAULT_BENCHMARK",
    "DEFAULT_MIN_OBSERVATION_DAYS",
    "DEFAULT_MIN_SAMPLES",
    "ModelEvaluator",
    "ModelEvaluatorError",
]