"""
A-Share Quant Engine - Risk & Position Manager (风控、止盈止损与仓位管理引擎)
功能:
1. 目标波动率组合管理 (Volatility Targeting)
2. 风险平价与分数凯利单标的头寸计算 (Position Sizing with 100-share Board Lot Alignment)
3. A股 T+1 状态机 (当日买入冻结，次日解冻可用)
4. 动态 ATR 移动止损 + 保本止损锁定 (Breakeven Lock)
5. 阶梯分批止盈状态机 (+5% 减1/3, +10% 减1/3, 尾仓跟踪)
6. 组合级全局分级熔断防护
"""

import math
from typing import Dict, List, Any, Optional, Tuple

from core.config import get_market_config


class PositionSizer:
    """仓位管理与资金分配器"""

    @staticmethod
    def calculate_portfolio_target_weight(market_volatility_annual: float, target_vol: float = 15.0) -> float:
        """根据目标波动率计算组合总仓位系数 (0.0 ~ 1.0)
        target_vol: 年化目标波动率 (默认 15.0%)
        """
        if market_volatility_annual <= 0:
            return 0.80  # 默认基准仓位 80%
        
        raw_weight = target_vol / market_volatility_annual
        # 限制在 [0.20, 0.95]
        return round(max(0.20, min(0.95, raw_weight)), 3)

    @staticmethod
    def calculate_stock_allocation(
        symbol: str,
        price: float,
        atr: float,
        total_equity: float,
        portfolio_target_weight: float = 0.80,
        max_stocks: int = 5,
        win_rate: float = 0.55,
        profit_loss_ratio: float = 1.8
    ) -> Dict[str, Any]:
        """计算单只股票的目标持仓金额与买入股数 (向下取整到 100 股整数手)"""
        if price <= 0 or total_equity <= 0:
            return {"shares": 0, "target_amount": 0.0, "weight": 0.0}

        # 1. 1/3 分数凯利公式: f* = (p*b - q)/b * 0.333
        p = win_rate
        q = 1.0 - p
        b = profit_loss_ratio
        kelly_f = ((p * b - q) / b) * 0.333 if b > 0 else 0.10
        kelly_f = max(0.05, min(0.30, kelly_f))

        # 2. 板块硬上限约束
        # 688/300 属于 20cm 板块，单股上限 8%；主板单股上限 15%
        is_high_vol_board = symbol.startswith(("30", "68"))
        board_cap = 0.08 if is_high_vol_board else 0.15

        # 3. ATR 风险平价权重修正 (波动率越低，权重略高；波动率越高，权重压降)
        norm_atr = (atr / price) if price > 0 else 0.03
        norm_atr = max(0.015, min(0.08, norm_atr))
        vol_scalar = 0.03 / norm_atr  # 假设基准日 ATR 为 3%

        # 4. 综合目标权重
        base_slot_weight = portfolio_target_weight / max_stocks
        target_weight = min(board_cap, base_slot_weight * vol_scalar * (kelly_f / 0.15))
        target_weight = max(0.03, min(board_cap, target_weight))

        # 5. 计算目标买入股数 (必须是 100 股整数倍)
        target_amount = total_equity * target_weight
        raw_shares = int(target_amount / price)
        # 向下取整到 100 股
        shares = (raw_shares // 100) * 100

        actual_amount = shares * price
        actual_weight = round(actual_amount / total_equity, 4)

        return {
            "symbol": symbol,
            "shares": shares,
            "target_amount": round(target_amount, 2),
            "actual_amount": round(actual_amount, 2),
            "weight": actual_weight,
            "board_cap": board_cap
        }


class AccountPortfolio:
    """A股账户持仓与 T+1 状态机"""

    def __init__(self, initial_cash: float = 1000000.0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.peak_equity = initial_cash
        # positions: {symbol: PositionData}
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_history: List[Dict[str, Any]] = []

    def get_total_equity(self, current_prices: Dict[str, float]) -> float:
        """获取当前账户总动态权益"""
        pos_value = 0.0
        for sym, pos in self.positions.items():
            p = current_prices.get(sym, pos["avg_cost"])
            pos_value += pos["shares"] * p
        total = self.cash + pos_value
        if total > self.peak_equity:
            self.peak_equity = total
        return total

    def get_current_drawdown(self, current_prices: Dict[str, float]) -> float:
        """计算相对于历史峰值的回撤幅度 %"""
        total = self.get_total_equity(current_prices)
        if self.peak_equity <= 0:
            return 0.0
        dd = (self.peak_equity - total) / self.peak_equity * 100.0
        return round(max(0.0, dd), 2)

    def buy(self, symbol: str, shares: int, price: float, date: str, atr: float) -> bool:
        """买入开仓/加仓 (当日买入冻结，T+1 才能卖出)"""
        if shares <= 0 or price <= 0:
            return False
        
        m_cfg = get_market_config()
        comm_rate = m_cfg.get("commission_rate", 0.00025)
        min_comm = m_cfg.get("min_commission", 5.0)

        cost = shares * price
        commission = max(min_comm, cost * comm_rate)  # 佣金
        total_cost = cost + commission

        if self.cash < total_cost:
            # 资金不足
            return False

        self.cash -= total_cost

        if symbol not in self.positions:
            self.positions[symbol] = {
                "symbol": symbol,
                "shares": shares,
                "available_shares": 0,  # T+1: 当日可用为 0
                "avg_cost": price,
                "highest_price": price,
                "initial_atr": atr,
                "buy_date": date,
                "take_profit_stage": 0  # 0: 未止盈, 1: 减仓1/3, 2: 减仓2/3
            }
        else:
            pos = self.positions[symbol]
            new_shares = pos["shares"] + shares
            pos["avg_cost"] = (pos["shares"] * pos["avg_cost"] + cost) / new_shares
            pos["shares"] = new_shares
            # 新买入的部分当日不能卖出

        self.trade_history.append({
            "action": "BUY",
            "symbol": symbol,
            "shares": shares,
            "price": price,
            "date": date,
            "cost": total_cost
        })
        return True

    def sell(self, symbol: str, shares: int, price: float, date: str, reason: str = "EXIT") -> bool:
        """卖出平仓/减仓 (严格校验 T+1 可用持仓)"""
        if symbol not in self.positions:
            return False
        
        pos = self.positions[symbol]
        if pos["available_shares"] < shares or shares <= 0:
            return False

        m_cfg = get_market_config()
        comm_rate = m_cfg.get("commission_rate", 0.00025)
        min_comm = m_cfg.get("min_commission", 5.0)
        tax_rate = m_cfg.get("tax_rate_sell", 0.0005)

        gross_amount = shares * price
        stamp_tax = gross_amount * tax_rate  # A股印花税 卖方单边万分之5
        commission = max(min_comm, gross_amount * comm_rate)  # 佣金
        net_proceeds = gross_amount - stamp_tax - commission

        self.cash += net_proceeds
        pos["shares"] -= shares
        pos["available_shares"] -= shares

        realized_pnl = (price - pos["avg_cost"]) * shares - stamp_tax - commission
        pnl_pct = (price - pos["avg_cost"]) / pos["avg_cost"] * 100.0

        self.trade_history.append({
            "action": "SELL",
            "symbol": symbol,
            "shares": shares,
            "price": price,
            "date": date,
            "pnl": round(realized_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "reason": reason
        })

        if pos["shares"] <= 0:
            del self.positions[symbol]

        return True

    def end_of_day_settlement(self):
        """日终结算：解冻今日买入的持仓 (T+1 状态流转)"""
        for sym, pos in self.positions.items():
            pos["available_shares"] = pos["shares"]


class RiskEngine:
    """动态三级止损与阶梯止盈风控引擎"""

    # 参数定义
    HARD_STOP_LOSS_PCT = -6.0        # T2 硬止损线: -6.0%
    BREAKEVEN_TRIGGER_PCT = 5.0     # 保本止损触发线: +5.0%
    BREAKEVEN_BUFFER_PCT = 0.3      # 保本缓冲比例 (覆盖税费): +0.3%
    TAKE_PROFIT_STAGE1_PCT = 5.0    # 阶梯止盈一档: +5.0% (减 1/3)
    TAKE_PROFIT_STAGE2_PCT = 10.0   # 阶梯止盈二档: +10.0% (再减 1/3)
    ATR_TRAILING_MULTIPLIER = 2.0   # ATR 移动跟踪倍数

    @classmethod
    def evaluate_position_risk(
        cls,
        pos: Dict[str, Any],
        current_price: float,
        current_atr: float,
        date: str
    ) -> List[Dict[str, Any]]:
        """评估单个持仓的风控与止盈止损状态，返回触发的交易动作列表"""
        actions = []
        if pos["available_shares"] <= 0 or current_price <= 0:
            return actions

        avg_cost = pos["avg_cost"]
        highest_price = max(pos.get("highest_price", avg_cost), current_price)
        pos["highest_price"] = highest_price

        # 当前未实现收益率
        pnl_pct = (current_price - avg_cost) / avg_cost * 100.0
        # 从最高点回撤幅度
        dd_from_high_pct = (highest_price - current_price) / highest_price * 100.0

        stage = pos.get("take_profit_stage", 0)

        # -------------------------------------------------------------
        # 1. T2 硬止损: 亏损超过硬止损阈值 (-6%)
        # -------------------------------------------------------------
        if pnl_pct <= cls.HARD_STOP_LOSS_PCT:
            actions.append({
                "type": "STOP_LOSS",
                "shares": pos["available_shares"],
                "reason": f"T2_HARD_STOP ({pnl_pct:.2f}%)",
                "price": current_price
            })
            return actions

        # -------------------------------------------------------------
        # 2. 动态 ATR 移动止损 & 保本止损 (Breakeven Stop)
        # -------------------------------------------------------------
        # 动态止损线计算
        atr_val = current_atr if current_atr > 0 else pos.get("initial_atr", current_price * 0.03)
        trailing_stop_price = highest_price - cls.ATR_TRAILING_MULTIPLIER * atr_val

        # 若曾达到过保本触发线 (+5%)，止损价至少上移至成本线 + 0.3%
        if highest_price >= avg_cost * (1.0 + cls.BREAKEVEN_TRIGGER_PCT / 100.0):
            breakeven_price = avg_cost * (1.0 + cls.BREAKEVEN_BUFFER_PCT / 100.0)
            trailing_stop_price = max(trailing_stop_price, breakeven_price)

        if current_price < trailing_stop_price:
            actions.append({
                "type": "STOP_LOSS",
                "shares": pos["available_shares"],
                "reason": f"ATR_TRAILING_STOP (Hit {trailing_stop_price:.2f}, High {highest_price:.2f})",
                "price": current_price
            })
            return actions

        # -------------------------------------------------------------
        # 3. 阶梯分批止盈 (Laddered Take Profit)
        # -------------------------------------------------------------
        total_shares = pos["shares"]
        
        # 阶段 1: 首次达到 +5%，减仓 1/3
        if stage == 0 and pnl_pct >= cls.TAKE_PROFIT_STAGE1_PCT:
            sell_qty = (total_shares // 3 // 100) * 100
            if sell_qty > 0 and sell_qty <= pos["available_shares"]:
                pos["take_profit_stage"] = 1
                actions.append({
                    "type": "TAKE_PROFIT_1",
                    "shares": sell_qty,
                    "reason": f"LADDER_TP1 (+{pnl_pct:.2f}% Sell 1/3)",
                    "price": current_price
                })

        # 阶段 2: 达到 +10%，再减仓 1/3
        elif stage == 1 and pnl_pct >= cls.TAKE_PROFIT_STAGE2_PCT:
            sell_qty = (total_shares // 2 // 100) * 100  # 剩余的一半即为初始的1/3
            if sell_qty > 0 and sell_qty <= pos["available_shares"]:
                pos["take_profit_stage"] = 2
                actions.append({
                    "type": "TAKE_PROFIT_2",
                    "shares": sell_qty,
                    "reason": f"LADDER_TP2 (+{pnl_pct:.2f}% Sell 1/3)",
                    "price": current_price
                })

        return actions
