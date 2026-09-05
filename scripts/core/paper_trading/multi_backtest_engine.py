# -*- coding: utf-8 -*-
"""
A-Share Quant Engine - Multi-Symbol Event-Driven Backtest Engine (事件驱动多标的回测引擎)

功能:
1. 真实 A股交易规则 (T+1、涨跌停无法成交过滤、印花税0.05%、佣金万2.5、滑点0.1%)
2. 逐日截面多因子重新打分与 Top-K 轮动选股
3. 严格执行 ATR 移动止损、保本跳变与阶梯分批止盈
4. 产出年化收益、最大回撤、夏普比率、卡玛比率、胜率、盈亏比与摩擦成本报告
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.data.data_layer import DataLayer
from core.indicators.pv_factors import PVFactors
from core.models.factor_synthesizer import FactorSynthesizer
from core.strategy.risk_position_manager import (
    AccountPortfolio,
    PositionSizer,
    RiskEngine,
)

try:
    from core.config import get_pool_stocks
    DEFAULT_UNIVERSE = get_pool_stocks("mainboard_24") or get_pool_stocks("h2_consensus")
except Exception:
    DEFAULT_UNIVERSE = []


class MultiBacktestEngine:
    """事件驱动多标的量化回测引擎"""

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        initial_cash: float = 1000000.0,
        rebalance_interval: int = 5,
        top_k: int = 4,
        target_vol: float = 15.0,
        slippage: float = 0.001,  # 0.1% 滑点
        commission_rate: float = 0.0003,
        slippage_rate: Optional[float] = None,
        max_positions: Optional[int] = None,
        **kwargs,
    ):
        self.symbols = symbols or DEFAULT_UNIVERSE
        self.initial_cash = initial_cash
        self.rebalance_interval = rebalance_interval
        self.top_k = max_positions if max_positions is not None else top_k
        self.target_vol = target_vol
        self.slippage = slippage_rate if slippage_rate is not None else slippage
        self.commission_rate = commission_rate

    @staticmethod
    def _limit_prices(symbol: str, prev_close: float) -> Tuple[float, float]:
        """返回 (涨停价, 跌停价)，按板块涨跌幅限制计算。

        - 科创板 688xxx/689xxx、创业板 300xxx/301xxx: 20%
        - 北交所 8xxxxx/4xxxxx/92xxxx: 30%
        - 主板及其他: 10%
        （ST 5% 因数据源无 ST 标识，暂按主板 10% 处理）
        """
        if not prev_close or prev_close <= 0:
            return (float("inf"), 0.0)
        raw = str(symbol).strip()
        digits = "".join(c for c in raw if c.isdigit())
        core_code = digits[-6:] if len(digits) >= 6 else digits

        if core_code.startswith(("688", "689", "30")):
            pct = 0.20
        elif core_code.startswith(("8", "4", "92")):
            pct = 0.30
        else:
            pct = 0.10
        return (
            round(prev_close * (1 + pct), 2),
            round(prev_close * (1 - pct), 2),
        )

    def run(
        self,
        num_days: int = 250,
        price_data: Optional[Dict[str, Any]] = None,
        strategy_func: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """运行历史多标的事件驱动回测"""
        # 1. 预拉取所有标的历史日K或使用传入的行情字典
        kline_data: Dict[str, List[Dict[str, Any]]] = {}
        if price_data:
            for s, v in price_data.items():
                if hasattr(v, "to_dict"):
                    kline_data[s] = v.to_dict(orient="records")
                elif isinstance(v, list):
                    kline_data[s] = v
        else:
            for s in self.symbols:
                kl = DataLayer.get_kline_history(s, num_days=num_days + 80, use_cache=True)
                if len(kl) >= 30:
                    kline_data[s] = kl

        if not kline_data:
            return {"error": "未获取到足够的标的历史K线数据"}

        # 2. 对齐交易日历 (以主板权重股日历为基准)
        sample_symbol = list(kline_data.keys())[0]
        all_dates = [k["date"] for k in kline_data[sample_symbol]]
        min_warmup = 30 if len(all_dates) >= 40 else 5
        if len(all_dates) <= min_warmup:
            return {"error": f"历史交易日数不足 {min_warmup} 日"}

        test_dates = all_dates[min_warmup:]

        # 3. 初始化回测账户与净值曲线
        account = AccountPortfolio(initial_cash=self.initial_cash)
        equity_curve: List[Dict[str, Any]] = []
        daily_returns: List[float] = []

        # 4. 逐日事件循环
        for day_idx, current_date in enumerate(test_dates):
            daily_prices: Dict[str, float] = {}
            daily_atrs: Dict[str, float] = {}
            daily_limit_up: Dict[str, float] = {}
            daily_limit_down: Dict[str, float] = {}
            current_klines_window: Dict[str, List[Dict[str, Any]]] = {}

            for sym, klines in kline_data.items():
                sub_k = [k for k in klines if k["date"] <= current_date]
                if sub_k and sub_k[-1]["date"] == current_date:
                    c = sub_k[-1]["close"]
                    daily_prices[sym] = c
                    atr_val, _ = PVFactors.calculate_atr(sub_k, 14)
                    daily_atrs[sym] = atr_val
                    current_klines_window[sym] = sub_k
                    # 涨跌停价基于前一交易日收盘价计算
                    prev_close = sub_k[-2]["close"] if len(sub_k) >= 2 else None
                    if prev_close:
                        lu, ld = self._limit_prices(sym, prev_close)
                        daily_limit_up[sym] = lu
                        daily_limit_down[sym] = ld

            # ---------------------------------------------------------
            # 策略信号分发 (自定义策略模式 或 默认多因子合成轮动)
            # ---------------------------------------------------------
            if strategy_func is not None:
                try:
                    import pandas as pd
                    df_window = {sym: pd.DataFrame(kl) for sym, kl in current_klines_window.items()}
                except ImportError:
                    df_window = current_klines_window

                signals = strategy_func(current_date, df_window, account.positions)
                for sig in (signals or []):
                    sym = sig.get("code")
                    act = sig.get("action")
                    if act == "buy" and sym in daily_prices:
                        # 涨停封板无法买入
                        if sym in daily_limit_up and daily_prices[sym] >= daily_limit_up[sym] - 1e-9:
                            continue
                        p = daily_prices[sym] * (1.0 + self.slippage)
                        cur_eq = account.get_total_equity(daily_prices)
                        target_pct = sig.get("target_pct", 1.0 / max(1, self.top_k))
                        target_val = cur_eq * target_pct
                        shares = int(target_val / (p * 100)) * 100
                        if shares > 0 and account.cash >= shares * p:
                            atr_v = daily_atrs.get(sym, p * 0.03)
                            account.buy(sym, shares, p, current_date, atr_v)
                    elif act == "sell" and sym in account.positions:
                        # 跌停封板无法卖出
                        if sym in daily_limit_down and daily_prices[sym] <= daily_limit_down[sym] + 1e-9:
                            continue
                        pos = account.positions[sym]
                        p = daily_prices[sym] * (1.0 - self.slippage)
                        account.sell(sym, pos["shares"], p, current_date, reason="strategy_signal")
            else:
                # ---------------------------------------------------------
                # Step A: 现有持仓风控与止盈止损检查
                # ---------------------------------------------------------
                active_symbols = list(account.positions.keys())
                for sym in active_symbols:
                    if sym not in daily_prices:
                        continue
                    pos = account.positions[sym]
                    cur_p = daily_prices[sym]
                    cur_atr = daily_atrs.get(sym, cur_p * 0.03)

                    actions = RiskEngine.evaluate_position_risk(pos, cur_p, cur_atr, current_date)
                    # 跌停封板无法卖出
                    if sym in daily_limit_down and cur_p <= daily_limit_down[sym] + 1e-9:
                        continue
                    for act in actions:
                        sell_shares = act["shares"]
                        sell_price = act["price"] * (1.0 - self.slippage)  # 计入滑点
                        account.sell(sym, sell_shares, sell_price, current_date, reason=act["reason"])

                # ---------------------------------------------------------
                # Step B: 定期轮动再平衡 (Rebalance & Screening)
                # ---------------------------------------------------------
                if day_idx % self.rebalance_interval == 0:
                    universe_factors: Dict[str, Dict[str, Any]] = {}
                    for sym, sub_k in current_klines_window.items():
                        if len(sub_k) < 30:
                            continue
                        factors = PVFactors.extract_factors(sub_k)

                        # 模拟舆情因子
                        sentiment = (
                            0.2
                            if factors["ret_20d"] > 5 and factors["vol_surge_5_20"] > 1.2
                            else (-0.3 if factors["ret_20d"] < -5 else 0.0)
                        )
                        factors["sentiment_score"] = sentiment
                        universe_factors[sym] = factors

                    ranked_univ = FactorSynthesizer.synthesize_universe(universe_factors)
                    top_candidates = FactorSynthesizer.select_top_k(
                        ranked_univ, top_k=self.top_k, min_percentile=60.0
                    )

                    current_total_equity = account.get_total_equity(daily_prices)
                    port_target_w = PositionSizer.calculate_portfolio_target_weight(
                        market_volatility_annual=18.0, target_vol=self.target_vol
                    )

                    for cand in top_candidates:
                        sym = cand["symbol"]
                        if sym in account.positions:
                            continue

                        p = daily_prices.get(sym, 0.0)
                        if p <= 0:
                            continue
                        # 涨停封板无法买入
                        if sym in daily_limit_up and p >= daily_limit_up[sym] - 1e-9:
                            continue
                        atr_v = daily_atrs.get(sym, p * 0.03)

                        alloc = PositionSizer.calculate_stock_allocation(
                            symbol=sym,
                            price=p,
                            atr=atr_v,
                            total_equity=current_total_equity,
                            portfolio_target_weight=port_target_w,
                            max_stocks=self.top_k,
                        )

                        buy_shares = alloc["shares"]
                        buy_price = p * (1.0 + self.slippage)
                        if buy_shares > 0:
                            account.buy(sym, buy_shares, buy_price, current_date, atr_v)


            # ---------------------------------------------------------
            # Step C: 日终结算与净值记录
            # ---------------------------------------------------------
            account.end_of_day_settlement()
            end_equity = account.get_total_equity(daily_prices)

            if equity_curve:
                prev_eq = equity_curve[-1]["equity"]
                d_ret = (end_equity - prev_eq) / prev_eq if prev_eq > 0 else 0.0
            else:
                d_ret = (
                    (end_equity - self.initial_cash) / self.initial_cash
                    if self.initial_cash > 0
                    else 0.0
                )

            daily_returns.append(d_ret)
            equity_curve.append({
                "date": current_date,
                "equity": round(end_equity, 2),
                "cash": round(account.cash, 2),
                "positions_count": len(account.positions),
            })

        # 5. 绩效统计指标计算
        metrics = self._calculate_performance_metrics(account, equity_curve, daily_returns)
        return {
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trade_history": account.trade_history,
            **metrics,
        }


    @staticmethod
    def _calculate_performance_metrics(
        account: AccountPortfolio,
        equity_curve: List[Dict[str, Any]],
        daily_returns: List[float],
    ) -> Dict[str, Any]:
        """计算量化绩效指标 (CAGR, MaxDD, Sharpe, Calmar, 胜率, 盈亏比)"""
        if not equity_curve:
            return {}

        init_eq = (
            getattr(account, "initial_cash", equity_curve[0]["equity"])
            if getattr(account, "initial_cash", None)
            else equity_curve[0]["equity"]
        )
        final_eq = equity_curve[-1]["equity"]
        total_return_pct = (final_eq - init_eq) / init_eq * 100.0 if init_eq > 0 else 0.0

        n_days = len(equity_curve)
        years = n_days / 250.0

        cagr = (
            (math.pow(final_eq / init_eq, 1.0 / max(0.01, years)) - 1.0) * 100.0
            if final_eq > 0 and init_eq > 0
            else -100.0
        )

        max_dd = 0.0
        peak = init_eq
        for item in equity_curve:
            eq = item["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        rf_daily = 0.02 / 250.0
        excess_returns = [r - rf_daily for r in daily_returns]
        mean_excess = sum(excess_returns) / len(excess_returns) if excess_returns else 0.0
        var_excess = (
            sum((r - mean_excess) ** 2 for r in excess_returns) / max(1, len(excess_returns) - 1)
            if excess_returns
            else 0.0
        )
        std_excess = math.sqrt(var_excess)
        sharpe = (mean_excess / std_excess * math.sqrt(250)) if std_excess > 0 else 0.0
        calmar = (cagr / max_dd) if max_dd > 0 else 0.0

        sells = [t for t in account.trade_history if t.get("action") == "SELL"]
        n_trades = len(sells)
        wins = [t for t in sells if t.get("pnl", 0) > 0]
        losses = [t for t in sells if t.get("pnl", 0) < 0]

        win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
        total_gain = sum(t.get("pnl", 0) for t in wins)
        total_loss = abs(sum(t.get("pnl", 0) for t in losses))
        profit_loss_ratio = (
            (total_gain / total_loss) if total_loss > 0 else (99.0 if total_gain > 0 else 1.0)
        )

        return {
            "initial_cash": init_eq,
            "final_equity": round(final_eq, 2),
            "total_return_pct": round(total_return_pct, 2),
            "annualized_cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "calmar_ratio": round(calmar, 2),
            "total_trades": n_trades,
            "trade_count": n_trades,
            "win_trades": len(wins),
            "loss_trades": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "profit_loss_ratio": round(profit_loss_ratio, 2),
            "daily_records": equity_curve,
        }



# 兼容别名
BacktestEngine = MultiBacktestEngine


def main():
    parser = argparse.ArgumentParser(description="多标的事件驱动量化回测引擎")
    parser.add_argument("--symbols", help="标的代码列表，逗号分隔 (默认: 12只核心权重股)")
    parser.add_argument("--days", type=int, default=250, help="回测天数 (默认 250)")
    parser.add_argument("--top", type=int, default=4, help="持仓轮动槽位数 (默认 4)")
    parser.add_argument("--cash", type=float, default=1000000.0, help="初始本金 (默认 1000000)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else DEFAULT_UNIVERSE
    engine = MultiBacktestEngine(
        symbols=symbols,
        initial_cash=args.cash,
        top_k=args.top,
    )
    res = engine.run(num_days=args.days)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if "error" in res:
        print(f"❌ 回测失败: {res['error']}")
        return

    m = res["metrics"]
    print("\n─────────────────────── 多标的回测绩效报告 ───────────────────────")
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
    print("───────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
