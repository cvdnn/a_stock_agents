# -*- coding: utf-8 -*-
"""
Algorithm Production Monitoring, Alpha Decay & Regime Adaptive Dispatcher (ALCM Phase 3).

Provides industrial-grade production operations:
1. AlphaDecayTracker: Spearman Rank IC, rolling IC_IR, win rate, and decay alarm.
2. RegimeAdaptiveDispatcher: Market regime-driven dynamic factor weighting,
   strategy routing, and portfolio target exposure calibration.
3. AlgorithmLifecycleManager: Lifecycle state transitions, performance-based
   decommissioning/retirement breakers, and compliance audit trail.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from core.config import get_logger
from core.models.base_algorithm import (
    AlgorithmCategory,
    AlgorithmLifecycleStage,
    AlgorithmMetadata,
    BaseAlgorithm,
)
from core.models.factor_synthesizer import FactorSynthesizer
from core.models.registry import AlgoRegistry

logger = get_logger("core.models.monitor_governance")


class DecayStatus(str, Enum):
    """Alpha factor or strategy validity decay status."""
    HEALTHY = "healthy"              # Solid IC and consistent predictive power
    DECAY_WARNING = "decay_warning"  # Recent IC deterioration, performance near threshold
    DECAY_CRITICAL = "decay_critical" # Structural alpha exhaustion, negative IC or sharp breakdown


@dataclass
class RegimeDispatchPlan:
    """Actionable adaptive dispatch plan generated for the current market regime."""
    regime: str                          # BULL / OSCILLATION / BEAR / DEFAULT
    health_score: float                  # 0 - 100 overall market score
    factor_weights: Dict[str, float]     # Dynamic synthesis weights for FactorSynthesizer
    primary_strategies: List[str]        # Priority trading strategies in this regime
    max_portfolio_weight: float          # Recommended aggregate portfolio exposure limit (0.0 - 1.0)
    stop_loss_pct: float                 # Dynamic stop-loss percentage buffer
    action_advice: str                   # Tactical guidance summary
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime,
            "health_score": round(self.health_score, 1),
            "factor_weights": dict(self.factor_weights),
            "primary_strategies": list(self.primary_strategies),
            "max_portfolio_weight": round(self.max_portfolio_weight, 2),
            "stop_loss_pct": round(self.stop_loss_pct, 2),
            "action_advice": self.action_advice,
            "created_at": self.created_at,
        }


# ==============================================================================
# 1. Alpha 衰减追踪器 (AlphaDecayTracker)
# ==============================================================================
class AlphaDecayTracker(BaseAlgorithm):
    """
    Real-time & Rolling Alpha Factor Decay Tracker.

    Calculates:
    - Cross-sectional Spearman Rank IC between factor score and forward return.
    - Rolling Mean IC, IC Standard Deviation, and Information Ratio (IC_IR).
    - IC Win Rate (proportion of positive IC periods).
    - Multi-stage decay alarm (HEALTHY -> DECAY_WARNING -> DECAY_CRITICAL).
    """

    def __init__(self, lookback_periods: int = 20, metadata: Optional[AlgorithmMetadata] = None, **kwargs: Any):
        super().__init__(metadata=metadata)
        self.lookback_periods = lookback_periods
        # Structure: {factor_name: [{"date": str, "ic": float}]}
        self._history: Dict[str, List[Dict[str, Any]]] = {}

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Default execution: generate decay report for given factor name."""
        factor_name = args[0] if args else kwargs.get("factor_name", "DEFAULT")
        return self.get_decay_report(factor_name)

    @staticmethod
    def _rank(values: List[float]) -> List[float]:
        """Compute fractional ranks for a list of values (average rank for ties)."""
        n = len(values)
        if n == 0:
            return []
        indexed = sorted(enumerate(values), key=lambda x: x[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and indexed[j][1] == indexed[j + 1][1]:
                j += 1
            avg_rank = (i + j + 2) / 2.0  # 1-based average rank
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    @classmethod
    def calculate_rank_ic(
        cls,
        factor_scores: Dict[str, float],
        forward_returns: Dict[str, float],
    ) -> float:
        """
        Compute cross-sectional Spearman Rank IC for a single period.
        """
        common_symbols = sorted(set(factor_scores.keys()) & set(forward_returns.keys()))
        n = len(common_symbols)
        if n < 4:
            return 0.0

        scores = [float(factor_scores[s]) for s in common_symbols]
        rets = [float(forward_returns[s]) for s in common_symbols]

        rank_x = cls._rank(scores)
        rank_y = cls._rank(rets)

        # Pearson correlation of ranks = Spearman correlation
        mean_x = sum(rank_x) / n
        mean_y = sum(rank_y) / n

        num = sum((rank_x[i] - mean_x) * (rank_y[i] - mean_y) for i in range(n))
        den_x = math.sqrt(sum((rx - mean_x) ** 2 for rx in rank_x))
        den_y = math.sqrt(sum((ry - mean_y) ** 2 for ry in rank_y))

        if den_x * den_y < 1e-12:
            return 0.0

        return round(num / (den_x * den_y), 4)

    def record_period_ic(self, factor_name: str, ic_value: float, date_str: Optional[str] = None) -> None:
        """Record an IC observation for a specific period."""
        if factor_name not in self._history:
            self._history[factor_name] = []
        d_str = date_str or datetime.now().strftime("%Y-%m-%d")
        self._history[factor_name].append({"date": d_str, "ic": round(ic_value, 4)})

    def get_decay_report(self, factor_name: str) -> Dict[str, Any]:
        """
        Generate statistical validity and decay diagnosis for a factor.
        """
        history = self._history.get(factor_name, [])
        if not history:
            return {
                "factor_name": factor_name,
                "status": DecayStatus.HEALTHY.value,
                "observations": 0,
                "mean_ic": 0.0,
                "ic_std": 0.0,
                "ic_ir": 0.0,
                "win_rate_pct": 0.0,
                "alert": "No history recorded",
            }

        recent = history[-self.lookback_periods :]
        ics = [item["ic"] for item in recent]
        n = len(ics)

        mean_ic = sum(ics) / n
        if n >= 2:
            var_ic = sum((x - mean_ic) ** 2 for x in ics) / (n - 1)
            std_ic = math.sqrt(var_ic)
        else:
            std_ic = 0.0

        ic_ir = (mean_ic / std_ic) if std_ic > 1e-6 else 0.0
        win_rate = (sum(1 for x in ics if x > 0) / n) * 100.0

        # Recent 5 periods trend
        recent_5 = ics[-5:] if n >= 5 else ics
        mean_recent_5 = sum(recent_5) / len(recent_5)

        # Decay Diagnosis
        if mean_recent_5 <= -0.02 and mean_ic <= 0.0:
            status = DecayStatus.DECAY_CRITICAL
            alert = "Critical alpha decay: negative IC persistence. Factor predictive power inverted."
        elif mean_recent_5 < mean_ic * 0.5 or win_rate < 40.0:
            status = DecayStatus.DECAY_WARNING
            alert = "Decay warning: recent IC degraded over 50% from historical rolling baseline."
        else:
            status = DecayStatus.HEALTHY
            alert = "Healthy: factor predictive edge active."

        return {
            "factor_name": factor_name,
            "status": status.value,
            "observations": n,
            "latest_ic": ics[-1],
            "mean_ic": round(mean_ic, 4),
            "recent_5_ic": round(mean_recent_5, 4),
            "ic_std": round(std_ic, 4),
            "ic_ir": round(ic_ir, 3),
            "win_rate_pct": round(win_rate, 1),
            "alert": alert,
        }


# ==============================================================================
# 2. 市场机制自适应调度器 (RegimeAdaptiveDispatcher)
# ==============================================================================
class RegimeAdaptiveDispatcher(BaseAlgorithm):
    """
    Market Regime-Aware Intelligent Dispatcher.

    Dynamically binds macro market state with:
    - Multi-factor synthesis weights (FactorSynthesizer)
    - Primary strategy execution routes
    - Portfolio target exposure caps & risk stop parameters
    """

    def execute(self, *args: Any, **kwargs: Any) -> RegimeDispatchPlan:
        """Execute dispatching based on input regime or assessor output."""
        target = args[0] if args else kwargs.get("regime_or_assessor_output", "DEFAULT")
        return self.dispatch(target)

    @classmethod
    def dispatch(
        cls,
        regime_or_assessor_output: Union[str, Dict[str, Any]] = "DEFAULT",
    ) -> RegimeDispatchPlan:
        """
        Generate a comprehensive dispatch plan based on current market state.
        """
        regime = "DEFAULT"
        health_score = 50.0

        if isinstance(regime_or_assessor_output, str):
            clean = regime_or_assessor_output.upper().strip()
            if clean in ("BULL", "BEAR", "OSCILLATION", "DEFAULT"):
                regime = clean
            elif "多" in clean:
                regime = "BULL"
            elif "空" in clean:
                regime = "BEAR"
            else:
                regime = "OSCILLATION"
            health_score = 80.0 if regime == "BULL" else 25.0 if regime == "BEAR" else 55.0

        elif isinstance(regime_or_assessor_output, dict):
            # Parse output from MarketAssessor
            score = float(regime_or_assessor_output.get("total_score", regime_or_assessor_output.get("score", 50.0)))
            health_score = score
            state_str = str(regime_or_assessor_output.get("state", ""))
            if score >= 70.0 or "多头" in state_str:
                regime = "BULL"
            elif score <= 35.0 or "空头" in state_str:
                regime = "BEAR"
            else:
                regime = "OSCILLATION"

        # Lookup factor weights from FactorSynthesizer
        factor_weights = FactorSynthesizer.REGIME_WEIGHTS.get(
            regime, FactorSynthesizer.DEFAULT_WEIGHTS
        ).copy()

        # Regime customized dispatching rules
        if regime == "BULL":
            primary_strategies = ["volatility_breakout", "multi_dim", "combo_scorer"]
            max_portfolio_weight = 0.85
            stop_loss_pct = 7.0
            action_advice = "主升进攻模式：提高动量突破与放量共振权重，放宽仓位上限至85%，持股顺势而为。"
        elif regime == "OSCILLATION":
            primary_strategies = ["mean_reversion", "grid_trading", "combo_scorer"]
            max_portfolio_weight = 0.50
            stop_loss_pct = 5.0
            action_advice = "震荡轮动模式：强化均值回归与网格高抛低吸，总仓位控制在50%中位线，严控追高。"
        elif regime == "BEAR":
            primary_strategies = ["trapped_position", "risk_position_manager"]
            max_portfolio_weight = 0.20
            stop_loss_pct = 3.5
            action_advice = "防御避险模式：压降总仓位至20%以下或空仓，以超卖反弹和解套自救为主，启动严格风控熔断。"
        else:
            primary_strategies = ["multi_dim", "combo_scorer"]
            max_portfolio_weight = 0.60
            stop_loss_pct = 6.0
            action_advice = "基准平衡模式：采用标准多因子中性配置与稳健仓位。"

        return RegimeDispatchPlan(
            regime=regime,
            health_score=health_score,
            factor_weights=factor_weights,
            primary_strategies=primary_strategies,
            max_portfolio_weight=max_portfolio_weight,
            stop_loss_pct=stop_loss_pct,
            action_advice=action_advice,
        )


# ==============================================================================
# 3. 算法生命周期状态流转与退市管理器 (AlgorithmLifecycleManager)
# ==============================================================================
class AlgorithmLifecycleManager:
    """
    Algorithm Lifecycle Governance & Retirement Breaker.

    Manages stage transitions (RESEARCH -> BACKTESTED -> STAGING -> PRODUCTION -> DEPRECATED -> RETIRED)
    and enforces automatic performance circuit-breaking in AlgoRegistry.
    """
    _audit_trail: List[Dict[str, Any]] = []

    @classmethod
    def get_audit_trail(cls, algo_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve historical lifecycle transition audit logs."""
        if algo_name:
            clean = algo_name.lower().strip()
            return [x for x in cls._audit_trail if x["algo_name"] == clean]
        return list(cls._audit_trail)

    @classmethod
    def transition_stage(
        cls,
        algo_name: str,
        target_stage: Union[AlgorithmLifecycleStage, str],
        reason: str = "",
        operator: str = "governance_system",
    ) -> AlgorithmMetadata:
        """
        Execute an audited lifecycle stage transition for a registered algorithm.
        """
        clean_name = algo_name.lower().strip()
        meta = AlgoRegistry.get_metadata(clean_name)
        if not meta:
            raise KeyError(f"Algorithm '{algo_name}' not registered in AlgoRegistry.")

        new_stage = AlgorithmLifecycleStage(target_stage) if isinstance(target_stage, str) else target_stage
        old_stage = meta.stage

        # Update metadata state in-place
        meta.stage = new_stage

        event = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "algo_name": meta.name,
            "old_stage": old_stage.value,
            "new_stage": new_stage.value,
            "reason": reason or "Normal lifecycle progression",
            "operator": operator,
        }
        cls._audit_trail.append(event)
        logger.info(f"ALCM Transition: {meta.name} [{old_stage.value} -> {new_stage.value}] - {reason}")
        return meta

    @classmethod
    def evaluate_retirement_breaker(
        cls,
        algo_name: str,
        max_drawdown_pct: float,
        baseline_drawdown_pct: float,
        consecutive_losses: int = 0,
        ic_value: Optional[float] = None,
        auto_demote: bool = True,
    ) -> Tuple[bool, str]:
        """
        Check if an active production algorithm should be circuit-broken and demoted to DEPRECATED.

        Triggers:
        1. Max drawdown exceeds 1.5x of baseline backtest max drawdown.
        2. Consecutive losses >= 5.
        3. Rolling IC inverted and persistently negative (IC <= -0.05).
        """
        clean_name = algo_name.lower().strip()
        meta = AlgoRegistry.get_metadata(clean_name)
        if not meta:
            raise KeyError(f"Algorithm '{algo_name}' is not registered.")

        triggers = []
        if baseline_drawdown_pct > 0 and max_drawdown_pct >= baseline_drawdown_pct * 1.5:
            triggers.append(
                f"Drawdown breach: current MaxDD {max_drawdown_pct:.1f}% exceeded 1.5x baseline ({baseline_drawdown_pct:.1f}%)"
            )

        if consecutive_losses >= 5:
            triggers.append(f"Consecutive loss breaker: {consecutive_losses} loss trades in a row.")

        if ic_value is not None and ic_value <= -0.05:
            triggers.append(f"Alpha inversion breaker: IC value {ic_value:.3f} severely negative.")

        should_demote = len(triggers) > 0
        reason_summary = " | ".join(triggers) if triggers else "Operating within normal variance."

        if should_demote and auto_demote and meta.stage == AlgorithmLifecycleStage.PRODUCTION:
            cls.transition_stage(
                algo_name=clean_name,
                target_stage=AlgorithmLifecycleStage.DEPRECATED,
                reason=f"Circuit-breaker triggered: {reason_summary}",
            )

        return should_demote, reason_summary
