"""
aStocks 网格交易策略 — ATR 锚定布林带区间分档挂单

核心逻辑:
- 区间: BOLL下轨到上轨之间
- 间距: 1 ATR(14)
- 网格数: (上轨-下轨) / ATR, 向下取整, 最少4格最多8格
- 每格资金: 总资金 / 网格数
- 买入: 价格触及某网格线下沿 → 买入该格资金对应数量
- 卖出: 价格回升到上一格线 → 卖出该格持仓
- 止损: 价格跌破BOLL下轨 - 1 ATR → 全部清仓

纯 Python 标准库实现。
K线格式: [[date, open, close, high, low, volume], ...]
"""

import json
import math
from typing import Any, Dict, List, Optional


class GridTradingStrategy:
    """网格交易策略"""

    def __init__(self, atr_period: int = 14, boll_period: int = 20,
                 boll_k: float = 2.0, min_grids: int = 4, max_grids: int = 8,
                 stop_loss_atr: float = 1.0):
        self.atr_period = atr_period
        self.boll_period = boll_period
        self.boll_k = boll_k
        self.min_grids = min_grids
        self.max_grids = max_grids
        self.stop_loss_atr = stop_loss_atr

    def build_grid(self, klines: List[List], total_cash: float = 1000000) -> Dict[str, Any]:
        """构建网格"""
        try:
            from core.indicators.technical_indicators import boll, atr
        except ImportError:
            from technical_indicators import boll, atr

        closes = [float(k[2]) for k in klines]
        boll_data = boll(closes, self.boll_period, self.boll_k)
        atr_vals = atr(klines, self.atr_period)

        boll_lower = boll_data["lower"][-1] if boll_data["lower"] else 0
        boll_upper = boll_data["upper"][-1] if boll_data["upper"] else 0
        boll_mid = boll_data["mid"][-1] if boll_data["mid"] else 0
        atr_val = atr_vals[-1] if atr_vals else 0

        if atr_val <= 0 or boll_lower <= 0 or boll_upper <= 0:
            return {"error": "指标数据不足"}

        # 网格数
        range_val = boll_upper - boll_lower
        grid_count = int(range_val / atr_val)
        grid_count = max(self.min_grids, min(self.max_grids, grid_count))

        # 网格间距
        grid_spacing = range_val / grid_count

        # 每格资金
        cash_per_grid = total_cash / grid_count

        # 网格线
        grid_levels = []
        for i in range(grid_count + 1):
            price = boll_lower + i * grid_spacing
            qty = int(cash_per_grid / price / 100) * 100  # 100股整数倍
            grid_levels.append({
                "level": i,
                "price": round(price, 2),
                "action": "buy" if i < grid_count / 2 else "sell",
                "quantity": qty,
            })

        stop_loss_price = boll_lower - self.stop_loss_atr * atr_val

        return {
            "boll_lower": round(boll_lower, 2),
            "boll_upper": round(boll_upper, 2),
            "boll_mid": round(boll_mid, 2),
            "atr": round(atr_val, 4),
            "grid_spacing": round(grid_spacing, 2),
            "grid_count": grid_count,
            "grid_levels": grid_levels,
            "cash_per_grid": round(cash_per_grid, 2),
            "stop_loss_price": round(stop_loss_price, 2),
            "total_cash": total_cash,
        }

    def simulate(self, klines: List[List], initial_cash: float = 1000000) -> Dict[str, Any]:
        """在历史数据上模拟网格交易"""
        grid_info = self.build_grid(klines, initial_cash)
        if "error" in grid_info:
            return grid_info

        grid_levels = grid_info["grid_levels"]
        stop_loss_price = grid_info["stop_loss_price"]
        grid_spacing = grid_info["grid_spacing"]

        # 模拟交易 — 逐日动态追踪权益
        cash = initial_cash
        trades = []
        grid_holdings = {}  # {level: quantity}
        grid_fills = 0
        total_profit = 0
        daily_equity = []  # 每日权益快照 (cash + 持仓市值)
        start_idx = max(self.boll_period, self.atr_period)

        for i in range(start_idx, len(klines)):
            current_close = float(klines[i][2])
            current_date = klines[i][0]

            # 止损检查
            if current_close <= stop_loss_price and grid_holdings:
                for lvl, qty in list(grid_holdings.items()):
                    if qty > 0:
                        buy_price = grid_levels[lvl]["price"]
                        trades.append({
                            "date": current_date,
                            "action": "sell",
                            "price": round(current_close, 2),
                            "quantity": qty,
                            "grid_level": lvl,
                        })
                        pnl = (current_close - buy_price) * qty
                        total_profit += pnl
                        cash += qty * current_close  # 止损卖出回笼资金
                        grid_fills += 1
                grid_holdings = {}
            else:
                # 检查每个网格线
                for j, level in enumerate(grid_levels):
                    if j == 0:
                        continue
                    lower_price = grid_levels[j - 1]["price"]
                    upper_price = level["price"]

                    # 买入: 价格从上方触及下沿
                    if i > 0:
                        prev_close = float(klines[i - 1][2])
                        if prev_close > lower_price >= current_close or (abs(current_close - lower_price) < grid_spacing * 0.1):
                            qty = grid_levels[j - 1]["quantity"]
                            if qty > 0 and cash >= qty * current_close:
                                cash -= qty * current_close
                                grid_holdings[j - 1] = grid_holdings.get(j - 1, 0) + qty
                                trades.append({
                                    "date": current_date,
                                    "action": "buy",
                                    "price": round(current_close, 2),
                                    "quantity": qty,
                                    "grid_level": j - 1,
                                })
                                grid_fills += 1

                    # 卖出: 价格从下方触及上沿
                    if i > 0 and j - 1 in grid_holdings and grid_holdings[j - 1] > 0:
                        prev_close = float(klines[i - 1][2])
                        if prev_close < upper_price <= current_close or (abs(current_close - upper_price) < grid_spacing * 0.1):
                            qty = grid_holdings[j - 1]
                            buy_price = grid_levels[j - 1]["price"]
                            trades.append({
                                "date": current_date,
                                "action": "sell",
                                "price": round(current_close, 2),
                                "quantity": qty,
                                "grid_level": j - 1,
                            })
                            cash += qty * current_close
                            pnl = (current_close - buy_price) * qty
                            total_profit += pnl
                            grid_holdings[j - 1] = 0
                            grid_fills += 1

            # 日末盯市: cash + 所有持仓的当日市值
            holdings_value = sum(qty * current_close for qty in grid_holdings.values() if qty > 0)
            daily_equity.append(cash + holdings_value)

        # 计算最终净值
        remaining_value = 0
        for lvl, qty in grid_holdings.items():
            if qty > 0:
                remaining_value += qty * float(klines[-1][2])

        final_equity = cash + remaining_value
        total_return_pct = (final_equity - initial_cash) / initial_cash * 100

        # 最大回撤 — 基于逐日动态权益曲线
        max_dd = 0
        max_dd_duration = 0
        dd_start = 0
        if daily_equity:
            peak = daily_equity[0]
            peak_idx = 0
            for i, v in enumerate(daily_equity):
                if v > peak:
                    peak = v
                    peak_idx = i
                dd = (peak - v) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd
                    max_dd_duration = i - peak_idx

        avg_profit = total_profit / grid_fills if grid_fills > 0 else 0

        return {
            "grid_info": grid_info,
            "trades": trades[-20:],  # 最近20笔
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "max_drawdown_duration": max_dd_duration,
            "grid_fills": grid_fills,
            "avg_profit_per_grid": round(avg_profit, 2),
            "equity_curve_length": len(daily_equity),
        }

    def score_grid_suitability(self, klines: List[List]) -> Dict[str, Any]:
        """评估股票是否适合网格交易"""
        try:
            from core.indicators.technical_indicators import boll, atr, ma
        except ImportError:
            from technical_indicators import boll, atr, ma


        closes = [float(k[2]) for k in klines]
        boll_data = boll(closes, self.boll_period, self.boll_k)
        atr_vals = atr(klines, self.atr_period)

        current_close = closes[-1]
        atr_val = atr_vals[-1] if atr_vals else 0
        boll_width = boll_data["bandwidth"][-1] if boll_data["bandwidth"] else 0

        # 波动率
        vol = (atr_val / current_close * 100) if current_close > 0 else 0

        # MA60斜率(趋势性)
        ma60 = ma(closes, 60) if len(closes) >= 60 else closes
        ma60_slope = 0
        if len(ma60) > 2 and ma60[-1] > 0 and ma60[-2] > 0:
            ma60_slope = (ma60[-1] - ma60[-2]) / ma60[-2] * 100

        score = 0
        reasons = []

        # 波动率评分 (40分): 2-6%最佳
        if 2 <= vol <= 6:
            score += 40
            reasons.append(f"波动率{vol:.1f}%适合网格")
        elif 1 <= vol < 2:
            score += 25
            reasons.append(f"波动率{vol:.1f}%偏低")
        elif 6 < vol <= 8:
            score += 25
            reasons.append(f"波动率{vol:.1f}%偏高")
        else:
            score += 10
            reasons.append(f"波动率{vol:.1f}%不适合")

        # BOLL带宽评分 (30分): >5%最佳
        if boll_width > 8:
            score += 30
            reasons.append(f"BOLL带宽{boll_width:.1f}%充足")
        elif boll_width > 5:
            score += 25
            reasons.append(f"BOLL带宽{boll_width:.1f}%适中")
        elif boll_width > 3:
            score += 15
            reasons.append(f"BOLL带宽{boll_width:.1f}%偏窄")
        else:
            score += 5
            reasons.append(f"BOLL带宽{boll_width:.1f}%过窄")

        # 趋势性评分 (30分): MA60斜率<0.5%非强趋势
        if abs(ma60_slope) < 0.3:
            score += 30
            reasons.append("非强趋势，适合网格")
        elif abs(ma60_slope) < 0.5:
            score += 20
            reasons.append("弱趋势")
        elif abs(ma60_slope) < 1.0:
            score += 10
            reasons.append(f"有一定趋势(斜率{ma60_slope:.2f}%)")
        else:
            score += 5
            reasons.append(f"强趋势(斜率{ma60_slope:.2f}%)不适合网格")

        suitable = score >= 60
        if score >= 75:
            rating = "A"
        elif score >= 60:
            rating = "B"
        elif score >= 40:
            rating = "C"
        else:
            rating = "D"

        return {
            "score": score,
            "rating": rating,
            "suitable": suitable,
            "reason": "; ".join(reasons),
            "volatility_pct": round(vol, 2),
            "boll_bandwidth": round(boll_width, 2),
            "ma60_slope": round(ma60_slope, 2),
        }


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="网格交易策略")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--cash", type=float, default=1000000)
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    from data_bridge import DataBridge

    klines = DataBridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}))
        exit(1)

    grid = GridTradingStrategy()
    info = grid.build_grid(klines, args.cash)
    sim = grid.simulate(klines, args.cash)
    score = grid.score_grid_suitability(klines)

    output = {"code": args.code, "grid_info": info, "simulation": sim, "suitability": score}
    print(json.dumps(output, ensure_ascii=False, indent=2))
