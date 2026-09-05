"""
aStocks 三合一组合策略评分引擎 (trading-combo)

100分制多维评分:
  均线结构(25) + MACD状态(20) + 量价关系(15) + 筹码集中度(15) + 资金流向(15) + 板块共振(5) + PE估值(5) = 100分

独立运行，不依赖 TACN/TradingAgents 项目。
"""

import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from core.config import (
    DEFAULT_MA_BUFFER_PCT,
    DEFAULT_STOP_LOSS_PCT,
    get_logger,
)

logger = get_logger("core.models.combo_scorer")


class ComboScorer:
    """三合一策略评分器"""

    @staticmethod
    def score_ma_structure(klines: Optional[List[List]] = None, latest: Optional[Dict] = None) -> Tuple[int, str]:
        """均线结构评分 (满分25)"""
        # 兼容 (klines, latest) 或仅传 (latest)
        if latest is None and isinstance(klines, dict):
            target = klines
        else:
            target = latest or {}

        ma5 = target.get("ma5", 0)
        ma10 = target.get("ma10", 0)
        ma20 = target.get("ma20", 0)
        ma60 = target.get("ma60", 0)
        close = target.get("close", 0)


        if all(v > 0 for v in [ma5, ma10, ma20, ma60]) and ma5 > ma10 > ma20 > ma60:
            if close > ma5:
                return 25, "完美多头排列，强势"
            return 22, "多头排列，价格略低于MA5"

        if ma5 > ma10 and close > ma20:
            return 18, "中期趋势向上，短期偏强"

        if close > ma20:
            return 12, "价格在MA20上方，方向尚可"

        if close > ma60:
            return 8, "长期均线上方，短期承压"

        return 3, "空头排列或数据不足"

    @staticmethod
    def score_macd(latest: Dict) -> Tuple[int, str]:
        """MACD 状态评分 (满分20)"""
        dif = latest.get("dif", 0)
        dea = latest.get("dea", 0)
        bar = latest.get("macd_bar", 0)

        if dif == 0 and dea == 0:
            return 10, "MACD数据不足，中性评分"

        if dif > 0 and dif > dea and bar > 0:
            return 20, "零轴上金叉+红柱放大 ⭐⭐⭐"
        if dif > 0 and dif > dea:
            return 16, "零轴上金叉中"
        if dif > 0:
            return 12, "零轴上但动能减弱"
        if dif > dea and dif < 0:
            return 8, "零轴下金叉（底部修复）"
        if dif < 0 and dif < dea:
            return 3, "零轴下死叉，空头强势"
        return 5, "MACD偏弱"

    @staticmethod
    def score_volume(klines: List[List], latest: Dict) -> Tuple[int, str]:
        """量价关系评分 (满分15) — 缩量回踩最佳"""
        close = latest.get("close", 0)
        ma20 = latest.get("ma20", 0)

        if len(klines) < 10:
            return 8, "数据不足"

        vols = [float(k[5]) for k in klines if float(k[5]) > 0]
        if len(vols) < 6:
            return 8, "成交量数据不足"

        latest_vol = vols[-1]
        avg_vol = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else latest_vol
        vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 1

        if ma20 > 0:
            pct_ma20 = abs(close - ma20) / ma20 * 100
        else:
            pct_ma20 = 100

        # 缩量回踩MA20 = 最佳信号
        if vol_ratio < 0.8 and close > ma20 and pct_ma20 < 3:
            return 15, f"缩量回踩MA20，量比{vol_ratio:.2f} ⭐⭐⭐"
        if vol_ratio < 0.9 and close > ma20 and pct_ma20 < 5:
            return 12, f"缩量靠近MA20，量比{vol_ratio:.2f}"
        if 0.8 <= vol_ratio < 1.2 and close > ma20:
            return 10, "量价正常"
        if vol_ratio > 1.5 and close < ma20:
            return 3, "放量下跌，风险信号"
        if vol_ratio > 2.0:
            return 5, "异常放量，需警惕"
        return 8, "量价中规中矩"

    @staticmethod
    def score_volume_short(klines: List[List], latest: Dict) -> Tuple[int, str]:
        """短线量价评分 (满分15) — 量比核心"""
        if len(klines) < 6:
            return 8, "数据不足"
        vols = [float(k[5]) for k in klines if float(k[5]) > 0]
        if len(vols) < 6:
            return 8, "数据不足"
        latest_vol = vols[-1]
        avg_vol = sum(vols[-6:-1]) / 5
        vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 1

        close = latest.get("close", 0)
        ma20 = latest.get("ma20", 0)
        pct_ma20 = abs(close - ma20) / ma20 * 100 if ma20 > 0 else 100

        if vol_ratio < 0.6 and close > ma20 and pct_ma20 < 3:
            return 15, f"极致缩量回踩MA20，短线最佳 {vol_ratio:.2f}"
        if vol_ratio < 0.8 and close > ma20:
            return 12, f"缩量+价格在均线上方 {vol_ratio:.2f}"
        if 0.8 <= vol_ratio <= 1.2:
            return 8, "量比正常"
        if vol_ratio > 1.5 and close < ma20:
            return 2, "放量下跌"
        return 7, "量价一般"

    @staticmethod
    def score_sector(board_chg: float, board_top10: bool) -> Tuple[int, str]:
        """板块共振评分 (满分10)"""
        if board_chg > 1 and board_top10:
            return 10, "板块强势，共振良好 ⭐"
        if board_chg > 0 and board_top10:
            return 8, "板块涨，共振偏强"
        if board_chg > -0.5 and board_top10:
            return 6, "板块平盘，共振中性"
        if board_top10:
            return 4, "板块在TOP10但偏弱"
        return 2, "板块不在TOP10或领跌"

    @staticmethod
    def score_cyq(cyq_data: Optional[Dict]) -> Tuple[int, str]:
        """筹码集中度评分 (满分15)"""
        if not cyq_data:
            return 8, "CYQ数据不可用，默认中性"
        conc_90 = float(cyq_data.get("concentration_90", 0.15))
        conc_70 = float(cyq_data.get("concentration_70", 0.15))
        profit_ratio = float(cyq_data.get("profit_ratio", 0.5))

        score = 8  # baseline
        reasons = []
        if conc_90 < 0.10:
            score += 4
            reasons.append("90%筹码高度集中")
        elif conc_90 < 0.13:
            score += 3
            reasons.append("90%筹码集中")
        elif conc_90 < 0.15:
            score += 1
            reasons.append("90%筹码中性")
        else:
            reasons.append("90%筹码发散")

        if 0.3 <= profit_ratio <= 0.6:
            score += 3
            reasons.append("获利比例健康(30-60%)")
        elif profit_ratio > 0.7:
            reasons.append("获利比例偏高(>70%)")
        else:
            reasons.append("获利比例低(<30%)")

        return min(score, 15), "; ".join(reasons)

    @staticmethod
    def score_fund_flow(fund_data: Optional[Any]) -> Tuple[int, str]:
        """资金流向评分 (满分15)"""
        if not fund_data:
            return 8, "资金流数据不可用，默认中性"

        inflow_yi = None

        # 1. 结构化 dict / list 处理
        if isinstance(fund_data, list) and fund_data:
            fund_data = fund_data[0]

        if isinstance(fund_data, dict):
            for k in ("main_net_inflow", "主力净流入", "主力净流入-净额", "net_inflow"):
                if k in fund_data:
                    v = fund_data[k]
                    if isinstance(v, (int, float)):
                        if abs(v) >= 1e7:
                            inflow_yi = v / 1e8
                        elif abs(v) >= 1e3:
                            inflow_yi = v / 1e4
                        else:
                            inflow_yi = float(v)
                        break
                    elif isinstance(v, str):
                        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(亿|万)?", v)
                        if m:
                            num = float(m.group(1))
                            unit = m.group(2)
                            inflow_yi = num if unit == "亿" else (num / 10000.0 if unit == "万" else num)
                            break

        # 2. 文本解析处理 (如 CLI 输出格式)
        if inflow_yi is None:
            text = str(fund_data)
            if "主力净流入" in text:
                try:
                    raw = text.split("主力净流入")[1].split()[0].strip(":： \t\"',")
                    m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(亿|万)?", raw)
                    if m:
                        num = float(m.group(1))
                        unit = m.group(2)
                        if unit == "亿":
                            inflow_yi = num
                        elif unit == "万":
                            inflow_yi = num / 10000.0
                        else:
                            inflow_yi = num if abs(num) < 100 else num / 10000.0
                except (ValueError, IndexError):
                    pass

        if inflow_yi is not None:
            if inflow_yi > 0.5:
                return 15, f"主力大幅净流入 ({inflow_yi:.2f}亿) ⭐⭐⭐"
            elif inflow_yi > 0:
                return 12, f"主力小幅净流入 ({inflow_yi:.2f}亿)"
            elif inflow_yi > -0.5:
                return 8, f"主力小幅净流出 ({inflow_yi:.2f}亿)"
            else:
                return 5, f"主力大幅净流出 ({inflow_yi:.2f}亿)"

        return 8, "资金流数据需解析，默认中性"

    @staticmethod
    def score_pe(pe_value: Optional[float], is_short: bool = False) -> Tuple[int, str]:
        """PE估值评分 (主要影响中线)"""
        if pe_value is None or pe_value <= 0:
            return 5, "PE数据不可用"
        if is_short:
            return 5, "短线忽略PE"
        if pe_value < 15:
            return 5, f"PE={pe_value:.0f} 可能低估"
        elif pe_value < 30:
            return 5, f"PE={pe_value:.0f} 合理"
        elif pe_value < 60:
            return 4, f"PE={pe_value:.0f} 偏高"
        elif pe_value < 100:
            return 3, f"PE={pe_value:.0f} 高估值"
        else:
            return 1, f"PE={pe_value:.0f} 极高估值 ⚠️"

    def score_full(self, klines: List[List], latest: Optional[Dict] = None,
                   board_chg: float = 0, board_top10: bool = False,
                   is_short: bool = False,
                   cyq_data: Optional[Dict] = None,
                   fund_data: Optional[Dict] = None,
                   pe_value: Optional[float] = None) -> Dict[str, Any]:
        """
        完整100分制综合评分

        新增维度: 筹码(15) + 资金流(15) + PE(5) → 补齐到100分
        """
        if latest is None:
            from . import technical_indicators as ti
            result = ti.calc_all(klines)
            latest = result["latest"]

        scores = {}

        # 均线结构 (25)
        ma_score, ma_reason = self.score_ma_structure(klines, latest)
        scores["ma_structure"] = {"score": ma_score, "max": 25, "reason": ma_reason}

        # MACD (20)
        macd_score, macd_reason = self.score_macd(latest)
        scores["macd"] = {"score": macd_score, "max": 20, "reason": macd_reason}

        # 量价 (15)
        if is_short:
            vol_score, vol_reason = self.score_volume_short(klines, latest)
        else:
            vol_score, vol_reason = self.score_volume(klines, latest)
        scores["volume"] = {"score": vol_score, "max": 15, "reason": vol_reason}

        # 筹码集中度 (15)
        cyq_score, cyq_reason = self.score_cyq(cyq_data)
        scores["cyq"] = {"score": cyq_score, "max": 15, "reason": cyq_reason}

        # 资金流向 (15)
        fund_score, fund_reason = self.score_fund_flow(fund_data)
        scores["fund_flow"] = {"score": fund_score, "max": 15, "reason": fund_reason}

        # 板块共振 (5) — 从10调整为5以容纳其他维度
        sector_score, sector_reason = self.score_sector(board_chg, board_top10)
        sector_score = min(sector_score, 5)
        scores["sector"] = {"score": sector_score, "max": 5, "reason": sector_reason}

        # PE估值 (5)
        pe_score, pe_reason = self.score_pe(pe_value, is_short)
        scores["pe"] = {"score": pe_score, "max": 5, "reason": pe_reason}

        total = ma_score + macd_score + vol_score + cyq_score + fund_score + sector_score + pe_score
        scores["total"] = total
        scores["max_total"] = 100

        # 数据可用性标记
        scores["data_availability"] = {
            "cyq": cyq_data is not None,
            "fund_flow": fund_data is not None,
            "pe": pe_value is not None,
            "scored_without_cyq_fund": (cyq_data is None and fund_data is None),
        }

        # 动态有效满分与剔除缺失项的中性分
        effective_max = 100
        adjusted_total = total

        if cyq_data is None:
            effective_max -= 15
            adjusted_total -= cyq_score
        if fund_data is None:
            effective_max -= 15
            adjusted_total -= fund_score

        # 归一化为百分制得分
        normalized_score = round(adjusted_total / effective_max * 100, 1) if effective_max > 0 else float(total)

        # 评级 (基于有效满分归一化)
        ratio = adjusted_total / effective_max if effective_max > 0 else 0.0
        if ratio >= 0.80:
            rating, rating_text, position = "A", "强烈推荐 ⭐⭐⭐⭐", "30-40%"
        elif ratio >= 0.70:
            rating, rating_text, position = "B", "推荐 ⭐⭐⭐", "15-25%"
        elif ratio >= 0.50:
            rating, rating_text, position = "C", "观望 ⭐⭐", "仅观察"
        else:
            rating, rating_text, position = "D", "回避 ⭐", "放弃"

        scores["effective_max"] = effective_max
        scores["adjusted_total"] = adjusted_total
        scores["normalized_score"] = normalized_score
        scores["rating"] = rating
        scores["rating_text"] = rating_text
        scores["suggested_position"] = position

        return scores


# ═══════════════════════════════════════════════════
#  入场时机判断
# ═══════════════════════════════════════════════════

def entry_assessment(klines: List[List], latest: Dict) -> Dict[str, Any]:
    """入场时机判断"""
    close = latest.get("close", 0)
    ma20 = latest.get("ma20", 0)
    ma10 = latest.get("ma10", 0)
    dif = latest.get("dif", 0)
    dea = latest.get("dea", 0)
    macd_bar = latest.get("macd_bar", 0)
    atr = latest.get("atr", 0)

    if ma20 == 0:
        return {"entry_ok": False, "reason": "MA20数据缺失"}

    pct_ma20 = (close - ma20) / ma20 * 100 if ma20 > 0 else 100

    # 距离MA20的百分比决定优先级
    if abs(pct_ma20) < 1:
        distance_tier = "first"
        distance_text = "第一档：今日可关注，回踩充分"
    elif abs(pct_ma20) < 3:
        distance_tier = "second"
        distance_text = "第二档：等待1~2日候低"
    elif abs(pct_ma20) < 5:
        distance_tier = "third"
        distance_text = "第三档：距均线较远，需等待回调"
    else:
        distance_tier = "far"
        distance_text = "距MA20 > 5%，盈亏比可能不佳"

    # 入场形态判断
    trigger = []
    if dif > 0 and dif > dea and macd_bar > 0:
        trigger.append("MACD零轴上金叉 ✅")
    if dif > dea and dif < 0:
        trigger.append("零轴下金叉（底部修复中）⚠️")
    if close > ma20:
        trigger.append(f"价格站上MA20 ({pct_ma20:+.1f}%) ✅")

    # 止损位 (结合 MA20 趋势防守位与入场硬止损位)
    stop_loss_b = round(close * (1 - DEFAULT_STOP_LOSS_PCT), 2)  # 入场价-5%
    if ma20 > 0:
        stop_loss_a = round(ma20 * (1 - DEFAULT_MA_BUFFER_PCT), 2)  # MA20下方2%
        stop_loss = stop_loss_a
    else:
        stop_loss = stop_loss_b

    return {
        "pct_from_ma20": round(pct_ma20, 2),
        "distance_tier": distance_tier,
        "distance_text": distance_text,
        "triggers": trigger,
        "stop_loss": stop_loss,
        "stop_loss_ma20": stop_loss_a if ma20 > 0 else None,
        "stop_loss_fixed": stop_loss_b,
        "stop_loss_pct": round((close - stop_loss) / close * 100, 2) if close > 0 else 0,
        "atr": round(atr, 4),
    }



# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    from pathlib import Path

    # 直接运行脚本时，将项目根目录加入 sys.path，保证 `core` 包可导入
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

    parser = argparse.ArgumentParser(description="aStocks 策略评分")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--klines-file", help="K线JSON文件路径")
    parser.add_argument("--count", type=int, default=120, help="K线数量")
    parser.add_argument("--board-chg", type=float, default=0, help="板块涨跌幅")
    parser.add_argument("--board-top10", action="store_true", help="板块是否在TOP10")
    parser.add_argument("--short", action="store_true", help="短线模式")
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    # 获取K线数据
    if args.klines_file:
        klines = json.loads(Path(args.klines_file).read_text(encoding="utf-8"))
    else:
        from core.data.data_bridge import DataBridge
        klines = DataBridge.tencent_kline(args.code, args.count)

    if not klines or len(klines) < 26:
        print(json.dumps({"error": "K线数据不足（至少需要26根）"}, ensure_ascii=False))
        sys.exit(1)

    # 计算技术指标
    from core.indicators.technical_indicators import calc_all
    tech = calc_all(klines)

    # 评分
    scorer = ComboScorer()
    scores = scorer.score_full(klines, tech["latest"], args.board_chg, args.board_top10, args.short)

    # 入场判断
    entry = entry_assessment(klines, tech["latest"])

    output = {
        "code": args.code,
        "scores": scores,
        "entry": entry,
        "technical_latest": tech["latest"],
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
