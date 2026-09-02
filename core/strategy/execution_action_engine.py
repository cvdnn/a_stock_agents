#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股实战交易反应动作与意图决策中枢 (Execution & Intent Action Engine - EMS)
版本: 2.0.0
核心特性:
  1. 自然语言意图智能评估与路由 (IntentEvaluator)
  2. 五类下跌场景化精准诊断与战术应对矩阵 (DownsideReactionMatrix)
  3. 6 大核心交易反应动作与微观订单生成 (ExecutionActionEngine)
  4. 摩擦税费最低保本精确计算 (万0.85) 与 ATR 波动率自适应风控
"""

import re
import math
from typing import Dict, Any, List, Optional, Tuple

# 交易摩擦成本常数
COMMISSION_RATE = 0.00012   # 佣金 万1.2 (双边)
STAMP_TAX_RATE = 0.0005     # 印花税 万5 (仅卖出)
TRANSFER_FEE_RATE = 0.00001 # 过户费 万0.1 (沪深双边)
MIN_COMMISSION = 5.0        # 单笔最低佣金 5元


class IntentEvaluator:
    """
    用户自然语言意图解析与评估器
    从用户日常大白话提问中智能提取：核心意图、标的代码/名称、持仓盈亏心理。
    """
    
    INTENT_STOCK_PICKING = "STOCK_PICKING"         # 意图1: 选股与建仓择时
    INTENT_ORDER_EXECUTION = "ORDER_EXECUTION"     # 意图2: 精确交易执行动作 (几点买/挂什么价/止盈)
    INTENT_TRAPPED_RECOVERY = "TRAPPED_RECOVERY"   # 意图3: 持仓诊断与解套自救
    INTENT_DOWNSIDE_REACTION = "DOWNSIDE_REACTION" # 意图4: 下跌应对与假摔/破位处置
    INTENT_REVIEW_REPORT = "REVIEW_REPORT"         # 意图5: 投研复盘与报告生成

    INTENT_PATTERNS = {
        INTENT_STOCK_PICKING: [
            r'买什么', r'推荐', r'选股', r'主线', r'能买吗', r'建仓', r'龙头', r'突破.*买', r'上车', r'找票', r'备选', r'买点'
        ],
        INTENT_ORDER_EXECUTION: [
            r'怎么操作', r'现在卖不卖', r'怎么卖', r'冲高.*卖', r'止盈', r'挂单', r'几点买', r'做T', r'减仓', r'卖出', r'拿了.*怎么', r'赚了.*怎么', r'移动止盈'
        ],
        INTENT_TRAPPED_RECOVERY: [
            r'被套', r'亏损', r'深套', r'解套', r'成本', r'补仓还是割肉', r'套牢', r'亏了', r'亏了.*点', r'如何自救', r'摊薄成本', r'补仓'
        ],
        INTENT_DOWNSIDE_REACTION: [
            r'跌了', r'破位', r'大跌', r'还会跌吗', r'要不要割', r'要割肉吗', r'假摔', r'跳水', r'闪崩', r'暴跌', r'杀跌', r'预测.*跌', r'防守', r'回调', r'回落', r'见顶', r'预测.*回调', r'大跌.*割'
        ],
        INTENT_REVIEW_REPORT: [
            r'复盘', r'报告', r'HTML', r'总结', r'生成', r'整理股池', r'归档'
        ]
    }

    STOCK_CODE_PATTERN = re.compile(r'\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b')
    KNOWN_NAMES = {
        '许继电气': '000400', '科大讯飞': '002230', '中航沈飞': '600760',
        '福晶科技': '002222', '长电科技': '600584', '瑞芯微': '603893',
        '紫金矿业': '601899', '恒瑞医药': '600276', '中国中车': '601766',
        '沪电股份': '002463', '工业富联': '601138', '贵州茅台': '600519',
        '宁德时代': '300750', '北方华创': '002371', '药明康德': '603259'
    }

    @classmethod
    def parse_user_query(cls, text: str) -> Dict[str, Any]:
        """
        解析用户自然语言输入
        """
        detected_codes = cls.STOCK_CODE_PATTERN.findall(text)
        detected_names = [name for name, code in cls.KNOWN_NAMES.items() if name in text]
        for name in detected_names:
            code = cls.KNOWN_NAMES[name]
            if code not in detected_codes:
                detected_codes.append(code)

        # 意图打分匹配
        intent_scores = {k: 0 for k in cls.INTENT_PATTERNS}
        for intent, patterns in cls.INTENT_PATTERNS.items():
            for p in patterns:
                if re.search(p, text, re.IGNORECASE):
                    intent_scores[intent] += 2

        # 优先权与上下文微调
        if any(kw in text for kw in ['补仓', '摊薄', '深套', '解套', '自救']) or (any(kw in text for kw in ['亏了', '亏损']) and '买' not in text):
            intent_scores[cls.INTENT_TRAPPED_RECOVERY] += 5

        if any(kw in text for kw in ['跌了', '大跌', '跳水', '假摔', '闪崩', '回调', '见顶']):
            intent_scores[cls.INTENT_DOWNSIDE_REACTION] += 4

        if any(kw in text for kw in ['赚了', '止盈', '做T', '怎么卖', '几点买']):
            intent_scores[cls.INTENT_ORDER_EXECUTION] += 4

        if any(kw in text for kw in ['买什么', '推荐', '选股', '突破.*买']):
            intent_scores[cls.INTENT_STOCK_PICKING] += 5

        primary_intent = max(intent_scores, key=intent_scores.get) if any(intent_scores.values()) else cls.INTENT_ORDER_EXECUTION

        return {
            "raw_query": text,
            "primary_intent": primary_intent,
            "detected_codes": detected_codes,
            "detected_names": detected_names,
            "intent_scores": intent_scores
        }


class DownsideReactionMatrix:
    """
    五类下跌场景化精准诊断与战术应对矩阵
    """

    TYPE_A_OVERBOUGHT_TOP = "TYPE_A_OVERBOUGHT_TOP"               # 类型A: 高位乖离过大技术性见顶
    TYPE_B_FALSE_BREAKDOWN_SHAKEOUT = "TYPE_B_FALSE_BREAKDOWN_SHAKEOUT" # 类型B: 主力洗盘缩量假摔诱空
    TYPE_C_REBOUND_RESISTANCE_HIT = "TYPE_C_REBOUND_RESISTANCE_HIT"     # 类型C: 弱势反弹触碰MA60强阻力
    TYPE_D_TRUE_TREND_BREAKDOWN = "TYPE_D_TRUE_TREND_BREAKDOWN"         # 类型D: 中期破位杀跌/主跌通道
    TYPE_E_FLASH_CRASH_T0 = "TYPE_E_FLASH_CRASH_T0"                     # 类型E: 盘中突发大单闪崩(-5%)

    @classmethod
    def diagnose_downside(cls, 
                          quote: Dict[str, Any], 
                          tech: Dict[str, Any], 
                          holding: Optional[Dict[str, Any]] = None,
                          model_score: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        评估下跌性质并生成战术应对
        """
        price = float(quote.get("price", 0.0))
        change_pct = float(quote.get("change_pct", 0.0))
        vol_ratio = float(quote.get("vol_ratio", 1.0))
        outer_ratio = float(quote.get("outer_ratio", 50.0))
        
        ma5 = float(tech.get("ma5", price))
        ma10 = float(tech.get("ma10", price))
        ma20 = float(tech.get("ma20", price))
        ma60 = float(tech.get("ma60", price))
        bias20 = ((price - ma20) / ma20 * 100.0) if ma20 > 0 else 0.0
        kdj_j = float(tech.get("kdj_j", 50.0))
        rsi14 = float(tech.get("rsi14", 50.0))
        atr14 = float(tech.get("atr14", price * 0.03))

        rating = str(model_score.get("rating", "B")) if model_score else "B"
        shares = int(holding.get("shares", 1000)) if holding else 1000
        cost = float(holding.get("cost", price)) if holding else price
        profit_pct = ((price - cost) / cost * 100.0) if cost > 0 else 0.0

        # 诊断类型 E: 日内极端闪崩
        if change_pct <= -5.0:
            return {
                "downside_type": cls.TYPE_E_FLASH_CRASH_T0,
                "title": "【类型 E：盘中极端闪崩】",
                "diagnosis": f"日内跌幅达到 {change_pct:.2f}% (<= -5.0%)，突发大单不计成本砸盘，触发 T0 硬风控",
                "action": "一键市价闪电清仓",
                "order_type": "对手价/市价单",
                "shares": shares,
                "execution_window": "触碰瞬间立即执行",
                "rule": "封死最大单笔损失在 -5% 以内，保全本金"
            }

        # 诊断类型 D: 中期破位杀跌
        if (price < ma20 and bias20 < -1.5) or rating == "D" or (ma5 < ma20 and ma10 < ma20 and change_pct < -1.5):
            return {
                "downside_type": cls.TYPE_D_TRUE_TREND_BREAKDOWN,
                "title": "【类型 D：趋势破位杀跌】",
                "diagnosis": f"收盘有效跌破 MA20 ({ma20:.2f}) 或评级降为 {rating} 级，均线空头下沉，主升逻辑证伪",
                "action": "次日早盘开盘 15 分钟无条件市价清仓 (严禁补仓接飞刀)",
                "order_type": "开盘市价单/集合竞价",
                "shares": shares,
                "execution_window": "次日 09:30-09:45",
                "rule": "空头形态越补越亏，立即斩仓剥离流动性，转入 A 级主线龙头"
            }

        # 诊断类型 A: 高位乖离过大技术性见顶
        if bias20 > 8.0 and (kdj_j > 95 or rsi14 > 72):
            trim_shares = max(int(shares * 0.30 // 100 * 100), 100) if shares >= 200 else shares
            return {
                "downside_type": cls.TYPE_A_OVERBOUGHT_TOP,
                "title": "【类型 A：高位乖离过大见顶】",
                "diagnosis": f"距 MA20 乖离率达 +{bias20:.1f}%，J值 {kdj_j:.1f}/RSI {rsi14:.1f} 严重超买，面临技术性获利回吐",
                "action": "尾盘主动抢跑卖出 25%~50% 仓位锁定利润",
                "order_type": "尾盘市价单",
                "shares": trim_shares,
                "execution_window": "尾盘 14:45-14:55",
                "rule": "锁定浮盈，剩余底仓上移止损线至 MA5，回踩 MA10/MA20 企稳再接回"
            }

        # 诊断类型 C: 弱势反弹触碰 MA60 强阻力
        if abs(price - ma60) / ma60 < 0.02 and outer_ratio < 45.0 and ma60 > ma20:
            trim_shares = max(int(shares * 0.50 // 100 * 100), 100) if shares >= 200 else shares
            return {
                "downside_type": cls.TYPE_C_REBOUND_RESISTANCE_HIT,
                "title": "【类型 C：弱势反弹触碰强阻力】",
                "diagnosis": f"超跌反弹逼近 MA60 ({ma60:.2f}元) 强阻力区，外盘仅 {outer_ratio:.1f}% 动能衰竭，即将二次探底",
                "action": "早盘冲高限价坚决卖出 50% 仓位",
                "order_type": "阻力位限价单",
                "shares": trim_shares,
                "execution_window": "早盘 09:30-10:00 冲高时",
                "rule": "反弹非反转，借反抽坚决大减仓，绝不留恋"
            }

        # 诊断类型 B: 主力洗盘缩量假摔诱空
        if change_pct < -1.8 and vol_ratio < 0.70 and price >= ma20 * 0.985:
            t_shares = max(int(shares * 0.30 // 100 * 100), 100)
            return {
                "downside_type": cls.TYPE_B_FALSE_BREAKDOWN_SHAKEOUT,
                "title": "【类型 B：主力缩量假摔诱空】",
                "diagnosis": f"早盘下探 {change_pct:.2f}%，但量比仅 {vol_ratio:.2f} (极度缩量)，MA20 支撑完好，判定为主力无量洗盘",
                "action": "绝不割肉！现价低吸 30% 仓位打底做 T，午后冲高 T 出",
                "order_type": "分时限价单",
                "buy_shares": t_shares,
                "buy_price": f"{price:.2f} 元",
                "sell_shares": t_shares,
                "sell_price": f"{price * 1.025:.2f} 元 (+2.5% 即抛出老筹码)",
                "execution_window": "早盘 10:00 低吸 / 午后 14:00 冲高卖出",
                "rule": "主力假摔不割肉，反向做 T 降低底仓成本"
            }

        # 默认常规回调
        return {
            "downside_type": "NORMAL_PULLBACK",
            "title": "【常规技术性良性回踩】",
            "diagnosis": f"当前回踩幅度 {change_pct:.2f}%，均线多头形态保持，处于正常波段整固区间",
            "action": "持仓不动，以 MA20 ({ma20:.2f}元) 为终极防线",
            "order_type": "持有观察",
            "shares": 0,
            "execution_window": "全天监控",
            "rule": "只要收盘不跌破 MA20，坚决持股待涨"
        }


class ExecutionActionEngine:
    """
    全量实战交易反应中枢 (集成意图路由与下跌矩阵)
    """

    @staticmethod
    def calc_min_breakeven_price(cost: float, shares: int = 1000) -> float:
        """计算含税费保本价"""
        if cost <= 0 or shares <= 0: return cost
        buy_principal = cost * shares
        buy_comm = max(buy_principal * COMMISSION_RATE, MIN_COMMISSION)
        buy_transfer = buy_principal * TRANSFER_FEE_RATE
        total_buy_cost = buy_principal + buy_comm + buy_transfer
        denom = 1.0 - COMMISSION_RATE - STAMP_TAX_RATE - TRANSFER_FEE_RATE
        raw_p = total_buy_cost / (shares * denom)
        return math.ceil(raw_p * 100.0) / 100.0

    @classmethod
    def _format_result(cls, code: str, name: str, price: float, is_held: bool,
                       action_type: str, urgency: str, actions: List[Dict[str, Any]],
                       exec_window: str, profit_pct: float, breakeven_p: float,
                       downside_diag: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "code": code,
            "name": name,
            "current_price": price,
            "is_held": is_held,
            "action_type": action_type,       # BUY, SELL, HOLD, DO_T, STOP_LOSS, TRIM, OBSERVE
            "urgency": urgency,               # CRITICAL, HIGH, MEDIUM, LOW
            "profit_pct": round(profit_pct, 2) if is_held else 0.0,
            "breakeven_price": breakeven_p,
            "recommended_window": exec_window,
            "action_items": actions,
            "downside_diagnosis": downside_diag
        }

    @classmethod
    def generate_action(cls, 
                        code: str, 
                        name: str,
                        quote: Dict[str, Any],
                        tech: Dict[str, Any],
                        holding: Optional[Dict[str, Any]] = None,
                        model_score: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        全量决策生成
        """
        price = float(quote.get("price", 0.0))
        open_p = float(quote.get("open", price))
        high_p = float(quote.get("high", price))
        low_p = float(quote.get("low", price))
        change_pct = float(quote.get("change_pct", 0.0))
        vol_ratio = float(quote.get("vol_ratio", 1.0))
        outer_ratio = float(quote.get("outer_ratio", 50.0))
        turnover = float(quote.get("turnover", 0.0))

        ma5 = float(tech.get("ma5", price))
        ma10 = float(tech.get("ma10", price))
        ma20 = float(tech.get("ma20", price))
        ma60 = float(tech.get("ma60", price))
        bias20 = ((price - ma20) / ma20 * 100.0) if ma20 > 0 else 0.0
        kdj_j = float(tech.get("kdj_j", 50.0))
        rsi14 = float(tech.get("rsi14", 50.0))
        atr14 = float(tech.get("atr14", price * 0.03))
        macd_dif = float(tech.get("macd_dif", 0.0))
        macd_dea = float(tech.get("macd_dea", 0.0))

        is_held = holding is not None and holding.get("shares", 0) > 0
        cost = float(holding.get("cost", 0.0)) if is_held else 0.0
        shares = int(holding.get("shares", 0)) if is_held else 0
        max_high = float(holding.get("max_high", price)) if is_held else price
        max_high = max(max_high, high_p)
        profit_pct = ((price - cost) / cost * 100.0) if is_held and cost > 0 else 0.0

        cs_score = float(model_score.get("cs", 60.0)) if model_score else 60.0
        rating = str(model_score.get("rating", "B")) if model_score else "B"
        breakeven_p = cls.calc_min_breakeven_price(cost, shares) if is_held else 0.0

        # 执行下跌场景化诊断
        downside_diag = DownsideReactionMatrix.diagnose_downside(quote, tech, holding, model_score)

        actions = []
        action_type = "OBSERVE"
        urgency = "NORMAL"
        exec_window = "14:45-14:55"

        # 1. 持仓风控与下跌处置优先
        if is_held:
            # 1.1 闪崩 / 破位
            if downside_diag["downside_type"] == DownsideReactionMatrix.TYPE_E_FLASH_CRASH_T0:
                action_type = "STOP_LOSS"
                urgency = "CRITICAL"
                actions.append(downside_diag)
                return cls._format_result(code, name, price, is_held, action_type, urgency, actions, "盘中即时触发", profit_pct, breakeven_p, downside_diag)

            if downside_diag["downside_type"] == DownsideReactionMatrix.TYPE_D_TRUE_TREND_BREAKDOWN:
                action_type = "STOP_LOSS"
                urgency = "HIGH"
                actions.append(downside_diag)
                return cls._format_result(code, name, price, is_held, action_type, urgency, actions, "次日 09:30-09:45", profit_pct, breakeven_p, downside_diag)

            # 1.2 动态移动追踪止盈 (浮盈 > +8%)
            if profit_pct >= 8.0:
                trailing_stop_p = round(max(max_high - 1.5 * atr14, max_high * 0.98, ma5), 2)
                if price < trailing_stop_p:
                    action_type = "TRIM"
                    urgency = "HIGH"
                    actions.append({
                        "action": "【动态追踪止盈】市价出清锁定暴利",
                        "reason": f"持仓浮盈达 +{profit_pct:.1f}%，现价跌破动态出场保护线 ({trailing_stop_p:.2f}元)",
                        "shares_to_sell": shares,
                        "order_type": "市价单/对手价",
                        "target_price": f"触发线 {trailing_stop_p:.2f} 元",
                        "time_window": "跌破动态线即时执行"
                    })
                    return cls._format_result(code, name, price, is_held, action_type, urgency, actions, "盘中即时 / 14:50", profit_pct, breakeven_p, downside_diag)
                else:
                    action_type = "HOLD"
                    urgency = "LOW"
                    actions.append({
                        "action": "【主升浪死拿】启用动态移动止盈保护",
                        "reason": f"持仓浮盈 +{profit_pct:.1f}%，多头主升完好；动态出场线设为 {trailing_stop_p:.2f} 元 (不破一股不卖)",
                        "shares_to_sell": 0,
                        "order_type": "暂不下单",
                        "target_price": f"动态防守线 {trailing_stop_p:.2f} 元",
                        "time_window": "全天监控"
                    })
                    return cls._format_result(code, name, price, is_held, action_type, urgency, actions, "持股待涨", profit_pct, breakeven_p, downside_diag)

            # 1.3 高位乖离 / 阻力减仓
            if downside_diag["downside_type"] in (DownsideReactionMatrix.TYPE_A_OVERBOUGHT_TOP, DownsideReactionMatrix.TYPE_C_REBOUND_RESISTANCE_HIT):
                action_type = "TRIM"
                urgency = "MEDIUM" if downside_diag["downside_type"] == DownsideReactionMatrix.TYPE_A_OVERBOUGHT_TOP else "HIGH"
                actions.append(downside_diag)
                return cls._format_result(code, name, price, is_held, action_type, urgency, actions, downside_diag["execution_window"], profit_pct, breakeven_p, downside_diag)

            # 1.4 主力假摔做 T
            if downside_diag["downside_type"] == DownsideReactionMatrix.TYPE_B_FALSE_BREAKDOWN_SHAKEOUT:
                action_type = "DO_T"
                urgency = "MEDIUM"
                actions.append(downside_diag)
                return cls._format_result(code, name, price, is_held, action_type, urgency, actions, downside_diag["execution_window"], profit_pct, breakeven_p, downside_diag)

        # 2. 未持仓 / 新标的建仓决策
        if not is_held:
            # 突破买入 (40/60)
            is_breakout = (price > ma20 and (price - open_p) / open_p > 0.02 and 
                           vol_ratio > 1.4 and outer_ratio > 53.0 and rating in ("A", "B"))
            if is_breakout:
                action_type = "BUY"
                urgency = "HIGH"
                actions.append({
                    "action": "【40/60 突破战法】尾盘市价买入首批 40% 底仓",
                    "reason": f"放量突破 MA20 ({ma20:.2f})，量比 {vol_ratio:.2f}，外盘占比 {outer_ratio:.1f}%，A级共振确立",
                    "target_position": "总目标仓位 15%~20%",
                    "first_batch_pct": "首批 40% 底仓",
                    "order_type": "尾盘市价单/对手价",
                    "buy_price": f"现价附近 ({price:.2f}元)",
                    "initial_stop_loss": f"{round(max(price * 0.95, price - 1.8 * atr14), 2)} 元",
                    "time_window": "14:45-14:55 定盘确认买入"
                })
                return cls._format_result(code, name, price, is_held, action_type, urgency, actions, "尾盘 14:45-14:55", profit_pct, breakeven_p, downside_diag)

            # 均线回踩两笔挂单
            is_pullback = (abs(bias20) <= 2.5 and vol_ratio < 0.90 and 
                           ma5 > ma20 and macd_dif > macd_dea and rating in ("A", "B"))
            if is_pullback:
                action_type = "BUY"
                urgency = "MEDIUM"
                actions.append({
                    "action": "【均线回踩挂单】MA20 处分两批限价挂单买入",
                    "reason": f"多头缩量回踩 MA20 ({ma20:.2f}元)，抛压衰竭，企稳低吸机会",
                    "batch_1": f"30% 仓位挂单在 {round(ma20 * 1.003, 2):.2f} 元 (MA20 + 0.3%)",
                    "batch_2": f"30% 仓位挂单在 {round(ma20 * 0.998, 2):.2f} 元 (MA20 - 0.2%)",
                    "initial_stop_loss": f"{round(ma20 * 0.96, 2)} 元 (跌破 MA20 4% 止损)",
                    "time_window": "早盘 09:25 集合竞价或开盘前提前挂入"
                })
                return cls._format_result(code, name, price, is_held, action_type, urgency, actions, "早盘提前限价挂单", profit_pct, breakeven_p, downside_diag)

        # 3. 常规持股或观望
        if is_held:
            action_type = "HOLD"
            urgency = "LOW"
            actions.append({
                "action": "【持股待涨】均线多头正常持仓",
                "reason": f"当前浮盈 +{profit_pct:.2f}%，趋势健康，T1防守位 {ma10:.2f}，T2底线 {ma20:.2f}，最低保本价 {breakeven_p:.2f}",
                "shares_to_sell": 0,
                "order_type": "暂不下单",
                "time_window": "全天观察"
            })
            return cls._format_result(code, name, price, is_held, action_type, urgency, actions, "持有观察", profit_pct, breakeven_p, downside_diag)
        else:
            action_type = "OBSERVE"
            urgency = "LOW"
            actions.append({
                "action": "【观望等待】未达标准右侧入场触发线",
                "reason": f"当前评分 {cs_score:.1f}，均线纠缠或动能不足，等待放量突破 MA20 ({ma20:.2f}) 或回踩确认",
                "target_watch_price": f"突破关注 {ma20 * 1.01:.2f} 元 / 回踩关注 {ma20:.2f} 元",
                "time_window": "放入自选股池监控"
            })
            return cls._format_result(code, name, price, is_held, action_type, urgency, actions, "观望等待", profit_pct, breakeven_p, downside_diag)

    @classmethod
    def render_markdown_card(cls, result: Dict[str, Any]) -> str:
        """渲染 Markdown 动作卡片"""
        code = result["code"]
        name = result["name"]
        p = result["current_price"]
        act_type = result["action_type"]
        urgency = result["urgency"]
        window = result["recommended_window"]
        is_held = result["is_held"]

        icon_map = {
            "BUY": "🚀 【买入 / 建仓指令】",
            "SELL": "🛑 【清仓 / 避险指令】",
            "STOP_LOSS": "⚠️ 【强制止损指令】",
            "TRIM": "💰 【止盈 / 减仓指令】",
            "DO_T": "🔄 【主力假摔 / 做T指令】",
            "HOLD": "🛡️ 【安心持股指令】",
            "OBSERVE": "👀 【观望等待指令】"
        }
        header_title = icon_map.get(act_type, "📋 【交易指令】")

        lines = [
            f"### {header_title} `{code}` **{name}** (现价: ¥{p:.2f})",
            f"> **执行时间窗口**：`{window}` | **紧迫度**：`{urgency}`"
        ]
        if is_held:
            lines.append(f"> **持仓浮盈**：`{result['profit_pct']:+.2f}%` | **最低税费保本价**：`¥{result['breakeven_price']:.2f}`")

        for idx, item in enumerate(result["action_items"], 1):
            title_txt = item.get('action') or item.get('title')
            diag_txt = item.get('reason') or item.get('diagnosis')
            lines.append(f"\n**{idx}. 核心动作**：`{title_txt}`")
            lines.append(f"- **量化依据 / 诊断**：{diag_txt}")
            for k, v in item.items():
                if k not in ("action", "title", "reason", "diagnosis", "downside_type"):
                    lines.append(f"- **{k}**：`{v}`")

        return "\n".join(lines)
