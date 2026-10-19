#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
退哥短线战法量化检测与交易执行决策引擎
Tuige Shortline Strategy Engine:
1. 涨停基因识别 (Limit Up Gene)
2. 缩量回踩 MA5/MA10 支撑 (Limit Up Pullback)
3. 龙头首阴断板弱转强反包 (First Yin Reversal)
4. 连板分歧换手接力 (Continuous Board Relay)
5. 250 日同类信号历史胜率锚 (C4 标准)
6. 实战交易三原则强制内嵌 (C6 标准: 保本价进位/三级止损/三场景动作单)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.workspace import PROJECT_ROOT, RUNTIME_ROOT

try:
    from core.data.data_bridge import DataBridge
    from core.data.evidence import build_evidence_meta
    from core.models.strategy_evaluator import attach_contextual_win_rate_anchor
except ImportError:
    DataBridge = None
    build_evidence_meta = None
    attach_contextual_win_rate_anchor = None


class TuigeStrategyEngine:
    """退哥短线交易战法研判与决策引擎"""

    SCENARIO_PULLBACK = "limit_up_pullback"
    SCENARIO_FIRST_YIN = "first_yin_reversal"
    SCENARIO_RELAY = "continuous_board_relay"
    SCENARIO_BREAK_STOP = "break_ma_stop"

    SCENARIO_NAMES = {
        SCENARIO_PULLBACK: "涨停缩量回踩 MA5/MA10 企稳",
        SCENARIO_FIRST_YIN: "龙头首阴断板次日弱转强反包",
        SCENARIO_RELAY: "连板分歧换手接力",
        SCENARIO_BREAK_STOP: "破位清仓离场",
    }

    @staticmethod
    def calculate_breakeven_price(cost: float, shares: int = 100) -> float:
        """
        精确计算最低保本卖出价。
        严格按印花税 0.05%，佣金万2.5（最低5元起），过户费十万分之一核算。
        结果强制向上取整到分位 (math.ceil(p * 100) / 100)。
        """
        if cost <= 0 or shares <= 0:
            return 0.0

        buy_amount = cost * shares
        buy_comm = max(5.0, buy_amount * 0.00025)
        buy_transfer = buy_amount * 0.00001
        total_buy_cost = buy_amount + buy_comm + buy_transfer

        low = cost
        high = cost * 1.15
        for _ in range(60):
            mid = (low + high) / 2.0
            sell_amount = mid * shares
            sell_comm = max(5.0, sell_amount * 0.00025)
            sell_stamp = sell_amount * 0.0005
            sell_transfer = sell_amount * 0.00001
            net_proceeds = sell_amount - sell_comm - sell_stamp - sell_transfer
            if net_proceeds >= total_buy_cost:
                high = mid
            else:
                low = mid

        return math.ceil(high * 100.0) / 100.0

    @staticmethod
    def detect_limit_up_gene(klines: List[Any], lookback: int = 60) -> Dict[str, Any]:
        """识别标的涨停基因 (主板>=9.5%, 双创>=19.5%)"""
        if not klines or len(klines) < 2:
            return {"has_gene": False, "limit_up_count": 0, "days_since_last": -1, "max_consecutive": 0}

        sub = klines[-lookback:] if len(klines) >= lookback else klines
        limit_ups = []
        max_consecutive = 0
        current_consecutive = 0

        for i in range(1, len(sub)):
            prev_close = float(sub[i - 1][2])
            curr_close = float(sub[i][2])
            chg = (curr_close - prev_close) / prev_close if prev_close > 0 else 0.0
            # 主板或通常涨幅 >= 9.5% 视作涨停或冲击涨停
            is_lu = chg >= 0.095
            if is_lu:
                limit_ups.append(len(sub) - 1 - i)  # 距今天数
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0

        has_gene = len(limit_ups) >= 1
        days_since_last = limit_ups[-1] if limit_ups else -1
        return {
            "has_gene": has_gene,
            "limit_up_count": len(limit_ups),
            "days_since_last": days_since_last,
            "max_consecutive": max_consecutive,
        }

    @classmethod
    def evaluate(
        cls,
        code: str,
        cost: Optional[float] = None,
        shares: Optional[int] = None,
        count: int = 60,
        scenario: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        退哥短线综合诊断
        """
        bridge = DataBridge() if DataBridge else None
        quote = {}
        klines = []
        if bridge:
            try:
                quote = bridge.get_realtime_quote(code) or {}
                klines = bridge.tencent_kline(code, count=max(count, 60)) or []
            except Exception:
                pass

        if not klines or len(klines) < 20:
            evidence = (
                build_evidence_meta(quote_source="L1:tencent_kline", kline_bars_count=len(klines), watermark_ready=False)
                if build_evidence_meta
                else {}
            )
            return {
                "status": "error",
                "error": "DATA_UNAVAILABLE",
                "code": code,
                "message": f"股票 {code} K线数据不足 (需≥20根)，退哥短线判定已安全终止 (Fail-Closed)。",
                "evidence_meta": evidence,
            }

        name = quote.get("name", code)
        curr_price = float(quote.get("price", 0.0))
        if curr_price <= 0 and klines:
            curr_price = float(klines[-1][2])
        if cost is None or cost <= 0:
            cost = curr_price if curr_price > 0 else 10.0
        if shares is None or shares <= 0:
            shares = 1000

        # 计算均线
        closes = [float(k[2]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        lows = [float(k[4]) for k in klines]
        highs = [float(k[3]) for k in klines]
        opens = [float(k[1]) for k in klines]

        ma5 = sum(closes[-5:]) / 5.0
        ma10 = sum(closes[-10:]) / 10.0
        ma20 = sum(closes[-20:]) / 20.0
        ma60 = sum(closes[-60:]) / len(closes[-60:]) if len(closes) >= 60 else ma20

        # 涨停基因
        gene = cls.detect_limit_up_gene(klines, lookback=min(60, len(klines)))

        # 战法场景匹配逻辑
        matched_scenarios = []
        checklist = []
        verdict = "C"
        primary_scenario = scenario or cls.SCENARIO_PULLBACK

        # 1. 缩量回踩 MA5/MA10
        vol_curr = volumes[-1]
        vol_prev = volumes[-2] if len(volumes) >= 2 else vol_curr
        vol_shrink = vol_curr <= vol_prev * 0.85
        pullback_support = (lows[-1] >= ma10 * 0.98 and curr_price >= ma5 * 0.98) or (curr_price >= ma10 and closes[-1] >= opens[-1])
        if gene["has_gene"] and gene["days_since_last"] <= 8 and pullback_support:
            matched_scenarios.append(cls.SCENARIO_PULLBACK)
            checklist.append("✅ 近8日内具备涨停基因，处于强势股回调周期")
            if vol_shrink:
                checklist.append("✅ 回调日成交量显著萎缩 (缩量蓄势)")
            checklist.append("✅ 企稳于 MA5/MA10 关键均线支撑位之上")
            verdict = "A" if vol_shrink else "B"

        # 2. 龙头首阴断板反包
        prev_is_yin = len(closes) >= 2 and closes[-2] < opens[-2]
        prev_drop = (closes[-2] - closes[-3]) / closes[-3] if len(closes) >= 3 else 0.0
        curr_strong = (curr_price > opens[-1] and curr_price >= closes[-2])
        if gene["max_consecutive"] >= 2 and gene["days_since_last"] <= 3 and prev_is_yin and curr_strong:
            matched_scenarios.append(cls.SCENARIO_FIRST_YIN)
            checklist.append("✅ 标的前期经历连板强势拉升 (连板数≥2)")
            checklist.append("✅ 昨日首度断板收阴释放分歧")
            checklist.append("✅ 今日盘中弱转强反包翻红，承接意愿坚决")
            verdict = "A"

        # 3. 连板分歧接力
        curr_is_up = len(closes) >= 2 and closes[-1] >= closes[-2] * 1.05
        if gene["max_consecutive"] >= 2 and curr_is_up:
            matched_scenarios.append(cls.SCENARIO_RELAY)
            checklist.append("✅ 处于连板上升通道")
            verdict = "B"

        # 4. 破位警告
        if curr_price < ma10 * 0.96 or curr_price < ma20 * 0.95:
            matched_scenarios.append(cls.SCENARIO_BREAK_STOP)
            checklist.append("⚠️ 跌破 MA10/MA20 防守均线，短线逻辑破坏")
            if verdict == "A":
                verdict = "B"
            else:
                verdict = "D"

        if not checklist:
            checklist.append("○ 暂未触发退哥短线典型形态，维持中性观察")

        # 确定主场景
        if matched_scenarios:
            primary_scenario = matched_scenarios[0]

        # 实战交易三原则 (C6 标准)
        breakeven = cls.calculate_breakeven_price(cost, shares)
        stop_t0 = round(cost * 0.97, 2)
        stop_t1 = round(cost * 0.95, 2)
        stop_t2 = round(cost * 0.92, 2)

        action_items = {
            "rush_high": "开盘冲高 >3% 或触及上轨阻力：短线严格落袋部分浮盈，不盲目追高",
            "consolidation": "盘中窄幅震荡守住 MA5/MA10：持股待涨，分时破均线即离场",
            "plunge_low": f"盘中急跌击穿绝杀线 {stop_t2} (-8%)：坚决止损清仓，绝不心存侥幸",
        }

        # 250 日同类信号历史胜率锚 (C4 标准)
        win_rate_anchor = {}
        if attach_contextual_win_rate_anchor:
            try:
                win_rate_anchor = attach_contextual_win_rate_anchor(
                    code=code,
                    klines=klines,
                    signal_type="tuige",
                    lookback_days=250,
                    cost_bps=45.0,
                )
            except Exception:
                win_rate_anchor = {}

        evidence = (
            build_evidence_meta(
                quote_source="L1:tencent_kline",
                kline_bars_count=len(klines),
                watermark_ready=True,
            )
            if build_evidence_meta
            else {}
        )

        return {
            "status": "success",
            "code": code,
            "name": name,
            "current_price": curr_price,
            "cost": cost,
            "shares": shares,
            "verdict": verdict,
            "scenario": primary_scenario,
            "scenario_name": cls.SCENARIO_NAMES.get(primary_scenario, primary_scenario),
            "matched_scenarios": matched_scenarios,
            "checklist": checklist,
            "gene": gene,
            "ma_levels": {
                "ma5": round(ma5, 2),
                "ma10": round(ma10, 2),
                "ma20": round(ma20, 2),
                "ma60": round(ma60, 2),
            },
            # 实战三原则强制字段 (C6)
            "breakeven_price": breakeven,
            "stop_t0": stop_t0,
            "stop_t1": stop_t1,
            "stop_t2": stop_t2,
            "action_items": action_items,
            # 250 日胜率锚 (C4)
            "win_rate_anchor": win_rate_anchor,
            # 溯源信封 (C2)
            "evidence_meta": evidence,
        }

    @classmethod
    def render_markdown(cls, res: Dict[str, Any]) -> str:
        """渲染为终端或研报展示用的 Markdown 文本"""
        if res.get("status") != "success":
            return f"❌ 退哥短线诊断失败: {res.get('message', res.get('error'))}"

        anchor = res.get("win_rate_anchor", {})
        md = [
            f"# 退哥短线战法量化诊断: {res['name']} ({res['code']})",
            f"- **当前现价**: ¥{res['current_price']:.2f} | **参考成本**: ¥{res['cost']:.2f}",
            f"- **战法评级**: **【{res['verdict']} 级】** | **主匹配场景**: {res['scenario_name']}",
            "",
            "## 一、短线战法形态核验",
        ]
        for c in res.get("checklist", []):
            md.append(f"- {c}")

        gene = res.get("gene", {})
        md.extend([
            "",
            "## 二、涨停基因与均线态势",
            f"- **近60日涨停次数**: {gene.get('limit_up_count', 0)} 次 | **最长连板**: {gene.get('max_consecutive', 0)} 板",
            f"- **最近涨停距今**: {gene.get('days_since_last', -1)} 个交易日",
            f"- **关键均线**: MA5={res['ma_levels']['ma5']} | MA10={res['ma_levels']['ma10']} | MA20={res['ma_levels']['ma20']}",
            "",
            "## 三、250 日同类信号历史胜率锚 (C4 摩擦过滤)",
            f"- **样本回溯**: {anchor.get('sample_count', 0)} 次 | **T+5 胜率**: {anchor.get('win_rate_t5', 'N/A')}%",
            f"- **45bps 扣费胜率**: {anchor.get('win_rate_net_t5', 'N/A')}% | **盈亏比**: {anchor.get('profit_loss_ratio', 'N/A')}",
            f"- **胜率锚结论**: {anchor.get('cost_filtered_conclusion', '无')}",
            "",
            "## 四、实战交易三原则与风控阶梯 (C6 铁律)",
            f"- **最低保本卖出价 (math.ceil 向上进位)**: **¥{res['breakeven_price']:.2f}**",
            f"- **三级风控止损阶梯**:",
            f"  - T0 警戒线 (-3%): ¥{res['stop_t0']:.2f}",
            f"  - T1 减仓线 (-5%): ¥{res['stop_t1']:.2f} (建议减半防守)",
            f"  - T2 绝杀线 (-8%): ¥{res['stop_t2']:.2f} (无条件清仓止损)",
            f"- **三场景即时动作单**:",
            f"  - 冲高应对: {res['action_items']['rush_high']}",
            f"  - 震荡应对: {res['action_items']['consolidation']}",
            f"  - 急跌应对: {res['action_items']['plunge_low']}",
        ])
        return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="退哥短线战法量化研判与风控引擎")
    parser.add_argument("code", nargs="?", default="600519", help="6位A股股票代码")
    parser.add_argument("--code", dest="opt_code", help="股票代码")
    parser.add_argument("--cost", type=float, default=None, help="买入成本价")
    parser.add_argument("--shares", type=int, default=1000, help="持仓股数")
    parser.add_argument("--scenario", default=None, help="指定短线场景")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")

    args = parser.parse_args()
    code = args.opt_code or args.code

    result = TuigeStrategyEngine.evaluate(
        code=code,
        cost=args.cost,
        shares=args.shares,
        scenario=args.scenario,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(TuigeStrategyEngine.render_markdown(result))


if __name__ == "__main__":
    main()
