# -*- coding: utf-8 -*-
"""
aStocks 五维大盘健康度评估模型

五维模型:
  趋势(30%) + 情绪(20%) + 量能(20%) + 结构(15%) + 资金(15%)
独立运行，数据通过 DataBridge 获取。
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple


class MarketAssessor:
    """大盘健康度评估"""

    @staticmethod
    def assess_trend(index_data: Dict, klines: Optional[List[List]] = None) -> Tuple[int, int, str]:
        """趋势维度 (满分30) — 基于上证指数MA20与短线方向"""
        sh_data = None
        for name, info in index_data.items():
            code = str(info.get("code", "")).lower()
            stock_name = str(info.get("name", ""))
            key = str(name).lower()
            is_sh_name = "上证" in name or "上证" in stock_name
            is_sh_code = any(
                c in ("sh000001", "000001.sh", "000001.ss") or (c.startswith("sh") and "000001" in c)
                for c in (code, key)
            )
            if is_sh_name or is_sh_code:
                sh_data = info
                break

        if not sh_data:
            return 15, 30, "无法获取上证指数数据，默认中性"

        chg_pct = sh_data.get("change_pct", 0)

        # 若传入K线，精确计算 MA20 趋势
        if klines and len(klines) >= 20:
            closes = [float(k[2]) for k in klines]
            ma20 = sum(closes[-20:]) / 20.0
            prev_ma20 = sum(closes[-21:-1]) / 20.0 if len(closes) >= 21 else ma20
            latest_close = closes[-1]
            if latest_close > ma20 and ma20 >= prev_ma20:
                return 30, 30, "MA20向上+收盘>MA20 ✅"
            elif latest_close < ma20 and ma20 < prev_ma20:
                return 0, 30, "MA20向下+收盘<MA20 ⚠️"
            else:
                return 15, 30, "MA20走平或震荡，中性"

        # 降级：基于上证指数短线涨跌幅
        if chg_pct > 0.5:
            return 30, 30, "上证涨幅>0.5%，短线趋势偏强 ✅"
        elif chg_pct > -0.5:
            return 15, 30, "上证涨跌在[-0.5%, 0.5%]，震荡走平"
        else:
            return 0, 30, "上证跌幅<-0.5%，短线趋势偏弱 ⚠️"

    @staticmethod
    def assess_sentiment(quotes: list) -> Tuple[int, int, str]:
        """情绪维度 (满分20) — 涨跌比"""
        if not quotes:
            return 10, 20, "数据不足"

        up_count = sum(1 for q in quotes if q.get("change_pct", 0) > 0)
        down_count = sum(1 for q in quotes if q.get("change_pct", 0) < 0)

        total = up_count + down_count
        if total == 0:
            return 10, 20, "数据不足"

        ratio = up_count / total if total > 0 else 0.5

        if ratio > 0.8:
            return 20, 20, f"涨跌比 {ratio:.2f} > 0.8，情绪健康"
        elif ratio > 0.5:
            return 15, 20, f"涨跌比 {ratio:.2f}，情绪正常"
        elif ratio > 0.3:
            return 10, 20, f"涨跌比 {ratio:.2f}，情绪偏弱"
        else:
            return 5, 20, f"涨跌比 {ratio:.2f} < 0.3，恐慌 ⚠️"

    @staticmethod
    def assess_volume(quotes: list) -> Tuple[int, int, str]:
        """量能维度 (满分20) — 全市场/核心指数成交额评估"""
        if not quotes:
            return 10, 20, "量能数据不足，默认中性"

        total_amount = 0.0
        for q in quotes:
            amt = q.get("amount", 0) or (q.get("amount_wan", 0) * 10000)
            if amt:
                total_amount += float(amt)

        # 换算为亿元
        total_amount_yi = total_amount / 1e8 if total_amount > 1e6 else total_amount / 1e4

        if total_amount_yi > 0:
            if total_amount_yi >= 10000:
                return 20, 20, f"成交额约{total_amount_yi:.0f}亿 (破万亿)，量能充沛 ⭐"
            elif total_amount_yi >= 8000:
                return 15, 20, f"成交额约{total_amount_yi:.0f}亿 (超8000亿)，量能温和"
            elif total_amount_yi >= 6000:
                return 10, 20, f"成交额约{total_amount_yi:.0f}亿，存量博弈偏弱"
            else:
                return 5, 20, f"成交额约{total_amount_yi:.0f}亿 (<6000亿)，地量萎缩 ⚠️"

        return 12, 20, "量能数据不足，取中性基准 (降级)"

    @staticmethod
    def assess_structure(board_data: Dict) -> Tuple[int, int, str]:
        """结构维度 (满分15) — 板块分化度"""
        if not board_data:
            return 7, 15, "板块数据不可用"

        # 从板块排行中数涨幅>2%的板块数
        boards = board_data.get("data", [])
        strong_boards = 0
        for b in boards:
            try:
                chg = float(b.get("changePct", 0) or 0)
                if chg > 2.0:
                    strong_boards += 1
            except (ValueError, TypeError):
                continue

        if strong_boards >= 5:
            return 15, 15, f"{strong_boards}个板块涨幅>2%，结构良好 ⭐"
        elif strong_boards >= 2:
            return 10, 15, f"{strong_boards}个板块涨幅>2%"
        else:
            return 5, 15, "无强势板块，结构偏弱"

    @staticmethod
    def assess_capital(capital_data: Optional[Dict] = None) -> Tuple[int, int, str]:
        """资金维度 (满分15) — 北向与主力资金流向"""
        if capital_data and isinstance(capital_data, dict):
            net_inflow = capital_data.get("net_inflow")
            if net_inflow is None:
                net_inflow = capital_data.get("净流入(亿)", capital_data.get("净买额(亿)"))
            if net_inflow is not None:
                try:
                    val = float(net_inflow)
                    if val > 30:
                        return 15, 15, f"资金大幅净流入 ({val:.1f}亿) ⭐"
                    elif val > 0:
                        return 12, 15, f"资金温和净流入 ({val:.1f}亿)"
                    elif val > -30:
                        return 8, 15, f"资金小幅净流出 ({val:.1f}亿)"
                    else:
                        return 4, 15, f"资金大幅净流出 ({val:.1f}亿) ⚠️"
                except (ValueError, TypeError):
                    pass

        return 8, 15, "无实时资金流数据，取中性基准 (降级)"

    def assess_all(self) -> Dict[str, Any]:
        """运行全维度评估"""
        try:
            from core.data.data_bridge import DataBridge
        except ImportError:
            from data_bridge import DataBridge
        bridge = DataBridge()

        # 获取大盘指数
        index_data = bridge.tencent_index()

        # 评估各维度
        trend_score, trend_max, trend_reason = self.assess_trend(index_data)
        sentiment_score, sentiment_max, sentiment_reason = self.assess_sentiment(list(index_data.values()))
        volume_score, volume_max, volume_reason = self.assess_volume(list(index_data.values()))

        # 板块数据（可能不可用）
        board_data = bridge.get_board_summary()
        structure_score, structure_max, structure_reason = self.assess_structure(board_data)
        capital_score, capital_max, capital_reason = self.assess_capital()

        total = trend_score + sentiment_score + volume_score + structure_score + capital_score
        max_total = trend_max + sentiment_max + volume_max + structure_max + capital_max

        # 市场模式
        if total >= 85:
            mode = "强牛市"
            max_position = "80%"
        elif total >= 65:
            mode = "结构性行情"
            max_position = "60%"
        elif total >= 45:
            mode = "弱势震荡"
            max_position = "50%"
        elif total >= 30:
            mode = "偏弱"
            max_position = "30%"
        else:
            mode = "系统性下跌"
            max_position = "空仓或<20%"

        return {
            "total_score": total,
            "max_score": max_total,
            "mode": mode,
            "max_position": max_position,
            "dimensions": {
                "trend": {"score": trend_score, "max": trend_max, "reason": trend_reason},
                "sentiment": {"score": sentiment_score, "max": sentiment_max, "reason": sentiment_reason},
                "volume": {"score": volume_score, "max": volume_max, "reason": volume_reason},
                "structure": {"score": structure_score, "max": structure_max, "reason": structure_reason},
                "capital": {"score": capital_score, "max": capital_max, "reason": capital_reason},
            },
            "index_data": {k: {"name": v.get("name"), "price": v.get("price"), "change_pct": v.get("change_pct")}
                           for k, v in index_data.items()},
        }


__all__ = ["MarketAssessor"]


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    assessor = MarketAssessor()
    result = assessor.assess_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
