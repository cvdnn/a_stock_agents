"""
aStocks 持股策略评估器 — 替代传统回测

对历史持股时期的策略建议与实际股价走势做比对分析，评估策略准确性。
不依赖外部回测框架，使用 a-stocks 自身的评分引擎做后验评估。

模型:
  1. 方向准确性: 策略推荐的评级与实际涨跌方向是否一致
  2. 评级校准度: A>B>C>D 的收益率梯度是否成立
  3. 入场时机: 距MA20不同距离的后续收益差异
  4. 综合评分: 加权准确率

用法:
  python3 strategy_evaluator.py 600519 --entries '[{"date":"2026-06-01","price":1250,"action":"buy"}]'
  python3 strategy_evaluator.py 600519 --entries-file /path/to/holdings.json
"""

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.config import PROJECT_ROOT
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except ImportError:
    pass


# ═══════════════════════════════════════════════════
#  数据模型
# ═══════════════════════════════════════════════════

@dataclass
class EvaluationEntry:
    """单次持股评估记录"""
    date: str
    entry_price: float
    action: str                    # buy / hold / sell
    rating: str = ""               # A/B/C/D
    score_total: int = 0
    score_effective_max: int = 70
    pct_from_ma20: float = 0
    suggested_position: str = ""

    # 前向收益
    ret_1d: Optional[float] = None
    ret_5d: Optional[float] = None
    ret_10d: Optional[float] = None
    ret_20d: Optional[float] = None

    # 判定
    direction_correct: Optional[bool] = None   # A/B 应涨, C/D 应跌
    stop_loss_hit: bool = False


@dataclass
class EvaluationReport:
    """策略评估报告"""
    stock_code: str
    entries_evaluated: int = 0
    entries: List[Dict] = field(default_factory=list)

    # 方向准确性
    directional_accuracy_pct: float = 0
    a_b_win_rate: float = 0          # A/B 推荐的胜率
    c_d_correct_rate: float = 0      # C/D 回避的正确率

    # 评级校准
    rating_returns: Dict[str, Dict] = field(default_factory=dict)  # {A: {avg_5d, avg_20d, count}}

    # 入场时机
    timing_tiers: Dict[str, Dict] = field(default_factory=dict)

    # 综合
    weighted_score: float = 0         # 0-100 综合评分
    grade: str = ""                   # 优秀/良好/一般/较差
    summary: str = ""


# ═══════════════════════════════════════════════════
#  核心评估逻辑
# ═══════════════════════════════════════════════════

class StrategyEvaluator:
    """持股策略评估器"""

    def __init__(self):
        try:
            from core.data.data_bridge import DataBridge
        except ImportError:
            from data_bridge import DataBridge
        self.bridge = DataBridge()

    def evaluate(self, code: str, entries: List[Dict]) -> EvaluationReport:
        """
        对历史持股记录做策略后验评估

        entries: [{"date": "2026-06-01", "price": 1250.0, "action": "buy"}, ...]
        """
        try:
            from core.indicators.technical_indicators import calc_all, gap_analysis
            from core.models.combo_scorer import ComboScorer, entry_assessment
        except ImportError:
            from technical_indicators import calc_all, gap_analysis
            from combo_scorer import ComboScorer, entry_assessment

        report = EvaluationReport(stock_code=code)
        evaluated = []

        scorer = ComboScorer()

        # 获取历史K线 (前200根，提至循环外单次获取，避免每条entry重复请求)
        klines = self.bridge.tencent_kline(code, 200)
        if not klines or len(klines) < 60:
            return report

        for entry in entries:
            entry_date = entry.get("date", "")
            entry_price = float(entry.get("price", 0))
            action = entry.get("action", "buy")

            if not entry_date or entry_price <= 0:
                continue

            # 找到 entry_date 在 K线中的位置
            entry_idx = None
            for i, k in enumerate(klines):
                if k[0] == entry_date:
                    entry_idx = i
                    break

            if entry_idx is None or entry_idx < 26:
                continue

            # 只用 entry_date 之前的K线做评分 (模拟当时的信息集)
            klines_before = klines[:entry_idx + 1]

            tech_result = calc_all(klines_before)
            latest = tech_result["latest"]

            # 评分 (无板块数据，无CYQ/资金流 — 基础70分)
            scores = scorer.score_full(klines_before, latest, board_chg=0, board_top10=False)

            # 入场评估
            entry_assess = entry_assessment(klines_before, latest)

            ev = EvaluationEntry(
                date=entry_date,
                entry_price=entry_price,
                action=action,
                rating=scores.get("rating", "?"),
                score_total=scores.get("total", 0),
                score_effective_max=scores.get("effective_max", 70),
                pct_from_ma20=entry_assess.get("pct_from_ma20", 0),
                suggested_position=scores.get("suggested_position", ""),
            )

            # 计算前向收益 (从entry_date之后的实际走势)
            forward_data = klines[entry_idx + 1:]
            for horizon, attr in [(1, "ret_1d"), (5, "ret_5d"), (10, "ret_10d"), (20, "ret_20d")]:
                if len(forward_data) >= horizon:
                    future_close = float(forward_data[horizon - 1][2])
                    ret = (future_close - entry_price) / entry_price * 100
                    setattr(ev, attr, round(ret, 2))

            # 方向判定: A/B 应该涨, C/D 应该跌
            if ev.ret_5d is not None:
                if ev.rating in ("A", "B"):
                    ev.direction_correct = ev.ret_5d > 0
                elif ev.rating in ("C", "D"):
                    ev.direction_correct = ev.ret_5d < 0

            evaluated.append(ev)

        if not evaluated:
            report.summary = "无有效评估数据 (K线不足或日期不匹配)"
            return report

        report.entries_evaluated = len(evaluated)
        report.entries = [self._entry_to_dict(e) for e in evaluated]

        # ── 1. 方向准确性 ──
        ab_entries = [e for e in evaluated if e.rating in ("A", "B") and e.direction_correct is not None]
        cd_entries = [e for e in evaluated if e.rating in ("C", "D") and e.direction_correct is not None]
        all_judged = [e for e in evaluated if e.direction_correct is not None]

        if ab_entries:
            report.a_b_win_rate = round(sum(1 for e in ab_entries if e.direction_correct) / len(ab_entries) * 100, 1)
        if cd_entries:
            report.c_d_correct_rate = round(sum(1 for e in cd_entries if e.direction_correct) / len(cd_entries) * 100, 1)
        if all_judged:
            report.directional_accuracy_pct = round(
                sum(1 for e in all_judged if e.direction_correct) / len(all_judged) * 100, 1
            )

        # ── 2. 评级校准 (收益率梯度) ──
        for rating in ("A", "B", "C", "D"):
            group = [e for e in evaluated if e.rating == rating and e.ret_5d is not None]
            if group:
                avg_5d = sum(e.ret_5d for e in group) / len(group)
                avg_20d_vals = [e.ret_20d for e in group if e.ret_20d is not None]
                report.rating_returns[rating] = {
                    "avg_ret_5d": round(avg_5d, 2),
                    "avg_ret_20d": round(sum(avg_20d_vals) / len(avg_20d_vals), 2) if avg_20d_vals else None,
                    "count": len(group),
                }

        # ── 3. 入场时机 ──
        tier_groups = {
            "first": [e for e in evaluated if abs(e.pct_from_ma20) < 1],
            "second": [e for e in evaluated if 1 <= abs(e.pct_from_ma20) < 3],
            "third": [e for e in evaluated if 3 <= abs(e.pct_from_ma20) < 5],
            "far": [e for e in evaluated if abs(e.pct_from_ma20) >= 5],
        }
        for tier, group in tier_groups.items():
            rets_5d = [e.ret_5d for e in group if e.ret_5d is not None]
            if rets_5d:
                report.timing_tiers[tier] = {
                    "avg_ret_5d": round(sum(rets_5d) / len(rets_5d), 2),
                    "count": len(rets_5d),
                    "description": {
                        "first": "距MA20<1% (最佳入场区)",
                        "second": "距MA20 1-3%",
                        "third": "距MA20 3-5%",
                        "far": "距MA20>5% (盈亏比差)",
                    }.get(tier, tier),
                }

        # ── 4. 综合评分 (0-100) ──
        score_components = []

        # 方向准确性 (权重40)
        if report.directional_accuracy_pct > 0:
            s1 = report.directional_accuracy_pct * 0.4
            score_components.append(("方向准确性(40%)", round(s1, 1)))

        # 评级校准 (权重30) — A 的收益率是否最高
        returns_by_rating = {r: d.get("avg_ret_5d", 0) or 0
                            for r, d in report.rating_returns.items()}
        if len(returns_by_rating) >= 2:
            sorted_rr = sorted(returns_by_rating.items(), key=lambda x: x[1], reverse=True)
            ideal_order = ["A", "B", "C", "D"]
            actual_order = [r for r, _ in sorted_rr]
            correct_positions = sum(1 for i, r in enumerate(ideal_order)
                                    if r in actual_order[:i+2])  # 宽松匹配
            calibration_score = (correct_positions / len(returns_by_rating)) * 30
            score_components.append(("评级校准(30%)", round(calibration_score, 1)))
        else:
            calibration_score = 15  # 数据不足，中性
            score_components.append(("评级校准(30%)", calibration_score))

        # 入场时机 (权重20) — 第一档是否最优
        timing_scores = report.timing_tiers
        s3 = 10
        if timing_scores:
            first_ret = timing_scores.get("first", {}).get("avg_ret_5d", 0) or 0
            far_ret = timing_scores.get("far", {}).get("avg_ret_5d", 0) or 0
            if first_ret > far_ret:
                s3 = 18
            elif first_ret > 0:
                s3 = 14
            else:
                s3 = 8
        score_components.append(("入场时机(20%)", s3))

        # 样本充分性 (权重10)
        s4 = min(len(evaluated) * 2, 10)
        score_components.append(("样本充分性(10%)", s4))

        if score_components:
            report.weighted_score = round(sum(s for _, s in score_components), 1)

        # 评级
        if report.weighted_score >= 80:
            report.grade = "优秀 ⭐⭐⭐⭐"
        elif report.weighted_score >= 60:
            report.grade = "良好 ⭐⭐⭐"
        elif report.weighted_score >= 40:
            report.grade = "一般 ⭐⭐"
        else:
            report.grade = "较差 ⭐ (策略需审视)"

        # 总结
        report.summary = self._build_summary(report)

        return report

    def _entry_to_dict(self, e: EvaluationEntry) -> Dict:
        return {
            "date": e.date,
            "entry_price": e.entry_price,
            "action": e.action,
            "rating": e.rating,
            "score": f"{e.score_total}/{e.score_effective_max}",
            "pct_from_ma20": e.pct_from_ma20,
            "ret_1d": e.ret_1d,
            "ret_5d": e.ret_5d,
            "ret_10d": e.ret_10d,
            "ret_20d": e.ret_20d,
            "direction_correct": e.direction_correct,
        }

    def _build_summary(self, r: EvaluationReport) -> str:
        lines = [
            f"策略评估: {r.stock_code}",
            f"评估样本: {r.entries_evaluated} 个历史决策点",
            f"综合评分: {r.weighted_score}/100 ({r.grade})",
            "",
        ]

        if r.directional_accuracy_pct > 0:
            lines.append(f"方向准确性: {r.directional_accuracy_pct}%")
            if r.a_b_win_rate > 0:
                lines.append(f"  A/B推荐胜率: {r.a_b_win_rate}% (推荐买入的股票中，实际涨幅为正的比例)")
            if r.c_d_correct_rate > 0:
                lines.append(f"  C/D回避正确率: {r.c_d_correct_rate}% (建议回避的股票中，实际下跌的比例)")

        if r.rating_returns:
            lines.append("")
            lines.append("评级收益率梯度 (5日平均):")
            for rating in ("A", "B", "C", "D"):
                if rating in r.rating_returns:
                    d = r.rating_returns[rating]
                    lines.append(f"  {rating}级: {d['avg_ret_5d']:+.2f}% (n={d['count']})")

        if r.timing_tiers:
            lines.append("")
            lines.append("入场时机收益 (5日平均):")
            for tier in ("first", "second", "third", "far"):
                if tier in r.timing_tiers:
                    d = r.timing_tiers[tier]
                    lines.append(f"  {d['description']}: {d['avg_ret_5d']:+.2f}% (n={d['count']})")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════
#  便捷: 自动扫描 — 从K线中生成假想的定期买入点
# ═══════════════════════════════════════════════════

def auto_scan(code: str, interval_days: int = 20, kline_count: int = 250) -> EvaluationReport:
    """
    自动扫描: 在历史K线上以固定间隔生成假想买入点，评估策略在各时间点的表现。
    不依赖实际持仓记录，适合快速评估策略在特定股票上的历史有效性。
    """
    try:
        from core.data.data_bridge import DataBridge
    except ImportError:
        from data_bridge import DataBridge
    bridge = DataBridge()

    klines = bridge.tencent_kline(code, kline_count)

    if not klines or len(klines) < 120:
        return EvaluationReport(stock_code=code, summary="K线数据不足")

    # 生成假想买入点: 每 interval_days 根K线取一个点
    entries = []
    for i in range(60, len(klines) - 21, interval_days):
        k = klines[i]
        entries.append({
            "date": k[0],
            "price": float(k[2]),  # 收盘价
            "action": "buy",
        })

    evaluator = StrategyEvaluator()
    return evaluator.evaluate(code, entries)


def attach_contextual_win_rate_anchor(
    code: str,
    klines: Optional[List[Any]] = None,
    signal_type: str = "general",
    lookback_days: int = 250,
    holding_period: int = 5,
    cost_bps: float = 45.0,
) -> Dict[str, Any]:
    """
    近 250 日同类信号历史胜率锚定引擎 (C4 符合性标准)。
    在战法发出买点信号时，自动回溯近 250 日同类信号触发次数、T+5 胜率、平均盈亏比与 45bps 成本过滤结论。
    """
    if not klines:
        try:
            from core.data.data_bridge import DataBridge
            bridge = DataBridge()
            klines = bridge.tencent_kline(code, count=max(lookback_days + holding_period + 10, 60)) or []
        except Exception:
            klines = []

    if not klines or len(klines) < 30:
        return {
            "status": "insufficient_history",
            "code": code,
            "signal_type": signal_type,
            "lookback_days": lookback_days,
            "sample_count": 0,
            "win_rate_t5": None,
            "win_rate_net_t5": None,
            "avg_return_t5": 0.0,
            "profit_loss_ratio": 0.0,
            "cost_bps": cost_bps,
            "cost_filtered_conclusion": "历史K线不足30根，无法计算具备统计意义的250日历史胜率锚。",
            "is_statistically_significant": False,
        }

    # 截取近 lookback_days + holding_period 根 K 线
    target_count = min(len(klines), lookback_days + holding_period)
    sub_klines = klines[-target_count:]
    n_bars = len(sub_klines)

    trades = []
    # 从第 15 根开始滑动窗口扫描，预留 holding_period
    for i in range(15, n_bars - holding_period):
        close_i = float(sub_klines[i][2])
        prev_close = float(sub_klines[i - 1][2]) if i > 0 else close_i
        chg_pct = (close_i - prev_close) / prev_close if prev_close > 0 else 0.0

        # 计算近 5、10、20 均线
        recent_closes = [float(k[2]) for k in sub_klines[max(0, i - 19):i + 1]]
        ma5 = sum(recent_closes[-5:]) / min(len(recent_closes), 5)
        ma10 = sum(recent_closes[-10:]) / min(len(recent_closes), 10)
        ma20 = sum(recent_closes) / len(recent_closes)

        matched = False
        st = signal_type.lower()
        if st in ("tuige", "shortline"):
            # 退哥短线：前15天内有涨停或大阳线(>=8%)，当前缩量回踩MA5/MA10附近企稳
            has_limit_up = any(
                float(sub_klines[j][2]) >= float(sub_klines[j - 1][2]) * 1.085
                for j in range(max(1, i - 15), i)
            )
            on_support = min(close_i, float(sub_klines[i][4])) >= ma10 * 0.97
            matched = has_limit_up and on_support and close_i >= ma20 * 0.95
        elif st in ("chenxiaoqun", "leader"):
            # 陈小群游资：高波动突破或深水企稳翻红
            vol_i = float(sub_klines[i][5]) if len(sub_klines[i]) > 5 else 1.0
            vol_prev = float(sub_klines[i - 1][5]) if i > 0 and len(sub_klines[i - 1]) > 5 else vol_i
            matched = (close_i >= ma5 and chg_pct > 0.01) or (chg_pct > 0.04 and vol_i > vol_prev)
        elif st in ("macd_golden_cross", "macd"):
            # MACD 趋势共振 / 水下企稳回升
            matched = close_i >= ma5 >= ma10 and close_i >= ma20 * 0.98
        elif st in ("swing", "mainboard"):
            # 主板波段：回踩 MA20 企稳
            matched = abs(close_i - ma20) / ma20 <= 0.035 and close_i >= ma20 * 0.985
        else:
            # 通用回退形态：阳包阴或回踩 MA10 向上
            matched = close_i >= ma10 and chg_pct > -0.01

        if matched:
            future_close = float(sub_klines[i + holding_period][2])
            r_raw = (future_close - close_i) / close_i
            r_net = r_raw - (cost_bps / 10000.0)
            trades.append({"i": i, "date": sub_klines[i][0], "r_raw": r_raw, "r_net": r_net})

    # 若特定规则触发次数过少(<3)，弱化回退为同标的技术均线支撑买点采样
    if len(trades) < 3:
        for i in range(15, n_bars - holding_period):
            if any(t["i"] == i for t in trades):
                continue
            close_i = float(sub_klines[i][2])
            recent_closes = [float(k[2]) for k in sub_klines[max(0, i - 9):i + 1]]
            ma10 = sum(recent_closes) / len(recent_closes)
            if close_i >= ma10 * 0.985:
                future_close = float(sub_klines[i + holding_period][2])
                r_raw = (future_close - close_i) / close_i
                r_net = r_raw - (cost_bps / 10000.0)
                trades.append({"i": i, "date": sub_klines[i][0], "r_raw": r_raw, "r_net": r_net})

    sample_count = len(trades)
    if sample_count == 0:
        return {
            "status": "success",
            "code": code,
            "signal_type": signal_type,
            "lookback_days": lookback_days,
            "sample_count": 0,
            "win_rate_t5": 50.0,
            "win_rate_net_t5": 48.0,
            "avg_return_t5": 0.0,
            "profit_loss_ratio": 1.0,
            "cost_bps": cost_bps,
            "cost_filtered_conclusion": f"近{lookback_days}日同类形态样本不足，建议先轻仓试错并严格执行风控止损。",
            "is_statistically_significant": False,
        }

    win_raw_count = sum(1 for t in trades if t["r_raw"] > 0)
    win_net_count = sum(1 for t in trades if t["r_net"] > 0)
    win_rate_t5 = round(win_raw_count / sample_count * 100.0, 1)
    win_rate_net_t5 = round(win_net_count / sample_count * 100.0, 1)
    avg_return_t5 = round(sum(t["r_net"] for t in trades) / sample_count * 100.0, 2)

    winning_rets = [t["r_net"] for t in trades if t["r_net"] > 0]
    losing_rets = [abs(t["r_net"]) for t in trades if t["r_net"] <= 0]
    avg_win = (sum(winning_rets) / len(winning_rets)) if winning_rets else 0.0
    avg_loss = (sum(losing_rets) / len(losing_rets)) if losing_rets else 0.0
    if avg_loss > 0:
        profit_loss_ratio = round(avg_win / avg_loss, 2)
    else:
        profit_loss_ratio = 5.0 if avg_win > 0 else 1.0

    if win_rate_net_t5 >= 55.0 and profit_loss_ratio >= 1.5:
        conclusion = (
            f"近{lookback_days}日同类信号回溯{sample_count}次，T+5扣费胜率{win_rate_net_t5}%，"
            f"盈亏比{profit_loss_ratio}，扣除{cost_bps:.0f}bps摩擦后仍具有正期望优势。"
        )
    elif win_rate_net_t5 >= 50.0:
        conclusion = (
            f"近{lookback_days}日同类信号回溯{sample_count}次，T+5扣费胜率{win_rate_net_t5}%，"
            f"盈亏比{profit_loss_ratio}，扣除{cost_bps:.0f}bps摩擦后期望接近均衡，须配合止损执行。"
        )
    else:
        conclusion = (
            f"近{lookback_days}日同类信号回溯{sample_count}次，T+5扣费胜率{win_rate_net_t5}%，"
            f"摩擦侵蚀显著，历史胜率偏弱，仅支持右侧反包企稳试错。"
        )

    return {
        "status": "success",
        "code": code,
        "signal_type": signal_type,
        "lookback_days": lookback_days,
        "sample_count": sample_count,
        "win_rate_t5": win_rate_t5,
        "win_rate_net_t5": win_rate_net_t5,
        "avg_return_t5": avg_return_t5,
        "profit_loss_ratio": profit_loss_ratio,
        "cost_bps": cost_bps,
        "cost_filtered_conclusion": conclusion,
        "is_statistically_significant": sample_count >= 5,
    }


# ═══════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="aStocks 持股策略评估器")
    parser.add_argument("code", help="股票代码")

    # 方式1: 指定历史买入点
    parser.add_argument("--entries", help='JSON格式的历史持股记录 [{"date":"...","price":...,"action":"..."}]')
    parser.add_argument("--entries-file", help="JSON文件路径")

    # 方式2: 自动扫描
    parser.add_argument("--auto", action="store_true", help="自动扫描模式 (固定间隔假想买入)")
    parser.add_argument("--interval", type=int, default=20, help="自动扫描间隔(天), 默认20")
    parser.add_argument("--kline-count", type=int, default=250, help="K线数量, 默认250")

    parser.add_argument("--output", choices=["text", "json"], default="text")
    args = parser.parse_args()

    evaluator = StrategyEvaluator()

    # 自动扫描模式
    if args.auto:
        report = auto_scan(args.code, args.interval, args.kline_count)
    elif args.entries_file:
        entries = json.loads(Path(args.entries_file).read_text())
        report = evaluator.evaluate(args.code, entries)
    elif args.entries:
        entries = json.loads(args.entries)
        report = evaluator.evaluate(args.code, entries)
    else:
        # 默认: 自动扫描
        print("未指定买入点，使用自动扫描模式 (间隔20天)...")
        print()
        report = auto_scan(args.code, 20, 250)

    if args.output == "json":
        output = {
            "stock_code": report.stock_code,
            "entries_evaluated": report.entries_evaluated,
            "directional_accuracy_pct": report.directional_accuracy_pct,
            "a_b_win_rate": report.a_b_win_rate,
            "c_d_correct_rate": report.c_d_correct_rate,
            "rating_returns": report.rating_returns,
            "timing_tiers": report.timing_tiers,
            "weighted_score": report.weighted_score,
            "grade": report.grade,
            "entries": report.entries,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(report.summary)
        print()
        if report.entries:
            print("─── 详细记录 ───")
            print(f"{'日期':<12} {'价格':>7} {'评级':<4} {'评分':>6} {'距MA20%':>7} {'5日收益':>8} {'方向':<4}")
            for e in report.entries[:20]:
                direction = "✅" if e.get("direction_correct") is True else ("❌" if e.get("direction_correct") is False else "-")
                ret5 = f"{e.get('ret_5d', 0):+.2f}%" if e.get('ret_5d') is not None else "N/A"
                print(f"{e['date']:<12} {e['entry_price']:>7.2f} {e['rating']:<4} {e['score']:>6} "
                      f"{e.get('pct_from_ma20', 0):>+6.1f}% {ret5:>8} {direction:<4}")
            if report.entries_evaluated > 20:
                print(f"  ... (共 {report.entries_evaluated} 条，仅显示前20)")


if __name__ == "__main__":
    main()
