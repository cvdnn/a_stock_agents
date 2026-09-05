"""
aStocks 三层漏斗选股流水线 — P1 新建

三层过滤:
  第一层: 板块级 — 从强势板块中找候选
  第二层: 技术面 — MA/MACD/量价硬条件
  第三层: 筹码+资金 — CYQ集中度+主力资金确认

独立运行，通过 data_bridge 获取数据。
"""

import json
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.models.combo_scorer import ComboScorer, entry_assessment
except ImportError:
    from data_bridge import DataBridge
    from technical_indicators import calc_all
    from combo_scorer import ComboScorer, entry_assessment


class StockScreener:
    """三层漏斗选股器"""

    def __init__(self):
        self.bridge = DataBridge()
        self.scorer = ComboScorer()

    # ═══════════════════════════════════════════════════
    #  第一层: 板块级筛选
    # ═══════════════════════════════════════════════════

    def filter_sector(self, codes: List[Any], min_board_chg: float = 0.5) -> List[Dict]:
        """
        从候选代码中筛出所属板块当日涨幅 > min_board_chg 的标的
        返回每只股票的板块信息
        """
        results = []
        # 批量获取行情 (若传入的本身为行情字典列表则直接复用)
        if codes and isinstance(codes[0], dict) and "code" in codes[0]:
            quotes = codes
        else:
            quotes = self.bridge.fetch_batch_snapshot(codes) if codes else []
        if not quotes:
            return results

        # 获取板块排行
        boards = self.bridge.get_board_summary(limit=30)
        board_data = boards.get("data", []) if boards else []

        # 构建板块名→涨跌幅映射及TOP10板块集合
        board_map = {}
        top10_board_names = set()
        for idx, b in enumerate(board_data):
            name = b.get("boardName", b.get("name", ""))
            try:
                chg = float(b.get("changePct", 0) or 0)
            except (ValueError, TypeError):
                chg = 0.0
            board_map[name] = chg
            if idx < 10 and name:
                top10_board_names.add(name)

        for q in quotes:
            code = q.get("code", "")
            name = q.get("name", "")

            # 获取行业信息 (优先直接从传入字典提取，其次调用 bridge)
            sector_name = q.get("sector", "")
            if not sector_name:
                sector = self.bridge.get_sector_info(code)
                if sector:
                    if isinstance(sector, dict):
                        sector_name = sector.get("industry", sector.get("sector", ""))
                    elif isinstance(sector, str):
                        sector_name = sector

            board_chg = board_map.get(sector_name, 0)
            passed = board_chg >= min_board_chg
            is_top10 = sector_name in top10_board_names

            results.append({
                "code": code,
                "name": name,
                "price": q.get("price", 0),
                "change_pct": q.get("change_pct", 0),
                "pe": q.get("pe", 0),
                "sector": sector_name,
                "board_chg": board_chg,
                "board_top10": is_top10,
                "passed_layer1": passed,
            })

        return results

    # ═══════════════════════════════════════════════════
    #  第二层: 技术面硬条件
    # ═══════════════════════════════════════════════════

    def filter_technical(self, candidates: List[Dict]) -> List[Dict]:
        """
        硬条件:
          1. MA5 > MA10 > MA20 (多头排列)
          2. 收盘价 > MA20
          3. 日均成交额 > 2亿
          4. 非ST/退市 (PE>0)
        """
        passed = []
        for c in candidates:
            code = c["code"]
            # 排除科创板/创业板/北交所
            if code.startswith(("688", "689", "30", "8", "4")):
                continue

            # 获取K线和技术指标
            klines = self.bridge.tencent_kline(code, 120)
            if not klines or len(klines) < 26:
                continue

            tech = calc_all(klines)
            latest = tech["latest"]

            close = latest.get("close", 0)
            ma5 = latest.get("ma5", 0)
            ma10 = latest.get("ma10", 0)
            ma20 = latest.get("ma20", 0)

            # 硬条件检查
            if not (ma5 > ma10 > ma20 > 0):
                continue
            if not (close > ma20):
                continue

            # 成交额检查 (>2亿)
            vols = [float(k[5]) for k in klines[-5:] if float(k[5]) > 0]
            avg_vol = sum(vols) / len(vols) if vols else 0
            avg_amount = avg_vol * close * 100  # 手→元
            if avg_amount < 2e8:
                continue

            # PE检查
            pe = c.get("pe", 0)
            if pe and pe < 0:  # 亏损ST
                continue

            c["klines"] = klines
            c["technical"] = latest
            c["avg_amount"] = avg_amount
            c["passed_layer2"] = True
            passed.append(c)

        return passed

    # ═══════════════════════════════════════════════════
    #  第三层: 策略评分 + 筹码/资金确认
    # ═══════════════════════════════════════════════════

    def filter_strategy(self, candidates: List[Dict], fetch_cyq: bool = True) -> List[Dict]:
        """
        对通过前两层筛选的标的进行策略评分和排序
        """
        results = []
        for c in candidates:
            klines = c.get("klines")
            tech_latest = c.get("technical")
            code = c["code"]

            if not klines:
                continue

            # 获取增强数据
            cyq_data = None
            fund_data = None
            pe_value = c.get("pe")

            if fetch_cyq:
                cyq_data = self.bridge.get_cyq(code)
            # fund_flow 太慢，批量跳过
            # pe 从腾讯行情已有

            # 评分
            scores = self.scorer.score_full(
                klines, tech_latest,
                board_chg=c.get("board_chg", 0),
                board_top10=c.get("board_top10", False),
                cyq_data=cyq_data,
                pe_value=pe_value,
            )

            # 入场判断
            entry = entry_assessment(klines, tech_latest)

            results.append({
                "code": code,
                "name": c["name"],
                "price": c.get("price", 0),
                "change_pct": c.get("change_pct", 0),
                "pe": pe_value,
                "sector": c.get("sector", ""),
                "board_chg": c.get("board_chg", 0),
                "avg_amount": c.get("avg_amount", 0),
                "scores": scores,
                "entry": entry,
            })

        # 按归一化百分制总分排序 (确保缺失cyq/fund的标的与完整标的尺度公平可比)
        results.sort(key=lambda x: x["scores"].get("normalized_score", x["scores"].get("total", 0)), reverse=True)
        return results

    # ═══════════════════════════════════════════════════
    #  完整流水线
    # ═══════════════════════════════════════════════════

    def screen(self, codes: List[str], fetch_cyq: bool = False) -> Dict[str, Any]:
        """
        三层漏斗完整流水线

        Args:
            codes: 股票代码列表
            fetch_cyq: 是否获取筹码分布(更慢但更全面)

        Returns:
            {
                stage1_count, stage2_count, stage3_count,
                results: [按评分排序的候选],
            }
        """
        # Layer 1: 板块
        layer1 = self.filter_sector(codes)
        l1_passed = [c for c in layer1 if c["passed_layer1"]]

        # Layer 2: 技术面
        layer2 = self.filter_technical(l1_passed)

        # Layer 3: 策略评分
        layer3 = self.filter_strategy(layer2, fetch_cyq=fetch_cyq)

        return {
            "total_input": len(codes),
            "stage1_board": len(l1_passed),
            "stage2_technical": len(layer2),
            "stage3_scored": len(layer3),
            "results": layer3,
        }


# ─── 便捷函数 ─────────────────────────────────────────

def quick_scan(codes: List[str]) -> List[Dict]:
    """快速扫描: 仅评级，不获取CYQ"""
    screener = StockScreener()
    result = screener.screen(codes, fetch_cyq=False)
    return result["results"]


def deep_scan(codes: List[str]) -> List[Dict]:
    """深度扫描: 含CYQ"""
    screener = StockScreener()
    result = screener.screen(codes, fetch_cyq=True)
    return result["results"]


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="aStocks 三层漏斗选股")
    parser.add_argument("codes", help="股票代码列表，逗号分隔")
    parser.add_argument("--cyq", action="store_true", help="获取筹码分布")
    parser.add_argument("--min-count", type=int, default=10, help="最少返回数量")
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    codes = [c.strip() for c in args.codes.split(",")]
    screener = StockScreener()
    result = screener.screen(codes, fetch_cyq=args.cyq)

    # 摘要
    print(f"输入: {result['total_input']} → 板块: {result['stage1_board']} "
          f"→ 技术: {result['stage2_technical']} → 评分: {result['stage3_scored']}")
    print()

    if result["results"]:
        print(f"{'代码':<8} {'名称':<10} {'评级':<4} {'总分':>5} {'现价':>7} {'涨跌%':>7} {'PE':>6}")
        for r in result["results"][:args.min_count]:
            s = r["scores"]
            print(f"{r['code']:<8} {r['name']:<10} {s['rating']:<4} "
                  f"{s['total']:>5}/{s['effective_max']:<3} "
                  f"{r['price']:>7.2f} {r['change_pct']:>+6.2f}% "
                  f"{r.get('pe',0) or 'N/A':>6}")
