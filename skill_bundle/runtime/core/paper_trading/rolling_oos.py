# -*- coding: utf-8 -*-
"""
Rolling Out-of-Sample (Rolling OOS) Validator & Triple Overfitting Detection Engine.
生产级滚动样本外检验器与过拟合三重警报系统 (SPEC-SKILL-002 S2-03).

核心标准:
  - 样本内 (In-Sample, IS) vs 样本外 (Out-of-Sample, OOS) 分割对比
  - 收益衰减率 (Decay Rate) 与夏普衰减率精算
  - 过拟合三重刚性警报:
      1. Sharpe > 3.5 (样本内夏普比率超常偏高)
      2. WinRate > 75.0% (样本内胜率超常偏高)
      3. IS-to-OOS 收益衰减 > 50.0% (样本外收益腰斩或转负)
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple


class RollingOOSValidator:
    """滚动样本外 (Rolling OOS) 检验器"""

    SHARPE_THRESHOLD: float = 3.5
    WIN_RATE_THRESHOLD: float = 75.0
    DECAY_THRESHOLD_PCT: float = 50.0

    @classmethod
    def split_samples(
        cls,
        klines: List[Any],
        oos_ratio: float = 0.3,
    ) -> Tuple[List[Any], List[Any]]:
        """按指定比例将 K 线分割为样本内 (IS) 与样本外 (OOS)。"""
        if not klines:
            return [], []
        oos_ratio = max(0.1, min(0.9, oos_ratio))
        split_idx = int(len(klines) * (1.0 - oos_ratio))
        return klines[:split_idx], klines[split_idx:]

    @classmethod
    def calculate_decay(
        cls,
        is_val: float,
        oos_val: float,
    ) -> float:
        """
        计算从样本内到样本外的衰减百分比。
        若 IS 为正而 OOS 转负或大幅下滑，衰减率 > 50% 甚至 > 100%。
        """
        if is_val <= 0:
            return 0.0 if oos_val >= is_val else 100.0
        decay = (is_val - oos_val) / is_val * 100.0
        return round(decay, 2)

    @classmethod
    def evaluate_overfitting(
        cls,
        in_sample_metrics: Dict[str, Any],
        out_sample_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        对样本内与样本外指标进行过拟合三重警报判定。

        三重警报判据:
          1. 样本内夏普 > 3.5
          2. 样本内胜率 > 75%
          3. IS 到 OOS 收益衰减 > 50%
        """
        is_sharpe = float(in_sample_metrics.get("sharpe_ratio", 0.0) or 0.0)
        oos_sharpe = float(out_sample_metrics.get("sharpe_ratio", 0.0) or 0.0)

        is_win_rate = float(in_sample_metrics.get("win_rate", in_sample_metrics.get("win_rate_pct", 0.0)) or 0.0)
        oos_win_rate = float(out_sample_metrics.get("win_rate", out_sample_metrics.get("win_rate_pct", 0.0)) or 0.0)

        is_annual = float(in_sample_metrics.get("annual_return", in_sample_metrics.get("annualized_cagr_pct", 0.0)) or 0.0)
        oos_annual = float(out_sample_metrics.get("annual_return", out_sample_metrics.get("annualized_cagr_pct", 0.0)) or 0.0)

        is_mdd = float(in_sample_metrics.get("max_drawdown", in_sample_metrics.get("max_drawdown_pct", 0.0)) or 0.0)
        oos_mdd = float(out_sample_metrics.get("max_drawdown", out_sample_metrics.get("max_drawdown_pct", 0.0)) or 0.0)

        return_decay_pct = cls.calculate_decay(is_annual, oos_annual)
        sharpe_decay_pct = cls.calculate_decay(is_sharpe, oos_sharpe)

        alert_sharpe = is_sharpe > cls.SHARPE_THRESHOLD
        alert_win_rate = is_win_rate > cls.WIN_RATE_THRESHOLD
        alert_decay = return_decay_pct > cls.DECAY_THRESHOLD_PCT

        overfitting_suspected = bool(alert_sharpe or alert_win_rate or alert_decay)

        warnings: List[str] = []
        if alert_sharpe:
            warnings.append(
                f"触发过拟合警报①[极值夏普]: 样本内夏普比率异常 ({is_sharpe:.2f} > {cls.SHARPE_THRESHOLD})"
            )
        if alert_win_rate:
            warnings.append(
                f"触发过拟合警报②[极值胜率]: 样本内胜率异常 ({is_win_rate:.1f}% > {cls.WIN_RATE_THRESHOLD:.1f}%)"
            )
        if alert_decay:
            warnings.append(
                f"触发过拟合警报③[严重衰减]: 收益衰减严重 ({return_decay_pct:.1f}% > {cls.DECAY_THRESHOLD_PCT:.1f}%)"
            )

        if overfitting_suspected:
            summary = f"疑似过拟合！触发 {len(warnings)} 项警报: " + "；".join(warnings)
        else:
            summary = (
                f"通过过拟合三重检验 (夏普<={cls.SHARPE_THRESHOLD}, "
                f"胜率<={cls.WIN_RATE_THRESHOLD}%, 收益衰减<={cls.DECAY_THRESHOLD_PCT}%)"
            )

        return {
            "in_sample_sharpe": round(is_sharpe, 2),
            "out_sample_sharpe": round(oos_sharpe, 2),
            "in_sample_win_rate": round(is_win_rate, 2),
            "out_sample_win_rate": round(oos_win_rate, 2),
            "in_sample_annual_return": round(is_annual, 2),
            "out_sample_annual_return": round(oos_annual, 2),
            "in_sample_max_drawdown": round(is_mdd, 2),
            "out_sample_max_drawdown": round(oos_mdd, 2),
            "return_decay_pct": return_decay_pct,
            "sharpe_decay_pct": sharpe_decay_pct,
            "overfitting_suspected": overfitting_suspected,
            "triple_alerts": {
                "sharpe_gt_3_5": alert_sharpe,
                "win_rate_gt_75": alert_win_rate,
                "decay_gt_50": alert_decay,
            },
            "warnings": warnings,
            "summary": summary,
            "warning": summary,  # 兼容既有字段名
        }

    @classmethod
    def run_oos_backtest(
        cls,
        engine: Any,
        klines: List[Any],
        strategy_func: Callable[[Any, Any, Any], Any],
        oos_ratio: float = 0.3,
    ) -> Dict[str, Any]:
        """
        执行样本内外回测并输出完整的过拟合检验分析报告。
        """
        in_sample, out_sample = cls.split_samples(klines, oos_ratio=oos_ratio)
        if not in_sample or not out_sample:
            return {
                "error": "K线数量过少，无法执行有效的样本内外分割",
                "in_sample": {},
                "out_sample": {},
                "overfitting_check": {
                    "overfitting_suspected": False,
                    "warning": "K线不足无法检验",
                },
            }

        in_res = engine.run_strategy(in_sample, strategy_func)
        out_res = engine.run_strategy(out_sample, strategy_func)

        in_metrics = in_res.get("metrics", {})
        out_metrics = out_res.get("metrics", {})

        overfitting_check = cls.evaluate_overfitting(in_metrics, out_metrics)

        return {
            "status": "success",
            "split_ratio": round(1.0 - oos_ratio, 2),
            "oos_ratio": round(oos_ratio, 2),
            "in_sample_bars": len(in_sample),
            "out_sample_bars": len(out_sample),
            "in_sample": in_metrics,
            "out_sample": out_metrics,
            "decay": {
                "return_decay_pct": overfitting_check["return_decay_pct"],
                "sharpe_decay_pct": overfitting_check["sharpe_decay_pct"],
            },
            "overfitting_check": overfitting_check,
            "triple_alerts": overfitting_check["triple_alerts"],
        }
