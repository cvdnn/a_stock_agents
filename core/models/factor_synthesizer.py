"""
A-Share Quant Engine - Factor Synthesizer (多因子合成与截面排序器)
功能:
1. 截面因子去极值 (MAD Winsorization)
2. 截面 Z-Score 标准化与方向修正 (Direction Alignment)
3. 多模态因子加权合成 (量价 Alpha 75% + 舆情情绪 25%)
4. 截面分位数排序 (Percentile Rank) 与 Top-K 选股
"""

import math
import statistics
from typing import Dict, List, Any, Optional, Tuple


class FactorSynthesizer:
    """截面多因子合成与排序引擎"""

    # 因子方向定义 (1: 越大越好, -1: 越小越好)
    FACTOR_DIRECTIONS = {
        "ret_5d": 1,
        "ret_20d": 1,
        "ret_60d": 1,
        "bias_5d": 1,
        "bias_20d": 1,
        "macd_hist": 1,
        "rsi_14": -1,         # 偏向超卖反弹
        "kdj_j": -1,          # 偏向低位金叉/超卖
        "boll_pct_b": -1,     # 偏向触及下轨反弹
        "vol_surge_5_20": 1,  # 放量突破
        "vwap_bias_5": 1,     # 站上短期均价
        "pv_corr_20": 1,      # 价涨量增共振
        "norm_atr": -1,       # 偏好低波动稳健标的
        "profit_ratio": 1,    # 筹码获利盘
        "sentiment_score": 1  # 积极正面舆情
    }

    # 默认合成权重配置 (总和 1.0)
    DEFAULT_WEIGHTS = {
        # 动量与趋势 (25%)
        "ret_20d": 0.15,
        "bias_20d": 0.10,
        
        # 均值回归与反弹 (15%)
        "kdj_j": 0.08,
        "boll_pct_b": 0.07,
        
        # 量价共振与突破 (20%)
        "vol_surge_5_20": 0.10,
        "vwap_bias_5": 0.05,
        "pv_corr_20": 0.05,
        
        # 波动率与筹码控制 (15%)
        "norm_atr": 0.08,
        "profit_ratio": 0.07,
        
        # 舆情与非结构化特征 (25%)
        "sentiment_score": 0.25
    }

    # 市场机制/模式专属权重预设 (各维度总和 1.0)
    REGIME_WEIGHTS = {
        "DEFAULT": DEFAULT_WEIGHTS,
        # 牛市/主升浪突破模式 (强化动量与量价共振突破)
        "BULL": {
            "ret_20d": 0.20,
            "bias_20d": 0.15,
            "kdj_j": 0.05,
            "boll_pct_b": 0.05,
            "vol_surge_5_20": 0.15,
            "vwap_bias_5": 0.08,
            "pv_corr_20": 0.07,
            "norm_atr": 0.05,
            "profit_ratio": 0.05,
            "sentiment_score": 0.15,
        },
        # 震荡/轮动防御模式 (均值回归、筹码与低波动)
        "OSCILLATION": {
            "ret_20d": 0.10,
            "bias_20d": 0.08,
            "kdj_j": 0.12,
            "boll_pct_b": 0.10,
            "vol_surge_5_20": 0.08,
            "vwap_bias_5": 0.06,
            "pv_corr_20": 0.06,
            "norm_atr": 0.12,
            "profit_ratio": 0.10,
            "sentiment_score": 0.18,
        },
        # 熊市/超跌反弹模式 (强调超卖金叉与极低波动防守)
        "BEAR": {
            "ret_20d": 0.05,
            "bias_20d": 0.05,
            "kdj_j": 0.18,
            "boll_pct_b": 0.15,
            "vol_surge_5_20": 0.05,
            "vwap_bias_5": 0.05,
            "pv_corr_20": 0.04,
            "norm_atr": 0.15,
            "profit_ratio": 0.13,
            "sentiment_score": 0.15,
        },
    }

    @classmethod
    def calculate_ic_weights(
        cls,
        ic_dict: Dict[str, float],
        min_weight: float = 0.02
    ) -> Dict[str, float]:
        """根据各因子历史 IC (信息系数) 计算动态自适应合成权重
        
        仅对 IC > 0 的有效预测因子赋予正向权重，若所有 IC <= 0 则回退至默认权重。
        """
        valid_ics = {k: max(0.0, float(v)) for k, v in ic_dict.items() if k in cls.FACTOR_DIRECTIONS}
        total_ic = sum(valid_ics.values())
        if total_ic <= 1e-6:
            return cls.DEFAULT_WEIGHTS.copy()

        raw_weights = {k: max(min_weight, v / total_ic) for k, v in valid_ics.items()}
        total_w = sum(raw_weights.values())
        return {k: round(v / total_w, 4) for k, v in raw_weights.items()}

    @staticmethod
    def _mad_winsorize(values: List[float], n: float = 3.0) -> List[float]:
        """中位数绝对偏差去极值 (MAD Winsorization)"""
        if not values or len(values) < 3:
            return values[:]
        
        sorted_v = sorted(values)
        mid_idx = len(sorted_v) // 2
        median = sorted_v[mid_idx] if len(sorted_v) % 2 != 0 else (sorted_v[mid_idx - 1] + sorted_v[mid_idx]) / 2.0
        
        diffs = [abs(x - median) for x in values]
        sorted_diffs = sorted(diffs)
        mad = sorted_diffs[mid_idx] if len(sorted_diffs) % 2 != 0 else (sorted_diffs[mid_idx - 1] + sorted_diffs[mid_idx]) / 2.0
        
        if mad == 0:
            return values[:]
        
        scale = 1.4826 * mad
        lower_bound = median - n * scale
        upper_bound = median + n * scale
        
        return [max(lower_bound, min(upper_bound, x)) for x in values]

    @staticmethod
    def _zscore(values: List[float], ddof: int = 1) -> List[float]:
        """截面 Z-Score 标准化 (默认 ddof=1 样本标准差，兼容总体标准差 ddof=0)"""
        if not values or len(values) < 2:
            return [0.0] * len(values)
        
        m = sum(values) / len(values)
        denom = max(1, len(values) - ddof)
        variance = sum((x - m) ** 2 for x in values) / denom
        std = math.sqrt(variance)
        if std == 0:
            return [0.0] * len(values)
        
        return [(x - m) / std for x in values]


    @classmethod
    def synthesize_universe(
        cls,
        universe_factors: Dict[str, Dict[str, float]],
        custom_weights: Optional[Dict[str, float]] = None,
        regime: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """对整个股票池进行截面标准化、加权合成与排名
        universe_factors: {'600519': {'ret_20d': 5.2, 'sentiment_score': 0.6, ...}, '000858': {...}}
        regime: 可选 'BULL' | 'BEAR' | 'OSCILLATION' | 'DEFAULT'
        """
        if not universe_factors:
            return {}

        symbols = list(universe_factors.keys())
        if custom_weights:
            raw_weights = custom_weights
        elif regime and regime.upper() in cls.REGIME_WEIGHTS:
            raw_weights = cls.REGIME_WEIGHTS[regime.upper()]
        else:
            raw_weights = cls.DEFAULT_WEIGHTS

        total_w = sum(raw_weights.values())
        if total_w > 0:
            weights = {k: v / total_w for k, v in raw_weights.items()}
        else:
            weights = cls.DEFAULT_WEIGHTS

        # 1. 逐个因子进行截面去极值和 Z-Score
        standardized_factors: Dict[str, Dict[str, float]] = {s: {} for s in symbols}

        for factor_name, weight in weights.items():
            if weight == 0:
                continue
            
            direction = cls.FACTOR_DIRECTIONS.get(factor_name, 1)
            # 收集该因子的有效非空值
            valid_vals = [
                universe_factors[s][factor_name]
                for s in symbols
                if factor_name in universe_factors[s] and universe_factors[s][factor_name] is not None
            ]
            
            # 使用有效值的中位数作为中性填补值，避免填0在偏离时被放大为极端异常Z值
            fill_val = statistics.median(valid_vals) if valid_vals else 0.0
            raw_vals = [
                universe_factors[s][factor_name]
                if (factor_name in universe_factors[s] and universe_factors[s][factor_name] is not None)
                else fill_val
                for s in symbols
            ]
            
            # MAD 去极值
            winsorized = cls._mad_winsorize(raw_vals)
            
            # Z-Score 标准化
            z_vals = cls._zscore(winsorized)
            
            # 方向修正 (如果因子方向为 -1，取反)
            for i, s in enumerate(symbols):
                standardized_factors[s][factor_name] = z_vals[i] * direction

        # 2. 加权合成 Alpha 总分
        composite_scores = []
        for s in symbols:
            total_score = 0.0
            for factor_name, weight in weights.items():
                z = standardized_factors[s].get(factor_name, 0.0)
                total_score += z * weight
            composite_scores.append((s, total_score))

        # 3. 截面分位数排序 (Percentile Rank 0 - 100)
        composite_scores.sort(key=lambda x: x[1])
        n_stocks = len(composite_scores)

        results = {}
        for rank_idx, (sym, raw_comp) in enumerate(composite_scores):
            pct_rank = round((rank_idx + 1) / n_stocks * 100.0, 2)
            results[sym] = {
                "symbol": sym,
                "composite_alpha": round(raw_comp, 4),
                "percentile_rank": pct_rank,
                "factor_details": universe_factors[sym],
                "standardized_z": standardized_factors[sym]
            }

        return results

    @classmethod
    def select_top_k(
        cls,
        ranked_universe: Dict[str, Dict[str, Any]],
        top_k: int = 5,
        min_percentile: float = 75.0
    ) -> List[Dict[str, Any]]:
        """从排序后的股票池中筛选出 Top-K 优质标的"""
        candidates = list(ranked_universe.values())
        # 按综合 Alpha 降序排列
        candidates.sort(key=lambda x: x["composite_alpha"], reverse=True)
        
        filtered = [c for c in candidates if c["percentile_rank"] >= min_percentile]
        return filtered[:top_k]
