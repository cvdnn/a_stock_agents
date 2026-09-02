# -*- coding: utf-8 -*-
"""
Unified CLI for a_stock_agents.
Supports command-line execution for human users, scripts, and Java AI Platform sub-processes.
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
        print(f"现价: {res.get('current_price')} | 买入成本: {cost:.2f} | 盈亏: {res.get('profit_pct'):+.2f}%")
        print(f"最低保本卖出价: {res.get('breakeven_price')} 元 (精确含税费进位)")
        print(f"建议反应动作: {res.get('action_type')} (紧急度: {res.get('urgency')})")
        print("操作指令明细:")
        for item in res.get("action_items", []):
            print(f"  - [{item.get('action')}] 委托方式: {item.get('order_type')}, 股数: {item.get('shares')}, 执行窗口: {item.get('execution_window')}")
            print(f"    纪律: {item.get('rule')}")

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

def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    parser = argparse.ArgumentParser(description="A-Stock Agents CLI - A股量化投研与智能体统一入口", parents=[common_parser])
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

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

    args = parser.parse_args()
    if args.command == "data":
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
    elif args.command == "skill":
        if args.skill_cmd == "list":
            cmd_skill_list(args)
        else:
            p_skill.print_help()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
