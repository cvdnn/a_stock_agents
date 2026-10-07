# -*- coding: utf-8 -*-
"""可回测的建仓与持股策略 `PositionPolicy`（E2 / SSOT §12.3 / §13.7）。

`PositionPolicy` 是**结构化、可解释、可回测**的持股方案，不得只输出自然语言"建议买入"：

- **建仓**：允许入场时间窗、触发条件、禁止追高条件、失效条件；
- **仓位**：风险预算（risk_budget）或波动率目标（vol_target），A股 100 股整手；
- **风控**：初始止损 `max(-5%, -2*ATR)`、ATR 移动止损、T+1 约束、最长持有交易日、
  三级风控阶梯及其**口径来源**（D-23 显式声明，未登记口径的新增模块即违规）；
- **退出**：分批止盈步长与模型失效退出。

铁律（§12.3 / 发布门禁 17）：

1. **缺账户规模或计划成交价时不生成伪精确股数与保本价**，只输出待补充字段；
2. 策略输出明确标识为**研究方案**，系统不存在自动实盘下单路径（`research_only=True`）。

本模块只做结构化装配与纯计算，不读取行情、不写盘、不下单。
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.selection_models.market_view import (
    Bar,
    annualized_volatility_pct,
    atr_value,
    breakeven_price,
    max_position_weight,
    market_config,
    stop_loss_levels,
)

#: 模型绑定的策略模板版本（D-15：统一风险模板库 + 模型绑定并保存模板版本）。
POLICY_TEMPLATE_VERSION = "position_policy/2024.1"

ENTRY_WINDOW_DEFAULT = "next_trade_day_09:30-10:00"

_DISCLAIMER = (
    "研究方案，非交易指令：本策略为可回测的参数化研究输出，"
    "系统不存在自动实盘下单路径；任何后续交易须由人工独立决策并自行承担风险。"
)


class PositionPolicyError(ValueError):
    code = "MODEL_CONFIG_INVALID"


def _round(value: Optional[float], digits: int = 6) -> Optional[float]:
    return None if value is None else round(float(value), digits)


def build_position_policy(
    *,
    code: str,
    name: Optional[str] = None,
    bars: Optional[Sequence[Bar]] = None,
    atr: Optional[float] = None,
    account_equity: Optional[float] = None,
    planned_entry_price: Optional[float] = None,
    risk_per_trade_pct: float = 1.0,
    target_vol_pct: Optional[float] = None,
    max_holding_trade_days: int = 10,
    take_profit_steps: Optional[Sequence[float]] = None,
    overrides: Optional[Mapping[str, Any]] = None,
    cfg: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """构造 `PositionPolicy`；缺失关键输入时只登记待补充字段，不伪造精度。"""
    override = dict(overrides or {})
    fee_cfg = dict(cfg or market_config())
    bar_list: List[Bar] = list(bars or [])

    entry_price = planned_entry_price if planned_entry_price and planned_entry_price > 0 else None
    equity = account_equity if account_equity and account_equity > 0 else None
    atr_used = atr if atr and atr > 0 else None
    if atr_used is None and bar_list:
        atr_used = atr_value(bar_list)

    missing: List[str] = []
    if equity is None:
        missing.append("account_equity")
    if entry_price is None:
        missing.append("planned_entry_price")
    if atr_used is None:
        missing.append("atr")

    max_weight = float(override.get("max_weight", max_position_weight(code)))
    risk_pct = float(override.get("risk_per_trade_pct", risk_per_trade_pct)) / 100.0

    # 初始止损：取 -5% 与 -2*ATR 中较紧者（价格较高者），口径来源显式登记（D-23）
    initial_stop_rule = "max(-5%, -2*ATR)"
    stop_price: Optional[float] = None
    if entry_price is not None:
        pct_stop = entry_price * 0.95
        atr_stop = entry_price - 2.0 * atr_used if atr_used else None
        stop_price = max([p for p in (pct_stop, atr_stop) if p is not None])

    shares: Optional[int] = None
    initial_weight: Optional[float] = None
    sizing_method = str(override.get("sizing_method", "risk_budget"))
    if equity is not None and entry_price is not None and stop_price is not None and entry_price > stop_price:
        per_share_risk = entry_price - stop_price
        risk_amount = equity * risk_pct
        raw_shares = risk_amount / per_share_risk
        shares = int(math.floor(raw_shares / 100.0) * 100)
        # 单股上限（D-20）与目标波动率上限（若提供）
        cap_weight = max_weight
        if target_vol_pct and bar_list:
            realized_vol = annualized_volatility_pct([bar.close for bar in bar_list])
            if realized_vol > 0:
                cap_weight = min(cap_weight, float(target_vol_pct) / realized_vol)
        cap_shares = int(math.floor(cap_weight * equity / entry_price / 100.0) * 100)
        shares = max(0, min(shares, cap_shares))
        initial_weight = _round(shares * entry_price / equity)
        if shares == 0:
            missing.append("position_size_below_one_lot")

    breakeven = breakeven_price(entry_price, shares, cfg=fee_cfg) if (entry_price and shares) else None

    steps = [float(s) for s in (take_profit_steps or (0.05, 0.10))]

    policy: Dict[str, Any] = {
        "code": str(code),
        "name": name,
        "template_version": POLICY_TEMPLATE_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "research_only": True,
        "entry": {
            "window": str(override.get("entry_window", ENTRY_WINDOW_DEFAULT)),
            "conditions": [
                "gap_pct <= 0.02",
                "price_above_vwap",
            ],
            "invalid_if": ["market_gate_failed", "limit_up_unbuyable"],
            "planned_entry_price": _round(entry_price),
        },
        "position": {
            "sizing_method": sizing_method,
            "risk_per_trade_pct": _round(risk_pct * 100.0, 4),
            "initial_weight": initial_weight,
            "max_weight": _round(max_weight * 100.0, 4),
            "round_lot": 100,
            "shares": shares,
            "account_equity": _round(equity, 2),
        },
        "risk": {
            "initial_stop": initial_stop_rule,
            "initial_stop_price": _round(stop_price),
            "trailing_stop": "ATR",
            "atr": _round(atr_used),
            "max_holding_trade_days": int(max_holding_trade_days),
            "t_plus_one": True,
            "stop_levels": stop_loss_levels(),
        },
        "exit": {
            "take_profit_steps": steps,
            "model_invalidation": True,
        },
        "breakeven_price": _round(breakeven, 2),
        "preconditions": [
            "仅在账户规模、计划成交价与个股 ATR 均可得时给出精确股数与保本价",
            "策略为研究方案，不构成投资建议，系统不存在自动下单路径",
        ],
        "missing_inputs": missing,
        "disclaimer": _DISCLAIMER,
    }
    return policy


__all__ = ["ENTRY_WINDOW_DEFAULT", "POLICY_TEMPLATE_VERSION", "PositionPolicyError", "build_position_policy"]