# -*- coding: utf-8 -*-
"""Engine B: 技术指标、截面因子与财务排雷引擎测试。

归属代码包：`core/indicators/`, `core/models/`, `core/strategy/fundamental_filter.py`
核心职责与断言：
1. 向量化技术指标计算（MA, MACD, KDJ, RSI, BOLL, ATR）；
2. 形态学分析：水下二次金叉（second_golden_cross）与跳空缺口（gap_analysis）；
3. 截面因子合成器（FactorSynthesizer）：MAD 去极值、Z-Score 标准化与 Top-K 百分位排序；
4. 基本面硬过滤（FundamentalFilter）：五大排雷规则（超高股价、超高PE、亏损股、长期阴跌）与周期股高 PE 动态豁免。
"""
from __future__ import annotations

import pytest

from core.indicators.technical_indicators import (
    calc_all,
    gap_analysis,
    ma,
    rsi,
    second_golden_cross,
)
from core.models.factor_synthesizer import FactorSynthesizer
from core.strategy.fundamental_filter import FundamentalFilter

pytestmark = pytest.mark.core


def _generate_synthetic_klines(count=60, base_price=10.0):
    """构造确定性日K序列：[date, open, close, high, low, volume]"""
    klines = []
    price = base_price
    for i in range(count):
        d = f"2026-08-{i+1:02d}" if i < 30 else f"2026-09-{i-29:02d}"
        op = price
        cl = price + (0.15 if i % 2 == 0 else -0.10)
        hi = max(op, cl) + 0.08
        lo = min(op, cl) - 0.08
        vol = 10000 + i * 150
        klines.append([d, op, cl, hi, lo, vol])
        price = cl
    return klines


def test_technical_indicators_calc_all():
    """验证 6 大核心指标全集计算（MA, MACD, KDJ, RSI, BOLL, ATR）。"""
    klines = _generate_synthetic_klines(60, 10.0)
    tech = calc_all(klines)

    assert "ma" in tech
    assert "macd" in tech
    assert "kdj" in tech
    assert "rsi" in tech
    assert "boll" in tech
    assert "atr" in tech
    assert "latest" in tech

    # 验证 MA 均线列表
    ma_dict = tech["ma"]
    assert "ma5" in ma_dict and "ma20" in ma_dict
    assert len(ma_dict["ma5"]) == 60

    # 验证 MACD
    macd = tech["macd"]
    assert "dif" in macd and "dea" in macd and "bar" in macd
    assert len(macd["dif"]) == 60

    # 验证 RSI 边界
    rsi_list = tech["rsi"]
    assert len(rsi_list) == 60
    assert all(0 <= v <= 100 for v in rsi_list if v is not None)


def test_gap_analysis_and_second_golden_cross():
    """验证跳空缺口识别与水下二次金叉信号。"""
    # 构造跳空缺口
    base_klines = [
        [f"2026-08-0{i+1}", 10.0, 10.0, 10.5, 9.8, 1000]
        for i in range(4)
    ]
    klines_unfilled = base_klines + [
        ["2026-08-05", 9.0, 9.2, 9.5, 8.9, 1000]
    ]
    res_unfilled = gap_analysis(klines_unfilled)
    assert len(res_unfilled["gaps"]) >= 1
    last_gap = res_unfilled["gaps"][-1]
    assert last_gap["direction"] == "down"
    assert last_gap["filled"] is False

    # 水下二次金叉评级判定
    normal_klines = _generate_synthetic_klines(60, 10.0)
    golden = second_golden_cross(normal_klines)
    assert isinstance(golden, dict)
    assert "verdict" in golden
    assert "checklist" in golden
    assert golden["verdict"] in ("A", "B", "C", "D")


def test_factor_synthesizer_mad_and_zscore():
    """验证 FactorSynthesizer 截面去极值与 Z-Score 标准化。"""
    # 包含极端离群值的数据集
    raw_vals = [1.0, 1.2, 1.1, 1.05, 100.0]
    winsorized = FactorSynthesizer._mad_winsorize(raw_vals, n=3.0)

    # 离群值 100.0 应被截断
    assert winsorized[-1] < 100.0
    assert winsorized[0] == 1.0

    # Z-Score 标准化
    z_vals = FactorSynthesizer._zscore(winsorized)
    assert len(z_vals) == 5
    avg = sum(z_vals) / len(z_vals)
    assert abs(avg) < 1e-4


def test_factor_synthesizer_multi_factor_rank():
    """验证多因子加权合成与截面百分位排名及 Top-K 筛选。"""
    stock_factors = {
        "600519": {"ret_20d": 5.0, "bias_20d": 2.0, "norm_atr": 0.02, "sentiment_score": 0.8},
        "000001": {"ret_20d": -2.0, "bias_20d": -1.0, "norm_atr": 0.04, "sentiment_score": 0.2},
        "300750": {"ret_20d": 8.0, "bias_20d": 3.0, "norm_atr": 0.03, "sentiment_score": 0.9},
    }

    ranked = FactorSynthesizer.synthesize_universe(stock_factors)
    assert len(ranked) == 3
    # 动量与舆情均最强的 300750 得分与分位数应最高
    assert ranked["300750"]["composite_alpha"] > ranked["000001"]["composite_alpha"]
    assert ranked["300750"]["percentile_rank"] == 100.0

    top_stocks = FactorSynthesizer.select_top_k(ranked, top_k=2, min_percentile=50.0)
    assert len(top_stocks) >= 1
    assert top_stocks[0]["symbol"] == "300750"


def test_fundamental_filter_five_hard_rules():
    """验证 FundamentalFilter 五大财务排雷规则。"""
    ff = FundamentalFilter(max_price=350.0, max_pe=100.0)
    normal_klines = _generate_synthetic_klines(260, 20.0)

    # 1. 极端高股价股票 (>350)
    res_high_price = ff.inspect("600519", normal_klines, quote={"price": 1500.0, "pe": 25.0})
    assert not res_high_price["passed"], "极端高股价股票应被拦截"

    # 2. 超高 PE 股票 (>100)
    res_high_pe = ff.inspect("000001", normal_klines, quote={"price": 25.0, "pe": 150.0})
    assert not res_high_pe["passed"], "超高PE应被拦截"

    # 3. 亏损股 (PE <= 0)
    res_loss = ff.inspect("000002", normal_klines, quote={"price": 25.0, "pe": -10.0})
    assert not res_loss["passed"], "亏损股票应被拦截"

    # 4. 持续大幅阴跌 (回撤 > 50%)
    klines_downtrend = []
    p = 100.0
    for i in range(260):
        if i > 10:
            p *= 0.996
        klines_downtrend.append([f"2026-{i:03d}", p, p, p * 1.01, p * 0.99, 10000])
    res_downtrend = ff.inspect("000003", klines_downtrend, quote={"price": p, "pe": 15.0})
    assert not res_downtrend["passed"], "长期阴跌股票应被拦截"

    # 5. 合规股票正常通过
    res_normal = ff.inspect("600000", normal_klines, quote={"price": 35.0, "pe": 20.0})
    assert res_normal["passed"] is True


def test_fundamental_filter_cyclical_sector_exemption():
    """验证周期股高 PE 动态行业豁免机制。"""
    ff = FundamentalFilter(max_pe=100.0)
    klines = _generate_synthetic_klines(260, 10.0)

    # 洛阳钼业 (有色金属) 周期股高 PE 应该得到豁免
    quote_cyclical = {
        "price": 8.50,
        "pe": 125.0,
        "sector": "有色金属",
        "industry": "小金属",
    }
    res_cyclical = ff.inspect("603993", klines, quote=quote_cyclical)
    pe_flags = [f for f in res_cyclical["risk_flags"] if "超高PE" in f]
    assert len(pe_flags) == 0, "周期股应豁免超高PE风险标记"
    assert any("周期股高PE豁免" in w for w in res_cyclical["warnings"])

    # 非周期行业（如传媒）高 PE 必须被严格拦截
    quote_non_cyclical = {
        "price": 20.0,
        "pe": 150.0,
        "sector": "传媒",
        "industry": "游戏",
    }
    res_non_cyclical = ff.inspect("002624", klines, quote=quote_non_cyclical)
    assert not res_non_cyclical["passed"]
    assert any("超高PE" in f for f in res_non_cyclical["risk_flags"])
