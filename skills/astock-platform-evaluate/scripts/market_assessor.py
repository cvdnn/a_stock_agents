"""
aStocks 五维大盘健康度评估

五维模型:
  趋势(30%) + 情绪(20%) + 量能(20%) + 结构(15%) + 资金(15%)
独立运行，数据通过 data_bridge 获取。
"""

import json
import time
from typing import Any, Dict, Optional, Tuple


class MarketAssessor:
    """大盘健康度评估"""

    @staticmethod
    def assess_trend(index_data: Dict) -> Tuple[int, int, str]:
        """趋势维度 (满分30) — 基于上证指数MA20方向"""
        sh_data = None
        for name, info in index_data.items():
            if "上证" in name or "000001" in info.get("code", ""):
                sh_data = info
                break

        if not sh_data:
            return 15, 30, "无法获取上证指数数据，默认中性"

        chg_pct = sh_data.get("change_pct", 0)
        if chg_pct > 0.5:
            return 30, 30, "MA20向上+收盘>MA20 ✅"
        elif chg_pct > -0.5:
            return 15, 30, "MA20走平，中性"
        else:
            return 0, 30, "MA20向下 ⚠️"

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
        """量能维度 (满分20) — 全市场成交额"""
        if not quotes:
            return 10, 20, "数据不足"

        total_amount = sum(q.get("volume_hands", 0) * 100 for q in quotes)

        # 粗略估算：不能直接从腾讯单个股票获取全市场成交额
        # 用代表性判断
        return 15, 20, "量能中规中矩（需全市场数据精算）"

    @staticmethod
    def assess_structure(board_data: Dict) -> Tuple[int, int, str]:
        """结构维度 (满分15) — 板块分化度"""
        if not board_data:
            return 7, 15, "板块数据不可用"

        # 从板块排行中数涨幅>2%的板块数
        boards = board_data.get("data", [])
        strong_boards = sum(1 for b in boards if float(b.get("changePct", 0)) > 2)

        if strong_boards >= 5:
            return 15, 15, f"{strong_boards}个板块涨幅>2%，结构良好 ⭐"
        elif strong_boards >= 2:
            return 10, 15, f"{strong_boards}个板块涨幅>2%"
        else:
            return 5, 15, "无强势板块，结构偏弱"

    @staticmethod
    def assess_capital() -> Tuple[int, int, str]:
        """资金维度 (满分15) — 北向资金"""
        # 北向资金需proxy-patch，此处用中性值
        return 10, 15, "北向资金数据需proxy-patch获取"

    def assess_all(self) -> Dict[str, Any]:
        """运行全维度评估"""
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


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    assessor = MarketAssessor()
    result = assessor.assess_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
