"""
aStocks 均值回归策略 — RSI + BOLL 区间反转

核心逻辑:
- 买入: RSI<30 + 价格触及/跌破BOLL下轨 → 超卖反转
- 卖出: RSI>70 + 价格触及/突破BOLL上轨 → 超买
- 中性: 价格在BOLL中轨附近 → 持有/观望

纯 Python 标准库实现。
K线格式: [[date, open, close, high, low, volume], ...]
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple


class MeanReversionStrategy:
    """均值回归策略"""

    def __init__(self, rsi_oversold: float = 30, rsi_overbought: float = 70,
                 boll_period: int = 20, boll_k: float = 2.0,
                 stop_loss_pct: float = 0.05):
        """
        Args:
            rsi_oversold: RSI超卖阈值
            rsi_overbought: RSI超买阈值
            boll_period: 布林带周期
            boll_k: 布林带标准差倍数
            stop_loss_pct: 止损百分比
        """
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.boll_period = boll_period
        self.boll_k = boll_k
        self.stop_loss_pct = stop_loss_pct

    def generate_signal(self, klines: List[List], idx: int,
                        position: int, entry_price: Optional[float] = None) -> Dict[str, Any]:
        """生成交易信号"""
        if idx < self.boll_period:
            return {"action": "hold", "reason": "数据不足"}

        try:
            from core.indicators.technical_indicators import rsi, boll
        except ImportError:
            from technical_indicators import rsi, boll

        closes = [float(k[2]) for k in klines[:idx + 1]]
        rsi_vals = rsi(closes, 14)
        boll_data = boll(closes, self.boll_period, self.boll_k)

        current_rsi = rsi_vals[-1] if rsi_vals else 50
        boll_upper = boll_data["upper"][-1] if boll_data["upper"] else 0
        boll_mid = boll_data["mid"][-1] if boll_data["mid"] else 0
        boll_lower = boll_data["lower"][-1] if boll_data["lower"] else 0
        current_close = closes[-1]

        indicators = {
            "rsi": round(current_rsi, 2),
            "boll_upper": round(boll_upper, 2),
            "boll_mid": round(boll_mid, 2),
            "boll_lower": round(boll_lower, 2),
        }

        # 止损检查
        if entry_price and current_close < entry_price * (1 - self.stop_loss_pct):
            return {
                "action": "sell",
                "quantity": position,
                "reason": f"止损触发: 价格{current_close:.2f} < 入场价{entry_price:.2f}的{self.stop_loss_pct:.0%}止损线",
                "indicators": indicators,
            }

        # 买入信号: RSI超卖 + 价格在BOLL下轨附近或以下
        if current_rsi < self.rsi_oversold and current_close <= boll_lower * 1.01 and position == 0:
            return {
                "action": "buy",
                "reason": f"RSI={current_rsi:.1f}<{self.rsi_oversold} + 价格触及BOLL下轨{boll_lower:.2f}",
                "indicators": indicators,
            }

        # 卖出信号: RSI超买 + 价格在BOLL上轨附近或以上
        if current_rsi > self.rsi_overbought and current_close >= boll_upper * 0.99 and position > 0:
            return {
                "action": "sell",
                "quantity": position,
                "reason": f"RSI={current_rsi:.1f}>{self.rsi_overbought} + 价格触及BOLL上轨{boll_upper:.2f}",
                "indicators": indicators,
            }

        return {
            "action": "hold",
            "reason": f"RSI={current_rsi:.1f}, 价格{current_close:.2f} 在BOLL{boll_lower:.2f}~{boll_upper:.2f}区间内",
            "indicators": indicators,
        }

    def backtest_signals(self, klines: List[List],
                         initial_cash: float = 1000000) -> Dict[str, Any]:
        try:
            from core.indicators.technical_indicators import rsi, boll
        except ImportError:
            from technical_indicators import rsi, boll


        closes = [float(k[2]) for k in klines]
        rsi_vals = rsi(closes, 14)
        boll_data = boll(closes, self.boll_period, self.boll_k)

        signals = []
        buy_count = 0
        sell_count = 0
        returns_5d = []
        returns_10d = []

        start_idx = max(self.boll_period, 14)

        for i in range(start_idx, len(klines)):
            current_rsi = rsi_vals[i] if i < len(rsi_vals) else 50
            boll_upper = boll_data["upper"][i] if i < len(boll_data["upper"]) else 0
            boll_lower = boll_data["lower"][i] if i < len(boll_data["lower"]) else 0
            current_close = closes[i]
            current_date = klines[i][0]

            # 买入信号
            if current_rsi < self.rsi_oversold and boll_lower > 0 and current_close <= boll_lower * 1.01:
                signals.append({
                    "date": current_date,
                    "action": "buy",
                    "price": round(current_close, 2),
                    "reason": f"RSI={current_rsi:.1f}<{self.rsi_oversold}+BOLL下轨",
                    "indicators": {
                        "rsi": round(current_rsi, 2),
                        "boll_upper": round(boll_upper, 2),
                        "boll_lower": round(boll_lower, 2),
                    },
                })
                buy_count += 1

                # 计算5日和10日收益
                if i + 5 < len(closes):
                    ret_5d = (closes[i + 5] - current_close) / current_close * 100
                    returns_5d.append(ret_5d)
                if i + 10 < len(closes):
                    ret_10d = (closes[i + 10] - current_close) / current_close * 100
                    returns_10d.append(ret_10d)

            # 卖出信号
            elif current_rsi > self.rsi_overbought and boll_upper > 0 and current_close >= boll_upper * 0.99:
                signals.append({
                    "date": current_date,
                    "action": "sell",
                    "price": round(current_close, 2),
                    "reason": f"RSI={current_rsi:.1f}>{self.rsi_overbought}+BOLL上轨",
                    "indicators": {
                        "rsi": round(current_rsi, 2),
                        "boll_upper": round(boll_upper, 2),
                        "boll_lower": round(boll_lower, 2),
                    },
                })
                sell_count += 1

        win_rate = 0.0
        if returns_5d:
            wins = sum(1 for r in returns_5d if r > 0)
            win_rate = wins / len(returns_5d) * 100

        avg_5d = sum(returns_5d) / len(returns_5d) if returns_5d else 0
        avg_10d = sum(returns_10d) / len(returns_10d) if returns_10d else 0

        return {
            "signals": signals[-20:],  # 最近20个信号
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "win_rate": round(win_rate, 2),
            "avg_return_5d": round(avg_5d, 2),
            "avg_return_10d": round(avg_10d, 2),
        }

    def score_reversion(self, klines: List[List], latest: Dict) -> Dict[str, Any]:
        """均值回归评分 (0-100)

        综合 RSI 位置 + BOLL 位置 + 量价确认
        """
        try:
            from core.indicators.technical_indicators import rsi, boll
        except ImportError:
            from technical_indicators import rsi, boll


        closes = [float(k[2]) for k in klines]
        rsi_vals = rsi(closes, 14)
        boll_data = boll(closes, self.boll_period, self.boll_k)

        current_rsi = rsi_vals[-1] if rsi_vals else 50
        boll_upper = boll_data["upper"][-1] if boll_data["upper"] else 0
        boll_mid = boll_data["mid"][-1] if boll_data["mid"] else 0
        boll_lower = boll_data["lower"][-1] if boll_data["lower"] else 0
        current_close = closes[-1]

        score = 0
        reasons = []

        # RSI 评分 (40分)
        if current_rsi < 20:
            score += 40
            reasons.append(f"RSI={current_rsi:.1f}极度超卖")
        elif current_rsi < 30:
            score += 35
            reasons.append(f"RSI={current_rsi:.1f}超卖")
        elif current_rsi < 40:
            score += 25
            reasons.append(f"RSI={current_rsi:.1f}偏弱")
        elif current_rsi > 80:
            score += 5
            reasons.append(f"RSI={current_rsi:.1f}极度超买")
        elif current_rsi > 70:
            score += 10
            reasons.append(f"RSI={current_rsi:.1f}超买")
        else:
            score += 20
            reasons.append(f"RSI={current_rsi:.1f}中性")

        # BOLL 位置评分 (40分)
        if boll_lower > 0 and boll_upper > 0:
            boll_pos = (current_close - boll_lower) / (boll_upper - boll_lower) if (boll_upper - boll_lower) != 0 else 0.5
            if boll_pos < 0.1:
                score += 40
                reasons.append("价格在BOLL下轨以下")
            elif boll_pos < 0.3:
                score += 35
                reasons.append("价格接近BOLL下轨")
            elif boll_pos < 0.5:
                score += 25
                reasons.append("价格在BOLL下半区")
            elif boll_pos < 0.7:
                score += 20
                reasons.append("价格在BOLL上半区")
            elif boll_pos < 0.9:
                score += 10
                reasons.append("价格接近BOLL上轨")
            else:
                score += 5
                reasons.append("价格在BOLL上轨以上")

        # 量价确认 (20分)
        if len(klines) >= 6:
            vols = [float(k[5]) for k in klines if float(k[5]) > 0]
            if len(vols) >= 6:
                latest_vol = vols[-1]
                avg_vol = sum(vols[-6:-1]) / 5
                vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 1

                if current_rsi < 30 and vol_ratio < 0.8:
                    score += 20
                    reasons.append("缩量超卖，反转概率高")
                elif current_rsi < 40 and vol_ratio < 0.9:
                    score += 15
                    reasons.append("缩量偏弱")
                elif vol_ratio > 2.0 and current_rsi > 70:
                    score += 15
                    reasons.append("放量超买")
                else:
                    score += 10
                    reasons.append(f"量比{vol_ratio:.2f}正常")

        if score >= 75:
            rating = "A"
        elif score >= 55:
            rating = "B"
        elif score >= 35:
            rating = "C"
        else:
            rating = "D"

        return {
            "score": score,
            "rating": rating,
            "reason": "; ".join(reasons),
            "rsi": round(current_rsi, 2),
            "boll_pos": round((current_close - boll_lower) / (boll_upper - boll_lower) * 100, 2) if boll_upper > boll_lower else 50,
        }


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="均值回归策略")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    from data_bridge import DataBridge
    from technical_indicators import calc_all

    klines = DataBridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}))
        exit(1)

    strategy = MeanReversionStrategy()
    result = strategy.backtest_signals(klines)
    tech = calc_all(klines)
    score = strategy.score_reversion(klines, tech["latest"])

    output = {"code": args.code, "backtest": result, "reversion_score": score}
    print(json.dumps(output, ensure_ascii=False, indent=2))
