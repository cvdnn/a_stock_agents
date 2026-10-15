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
