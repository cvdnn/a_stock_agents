# -*- coding: utf-8 -*-
"""结果个股研究评估 `ResultAssessment`（E1 / SSOT §12.1 / §13.7）。

为每个最终候选生成结构化评估，至少包含：

| 分组 | 内容 |
|---|---|
| 个股信息 | 代码、名称、上市板、流通市值、交易状态、风险标签、`as_of` 行情与关键事件 |
| 入选解释 | 来源模型/版本/运行、命中层级、通过规则、关键观测值、同批排名、证据链接 |
| 技术与风险画像 | 趋势、动量、波动率、ATR、成交活跃度、跳空、回撤、流动性、停牌/涨跌停风险 |
| 历史行为 | 相似信号历史次数、T+N 收益分布、MFE/MAE、最大回撤 |
| 相对表现 | 相对大盘/行业的超额收益与胜率 |
| 建仓/持股策略 | 结构化 `PositionPolicy`（研究方案，非下单指令） |

铁律：

- 个股信息必须绑定 `assessment_as_of` 与 `data_snapshot_id`；**盘后报告不得使用次日数据**（§12.1）；
- 两类回测口径严格分离（信号标记 vs 交易策略回测，§12.2）；
- **回测/跟踪结果不得被描述为未来收益保证**（发布门禁 12）；
- **建仓与持股策略是研究方案，系统不存在自动实盘下单路径**（发布门禁 17）;
- 数据缺失一律如实标注"不可用"，不伪造任何数值。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.selection_models.backtest_service import (
    BacktestServiceError,
    event_backtest,
    markout_analysis,
)
from core.selection_models.definition_repository import atomic_write_text
from core.selection_models.market_view import (
    Bar,
    MarketViewError,
    PRICE_CALIBER,
    annualized_volatility_pct,
    atr_value,
    board_of,
    limit_prices,
    max_drawdown_pct,
    moving_average,
    normalize_bars,
    simple_returns,
)
from core.selection_models.paths import REPORTS_ROOT, assessment_path
from core.selection_models.position_policy import build_position_policy
from core.selection_models.run_repository import RunRepository

#: 回测/跟踪结果的统一解释口径（发布门禁 12：不得描述为未来收益保证）。
INTERPRETATION = (
    "历史回测与跟踪结果仅代表过去样本的表现，不构成对未来收益的任何保证或承诺；"
    "样本量、市场环境与摩擦成本的变化均可能导致结果显著偏离。"
)
RESEARCH_ONLY_NOTICE = (
    "建仓与持股策略为可回测的研究方案，非交易指令；系统不存在自动实盘下单路径。"
)


class ResultAssessmentError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _snapshot_id(run: Mapping[str, Any]) -> Optional[str]:
    meta = dict(run.get("run_metadata") or {})
    snapshots = meta.get("data_snapshots") or []
    for item in snapshots:
        if isinstance(item, Mapping) and item.get("data_snapshot_id"):
            return str(item["data_snapshot_id"])
    return run.get("data_snapshot_id")


class ResultAssessmentService:
    """按 `run_id` 生成/读取逐候选结果研究评估。"""

    def __init__(
        self,
        *,
        reports_root: Optional[Path] = None,
        run_repository: Optional[RunRepository] = None,
    ) -> None:
        self.reports_root = Path(reports_root) if reports_root else REPORTS_ROOT
        self.runs = run_repository or RunRepository()

    def path(self, run_id: str) -> Path:
        return assessment_path(run_id, root=self.reports_root)

    def load(self, run_id: str) -> Dict[str, Any]:
        path = self.path(run_id)
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------ 生成
    def generate(
        self,
        run_id: str,
        *,
        records_by_code: Mapping[str, Any],
        benchmarks: Optional[Mapping[str, Any]] = None,
        account_equity: Optional[float] = None,
        planned_entry_prices: Optional[Mapping[str, float]] = None,
        risk_per_trade_pct: float = 1.0,
        history_observations: Optional[Sequence[Mapping[str, Any]]] = None,
        horizons: Optional[Sequence[int]] = None,
        initial_cash: float = 1_000_000.0,
        as_of: Optional[str] = None,
    ) -> Dict[str, Any]:
        run = self.runs.load_run(run_id)
        if not run:
            raise ResultAssessmentError("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")
        candidates = self.runs.load_run_candidates(run_id)
        stages = self.runs.load_run_stages(run_id)
        selected = [str(code) for code in (run.get("selected_codes") or [])]
        benchmark_map = dict(benchmarks or {})
        entry_map = dict(planned_entry_prices or {})
        history = list(history_observations or [])

        assessments: List[Dict[str, Any]] = []
        for rank, code in enumerate(selected, start=1):
            record = records_by_code.get(code)
            assessments.append(
                self._assess_one(
                    run=run,
                    code=code,
                    rank=rank,
                    record=record,
                    candidates=candidates,
                    stages=stages,
                    benchmarks=benchmark_map,
                    account_equity=account_equity,
                    planned_entry_price=entry_map.get(code),
                    risk_per_trade_pct=risk_per_trade_pct,
                    history=history,
                    horizons=horizons,
                    initial_cash=initial_cash,
                    as_of=as_of,
                )
            )

        payload = {
            "run_id": run_id,
            "model_id": run.get("model_id"),
            "model_version": run.get("model_version"),
            "signal_trade_date": run.get("signal_trade_date"),
            "assessment_as_of": as_of or _now(),
            "data_snapshot_id": _snapshot_id(run),
            "price_caliber": PRICE_CALIBER,
            "research_only": True,
            "future_returns_guaranteed": False,
            "interpretation": INTERPRETATION,
            "research_only_notice": RESEARCH_ONLY_NOTICE,
            "assessments": assessments,
            "generated_at": _now(),
        }
        atomic_write_text(self.path(run_id), json.dumps(payload, ensure_ascii=False, indent=2))
        return payload

    # ------------------------------------------------------------ 单候选
    def _assess_one(
        self,
        *,
        run: Mapping[str, Any],
        code: str,
        rank: int,
        record: Any,
        candidates: Sequence[Mapping[str, Any]],
        stages: Sequence[Mapping[str, Any]],
        benchmarks: Mapping[str, Any],
        account_equity: Optional[float],
        planned_entry_price: Optional[float],
        risk_per_trade_pct: float,
        history: Sequence[Mapping[str, Any]],
        horizons: Optional[Sequence[int]],
        initial_cash: float,
        as_of: Optional[str],
    ) -> Dict[str, Any]:
        signal_date = str(run.get("signal_trade_date") or "")[:10]
        signal_id = f"{run.get('run_id')}:{code}"
        evidence = _selection_evidence(code, candidates, stages, rank)
        evidence["evidence_link"]["run_id"] = run.get("run_id")

        bars: Optional[List[Bar]] = None
        try:
            bars = normalize_bars(record) if record else None
        except MarketViewError:
            bars = None

        security = _security_info(code, record, bars, as_of)
        profile = _technical_risk_profile(bars, code)
        relative = _relative_performance(bars, benchmarks, signal_date)
        history_behavior = _history_behavior(code, history)
        entry_price = planned_entry_price
        if entry_price is None and bars:
            entry_price = bars[-1].close
        policy = build_position_policy(
            code=code,
            name=security.get("name"),
            bars=bars,
            account_equity=account_equity,
            planned_entry_price=entry_price,
            risk_per_trade_pct=risk_per_trade_pct,
        )

        markout: Dict[str, Any] = {"available": False, "reason_code": "MODEL_DATA_MISSING"}
        trading: Dict[str, Any] = {"available": False, "reason_code": "MODEL_DATA_MISSING"}
        if bars and signal_date:
            try:
                markout = markout_analysis(bars, signal_date=signal_date, horizons=horizons or (1, 3, 5, 10, 20), as_of=as_of)
                markout = {"available": True, **markout}
            except BacktestServiceError as exc:
                markout = {"available": False, "reason_code": exc.code, "message": str(exc)}
            try:
                trading = event_backtest(
                    bars, policy, code=code, signal_date=signal_date,
                    initial_cash=initial_cash, as_of=as_of,
                )
                trading = {"available": True, **trading}
            except BacktestServiceError as exc:
                trading = {"available": False, "reason_code": exc.code, "message": str(exc)}

        return {
            "code": code,
            "signal_id": signal_id,
            "data_available": bars is not None,
            "security": security,
            "selection_evidence": evidence,
            "technical_risk_profile": profile,
            "history_behavior": history_behavior,
            "relative_performance": relative,
            "position_policy": policy,
            "markout_analysis": markout,
            "trading_backtest": trading,
        }


# ------------------------------------------------------------------ 组装辅助
def _security_info(code: str, record: Any, bars: Optional[Sequence[Bar]], as_of: Optional[str]) -> Dict[str, Any]:
    data = dict(record) if isinstance(record, Mapping) else {}
    last_close = bars[-1].close if bars else None
    return {
        "code": code,
        "name": data.get("name"),
        "industry": data.get("industry"),
        "board": board_of(code),
        "circulating_market_cap": data.get("circulating_market_cap"),
        "trade_status": data.get("trade_status") or ("tradable" if bars else "unknown"),
        "risk_tags": list(data.get("risk_tags") or []),
        "as_of": as_of,
        "last_close": round(last_close, 4) if last_close is not None else None,
        "key_events": list(data.get("events") or []),
    }


def _technical_risk_profile(bars: Optional[Sequence[Bar]], code: str) -> Dict[str, Any]:
    if not bars:
        return {"available": False, "reason_code": "MODEL_DATA_MISSING"}
    closes = [bar.close for bar in bars]
    last = closes[-1]
    ma20 = moving_average(closes, 20)
    ma60 = moving_average(closes, 60)
    returns = simple_returns(closes)
    momentum = (last / closes[-21] - 1.0) * 100.0 if len(closes) >= 21 else None
    volume_ratio = None
    volumes = [bar.volume for bar in bars if bar.volume]
    if len(volumes) >= 6 and volumes[-6]:
        volume_ratio = round(volumes[-1] / (sum(volumes[-6:-1]) / 5.0), 4)
    gap_pct = None
    if len(closes) >= 2 and closes[-2]:
        gap_pct = round((last / closes[-2] - 1.0) * 100.0, 4)
    _, limit_down = limit_prices(code, closes[-2] if len(closes) >= 2 else last)
    risk_flags: List[str] = []
    if ma20 is not None and last < ma20:
        risk_flags.append("below_ma20")
    if momentum is not None and momentum < -10:
        risk_flags.append("momentum_weak")
    return {
        "available": True,
        "trend": {
            "above_ma20": None if ma20 is None else last >= ma20,
            "above_ma60": None if ma60 is None else last >= ma60,
            "ma20": ma20,
            "ma60": ma60,
        },
        "momentum_20d_pct": None if momentum is None else round(momentum, 4),
        "volatility_annualized_pct": annualized_volatility_pct(closes),
        "atr": atr_value(bars),
        "volume_activity_ratio": volume_ratio,
        "last_gap_pct": gap_pct,
        "window_max_drawdown_pct": max_drawdown_pct(closes),
        "liquidity": {"avg_volume": round(sum(volumes) / len(volumes), 2) if volumes else None},
        "suspension_risk": "unknown",
        "limit_down_price": round(limit_down, 2) if limit_down else None,
        "risk_flags": risk_flags,
        "return_series_count": len(returns),
    }


def _relative_performance(
    bars: Optional[Sequence[Bar]], benchmarks: Mapping[str, Any], signal_date: str
) -> Dict[str, Any]:
    if not bars or not benchmarks:
        return {"available": False, "reason_code": "NO_BENCHMARK_DATA"}
    start = str(signal_date)[:10]
    window = [bar for bar in bars if bar.date >= start]
    if len(window) < 2:
        return {"available": False, "reason_code": "WINDOW_TOO_SHORT"}
    stock_return = (window[-1].close / window[0].close - 1.0) * 100.0
    excess: Dict[str, Any] = {}
    for name, record in benchmarks.items():
        try:
            bench_bars = normalize_bars(record)
        except MarketViewError:
            continue
        bench_window = [bar for bar in bench_bars if bar.date >= start]
        if len(bench_window) < 2:
            continue
        bench_return = (bench_window[-1].close / bench_window[0].close - 1.0) * 100.0
        excess[str(name)] = {
            "benchmark_return_pct": round(bench_return, 4),
            "excess_return_pct": round(stock_return - bench_return, 4),
        }
    if not excess:
        return {"available": False, "reason_code": "NO_BENCHMARK_DATA"}
    return {
        "available": True,
        "stock_return_pct": round(stock_return, 4),
        "benchmarks": excess,
        "win_vs_benchmark": {name: item["excess_return_pct"] > 0 for name, item in excess.items()},
    }


def _history_behavior(code: str, history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    samples = [dict(item) for item in history if str(item.get("code")) == str(code)]
    if not samples:
        return {"available": False, "reason_code": "NO_HISTORY_OBSERVATIONS"}
    returns = [float(item["raw_return_pct"]) for item in samples if item.get("raw_return_pct") is not None]
    mfes = [float(item["mfe_pct"]) for item in samples if item.get("mfe_pct") is not None]
    maes = [float(item["mae_pct"]) for item in samples if item.get("mae_pct") is not None]
    ordered = sorted(returns)
    median = ordered[len(ordered) // 2] if ordered else None
    return {
        "available": True,
        "similar_signal_count": len(samples),
        "mean_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
        "median_return_pct": round(median, 4) if median is not None else None,
        "mean_mfe_pct": round(sum(mfes) / len(mfes), 4) if mfes else None,
        "mean_mae_pct": round(sum(maes) / len(maes), 4) if maes else None,
        "max_drawdown_pct": max((float(item.get("max_drawdown_pct") or 0.0) for item in samples), default=None),
    }


def _selection_evidence(
    code: str,
    candidates: Sequence[Mapping[str, Any]],
    stages: Sequence[Mapping[str, Any]],
    rank: int,
) -> Dict[str, Any]:
    trace = [dict(item) for item in candidates if str(item.get("code")) == str(code)]
    hit_stages: List[str] = []
    passed_rules: List[Dict[str, Any]] = []
    for stage in stages:
        result = dict(stage.get("result") or {})
        for record in result.get("passed_records") or []:
            if str(record.get("code")) != str(code):
                continue
            stage_id = stage.get("stage_id") or result.get("stage_id")
            if stage_id and stage_id not in hit_stages:
                hit_stages.append(str(stage_id))
            audit = dict(record.get("_funnel") or {})
            for rule in audit.get("rules") or []:
                passed_rules.append(
                    {
                        "stage": stage_id,
                        "rule_id": rule.get("rule_id"),
                        "verdict": rule.get("verdict"),
                        "observed": rule.get("observed"),
                        "expected": rule.get("expected"),
                    }
                )
    return {
        "rank_in_batch": rank,
        "hit_stages": hit_stages,
        "passed_rules": passed_rules,
        "candidate_trace": trace,
        "evidence_link": {
            "nodes_endpoint": "/api/selection-models/runs/{run_id}/nodes",
            "candidates_endpoint": "/api/selection-models/runs/{run_id}/candidates",
        },
    }


__all__ = [
    "INTERPRETATION",
    "RESEARCH_ONLY_NOTICE",
    "ResultAssessmentError",
    "ResultAssessmentService",
]