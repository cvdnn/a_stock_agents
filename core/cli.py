# -*- coding: utf-8 -*-
"""
Unified CLI for a_stock_agents.
Supports command-line execution for human users, scripts, and external UI/API sub-processes.
Integrates all standard quantitative research, risk control, screening, and backtesting subcommands.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

CUR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CUR_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CUR_DIR) not in sys.path:
    sys.path.insert(0, str(CUR_DIR))

from core.config import (
    CACHE_DIR,
    GLOBAL_CONFIG,
    OUTPUT_REPORTS_DIR,
    POOLS_DIR,
    POSITIONS_DIR,
    REPORTS_DIR,
)


# ═══════════════════════════════════════════════════
#  行情与技术面命令 (Data & Technicals)
# ═══════════════════════════════════════════════════

def cmd_data_quote(args):
    """实时行情 (单股或多股)"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    raw_code = getattr(args, "code", None)
    raw_codes = getattr(args, "codes", None)

    codes: List[str] = []
    if raw_code:
        codes = [raw_code]
    elif raw_codes:
        if isinstance(raw_codes, list):
            codes = raw_codes
        else:
            codes = [c.strip() for c in str(raw_codes).split(",") if c.strip()]

    if not codes:
        msg = {"error": "未提供股票代码"}
        print(json.dumps(msg, ensure_ascii=False) if getattr(args, "json", False) else "错误: 未提供股票代码")
        return

    if len(codes) == 1:
        c = codes[0]
        q = bridge.get_realtime_quote(c)
        if not q:
            err = {"error": f"无法获取 {c} 实时行情"}
            print(json.dumps(err, ensure_ascii=False) if getattr(args, "json", False) else f"错误: 无法获取 {c} 实时行情")
            return
        if getattr(args, "json", False) or getattr(args, "output", "") == "json":
            print(json.dumps(q, ensure_ascii=False, indent=2))
        else:
            print(f"{q.get('name', c)}({q.get('code', c)})")
            print(f"  现价: {q.get('price')}  涨跌: {q.get('change_pct', 0):+.2f}%")
            print(f"  PE: {q.get('pe', 'N/A')}  换手: {q.get('turnover_pct', 'N/A')}%")
            print(f"  日内: {q.get('low', 'N/A')} ~ {q.get('high', 'N/A')}")
    else:
        results = bridge.fetch_batch_snapshot(codes)
        if getattr(args, "json", False) or getattr(args, "output", "") == "json":
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(f"{'代码':<8} {'名称':<10} {'现价':>7} {'涨跌%':>7} {'PE':>6} {'换手%':>6} {'市值(亿)':>10} {'外盘比':>6}")
            print("-" * 75)
            for r in results:
                chg_color = "🔴" if r.get("change_pct", 0) > 0 else "🟢"
                print(
                    f"{r.get('code',''):<8} {r.get('name',''):<10} {r.get('price',0):>7.2f} "
                    f"{r.get('change_pct',0):>+6.2f}% {r.get('pe',0):>6.1f} {r.get('turnover_pct',0):>6.2f}% "
                    f"{r.get('market_cap',0):>10.1f} {r.get('o_ratio',0):>5.1f}% {chg_color}"
                )


def cmd_data_technical(args):
    """技术指标分析与缺口检测"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all, gap_analysis, second_golden_cross

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count=count)
    if not klines or len(klines) < 20:
        err = {"error": f"标的 {args.code} K线数据不足 ({len(klines) if klines else 0}根)"}
        print(json.dumps(err, ensure_ascii=False) if getattr(args, "json", False) else err["error"])
        return

    tech = calc_all(klines)
    gaps = gap_analysis(klines)
    golden = second_golden_cross(klines)
    res = {"code": args.code, "technical": tech, "gaps": gaps, "second_golden_cross": golden}

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        l = tech.get("latest", {})
        print(f"=== [{args.code}] 经典技术指标 (K线 {len(klines)} 根) ===")
        print(f"收盘价: {l.get('close')}")
        print(f"MA5/10/20/60: {l.get('ma5', 'N/A')}/{l.get('ma10', 'N/A')}/{l.get('ma20', 'N/A')}/{l.get('ma60', 'N/A')}")
        print(f"MACD: DIF={l.get('dif', 'N/A')} | DEA={l.get('dea', 'N/A')} | Bar={l.get('macd_bar', 'N/A')}")
        print(f"KDJ: K={l.get('kdj_k', 'N/A')} | D={l.get('kdj_d', 'N/A')} | J={l.get('kdj_j', 'N/A')}")
        print(f"RSI: {l.get('rsi', 'N/A')} | ATR: {l.get('atr', 'N/A')}")
        print(f"BOLL通道: {l.get('boll_lower', 'N/A')} ~ {l.get('boll_mid', 'N/A')} ~ {l.get('boll_upper', 'N/A')}")
        if gaps.get("gaps"):
            print(f"跳空缺口: 近10日共 {gaps.get('count')} 次, 连续同向 {gaps.get('consecutive_same')} 次")
        print(f"二次金叉检测: {golden.get('verdict')} | 理由: {golden.get('reason', '无')}")


def cmd_batch(args):
    """批量行情快照"""
    args.codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    cmd_data_quote(args)


def cmd_events(args):
    """个股重要事件与公告"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    name = getattr(args, "name", "")
    result = bridge.get_stock_events(args.code, name)
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 个股事件 ===")
        if result:
            print(result.get("text", str(result))[:2000])
        else:
            print("  暂无事件数据（需配置 proxy-patch 或数据源插件）")


def cmd_cyq(args):
    """筹码分布 (CYQ)"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    result = bridge.get_cyq(args.code)
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 筹码分布 ===")
        if result:
            print(f"  获利比例: {result.get('profit_ratio', 'N/A')}")
            print(f"  平均成本: {result.get('avg_cost', 'N/A')}")
            print(f"  90%集中度: {result.get('concentration_90', 'N/A')}")
            print(f"  70%集中度: {result.get('concentration_70', 'N/A')}")
            conc = result.get("concentration_90", 0)
            if conc and conc < 0.10:
                print("  判断: 高度集中，主力控盘 ⭐")
            elif conc and conc < 0.13:
                print("  判断: 筹码相对集中")
            elif conc and conc < 0.15:
                print("  判断: 中性")
            else:
                print("  判断: 筹码相对发散")
        else:
            print("  暂无筹码数据（需数据源支持）")


def cmd_balance(args):
    """代理服务与数据源余额检查"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    result = bridge.check_proxy_balance()
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print("代理积分与服务状态:")
        print(f"  {result or '状态正常 / 零积分直连运行中'}")


# ═══════════════════════════════════════════════════
#  评分与研判命令 (Scoring & Analysis)
# ═══════════════════════════════════════════════════

def cmd_score(args):
    """ComboScorer 策略评分"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.models.combo_scorer import ComboScorer, entry_assessment

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    if not klines or len(klines) < 26:
        print(json.dumps({"error": "K线数据不足"}, ensure_ascii=False))
        return

    tech = calc_all(klines)
    scorer = ComboScorer()
    scores = scorer.score_full(
        klines,
        tech["latest"],
        getattr(args, "board_chg", 0) or 0,
        getattr(args, "board_top10", False),
        getattr(args, "short", False),
    )
    entry = entry_assessment(klines, tech["latest"])
    output = {"code": args.code, "scores": scores, "entry": entry}

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 量化策略评分 ===")
        for dim, info in scores.items():
            if isinstance(info, dict) and "score" in info and "max" in info:
                print(f"  {dim}: {info['score']}/{info['max']} {info.get('reason', '')}")
        print("  ───────────────────")
        print(f"  总分: {scores.get('total')}/{scores.get('max_total')} | 评级: {scores.get('rating')} → {scores.get('rating_text')}")
        print(f"  建议仓位: {scores.get('suggested_position')}")
        print(f"  {entry.get('distance_text')}")
        print(f"  止损参考: {entry.get('stop_loss')} (约 -{entry.get('stop_loss_pct', 0):.1f}%)")


def cmd_analyze(args):
    """全维度大盘与个股联动综合分析"""
    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  aStocks 全维度分析: {args.code:<28}║")
    print(f"╚══════════════════════════════════════════════════╝\n")

    # 1. 大盘环境
    print("─── 📊 大盘环境 ───")
    from core.models.market_assessor import MarketAssessor

    assessor = MarketAssessor()
    market = assessor.assess_all()
    print(f"  大盘模式: {market['mode']} (得分 {market['total_score']}/{market['max_score']})")
    print(f"  建议仓位上限: {market['max_position']}")
    for dim, info in market.get("dimensions", {}).items():
        print(f"  {dim}: {info['score']}/{info['max']} {info.get('reason', '')}")

    # 2. 个股技术面
    print(f"\n─── 🔍 个股技术分析 ───")
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all, gap_analysis

    bridge = DataBridge()
    quote = bridge.get_realtime_quote(args.code)
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    if not klines or len(klines) < 26:
        print("  ⚠️ K线数据不足")
        return

    tech = calc_all(klines)
    gaps = gap_analysis(klines)
    l = tech.get("latest", {})

    if quote:
        print(f"  {quote.get('name', args.code)}({quote.get('code')}) 现价 {quote.get('price')} ({quote.get('change_pct', 0):+.2f}%)")
    print(f"  MA5/10/20/60: {l.get('ma5','N/A')}/{l.get('ma10','N/A')}/{l.get('ma20','N/A')}/{l.get('ma60','N/A')}")
    print(f"  MACD: DIF={l.get('dif','N/A')} DEA={l.get('dea','N/A')} Bar={l.get('macd_bar','N/A')}")
    print(f"  KDJ: K={l.get('kdj_k','N/A')} D={l.get('kdj_d','N/A')} J={l.get('kdj_j','N/A')}")
    print(f"  RSI: {l.get('rsi','N/A')} | ATR: {l.get('atr','N/A')}")

    # 3. 策略评分
    print(f"\n─── 📈 策略评分 ───")
    from core.models.combo_scorer import ComboScorer, entry_assessment

    scorer = ComboScorer()
    scores = scorer.score_full(
        klines,
        l,
        getattr(args, "board_chg", 0) or 0,
        getattr(args, "board_top10", False),
        getattr(args, "short", False),
    )
    entry = entry_assessment(klines, l)
    print(f"  总分: {scores.get('total')}/{scores.get('max_total')} | 评级: {scores.get('rating')} → {scores.get('rating_text')}")
    print(f"  建议仓位: {scores.get('suggested_position')}")
    print(f"  {entry.get('distance_text')}")
    print(f"  止损位: {entry.get('stop_loss')} (约 -{entry.get('stop_loss_pct', 0):.1f}%)")


def cmd_market(args):
    """五维大盘健康度评估"""
    from core.models.market_assessor import MarketAssessor

    assessor = MarketAssessor()
    result = assessor.assess_all()
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"╔══════════════════════════════════════════════════╗")
        print(f"║  五维大盘健康度综合评估                          ║")
        print(f"╚══════════════════════════════════════════════════╝")
        print(f"  总分: {result['total_score']}/{result['max_score']}")
        print(f"  市场模式: {result['mode']} | 建议仓位上限: {result['max_position']}")
        for dim, info in result.get("dimensions", {}).items():
            bar = "█" * info["score"] + "░" * (info["max"] - info["score"])
            print(f"  {dim:<12} [{bar}] {info['score']}/{info['max']}")
            print(f"             {info.get('reason', '')}")
        print("\n  主要指数:")
        for k, v in result.get("index_data", {}).items():
            chg = v.get("change_pct", 0)
            arrow = "↑" if chg > 0 else "↓"
            print(f"  {v.get('name', k):<8} {v.get('price', 'N/A')} {arrow} {chg:+.2f}%")


def cmd_multi_factor(args):
    """多因子选股综合评分"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.models.multi_factor_scorer import MultiFactorScorer

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}, ensure_ascii=False))
        return

    tech = calc_all(klines)
    latest = tech.get("latest", {})

    pe = getattr(args, "pe", None)
    if pe is None:
        quote = bridge.get_realtime_quote(args.code)
        if quote and quote.get("pe"):
            try:
                pe = float(quote["pe"])
            except ValueError:
                pe = None

    scorer = MultiFactorScorer()
    result = scorer.score_multi_factor(klines, latest, pe, getattr(args, "pb", None))

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 多因子量化评分 ===")
        print(f"  综合Alpha得分: {result.get('composite_score', 0):.1f} → {result.get('rating')} {result.get('rating_text')}")
        for name, info in result.get("factors", {}).items():
            if "weight" in info:
                print(f"  {name:<14} {info.get('normalized', 0):>6.1f} (权重 {info['weight']:.0%})")
            elif "normalized" in info:
                print(f"  {name:<14} {info.get('normalized', 0):>6.1f}")


# ═══════════════════════════════════════════════════
#  风控与交易决策命令 (Risk & Actions)
# ═══════════════════════════════════════════════════

def cmd_trapped(args):
    """被套持仓诊断与解套决策树"""
    from core.data.data_bridge import DataBridge
    from core.strategy.trapped_position import TrappedPositionAnalyzer

    bridge = DataBridge()
    count = getattr(args, "count", 250)
    klines = bridge.tencent_kline(args.code, count)
    if not klines or len(klines) < 26:
        print(json.dumps({"error": "K线数据不足"}, ensure_ascii=False))
        return

    analyzer = TrappedPositionAnalyzer(args.cost, args.shares, klines)
    result = analyzer.analyze()

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        d = result["diagnostic"]
        dt = result["decision_tree"]
        print(f"╔══════════════════════════════════════════════════╗")
        print(f"║  持仓解套量化诊断: {args.code:<26}║")
        print(f"╚══════════════════════════════════════════════════╝")
        print(f"  成本: ¥{d['cost_price']} × {d['shares']}股 = ¥{d['total_cost']:,.0f}")
        print(f"  现价: ¥{d['current_price']}  浮亏: ¥{d['unrealized_loss']:+,.0f} ({d['loss_pct']:+.1f}%)")
        print(f"  ATR(14): {d.get('atr_14')}  凯利仓位建议: {d.get('kelly_f')}")
        print(f"  {d.get('kelly_interpretation')}")
        print(f"\n  决策树建议: {dt.get('recommended')} — {dt.get('reason')}")
        for s in dt.get("strategies", []):
            print(f"    → {s}")


def cmd_risk(args):
    """风控分析 (三级止损 + 卖点信号 + 3日K线形态 + 回撤管理)"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.strategy.risk_manager import RiskManager

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    if not klines or len(klines) < 26:
        print(json.dumps({"error": "K线数据不足"}, ensure_ascii=False))
        return

    tech = calc_all(klines)
    rm = RiskManager()
    entry_price = getattr(args, "entry", None) or float(klines[-1][2])

    result: Dict[str, Any] = {
        "stop_losses": rm.calc_stop_losses(entry_price, tech["latest"]),
        "sell_signals": rm.sell_signals(klines, tech["latest"]),
        "candle": rm.candle_pattern(klines),
    }

    cost = getattr(args, "cost", None)
    cur_val = getattr(args, "current_value", None)
    if cost and cur_val:
        peak = getattr(args, "peak", None) or cost
        result["drawdown"] = rm.drawdown_control(cur_val, peak, cost)

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        sl = result["stop_losses"]
        print(f"=== [{args.code}] 风控与止损位分析 ===")
        print(f"  入场基准价: {entry_price}")
        print(f"  T0 日内强平线: {sl['t0_intraday']['price']} (-{sl['t0_intraday']['loss_pct']}%) → {sl['t0_intraday']['action']}")
        print(f"  T1 MA10防守线: {sl['t1_ma10']['price']} (-{sl['t1_ma10']['loss_pct']}%) → {sl['t1_ma10']['action']}")
        print(f"  T2 MA20清仓线: {sl['t2_ma20']['price']} (-{sl['t2_ma20']['loss_pct']}%) → {sl['t2_ma20']['action']}")
        print()
        ss = result["sell_signals"]
        print("  卖点预警信号:")
        for s in ss.get("signals", []):
            print(f"    ⚠️ {s}")
        if not ss.get("signals"):
            print("    ✅ 无卖出信号")


def cmd_golden_cross(args):
    """MACD 二次金叉形态检测"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import second_golden_cross

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    if not klines or len(klines) < 60:
        print(json.dumps({"error": "至少需要60根K线"}, ensure_ascii=False))
        return

    result = second_golden_cross(klines)
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] MACD二次金叉检测 ===")
        print(f"  判决: {result.get('verdict')} — {result.get('reason')}")
        print(f"  通过条件: {result.get('passed_count')}/{result.get('total_checks')}")
        for c in result.get("checklist", []):
            print(f"    - {c}")


def cmd_portfolio_risk(args):
    """组合层级风险管理与集中度控制"""
    from core.data.data_bridge import DataBridge
    from core.strategy.portfolio_risk_manager import PortfolioRiskManager

    holdings_path = getattr(args, "holdings", None)
    if holdings_path and os.path.exists(holdings_path):
        with open(holdings_path, encoding="utf-8") as f:
            holdings = json.load(f)
    else:
        holdings = [
            {"code": "600519", "weight": 0.20, "sector": "白酒", "industry": "食品饮料"},
            {"code": "601899", "weight": 0.15, "sector": "有色", "industry": "贵金属"},
            {"code": "600276", "weight": 0.15, "sector": "医药", "industry": "生物医药"},
        ]

    bridge = DataBridge()
    klines_map = {}
    for h in holdings:
        klines_map[h["code"]] = bridge.tencent_kline(h["code"], 60)

    mgr = PortfolioRiskManager()
    report = mgr.generate_risk_report(holdings, klines_map, getattr(args, "pnl", 0.0))

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        s = report.get("summary", {})
        print("=== 投资组合风险分析报告 ===")
        print(f"  持仓标的数: {s.get('total_positions')} | 总仓位占比: {s.get('total_weight', 0):.1%}")
        print(f"  有效分散度指数 (Herfindahl): {s.get('herfindahl_index', 0):.1f}")
        print(f"  组合年化波动率: {s.get('portfolio_volatility', 0):.1%}")
        print(f"  回撤状态: {report.get('drawdown_control', {}).get('message')}")
        print(f"  行业敞口违规项: {s.get('sector_violations')}")
        print("\n  调仓与风控建议:")
        for r in report.get("recommendations", []):
            print(f"    💡 {r}")


def cmd_action_plan(args):
    """实战交易反应动作与微观指令"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.models.combo_scorer import ComboScorer
    from core.strategy.execution_action_engine import ExecutionActionEngine

    bridge = DataBridge()
    code = getattr(args, "code", None) or "600519"
    cost = getattr(args, "cost", None) or 1200.0
    shares = getattr(args, "shares", None) or 100
    count = getattr(args, "count", 120)

    q = bridge.get_realtime_quote(code) or {"price": cost, "open": cost, "high": cost, "low": cost, "change_pct": 0.0}
    name = q.get("name", code)
    klines = bridge.tencent_kline(code, count=count)
    tech_all = calc_all(klines) if (klines and len(klines) >= 26) else {}
    tech = tech_all.get("latest", {}) if tech_all else {}

    score_res = {"cs": 65, "rating": "B"}
    if klines and len(klines) >= 26 and tech:
        try:
            scorer = ComboScorer()
            scores = scorer.score_full(klines, tech)
            total_s = scores.get("total", 65)
            rating = "A" if total_s >= 75 else ("B" if total_s >= 60 else ("C" if total_s >= 45 else "D"))
            score_res = {"cs": total_s, "rating": rating}
        except Exception:
            pass

    holding = {"cost": cost, "shares": shares, "max_high": max(float(q.get("high", 0)), cost)}
    result = ExecutionActionEngine.generate_action(
        code=code,
        name=name,
        quote=q,
        tech=tech,
        holding=holding,
        model_score=score_res,
    )

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(ExecutionActionEngine.render_markdown_card(result))


def cmd_intent(args):
    """自然语言用户意图智能解析"""
    from core.strategy.execution_action_engine import IntentEvaluator

    res = IntentEvaluator.parse_user_query(args.query)
    print(json.dumps(res, ensure_ascii=False, indent=2))


def cmd_downside(args):
    """五类下跌场景化精准诊断与应对"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.strategy.execution_action_engine import DownsideReactionMatrix

    bridge = DataBridge()
    quote = bridge.get_realtime_quote(args.code)
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    tech = calc_all(klines) if klines else {}
    holding = (
        {"cost": args.cost, "shares": args.shares}
        if (getattr(args, "cost", None) and getattr(args, "shares", None))
        else None
    )

    diag = DownsideReactionMatrix.diagnose_downside(quote, tech, holding)
    print(json.dumps(diag, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════
#  选股与策略回测命令 (Screener & Backtest)
# ═══════════════════════════════════════════════════

def cmd_screen(args):
    """三层漏斗选股 (板块环境 → 技术过滤 → 综合打分)"""
    from core.models.stock_screener import StockScreener

    raw_codes = getattr(args, "codes", "")
    if isinstance(raw_codes, list):
        codes = raw_codes
    elif raw_codes:
        codes = [c.strip() for c in raw_codes.replace(" ", ",").split(",") if c.strip()]
    else:
        codes = ["600519", "000858", "601318", "600036", "601899"]

    screener = StockScreener()
    result = screener.screen(codes, fetch_cyq=getattr(args, "cyq", False))

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        clean = {k: v for k, v in result.items() if k != "results"}
        clean["results"] = [
            {k: v for k, v in r.items() if k not in ("klines", "technical")}
            for r in result.get("results", [])
        ]
        print(json.dumps(clean, ensure_ascii=False, indent=2))
    else:
        print(f"选股漏斗: 输入 {result['total_input']} 只 → 行业过滤 {result['stage1_board']} 只 "
              f"→ 技术初筛 {result['stage2_technical']} 只 → 综合优选 {result['stage3_scored']} 只\n")
        if result.get("results"):
            print(f"{'评级':<4} {'代码':<8} {'名称':<10} {'总分':>5} {'现价':>7} {'涨跌%':>7} {'板块':<8}")
            print("-" * 65)
            limit = getattr(args, "limit", 20) or 20
            for r in result["results"][:limit]:
                s = r["scores"]
                chg = r.get("change_pct", 0)
                arrow = "↑" if chg > 0 else "↓"
                print(
                    f"{s.get('rating', '-'):<4} {r['code']:<8} {r.get('name',''):<10} "
                    f"{s.get('total', 0):>5}/{s.get('max_total', 100):<3} "
                    f"{r.get('price', 0):>7.2f} {chg:>+6.2f}% {arrow} "
                    f"{str(r.get('sector','-'))[:6]:<8}"
                )
        else:
            print("未发现满足全部选股条件的标的")


def cmd_evaluate(args):
    """持股策略评估 (兼容历史持仓表现扫描与单股量化诊断)"""
    is_historical_eval = bool(
        getattr(args, "auto", False)
        or getattr(args, "entries", None)
        or getattr(args, "entries_file", None)
    )

    if is_historical_eval:
        from core.models.strategy_evaluator import StrategyEvaluator, auto_scan

        count = getattr(args, "count", 250)
        interval = getattr(args, "interval", 20) or 20

        if getattr(args, "auto", False):
            report = auto_scan(args.code, interval_days=interval, kline_count=count)
        elif getattr(args, "entries", None):
            entries = json.loads(args.entries)
            evaluator = StrategyEvaluator()
            report = evaluator.evaluate(args.code, entries)
        else:
            entries = json.loads(Path(args.entries_file).read_text(encoding="utf-8"))
            evaluator = StrategyEvaluator()
            report = evaluator.evaluate(args.code, entries)

        if getattr(args, "json", False) or getattr(args, "output", "") == "json":
            out = {
                "stock_code": report.stock_code,
                "entries_evaluated": report.entries_evaluated,
                "directional_accuracy_pct": report.directional_accuracy_pct,
                "a_b_win_rate": report.a_b_win_rate,
                "c_d_correct_rate": report.c_d_correct_rate,
                "grade": report.grade,
                "entries": report.entries,
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(report.summary)
    else:
        # 单股综合量化诊断
        from core.data.data_bridge import DataBridge
        from core.models.combo_scorer import ComboScorer

        bridge = DataBridge()
        code = args.code
        q = bridge.get_realtime_quote(code)
        klines = bridge.tencent_kline(code, count=120)
        if not q or not klines:
            print(json.dumps({"error": f"无法获取 {code} 行情数据"}, ensure_ascii=False))
            return

        scorer = ComboScorer()
        res = scorer.score_full(klines=klines, latest=q)
        if getattr(args, "json", False) or getattr(args, "output", "") == "json":
            out = {"code": code, "name": q.get("name", code), "price": q.get("price", 0), "score": res}
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"=== [{code}] {q.get('name', code)} 综合量化诊断 ===")
            print(f"现价: {q.get('price', 0):.2f} | 综合评分: {res.get('total', 'N/A')}/100")
            print(f"评级: {res.get('rating', 'N/A')} - {res.get('rating_text', 'N/A')} | 建议仓位: {res.get('suggested_position', 'N/A')}")


def cmd_backtest(args):
    """单标的量化策略回测 (SMA/ComboScore等策略对比与过拟合检验)"""
    from core.data.data_bridge import DataBridge
    from core.paper_trading.a_stocks_backtest import (
        BacktestEngine,
        combo_score_strategy,
        sma_cross_strategy,
    )

    bridge = DataBridge()
    count = getattr(args, "count", 250)
    klines = bridge.tencent_kline(args.code, count)
    if not klines or len(klines) < 30:
        print(json.dumps({"error": "K线数据不足"}, ensure_ascii=False))
        return

    cash = getattr(args, "cash", 1000000.0)
    strategy_name = getattr(args, "strategy", "sma_cross")
    engine = BacktestEngine(initial_cash=cash)
    strategy = sma_cross_strategy if strategy_name == "sma_cross" else combo_score_strategy

    if getattr(args, "split", False):
        in_sample, out_sample = engine.split_sample(klines)
        in_result = engine.run_strategy(in_sample, strategy)
        out_result = engine.run_strategy(out_sample, strategy)
        in_m = in_result["metrics"]
        out_m = out_result["metrics"]
        overfit = in_m["sharpe_ratio"] > 3 and in_m["max_drawdown"] < 5 and in_m["win_rate"] > 75
        output = {
            "code": args.code,
            "in_sample": in_m,
            "out_sample": out_m,
            "overfitting_check": {
                "in_sample_sharpe": in_m["sharpe_ratio"],
                "out_sample_sharpe": out_m["sharpe_ratio"],
                "overfitting_suspected": overfit,
                "warning": "疑似过拟合: 夏普>3 + 回撤<5% + 胜率>75%" if overfit else "未见明显过拟合",
            },
        }
    else:
        result = engine.run_strategy(klines, strategy)
        output = {
            "code": args.code,
            "strategy": strategy_name,
            "metrics": result["metrics"],
            "trades_count": len(result.get("trades", [])),
            "sample_trades": result.get("trades", [])[:5],
        }

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        m = output.get("metrics", output.get("in_sample", {}))
        print(f"{'代码':<8} {'策略':<12} {'年化收益':>8} {'夏普':>6} {'最大回撤':>8} {'胜率':>6} {'盈亏比':>6} {'Calmar':>6}")
        print(
            f"{args.code:<8} {strategy_name:<12} {m.get('annual_return',0):>7.2f}% "
            f"{m.get('sharpe_ratio',0):>6.2f} {m.get('max_drawdown',0):>7.2f}% "
            f"{m.get('win_rate',0):>5.1f}% {m.get('profit_factor',0):>6.2f} "
            f"{m.get('calmar_ratio',0):>6.2f}"
        )
        if "overfitting_check" in output:
            print(f"\n  过拟合检验: {output['overfitting_check']['warning']}")


def cmd_multi_backtest(args):
    """事件驱动多标的资产组合回测 (Top-K 截面轮动 + ATR 风控)"""
    from core.paper_trading.multi_backtest_engine import MultiBacktestEngine

    symbols = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if getattr(args, "symbols", None)
        else None
    )
    engine = MultiBacktestEngine(
        symbols=symbols,
        initial_cash=getattr(args, "cash", 1000000.0),
        top_k=getattr(args, "top", 4),
    )
    days = getattr(args, "days", 250)
    res = engine.run(num_days=days)

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if "error" in res:
        print(f"❌ 多标的回测失败: {res['error']}")
        return

    m = res["metrics"]
    print("\n─────────────────────── 多标的事件驱动回测绩效报告 ───────────────────────")
    print(f"  初始本金:             ￥{m['initial_cash']:,.2f}")
    print(f"  期末总权益:           ￥{m['final_equity']:,.2f}")
    print(f"  累计收益率:           {m['total_return_pct']:+.2f}%")
    print(f"  年化收益率 (CAGR):     {m['annualized_cagr_pct']:+.2f}%")
    print(f"  最大回撤 (MaxDD):     {m['max_drawdown_pct']:.2f}%")
    print(f"  夏普比率 (Sharpe):    {m['sharpe_ratio']:.2f}")
    print(f"  卡玛比率 (Calmar):    {m['calmar_ratio']:.2f}")
    print(f"  总交易笔数:           {m['total_trades']} 笔 (盈利: {m['win_trades']}, 亏损: {m['loss_trades']})")
    print(f"  交易胜率:             {m['win_rate_pct']:.1f}%")
    print(f"  盈亏比 (P/L Ratio):   {m['profit_loss_ratio']:.2f}")
    print("─────────────────────────────────────────────────────────────────────────\n")


def cmd_mean_reversion(args):
    """均值回归策略回测与机会评分"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.strategy.mean_reversion_strategy import MeanReversionStrategy

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}, ensure_ascii=False))
        return

    strategy = MeanReversionStrategy()
    bt = strategy.backtest_signals(klines)
    tech = calc_all(klines)
    score = strategy.score_reversion(klines, tech["latest"])

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps({"code": args.code, "backtest": bt, "reversion_score": score}, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 均值回归策略 ===")
        print(f"  买入信号: {bt['buy_signals']} 次 | 卖出信号: {bt['sell_signals']} 次")
        print(f"  胜率(5日): {bt['win_rate']:.1f}% | 平均5日收益: {bt['avg_return_5d']:+.2f}%")
        print(f"  均值回归评分: {score['score']}/100 → {score['rating']} ({score.get('reason', '')})")


def cmd_grid(args):
    """网格交易策略区间构建与回测模拟"""
    from core.data.data_bridge import DataBridge
    from core.strategy.grid_trading_strategy import GridTradingStrategy

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}, ensure_ascii=False))
        return

    cash = getattr(args, "cash", 1000000.0)
    grid = GridTradingStrategy()
    info = grid.build_grid(klines, cash)
    sim = grid.simulate(klines, cash)
    score = grid.score_grid_suitability(klines)

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps({"code": args.code, "grid_info": info, "simulation": sim, "suitability": score}, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 网格交易策略 ===")
        print(f"  网格数: {info.get('grid_count', 'N/A')} | 间距: {info.get('grid_spacing', 'N/A')}")
        print(f"  BOLL通道区间: {info.get('boll_lower', 'N/A')} ~ {info.get('boll_upper', 'N/A')}")
        print(f"  止损价: {info.get('stop_loss_price', 'N/A')}")
        print(f"  模拟收益: {sim.get('total_return_pct', 0):+.2f}% | 最大回撤: {sim.get('max_drawdown_pct', 0):.2f}%")
        print(f"  适合度评估: {score['score']}/100 → {score['rating']} ({score.get('reason', '')})")


def cmd_vol_breakout(args):
    """波动率收缩突破策略"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.strategy.volatility_breakout_strategy import VolatilityBreakoutStrategy

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}, ensure_ascii=False))
        return

    strategy = VolatilityBreakoutStrategy()
    bt = strategy.backtest_signals(klines)
    tech = calc_all(klines)
    score = strategy.score_breakout_opportunity(klines, tech["latest"])

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps({"code": args.code, "backtest": bt, "opportunity_score": score}, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 波动率突破策略 ===")
        print(f"  收缩期次数: {bt.get('squeeze_periods', 0)} 次 | 突破信号: {bt.get('breakout_signals', 0)} 次")
        print(f"  历史成功率: {bt.get('win_rate', 0):.1f}% | 平均5日收益: {bt.get('avg_return_5d', 0):+.2f}%")
        print(f"  突破机会评分: {score['score']}/100 → {score['rating']} ({score.get('reason', '')})")


def cmd_deploy_monitor(args):
    """监控部署说明"""
    print("aStocks 监控守护进程部署指南")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("1. 部署全天持仓盯盘任务 (每5分钟):")
    print("   AI-Platform cron create --name '全天持仓监控' \\")
    print("     --script skills/astock-platform-evaluate/scripts/monitor_watchdog.py \\")
    print("     --schedule 'every 5m' --no-agent --deliver all")
    print("\n2. 测试运行监控:")
    print("   python skills/astock-platform-evaluate/scripts/monitor_watchdog.py")


# ═══════════════════════════════════════════════════
#  配置与系统管理命令 (Config & System)
# ═══════════════════════════════════════════════════

def cmd_config_paths(args):
    from core.config import get_active_paths

    paths = get_active_paths()
    if getattr(args, "json", False):
        print(json.dumps(paths, ensure_ascii=False, indent=2))
    else:
        print("=== A-Stock Agents 路径与专属数据隔离配置 ===")
        print(f"  项目根目录 (PROJECT_ROOT):    {paths['project_root']}")
        print(f"  用户专属数据 (OUTPUT_DIR):    {paths['output_dir']} {'[自定义生效]' if paths['is_custom_output'] else '[默认隔离目录]'}")
        print(f"  - 股票池与持仓 (POOLS_DIR):   {paths['pools_dir']}")
        print(f"  - 投研报告目录 (REPORTS_DIR): {paths['reports_dir']}")
        print(f"  - 运行缓存目录 (CACHE_DIR):   {paths['cache_dir']}")
        print(f"  - 回测结果目录 (BACKTEST):    {paths['backtest_dir']}")
        print(f"  - 快照备份目录 (BACKUPS_DIR): {paths['backups_dir']}")
        print(f"  隔离状态: {'✅ 已配置独立数据目录' if paths['is_custom_output'] else 'ℹ️ 使用项目内 output/ 目录'}")


def cmd_config_market(args):
    from core.config import get_market_config, save_market_config

    if getattr(args, "interactive", False):
        m = get_market_config()
        print("=== A-Stock Agents 券商交易费率向导配置 ===")
        print(f"当前配置状态: {'[已确认]' if m['is_user_configured'] else '[使用默认值(未确认)]'}")
        print(f"  当前佣金率: {m['commission_rate']} (万{m['commission_rate']*10000:.1f})")
        print(f"  当前最低佣金: {m['min_commission']} 元 (免5填0.0)")
        print(f"  当前卖出印花税: {m['tax_rate_sell']} (万{m['tax_rate_sell']*10000:.1f})")
        print(f"  当前过户费率: {m['transfer_fee_rate']}")
        print("-" * 50)

        try:
            val_comm = input(f"请输入券商佣金率 [回车保持 {m['commission_rate']}]: ").strip()
            comm = float(val_comm) if val_comm else m["commission_rate"]

            val_min = input(f"请输入单笔最低佣金(元, 免5填0.0) [回车保持 {m['min_commission']}]: ").strip()
            min_c = float(val_min) if val_min else m["min_commission"]

            val_tax = input(f"请输入卖出印花税率 [回车保持 {m['tax_rate_sell']}]: ").strip()
            tax = float(val_tax) if val_tax else m["tax_rate_sell"]

            new_m = save_market_config(commission_rate=comm, min_commission=min_c, tax_rate_sell=tax, is_user_configured=True)
            print("✅ 费率配置已成功保存并即时生效！")
            print(f"  新佣金率: {new_m['commission_rate']} (万{new_m['commission_rate']*10000:.1f}) | 最低起收: {new_m['min_commission']}元")
        except Exception as e:
            print(f"❌ 配置失败: {e}")
        return

    has_update = (
        getattr(args, "commission", None) is not None
        or getattr(args, "min_commission", None) is not None
        or getattr(args, "tax", None) is not None
        or getattr(args, "transfer", None) is not None
    )

    if has_update:
        new_m = save_market_config(
            commission_rate=args.commission,
            min_commission=args.min_commission,
            tax_rate_sell=args.tax,
            transfer_fee_rate=args.transfer,
            is_user_configured=True,
        )
        if getattr(args, "json", False):
            print(json.dumps(new_m, ensure_ascii=False, indent=2))
        else:
            print("✅ 券商交易费率配置已成功更新并持久化至 config.yaml：")
            print(f"  - 券商佣金率: {new_m['commission_rate']} (万{new_m['commission_rate']*10000:.2f})")
            print(f"  - 最低单笔佣金: {new_m['min_commission']:.1f} 元 {'(已启用免五规则)' if new_m['min_commission'] <= 0 else '(最低起收)'}")
            print(f"  - 卖出印花税率: {new_m['tax_rate_sell']} (万{new_m['tax_rate_sell']*10000:.1f})")
            print(f"  - 过户费率: {new_m['transfer_fee_rate']}")
    else:
        m = get_market_config()
        if getattr(args, "json", False):
            print(json.dumps(m, ensure_ascii=False, indent=2))
        else:
            print("=== 当前券商交易费率配置 ===")
            print(f"  - 券商佣金率: {m['commission_rate']} (万{m['commission_rate']*10000:.2f})")
            print(f"  - 最低单笔佣金: {m['min_commission']:.1f} 元 {'(已启用免五规则)' if m['min_commission'] <= 0 else '(最低起收)'}")
            print(f"  - 卖出印花税率: {m['tax_rate_sell']} (万{m['tax_rate_sell']*10000:.1f})")
            print(f"  - 过户费率: {m['transfer_fee_rate']}")


def cmd_skill_list(args):
    """列出注册的 Skills"""
    skills_dir = PROJECT_ROOT / "skills"
    if not skills_dir.exists():
        print("未找到 skills 目录")
        return
    skills = [d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if getattr(args, "json", False):
        print(json.dumps({"skills": sorted(skills)}, ensure_ascii=False, indent=2))
    else:
        print(f"=== A-Stock Agents 已注册技能模块 ({len(skills)} 个) ===")
        for s in sorted(skills):
            print(f"  - {s}")


def cmd_report(args):
    """生成 HTML 量化诊断报告"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all, gap_analysis
    from core.models.combo_scorer import ComboScorer, entry_assessment
    from core.reporting.report_generator import generate_simple_report


    bridge = DataBridge()
    code = args.code
    quote = bridge.get_realtime_quote(code)
    name = quote.get("name", code) if quote else code
    klines = bridge.tencent_kline(code, count=120)
    if not klines:
        print(f"错误: 无法获取 {code} 行情数据生成报告")
        return

    tech = calc_all(klines)
    scorer = ComboScorer()
    scores = scorer.score_full(klines, tech["latest"])
    entry = entry_assessment(klines, tech["latest"])
    gaps = gap_analysis(klines)

    data = {
        "code": code,
        "name": name,
        "quote": quote,
        "scores": scores,
        "technical_latest": tech["latest"],
        "entry": entry,
        "gaps": gaps,
    }
    out_dir = OUTPUT_REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output or str(out_dir / f"aStocks_{code}_{datetime.now():%Y%m%d}.html")
    generate_simple_report(data, out_path)
    if getattr(args, "json", False):
        print(json.dumps({"status": "success", "report_path": out_path, "code": code, "name": name}, ensure_ascii=False, indent=2))
    else:
        print(f"量化诊断 HTML 报告已成功生成: {out_path}")


# ═══════════════════════════════════════════════════
#  主入口与参数解析器构建
# ═══════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    parser = argparse.ArgumentParser(
        description="A-Stock Agents CLI — 统一 A 股量化投研与智能体入口",
        parents=[common_parser],
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # quote
    p_quote = subparsers.add_parser("quote", help="实时行情快照", parents=[common_parser])
    p_quote.add_argument("code", help="股票代码，如 600519")

    # technical
    p_tech = subparsers.add_parser("technical", help="经典技术指标与缺口", parents=[common_parser])
    p_tech.add_argument("code", help="股票代码")
    p_tech.add_argument("--count", type=int, default=120, help="K线数量 (默认 120)")
    p_tech.add_argument("--board-chg", type=float, default=None, help="板块涨跌幅")
    p_tech.add_argument("--board-top10", action="store_true", help="板块前10")
    p_tech.add_argument("--short", action="store_true", help="短线模式")

    # score
    p_score = subparsers.add_parser("score", help="量化策略综合评分", parents=[common_parser])
    p_score.add_argument("code", help="股票代码")
    p_score.add_argument("--count", type=int, default=120)
    p_score.add_argument("--board-chg", type=float, default=None)
    p_score.add_argument("--board-top10", action="store_true")
    p_score.add_argument("--short", action="store_true")

    # analyze
    p_ana = subparsers.add_parser("analyze", help="全维度大盘与个股诊断", parents=[common_parser])
    p_ana.add_argument("code", help="股票代码")
    p_ana.add_argument("--count", type=int, default=120)
    p_ana.add_argument("--board-chg", type=float, default=None)
    p_ana.add_argument("--board-top10", action="store_true")
    p_ana.add_argument("--short", action="store_true")

    # trapped
    p_trapped = subparsers.add_parser("trapped", help="解套量化分析与决策树", parents=[common_parser])
    p_trapped.add_argument("code", help="股票代码，如 600760")
    p_trapped.add_argument("--cost", type=float, required=True, help="持仓平均成本")
    p_trapped.add_argument("--shares", type=int, required=True, help="持仓股数")
    p_trapped.add_argument("--count", type=int, default=250, help="分析K线数量")

    # market
    subparsers.add_parser("market", help="五维大盘健康度评估", parents=[common_parser])

    # batch
    p_batch = subparsers.add_parser("batch", help="批量实时行情快照", parents=[common_parser])
    p_batch.add_argument("codes", help="股票代码列表，逗号分隔 (如 600519,000858,601318)")

    # deploy-monitor
    subparsers.add_parser("deploy-monitor", help="查看监控部署指南", parents=[common_parser])

    # screen
    p_screen = subparsers.add_parser("screen", help="三层漏斗选股", parents=[common_parser])
    p_screen.add_argument("codes", nargs="?", default="", help="标的代码列表 (逗号分隔)")
    p_screen.add_argument("--codes", dest="opt_codes", default=None, help="标的代码列表选项传参")
    p_screen.add_argument("--cyq", action="store_true", help="拉取筹码分布")
    p_screen.add_argument("--limit", type=int, default=10, help="最多展示数量")

    # risk
    p_risk = subparsers.add_parser("risk", help="风控止损与卖点预警", parents=[common_parser])
    p_risk.add_argument("code", help="股票代码")
    p_risk.add_argument("--entry", type=float, default=None, help="入场基准价")
    p_risk.add_argument("--cost", type=float, default=None, help="持仓成本")
    p_risk.add_argument("--current-value", type=float, default=0, help="当前市值")
    p_risk.add_argument("--peak", type=float, default=0, help="最高市值")
    p_risk.add_argument("--count", type=int, default=120)

    # golden-cross
    p_gc = subparsers.add_parser("golden-cross", help="MACD二次金叉检测", parents=[common_parser])
    p_gc.add_argument("code", help="股票代码")
    p_gc.add_argument("--count", type=int, default=120)

    # events
    p_ev = subparsers.add_parser("events", help="个股重要事件公告", parents=[common_parser])
    p_ev.add_argument("code", help="股票代码")
    p_ev.add_argument("--name", default="", help="股票名称")

    # cyq
    p_cyq = subparsers.add_parser("cyq", help="筹码分布特征", parents=[common_parser])
    p_cyq.add_argument("code", help="股票代码")

    # balance
    subparsers.add_parser("balance", help="代理余额与数据源查询", parents=[common_parser])

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="策略综合评估 (单股量化诊断 / 历史走势扫描)", parents=[common_parser])
    p_eval.add_argument("code", nargs="?", default=None, help="股票代码")
    p_eval.add_argument("--auto", action="store_true", help="历史走势自动扫描模式")
    p_eval.add_argument("--entries", help='JSON格式历史持仓 [{"date":"...","price":...,"action":"..."}]')
    p_eval.add_argument("--entries-file", help="持仓JSON文件路径")
    p_eval.add_argument("--interval", type=int, default=20, help="自动扫描间隔(天)")
    p_eval.add_argument("--count", type=int, default=250, help="K线数量")
    p_eval.add_argument("--days", dest="count", type=int, help="扫描天数 (同 --count)")


    # backtest
    p_bt = subparsers.add_parser("backtest", help="单标的回测评估 (夏普/回撤/胜率/过拟合)", parents=[common_parser])
    p_bt.add_argument("code", help="股票代码")
    p_bt.add_argument("--strategy", choices=["sma_cross", "combo_score"], default="sma_cross", help="策略选择")
    p_bt.add_argument("--count", type=int, default=250, help="K线数量")
    p_bt.add_argument("--cash", type=float, default=1000000, help="初始本金")
    p_bt.add_argument("--split", action="store_true", help="样本内外过拟合检验")

    # multi-backtest
    p_mbt = subparsers.add_parser("multi-backtest", help="多标的事件驱动轮动回测", parents=[common_parser])
    p_mbt.add_argument("--symbols", default=None, help="标的池代码列表，逗号分隔")
    p_mbt.add_argument("--days", type=int, default=250, help="回测交易日数 (默认 250)")
    p_mbt.add_argument("--top", type=int, default=4, help="持仓轮动槽位数 (默认 4)")
    p_mbt.add_argument("--cash", type=float, default=1000000.0, help="初始本金 (默认 1000000)")

    # multi-factor
    p_mf = subparsers.add_parser("multi-factor", help="多因子Alpha评分", parents=[common_parser])
    p_mf.add_argument("code", help="股票代码")
    p_mf.add_argument("--count", type=int, default=120)
    p_mf.add_argument("--pe", type=float, default=None)
    p_mf.add_argument("--pb", type=float, default=None)

    # portfolio-risk
    p_pr = subparsers.add_parser("portfolio-risk", help="组合风险与集中度评估", parents=[common_parser])
    p_pr.add_argument("--holdings", help="持仓JSON文件路径")
    p_pr.add_argument("--pnl", type=float, default=0, help="组合浮亏比例")

    # mean-reversion
    p_mr = subparsers.add_parser("mean-reversion", help="均值回归策略回测", parents=[common_parser])
    p_mr.add_argument("code", help="股票代码")
    p_mr.add_argument("--count", type=int, default=120)

    # grid
    p_grid = subparsers.add_parser("grid", help="网格交易策略区间构建与模拟", parents=[common_parser])
    p_grid.add_argument("code", help="股票代码")
    p_grid.add_argument("--count", type=int, default=120)
    p_grid.add_argument("--cash", type=float, default=1000000)

    # vol-breakout
    p_vb = subparsers.add_parser("vol-breakout", help="波动率突破策略回测", parents=[common_parser])
    p_vb.add_argument("code", help="股票代码")
    p_vb.add_argument("--count", type=int, default=120)

    # action
    p_action = subparsers.add_parser("action", help="实战交易反应动作决策单", parents=[common_parser])
    p_action.add_argument("code", nargs="?", default=None, help="股票代码")
    p_action.add_argument("--code", dest="opt_code", default=None, help="股票代码 (选项传参)")
    p_action.add_argument("--cost", type=float, default=None, help="持仓成本")
    p_action.add_argument("--shares", type=int, default=None, help="持仓股数")
    p_action.add_argument("--count", type=int, default=120)

    # intent
    p_intent = subparsers.add_parser("intent", help="自然语言意图智能解析", parents=[common_parser])
    p_intent.add_argument("query", help="用户输入的自然语言句子")

    # downside
    p_down = subparsers.add_parser("downside", help="五类下跌场景化精准诊断", parents=[common_parser])
    p_down.add_argument("code", help="股票代码")
    p_down.add_argument("--cost", type=float, default=None, help="持仓成本")
    p_down.add_argument("--shares", type=int, default=None, help="持仓股数")
    p_down.add_argument("--count", type=int, default=120)

    # report
    p_report = subparsers.add_parser("report", help="生成 HTML 量化诊断报告", parents=[common_parser])
    p_report.add_argument("code", help="股票代码")
    p_report.add_argument("--output", default=None, help="报告保存路径")

    # config
    p_cfg = subparsers.add_parser("config", help="配置与环境数据隔离管理", parents=[common_parser])
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd")
    cfg_sub.add_parser("paths", help="查看生效路径隔离", parents=[common_parser])
    p_mkt = cfg_sub.add_parser("market", help="查看/修改券商费率配置", parents=[common_parser])
    p_mkt.add_argument("--commission", type=float, default=None, help="佣金率 (如 0.00025)")
    p_mkt.add_argument("--min-commission", type=float, default=None, help="最低佣金 (免5填0.0)")
    p_mkt.add_argument("--tax", type=float, default=None, help="印花税率 (如 0.0005)")
    p_mkt.add_argument("--transfer", type=float, default=None, help="过户费率")
    p_mkt.add_argument("--interactive", action="store_true", help="交互式向导配置")

    # pool
    p_pool = subparsers.add_parser("pool", help="自选股与关注股池管理", parents=[common_parser])
    pool_sub = p_pool.add_subparsers(dest="pool_cmd")
    p_pool_list = pool_sub.add_parser("list", help="查看股票池", parents=[common_parser])
    p_pool_list.add_argument("--pool", choices=["selected", "watch"], default=None)

    # position
    p_pos = subparsers.add_parser("position", help="实盘与模拟持仓管理", parents=[common_parser])
    pos_sub = p_pos.add_subparsers(dest="pos_cmd")
    p_pos_list = pos_sub.add_parser("list", help="查看持仓列表", parents=[common_parser])
    p_pos_list.add_argument("--history", action="store_true", help="查看平仓历史")
    pos_sub.add_parser("pnl", help="查看持仓盈亏汇总", parents=[common_parser])
    pos_sub.add_parser("snapshot", help="生成持仓风控快照", parents=[common_parser])

    # data
    p_data = subparsers.add_parser("data", help="底层数据直连命令", parents=[common_parser])
    data_sub = p_data.add_subparsers(dest="data_cmd")
    p_data_q = data_sub.add_parser("quote", help="获取实时行情", parents=[common_parser])
    p_data_q.add_argument("codes", nargs="+", help="股票代码列表")
    p_data_t = data_sub.add_parser("tech", help="获取技术指标", parents=[common_parser])
    p_data_t.add_argument("code", help="股票代码")
    p_data_t.add_argument("--count", type=int, default=120)

    # skill
    p_skill = subparsers.add_parser("skill", help="查看已注册技能模块", parents=[common_parser])
    skill_sub = p_skill.add_subparsers(dest="skill_cmd")
    skill_sub.add_parser("list", help="列出技能列表", parents=[common_parser])

    # version
    subparsers.add_parser("version", help="显示平台版本信息", parents=[common_parser])

    return parser



def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 命令路由表
    cmd = args.command

    if cmd == "quote":
        cmd_data_quote(args)
    elif cmd == "technical":
        cmd_data_technical(args)
    elif cmd == "score":
        cmd_score(args)
    elif cmd == "analyze":
        cmd_analyze(args)
    elif cmd == "trapped":
        cmd_trapped(args)
    elif cmd == "market":
        cmd_market(args)
    elif cmd == "batch":
        cmd_batch(args)
    elif cmd == "deploy-monitor":
        cmd_deploy_monitor(args)
    elif cmd == "screen":
        if getattr(args, "opt_codes", None):
            args.codes = args.opt_codes
        cmd_screen(args)
    elif cmd == "risk":
        cmd_risk(args)
    elif cmd == "golden-cross":
        cmd_golden_cross(args)
    elif cmd == "events":
        cmd_events(args)
    elif cmd == "cyq":
        cmd_cyq(args)
    elif cmd == "balance":
        cmd_balance(args)
    elif cmd == "evaluate":
        cmd_evaluate(args)
    elif cmd == "backtest":
        cmd_backtest(args)
    elif cmd == "multi-backtest":
        cmd_multi_backtest(args)
    elif cmd == "multi-factor":
        cmd_multi_factor(args)
    elif cmd == "portfolio-risk":
        cmd_portfolio_risk(args)
    elif cmd == "mean-reversion":
        cmd_mean_reversion(args)
    elif cmd == "grid":
        cmd_grid(args)
    elif cmd == "vol-breakout":
        cmd_vol_breakout(args)
    elif cmd == "action":
        if getattr(args, "opt_code", None):
            args.code = args.opt_code
        cmd_action_plan(args)
    elif cmd == "intent":
        cmd_intent(args)
    elif cmd == "downside":
        cmd_downside(args)
    elif cmd == "report":
        cmd_report(args)
    elif cmd == "config":
        if getattr(args, "config_cmd", None) == "paths":
            cmd_config_paths(args)
        else:
            cmd_config_market(args)
    elif cmd == "pool":
        from core.strategy import pool_manager

        pool_cmd = getattr(args, "pool_cmd", None)
        if pool_cmd == "list" or not pool_cmd:
            pool_manager.cmd_list(args)
        else:
            parser.print_help()
    elif cmd == "position":
        from core.strategy import position_manager

        pos_cmd = getattr(args, "pos_cmd", None)
        if pos_cmd == "list" or not pos_cmd:
            position_manager.cmd_list(args)
        elif pos_cmd == "pnl":
            position_manager.cmd_pnl(args)
        elif pos_cmd == "snapshot":
            position_manager.cmd_snapshot(args)
        else:
            parser.print_help()
    elif cmd == "data":
        data_cmd = getattr(args, "data_cmd", None)
        if data_cmd == "quote":
            cmd_data_quote(args)
        elif data_cmd == "tech":
            cmd_data_technical(args)
        else:
            parser.print_help()
    elif cmd == "skill":
        if getattr(args, "skill_cmd", None) == "list":
            cmd_skill_list(args)
        else:
            parser.print_help()
    elif cmd == "version":
        if getattr(args, "json", False):
            print(json.dumps({"platform": "A-Stock Agents", "version": "2.0.0", "status": "active"}, ensure_ascii=False, indent=2))
        else:
            print("A-Stock Agents Platform CLI v2.0.0 — 统一量化投研与智能体架构")
    else:
        parser.print_help()



if __name__ == "__main__":
    main()
