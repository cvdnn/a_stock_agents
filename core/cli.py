# -*- coding: utf-8 -*-
"""
Unified CLI for a_stock_agents.
Supports command-line execution for human users, scripts, and external UI/API sub-processes.
"""

import sys
import os
import argparse
import json
from pathlib import Path

CUR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CUR_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CUR_DIR) not in sys.path:
    sys.path.insert(0, str(CUR_DIR))

from core.config import GLOBAL_CONFIG, POOLS_DIR, POSITIONS_DIR, CACHE_DIR, REPORTS_DIR

def cmd_data_quote(args):
    from core.data.data_bridge import DataBridge
    bridge = DataBridge()
    codes = args.codes
    if not codes:
        print(json.dumps({"error": "No stock codes provided"}, ensure_ascii=False) if args.json else "Error: No stock codes provided")
        return
    
    if len(codes) == 1:
        q = bridge.get_realtime_quote(codes[0])
        if not q:
            print(json.dumps({"error": f"Failed to get quote for {codes[0]}"}, ensure_ascii=False) if args.json else f"Failed to get quote for {codes[0]}")
            return
        if args.json:
            print(json.dumps(q, ensure_ascii=False, indent=2))
        else:
            print(f"[{q.get('code')}] {q.get('name', 'N/A')} | 现价: {q.get('price', 0):.2f} | 涨跌幅: {q.get('change_pct', 0):+.2f}% | PE: {q.get('pe', 'N/A')}")
    else:
        quotes = {}
        for c in codes:
            q = bridge.get_realtime_quote(c)
            if q:
                quotes[c] = q
        if args.json:
            print(json.dumps(quotes, ensure_ascii=False, indent=2))
        else:
            print(f"=== 实时行情快照 (共 {len(quotes)} 只) ===")
            for code, q in quotes.items():
                print(f"[{q.get('code', code)}] {q.get('name', 'N/A'):8s} | 现价: {q.get('price', 0):8.2f} | 涨跌幅: {q.get('change_pct', 0):+6.2f}%")

def cmd_data_technical(args):
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all, gap_analysis, second_golden_cross
    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, count=args.count)
    if not klines or len(klines) < 20:
        print(json.dumps({"error": f"Insufficient K-line data for {args.code}"}, ensure_ascii=False) if args.json else f"Insufficient K-line data for {args.code}")
        return
    
    tech = calc_all(klines)
    gaps = gap_analysis(klines)
    golden = second_golden_cross(klines)
    res = {"code": args.code, "technical": tech, "gaps": gaps, "second_golden_cross": golden}
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"=== [{args.code}] 经典技术指标 ===")
        ma_info = tech.get('ma', {})
        print(f"均线: MA5={ma_info.get(5, 'N/A')} | MA10={ma_info.get(10, 'N/A')} | MA20={ma_info.get(20, 'N/A')} | MA60={ma_info.get(60, 'N/A')}")
        macd_info = tech.get('macd', {})
        print(f"MACD: DIF={macd_info.get('dif', 'N/A')} | DEA={macd_info.get('dea', 'N/A')} | MACD={macd_info.get('macd', 'N/A')}")
        kdj_info = tech.get('kdj', {})
        print(f"KDJ: K={kdj_info.get('k', 'N/A')} | D={kdj_info.get('d', 'N/A')} | J={kdj_info.get('j', 'N/A')}")
        rsi_info = tech.get('rsi', {})
        print(f"RSI: {rsi_info}")
        print(f"水下二次金叉信号: {golden.get('verdict')} | 理由: {golden.get('reason', '无')}")

def cmd_evaluate(args):
    from core.data.data_bridge import DataBridge
    from core.models.combo_scorer import ComboScorer
    bridge = DataBridge()
    code = args.code
    q = bridge.get_realtime_quote(code)
    klines = bridge.tencent_kline(code, count=120)
    if not q or not klines:
        print(json.dumps({"error": f"Failed to fetch market data for {code}"}, ensure_ascii=False) if args.json else f"Failed to fetch data for {code}")
        return
        
    scorer = ComboScorer()
    res = scorer.score_full(klines=klines, latest=q)
    if args.json:
        out = {"code": code, "name": q.get('name', code), "price": q.get('price', 0), "score": res}
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"=== [{code}] {q.get('name', code)} 综合量化诊断 ===")
        print(f"现价: {q.get('price', 0):.2f} | 综合评分: {res.get('total', 'N/A')}/100")
        print(f"评级: {res.get('rating', 'N/A')} - {res.get('rating_text', 'N/A')} | 建议仓位: {res.get('suggested_position', 'N/A')}")

def cmd_action_plan(args):
    from core.strategy.execution_action_engine import ExecutionActionEngine
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    
    bridge = DataBridge()
    code = args.code or "600519"
    cost = args.cost or 1200.0
    shares = args.shares or 100
    q = bridge.get_realtime_quote(code) or {"price": cost, "open": cost, "high": cost, "low": cost, "change_pct": 0.0}
    name = q.get("name", code)
    klines = bridge.tencent_kline(code, count=60)
    tech = calc_all(klines) if klines else {}
    
    res = ExecutionActionEngine.generate_action(
        code=code, name=name, quote=q, tech=tech,
        holding={"cost": cost, "shares": shares}
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"=== [{code}] {name} 实战交易反应决策单 ===")
        if res.get("config_prompt"):
            print("-" * 65)
            print("⚠️  " + res["config_prompt"].replace("\n", "\n   "))
            print("-" * 65)
        print(f"现价: {res.get('current_price')} | 买入成本: {cost:.2f} | 盈亏: {res.get('profit_pct'):+.2f}%")
        print(f"最低保本卖出价: {res.get('breakeven_price')} 元 (精确含税费进位)")
        print(f"建议反应动作: {res.get('action_type')} (紧急度: {res.get('urgency')})")
        print("操作指令明细:")
        for item in res.get("action_items", []):
            print(f"  - [{item.get('action')}] 委托方式: {item.get('order_type')}, 股数: {item.get('shares')}, 执行窗口: {item.get('execution_window')}")
            print(f"    纪律: {item.get('rule')}")

def cmd_config_paths(args):
    from core.config import get_active_paths
    paths = get_active_paths()
    if args.json:
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
            comm = float(val_comm) if val_comm else m['commission_rate']
            
            val_min = input(f"请输入单笔最低佣金(元, 免5填0.0) [回车保持 {m['min_commission']}]: ").strip()
            min_c = float(val_min) if val_min else m['min_commission']
            
            val_tax = input(f"请输入卖出印花税率 [回车保持 {m['tax_rate_sell']}]: ").strip()
            tax = float(val_tax) if val_tax else m['tax_rate_sell']
            
            new_m = save_market_config(commission_rate=comm, min_commission=min_c, tax_rate_sell=tax, is_user_configured=True)
            print("✅ 费率配置已成功保存并即时生效！")
            print(f"  新佣金率: {new_m['commission_rate']} (万{new_m['commission_rate']*10000:.1f}) | 最低起收: {new_m['min_commission']}元")
        except Exception as e:
            print(f"❌ 配置失败: {e}")
        return

    has_update = (getattr(args, "commission", None) is not None or 
                  getattr(args, "min_commission", None) is not None or 
                  getattr(args, "tax", None) is not None or 
                  getattr(args, "transfer", None) is not None)
    
    if has_update:
        new_m = save_market_config(
            commission_rate=args.commission,
            min_commission=args.min_commission,
            tax_rate_sell=args.tax,
            transfer_fee_rate=args.transfer,
            is_user_configured=True
        )
        if args.json:
            print(json.dumps(new_m, ensure_ascii=False, indent=2))
        else:
            print("✅ 券商交易费率配置已成功更新并持久化至 config.yaml：")
            print(f"  - 券商佣金率: {new_m['commission_rate']} (万{new_m['commission_rate']*10000:.2f})")
            print(f"  - 最低单笔佣金: {new_m['min_commission']:.1f} 元 {'(已启用免五规则)' if new_m['min_commission'] <= 0 else '(最低起收)'}")
            print(f"  - 卖出印花税率: {new_m['tax_rate_sell']} (万{new_m['tax_rate_sell']*10000:.1f})")
            print(f"  - 过户费率: {new_m['transfer_fee_rate']}")
            print(f"  - 配置状态: 已确认 (is_user_configured: True)")
    else:
        m = get_market_config()
        if args.json:
            print(json.dumps(m, ensure_ascii=False, indent=2))
        else:
            print("=== A-Stock Agents 市场交易费率配置 ===")
            print(f"  券商佣金率:     {m['commission_rate']} (万{m['commission_rate']*10000:.2f})")
            print(f"  最低佣金起收:   {m['min_commission']:.1f} 元 {'(免五)' if m['min_commission'] <= 0 else ''}")
            print(f"  卖出印花税率:   {m['tax_rate_sell']} (万{m['tax_rate_sell']*10000:.1f})")
            print(f"  过户费率(双边): {m['transfer_fee_rate']}")
            print(f"  精确进位到分:   {'开启 (向上进位保证保本)' if m['breakeven_ceil_cent'] else '关闭'}")
            print(f"  用户确认状态:   {'✅ 已自定义配置' if m['is_user_configured'] else '⚠️ 未确认 (使用默认万2.5/5元)'}")
            if not m['is_user_configured']:
                print("\n  💡 [提示] 若实际费率不同，建议执行以下命令配置您的真实佣金：")
                print(f"     python core/cli.py config market --commission 0.00025 --min-commission 5.0")
                print(f"     或运行交互向导: python core/cli.py config market --interactive")

def cmd_skill_list(args):
    manifest_file = PROJECT_ROOT / "config" / "skills_manifest.json"
    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"=== 已注册 A股 技能清单 (共 {data.get('total_skills', 0)} 个) ===")
            for s in data.get("skills", []):
                triggers = ", ".join(s.get('triggers', [])[:5])
                print(f"- [{s['id']}] {s['title']} ({s['category']})")
                print(f"  描述: {s['description']}")
                print(f"  触发词: {triggers}")
                print(f"  入口命令: {s['cli_command']}")
                print()
    else:
        print("skills_manifest.json not found.")

def cmd_screen(args):
    from core.models.stock_screener import StockScreener
    screener = StockScreener()
    raw_codes = args.codes.split(",") if "," in args.codes else args.codes.split()
    codes = [c.strip() for c in raw_codes if c.strip()]
    if not codes:
        print(json.dumps({"error": "No stock codes provided"}, ensure_ascii=False) if args.json else "Error: No stock codes provided")
        return
    res = screener.screen(codes, fetch_cyq=args.cyq)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"=== 三层漏斗选股 (输入: {res['total_input']} -> 板块: {res['stage1_board']} -> 技术: {res['stage2_technical']} -> 评分: {res['stage3_scored']}) ===")
        if res.get("results"):
            print(f"{'代码':<8} {'名称':<10} {'评级':<4} {'总分':>5} {'现价':>8} {'涨跌幅%':>8} {'PE':>6}")
            for r in res["results"][:args.limit]:
                print(f"{r.get('code', ''):<8} {r.get('name', 'N/A'):<10} {r.get('rating', ''):<4} {r.get('total_score', 0):>5} {r.get('price', 0):>8.2f} {r.get('change_pct', 0):>+8.2f}% {r.get('pe', 'N/A')}")

def cmd_trapped(args):
    from core.data.data_bridge import DataBridge
    from core.strategy.trapped_position import TrappedPositionAnalyzer
    bridge = DataBridge()
    klines = bridge.tencent_kline(args.code, count=120)
    if not klines or len(klines) < 20:
        print(json.dumps({"error": f"Insufficient K-line data for {args.code}"}, ensure_ascii=False) if args.json else f"Insufficient K-line data for {args.code}")
        return
    analyzer = TrappedPositionAnalyzer(cost_price=args.cost, shares=args.shares, klines=klines)
    res = analyzer.analyze()
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        diag = res.get("diagnostic", {})
        dt = res.get("decision_tree", {})
        print(f"=== 被困持仓量化解套分析: {args.code} ===")
        print(f"持仓成本: {args.cost:.2f}元 | 持股数: {args.shares} | 现价: {diag.get('current_price', 0):.2f}元 | 浮亏: {diag.get('loss_pct', 0):+.2f}%")
        print(f"凯利仓位评估: {diag.get('kelly_interpretation', 'N/A')}")
        print(f"决策树推荐: {dt.get('recommended', 'N/A')} ({dt.get('reason', 'N/A')})")
        for st in dt.get("strategies", []):
            print(f"  - {st}")

def cmd_report(args):
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all, gap_analysis
    from core.models.combo_scorer import ComboScorer, entry_assessment
    from core.reporting.report_generator import generate_simple_report
    from core.config import OUTPUT_REPORTS_DIR
    from datetime import datetime

    bridge = DataBridge()
    code = args.code
    quote = bridge.get_realtime_quote(code)
    klines = bridge.tencent_kline(code, count=120)
    if not klines or len(klines) < 26:
        print(json.dumps({"error": f"Insufficient K-line data for {code}"}, ensure_ascii=False) if args.json else f"Insufficient K-line data for {code}")
        return
    tech = calc_all(klines)
    gaps = gap_analysis(klines)
    scorer = ComboScorer()
    scores = scorer.score_full(klines, tech["latest"])
    entry = entry_assessment(klines, tech["latest"])
    name = quote.get("name", code) if quote else code
    data = {
        "code": code,
        "name": name,
        "quote": quote,
        "scores": scores,
        "technical_latest": tech["latest"],
        "entry": entry,
        "gaps": gaps
    }
    out_dir = OUTPUT_REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output or str(out_dir / f"aStocks_{code}_{datetime.now():%Y%m%d}.html")
    generate_simple_report(data, out_path)
    if args.json:
        print(json.dumps({"status": "success", "report_path": out_path, "code": code, "name": name}, ensure_ascii=False, indent=2))
    else:
        print(f"量化诊断 HTML 报告已成功生成: {out_path}")

def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    parser = argparse.ArgumentParser(description="A-Stock Agents CLI - A股量化投研与智能体统一入口", parents=[common_parser])
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # config
    p_cfg = subparsers.add_parser("config", help="Configuration & Path Isolation", parents=[common_parser])
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd")
    cfg_sub.add_parser("paths", help="Show active data isolation paths", parents=[common_parser])
    
    p_mkt = cfg_sub.add_parser("market", help="View & configure market fee rates (commission, min fee, stamp tax)", parents=[common_parser])
    p_mkt.add_argument("--commission", type=float, default=None, help="Broker commission rate e.g. 0.00025 (万2.5) or 0.00012 (万1.2)")
    p_mkt.add_argument("--min-commission", type=float, default=None, help="Minimum commission per trade in RMB (e.g. 5.0 or 0.0 for 免5)")
    p_mkt.add_argument("--tax", type=float, default=None, help="Stamp tax rate on sell (e.g. 0.0005 for 0.05%)")
    p_mkt.add_argument("--transfer", type=float, default=None, help="Transfer fee rate (e.g. 0.00001)")
    p_mkt.add_argument("--interactive", action="store_true", help="Interactive prompt to configure market fees")

    # pool
    p_pool = subparsers.add_parser("pool", help="Stock Pool Management", parents=[common_parser])
    pool_sub = p_pool.add_subparsers(dest="pool_cmd")
    p_pool_list = pool_sub.add_parser("list", help="List stock pools", parents=[common_parser])
    p_pool_list.add_argument("--pool", choices=["selected", "watch"], default=None)
    
    # position
    p_pos = subparsers.add_parser("position", help="Portfolio & Position Management", parents=[common_parser])
    pos_sub = p_pos.add_subparsers(dest="pos_cmd")
    p_pos_list = pos_sub.add_parser("list", help="List current positions", parents=[common_parser])
    p_pos_list.add_argument("--history", action="store_true", help="View closed trades history")
    pos_sub.add_parser("pnl", help="View total PnL", parents=[common_parser])
    pos_sub.add_parser("snapshot", help="Take position snapshot with stop triggers", parents=[common_parser])

    # data
    p_data = subparsers.add_parser("data", help="Market & Technical Data", parents=[common_parser])
    data_sub = p_data.add_subparsers(dest="data_cmd")
    p_quote = data_sub.add_parser("quote", help="Fetch realtime quotes", parents=[common_parser])
    p_quote.add_argument("codes", nargs="+", help="Stock codes e.g. 600519 000858")
    
    p_tech = data_sub.add_parser("tech", help="Fetch technical indicators", parents=[common_parser])
    p_tech.add_argument("code", help="Stock code")
    p_tech.add_argument("--count", type=int, default=120, help="K-line count")

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="Stock Multi-factor Evaluation", parents=[common_parser])
    p_eval.add_argument("code", help="Stock code e.g. 600519")

    # action
    p_action = subparsers.add_parser("action", help="Execution Action Engine", parents=[common_parser])
    action_sub = p_action.add_subparsers(dest="action_cmd")
    p_plan = action_sub.add_parser("plan", help="Generate reaction plan & breakeven prices", parents=[common_parser])
    p_plan.add_argument("--code", default=None, help="Stock code e.g. 600519")
    p_plan.add_argument("--cost", type=float, default=None, help="Cost price")
    p_plan.add_argument("--shares", type=int, default=None, help="Position shares")

    # skill
    p_skill = subparsers.add_parser("skill", help="Skill Management", parents=[common_parser])
    skill_sub = p_skill.add_subparsers(dest="skill_cmd")
    skill_sub.add_parser("list", help="List all registered skills", parents=[common_parser])

    # screen
    p_screen = subparsers.add_parser("screen", help="Three-Layer Funnel Stock Screener", parents=[common_parser])
    p_screen.add_argument("--codes", default="600519,000858,300750,601318,688981", help="Stock codes separated by comma or space")
    p_screen.add_argument("--cyq", action="store_true", help="Fetch chip distribution (CYQ)")
    p_screen.add_argument("--limit", type=int, default=10, help="Maximum results to display")

    # trapped
    p_trapped = subparsers.add_parser("trapped", help="Trapped Position Quantitative Rescue", parents=[common_parser])
    p_trapped.add_argument("code", help="Stock code e.g. 600760")
    p_trapped.add_argument("--cost", type=float, required=True, help="Average holding cost")
    p_trapped.add_argument("--shares", type=int, required=True, help="Total holding shares")

    # report
    p_report = subparsers.add_parser("report", help="Generate HTML Diagnostic Report", parents=[common_parser])
    p_report.add_argument("code", help="Stock code e.g. 600519")
    p_report.add_argument("--output", default=None, help="Custom output file path")

    args = parser.parse_args()
    if args.command == "config":
        if args.config_cmd == "paths":
            cmd_config_paths(args)
        elif args.config_cmd == "market":
            cmd_config_market(args)
        elif not args.config_cmd:
            cmd_config_market(args)
        else:
            p_cfg.print_help()
    elif args.command == "pool":
        from core.strategy import pool_manager
        if args.pool_cmd == "list" or not args.pool_cmd:
            pool_manager.cmd_list(args)
        else:
            p_pool.print_help()
    elif args.command == "position":
        from core.strategy import position_manager
        if args.pos_cmd == "list" or not args.pos_cmd:
            position_manager.cmd_list(args)
        elif args.pos_cmd == "pnl":
            position_manager.cmd_pnl(args)
        elif args.pos_cmd == "snapshot":
            position_manager.cmd_snapshot(args)
        else:
            p_pos.print_help()
    elif args.command == "data":
        if args.data_cmd == "quote":
            cmd_data_quote(args)
        elif args.data_cmd == "tech":
            cmd_data_technical(args)
        else:
            p_data.print_help()
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "action":
        cmd_action_plan(args)
    elif args.command == "screen":
        cmd_screen(args)
    elif args.command == "trapped":
        cmd_trapped(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "skill":
        if args.skill_cmd == "list":
            cmd_skill_list(args)
        else:
            p_skill.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
