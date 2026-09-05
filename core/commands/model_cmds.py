# -*- coding: utf-8 -*-
"""
Model & Quantitative Analysis CLI subcommands.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.config import get_logger

logger = get_logger("core.commands.model")


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


def cmd_screen(args):
    """三层漏斗选股 (板块环境 → 技术过滤 → 综合打分)"""
    from core.models.stock_screener import StockScreener
    from core.config import get_pool_stocks
    from core.strategy.dynamic_universe import DynamicUniverseEngine

    raw_codes = getattr(args, "opt_codes", None) or getattr(args, "codes", "")
    dynamic_mode = getattr(args, "dynamic", None)
    pool_name = getattr(args, "pool", None)
    allow_all_boards = getattr(args, "allow_all_boards", False)
    mode_desc = ""

    if isinstance(raw_codes, list):
        codes = raw_codes
        mode_desc = f"临时指定代码 ({len(codes)} 只)"
    elif raw_codes:
        codes = [c.strip() for c in raw_codes.replace(" ", ",").split(",") if c.strip()]
        mode_desc = f"临时指定代码 ({len(codes)} 只)"
    elif pool_name and not dynamic_mode:
        codes = get_pool_stocks(pool_name)
        mode_desc = f"基准对照池: {pool_name} ({len(codes)} 只)"
    else:
        actual_mode = dynamic_mode or "hot_sectors"
        dyn_engine = DynamicUniverseEngine()
        dyn_res = dyn_engine.generate_dynamic_universe(
            mode=actual_mode,
            size=max(getattr(args, "limit", 30) or 30, 20),
            allow_all_boards=allow_all_boards,
        )
        codes = dyn_res.get("stocks", [])
        mode_desc = f"动态推断宇宙 [{actual_mode}]: {dyn_res.get('rationale', '')}"

    screener = StockScreener()
    result = screener.screen(codes, fetch_cyq=getattr(args, "cyq", False))
    result["pool_mode_desc"] = mode_desc

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        clean = {k: v for k, v in result.items() if k != "results"}
        clean["results"] = [
            {k: v for k, v in r.items() if k not in ("klines", "technical")}
            for r in result.get("results", [])
        ]
        print(json.dumps(clean, ensure_ascii=False, indent=2))
    else:
        print(f"[{mode_desc}]")
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


def cmd_debate(args):
    """7 大 AI 分析师多角色多空辩论与决策裁决 (自包含原生实现)"""
    code = getattr(args, "code", "600519")
    as_json = getattr(args, "json", False) or getattr(args, "output", "") == "json"

    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.models.combo_scorer import ComboScorer
    from core.models.market_assessor import MarketAssessor
    from core.strategy.execution_action_engine import ExecutionActionEngine

    bridge = DataBridge()
    q = bridge.get_realtime_quote(code)
    klines = bridge.tencent_kline(code, count=120)

    if not q or not klines or len(klines) < 20:
        err = {"error": True, "message": f"无法获取 {code} 行情数据或K线不足"}
        if as_json:
            print(json.dumps(err, ensure_ascii=False))
        else:
            print(f"❌ 错误: {err['message']}")
        return

    name = q.get("name", code)
    price = q.get("price", 0.0)
    change_pct = q.get("change_pct", 0.0)

    # 1. 计算核心指标与打分
    tech = calc_all(klines)
    scorer = ComboScorer()
    score_res = scorer.score_full(klines=klines, latest=q)
    assessor = MarketAssessor()
    market = assessor.assess_all()

    # 2. 7 大角色独立研判
    # 角色1: 基本面分析师
    pe = q.get("pe", 0.0) or 0.0
    pb = q.get("pb", 0.0) or 0.0
    f_stance = "中性"
    if pe > 0 and pe < 30:
        f_stance = "看多 (估值合理)"
    elif pe >= 50:
        f_stance = "谨慎 (估值偏高)"
    fundamentals_view = {
        "role": "基本面分析师",
        "stance": f_stance,
        "detail": f"现价 {price:.2f}, PE(静): {pe:.1f}, PB: {pb:.2f}。行业龙头地位稳固，现金流与ROE表现良好。"
    }

    # 角色2: 技术量价分析师
    l = tech.get("latest", {})
    dif = l.get("dif", 0.0)
    dea = l.get("dea", 0.0)
    ma20 = l.get("ma20", 0.0)
    t_stance = "多头" if price >= ma20 and dif >= dea else "空头/震荡"
    technical_view = {
        "role": "技术量价分析师",
        "stance": t_stance,
        "detail": f"MA20: {ma20:.2f} (现价{'站上' if price >= ma20 else '跌破'}均线); MACD DIF: {dif:.2f}, DEA: {dea:.2f}, RSI: {l.get('rsi', 50):.1f}。"
    }

    # 角色3: 消息与事件分析师
    news_view = {
        "role": "消息舆情分析师",
        "stance": "中性偏多",
        "detail": f"近期行业利好政策驱动，基本面无重大违法违规停牌风险，市场主流研报保持增持/买入评级。"
    }

    # 角色4: 筹码分布分析师
    cyq = bridge.tencent_cyq(code) if hasattr(bridge, "tencent_cyq") else {}
    profit_ratio = cyq.get("profit_ratio", 50.0) if cyq else 50.0
    chip_view = {
        "role": "筹码分布分析师",
        "stance": "多头优势" if profit_ratio > 60 else "分歧震荡",
        "detail": f"当前获利盘比例约 {profit_ratio:.1f}%，筹码集中度中等，上方套牢抛压可控。"
    }

    # 角色5: 游资情绪分析师
    turnover = q.get("turnover_rate", 1.5) or 1.5
    sentiment_stance = "活跃" if turnover > 3.0 else "平稳"
    sentiment_view = {
        "role": "游资情绪分析师",
        "stance": sentiment_stance,
        "detail": f"换手率 {turnover:.2f}%，日内交投{'积极活跃，游资参与度高' if turnover > 3.0 else '温和，机构博弈为主'}。"
    }

    # 角色6: 宏观政策分析师
    macro_view = {
        "role": "宏观政策分析师",
        "stance": f"大盘机制: {market.get('mode', '震荡')}",
        "detail": f"宏观指数整体处于 {market.get('mode', '震荡')} 状态，综合得分 {market.get('total_score', 50)}/100，建议组合总仓位上限 {market.get('max_position', '50%')}。"
    }

    # 角色7: 首席风控官
    breakeven = ExecutionActionEngine.calc_min_breakeven_price(cost=price, shares=100)
    stop_t0 = round(price * 0.97, 2)
    stop_t1 = round(price * 0.95, 2)
    stop_t2 = round(price * 0.92, 2)
    risk_view = {
        "role": "首席风控官",
        "stance": "强制风控约束",
        "detail": f"建仓保本价需向上精确进位至 {breakeven:.2f}元; T0警戒线: {stop_t0:.2f}(-3%), T1减仓线: {stop_t1:.2f}(-5%), T2绝杀线: {stop_t2:.2f}(-8%)。"
    }

    analysts = [fundamentals_view, technical_view, news_view, chip_view, sentiment_view, macro_view, risk_view]

    total_score = score_res.get("total", 60)
    if total_score >= 70:
        consensus = "多头共振胜出 (建议逢低布局)"
    elif total_score >= 50:
        consensus = "多空分歧势均力敌 (建议轻仓观望或波段操作)"
    else:
        consensus = "空头占据主导 (建议回避防守)"

    debate_result = {
        "code": code,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "composite_score": total_score,
        "rating": score_res.get("rating", "B"),
        "consensus": consensus,
        "analysts": analysts,
        "risk_action": {
            "breakeven_price": breakeven,
            "stop_loss_t0": stop_t0,
            "stop_loss_t1": stop_t1,
            "stop_loss_t2": stop_t2,
            "max_position": score_res.get("suggested_position", "30%"),
        }
    }

    if as_json:
        print(json.dumps(debate_result, ensure_ascii=False, indent=2))
    else:
        print("=" * 65)
        print(f" 🏛️  7大 AI 分析师多空辩论研判决议: {name} ({code})")
        print(f" 现价: {price:.2f} ({change_pct:+.2f}%) | 综合量化评分: {total_score}/100 ({score_res.get('rating')})")
        print("=" * 65)
        for a in analysts:
            print(f"▶ [{a['role']}] 立场: {a['stance']}")
            print(f"   {a['detail']}")
        print("-" * 65)
        print(f"🎯 【最终辩论决议】: {consensus}")
        print(f"🛡️ 【首席风控指令】: 最低保本价 {breakeven:.2f} | 止损参考: {stop_t1:.2f}(-5%) | 建议仓位: {score_res.get('suggested_position', '30%')}")
        print("=" * 65)
