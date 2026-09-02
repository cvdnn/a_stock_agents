"""
波动率突破策略 — BOLL带宽收窄后放量突破入场

核心逻辑:
1. 波动率收缩识别: BOLL带宽(bandwidth)处于近60日最低20%分位
2. 放量突破确认: 当日成交量 > 5日均量 * 1.5, 且收盘价突破BOLL上轨
3. 入场: 收缩+放量突破 → 买入
4. 止盈: 价格触及BOLL上轨 + 2*ATR 或 RSI>75
5. 止损: 跌破BOLL中轨 或 跌回收缩区间下沿

纯Python标准库实现，不依赖pandas/numpy。
K线格式: [[date, open, close, high, low, volume], ...]
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from technical_indicators import boll, atr, rsi, calc_all, ma
from data_bridge import DataBridge


class VolatilityBreakoutStrategy:
    """波动率突破策略

    核心逻辑:
    1. 波动率收缩识别: BOLL带宽(bandwidth)处于近squeeze_lookback日最低squeeze_percentile分位
    2. 放量突破确认: 当日成交量 > 5日均量 * volume_ratio_threshold, 且收盘价突破BOLL上轨
    3. 入场: 收缩+放量突破 → 买入
    4. 止盈: 价格触及BOLL上轨 + 2*ATR 或 RSI>rsi_overbought
    5. 止损: 跌破BOLL中轨 或 跌回收缩区间下沿

    参数:
    - boll_period: 20
    - boll_k: 2.0
    - squeeze_lookback: 60 (收缩判断回看天数)
    - squeeze_percentile: 20 (最低20%分位判定收缩)
    - volume_ratio_threshold: 1.5 (放量倍数)
    - atr_period: 14
    - rsi_overbought: 75
    """

    def __init__(self, boll_period: int = 20, boll_k: float = 2.0,
                 squeeze_lookback: int = 60, squeeze_percentile: float = 20,
                 volume_ratio_threshold: float = 1.5, atr_period: int = 14,
                 rsi_overbought: float = 75):
        self.boll_period = boll_period
        self.boll_k = boll_k
        self.squeeze_lookback = squeeze_lookback
        self.squeeze_percentile = squeeze_percentile
        self.volume_ratio_threshold = volume_ratio_threshold
        self.atr_period = atr_period
        self.rsi_overbought = rsi_overbought

    # ═══════════════════════════════════════════════════
    #  内部辅助 — 直接使用 technical_indicators 的函数
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _safe_get(lst, idx, default=0.0):
        """安全获取列表指定索引的值"""
        if 0 <= idx < len(lst):
            return lst[idx]
        return default

    def _compute_indicators(self, klines):
        """预计算全部指标序列，供后续方法复用
        Returns: {"boll": dict, "atr": list, "rsi": list}
        """
        closes = [float(k[2]) for k in klines]
        return {
            "boll": boll(closes, self.boll_period, self.boll_k),
            "atr": atr(klines, self.atr_period),
            "rsi": rsi(closes, 14),
        }

    @staticmethod
    def _volume_avg(klines, idx, period=5):
        """计算idx前period日均量(不含当日)"""
        if idx < 1:
            return 0.0
        start = max(0, idx - period)
        vols = [float(klines[i][5]) for i in range(start, idx)]
        if not vols:
            return 0.0
        return sum(vols) / len(vols)

    # ═══════════════════════════════════════════════════
    #  公开方法
    # ═══════════════════════════════════════════════════

    def detect_squeeze(self, klines: List[List], idx: int,
                       indicators: Optional[Dict] = None) -> Dict[str, Any]:
        """检测波动率收缩

        判断: 当前BOLL带宽在近squeeze_lookback日中处于最低squeeze_percentile分位
        Returns: {"is_squeezed": bool, "current_bandwidth": float, "percentile": float, "median_bandwidth": float}
        """
        if indicators is None:
            indicators = self._compute_indicators(klines)
        bw_list = indicators["boll"]["bandwidth"]

        n = len(bw_list)
        # BOLL需要boll_period根K线才有第一个值
        # bandwidth前(boll_period-1)个为0，需要跳过
        valid_start = self.boll_period - 1  # 第一个有效带宽索引

        if idx < 0 or idx >= n:
            return {"is_squeezed": False, "current_bandwidth": 0.0,
                    "percentile": 50.0, "median_bandwidth": 0.0}

        current_bw = bw_list[idx]
        if current_bw == 0:
            # 可能是前面的填充值，用前一个有效值
            for j in range(idx, valid_start - 1, -1):
                if bw_list[j] != 0:
                    current_bw = bw_list[j]
                    break
            if current_bw == 0:
                return {"is_squeezed": False, "current_bandwidth": 0.0,
                        "percentile": 50.0, "median_bandwidth": 0.0}

        # 收集回看窗口内的有效带宽值
        lookback_start = max(valid_start, idx - self.squeeze_lookback + 1)
        window = [bw_list[i] for i in range(lookback_start, idx + 1) if bw_list[i] != 0]

        if len(window) < 2:
            return {"is_squeezed": False, "current_bandwidth": round(current_bw, 4),
                    "percentile": 50.0, "median_bandwidth": 0.0}

        # 百分位计算: rank / total * 100
        # rank = 窗口中 <= current_bw 的数量
        rank = sum(1 for w in window if w <= current_bw)
        total = len(window)
        percentile = (rank / total) * 100.0

        # 中位数
        sorted_window = sorted(window)
        mid_idx = len(sorted_window) // 2
        median_bw = sorted_window[mid_idx] if len(sorted_window) % 2 == 1 else \
            (sorted_window[mid_idx - 1] + sorted_window[mid_idx]) / 2

        is_squeezed = percentile <= self.squeeze_percentile

        return {
            "is_squeezed": is_squeezed,
            "current_bandwidth": round(current_bw, 4),
            "percentile": round(percentile, 2),
            "median_bandwidth": round(median_bw, 4),
        }

    def detect_breakout(self, klines: List[List], idx: int,
                       indicators: Optional[Dict] = None) -> Dict[str, Any]:
        """检测放量突破

        条件:
        1. 当日成交量 > 5日均量 * volume_ratio_threshold
        2. 收盘价 > BOLL上轨
        3. 前一日处于收缩状态(可选, 非必须)
        Returns: {"is_breakout": bool, "volume_ratio": float, "above_upper": bool, "reason": str}
        """
        if idx < 1 or idx >= len(klines):
            return {"is_breakout": False, "volume_ratio": 0.0,
                    "above_upper": False, "reason": "数据不足"}

        if indicators is None:
            indicators = self._compute_indicators(klines)
        upper = self._safe_get(indicators["boll"]["upper"], idx)

        close = float(klines[idx][2])
        vol = float(klines[idx][5])
        vol_avg = self._volume_avg(klines, idx, 5)

        if vol_avg <= 0:
            return {"is_breakout": False, "volume_ratio": 0.0,
                    "above_upper": False, "reason": "均量数据不足"}

        vol_ratio = vol / vol_avg
        above_upper = close > upper

        reasons = []
        if vol_ratio > self.volume_ratio_threshold:
            reasons.append(f"放量({vol_ratio:.2f}倍)")
        if above_upper:
            reasons.append("突破上轨")

        # 前一日收缩(可选)
        prev_squeeze = self.detect_squeeze(klines, idx - 1, indicators)
        if prev_squeeze["is_squeezed"]:
            reasons.append("前日处于收缩")

        is_breakout = (vol_ratio > self.volume_ratio_threshold) and above_upper

        if is_breakout:
            reason = "放量突破: " + ", ".join(reasons)
        elif above_upper and vol_ratio <= self.volume_ratio_threshold:
            reason = "突破上轨但量能不足"
        elif vol_ratio > self.volume_ratio_threshold and not above_upper:
            reason = "放量但未突破上轨"
        else:
            reason = "无突破信号"

        return {
            "is_breakout": is_breakout,
            "volume_ratio": round(vol_ratio, 4),
            "above_upper": above_upper,
            "reason": reason,
        }

    def generate_signal(self, klines: List[List], idx: int,
                        position: int = 0, entry_price: Optional[float] = None) -> Dict[str, Any]:
        """生成交易信号

        Args:
            klines: K线数据
            idx: 当前K线索引
            position: 当前持仓股数
            entry_price: 入场价

        Returns: {
            "action": "buy"/"sell"/"hold",
            "quantity": int (optional),
            "reason": str,
            "indicators": {"boll_width", "volume_ratio", "rsi", "atr", "squeeze_detected", "breakout_detected"},
            "stop_loss": float,
            "take_profit": float,
        }
        """
        if idx < 0 or idx >= len(klines):
            return {"action": "hold", "reason": "索引无效",
                    "indicators": {}, "stop_loss": 0.0, "take_profit": 0.0}

        indicators = self._compute_indicators(klines)
        boll_data = indicators["boll"]
        atr_list = indicators["atr"]
        rsi_list = indicators["rsi"]

        mid = self._safe_get(boll_data["mid"], idx)
        upper = self._safe_get(boll_data["upper"], idx)
        lower = self._safe_get(boll_data["lower"], idx)
        bw = self._safe_get(boll_data["bandwidth"], idx)
        atr_val = self._safe_get(atr_list, idx)
        rsi_val = self._safe_get(rsi_list, idx, 50.0)

        squeeze_info = self.detect_squeeze(klines, idx, indicators)
        breakout_info = self.detect_breakout(klines, idx, indicators)

        close = float(klines[idx][2])

        indicators = {
            "boll_width": round(bw, 4),
            "volume_ratio": breakout_info["volume_ratio"],
            "rsi": round(rsi_val, 2),
            "atr": round(atr_val, 4),
            "squeeze_detected": squeeze_info["is_squeezed"],
            "breakout_detected": breakout_info["is_breakout"],
        }

        # 止盈止损位
        take_profit = upper + 2 * atr_val if atr_val > 0 else upper * 1.05
        stop_loss = mid  # 跌破中轨止损
        # 如果有收缩区间下沿(最近squeeze期间最低价)，也作为止损参考
        # 在backtest中会更精确，这里用中轨

        # 有仓位 → 检查止盈止损
        if position > 0 and entry_price is not None:
            # 止盈: 价格触及 BOLL上轨 + 2*ATR 或 RSI > overbought
            if close >= take_profit:
                return {
                    "action": "sell", "quantity": position,
                    "reason": f"止盈: 价格触及上轨+2*ATR({take_profit:.2f})",
                    "indicators": indicators,
                    "stop_loss": round(stop_loss, 2),
                    "take_profit": round(take_profit, 2),
                }
            if rsi_val > self.rsi_overbought:
                return {
                    "action": "sell", "quantity": position,
                    "reason": f"止盈: RSI超买({rsi_val:.1f}>{self.rsi_overbought})",
                    "indicators": indicators,
                    "stop_loss": round(stop_loss, 2),
                    "take_profit": round(take_profit, 2),
                }
            # 止损: 跌破BOLL中轨
            if close < mid:
                return {
                    "action": "sell", "quantity": position,
                    "reason": f"止损: 跌破BOLL中轨({mid:.2f})",
                    "indicators": indicators,
                    "stop_loss": round(stop_loss, 2),
                    "take_profit": round(take_profit, 2),
                }
            # 止损: 跌回收缩区间下沿(用BOLL下轨近似)
            if close < lower:
                return {
                    "action": "sell", "quantity": position,
                    "reason": f"止损: 跌破BOLL下轨({lower:.2f})",
                    "indicators": indicators,
                    "stop_loss": round(stop_loss, 2),
                    "take_profit": round(take_profit, 2),
                }
            # 持有
            return {
                "action": "hold",
                "reason": "持有中, 等待止盈/止损",
                "indicators": indicators,
                "stop_loss": round(stop_loss, 2),
                "take_profit": round(take_profit, 2),
            }

        # 无仓位 → 检查入场
        if squeeze_info["is_squeezed"] and breakout_info["is_breakout"]:
            # 计算买入数量: 用close价格, 100股整数倍
            # 假设资金100万, 每次用1/3仓位
            budget = 1000000 / 3
            qty = int(budget // (close * 100)) * 100 if close > 0 else 0
            if qty <= 0:
                qty = 100  # 至少买1手

            return {
                "action": "buy", "quantity": qty,
                "reason": f"波动率收缩+放量突破入场 (带宽百分位:{squeeze_info['percentile']:.1f}%, "
                          f"放量:{breakout_info['volume_ratio']:.2f}倍)",
                "indicators": indicators,
                "stop_loss": round(stop_loss, 2),
                "take_profit": round(take_profit, 2),
            }

        # 无信号
        return {
            "action": "hold",
            "reason": f"无入场信号 (收缩:{squeeze_info['is_squeezed']}, "
                      f"突破:{breakout_info['is_breakout']})",
            "indicators": indicators,
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
        }

    def backtest_signals(self, klines: List[List], initial_cash: float = 1000000) -> Dict[str, Any]:
        """在历史K线上回测

        Returns: {
            "signals": [{"date", "action", "price", "reason", "indicators"}, ...],
            "squeeze_periods": int,
            "breakout_signals": int,
            "successful_breakouts": int,
            "win_rate": float,
            "avg_return_5d": float,
            "avg_return_10d": float,
            "max_return_5d": float,
            "max_loss_5d": float,
        }
        """
        n = len(klines)
        if n < self.boll_period + self.squeeze_lookback:
            return {
                "signals": [],
                "squeeze_periods": 0,
                "breakout_signals": 0,
                "successful_breakouts": 0,
                "win_rate": 0.0,
                "avg_return_5d": 0.0,
                "avg_return_10d": 0.0,
                "max_return_5d": 0.0,
                "max_loss_5d": 0.0,
            }

        signals = []
        squeeze_count = 0
        breakout_count = 0
        successful_breakouts = 0
        breakout_returns_5d = []
        breakout_returns_10d = []

        position = 0
        entry_price = None
        cash = initial_cash

        # 预计算指标一次，整个回测复用
        indicators = self._compute_indicators(klines)
        boll_data = indicators["boll"]
        atr_list = indicators["atr"]
        rsi_list = indicators["rsi"]

        start_idx = max(self.boll_period, self.atr_period) + 1

        for idx in range(start_idx, n):
            squeeze_info = self.detect_squeeze(klines, idx, indicators)
            breakout_info = self.detect_breakout(klines, idx, indicators)

            if squeeze_info["is_squeezed"]:
                squeeze_count += 1

            close = float(klines[idx][2])

            # --- 有仓位时检查止盈止损 ---
            if position > 0 and entry_price is not None:
                mid = self._safe_get(boll_data["mid"], idx)
                upper = self._safe_get(boll_data["upper"], idx)
                lower = self._safe_get(boll_data["lower"], idx)
                bw = self._safe_get(boll_data["bandwidth"], idx)
                atr_val = self._safe_get(atr_list, idx)
                rsi_val = self._safe_get(rsi_list, idx, 50.0)
                take_profit = upper + 2 * atr_val if atr_val > 0 else upper * 1.05

                sell_reason = None
                if close >= take_profit:
                    sell_reason = f"止盈: 触及上轨+2*ATR({take_profit:.2f})"
                elif rsi_val > self.rsi_overbought:
                    sell_reason = f"止盈: RSI超买({rsi_val:.1f})"
                elif close < mid:
                    sell_reason = f"止损: 跌破中轨({mid:.2f})"
                elif close < lower:
                    sell_reason = f"止损: 跌破下轨({lower:.2f})"

                if sell_reason:
                    signals.append({
                        "date": klines[idx][0],
                        "action": "sell",
                        "price": close,
                        "reason": sell_reason,
                        "indicators": {
                            "boll_width": round(bw, 4),
                            "volume_ratio": breakout_info["volume_ratio"],
                            "rsi": round(rsi_val, 2),
                            "atr": round(atr_val, 4),
                        },
                    })
                    position = 0
                    entry_price = None
                    continue

            # --- 无仓位时检查入场 ---
            if position == 0:
                if squeeze_info["is_squeezed"] and breakout_info["is_breakout"]:
                    breakout_count += 1
                    budget = initial_cash / 3
                    qty = int(budget // (close * 100)) * 100 if close > 0 else 0
                    if qty <= 0:
                        qty = 100

                    # 记录入场并评估5日/10日收益
                    signals.append({
                        "date": klines[idx][0],
                        "action": "buy",
                        "price": close,
                        "reason": f"收缩+放量突破 (带宽百分位:{squeeze_info['percentile']:.1f}%, "
                                  f"放量:{breakout_info['volume_ratio']:.2f}倍)",
                        "indicators": {
                            "boll_width": round(squeeze_info["current_bandwidth"], 4),
                            "volume_ratio": breakout_info["volume_ratio"],
                            "rsi": round(self._safe_get(rsi_list, idx, 50.0), 2),
                            "atr": round(self._safe_get(atr_list, idx), 4),
                        },
                    })

                    position = qty
                    entry_price = close

                    # 评估5日和10日后收益
                    ret_5d = None
                    ret_10d = None
                    if idx + 5 < n:
                        future_close = float(klines[idx + 5][2])
                        ret_5d = (future_close - close) / close * 100
                        breakout_returns_5d.append(ret_5d)
                        if ret_5d > 0:
                            successful_breakouts += 1
                    if idx + 10 < n:
                        future_close = float(klines[idx + 10][2])
                        ret_10d = (future_close - close) / close * 100
                        breakout_returns_10d.append(ret_10d)

        # 统计
        win_rate = 0.0
        avg_ret_5d = 0.0
        avg_ret_10d = 0.0
        max_ret_5d = 0.0
        max_loss_5d = 0.0

        if breakout_returns_5d:
            wins = sum(1 for r in breakout_returns_5d if r > 0)
            win_rate = wins / len(breakout_returns_5d) * 100
            avg_ret_5d = sum(breakout_returns_5d) / len(breakout_returns_5d)
            max_ret_5d = max(breakout_returns_5d)
            max_loss_5d = min(breakout_returns_5d)

        if breakout_returns_10d:
            avg_ret_10d = sum(breakout_returns_10d) / len(breakout_returns_10d)

        return {
            "signals": signals,
            "squeeze_periods": squeeze_count,
            "breakout_signals": breakout_count,
            "successful_breakouts": successful_breakouts,
            "win_rate": round(win_rate, 2),
            "avg_return_5d": round(avg_ret_5d, 2),
            "avg_return_10d": round(avg_ret_10d, 2),
            "max_return_5d": round(max_ret_5d, 2),
            "max_loss_5d": round(max_loss_5d, 2),
        }

    def score_breakout_opportunity(self, klines: List[List], latest: Dict) -> Dict[str, Any]:
        """评估当前波动率突破机会 (0-100)

        综合: 收缩程度 + 量能放大 + 价格位置 + 趋势方向
        Returns: {"score": int, "rating": "A"/"B"/"C"/"D", "reason": str, "squeeze": bool, "breakout": bool}
        """
        n = len(klines)
        if n < self.boll_period + 5:
            return {"score": 0, "rating": "D", "reason": "数据不足",
                    "squeeze": False, "breakout": False}

        idx = n - 1

        indicators = self._compute_indicators(klines)
        squeeze_info = self.detect_squeeze(klines, idx, indicators)
        breakout_info = self.detect_breakout(klines, idx, indicators)

        score = 0
        reasons = []

        # 1. 收缩程度 (0-30分)
        # 百分位越低 → 收缩越强 → 分越高
        percentile = squeeze_info["percentile"]
        if squeeze_info["is_squeezed"]:
            # 百分位0-20映射到20-30分
            squeeze_score = int(30 - (percentile / self.squeeze_percentile) * 10)
            score += max(squeeze_score, 20)
            reasons.append(f"收缩确认(百分位{percentile:.1f}%)")
        elif percentile < 40:
            score += 10
            reasons.append(f"轻度收缩(百分位{percentile:.1f}%)")
        else:
            score += 0

        # 2. 量能放大 (0-25分)
        vol_ratio = breakout_info["volume_ratio"]
        if vol_ratio > self.volume_ratio_threshold:
            # 1.5-3.0映射到15-25分
            vol_score = min(25, int(15 + (vol_ratio - self.volume_ratio_threshold) * 10))
            score += vol_score
            reasons.append(f"放量{vol_ratio:.2f}倍")
        elif vol_ratio > 1.2:
            score += 8
            reasons.append(f"温和放量{vol_ratio:.2f}倍")
        else:
            score += 0

        # 3. 价格位置 (0-25分)
        mid = self._safe_get(indicators["boll"]["mid"], idx)
        upper = self._safe_get(indicators["boll"]["upper"], idx)
        lower = self._safe_get(indicators["boll"]["lower"], idx)
        bw = self._safe_get(indicators["boll"]["bandwidth"], idx)
        close = float(klines[idx][2])

        if close > upper:
            score += 20
            reasons.append("突破上轨")
        elif close > mid and upper > 0:
            # 在中轨和上轨之间, 接近上轨加分
            position_pct = (close - mid) / (upper - mid) if (upper - mid) != 0 else 0
            price_score = int(5 + position_pct * 15)
            score += max(price_score, 5)
            reasons.append(f"中上轨区间({position_pct*100:.0f}%)")
        elif close > lower:
            score += 3
            reasons.append("中下轨区间")
        else:
            score += 0

        # 4. 趋势方向 (0-20分)
        closes = [float(k[2]) for k in klines]
        if len(closes) >= 20:
            ma5_vals = ma(closes, 5)
            ma20_vals = ma(closes, 20)
            ma5_last = ma5_vals[-1] if ma5_vals else 0
            ma20_last = ma20_vals[-1] if ma20_vals else 0

            if ma5_last > ma20_last and ma20_last > 0:
                score += 20
                reasons.append("多头排列(MA5>MA20)")
            elif ma5_last > ma20_last * 0.98 and ma20_last > 0:
                score += 10
                reasons.append("均线粘合趋多")
            else:
                score += 0
                reasons.append("空头或均线压制")

        # 限制0-100
        score = max(0, min(100, score))

        # 评级
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
            "squeeze": squeeze_info["is_squeezed"],
            "breakout": breakout_info["is_breakout"],
        }


# ═══════════════════════════════════════════════════
#  CLI入口
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="波动率突破策略")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    klines = DataBridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}))
        exit(1)

    strategy = VolatilityBreakoutStrategy()
    bt = strategy.backtest_signals(klines)
    tech = calc_all(klines)
    score = strategy.score_breakout_opportunity(klines, tech["latest"])

    output = {"code": args.code, "backtest": bt, "opportunity_score": score}
    print(json.dumps(output, ensure_ascii=False, indent=2))
