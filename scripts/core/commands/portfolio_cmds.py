# -*- coding: utf-8 -*-
"""
Portfolio, Reports & Configuration CLI subcommands.
"""
from __future__ import annotations

import json
from datetime import datetime

from core.config import (
    OUTPUT_REPORTS_DIR,
    PROJECT_ROOT,
    SKILLS_DIR,
    get_logger,
)

logger = get_logger("core.commands.portfolio")


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


def cmd_config_paths(args):
    """显示路径与隔离配置"""
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
    """配置券商佣金与印花税"""
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
    skills_dir = SKILLS_DIR if SKILLS_DIR.exists() else (PROJECT_ROOT / ".agents" / "skills")
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


def cmd_pool_dispatch(args, parser):
    """股票池子命令路由"""
    from core.strategy import pool_manager

    pool_cmd = getattr(args, "pool_cmd", None)
    if pool_cmd == "list" or not pool_cmd:
        pool_manager.cmd_list(args)
    else:
        parser.print_help()


def cmd_pos_dispatch(args, parser):
    """持仓子命令路由"""
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
