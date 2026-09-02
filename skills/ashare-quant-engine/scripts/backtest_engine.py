"""
A-Share Quant Engine - Backtest Engine (事件驱动多标的回测引擎)
功能:
1. 真实 A股交易规则 (T+1、涨跌停无法成交过滤、印花税0.05%、佣金万2.5、滑点0.1%)
2. 逐日截面多因子重新打分与 Top-K 轮动选股
3. 严格执行 ATR 移动止损、保本跳变与阶梯分批止盈
4. 产出年化收益、最大回撤、夏普比率、卡玛比率、胜率、盈亏比与摩擦成本报告
"""

import math
from typing import Dict, List, Any, Optional, Tuple
from data_layer import DataLayer
from pv_factors import PVFactors
from unstructured_factors import UnstructuredFactors
from factor_synthesizer import FactorSynthesizer
from risk_position_manager import PositionSizer, AccountPortfolio, RiskEngine


class BacktestEngine:
    """事件驱动多标的量化回测引擎"""

    def __init__(
        self,
        symbols: List[str],
        initial_cash: float = 1000000.0,
        rebalance_interval: int = 5,
        top_k: int = 4,
        target_vol: float = 15.0,
        slippage: float = 0.001  # 0.1% 滑点
    ):
        self.symbols = symbols
        self.initial_cash = initial_cash
        self.rebalance_interval = rebalance_interval
        self.top_k = top_k
        self.target_vol = target_vol
        self.slippage = slippage

    def run(self, num_days: int = 250) -> Dict[str, Any]:
        """运行历史多标的事件驱动回测"""
        # 1. 预拉取所有标的历史日K
        kline_data: Dict[str, List[Dict[str, Any]]] = {}
        for s in self.symbols:
            kl = DataLayer.get_kline_history(s, num_days=num_days + 80, use_cache=True)
            if len(kl) >= 60:
                kline_data[s] = kl

        if not kline_data:
            return {"error": "未获取到足够的标的历史K线数据"}

        # 2. 对齐交易日历
        # 取交集或以主板权重股日历为基准
        sample_symbol = list(kline_data.keys())[0]
        all_dates = [k["date"] for k in kline_data[sample_symbol]]
        # 截取回测窗口 (前 60 日作为特征冷启动)
        if len(all_dates) < 60:
            return {"error": "历史交易日数不足 60 日"}

        test_dates = all_dates[60:]
        
        # 3. 初始化回测账户与净值曲线
        account = AccountPortfolio(initial_cash=self.initial_cash)
        equity_curve = []
        daily_returns = []

        # 4. 逐日事件循环
        for day_idx, current_date in enumerate(test_dates):
            # 获取当日各股价格快照
            daily_prices = {}
            daily_atrs = {}
            current_klines_window = {}

            for sym, klines in kline_data.items():
                # 寻找当天及之前的 K 线切片
                sub_k = [k for k in klines if k["date"] <= current_date]
                if sub_k and sub_k[-1]["date"] == current_date:
                    c = sub_k[-1]["close"]
                    daily_prices[sym] = c
                    atr_val, _ = PVFactors.calculate_atr(sub_k, 14)
                    daily_atrs[sym] = atr_val
                    current_klines_window[sym] = sub_k

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
                for act in actions:
                    sell_shares = act["shares"]
                    sell_price = act["price"] * (1.0 - self.slippage)  # 计入滑点
                    account.sell(sym, sell_shares, sell_price, current_date, reason=act["reason"])

            # ---------------------------------------------------------
            # Step B: 定期轮动再平衡 (Rebalance & Screening)
            # ---------------------------------------------------------
            if day_idx % self.rebalance_interval == 0:
                # 1. 提取所有标的截至今日的量价与情绪因子
                universe_factors = {}
                for sym, sub_k in current_klines_window.items():
                    if len(sub_k) < 30:
                        continue
                    factors = PVFactors.extract_factors(sub_k)
                    
                    # 模拟新闻舆情因子 (基于近期突破/均线态势与事件)
                    # 实盘时可接入真实新闻流，回测时基于收益与波动合成代表性情绪
                    sentiment = 0.2 if factors["ret_20d"] > 5 and factors["vol_surge_5_20"] > 1.2 else (
                        -0.3 if factors["ret_20d"] < -5 else 0.0
                    )
                    factors["sentiment_score"] = sentiment
                    universe_factors[sym] = factors

                # 2. 截面多因子标准化与排名
                ranked_univ = FactorSynthesizer.synthesize_universe(universe_factors)
                top_candidates = FactorSynthesizer.select_top_k(ranked_univ, top_k=self.top_k, min_percentile=60.0)
                target_top_symbols = [c["symbol"] for c in top_candidates]

                # 3. 仓位分配与买入
                current_total_equity = account.get_total_equity(daily_prices)
                
                # 计算组合目标总仓位
                port_target_w = PositionSizer.calculate_portfolio_target_weight(market_volatility_annual=18.0, target_vol=self.target_vol)

                for cand in top_candidates:
                    sym = cand["symbol"]
                    # 如果已经在持仓中，不重复开仓
                    if sym in account.positions:
                        continue
                    
                    p = daily_prices[sym]
                    atr_v = daily_atrs.get(sym, p * 0.03)
                    
                    alloc = PositionSizer.calculate_stock_allocation(
                        symbol=sym,
                        price=p,
                        atr=atr_v,
                        total_equity=current_total_equity,
                        portfolio_target_weight=port_target_w,
                        max_stocks=self.top_k
                    )

                    buy_shares = alloc["shares"]
                    buy_price = p * (1.0 + self.slippage)  # 计入滑点
                    if buy_shares > 0:
                        account.buy(sym, buy_shares, buy_price, current_date, atr_v)

            # ---------------------------------------------------------
            # Step C: 日终结算与净值记录
            # ---------------------------------------------------------
            account.end_of_day_settlement()
            end_equity = account.get_total_equity(daily_prices)
            
            if equity_curve:
                prev_eq = equity_curve[-1]["equity"]
                d_ret = (end_equity - prev_eq) / prev_eq
            else:
                d_ret = (end_equity - self.initial_cash) / self.initial_cash

            daily_returns.append(d_ret)
            equity_curve.append({
                "date": current_date,
                "equity": round(end_equity, 2),
                "cash": round(account.cash, 2),
                "positions_count": len(account.positions)
            })

        # 5. 绩效统计指标计算
        metrics = self._calculate_performance_metrics(account, equity_curve, daily_returns)
        return {
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trade_history": account.trade_history
        }

    @staticmethod
    def _calculate_performance_metrics(
        account: AccountPortfolio,
        equity_curve: List[Dict[str, Any]],
        daily_returns: List[float]
    ) -> Dict[str, Any]:
        """计算量化绩效指标 (CAGR, MaxDD, Sharpe, Calmar, 胜率, 盈亏比)"""
        if not equity_curve:
            return {}

        init_eq = equity_curve[0]["equity"]
        final_eq = equity_curve[-1]["equity"]
        total_return_pct = (final_eq - init_eq) / init_eq * 100.0
        n_days = len(equity_curve)
        years = n_days / 250.0

        # 年化收益率 (CAGR)
        cagr = (math.pow(final_eq / init_eq, 1.0 / max(0.01, years)) - 1.0) * 100.0 if final_eq > 0 else -100.0

        # 最大回撤 (Max Drawdown)
        max_dd = 0.0
        peak = init_eq
        for item in equity_curve:
            eq = item["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

        # 夏普比率 (Sharpe Ratio, 年化无风险利率 rf=2.0%)
        rf_daily = 0.02 / 250.0
        excess_returns = [r - rf_daily for r in daily_returns]
        mean_excess = sum(excess_returns) / len(excess_returns) if excess_returns else 0.0
        var_excess = sum((r - mean_excess) ** 2 for r in excess_returns) / max(1, len(excess_returns) - 1)
        std_excess = math.sqrt(var_excess)
        sharpe = (mean_excess / std_excess * math.sqrt(250)) if std_excess > 0 else 0.0

        # 卡玛比率 (Calmar Ratio)
        calmar = (cagr / max_dd) if max_dd > 0 else 0.0

        # 交易统计
        sells = [t for t in account.trade_history if t["action"] == "SELL"]
        n_trades = len(sells)
        wins = [t for t in sells if t.get("pnl", 0) > 0]
        losses = [t for t in sells if t.get("pnl", 0) < 0]
        
        win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
        total_gain = sum(t.get("pnl", 0) for t in wins)
        total_loss = abs(sum(t.get("pnl", 0) for t in losses))
        profit_loss_ratio = (total_gain / total_loss) if total_loss > 0 else (99.0 if total_gain > 0 else 1.0)

        return {
            "initial_cash": init_eq,
            "final_equity": round(final_eq, 2),
            "total_return_pct": round(total_return_pct, 2),
            "annualized_cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "calmar_ratio": round(calmar, 2),
            "total_trades": n_trades,
            "win_trades": len(wins),
            "loss_trades": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "profit_loss_ratio": round(profit_loss_ratio, 2)
        }
