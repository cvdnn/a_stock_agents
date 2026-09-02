#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股五大风险与基本面过滤层 (Fundamental & Risk Filter Layer)
基于《A股选股模型风险审查与改进》评估报告设计

针对原纯技术五维模型的五大缺陷提供前置风控拦截:
  1. 高股价风险 (流动性折损、单手资金占用过大)
  2. 超高PE风险 (亏损或估值泡沫)
  3. 长期亏损风险 (准ST、业绩雷)
  4. 业绩差风险 (主营下滑、反弹无持续性)
  5. 长期阴跌风险 (长周期下行通道、抄底接飞刀)
"""

from typing import Dict, List, Optional, Tuple, Any


class FundamentalFilter:
    """基本面与五大风险前置过滤引擎 (P0 + P1 级风控)"""

    # 默认行业/周期股豁免白名单 (可按需动态扩展)
    DEFAULT_CYCLICAL_WHITELIST = {
        "601899",  # 紫金矿业 (有色金属)
        "601088",  # 中国神华 (煤炭)
        "600028",  # 中国石化 (石油)
        "600900",  # 长江电力 (电力)
    }

    def __init__(
        self,
        max_price: float = 350.0,
        max_pe: float = 100.0,
        min_pe: float = 0.0,
        enable_price_filter: bool = True,
        enable_pe_filter: bool = True,
        enable_profit_filter: bool = True,
        enable_growth_filter: bool = True,
        enable_downtrend_filter: bool = True,
        cyclical_whitelist: Optional[set] = None,
    ):
        self.max_price = max_price
        self.max_pe = max_pe
        self.min_pe = min_pe
        self.enable_price_filter = enable_price_filter
        self.enable_pe_filter = enable_pe_filter
        self.enable_profit_filter = enable_profit_filter
        self.enable_growth_filter = enable_growth_filter
        self.enable_downtrend_filter = enable_downtrend_filter
        self.cyclical_whitelist = cyclical_whitelist or self.DEFAULT_CYCLICAL_WHITELIST

    def inspect(
        self,
        code: str,
        klines: List[List[Any]],
        quote: Optional[Dict[str, Any]] = None,
        finance: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        对标的执行全维度基本面与风险点审查

        Args:
            code: 股票代码 (如 "600519")
            klines: 历史日K线 [[date, open, close, high, low, vol], ...]
            quote: 实时行情数据 (包含 price, pe, turnover_pct, market_cap 等)
            finance: 财务数据 (包含 net_profit, deduct_profit, profit_yoy, revenue_yoy 等)

        Returns:
            dict: 审查结果字典
        """
        risk_flags = []
        warnings = []
        details = {}
        is_cyclical_exempt = code in self.cyclical_whitelist

        if not klines or len(klines) < 10:
            return {
                "code": code,
                "passed": False,
                "risk_flags": ["K线数据严重不足"],
                "warnings": [],
                "details": {},
                "action_suggest": "强制剔除 (数据缺失)",
            }

        closes = [float(k[2]) for k in klines]
        highs = [float(k[3]) for k in klines]
        lows = [float(k[4]) for k in klines]
        curr_price = float(quote.get("price", closes[-1])) if quote else closes[-1]

        # -------------------------------------------------------------
        # 1. 风险一：高股价风险 (P1-重要)
        # -------------------------------------------------------------
        details["price"] = round(curr_price, 2)
        if self.enable_price_filter:
            if curr_price > self.max_price:
                risk_flags.append(f"高股价风险 (现价 {curr_price:.2f} > 上限 {self.max_price:.0f}元)")
            elif curr_price > self.max_price * 0.6:
                warnings.append(f"股价偏高 ({curr_price:.2f}元, 建议适度控制单仓规模)")

        # -------------------------------------------------------------
        # 2. 风险二：超高PE/亏损风险 (P0-必须)
        # -------------------------------------------------------------
        pe = None
        if quote and "pe" in quote and quote["pe"] is not None:
            try:
                pe = float(quote["pe"])
            except (ValueError, TypeError):
                pe = None

        details["pe"] = pe
        if self.enable_pe_filter and pe is not None:
            if pe <= self.min_pe:
                risk_flags.append(f"亏损风险 (PE={pe:.1f} <= 0)")
            elif pe > self.max_pe:
                if not is_cyclical_exempt:
                    risk_flags.append(f"超高PE风险 (PE={pe:.1f} > {self.max_pe:.0f}倍)")
                else:
                    warnings.append(f"周期股高PE豁免 (PE={pe:.1f})")
            elif pe > 60:
                warnings.append(f"估值偏高 (PE={pe:.1f} ∈ (60, 100], 建议仓位减半)")

        # -------------------------------------------------------------
        # 3. 风险三：长期亏损与暴雷风险 (P0-必须)
        # -------------------------------------------------------------
        if self.enable_profit_filter and finance:
            net_profit = finance.get("net_profit")
            deduct_profit = finance.get("deduct_profit")
            if net_profit is not None and net_profit <= 0:
                risk_flags.append("净利润为负 (亏损风险)")
            if deduct_profit is not None and deduct_profit <= 0:
                risk_flags.append("扣非净利润为负 (主营恶化/保壳风险)")

        # -------------------------------------------------------------
        # 4. 风险四：业绩差风险 (P0-必须)
        # -------------------------------------------------------------
        if self.enable_growth_filter and finance:
            profit_yoy = finance.get("profit_yoy")
            revenue_yoy = finance.get("revenue_yoy")
            if profit_yoy is not None and revenue_yoy is not None:
                if profit_yoy <= -20.0 and revenue_yoy <= -15.0:
                    if not is_cyclical_exempt:
                        risk_flags.append(f"业绩大幅下滑 (净利同比{profit_yoy:.1f}%, 营收同比{revenue_yoy:.1f}%)")
                    else:
                        warnings.append("周期股业绩低谷豁免")
                elif profit_yoy <= 0 and revenue_yoy <= 0:
                    warnings.append(f"业绩双下滑 (净利同比{profit_yoy:.1f}%, 营收同比{revenue_yoy:.1f}%)")

        # -------------------------------------------------------------
        # 5. 风险五：长期阴跌与抄底接飞刀风险 (P1-重要)
        # -------------------------------------------------------------
        if self.enable_downtrend_filter:
            n_len = len(closes)
            # 近60日跌幅
            if n_len >= 60:
                peak_60 = max(highs[-60:])
                dd_60 = (curr_price / peak_60 - 1) * 100 if peak_60 > 0 else 0
                details["dd_60"] = round(dd_60, 2)
                if dd_60 < -20.0:
                    risk_flags.append(f"近60日大幅阴跌 (距高点回撤 {dd_60:.1f}% < -20%)")

            # 近120日跌幅
            if n_len >= 120:
                peak_120 = max(highs[-120:])
                dd_120 = (curr_price / peak_120 - 1) * 100 if peak_120 > 0 else 0
                details["dd_120"] = round(dd_120, 2)
                if dd_120 < -30.0:
                    risk_flags.append(f"近120日大幅阴跌 (距高点回撤 {dd_120:.1f}% < -30%)")

            # 近250日跌幅与新低校验
            if n_len >= 250:
                peak_250 = max(highs[-250:])
                min_250 = min(lows[-250:])
                dd_250 = (curr_price / peak_250 - 1) * 100 if peak_250 > 0 else 0
                dist_low_250 = (curr_price / min_250 - 1) * 100 if min_250 > 0 else 0
                details["dd_250"] = round(dd_250, 2)
                details["dist_low_250"] = round(dist_low_250, 2)

                if dd_250 < -40.0:
                    risk_flags.append(f"近250日长期阴跌 (距年内高点回撤 {dd_250:.1f}% < -40%)")
                if dist_low_250 < 10.0:
                    risk_flags.append(f"处于年内历史新低附近 (距250日低点仅 +{dist_low_250:.1f}% < 10%)")
            elif n_len >= 60:
                min_60 = min(lows[-60:])
                dist_low_60 = (curr_price / min_60 - 1) * 100 if min_60 > 0 else 0
                if dist_low_60 < 5.0:
                    risk_flags.append(f"处于阶段新低附近 (距60日低点仅 +{dist_low_60:.1f}% < 5%)")

        passed = len(risk_flags) == 0

        # 汇总建议
        if not passed:
            action_suggest = "强制剔除 (" + "；".join(risk_flags) + ")"
        elif warnings:
            action_suggest = "通过(谨慎/需减仓) (" + "；".join(warnings) + ")"
        else:
            action_suggest = "正常纳入"

        return {
            "code": code,
            "passed": passed,
            "risk_flags": risk_flags,
            "warnings": warnings,
            "details": details,
            "action_suggest": action_suggest,
            "cyclical_exempt": is_cyclical_exempt,
        }
