"""
aStocks 多因子选股评分模块

在 combo_scorer 的 100 分评分基础上，增加截面因子排序和 Z-score 合成:
  动量因子(25%) + 价值因子(15%) + 质量因子(10%) + 波动率因子(10%) + combo评分(40%)

纯 Python 标准库实现，不依赖 pandas/numpy。
K线数据格式: [[date, open, close, high, low, volume], ...]
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple


class MultiFactorScorer:
    """多因子选股评分器"""

    def __init__(self):
        pass

    # ═══════════════════════════════════════════════════
    #  动量因子
    # ═══════════════════════════════════════════════════

    @staticmethod
    def momentum_factor(klines: List[List], period: int = 20) -> Tuple[float, float]:
        """动量因子: 过去 period 日收益率%

        Returns: (factor_value, rank_score)
            factor_value = (close[-1] - close[-period]) / close[-period] * 100
            rank_score: 0-100
        """
        closes = [float(k[2]) for k in klines]
        if len(closes) < period + 1:
            return 0.0, 50.0

        ret = (closes[-1] - closes[-period]) / closes[-period] * 100

        # 绝对评分: 收益率映射到 0-100
        if ret >= 20:
            score = 100.0
        elif ret >= 10:
            score = 80.0 + (ret - 10) * 2  # 10-20 → 80-100
        elif ret >= 5:
            score = 65.0 + (ret - 5) * 3  # 5-10 → 65-80
        elif ret >= 0:
            score = 50.0 + ret * 3  # 0-5 → 50-65
        elif ret >= -5:
            score = 35.0 + (ret + 5) * 3  # -5-0 → 35-50
        elif ret >= -10:
            score = 20.0 + (ret + 10) * 3  # -10-(-5) → 20-35
        elif ret >= -20:
            score = max(0.0, 20.0 + (ret + 10) * 2)  # -20-(-10) → 0-20
        else:
            score = 0.0

        return round(ret, 2), round(score, 2)

    @staticmethod
    def momentum_factor_60d(klines: List[List]) -> Tuple[float, float]:
        """60日动量因子"""
        return MultiFactorScorer.momentum_factor(klines, 60)

    # ═══════════════════════════════════════════════════
    #  价值因子
    # ═══════════════════════════════════════════════════

    @staticmethod
    def value_factor(pe_value: Optional[float], pb_value: Optional[float] = None) -> float:
        """价值因子: PE/PB 分位评分 (0-100)"""
        if pe_value is None or pe_value <= 0:
            score = 40.0  # 无PE数据，给中性偏低分
        elif pe_value < 15:
            score = 100.0
        elif pe_value < 30:
            score = 80.0
        elif pe_value < 60:
            score = 50.0
        elif pe_value < 100:
            score = 20.0
        else:
            score = 0.0

        # PB 加成
        if pb_value is not None:
            if pb_value > 0:
                if pb_value < 1:
                    score = min(100.0, score + 20)
                elif pb_value < 3:
                    score = min(100.0, score + 10)
                elif pb_value > 5:
                    score = max(0.0, score - 10)

        return round(score, 2)

    # ═══════════════════════════════════════════════════
    #  质量因子
    # ═══════════════════════════════════════════════════

    @staticmethod
    def quality_factor(klines: List[List], pe_value: Optional[float] = None) -> float:
        """质量因子: 基于波动率和趋势稳定性反推 (0-100)"""
        closes = [float(k[2]) for k in klines]
        if len(closes) < 20:
            return 50.0

        # 趋势稳定性: 上涨日占比
        up_days = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1])
        up_ratio = up_days / (len(closes) - 1)

        # 波动率: ATR(14)/close * 100
        try:
            from technical_indicators import atr
            atr_vals = atr(klines, 14)
            atr_latest = atr_vals[-1] if atr_vals and len(atr_vals) > 0 else 0
            vol = (atr_latest / closes[-1] * 100) if closes[-1] > 0 else 10
        except Exception:
            vol = 10.0

        # 波动率评分: 越低越好
        if vol < 2:
            vol_score = 100.0
        elif vol < 4:
            vol_score = 80.0
        elif vol < 6:
            vol_score = 50.0
        elif vol < 8:
            vol_score = 20.0
        else:
            vol_score = 0.0

        # 趋势稳定性评分
        if 0.5 <= up_ratio <= 0.65:
            trend_score = 100.0  # 温和上涨
        elif 0.4 <= up_ratio <= 0.7:
            trend_score = 70.0
        elif 0.3 <= up_ratio <= 0.8:
            trend_score = 40.0
        else:
            trend_score = 20.0

        quality = vol_score * 0.6 + trend_score * 0.4

        # PE 合理加分
        if pe_value and 15 <= pe_value <= 30:
            quality = min(100.0, quality + 5)

        return round(quality, 2)

    # ═══════════════════════════════════════════════════
    #  波动率因子
    # ═══════════════════════════════════════════════════

    @staticmethod
    def volatility_factor(klines: List[List]) -> float:
        """波动率因子: ATR(14)/close * 100 (0-100, 越低越好)"""
        closes = [float(k[2]) for k in klines]
        if len(closes) < 15 or closes[-1] <= 0:
            return 50.0

        try:
            from technical_indicators import atr
            atr_vals = atr(klines, 14)
            atr_latest = atr_vals[-1] if atr_vals and len(atr_vals) > 0 else 0
        except Exception:
            return 50.0

        vol = atr_latest / closes[-1] * 100

        if vol < 2:
            return 100.0
        elif vol < 4:
            return 80.0
        elif vol < 6:
            return 50.0
        elif vol < 8:
            return 20.0
        else:
            return 0.0

    # ═══════════════════════════════════════════════════
    #  标准化方法
    # ═══════════════════════════════════════════════════

    @staticmethod
    def z_score(values: List[float]) -> List[float]:
        """Z-score 标准化: (x - mean) / std"""
        if len(values) < 2:
            return [0.0] * len(values)
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = math.sqrt(variance)
        if std == 0:
            return [0.0] * len(values)
        return [(x - mean) / std for x in values]

    @staticmethod
    def rank_normalize(values: List[float]) -> List[float]:
        """排名归一化到 0-100"""
        n = len(values)
        if n == 0:
            return []
        if n == 1:
            return [50.0]

        # 计算每个值的排名(升序, 0-based)
        indexed = sorted(range(n), key=lambda i: values[i])
        result = [0.0] * n
        for rank, idx in enumerate(indexed):
            result[idx] = rank / (n - 1) * 100
        return result

    # ═══════════════════════════════════════════════════
    #  综合评分
    # ═══════════════════════════════════════════════════

    def score_multi_factor(self, klines: List[List], latest: Dict,
                           pe_value: Optional[float] = None,
                           pb_value: Optional[float] = None) -> Dict[str, Any]:
        """多因子综合评分

        因子权重:
        - combo_score (现有100分评分): 40%
        - 动量因子 (20日+60日均值): 25%
        - 价值因子 (PE/PB): 15%
        - 质量因子: 10%
        - 波动率因子: 10%
        """
        # combo 评分
        try:
            from combo_scorer import ComboScorer
            scorer = ComboScorer()
            combo_result = scorer.score_full(klines, latest)
            combo_raw = combo_result.get("total", 50)
        except Exception:
            combo_raw = 50

        # 动量因子
        mom_20_raw, mom_20_score = self.momentum_factor(klines, 20)
        mom_60_raw, mom_60_score = self.momentum_factor_60d(klines)
        momentum_score = (mom_20_score + mom_60_score) / 2

        # 价值因子
        value_raw = self.value_factor(pe_value, pb_value)

        # 质量因子
        quality_raw = self.quality_factor(klines, pe_value)

        # 波动率因子
        vol_raw = self.volatility_factor(klines)

        # 归一化(单只股票用绝对评分0-100)
        combo_norm = combo_raw  # 已是0-100
        momentum_norm = momentum_score
        value_norm = value_raw
        quality_norm = quality_raw
        volatility_norm = vol_raw

        # 权重
        w_combo = 0.40
        w_momentum = 0.25
        w_value = 0.15
        w_quality = 0.10
        w_volatility = 0.10

        composite = (combo_norm * w_combo + momentum_norm * w_momentum +
                     value_norm * w_value + quality_norm * w_quality +
                     volatility_norm * w_volatility)

        # 评级
        if composite >= 80:
            rating, rating_text = "A", "多因子优秀 ⭐⭐⭐⭐"
        elif composite >= 65:
            rating, rating_text = "B", "多因子良好 ⭐⭐⭐"
        elif composite >= 50:
            rating, rating_text = "C", "多因子中性 ⭐⭐"
        else:
            rating, rating_text = "D", "多因子偏弱 ⭐"

        # 亮点与风险提示
        highlights = []
        warnings = []

        if combo_norm >= 70:
            highlights.append(f"技术面评分优秀({combo_norm:.0f}分)")
        if momentum_norm >= 70:
            highlights.append(f"动量强劲(20日{mom_20_raw:+.1f}%, 60日{mom_60_raw:+.1f}%)")
        if value_norm >= 80:
            highlights.append(f"估值偏低(PE={pe_value}, PB={pb_value})")
        if quality_norm >= 70:
            highlights.append("波动率低、趋势稳定")
        if volatility_norm >= 80:
            highlights.append("低波动率，适合稳健持有")

        if combo_norm < 40:
            warnings.append(f"技术面评分偏低({combo_norm:.0f}分)")
        if momentum_norm < 30:
            warnings.append(f"动量不足(20日{mom_20_raw:+.1f}%)")
        if value_norm < 30:
            warnings.append(f"估值偏高(PE={pe_value})")
        if volatility_norm < 20:
            warnings.append("高波动率，风险较大")
        if quality_norm < 30:
            warnings.append("趋势不稳定")

        return {
            "factors": {
                "combo_score": {"raw": round(combo_raw, 2), "normalized": round(combo_norm, 2), "weight": w_combo},
                "momentum_20d": {"raw": mom_20_raw, "normalized": round(mom_20_score, 2)},
                "momentum_60d": {"raw": mom_60_raw, "normalized": round(mom_60_score, 2)},
                "momentum": {"normalized": round(momentum_norm, 2), "weight": w_momentum},
                "value": {"raw": round(value_raw, 2), "normalized": round(value_norm, 2), "weight": w_value},
                "quality": {"raw": round(quality_raw, 2), "normalized": round(quality_norm, 2), "weight": w_quality},
                "volatility": {"raw": round(vol_raw, 2), "normalized": round(volatility_norm, 2), "weight": w_volatility},
            },
            "composite_score": round(composite, 2),
            "rating": rating,
            "rating_text": rating_text,
            "factor_highlights": highlights,
            "factor_warnings": warnings,
        }

    def _compute_factors(self, klines, latest, pe_value=None, pb_value=None):
        """预计算单只股票的全部因子原始值（供截面排序复用）
        Returns: {
            "combo_score": float,
            "momentum_20d": {"raw": float, "score": float},
            "momentum_60d": {"raw": float, "score": float},
            "value": float,
            "quality": float,
            "volatility": float,
        }
        """
        # combo 评分
        try:
            from combo_scorer import ComboScorer
            scorer = ComboScorer()
            combo_result = scorer.score_full(klines, latest)
            combo_raw = combo_result.get("total", 50)
        except Exception:
            combo_raw = 50

        mom_20_raw, mom_20_score = self.momentum_factor(klines, 20)
        mom_60_raw, mom_60_score = self.momentum_factor_60d(klines)
        value_raw = self.value_factor(pe_value, pb_value)
        quality_raw = self.quality_factor(klines, pe_value)
        vol_raw = self.volatility_factor(klines)

        return {
            "combo_score": combo_raw,
            "momentum_20d": {"raw": mom_20_raw, "score": mom_20_score},
            "momentum_60d": {"raw": mom_60_raw, "score": mom_60_score},
            "value": value_raw,
            "quality": quality_raw,
            "volatility": vol_raw,
        }

    def screen_stocks(self, stock_data_list: List[Dict], top_n: int = 10) -> Dict[str, Any]:
        """截面选股: 对多只股票做多因子排序

        优化版: 分两阶段执行
          阶段1: 对每只股票预计算因子原始值（combo_score+技术指标各算1次）
          阶段2: 对因子值做截面排名归一化 → 加权 → 排序
        """
        # 阶段1: 预计算各股因子
        stock_factors = []
        for stock in stock_data_list:
            factors = self._compute_factors(
                stock["klines"], stock.get("latest", {}),
                stock.get("pe"), stock.get("pb")
            )
            stock_factors.append({"code": stock.get("code", ""), "factors": factors})

        # 阶段2: 截面排名归一化 + 加权合成
        w_combo = 0.40
        w_momentum = 0.25
        w_value = 0.15
        w_quality = 0.10
        w_volatility = 0.10

        # 收集各因子值列表用于截面排名
        combo_vals = [sf["factors"]["combo_score"] for sf in stock_factors]
        mom20_vals = [sf["factors"]["momentum_20d"]["score"] for sf in stock_factors]
        mom60_vals = [sf["factors"]["momentum_60d"]["score"] for sf in stock_factors]
        value_vals = [sf["factors"]["value"] for sf in stock_factors]
        quality_vals = [sf["factors"]["quality"] for sf in stock_factors]
        vol_vals = [sf["factors"]["volatility"] for sf in stock_factors]

        # 截面排名归一化（多只股票时用排名，单只时用绝对评分）
        if len(stock_factors) > 1:
            combo_norm = self.rank_normalize(combo_vals)
            mom20_norm = self.rank_normalize(mom20_vals)
            mom60_norm = self.rank_normalize(mom60_vals)
            value_norm = self.rank_normalize(value_vals)
            quality_norm = self.rank_normalize(quality_vals)
            vol_norm = self.rank_normalize(vol_vals)
        else:
            combo_norm = combo_vals
            mom20_norm = mom20_vals
            mom60_norm = mom60_vals
            value_norm = value_vals
            quality_norm = quality_vals
            vol_norm = vol_vals

        results = []
        for i, sf in enumerate(stock_factors):
            momentum_norm = (mom20_norm[i] + mom60_norm[i]) / 2
            composite = (combo_norm[i] * w_combo + momentum_norm * w_momentum +
                         value_norm[i] * w_value + quality_norm[i] * w_quality +
                         vol_norm[i] * w_volatility)

            if composite >= 80:
                rating, rating_text = "A", "多因子优秀 ⭐⭐⭐⭐"
            elif composite >= 65:
                rating, rating_text = "B", "多因子良好 ⭐⭐⭐"
            elif composite >= 50:
                rating, rating_text = "C", "多因子中性 ⭐⭐"
            else:
                rating, rating_text = "D", "多因子偏弱 ⭐"

            f = sf["factors"]
            results.append({
                "code": sf["code"],
                "composite_score": round(composite, 2),
                "rating": rating,
                "rating_text": rating_text,
                "factors": {
                    "combo_score": {"raw": round(f["combo_score"], 2), "normalized": round(combo_norm[i], 2), "weight": w_combo},
                    "momentum_20d": {"raw": f["momentum_20d"]["raw"], "normalized": round(mom20_norm[i], 2)},
                    "momentum_60d": {"raw": f["momentum_60d"]["raw"], "normalized": round(mom60_norm[i], 2)},
                    "momentum": {"normalized": round(momentum_norm, 2), "weight": w_momentum},
                    "value": {"raw": round(f["value"], 2), "normalized": round(value_norm[i], 2), "weight": w_value},
                    "quality": {"raw": round(f["quality"], 2), "normalized": round(quality_norm[i], 2), "weight": w_quality},
                    "volatility": {"raw": round(f["volatility"], 2), "normalized": round(vol_norm[i], 2), "weight": w_volatility},
                },
            })

        # 截面排名
        if len(results) > 1:
            composite_scores = [r["composite_score"] for r in results]
            ranks = self.rank_normalize(composite_scores)
            for i, r in enumerate(results):
                r["cross_section_rank"] = round(ranks[i], 2)

        results.sort(key=lambda x: x["composite_score"], reverse=True)

        return {
            "ranked": results[:top_n],
            "total": len(results),
            "selected": min(top_n, len(results)),
        }


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="多因子选股评分")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--pe", type=float, default=None)
    parser.add_argument("--pb", type=float, default=None)
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    from data_bridge import DataBridge
    from technical_indicators import calc_all

    klines = DataBridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线数据"}))
        exit(1)

    tech = calc_all(klines)
    latest = tech["latest"]

    # 如果未指定PE, 尝试从行情获取
    pe = args.pe
    if pe is None:
        try:
            quote = DataBridge().get_realtime_quote(args.code)
            if quote:
                pe = quote.get("pe")
                if pe and pe > 0:
                    pe = float(pe)
                else:
                    pe = None
        except Exception:
            pass

    scorer = MultiFactorScorer()
    result = scorer.score_multi_factor(klines, latest, pe, args.pb)

    print(json.dumps(result, ensure_ascii=False, indent=2))
