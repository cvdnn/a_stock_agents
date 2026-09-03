"""
A-Share Quant Engine - Unified Pipeline & CLI Entry (统一量化流水线与入口)
命令说明:
  python run_quant_pipeline.py scan [--universe 600519,000858,601318...] [--top 5]
  python run_quant_pipeline.py backtest [--days 250] [--top 4]
  python run_quant_pipeline.py analyze 600519
"""

import sys
import argparse
import json
from typing import List, Dict, Any

from data_layer import DataLayer
from pv_factors import PVFactors
from unstructured_factors import UnstructuredFactors
from factor_synthesizer import FactorSynthesizer
from risk_position_manager import PositionSizer, RiskEngine
from backtest_engine import BacktestEngine

# 预置 A 股代表性多风格核心样本池 (包含白马消费、新能源、半导体、大金融、高端制造、医药等)
DEFAULT_UNIVERSE = [
    "600519",  # 贵州茅台 (白酒消费)
    "000858",  # 五粮液 (白酒消费)
    "300750",  # 宁德时代 (新能源/创业板)
    "601318",  # 中国平安 (大金融保险)
    "600036",  # 招商银行 (大金融银行)
    "600760",  # 中航沈飞 (高端制造/国防军工)
    "002594",  # 比亚迪 (新能源汽车)
    "688981",  # 中芯国际 (半导体/科创板)
    "600276",  # 恒瑞医药 (创新药)
    "002475",  # 立讯精密 (消费电子)
    "601899",  # 紫金矿业 (资源有色)
    "000333",  # 美的集团 (家电制造)
]


def cmd_scan(args):
    """全市场/股票池截面扫描与 Top-K 选股决策"""
    symbols = args.universe.split(",") if args.universe else DEFAULT_UNIVERSE
    symbols = [s.strip() for s in symbols if s.strip()]
    top_k = args.top

    print(f"\n=======================================================")
    print(f"  A-Share Quant Engine - 截面多因子扫描与选股决策")
    print(f"  扫描标的数量: {len(symbols)} | 目标选股数: Top-{top_k}")
    print(f"=======================================================\n")

    quotes = DataLayer.get_batch_quotes(symbols)
    universe_factors = {}
    valid_klines = {}

    for s in symbols:
        kl = DataLayer.get_kline_history(s, num_days=100, use_cache=True)
        if len(kl) < 30:
            continue
        
        valid_klines[s] = kl
        f = PVFactors.extract_factors(kl)
        
        # 实时舆情特征接入与衰减 (示例：根据近期动量和异动计算综合情绪分)
        q = quotes.get(s, {})
        change = q.get("change_pct", 0.0)
        # 模拟近期公告/舆情打分
        news_sentiment = 0.3 if change > 2.0 and f.get("vol_surge_5_20", 1.0) > 1.3 else (
            -0.4 if change < -3.0 else 0.05
        )
        f["sentiment_score"] = news_sentiment
        universe_factors[s] = f

    if not universe_factors:
        print("错误: 未能获取到有效的标的因子数据。")
        return

    # 截面标准化与分位数排序
    ranked_univ = FactorSynthesizer.synthesize_universe(universe_factors)
    top_candidates = FactorSynthesizer.select_top_k(ranked_univ, top_k=top_k, min_percentile=50.0)

    # 仓位与风控参数计算 (假设账户总资金 100 万元)
    TOTAL_EQUITY = 1000000.0
    print(f"{'代码':<8} {'名称':<8} {'现价(元)':<9} {'综合Alpha':<10} {'分位Rank':<10} {'建议仓位':<10} {'建议股数':<8} {'ATR止损价':<10} {'保本价':<9} {'止盈目标(+5%)'}")
    print("-" * 105)

    for cand in top_candidates:
        sym = cand["symbol"]
        q = quotes.get(sym, {})
        name = q.get("name", sym)
        price = q.get("price", 0.0)
        if price <= 0:
            price = valid_klines[sym][-1]["close"]
        
        atr_val, _ = PVFactors.calculate_atr(valid_klines[sym], 14)
        
        # 计算头寸
        alloc = PositionSizer.calculate_stock_allocation(
            symbol=sym,
            price=price,
            atr=atr_val,
            total_equity=TOTAL_EQUITY,
            max_stocks=top_k
        )

        stop_loss_price = round(price - 2.0 * atr_val, 2)
        hard_stop_price = round(price * 0.94, 2)
        effective_stop = max(stop_loss_price, hard_stop_price)
        breakeven_price = round(price * 1.003, 2)
        tp1_price = round(price * 1.05, 2)

        pct_rank_str = f"{cand['percentile_rank']:.1f}%"
        weight_str = f"{alloc['weight']*100:.1f}%"
        print(f"{sym:<8} {name:<8} {price:<9.2f} {cand['composite_alpha']:<10.3f} {pct_rank_str:<10} {weight_str:<10} {alloc['shares']:<8} {effective_stop:<10.2f} {breakeven_price:<9.2f} {tp1_price:.2f}")

    print("\n[风控说明]:")
    print(" 1. 所有开仓次日方可卖出 (T+1 状态机约束)。")
    print(" 2. 盘中盈利超过 +5% 自动减仓 1/3，并强制将止损价上移至保本价 (成本+0.3%)。")
    print(" 3. 盘中若触碰 ATR 移动止损或硬止损 (-6%)，立即市价平仓。")


def cmd_backtest(args):
    """运行多标的历史事件驱动回测"""
    days = args.days
    top_k = args.top
    symbols = DEFAULT_UNIVERSE

    print(f"\n=======================================================")
    print(f"  A-Share Quant Engine - 历史事件驱动回测引擎")
    print(f"  股票池标的: {len(symbols)} 只 | 回测周期: {days} 交易日 | 槽位: Top-{top_k}")
    print(f"  交易摩擦: 印花税0.05%(卖方) | 佣金万2.5(最低5元) | 滑点0.1%")
    print(f"=======================================================\n")

    engine = BacktestEngine(symbols=symbols, initial_cash=1000000.0, rebalance_interval=5, top_k=top_k)
    res = engine.run(num_days=days)

    if "error" in res:
        print(f"回测失败: {res['error']}")
        return

    m = res["metrics"]
    print("─────────────────────── 回测核心绩效指标 ───────────────────────")
    print(f"  初始本金:             ￥{m['initial_cash']:,.2f}")
    print(f"  期末总权益:           ￥{m['final_equity']:,.2f}")
    print(f"  累计收益率:           {m['total_return_pct']:+.2f}%")
    print(f"  年化收益率 (CAGR):     {m['annualized_cagr_pct']:+.2f}%")
    print(f"  最大回撤 (MaxDD):     {m['max_drawdown_pct']:.2f}%")
    print(f"  夏普比率 (Sharpe):    {m['sharpe_ratio']:.2f}")
    print(f"  卡玛比率 (Calmar):    {m['calmar_ratio']:.2f}")
    print(f"  总交易笔数:           {m['total_trades']} 笔 (盈利: {m['win_trades']}, 亏损: {m['loss_trades']})")
    print(f"  交易胜率:             {m['win_rate_pct']:.1f}%")
    print(f"  盈亏比 (Profit/Loss): {m['profit_loss_ratio']:.2f}")
    print("─────────────────────────────────────────────────────────────────\n")

    # 显示最近 5 笔交易记录
    trades = res["trade_history"]
    if trades:
        print("最近成交记录 (样例):")
        for t in trades[-6:]:
            action = t['action']
            pnl_info = f" | 盈亏: {t.get('pnl', 0.0):+,.1f}元 ({t.get('pnl_pct', 0.0):+.2f}%) [{t.get('reason', '')}]" if action == "SELL" else ""
            print(f"  [{t['date']}] {action:<4} {t['symbol']} | {t['shares']}股 @ ￥{t['price']:.2f}{pnl_info}")


def cmd_analyze(args):
    """单只个股深度量化诊断"""
    sym = args.symbol
    print(f"\n=======================================================")
    print(f"  A-Share Quant Engine - 单股量化因子与风控诊断 [{sym}]")
    print(f"=======================================================\n")

    q = DataLayer.get_realtime_quote(sym)
    kl = DataLayer.get_kline_history(sym, num_days=120)

    if not kl:
        print(f"错误: 无法获取标的 {sym} 的行情数据")
        return

    name = q.get("name", sym)
    price = q.get("price", kl[-1]["close"])
    f = PVFactors.extract_factors(kl)
    atr_val, norm_atr = PVFactors.calculate_atr(kl, 14)

    print(f"标的名称: {name} ({sym})  现价: ￥{price:.2f}  当日涨跌幅: {q.get('change_pct', 0.0):+.2f}%")
    print(f"市盈率(PE): {q.get('pe', 0.0)}  换手率: {q.get('turnover', 0.0)}%  ST状态: {'是' if q.get('is_st') else '否'}\n")

    print("【量价核心 Alpha 因子】:")
    print(f"  • 5日/20日/60日收益率:   {f.get('ret_5d'):+.2f}% / {f.get('ret_20d'):+.2f}% / {f.get('ret_60d'):+.2f}%")
    print(f"  • 均线乖离率 (BIAS 20d):  {f.get('bias_20d'):+.2f}%")
    print(f"  • MACD 柱状值:           {f.get('macd_hist'):+.3f}")
    print(f"  • RSI(14) / KDJ(J):      {f.get('rsi_14'):.1f} / {f.get('kdj_j'):.1f}")
    print(f"  • 量能爆发比 (5日/20日): {f.get('vol_surge_5_20'):.2f} 倍")
    print(f"  • 筹码获利盘估计:         {f.get('profit_ratio'):+.2f}%\n")

    print("【动态风控标尺与建议】:")
    stop_atr = round(price - 2.0 * atr_val, 2)
    hard_stop = round(price * 0.94, 2)
    breakeven = round(price * 1.003, 2)
    tp1 = round(price * 1.05, 2)
    tp2 = round(price * 1.10, 2)

    print(f"  • ATR 真实波幅:         ￥{atr_val:.2f} (日均相对波幅 {norm_atr*100:.2f}%)")
    print(f"  • 动态跟踪止损位:       ￥{stop_atr:.2f}")
    print(f"  • T2 硬止损警戒位:      ￥{hard_stop:.2f} (-6.0%)")
    print(f"  • 保本跳变触发价:       ￥{breakeven:.2f} (+0.3% 覆盖税费)")
    print(f"  • 阶梯止盈第一档:       ￥{tp1:.2f} (+5.0% 减仓 1/3)")
    print(f"  • 阶梯止盈第二档:       ￥{tp2:.2f} (+10.0% 减仓 1/3)")


def main():
    parser = argparse.ArgumentParser(description="A-Share Quant Engine")
    subparsers = parser.add_subparsers(dest="command")

    # scan
    scan_p = subparsers.add_parser("scan", help="截面多因子扫描与选股")
    scan_p.add_argument("--universe", type=str, default="", help="股票代码列表，逗号分隔")
    scan_p.add_argument("--top", type=int, default=4, help="输出 Top-K 标的数")

    # backtest
    bt_p = subparsers.add_parser("backtest", help="历史多标的事件驱动回测")
    bt_p.add_argument("--days", type=int, default=250, help="回测天数")
    bt_p.add_argument("--top", type=int, default=4, help="最大持股数")

    # analyze
    ana_p = subparsers.add_parser("analyze", help="单股量化因子与风控诊断")
    ana_p.add_argument("symbol", type=str, help="股票代码 (如 600519)")

    args = parser.parse_args()

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
