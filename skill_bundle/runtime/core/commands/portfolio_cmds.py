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
    is_json = getattr(args, "json", False)
    generate_simple_report(data, out_path, verbose=not is_json)
    if is_json:
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
    from core.workspace import SKILLS_ROOT, MANIFEST_PATH
    skills_dir = SKILLS_ROOT
    if skills_dir.exists():
        skills = sorted([d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith(".")])
    elif MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        skills = sorted([s["id"] for s in manifest.get("skills", [])] + ["a-stock-agents"])
    else:
        skills = []
    if getattr(args, "json", False):
        print(json.dumps({"total": len(skills), "skills": skills}, ensure_ascii=False, indent=2))
    else:
        print(f"=== A-Stock Agents 已注册技能模块 ({len(skills)} 个) ===")
        for s in skills:
            print(f"  - {s}")


def cmd_tips(args):
    """输出实战经验与数据源降级速查。"""
    result = {
        "status": "success",
        "type": "reference",
        "topic": getattr(args, "topic", "all"),
        "tips": [
            "集合竞价重点观察9:20-9:25不可撤单阶段的匹配量变化。",
            "行情数据失败时按腾讯、新浪、东方财富、本地缓存顺序降级。",
            "个股建议必须包含最低保本卖出价、三级止损和三场景动作单。",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_validate_model(args):
    """输出外部时序模型的样本外验证协议或对指定标的执行基线滚动样本外检验 (SPEC-SKILL-002 S2-03)。"""
    code = getattr(args, "code", None)
    model_name = getattr(args, "model", "Kronos")

    if code:
        from core.data.data_bridge import DataBridge
        from core.paper_trading.a_stocks_backtest import BacktestEngine, sma_cross_strategy

        klines = DataBridge.get_kline_robust(code, count=250)
        if klines and len(klines) >= 30:
            engine = BacktestEngine()
            oos_res = engine.run_oos_validation(klines, sma_cross_strategy)
            result = {
                "status": "success",
                "type": "model_validation",
                "model_name": model_name,
                "code": code,
                "execution_available": True,
                "baseline_comparison": {
                    "baseline_strategy": "sma_cross",
                    "in_sample": oos_res.get("in_sample", {}),
                    "out_sample": oos_res.get("out_sample", {}),
                    "decay": oos_res.get("decay", {}),
                    "overfitting_check": oos_res.get("overfitting_check", {}),
                    "triple_alerts": oos_res.get("triple_alerts", {}),
                },
                "verdict": "样本外检验完成；外部模型接入必须在样本外显著跑赢上述朴素基线且未触发过拟合三重警报。",
                "steps": ["滚动样本外切分", "对比朴素基线", "计入交易摩擦", "报告IC、回撤与稳定性"],
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

    result = {
        "status": "success",
        "type": "validation_protocol",
        "model_name": model_name,
        "code": code,
        "execution_available": False,
        "steps": ["滚动样本外切分", "对比朴素基线", "计入交易摩擦", "报告IC、回撤与稳定性"],
        "message": "当前命令提供验证协议；指定 --code <代码> 时可自动执行本地朴素基线滚动样本外比对。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))



def cmd_pool_audit(args):
    """五步真实 MA 股池审查与失效标的清洗。"""
    from core.strategy.pool_manager import PoolManager

    data_dir = getattr(args, "data", None)
    pm = PoolManager(pools_dir=data_dir) if data_dir else PoolManager()
    fix = bool(getattr(args, "fix", False))
    pool_type = getattr(args, "pool", None)
    result = pm.audit_pools(fix=fix, pool_type=pool_type)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_pool_dispatch(args, parser):
    """股票池子命令路由"""
    from core.strategy import pool_manager

    pool_cmd = getattr(args, "pool_cmd", None)
    if pool_cmd == "list" or not pool_cmd:
        pool_manager.cmd_list(args)
    elif pool_cmd == "audit":
        cmd_pool_audit(args)
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
