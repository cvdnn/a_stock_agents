# -*- coding: utf-8 -*-
"""
Strategy & Risk Execution CLI subcommands.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from core.config import get_logger

logger = get_logger("core.commands.strategy")


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
    from core.config import OUTPUT_POOLS_DIR

    holdings_path = getattr(args, "holdings", None)
    holdings = []
    if holdings_path and os.path.exists(holdings_path):
        with open(holdings_path, encoding="utf-8") as f:
            holdings = json.load(f)
    else:
        # 优先尝试从本地用户持仓 CSV 动态加载
        pos_csv = OUTPUT_POOLS_DIR / "positions.csv"
        if pos_csv.exists():
            try:
                import csv
                with open(pos_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    total_val = 0.0
                    items = []
                    for r in reader:
                        c = r.get("code", "").strip()
                        if not c:
                            continue
                        bp = float(r.get("buy_price") or 0)
                        qty = float(r.get("qty") or 0)
                        val = bp * qty
                        sec = r.get("sector") or "其他"
                        items.append({"code": c, "val": val, "sector": sec, "industry": sec})
                        total_val += val
                    if total_val > 0:
                        for it in items:
                            holdings.append({
                                "code": it["code"],
                                "weight": round(it["val"] / total_val, 4),
                                "sector": it["sector"],
                                "industry": it["industry"]
                            })
            except Exception:
                holdings = []

    if not holdings:
        print("⚠️ 未检测到有效持仓数据。请通过以下方式之一执行组合风控：")
        print("  1. 记录持仓: python core/cli.py position buy <CODE> <NAME> <PRICE> <QTY>")
        print("  2. 指定文件: python core/cli.py portfolio-risk --holdings /path/to/holdings.json")
        return

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
    from core.config import OUTPUT_POOLS_DIR

    code = getattr(args, "opt_code", None) or getattr(args, "code", None)
    cost = getattr(args, "cost", None)
    shares = getattr(args, "shares", None)
    count = getattr(args, "count", 120)

    # 若未传股票代码，尝试从本地持仓自选检查唯一持仓
    if not code:
        pos_csv = OUTPUT_POOLS_DIR / "positions.csv"
        if pos_csv.exists():
            try:
                import csv
                with open(pos_csv, "r", encoding="utf-8") as f:
                    positions = [r for r in csv.DictReader(f) if r.get("code", "").strip()]
                    if len(positions) == 1:
                        p = positions[0]
                        code = p["code"].strip()
                        if cost is None and p.get("buy_price"):
                            cost = float(p["buy_price"])
                        if shares is None and p.get("qty"):
                            shares = int(float(p["qty"]))
                        print(f"  ℹ️ 未指定标的代码，自动选取本地唯一持仓标的: {code} ({p.get('name', '')})")
            except Exception:
                pass

    if not code:
        print("❌ 错误: 请指定股票代码。")
        print("  用法: python core/cli.py action <CODE> [--cost COST] [--shares SHARES]")
        print("  示例: python core/cli.py action 600036 --cost 35.5 --shares 1000")
        return

    bridge = DataBridge()
    q = bridge.get_realtime_quote(code) or {"price": cost or 10.0, "open": cost or 10.0, "high": cost or 10.0, "low": cost or 10.0, "change_pct": 0.0}
    name = q.get("name", code)
    curr_price = float(q.get("price", cost or 10.0))
    if cost is None:
        cost = curr_price
    if shares is None:
        shares = 100

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
        except Exception as exc:
            logger.debug(f"cmd_action_plan score calculation failed: {exc}")

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
