"""
aStocks 风险管理器 — P1 新建

三级止损 + 减仓规则 + 卖点信号 + 回撤控制

独立运行，依赖 technical_indicators。
"""

from typing import Any, Dict, List, Optional, Tuple


class RiskManager:
    """三级止损 + 卖点 + 回撤控制"""

    # ═══════════════════════════════════════════════════
    #  止损位计算
    # ═══════════════════════════════════════════════════

    @staticmethod
    def calc_stop_losses(entry_price: float, latest: Dict) -> Dict[str, Any]:
        """
        计算三级止损位

        T0: 日内止损 (入场价 -5%)
        T1: MA10 下方2% (减半仓)
        T2: MA20 下方2% (清仓)
        """
        ma10 = latest.get("ma10", entry_price * 0.95)
        ma20 = latest.get("ma20", entry_price * 0.92)
        atr = latest.get("atr", entry_price * 0.02)

        t0 = round(entry_price * 0.95, 2)
        t1 = round(ma10 * 0.98, 2)
        t2 = round(ma20 * 0.98, 2)

        return {
            "entry_price": entry_price,
            "t0_intraday": {
                "price": t0,
                "loss_pct": round((entry_price - t0) / entry_price * 100, 1),
                "action": "即时清仓",
                "trigger": "日内跌幅 > 5%",
            },
            "t1_ma10": {
                "price": t1,
                "loss_pct": round((entry_price - t1) / entry_price * 100, 1),
                "action": "减半仓",
                "trigger": f"收盘跌破MA10 ({ma10})",
            },
            "t2_ma20": {
                "price": t2,
                "loss_pct": round((entry_price - t2) / entry_price * 100, 1),
                "action": "清仓",
                "trigger": f"收盘跌破MA20 ({ma20})",
            },
            "atr": round(atr, 4),
            "ma10": round(ma10, 2),
            "ma20": round(ma20, 2),
        }

    # ═══════════════════════════════════════════════════
    #  卖点信号
    # ═══════════════════════════════════════════════════

    @staticmethod
    def sell_signals(klines: List[List], latest: Dict) -> Dict[str, Any]:
        """检测卖点信号"""
        if len(klines) < 26:
            return {"signals": [], "should_sell": False}

        close = latest.get("close", 0)
        ma10 = latest.get("ma10", 0)
        ma20 = latest.get("ma20", 0)
        dif = latest.get("dif", 0)
        dea = latest.get("dea", 0)
        macd_bar = latest.get("macd_bar", 0)

        # 判断MACD最近变化
        closes_seq = [float(k[2]) for k in klines]
        try:
            from core.indicators.technical_indicators import macd as calc_macd
        except ImportError:
            from technical_indicators import macd as calc_macd
        m = calc_macd(closes_seq)
        bars = m["bar"]

        signals = []

        # MACD死叉
        if dif < dea and macd_bar < 0:
            signals.append("🔴 MACD死叉 + 绿柱 → 清仓信号")

        # DIF跌破零轴
        if dif < 0:
            signals.append("🔴 DIF跌破零轴 → 清仓信号")

        # MACD红柱连续缩短
        if len(bars) >= 4:
            recent = bars[-4:]
            if all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1)):
                signals.append("🟠 MACD红柱连续3日缩短 → 减仓信号")

        # 顶背离提示
        if len(klines) >= 40:
            recent_highs = [float(k[3]) for k in klines[-30:]]
            max_price = max(recent_highs)
            max_price_dif = dif
            # 简化检测: 价格创新高但DIF未新高
            if close >= max_price * 0.95 and dif < max(dif for _ in [0]):
                signals.append("⚠️ 可能顶背离 → 减仓观察")

        # 股价跌破布林带中轨
        boll_mid = latest.get("boll_mid", 0)
        if boll_mid > 0 and close < boll_mid:
            signals.append("🟡 跌破布林带中轨 → 持仓观察")

        return {
            "signals": signals,
            "should_sell": len([s for s in signals if s.startswith("🔴")]) > 0,
            "should_reduce": len([s for s in signals if s.startswith("🟠")]) > 0,
            "should_watch": len([s for s in signals if s.startswith("🟡") or s.startswith("⚠️")]) > 0,
        }

    # ═══════════════════════════════════════════════════
    #  回撤控制
    # ═══════════════════════════════════════════════════

    @staticmethod
    def drawdown_control(current_value: float, peak_value: float, cost: float) -> Dict[str, Any]:
        """
        回撤控制分级

        Args:
            current_value: 当前市值
            peak_value: 最高市值
            cost: 成本
        """
        dd_from_peak = (current_value - peak_value) / peak_value * 100 if peak_value > 0 else 0
        pnl_pct = (current_value - cost) / cost * 100 if cost > 0 else 0

        if dd_from_peak <= -15:
            action = "清仓反思，暂停交易"
            level = "🔴"
        elif dd_from_peak <= -12:
            action = "减仓2/3，仅保留底仓"
            level = "🟠"
        elif dd_from_peak <= -8:
            action = "减仓1/2，严格风控"
            level = "🟠"
        elif dd_from_peak <= -5:
            action = "减仓1/3，检查逻辑是否变化"
            level = "🟡"
        else:
            action = "正常持有"
            level = "🟢"

        return {
            "current_value": round(current_value, 2),
            "peak_value": round(peak_value, 2),
            "cost": round(cost, 2),
            "drawdown_from_peak_pct": round(dd_from_peak, 2),
            "pnl_pct": round(pnl_pct, 2),
            "action": action,
            "level": level,
        }

    # ═══════════════════════════════════════════════════
    #  K线形态确认
    # ═══════════════════════════════════════════════════

    @staticmethod
    def candle_pattern(klines: List[List]) -> Dict[str, Any]:
        """最近3日K线形态解读"""
        if len(klines) < 3:
            return {"pattern": "数据不足"}

        recent = klines[-3:]
        patterns = []

        for i, k in enumerate(recent):
            o = float(k[1])
            c = float(k[2])
            h = float(k[3])
            l = float(k[4])
            v = float(k[5])
            body = abs(c - o)
            upper_shadow = h - max(o, c)
            lower_shadow = min(o, c) - l
            total_range = h - l

            desc = []
            # 十字星
            if total_range > 0 and body / total_range < 0.1:
                desc.append("十字星 (方向选择)")
            # 锤子线
            elif body > 0 and lower_shadow > body * 2 and upper_shadow < body * 0.5:
                if c > o:
                    desc.append("锤子线 (止跌信号)")
                else:
                    desc.append("倒锤子线")
            # 长阳/长阴
            elif body > total_range * 0.7:
                if c > o:
                    desc.append("长阳 (强势)")
                else:
                    desc.append("长阴 (弱势)")

            # 缩量/放量
            if i > 0:
                prev_v = float(recent[i - 1][5])
                vol_ratio = v / prev_v if prev_v > 0 else 1
                if vol_ratio < 0.5:
                    desc.append("极度缩量")
                elif vol_ratio > 2:
                    desc.append("异常放量")

            patterns.append({
                "date": k[0],
                "open": round(o, 2),
                "close": round(c, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "description": " | ".join(desc) if desc else "普通K线",
            })

        return {"recent_3d": patterns}


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="aStocks 风险管理")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--entry", type=float, help="入场价", default=0)
    parser.add_argument("--cost", type=float, help="持仓成本")
    parser.add_argument("--peak", type=float, help="最高市值", default=0)
    parser.add_argument("--current-value", type=float, help="当前市值", default=0)
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    from data_bridge import DataBridge
    from technical_indicators import calc_all

    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)

    if not klines or len(klines) < 26:
        print(json.dumps({"error": "K线数据不足"}, ensure_ascii=False))
        exit(1)

    tech = calc_all(klines)
    rm = RiskManager()

    result = {}
    entry_price = args.entry or float(klines[-1][2])

    result["stop_losses"] = rm.calc_stop_losses(entry_price, tech["latest"])
    result["sell_signals"] = rm.sell_signals(klines, tech["latest"])
    result["candle"] = rm.candle_pattern(klines)

    if args.cost and args.current_value:
        result["drawdown"] = rm.drawdown_control(
            args.current_value, args.peak or args.cost, args.cost)

    print(json.dumps(result, ensure_ascii=False, indent=2))
