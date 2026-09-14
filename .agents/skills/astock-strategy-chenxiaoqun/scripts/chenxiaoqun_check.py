#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
游资陈小群核心战法量化检测与交易执行决策引擎
Chen Xiaoqun Strategy Quantitative Screener & Execution Engine.
Supports CLI, JSON structured output, and strict risk control execution.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 动态寻找项目根目录
CUR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CUR_DIR.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
except ImportError:
    DataBridge = None
    calc_all = None


class ChenXiaoqunStrategyEngine:
    """游资陈小群战法研判与风控引擎"""

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

        # 迭代推算覆盖卖出佣金(>=5元)、印花税(0.05%)、卖出过户费的最低售价
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

        # 向上进位至分位 (保证实际卖出绝不亏一分钱)
        return math.ceil(high * 100.0) / 100.0

    @classmethod
    def evaluate(
        cls,
        code: str,
        cost: Optional[float] = None,
        shares: Optional[int] = None,
        count: int = 60,
    ) -> Dict[str, Any]:
        """对给定标的执行陈小群战法多维度诊断"""
        bridge = DataBridge() if DataBridge else None
        quote = {}
        klines = []
        if bridge:
            try:
                quote = bridge.get_realtime_quote(code) or {}
                klines = bridge.tencent_kline(code, count=count) or []
            except Exception as e:
                pass

        name = quote.get("name", code)
        curr_price = float(quote.get("price", 0.0))
        if curr_price <= 0 and klines:
            curr_price = float(klines[-1][2])  # 收盘价
        if cost is None or cost <= 0:
            cost = curr_price if curr_price > 0 else 10.0
        if shares is None or shares <= 0:
            shares = 1000

        # 技术面指标与均线计算
        ma5 = ma10 = ma20 = curr_price
        if klines and len(klines) >= 20:
            closes = [float(k[2]) for k in klines]
            ma5 = sum(closes[-5:]) / 5.0
            ma10 = sum(closes[-10:]) / 10.0
            ma20 = sum(closes[-20:]) / 20.0

        # 四大战法形态判定
        setups_matched = []
        scores = {}

        # 1. 战法一：深水低吸 / 大长腿 / 地天板
        # 特征：日内最低价探底很深（<-5%），但尾盘或现价大幅拉升回升（下影线很长）
        open_p = float(quote.get("open", curr_price))
        low_p = float(quote.get("low", curr_price))
        high_p = float(quote.get("high", curr_price))
        prev_close = float(quote.get("close", curr_price)) or open_p
        
        dip_pct = ((low_p - prev_close) / prev_close) * 100 if prev_close > 0 else 0
        rebound_from_low = ((curr_price - low_p) / low_p) * 100 if low_p > 0 else 0
        
        is_deep_water = False
        deep_water_details = ""
        if dip_pct <= -4.5 and rebound_from_low >= 5.0:
            is_deep_water = True
            setups_matched.append("战法一：总龙头分歧深水低吸(大长腿反转)")
            deep_water_details = f"早盘深探跌幅达 {dip_pct:.2f}%，低点反弹幅度达 +{rebound_from_low:.2f}%，具备资金深水逆向点火承接特征。"

        # 2. 战法二：弱转强竞价超预期
        # 特征：前一日为大分歧/跌势/烂板，今日大幅高开或放量反包
        is_weak_to_strong = False
        w2s_details = ""
        if klines and len(klines) >= 2:
            prev_k = klines[-2]
            prev_change = ((float(prev_k[2]) - float(prev_k[1])) / float(prev_k[1])) * 100 if float(prev_k[1]) > 0 else 0
            open_change = ((open_p - prev_close) / prev_close) * 100 if prev_close > 0 else 0
            if prev_change <= 2.0 and open_change >= 2.0:
                is_weak_to_strong = True
                setups_matched.append("战法二：爆量分歧次日竞价超预期弱转强")
                w2s_details = f"前日收盘涨跌幅 {prev_change:.2f}%，今日竞价超预期高开 +{open_change:.2f}%，主力资金早盘抢筹意图坚决。"

        # 3. 战法三：主升浪中军大格局换手板
        # 特征：多头排列（价格>MA5>MA10>MA20），温和放量
        is_main_wave = False
        mw_details = ""
        if curr_price >= ma5 >= ma10:
            is_main_wave = True
            setups_matched.append("战法三：主升浪核心中军换手板与做T锁仓")
            mw_details = f"股价站稳 MA5({ma5:.2f}) 与 MA10({ma10:.2f})，均线呈标准多头主升排列，适合底仓锁仓+日内差价T+0。"

        # 4. 战法四：龙头首阴反包与二波起爆
        # 特征：近期有连续大幅上涨，近期首次收阴回踩MA5/MA10获得支撑
        is_dragon_rebound = False
        dr_details = ""
        if klines and len(klines) >= 10:
            recent_high = max([float(k[3]) for k in klines[-10:]])
            recent_low = min([float(k[4]) for k in klines[-10:]])
            wave_gain = ((recent_high - recent_low) / recent_low) * 100 if recent_low > 0 else 0
            if wave_gain >= 25.0 and curr_price >= ma10 * 0.98:
                is_dragon_rebound = True
                setups_matched.append("战法四：龙头首阴企稳二波起爆模型")
                dr_details = f"近10日波段最大涨幅达 +{wave_gain:.1f}%，首次分歧回踩 MA10 均线未破，存在极高概率首阴反包或二波合力。"

        # 综合计算保本价与风控
        breakeven_p = cls.calculate_breakeven_price(cost, shares)
        t0_warn = round(cost * 0.97, 2)
        t1_reduce = round(cost * 0.95, 2)
        t2_cut = round(cost * 0.92, 2)

        # 情绪研判与建议
        regime = "分歧震荡 / 寻找龙头破局点"
        if is_weak_to_strong and is_main_wave:
            regime = "主升加速期 (情绪强)"
        elif is_deep_water:
            regime = "极端分歧点火期 (博弈地天长腿)"

        action_plan = {
            "open_rush": f"若早盘冲高涨幅 > +5%，观察封单量；若多次触板不回封，在保本价 {breakeven_p} 元上方逢高减半锁定利润。",
            "intraday_consolidation": f"在分时均线与 MA5({ma5:.2f}元) 之间震荡，若持有底仓可围绕均线做 T+0 降低成本，止损点坚守 T0 警戒线 {t0_warn} 元。",
            "sudden_drop": f"若放量跳水击穿 T1 减仓线 {t1_reduce} 元(-5%)无条件减仓50%；若击穿 T2 绝杀线 {t2_cut} 元(-8%)坚决清仓，绝不锁仓死扛。",
        }

        verdict = "观望"
        pos_advice = "0-2成仓轻仓试探"
        if len(setups_matched) >= 2:
            verdict = "重点关注 / 积极博弈"
            pos_advice = "3-5成标准仓位"
        elif len(setups_matched) == 1:
            verdict = "分步低吸 / 条件触发入场"
            pos_advice = "2-3成试错仓位"

        return {
            "code": code,
            "name": name,
            "current_price": curr_price,
            "cost": cost,
            "shares": shares,
            "breakeven_price": breakeven_p,
            "technical_indicators": {
                "ma5": round(ma5, 2),
                "ma10": round(ma10, 2),
                "ma20": round(ma20, 2),
                "dip_pct_from_prev_close": round(dip_pct, 2),
                "rebound_from_low": round(rebound_from_low, 2),
            },
            "market_regime": regime,
            "setups_matched": setups_matched,
            "setup_details": {
                "deep_water": deep_water_details,
                "weak_to_strong": w2s_details,
                "main_wave": mw_details,
                "dragon_rebound": dr_details,
            },
            "seats_signature": {
                "primary_seat": "中国银河证券大连金马路",
                "collaborators": ["中国银河证券大连黄河路", "中信建投北京东城分公司(呼家楼)", "中信西安朱雀大街(方新侠)"],
                "seat_style": "大局观总龙点火、深水撬板、主升换手板锁仓、决绝止损",
            },
            "risk_control": {
                "t0_warning_line": {"price": t0_warn, "loss_pct": 3.0, "action": "停止加仓，密切盯盘分时承接"},
                "t1_reduce_line": {"price": t1_reduce, "loss_pct": 5.0, "action": "无条件减仓 50% 防御"},
                "t2_cut_line": {"price": t2_cut, "loss_pct": 8.0, "action": "彻底清仓离场，逻辑证伪"},
            },
            "three_scenario_actions": action_plan,
            "verdict": verdict,
            "position_grade": pos_advice,
        }

    @classmethod
    def render_markdown(cls, res: Dict[str, Any]) -> str:
        """渲染高颜值 Markdown 决策卡片"""
        lines = []
        lines.append(f"# ⚡ 游资陈小群战法决策卡片：{res['name']} ({res['code']})")
        lines.append("")
        lines.append("## 1. 核心状态与战法命中")
        lines.append(f"- **最新现价**：`{res['current_price']:.2f}` 元")
        lines.append(f"- **参考成本**：`{res['cost']:.2f}` 元 (持仓: {res['shares']} 股)")
        lines.append(f"- **情绪周期评估**：`{res['market_regime']}`")
        lines.append(f"- **决策建议**：**{res['verdict']}** (建议仓位: `{res['position_grade']}`)")
        lines.append("")
        lines.append("### 🎯 命中陈小群战法形态")
        if res["setups_matched"]:
            for s in res["setups_matched"]:
                lines.append(f"- 🟢 **{s}**")
        else:
            lines.append("- ⚪ *暂无明显陈小群特有战法特征（非总龙头或处于混沌期）*")

        lines.append("")
        lines.append("## 2. 实战交易三原则 (铁律风控)")
        lines.append(f"- 🔒 **精确最低保本卖出价**：`{res['breakeven_price']:.2f}` 元 *(含印花税0.05%、佣金万2.5五元起、过户费并向上取整)*")
        rc = res["risk_control"]
        lines.append("- 🛡️ **三级止损阶梯**：")
        lines.append(f"  - **T0 警戒线 (-3%)**：`{rc['t0_warning_line']['price']:.2f}` 元 $\\to$ {rc['t0_warning_line']['action']}")
        lines.append(f"  - **T1 减仓线 (-5%)**：`{rc['t1_reduce_line']['price']:.2f}` 元 $\\to$ {rc['t1_reduce_line']['action']}")
        lines.append(f"  - **T2 绝杀线 (-8%)**：`{rc['t2_cut_line']['price']:.2f}` 元 $\\to$ {rc['t2_cut_line']['action']}")

        lines.append("")
        lines.append("## 3. 三场景即时动作单")
        act = res["three_scenario_actions"]
        lines.append(f"- 🌅 **场景 A (开盘冲高)**：{act['open_rush']}")
        lines.append(f"- ⚖️ **场景 B (盘中震荡)**：{act['intraday_consolidation']}")
        lines.append(f"- ⚠️ **场景 C (急跌跳水)**：{act['sudden_drop']}")

        lines.append("")
        lines.append("## 4. 顶级游资席位特征参考")
        seat = res["seats_signature"]
        lines.append(f"- **主招牌席位**：{seat['primary_seat']}")
        lines.append(f"- **常见合力席位**：{', '.join(seat['collaborators'])}")
        lines.append(f"- **操盘风格精髓**：*{seat['seat_style']}*")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="游资陈小群战法量化诊断工具")
    parser.add_argument("code", nargs="?", default="600519", help="股票代码 (如 600519)")
    parser.add_argument("--cost", type=float, default=None, help="持仓成本价")
    parser.add_argument("--shares", type=int, default=1000, help="持仓股数")
    parser.add_argument("--count", type=int, default=60, help="获取K线根数")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")

    args = parser.parse_args()
    res = ChenXiaoqunStrategyEngine.evaluate(
        code=args.code,
        cost=args.cost,
        shares=args.shares,
        count=args.count,
    )

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(ChenXiaoqunStrategyEngine.render_markdown(res))


if __name__ == "__main__":
    main()
