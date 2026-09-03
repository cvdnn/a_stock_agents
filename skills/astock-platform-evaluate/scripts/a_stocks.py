#!/usr/bin/env python3
"""
aStocks — 统一A股分析平台 CLI

A股全流程：数据桥接 → 技术分析 → 策略评分 → 解套方案 → 市场研判 → 监控部署

用法:
  python3 a_stocks.py quote 600519           # 实时行情
  python3 a_stocks.py technical 600519       # 技术指标
  python3 a_stocks.py score 600519           # 策略评分
  python3 a_stocks.py analyze 600519         # 全维度分析
  python3 a_stocks.py trapped 600760 --cost 43 --shares 2200  # 解套分析
  python3 a_stocks.py market                 # 大盘健康度
  python3 a_stocks.py batch 600519,000400,002230  # 批量行情
  python3 a_stocks.py deploy-monitor         # 部署监控
  python3 a_stocks.py evaluate 600519 --auto --interval 30  # 策略评估
  python3 a_stocks.py screen "600519,..."     # 三层漏斗选股
"""

import json
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))


def cmd_quote(args):
    """实时行情"""
    from data_bridge import DataBridge
    bridge = DataBridge()
    result = bridge.get_realtime_quote(args.code)
    if not result:
        print(json.dumps({"error": f"无法获取 {args.code} 行情"}, ensure_ascii=False))
        return
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result.get('name', args.code)}({result.get('code')})")
        print(f"  现价: {result['price']}  涨跌: {result['change_pct']:+.2f}%")
        print(f"  PE: {result.get('pe', 'N/A')}  换手: {result.get('turnover_pct', 'N/A')}%")
        print(f"  日内: {result.get('low')} ~ {result.get('high')}")


def cmd_technical(args):
    """技术指标"""
    from data_bridge import DataBridge
    from technical_indicators import calc_all, gap_analysis
    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines or len(klines) < 26:
        print(json.dumps({"error": f"K线数据不足 ({len(klines)}根)"}, ensure_ascii=False))
        return
    tech = calc_all(klines)
    gaps = gap_analysis(klines)
    output = {"code": args.code, "technical": tech, "gaps": gaps}
    if args.output == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        l = tech["latest"]
        print(f"{args.code} 技术指标 (K线{len(klines)}根)")
        print(f"  收盘: {l['close']}")
        print(f"  MA5/10/20/60: {l.get('ma5', 'N/A')}/{l.get('ma10', 'N/A')}/{l.get('ma20', 'N/A')}/{l.get('ma60', 'N/A')}")
        print(f"  MACD DIF/DEA/Bar: {l.get('dif', 'N/A')}/{l.get('dea', 'N/A')}/{l.get('macd_bar', 'N/A')}")
        print(f"  KDJ K/D/J: {l.get('kdj_k', 'N/A')}/{l.get('kdj_d', 'N/A')}/{l.get('kdj_j', 'N/A')}")
        print(f"  RSI: {l.get('rsi', 'N/A')}  ATR: {l.get('atr', 'N/A')}")
        print(f"  BOLL: {l.get('boll_lower', 'N/A')} ~ {l.get('boll_upper', 'N/A')}")
        if gaps["gaps"]:
            print(f"  近10日跳空: {gaps['count']}次, 连续同向{gaps['consecutive_same']}次")


def cmd_score(args):
    """策略评分"""
    from data_bridge import DataBridge
    from technical_indicators import calc_all
    from combo_scorer import ComboScorer, entry_assessment
    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines or len(klines) < 26:
        print(json.dumps({"error": f"K线数据不足"}, ensure_ascii=False))
        return
    tech = calc_all(klines)
    scorer = ComboScorer()
    scores = scorer.score_full(klines, tech["latest"], args.board_chg or 0, args.board_top10, args.short)
    entry = entry_assessment(klines, tech["latest"])
    output = {"code": args.code, "scores": scores, "entry": entry}
    if args.output == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"{args.code} 策略评分")
        for dim, info in scores.items():
            if isinstance(info, dict) and "score" in info and "max" in info:
                print(f"  {dim}: {info['score']}/{info['max']} {info['reason']}")
        print(f"  ───────────────────")
        print(f"  总分: {scores['total']}/{scores['max_total']} 评级: {scores['rating']} → {scores['rating_text']}")
        print(f"  建议仓位: {scores['suggested_position']}")
        print(f"  {entry['distance_text']}")
        print(f"  止损位: {entry['stop_loss']} (约 -{entry['stop_loss_pct']:.1f}%)")


def cmd_analyze(args):
    """全维度分析"""
    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  aStocks 全维度分析: {args.code}                     ║")
    print(f"╚══════════════════════════════════════════════════╝")
    print()

    # 1. Market health
    print("─── 📊 大盘环境 ───")
    from market_assessor import MarketAssessor
    assessor = MarketAssessor()
    market = assessor.assess_all()
    print(f"  大盘模式: {market['mode']} (得分 {market['total_score']}/{market['max_score']})")
    print(f"  建议仓位上限: {market['max_position']}")
    for dim, info in market["dimensions"].items():
        print(f"  {dim}: {info['score']}/{info['max']} {info.get('reason', '')}")

    # 2. Quote & Technical
    print(f"\n─── 🔍 个股分析 ───")
    from data_bridge import DataBridge
    from technical_indicators import calc_all, gap_analysis
    bridge = DataBridge()
    quote = bridge.get_realtime_quote(args.code)
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines or len(klines) < 26:
        print("  ⚠️ K线数据不足")
        return

    tech = calc_all(klines)
    gaps = gap_analysis(klines)
    l = tech["latest"]

    if quote:
        print(f"  {quote.get('name', args.code)}({quote.get('code')}) {quote['price']} {quote['change_pct']:+.2f}%")
    print(f"  MA5/10/20/60: {l.get('ma5','N/A')}/{l.get('ma10','N/A')}/{l.get('ma20','N/A')}/{l.get('ma60','N/A')}")
    print(f"  MACD: DIF={l.get('dif','N/A')} DEA={l.get('dea','N/A')} Bar={l.get('macd_bar','N/A')}")
    print(f"  KDJ: K={l.get('kdj_k','N/A')} D={l.get('kdj_d','N/A')} J={l.get('kdj_j','N/A')}")
    print(f"  RSI: {l.get('rsi','N/A')}  ATR: {l.get('atr','N/A')}")
    if gaps["latest_gap"]:
        g = gaps["latest_gap"]
        print(f"  最近跳空: {g['date']} {g['direction']} {g['gap_pct']:+.2f}% {'已补' if g['filled'] else '未补'}")

    # 3. Strategy Score
    print(f"\n─── 📈 策略评分 ───")
    from combo_scorer import ComboScorer, entry_assessment
    scorer = ComboScorer()
    scores = scorer.score_full(klines, l, args.board_chg or 0, args.board_top10, args.short)
    entry = entry_assessment(klines, l)
    for dim, info in scores.items():
        if isinstance(info, dict) and "score" in info and "max" in info:
            print(f"  {dim}: {info['score']}/{info['max']} {info['reason']}")
    print(f"  总分: {scores['total']}/{scores['max_total']} 评级: {scores['rating']} → {scores['rating_text']}")
    print(f"  建议仓位: {scores['suggested_position']}")
    print(f"  {entry['distance_text']} (距MA20: {entry['pct_from_ma20']:+.1f}%)")
    print(f"  止损位: {entry['stop_loss']} (约 -{entry['stop_loss_pct']:.1f}%)")
    print(f"  触发条件: {'; '.join(entry['triggers'])}")


def cmd_trapped(args):
    """解套分析"""
    from data_bridge import DataBridge
    from trapped_position import TrappedPositionAnalyzer
    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines or len(klines) < 26:
        print(json.dumps({"error": "K线数据不足"}, ensure_ascii=False))
        return
    analyzer = TrappedPositionAnalyzer(args.cost, args.shares, klines)
    result = analyzer.analyze()
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        d = result["diagnostic"]
        dt = result["decision_tree"]
        print(f"╔══════════════════════════════════════════════════╗")
        print(f"║  持仓解套分析: {args.code}                              ║")
        print(f"╚══════════════════════════════════════════════════╝")
        print(f"  成本: ¥{d['cost_price']} × {d['shares']}股 = ¥{d['total_cost']:,.0f}")
        print(f"  现价: ¥{d['current_price']}  浮亏: ¥{d['unrealized_loss']:+,.0f} ({d['loss_pct']:+.1f}%)")
        print(f"  ATR(14): {d['atr_14']}  凯利 f*: {d['kelly_f']}")
        print(f"  {d['kelly_interpretation']}")
        print(f"\n  决策树: {dt['recommended']} — {dt['reason']}")
        for s in dt['strategies']:
            print(f"    → {s}")

        # 策略A详情
        a = result["strategy_a_ladder"]
        print(f"\n  策略A: 阶梯减仓 ({a['total_shares']}股, 每档{a['per_tier_shares']}股)")
        for t in a["tiers"]:
            print(f"    档{t['level']}: ¥{t['trigger_price']} ({t['label']})")

        # 策略B详情
        b = result["strategy_b_grid"]
        print(f"\n  策略B: 网格做T (ATR={b['atr']})")
        for g in b["grids"]:
            print(f"    格{g['grid']}: 买{g['buy']} → 卖{g['sell']} (+{g['profit_per_round']})")

        # 策略C详情
        c = result["strategy_c_replenish"]
        print(f"\n  策略C: 等额补仓 (需{c['required_pass']}个条件, 当前满足{c['actual_pass']})")
        for check, info in c["checks"].items():
            print(f"    {'✅' if info['passed'] else '❌'} {check}: {info['value']}")


def cmd_market(args):
    """大盘健康度"""
    from market_assessor import MarketAssessor
    assessor = MarketAssessor()
    result = assessor.assess_all()
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"╔══════════════════════════════════════════════════╗")
        print(f"║  大盘健康度评估                                    ║")
        print(f"╚══════════════════════════════════════════════════╝")
        print(f"  总分: {result['total_score']}/{result['max_score']}")
        print(f"  模式: {result['mode']}  建议仓位上限: {result['max_position']}")
        for dim, info in result["dimensions"].items():
            bar = "█" * info["score"] + "░" * (info["max"] - info["score"])
            print(f"  {dim:<12} [{bar}] {info['score']}/{info['max']}")
            print(f"             {info['reason']}")
        print(f"\n  指数:")
        for k, v in result.get("index_data", {}).items():
            chg = v.get("change_pct", 0)
            arrow = "↑" if chg > 0 else "↓"
            print(f"  {v.get('name', k):<8} {v.get('price', 'N/A')} {arrow} {chg:+.2f}%")


def cmd_batch(args):
    """批量行情"""
    from data_bridge import DataBridge
    codes = [c.strip() for c in args.codes.split(",")]
    bridge = DataBridge()
    results = bridge.fetch_batch_snapshot(codes)
    if args.output == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"{'代码':<8} {'名称':<10} {'现价':>7} {'涨跌%':>7} {'PE':>6} {'换手%':>6} {'市值':>10} {'外盘比':>6}")
        for r in results:
            chg_color = "🔴" if r.get("change_pct", 0) > 0 else "🟢"
            print(f"{r.get('code',''):<8} {r.get('name',''):<10} {r.get('price',0):>7.2f} "
                  f"{r.get('change_pct',0):>+6.2f}% {r.get('pe',0):>6.1f} {r.get('turnover_pct',0):>6.2f}% "
                  f"{r.get('market_cap',0):>10.1f} {r.get('o_ratio',0):>5.1f}% {chg_color}")


def cmd_deploy_monitor(args):
    """部署监控说明"""
    print("aStocks 监控部署")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("1. 复制监控模板:")
    print(f"   cp {SKILL_DIR}/scripts/monitor_watchdog.py ~/.AI-Platform/scripts/monitor_watchdog.py")
    print()
    print("2. 编辑配置 (修改 HOLDINGS, AVAILABLE_CASH):")
    print("   nano ~/.AI-Platform/scripts/monitor_watchdog.py")
    print()
    print("3. 部署 cron 任务:")
    print("   AI-Platform cron create --name '全天持仓监控' \\")
    print("     --script monitor_watchdog.py --schedule 'every 5m' \\")
    print("     --no-agent --workdir ~/.AI-Platform/scripts --deliver all")
    print()
    print("4. 测试运行:")
    print("   AI-Platform cron run <job_id>")


# ─── P0-P1 新增命令处理函数 ──────────────────────

def cmd_screen(args):
    """三层漏斗选股"""
    from stock_screener import StockScreener
    codes = [c.strip() for c in args.codes.split(",")]
    screener = StockScreener()
    result = screener.screen(codes, fetch_cyq=args.cyq)

    if args.output == "json":
        # 去klines后输出
        clean = {k: v for k, v in result.items() if k != "results"}
        clean["results"] = [{k: v for k, v in r.items() if k != "klines" and k != "technical"}
                            for r in result["results"]]
        print(json.dumps(clean, ensure_ascii=False, indent=2))
    else:
        print(f"输入: {result['total_input']} → 板块: {result['stage1_board']} "
              f"→ 技术: {result['stage2_technical']} → 评分: {result['stage3_scored']}")
        print()
        if result["results"]:
            print(f"{'评级':<4} {'代码':<8} {'名称':<10} {'总分':>5} {'现价':>7} {'涨跌%':>7} {'板块':<8}")
            for r in result["results"][:20]:
                s = r["scores"]
                chg = r.get("change_pct", 0)
                arrow = "↑" if chg > 0 else "↓"
                print(f"{s['rating']:<4} {r['code']:<8} {r['name']:<10} "
                      f"{s['total']:>5}/{s['effective_max']:<3} "
                      f"{r['price']:>7.2f} {chg:>+6.2f}% {arrow} "
                      f"{r.get('sector','-')[:6]:<8}")
        else:
            print("无候选通过筛选")


def cmd_risk(args):
    """风控分析"""
    from risk_manager import RiskManager
    from data_bridge import DataBridge
    from technical_indicators import calc_all

    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines or len(klines) < 26:
        print(json.dumps({"error": "K线数据不足"}))
        return

    tech = calc_all(klines)
    rm = RiskManager()
    entry_price = args.entry or float(klines[-1][2])

    result = {}
    result["stop_losses"] = rm.calc_stop_losses(entry_price, tech["latest"])
    result["sell_signals"] = rm.sell_signals(klines, tech["latest"])
    result["candle"] = rm.candle_pattern(klines)

    if args.cost and args.current_value:
        result["drawdown"] = rm.drawdown_control(args.current_value, args.peak or args.cost, args.cost)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        sl = result["stop_losses"]
        print(f"{args.code} 风控分析")
        print(f"  入场价: {entry_price}")
        print(f"  ─── 三级止损 ───")
        print(f"  T0 日内: {sl['t0_intraday']['price']} (-{sl['t0_intraday']['loss_pct']}%) → {sl['t0_intraday']['action']}")
        print(f"  T1 MA10: {sl['t1_ma10']['price']} (-{sl['t1_ma10']['loss_pct']}%) → {sl['t1_ma10']['action']}")
        print(f"  T2 MA20: {sl['t2_ma20']['price']} (-{sl['t2_ma20']['loss_pct']}%) → {sl['t2_ma20']['action']}")
        print()

        ss = result["sell_signals"]
        print(f"  ─── 卖点信号 ───")
        for s in ss.get("signals", []):
            print(f"  {s}")
        if not ss.get("signals"):
            print("  ✅ 无卖出信号")
        print()

        cp = result["candle"]
        print(f"  ─── 最近3日K线 ───")
        for k in cp.get("recent_3d", []):
            print(f"  {k['date']} O={k['open']} C={k['close']} {k['description']}")

        if "drawdown" in result:
            dd = result["drawdown"]
            print(f"\n  ─── 回撤控制 ───")
            print(f"  {dd['level']} {dd['action']} (回撤{dd['drawdown_from_peak_pct']:.1f}%)")


def cmd_golden_cross(args):
    """MACD二次金叉检测"""
    from data_bridge import DataBridge
    from technical_indicators import second_golden_cross

    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines or len(klines) < 60:
        print(json.dumps({"error": "至少需要60根K线"}))
        return

    result = second_golden_cross(klines)
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{args.code} MACD二次金叉检测")
        print(f"  判决: {result['verdict']} — {result['reason']}")
        print(f"  通过: {result['passed_count']}/{result['total_checks']}")
        if result.get("crosses_count", 0) >= 2:
            f = result.get("first_leg", {})
            s = result.get("second_leg", {})
            print(f"  第一脚 idx={f.get('idx')} DIF={f.get('dif')}")
            print(f"  第二脚 idx={s.get('idx')} DIF={s.get('dif')} DEA={s.get('dea')}")
            print(f"  DIF抬高: {result['dif_higher']}  红柱增强: {result['bars_stronger']}")
        print()
        for c in result.get("checklist", []):
            print(f"  {c}")


def cmd_events(args):
    """个股事件"""
    from data_bridge import DataBridge
    bridge = DataBridge()
    result = bridge.get_stock_events(args.code, args.name)
    if args.output == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print(f"{args.code} 个股事件")
        if result:
            text = result.get("text", str(result))
            print(text[:2000])
        else:
            print("  无事件数据（需 proxy-patch 模式）")


def cmd_cyq(args):
    """筹码分布"""
    from data_bridge import DataBridge
    bridge = DataBridge()
    result = bridge.get_cyq(args.code)
    if args.output == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print(f"{args.code} 筹码分布")
        if result:
            print(f"  获利比例: {result.get('profit_ratio', 'N/A')}")
            print(f"  平均成本: {result.get('avg_cost', 'N/A')}")
            print(f"  90%集中度: {result.get('concentration_90', 'N/A')}")
            print(f"  70%集中度: {result.get('concentration_70', 'N/A')}")
            conc = result.get('concentration_90', 0)
            if conc < 0.10:
                print(f"  判断: 高度集中，主力控盘 ⭐")
            elif conc < 0.13:
                print(f"  判断: 筹码集中")
            elif conc < 0.15:
                print(f"  判断: 中性")
            else:
                print(f"  判断: 筹码发散")
        else:
            print("  无数据（需 proxy-patch 模式 + venv Python）")


def cmd_balance(args):
    """代理积分余额"""
    from data_bridge import DataBridge
    bridge = DataBridge()
    result = bridge.check_proxy_balance()
    if args.output == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print("代理积分余额:")
        print(f"  {result or '查询失败（需 a-share-data skill 就绪）'}")


def cmd_evaluate(args):
    """持股策略评估"""
    from strategy_evaluator import StrategyEvaluator, auto_scan
    if args.auto:
        report = auto_scan(args.code, interval_days=args.interval or 20, kline_count=args.count)
    elif args.entries:
        entries = json.loads(args.entries)
        evaluator = StrategyEvaluator()
        report = evaluator.evaluate(args.code, entries)
    elif args.entries_file:
        entries = json.loads(Path(args.entries_file).read_text())
        evaluator = StrategyEvaluator()
        report = evaluator.evaluate(args.code, entries)
    else:
        print("请指定 --auto (自动扫描) 或 --entries (历史持仓)")
        return

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
            print(f"{'日期':<12} {'价格':>7} {'评级':<4} {'评分':>6} {'距MA20%':>7} {'5日收益':>8} {'方向':<4}")
            for e in report.entries[:20]:
                direction = "✅" if e.get("direction_correct") is True else ("❌" if e.get("direction_correct") is False else "-")
                ret5 = f"{e.get('ret_5d', 0):+.2f}%" if e.get('ret_5d') is not None else "N/A"
                print(f"{e['date']:<12} {e['entry_price']:>7.2f} {e['rating']:<4} {e['score']:>6} "
                      f"{e.get('pct_from_ma20', 0):>+6.1f}% {ret5:>8} {direction:<4}")


# ─── P2-P3 量化策略命令 ──────────────────────────────

def cmd_backtest(args):
    """回测评估"""
    from data_bridge import DataBridge
    from backtest_engine import BacktestEngine, sma_cross_strategy, combo_score_strategy

    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines or len(klines) < 30:
        print(json.dumps({"error": "K线数据不足"}, ensure_ascii=False))
        return

    engine = BacktestEngine(initial_cash=args.cash)
    strategy = sma_cross_strategy if args.strategy == "sma_cross" else combo_score_strategy

    if args.split:
        in_sample, out_sample = engine.split_sample(klines)
        in_result = engine.run_strategy(in_sample, strategy)
        out_result = engine.run_strategy(out_sample, strategy)
        in_m = in_result["metrics"]
        out_m = out_result["metrics"]
        overfit = (in_m["sharpe_ratio"] > 3 and in_m["max_drawdown"] < 5 and in_m["win_rate"] > 75)
        output = {
            "code": args.code,
            "in_sample": in_m,
            "out_sample": out_m,
            "overfitting_check": {
                "in_sample_sharpe": in_m["sharpe_ratio"],
                "out_sample_sharpe": out_m["sharpe_ratio"],
                "overfitting_suspected": overfit,
                "warning": "疑似过拟合: 夏普>3+回撤<5%+胜率>75%" if overfit else "未见明显过拟合",
            },
        }
    else:
        result = engine.run_strategy(klines, strategy)
        output = {
            "code": args.code,
            "strategy": args.strategy,
            "metrics": result["metrics"],
            "trades_count": len(result["trades"]),
            "sample_trades": result["trades"][:5],
        }

    if args.output == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        m = output.get("metrics", output.get("in_sample", {}))
        print(f"{'代码':<8} {'策略':<12} {'年化收益':>8} {'夏普':>6} {'最大回撤':>8} {'胜率':>6} {'盈亏比':>6} {'Calmar':>6}")
        print(f"{args.code:<8} {args.strategy:<12} {m.get('annual_return',0):>7.2f}% "
              f"{m.get('sharpe_ratio',0):>6.2f} {m.get('max_drawdown',0):>7.2f}% "
              f"{m.get('win_rate',0):>5.1f}% {m.get('profit_factor',0):>6.2f} "
              f"{m.get('calmar_ratio',0):>6.2f}")
        if "overfitting_check" in output:
            print(f"\n  过拟合检测: {output['overfitting_check']['warning']}")


def cmd_multi_factor(args):
    """多因子评分"""
    from data_bridge import DataBridge
    from technical_indicators import calc_all
    from multi_factor_scorer import MultiFactorScorer

    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}, ensure_ascii=False))
        return

    tech = calc_all(klines)
    latest = tech["latest"]

    pe = args.pe
    if pe is None:
        quote = bridge.get_realtime_quote(args.code)
        if quote:
            pe = quote.get("pe")
            if pe and pe > 0:
                pe = float(pe)

    scorer = MultiFactorScorer()
    result = scorer.score_multi_factor(klines, latest, pe, args.pb)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{args.code} 多因子评分")
        print(f"  综合评分: {result['composite_score']:.1f} → {result['rating']} {result['rating_text']}")
        for name, info in result["factors"].items():
            if "weight" in info:
                print(f"  {name:<14} {info.get('normalized',0):>6.1f} (权重{info['weight']:.0%})")
            elif "normalized" in info:
                print(f"  {name:<14} {info['normalized']:>6.1f}")
        if result["factor_highlights"]:
            print(f"\n  亮点:")
            for h in result["factor_highlights"]:
                print(f"    ✅ {h}")
        if result["factor_warnings"]:
            print(f"  风险:")
            for w in result["factor_warnings"]:
                print(f"    ⚠️ {w}")


def cmd_portfolio_risk(args):
    """组合风险管理"""
    from data_bridge import DataBridge
    from portfolio_risk_manager import PortfolioRiskManager

    if args.holdings:
        with open(args.holdings) as f:
            holdings = json.load(f)
    else:
        holdings = [
            {"code": "600519", "weight": 0.15, "sector": "白酒", "industry": "食品饮料"},
            {"code": "000400", "weight": 0.10, "sector": "电气设备", "industry": "电力设备"},
            {"code": "002230", "weight": 0.08, "sector": "AI", "industry": "计算机"},
        ]

    bridge = DataBridge()
    klines_map = {}
    for h in holdings:
        klines_map[h["code"]] = bridge.tencent_kline(h["code"], 60)

    mgr = PortfolioRiskManager()
    report = mgr.generate_risk_report(holdings, klines_map, args.pnl)

    if args.output == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        s = report["summary"]
        print(f"组合风险管理报告")
        print(f"  持仓数: {s['total_positions']}  总仓位: {s['total_weight']:.1%}")
        print(f"  有效持仓数(Herfindahl): {s['herfindahl_index']:.1f}")
        print(f"  组合波动率: {s['portfolio_volatility']:.1%}")
        print(f"  回撤控制: {report['drawdown_control']['message']}")
        print(f"  行业暴露违规: {s['sector_violations']}")
        print(f"\n  建议:")
        for r in report["recommendations"]:
            print(f"    {r}")


def cmd_mean_reversion(args):
    """均值回归策略"""
    from data_bridge import DataBridge
    from technical_indicators import calc_all
    from mean_reversion_strategy import MeanReversionStrategy

    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}, ensure_ascii=False))
        return

    strategy = MeanReversionStrategy()
    bt = strategy.backtest_signals(klines)
    tech = calc_all(klines)
    score = strategy.score_reversion(klines, tech["latest"])

    if args.output == "json":
        print(json.dumps({"code": args.code, "backtest": bt, "reversion_score": score}, ensure_ascii=False, indent=2))
    else:
        print(f"{args.code} 均值回归策略")
        print(f"  买入信号: {bt['buy_signals']}次  卖出信号: {bt['sell_signals']}次")
        print(f"  胜率(5日): {bt['win_rate']:.1f}%  平均5日收益: {bt['avg_return_5d']:+.2f}%")
        print(f"  均值回归评分: {score['score']}/100 → {score['rating']}  {score['reason']}")


def cmd_grid(args):
    """网格交易策略"""
    from data_bridge import DataBridge
    from grid_trading_strategy import GridTradingStrategy

    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}, ensure_ascii=False))
        return

    grid = GridTradingStrategy()
    info = grid.build_grid(klines, args.cash)
    sim = grid.simulate(klines, args.cash)
    score = grid.score_grid_suitability(klines)

    if args.output == "json":
        print(json.dumps({"code": args.code, "grid_info": info, "simulation": sim,
                          "suitability": score}, ensure_ascii=False, indent=2))
    else:
        print(f"{args.code} 网格交易策略")
        print(f"  网格数: {info.get('grid_count', 'N/A')}  间距: {info.get('grid_spacing', 'N/A')}")
        print(f"  BOLL区间: {info.get('boll_lower', 'N/A')} ~ {info.get('boll_upper', 'N/A')}")
        print(f"  止损价: {info.get('stop_loss_price', 'N/A')}")
        print(f"  模拟收益: {sim.get('total_return_pct', 0):+.2f}%  最大回撤: {sim.get('max_drawdown_pct', 0):.2f}%")
        print(f"  网格成交: {sim.get('grid_fills', 0)}次  每格均利: {sim.get('avg_profit_per_grid', 0)}")
        print(f"  适合度: {score['score']}/100 → {score['rating']} {'✅适合' if score['suitable'] else '❌不适合'}")
        print(f"    {score['reason']}")


def cmd_vol_breakout(args):
    """波动率突破策略"""
    from data_bridge import DataBridge
    from technical_indicators import calc_all
    from volatility_breakout_strategy import VolatilityBreakoutStrategy

    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线"}, ensure_ascii=False))
        return

    strategy = VolatilityBreakoutStrategy()
    bt = strategy.backtest_signals(klines)
    tech = calc_all(klines)
    score = strategy.score_breakout_opportunity(klines, tech["latest"])

    if args.output == "json":
        print(json.dumps({"code": args.code, "backtest": bt, "opportunity_score": score}, ensure_ascii=False, indent=2))
    else:
        print(f"{args.code} 波动率突破策略")
        print(f"  收缩期: {bt.get('squeeze_periods', 0)}次  突破信号: {bt.get('breakout_signals', 0)}次")
        print(f"  成功率: {bt.get('win_rate', 0):.1f}%  平均5日收益: {bt.get('avg_return_5d', 0):+.2f}%")
        print(f"  突破机会评分: {score['score']}/100 → {score['rating']}")
        print(f"    收缩: {'✅' if score.get('squeeze') else '❌'}  突破: {'✅' if score.get('breakout') else '❌'}")
        print(f"    {score.get('reason', '')}")


# ═══════════════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════════════


def cmd_action(args):
    """实战交易反应动作与微观指令"""
    from data_bridge import DataBridge
    from technical_indicators import calc_all
    from combo_scorer import ComboScorer
    from execution_action_engine import ExecutionActionEngine
    
    bridge = DataBridge()
    quote = bridge.get_realtime_quote(args.code)
    if not quote:
        print(json.dumps({"error": f"无法获取 {args.code} 行情"}, ensure_ascii=False))
        return
    klines = bridge.tencent_kline(args.code, args.count)
    tech_all = calc_all(klines) if (klines and len(klines) >= 26) else {}
    tech = tech_all.get("latest", {}) if tech_all else {}
    
    score_res = {"cs": 65, "rating": "B"}
    if klines and len(klines) >= 26 and tech:
        try:
            scorer = ComboScorer()
            scores = scorer.score_full(klines, tech)
            total_s = scores.get("total", {}).get("score", 65)
            rating = "A" if total_s >= 75 else ("B" if total_s >= 60 else ("C" if total_s >= 45 else "D"))
            score_res = {"cs": total_s, "rating": rating}
        except Exception:
            pass
            
    holding = None
    if args.cost and args.shares:
        holding = {"cost": args.cost, "shares": args.shares, "max_high": max(float(quote.get("high", 0)), args.cost)}
        
    result = ExecutionActionEngine.generate_action(
        code=args.code,
        name=quote.get("name", args.code),
        quote=quote,
        tech=tech,
        holding=holding,
        model_score=score_res
    )
    if hasattr(args, "output") and args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(ExecutionActionEngine.render_markdown_card(result))


def cmd_intent(args):
    """自然语言用户意图解析"""
    from execution_action_engine import IntentEvaluator
    res = IntentEvaluator.parse_user_query(args.query)
    print(json.dumps(res, ensure_ascii=False, indent=2))


def cmd_downside(args):
    """五类下跌场景化诊断与应对"""
    from data_bridge import DataBridge
    from technical_indicators import calc_all
    from execution_action_engine import DownsideReactionMatrix
    
    bridge = DataBridge()
    quote = bridge.get_realtime_quote(args.code)
    klines = bridge.tencent_kline(args.code, args.count)
    tech = calc_all(klines) if klines else {}
    holding = {"cost": args.cost, "shares": args.shares} if (args.cost and args.shares) else None
    
    diag = DownsideReactionMatrix.diagnose_downside(quote, tech, holding)
    print(json.dumps(diag, ensure_ascii=False, indent=2))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="aStocks — 统一A股分析平台")
    parser.add_argument("--output", "-o", choices=["json", "text"], default="text",
                        help="输出格式 (默认: text)")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # quote
    p = subparsers.add_parser("quote", help="实时行情")
    p.add_argument("code", help="股票代码")

    # technical
    p = subparsers.add_parser("technical", help="技术指标")
    p.add_argument("code", help="股票代码")
    p.add_argument("--count", type=int, default=120)

    # score
    p = subparsers.add_parser("score", help="策略评分")
    p.add_argument("code", help="股票代码")
    p.add_argument("--count", type=int, default=120)
    p.add_argument("--board-chg", type=float)
    p.add_argument("--board-top10", action="store_true")
    p.add_argument("--short", action="store_true", help="短线模式")

    # analyze
    p = subparsers.add_parser("analyze", help="全维度分析")
    p.add_argument("code", help="股票代码")
    p.add_argument("--count", type=int, default=120)
    p.add_argument("--board-chg", type=float)
    p.add_argument("--board-top10", action="store_true")
    p.add_argument("--short", action="store_true")

    # trapped
    p = subparsers.add_parser("trapped", help="解套分析")
    p.add_argument("code", help="股票代码")
    p.add_argument("--cost", type=float, required=True, help="持仓成本")
    p.add_argument("--shares", type=int, required=True, help="持仓股数")
    p.add_argument("--count", type=int, default=250)

    # market
    subparsers.add_parser("market", help="大盘健康度评估")

    # batch
    p = subparsers.add_parser("batch", help="批量行情")
    p.add_argument("codes", help="股票代码列表，逗号分隔")

    # deploy-monitor
    subparsers.add_parser("deploy-monitor", help="部署监控指南")

    # P0-P1 新增命令
    p = subparsers.add_parser("screen", help="三层漏斗选股")
    p.add_argument("codes", help="股票代码列表，逗号分隔")
    p.add_argument("--cyq", action="store_true", help="获取筹码分布")

    p = subparsers.add_parser("risk", help="风控分析 (止损+卖点+回撤)")
    p.add_argument("code", help="股票代码")
    p.add_argument("--entry", type=float, help="入场价")
    p.add_argument("--cost", type=float, help="持仓成本")
    p.add_argument("--current-value", type=float, help="当前市值", default=0)
    p.add_argument("--peak", type=float, help="最高市值", default=0)
    p.add_argument("--count", type=int, default=120)

    p = subparsers.add_parser("golden-cross", help="MACD二次金叉检测")
    p.add_argument("code", help="股票代码")
    p.add_argument("--count", type=int, default=120)

    p = subparsers.add_parser("events", help="个股事件")
    p.add_argument("code", help="股票代码")
    p.add_argument("--name", help="股票名称", default="")

    p = subparsers.add_parser("cyq", help="筹码分布")
    p.add_argument("code", help="股票代码")

    p = subparsers.add_parser("balance", help="代理积分余额查询")

    p = subparsers.add_parser("evaluate", help="持股策略评估 (历史策略vs实际走势)")
    p.add_argument("code", help="股票代码")
    p.add_argument("--auto", action="store_true", help="自动扫描模式 (无需历史持仓)")
    p.add_argument("--entries", help='JSON格式历史持仓 [{"date":"...","price":...,"action":"..."}]')
    p.add_argument("--entries-file", help="持仓JSON文件路径")
    p.add_argument("--interval", type=int, help="自动扫描间隔(天), 默认20")
    p.add_argument("--count", type=int, default=250)

    # P0-P3 量化策略命令
    p = subparsers.add_parser("backtest", help="回测评估 (夏普/回撤/胜率/盈亏比)")
    p.add_argument("code", help="股票代码")
    p.add_argument("--strategy", choices=["sma_cross", "combo_score"], default="sma_cross")
    p.add_argument("--count", type=int, default=250)
    p.add_argument("--cash", type=float, default=1000000)
    p.add_argument("--split", action="store_true", help="样本内外过拟合检测")

    p = subparsers.add_parser("multi-factor", help="多因子选股评分")
    p.add_argument("code", help="股票代码")
    p.add_argument("--count", type=int, default=120)
    p.add_argument("--pe", type=float, default=None)
    p.add_argument("--pb", type=float, default=None)

    p = subparsers.add_parser("portfolio-risk", help="组合风险管理")
    p.add_argument("--holdings", help="持仓JSON文件路径")
    p.add_argument("--pnl", type=float, default=0, help="组合浮亏%%")

    p = subparsers.add_parser("mean-reversion", help="均值回归策略 (RSI+BOLL)")
    p.add_argument("code", help="股票代码")
    p.add_argument("--count", type=int, default=120)

    p = subparsers.add_parser("grid", help="网格交易策略 (ATR+BOLL)")
    p.add_argument("code", help="股票代码")
    p.add_argument("--count", type=int, default=120)
    p.add_argument("--cash", type=float, default=1000000)

    p = subparsers.add_parser("vol-breakout", help="波动率突破策略 (BOLL收缩+放量)")
    p.add_argument("code", help="股票代码")
    p.add_argument("--count", type=int, default=120)

    
    p = subparsers.add_parser("action", help="实战交易反应动作与微观订单")
    p.add_argument("code", help="股票代码")
    p.add_argument("--cost", type=float, default=None, help="持仓成本")
    p.add_argument("--shares", type=int, default=None, help="持仓股数")
    p.add_argument("--count", type=int, default=120)

    p = subparsers.add_parser("intent", help="自然语言意图智能解析")
    p.add_argument("query", help="用户自然语言输入")

    p = subparsers.add_parser("downside", help="五类下跌场景化精准诊断")
    p.add_argument("code", help="股票代码")
    p.add_argument("--cost", type=float, default=None, help="持仓成本")
    p.add_argument("--shares", type=int, default=None, help="持仓股数")
    p.add_argument("--count", type=int, default=120)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "quote": cmd_quote,
        "technical": cmd_technical,
        "score": cmd_score,
        "analyze": cmd_analyze,
        "trapped": cmd_trapped,
        "market": cmd_market,
        "batch": cmd_batch,
        "deploy-monitor": cmd_deploy_monitor,
        "screen": cmd_screen,
        "risk": cmd_risk,
        "golden-cross": cmd_golden_cross,
        "events": cmd_events,
        "cyq": cmd_cyq,
        "balance": cmd_balance,
        "evaluate": cmd_evaluate,
        "backtest": cmd_backtest,
        "multi-factor": cmd_multi_factor,
        "portfolio-risk": cmd_portfolio_risk,
        "mean-reversion": cmd_mean_reversion,
        "grid": cmd_grid,
        "vol-breakout": cmd_vol_breakout,
        "action": cmd_action,
        "intent": cmd_intent,
        "downside": cmd_downside,
    }

    fn = commands.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
