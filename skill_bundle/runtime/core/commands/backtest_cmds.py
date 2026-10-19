# -*- coding: utf-8 -*-
"""
Backtesting CLI subcommands.
"""
from __future__ import annotations

import json

from core.config import get_logger

logger = get_logger("core.commands.backtest")


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

    is_oos_mode = getattr(args, "oos", False) or getattr(args, "split", False)
    if is_oos_mode:
        oos_res = engine.run_oos_validation(klines, strategy)
        in_m = oos_res.get("in_sample", {})
        out_m = oos_res.get("out_sample", {})
        decay = oos_res.get("decay", {})
        overfitting_check = oos_res.get("overfitting_check", {})
        triple_alerts = oos_res.get("triple_alerts", {})

        output = {
            "code": args.code,
            "strategy": strategy_name,
            "mode": "rolling_oos",
            "in_sample": in_m,
            "out_sample": out_m,
            "decay": decay,
            "overfitting_check": overfitting_check,
            "triple_alerts": triple_alerts,
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
        if is_oos_mode:
            in_m = output.get("in_sample", {})
            out_m = output.get("out_sample", {})
            chk = output.get("overfitting_check", {})
            print("──────────────────────── 滚动样本外 (Rolling OOS) 检验报告 ────────────────────────")
            print(f"  标的代码: {args.code} | 回测策略: {strategy_name}")
            print(f"{'阶段':<8} {'年化收益':>10} {'夏普比率':>10} {'最大回撤':>10} {'胜率':>8} {'盈亏比':>8}")
            print(
                f"{'样本内(IS)':<8} {in_m.get('annual_return', 0):>9.2f}% "
                f"{in_m.get('sharpe_ratio', 0):>10.2f} {in_m.get('max_drawdown', 0):>9.2f}% "
                f"{in_m.get('win_rate', 0):>7.1f}% {in_m.get('profit_factor', 0):>8.2f}"
            )
            print(
                f"{'样本外(OOS)':<8} {out_m.get('annual_return', 0):>9.2f}% "
                f"{out_m.get('sharpe_ratio', 0):>10.2f} {out_m.get('max_drawdown', 0):>9.2f}% "
                f"{out_m.get('win_rate', 0):>7.1f}% {out_m.get('profit_factor', 0):>8.2f}"
            )
            print("──────────────────────────────────────────────────────────────────────────")
            print(f"  收益衰减率: {chk.get('return_decay_pct', 0.0):.2f}% | 夏普衰减率: {chk.get('sharpe_decay_pct', 0.0):.2f}%")
            print(f"  过拟合结论: {chk.get('summary', '正常')}")
            for w in chk.get("warnings", []):
                print(f"    ⚠️  {w}")
            print("──────────────────────────────────────────────────────────────────────────\n")
        else:
            m = output.get("metrics", {})
            print(f"{'代码':<8} {'策略':<12} {'年化收益':>8} {'夏普':>6} {'最大回撤':>8} {'胜率':>6} {'盈亏比':>6} {'Calmar':>6}")
            print(
                f"{args.code:<8} {strategy_name:<12} {m.get('annual_return', 0):>7.2f}% "
                f"{m.get('sharpe_ratio', 0):>6.2f} {m.get('max_drawdown', 0):>7.2f}% "
                f"{m.get('win_rate', 0):>5.1f}% {m.get('profit_factor', 0):>6.2f} "
                f"{m.get('calmar_ratio', 0):>6.2f}"
            )



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
