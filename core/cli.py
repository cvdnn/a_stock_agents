# -*- coding: utf-8 -*-
"""
Unified CLI for a_stock_agents.
Supports command-line execution for human users, scripts, and external UI/API sub-processes.
Integrates all standard quantitative research, risk control, screening, and backtesting subcommands.
Modularized via core.commands for clean separation of concerns and high maintainability.
"""
from __future__ import annotations

import argparse
import json
import sys
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
    VERSION,
    get_logger,
)
from core.commands import (
    cmd_action_plan,
    cmd_analyze,
    cmd_backtest,
    cmd_balance,
    cmd_batch,
    cmd_config_market,
    cmd_config_paths,
    cmd_cyq,
    cmd_data_quote,
    cmd_data_technical,
    cmd_deploy_monitor,
    cmd_downside,
    cmd_evaluate,
    cmd_events,
    cmd_golden_cross,
    cmd_grid,
    cmd_intent,
    cmd_market,
    cmd_mean_reversion,
    cmd_multi_backtest,
    cmd_multi_factor,
    cmd_pool_dispatch,
    cmd_portfolio_risk,
    cmd_pos_dispatch,
    cmd_report,
    cmd_risk,
    cmd_score,
    cmd_screen,
    cmd_skill_list,
    cmd_trapped,
    cmd_vol_breakout,
)

logger = get_logger("core.cli")

__all__ = [
    "build_parser",
    "main",
    "cmd_data_quote",
    "cmd_data_technical",
    "cmd_batch",
    "cmd_events",
    "cmd_cyq",
    "cmd_balance",
    "cmd_market",
    "cmd_score",
    "cmd_analyze",
    "cmd_multi_factor",
    "cmd_trapped",
    "cmd_risk",
    "cmd_golden_cross",
    "cmd_portfolio_risk",
    "cmd_action_plan",
    "cmd_intent",
    "cmd_downside",
    "cmd_screen",
    "cmd_evaluate",
    "cmd_backtest",
    "cmd_multi_backtest",
    "cmd_mean_reversion",
    "cmd_grid",
    "cmd_vol_breakout",
    "cmd_deploy_monitor",
    "cmd_config_paths",
    "cmd_config_market",
    "cmd_skill_list",
    "cmd_report",
]


def build_parser() -> argparse.ArgumentParser:
    """构建统一 CLI 解析器并注册全部子命令。"""
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
    p_screen.add_argument("--pool", default=None, help="候选股票池名称 (来自 stock_pools.yaml, 如 mainboard_24, h2_mainlines)")
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

    # 命令路由表 (直接分发至 core.commands 模块)
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
        cmd_pool_dispatch(args, parser)
    elif cmd == "position":
        cmd_pos_dispatch(args, parser)
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
            print(json.dumps({"platform": "A-Stock Agents", "version": VERSION, "status": "active"}, ensure_ascii=False, indent=2))
        else:
            print(f"A-Stock Agents Platform CLI v{VERSION} — 统一量化投研与智能体架构")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
