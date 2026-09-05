"""
A-Share Quant Engine - Price-Volume Factors (量价因子计算引擎)
纯 Python 标准库零依赖实现，提供高效的动量、反转、量价共振、波动率与筹码特征计算。
"""

import math
from typing import Dict, List, Any, Optional, Tuple


class PVFactors:
    """量价与技术指标 Alpha 因子计算引擎"""

    @staticmethod
    def _sma(values: List[float], period: int) -> List[float]:
        """简单移动平均 (SMA)"""
        if len(values) < period:
            return [sum(values) / len(values)] * len(values) if values else []
        res = []
        cur_sum = sum(values[:period])
        res.append(cur_sum / period)
        for i in range(period, len(values)):
            cur_sum += values[i] - values[i - period]
            res.append(cur_sum / period)
        # 前面补齐
        prefix = [res[0]] * (period - 1)
        return prefix + res

    @staticmethod
    def _ema(values: List[float], period: int) -> List[float]:
        """指数移动平均 (EMA)"""
        if not values:
            return []
        alpha = 2.0 / (period + 1)
        res = [values[0]]
        for v in values[1:]:
            res.append(alpha * v + (1 - alpha) * res[-1])
        return res

    @staticmethod
    def _std(values: List[float], period: int) -> List[float]:
        """滑动标准差"""
        if len(values) < period:
            return [0.0] * len(values)
        res = []
        for i in range(period, len(values) + 1):
            sub = values[i - period:i]
            m = sum(sub) / period
            variance = sum((x - m) ** 2 for x in sub) / max(1, period - 1)
            res.append(math.sqrt(variance))
        prefix = [res[0]] * (period - 1)
        return prefix + res

    @classmethod
    def calculate_atr(cls, klines: List[Dict[str, Any]], period: int = 14) -> Tuple[float, float]:
        """计算 ATR 真实波幅与 归一化 ATR (ATR / Close)"""
        if len(klines) < 2:
            return 0.0, 0.0
        
        tr_list = []
        for i in range(len(klines)):
            if i == 0:
                tr = klines[i]["high"] - klines[i]["low"]
            else:
                h = klines[i]["high"]
                l = klines[i]["low"]
                prev_c = klines[i - 1]["close"]
                tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)
        
        atr_series = cls._sma(tr_list, period)
        latest_atr = atr_series[-1] if atr_series else 0.0
        close = klines[-1]["close"]
        norm_atr = (latest_atr / close) if close > 0 else 0.0
        return round(latest_atr, 4), round(norm_atr, 4)

    @classmethod
    def calculate_rsi(cls, closes: List[float], period: int = 14) -> float:
        """计算 RSI"""
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff >= 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return round(rsi, 2)

    @classmethod
    def calculate_kdj(cls, klines: List[Dict[str, Any]], n: int = 9, m1: int = 3, m2: int = 3) -> Tuple[float, float, float]:
        """计算 KDJ 指标"""
        if len(klines) < n:
            return 50.0, 50.0, 50.0
        
        k, d = 50.0, 50.0
        for i in range(n - 1, len(klines)):
            window = klines[i - n + 1:i + 1]
            low_n = min(x["low"] for x in window)
            high_n = max(x["high"] for x in window)
            close = klines[i]["close"]
            
            if high_n == low_n:
                rsv = 50.0
            else:
                rsv = (close - low_n) / (high_n - low_n) * 100.0
            
            k = (2.0 / 3.0) * k + (1.0 / 3.0) * rsv
            d = (2.0 / 3.0) * d + (1.0 / 3.0) * k
        j = 3.0 * k - 2.0 * d
        return round(k, 2), round(d, 2), round(j, 2)

    @classmethod
    def calculate_boll(cls, closes: List[float], period: int = 20, num_std: float = 2.0) -> Tuple[float, float, float, float]:
        """计算布林带 (Mid, Upper, Lower, %b 相对分位, 带宽 Bandwidth)"""
        if len(closes) < period:
            c = closes[-1] if closes else 0.0
            return c, c, c, 0.5
        
        mid = sum(closes[-period:]) / period
        variance = sum((x - mid) ** 2 for x in closes[-period:]) / max(1, period - 1)
        std = math.sqrt(variance)
        upper = mid + num_std * std
        lower = mid - num_std * std
        c = closes[-1]
        
        pct_b = (c - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
        bandwidth = (upper - lower) / mid if mid > 0 else 0.0
        return round(mid, 2), round(upper, 2), round(lower, 2), round(pct_b, 4)

    @classmethod
    def calculate_macd(cls, closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """计算 MACD (DIF, DEA, MACD 柱)"""
        if len(closes) < slow:
            return 0.0, 0.0, 0.0
        ema_fast = cls._ema(closes, fast)
        ema_slow = cls._ema(closes, slow)
        dif = [f - s for f, s in zip(ema_fast, ema_slow)]
        dea = cls._ema(dif, signal)
        macd_bar = (dif[-1] - dea[-1]) * 2.0
        return round(dif[-1], 3), round(dea[-1], 3), round(macd_bar, 3)

    @classmethod
    def extract_factors(cls, klines: List[Dict[str, Any]]) -> Dict[str, float]:
        """提取单个标的的全面量价因子字典
        返回因子包括:
        - 动量/趋势: ret_5d, ret_20d, ret_60d, bias_5d, bias_20d, macd_hist
        - 反转/超买超卖: rsi_14, kdj_j, boll_pct_b
        - 量价突破/流动性: vol_surge_5_20, vwap_bias_5, pv_corr_20
        - 波动率: norm_atr, hist_vol_20
        - 筹码估计: profit_ratio
        """
        if not klines or len(klines) < 30:
            return {}

        closes = [float(k["close"]) for k in klines]
        volumes = [float(k["volume"]) for k in klines]
        amounts = [float(k.get("amount", float(k.get("volume", 0.0)) * float(k.get("close", 0.0)))) for k in klines]
        c = closes[-1]

        # 1. 动量因子 (Momentum Returns %)
        ret_5d = (c - closes[-6]) / closes[-6] * 100.0 if len(closes) >= 6 else 0.0
        ret_20d = (c - closes[-21]) / closes[-21] * 100.0 if len(closes) >= 21 else 0.0
        ret_60d = (c - closes[-61]) / closes[-61] * 100.0 if len(closes) >= 61 else 0.0

        # 2. 均线乖离率 (BIAS %)
        ma5 = sum(closes[-5:]) / 5.0
        ma20 = sum(closes[-20:]) / 20.0
        bias_5d = (c - ma5) / ma5 * 100.0
        bias_20d = (c - ma20) / ma20 * 100.0

        # 3. 技术指标 (MACD, RSI, KDJ, BOLL)
        dif, dea, macd_hist = cls.calculate_macd(closes)
        rsi_14 = cls.calculate_rsi(closes, 14)
        k, d, kdj_j = cls.calculate_kdj(klines, 9, 3, 3)
        mid, upper, lower, boll_pct_b = cls.calculate_boll(closes, 20)

        # 4. 量价共振与突破 (Volume Surge & VWAP)
        vol_5_avg = sum(volumes[-5:]) / 5.0
        vol_20_avg = sum(volumes[-20:]) / 20.0 if len(volumes) >= 20 else vol_5_avg
        vol_surge = (vol_5_avg / vol_20_avg) if vol_20_avg > 0 else 1.0

        # 5日 VWAP 偏离度
        amt_5_sum = sum(amounts[-5:])
        vol_5_sum = sum(volumes[-5:])
        vwap_5 = (amt_5_sum / (vol_5_sum * 100)) if vol_5_sum > 0 else c
        vwap_bias = (c - vwap_5) / vwap_5 * 100.0 if vwap_5 > 0 else 0.0

        # 5. 波动率指标 (ATR & 历史波动率)
        atr, norm_atr = cls.calculate_atr(klines, 14)
        
        # 20日历史年化波动率
        if len(closes) >= 21:
            log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 20, len(closes))]
            mean_ret = sum(log_rets) / len(log_rets)
            var_ret = sum((r - mean_ret) ** 2 for r in log_rets) / (len(log_rets) - 1)
            hist_vol_20 = math.sqrt(var_ret) * math.sqrt(250) * 100.0
        else:
            hist_vol_20 = norm_atr * math.sqrt(250) * 100.0

        # 6. 价量相关性 (20日 Close 与 Volume 相关系数)
        if len(closes) >= 20:
            c_sub = closes[-20:]
            v_sub = volumes[-20:]
            mc, mv = sum(c_sub) / 20.0, sum(v_sub) / 20.0
            cov = sum((c_sub[i] - mc) * (v_sub[i] - mv) for i in range(20))
            std_c = math.sqrt(sum((x - mc) ** 2 for x in c_sub))
            std_v = math.sqrt(sum((x - mv) ** 2 for x in v_sub))
            pv_corr_20 = cov / (std_c * std_v) if (std_c * std_v) > 0 else 0.0
        else:
            pv_corr_20 = 0.0

        # 7. 筹码获利盘与成本估计 (基于真实/估算换手率的成交量沉淀加权模型)
        avg_chip_cost = cls.calculate_chip_cost(klines, lookback=120)
        profit_ratio = round((c - avg_chip_cost) / avg_chip_cost * 100.0, 2) if avg_chip_cost > 0 else 0.0

        return {
            "ret_5d": round(ret_5d, 2),
            "ret_20d": round(ret_20d, 2),
            "ret_60d": round(ret_60d, 2),
            "bias_5d": round(bias_5d, 2),
            "bias_20d": round(bias_20d, 2),
            "macd_hist": round(macd_hist, 3),
            "rsi_14": round(rsi_14, 2),
            "kdj_j": round(kdj_j, 2),
            "boll_pct_b": round(boll_pct_b, 4),
            "vol_surge_5_20": round(vol_surge, 2),
            "vwap_bias_5": round(vwap_bias, 2),
            "pv_corr_20": round(pv_corr_20, 3),
            "norm_atr": round(norm_atr, 4),
            "hist_vol_20": round(hist_vol_20, 2),
            "profit_ratio": round(profit_ratio, 2)
        }

    @classmethod
    def calculate_chip_cost(cls, klines: List[Dict[str, Any]], lookback: int = 120) -> float:
        """基于换手率沉淀的动态筹码分布加权成本算法 (Volume-by-Price Turnover Decay)
        
        每一天新进入流通的筹码以典型价格进入，历史筹码按当期换手率比例 (1 - turnover) 沉淀衰减。
        """
        if not klines:
            return 0.0

        sub_klines = klines[-lookback:] if len(klines) > lookback else klines
        n = len(sub_klines)
        c = sub_klines[-1]["close"]
        if n == 1:
            return c

        volumes = [float(k.get("volume", 0.0)) for k in sub_klines]
        avg_vol = sum(volumes) / max(1, n)
        est_float_vol = avg_vol * 60.0  # 假设全流通平均周期约为60个交易日

        # 逐日计算典型价格 (Typical Price) 和换手率
        # Typical Price = (H + L + 2*C) / 4
        typical_prices = []
        turnovers = []
        for k in sub_klines:
            h = float(k.get("high", k.get("close", c)))
            l = float(k.get("low", k.get("close", c)))
            cl = float(k.get("close", c))
            tp = (h + l + 2.0 * cl) / 4.0
            typical_prices.append(tp)

            # 优先使用真实换手率，若无则基于估算流通量
            if "turnover" in k and k["turnover"] is not None and float(k["turnover"]) > 0:
                to = min(0.40, float(k["turnover"]) / 100.0)
            elif est_float_vol > 0:
                to = min(0.30, max(0.005, float(k.get("volume", 0.0)) / est_float_vol))
            else:
                to = 0.02
            turnovers.append(to)

        # 反向递归计算截至最新日各历史日筹码的有效存留权重
        # w_i = turnover_i * \prod_{j=i+1}^{n-1} (1 - turnover_j)
        weights = [0.0] * n
        retained = 1.0
        for i in range(n - 1, -1, -1):
            weights[i] = turnovers[i] * retained
            retained *= (1.0 - turnovers[i])
            if retained < 1e-4:
                break

        weight_sum = sum(weights)
        if weight_sum > 0:
            weighted_cost = sum(p * w for p, w in zip(typical_prices, weights)) / weight_sum
        else:
            weighted_cost = c

        return round(weighted_cost, 2)

