#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股回测评估引擎 — 纯Python标准库实现

接收策略信号和K线数据，输出业界标准评估指标(夏普比率、最大回撤、Calmar比率、
盈亏比、Recovery Factor、胜率等)，并支持样本内外分割过拟合检测。

依赖: 仅Python标准库 (math/json/datetime)
不依赖: pandas / numpy / akshare

K线格式: [[date, open, close, high, low, volume], ...]
    日期=索引0, 开盘=1, 收盘=2, 最高=3, 最低=4, 成交量=5
"""

import math
import json
from datetime import datetime, timedelta


class BacktestEngine:
    """A股回测引擎

    交易成本模型:
        - 佣金: 万分之2.5, 最低5元/笔
        - 印花税: 卖出万分之5
        - 滑点: 1个tick = 0.01元/股
    交易规则:
        - T+1: 买入当日不可卖出
        - 买入数量必须是100股整数倍
        - 涨跌停限制: 价格触及涨跌停板时无法成交
    """

    def __init__(self, initial_cash=None, commission_rate=None,
                 stamp_tax=None, slippage_ticks=None, risk_free_rate=None,
                 config_path=None):
        """初始化回测引擎

        参数优先级: 显式参数 > config.yaml > 默认值

        Args:
            initial_cash: 初始资金(默认100万)
            commission_rate: 佣金率(默认万分之2.5 = 0.00025)
            stamp_tax: 印花税(卖出万分之5 = 0.0005)
            slippage_ticks: 滑点tick数(默认1个最小变动价位0.01元)
            risk_free_rate: 无风险利率(默认2%)
            config_path: config.yaml 路径(可选, 自动探测默认路径)
        """
        # 尝试从 config.yaml 加载
        cfg = {}
        if config_path is None:
            # 自动探测默认路径
            import os
            for p in [
                os.path.join(os.path.dirname(__file__), "..", "config.yaml"),
                os.path.expanduser("skills/a-stocks/config.yaml"),
            ]:
                if os.path.exists(p):
                    config_path = p
                    break
        if config_path:
            try:
                import yaml
                with open(config_path) as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception:
                pass

        bt_cfg = cfg.get("backtest", {})

        self.initial_cash = initial_cash if initial_cash is not None else bt_cfg.get("initial_cash", 1000000)
        self.commission_rate = commission_rate if commission_rate is not None else bt_cfg.get("commission_rate", 0.00025)
        self.stamp_tax = stamp_tax if stamp_tax is not None else bt_cfg.get("stamp_tax", 0.0005)
        _slippage = slippage_ticks if slippage_ticks is not None else bt_cfg.get("slippage_ticks", 1)
        self.risk_free_rate = risk_free_rate if risk_free_rate is not None else bt_cfg.get("risk_free_rate", 0.02)

        self.tick_size = 0.01  # A股最小变动价位0.01元
        self.slippage = _slippage * self.tick_size

    # ------------------------------------------------------------------
    # 交易成本计算
    # ------------------------------------------------------------------
    def _calc_commission(self, amount):
        """计算佣金: 万分之2.5, 最低5元"""
        comm = amount * self.commission_rate
        return max(comm, 5.0)

    def _calc_stamp_tax(self, amount):
        """计算印花税: 卖出万分之5"""
        return amount * self.stamp_tax

    # ------------------------------------------------------------------
    # 涨跌停判断
    # ------------------------------------------------------------------
    @staticmethod
    def _is_limit_up(prev_close, price):
        """判断是否触及涨停板(10%) — ST股5%简化处理略"""
        if prev_close is None or prev_close <= 0:
            return False
        limit_up_price = round(prev_close * 1.1, 2)
        return price >= limit_up_price

    @staticmethod
    def _is_limit_down(prev_close, price):
        """判断是否触及跌停板(10%)"""
        if prev_close is None or prev_close <= 0:
            return False
        limit_down_price = round(prev_close * 0.9, 2)
        return price <= limit_down_price

    @staticmethod
    def _parse_date(date_str):
        """解析日期字符串，支持 '2026-01-15' 或 '2026-01-15 00:00:00' 格式"""
        if isinstance(date_str, str):
            date_str = date_str.strip()
            if ' ' in date_str:
                date_str = date_str.split(' ')[0]
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                try:
                    return datetime.strptime(date_str, "%Y/%m/%d")
                except ValueError:
                    return None
        elif isinstance(date_str, (int, float)):
            try:
                return datetime.strptime(str(int(date_str)), "%Y%m%d")
            except ValueError:
                return None
        return None

    @staticmethod
    def _days_between(d1, d2):
        """计算两个日期之间的天数差(交易日近似为日历天)"""
        if d1 is None or d2 is None:
            return 0
        delta = d2 - d1
        return abs(delta.days)

    # ------------------------------------------------------------------
    # 滑点调整后的实际成交价
    # ------------------------------------------------------------------
    def _fill_price(self, signal_price, action):
        """根据滑点调整实际成交价

        买入: 成交价 = 信号价 + 滑点
        卖出: 成交价 = 信号价 - 滑点
        """
        if action == "buy":
            return round(signal_price + self.slippage, 2)
        else:
            return round(signal_price - self.slippage, 2)

    # ------------------------------------------------------------------
    # 核心回测: 基于显式信号列表
    # ------------------------------------------------------------------
    def run(self, klines, signals):
        """执行回测 — 基于预先生成的信号列表

        Args:
            klines: [[date, open, close, high, low, volume], ...]
            signals: [{"date": "2026-01-15", "action": "buy", "price": 10.5, "quantity": 1000}, ...]
                    action: "buy" or "sell"
                    price: 信号价格(理想价格)
                    quantity: 买入/卖出数量(买入必须是100的整数倍)

        Returns:
            dict: 包含 trades, equity_curve, metrics 的完整回测结果
        """
        if not klines:
            return self._empty_result()

        # 构建日期->K线索引映射
        date_to_kline = {}
        prev_close_map = {}  # 每个日期对应的前一交易日收盘价(用于涨跌停判断)
        prev_close = None
        for i, k in enumerate(klines):
            date_str = str(k[0])
            date_to_kline[date_str] = i
            prev_close_map[date_str] = prev_close
            prev_close = float(k[2])

        # 按日期排序信号
        sorted_signals = sorted(signals, key=lambda s: s.get("date", ""))

        # 回测状态
        cash = float(self.initial_cash)
        position = 0          # 持仓数量(股)
        entry_price = 0.0     # 持仓成本价
        entry_date = None     # 持仓日期对象(T+1判断)
        buy_date_str = None   # 买入日期字符串(T+1判断)

        trades = []           # 已完成交易列表
        equity_curve = []     # 每日净值曲线
        open_position = None  # 当前持仓记录 {entry_date, entry_price, quantity, entry_date_str}

        # 逐日遍历K线
        for i, k in enumerate(klines):
            date_str = str(k[0])
            open_p = float(k[1])
            close_p = float(k[2])
            high_p = float(k[3])
            low_p = float(k[4])
            vol = float(k[5]) if len(k) > 5 else 0.0

            p_close = prev_close_map.get(date_str)

            # 查找当日信号
            today_signals = [s for s in sorted_signals if str(s.get("date", "")) == date_str]

            for sig in today_signals:
                action = sig.get("action", "hold")
                sig_price = float(sig.get("price", close_p))
                sig_qty = int(sig.get("quantity", 0))

                if action == "buy" and position == 0:
                    # 买入逻辑
                    qty = (sig_qty // 100) * 100  # 确保100股整数倍
                    if qty <= 0:
                        continue

                    # 涨跌停判断: 如果当日价格已经涨停，无法买入
                    fill = self._fill_price(sig_price, "buy")
                    if p_close and self._is_limit_up(p_close, open_p):
                        # 开盘即涨停，全天无法买入
                        continue

                    # 成交金额
                    amount = fill * qty
                    commission = self._calc_commission(amount)
                    total_cost = amount + commission

                    if total_cost > cash:
                        # 资金不足，减少买入量
                        max_qty = int((cash - commission) / fill / 100) * 100
                        if max_qty <= 0:
                            continue
                        qty = max_qty
                        amount = fill * qty
                        commission = self._calc_commission(amount)
                        total_cost = amount + commission

                    cash -= total_cost
                    position = qty
                    entry_price = fill
                    entry_date = self._parse_date(date_str)
                    buy_date_str = date_str
                    open_position = {
                        "entry_date": date_str,
                        "entry_price": fill,
                        "quantity": qty,
                        "entry_date_obj": entry_date,
                    }

                elif action == "sell" and position > 0:
                    # 卖出逻辑
                    # T+1: 买入当日不能卖出
                    if buy_date_str == date_str:
                        continue

                    qty = min(sig_qty, position)
                    if qty <= 0:
                        continue

                    # 跌停判断: 如果当日价格已经跌停，无法卖出
                    fill = self._fill_price(sig_price, "sell")
                    if p_close and self._is_limit_down(p_close, open_p):
                        continue

                    amount = fill * qty
                    commission = self._calc_commission(amount)
                    stamp = self._calc_stamp_tax(amount)
                    net = amount - commission - stamp

                    cash += net
                    position -= qty

                    # 记录交易
                    if open_position:
                        exit_date_obj = self._parse_date(date_str)
                        holding_days = self._days_between(
                            open_position.get("entry_date_obj"), exit_date_obj
                        )
                        cost = open_position["entry_price"] * qty
                        pnl = net - cost if open_position["entry_price"] * qty else 0.0
                        # 更准确的pnl计算
                        trade_pnl = (fill - open_position["entry_price"]) * qty \
                                    - commission - stamp \
                                    - self._calc_commission(open_position["entry_price"] * qty)
                        pnl_pct = (trade_pnl / cost * 100) if cost > 0 else 0.0

                        trades.append({
                            "entry_date": open_position["entry_date"],
                            "exit_date": date_str,
                            "entry_price": round(open_position["entry_price"], 4),
                            "exit_price": round(fill, 4),
                            "quantity": qty,
                            "pnl": round(trade_pnl, 2),
                            "pnl_pct": round(pnl_pct, 2),
                            "holding_days": holding_days,
                        })

                    if position == 0:
                        open_position = None
                        entry_price = 0.0
                        buy_date_str = None

            # 每日结算: 计算权益 = 现金 + 持仓市值
            position_value = position * close_p
            equity = cash + position_value
            equity_curve.append({
                "date": date_str,
                "equity": round(equity, 2),
                "position_value": round(position_value, 2),
            })

        return self._build_result(trades, equity_curve, klines)

    # ------------------------------------------------------------------
    # 策略函数回测: 逐日调用策略生成信号
    # ------------------------------------------------------------------
    def run_strategy(self, klines, strategy_func, start_date=None, end_date=None):
        """用策略函数在K线上逐日生成信号并回测

        Args:
            klines: K线数据
            strategy_func: callable(klines, idx, current_position, current_cash) -> {"action", "quantity"}
            start_date: 回测起始日期(字符串或None)
            end_date: 回测起始日期(字符串或None)

        Returns:
            同 run() 的返回值
        """
        if not klines:
            return self._empty_result()

        # 日期过滤
        start_dt = self._parse_date(start_date) if start_date else None
        end_dt = self._parse_date(end_date) if end_date else None

        # 回测状态
        cash = float(self.initial_cash)
        position = 0
        entry_price = 0.0
        entry_date = None
        buy_date_str = None

        trades = []
        equity_curve = []
        open_position = None

        prev_close = None

        for i, k in enumerate(klines):
            date_str = str(k[0])
            open_p = float(k[1])
            close_p = float(k[2])
            high_p = float(k[3])
            low_p = float(k[4])

            # 日期过滤
            cur_dt = self._parse_date(date_str)
            if start_dt and cur_dt and cur_dt < start_dt:
                prev_close = close_p
                continue
            if end_dt and cur_dt and cur_dt > end_dt:
                break

            # 涨跌停判断
            limit_up = self._is_limit_up(prev_close, open_p) if prev_close else False
            limit_down = self._is_limit_down(prev_close, open_p) if prev_close else False

            # 调用策略函数获取信号
            try:
                sig = strategy_func(klines, i, position, cash)
            except Exception:
                sig = {"action": "hold"}
            action = sig.get("action", "hold")

            if action == "buy" and position == 0 and not limit_up:
                # 买入: 使用当日收盘价作为信号价
                sig_price = sig.get("price", close_p)
                qty = sig.get("quantity", 0)
                if qty is None:
                    # 策略未指定数量，默认满仓95%
                    qty = int(cash * 0.95 / close_p / 100) * 100
                qty = (qty // 100) * 100
                if qty <= 0:
                    pass
                else:
                    fill = self._fill_price(sig_price, "buy")
                    amount = fill * qty
                    commission = self._calc_commission(amount)
                    total_cost = amount + commission
                    if total_cost > cash:
                        max_qty = int((cash - commission) / fill / 100) * 100
                        if max_qty > 0:
                            qty = max_qty
                            amount = fill * qty
                            commission = self._calc_commission(amount)
                            total_cost = amount + commission
                        else:
                            qty = 0
                    if qty > 0:
                        cash -= total_cost
                        position = qty
                        entry_price = fill
                        entry_date = cur_dt
                        buy_date_str = date_str
                        open_position = {
                            "entry_date": date_str,
                            "entry_price": fill,
                            "quantity": qty,
                            "entry_date_obj": entry_date,
                        }

            elif action == "sell" and position > 0 and not limit_down:
                # T+1: 买入当日不可卖出
                if buy_date_str == date_str:
                    pass
                else:
                    qty = sig.get("quantity", position)
                    if qty is None:
                        qty = position
                    qty = min(qty, position)
                    if qty > 0:
                        sig_price = sig.get("price", close_p)
                        fill = self._fill_price(sig_price, "sell")
                        amount = fill * qty
                        commission = self._calc_commission(amount)
                        stamp = self._calc_stamp_tax(amount)
                        net = amount - commission - stamp

                        cash += net
                        position -= qty

                        if open_position:
                            exit_dt = cur_dt
                            holding_days = self._days_between(
                                open_position.get("entry_date_obj"), exit_dt
                            )
                            cost = open_position["entry_price"] * qty
                            buy_comm = self._calc_commission(open_position["entry_price"] * qty)
                            trade_pnl = (fill - open_position["entry_price"]) * qty \
                                        - commission - stamp - buy_comm
                            pnl_pct = (trade_pnl / cost * 100) if cost > 0 else 0.0

                            trades.append({
                                "entry_date": open_position["entry_date"],
                                "exit_date": date_str,
                                "entry_price": round(open_position["entry_price"], 4),
                                "exit_price": round(fill, 4),
                                "quantity": qty,
                                "pnl": round(trade_pnl, 2),
                                "pnl_pct": round(pnl_pct, 2),
                                "holding_days": holding_days,
                            })

                        if position == 0:
                            open_position = None
                            entry_price = 0.0
                            buy_date_str = None

            # 每日结算
            position_value = position * close_p
            equity = cash + position_value
            equity_curve.append({
                "date": date_str,
                "equity": round(equity, 2),
                "position_value": round(position_value, 2),
            })

            prev_close = close_p

        return self._build_result(trades, equity_curve, klines)

    # ------------------------------------------------------------------
    # 样本分割
    # ------------------------------------------------------------------
    def split_sample(self, klines, ratio=0.7):
        """将K线数据分为样本内和样本外

        Args:
            klines: K线数据
            ratio: 样本内比例(默认0.7)

        Returns:
            (in_sample_klines, out_sample_klines)
        """
        split_idx = int(len(klines) * ratio)
        return klines[:split_idx], klines[split_idx:]

    # ------------------------------------------------------------------
    # 构建回测结果(计算所有指标)
    # ------------------------------------------------------------------
    def _build_result(self, trades, equity_curve, klines):
        """从交易记录和净值曲线计算所有评估指标"""

        metrics = self._calc_metrics(trades, equity_curve)

        result = {
            "trades": trades,
            "equity_curve": equity_curve,
            "metrics": metrics,
            "benchmark": {
                "benchmark_return": 0.0,
                "alpha": 0.0,
                "beta": 0.0,
            },
            "overfitting_check": {
                "in_sample_sharpe": 0.0,
                "out_sample_sharpe": 0.0,
                "overfitting_suspected": False,
                "warning": "未执行样本内外分割检测",
            },
        }
        return result

    # ------------------------------------------------------------------
    # 指标计算
    # ------------------------------------------------------------------
    def _calc_metrics(self, trades, equity_curve):
        """计算全部评估指标

        Args:
            trades: 交易记录列表
            equity_curve: 净值曲线列表

        Returns:
            dict: 所有评估指标
        """
        metrics = {}

        # --- 基本交易统计 ---
        total_trades = len(trades)
        winning = [t for t in trades if t["pnl"] > 0]
        losing = [t for t in trades if t["pnl"] < 0]
        even = [t for t in trades if t["pnl"] == 0]

        winning_trades = len(winning)
        losing_trades = len(losing)

        # 胜率
        if total_trades > 0:
            win_rate = (winning_trades / total_trades) * 100
        else:
            win_rate = 0.0

        # 平均盈亏百分比
        win_pcts = [t["pnl_pct"] for t in winning]
        loss_pcts = [t["pnl_pct"] for t in losing]
        avg_win = sum(win_pcts) / len(win_pcts) if win_pcts else 0.0
        avg_loss = sum(loss_pcts) / len(loss_pcts) if loss_pcts else 0.0
        max_win = max(win_pcts) if win_pcts else 0.0
        max_loss = min(loss_pcts) if loss_pcts else 0.0

        # 平均持仓天数
        holding_days_list = [t["holding_days"] for t in trades]
        avg_holding = sum(holding_days_list) / len(holding_days_list) if holding_days_list else 0.0

        # --- 资金曲线指标 ---
        if not equity_curve:
            # 无净值数据
            return self._empty_metrics(total_trades, winning_trades, losing_trades)

        final_equity = equity_curve[-1]["equity"]
        total_return = (final_equity - self.initial_cash) / self.initial_cash * 100

        # 年化收益率
        num_days = len(equity_curve)
        if num_days > 1:
            years = num_days / 252.0
            if years > 0 and final_equity > 0:
                annual_return = ((final_equity / self.initial_cash) ** (1.0 / years) - 1) * 100
            else:
                annual_return = 0.0
        else:
            annual_return = 0.0

        # 日收益率序列
        daily_returns = []
        for i in range(1, len(equity_curve)):
            prev_eq = equity_curve[i - 1]["equity"]
            cur_eq = equity_curve[i]["equity"]
            if prev_eq > 0:
                daily_returns.append((cur_eq - prev_eq) / prev_eq)
            else:
                daily_returns.append(0.0)

        # 年化波动率: 日收益率标准差 * sqrt(252)
        if len(daily_returns) > 1:
            mean_ret = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            std_daily = math.sqrt(variance)
            annual_vol = std_daily * math.sqrt(252)
        else:
            annual_vol = 0.0

        # 夏普比率: (年化收益率% / 100 - 无风险利率) / 年化波动率
        if annual_vol > 0:
            sharpe = (annual_return / 100.0 - self.risk_free_rate) / annual_vol
        else:
            sharpe = 0.0

        # 最大回撤
        max_dd, max_dd_duration, recovery_time = self._calc_max_drawdown(equity_curve)

        # Calmar比率: 年化收益率 / 最大回撤(绝对值)
        if max_dd > 0:
            calmar = abs(annual_return) / max_dd
        else:
            calmar = 0.0

        # 盈亏比(Profit Factor): 总盈利金额 / 总亏损金额(绝对值)
        total_profit = sum(t["pnl"] for t in winning)
        total_loss_abs = abs(sum(t["pnl"] for t in losing))
        if total_loss_abs > 0:
            profit_factor = total_profit / total_loss_abs
        else:
            profit_factor = total_profit if total_profit > 0 else 0.0

        # Recovery Factor: 净利润 / 最大回撤金额
        net_profit = final_equity - self.initial_cash
        # 最大回撤金额 = 最大回撤%时的回撤额
        max_dd_amount = self._calc_max_dd_amount(equity_curve)
        if max_dd_amount > 0:
            recovery_factor = net_profit / max_dd_amount
        else:
            recovery_factor = 0.0

        metrics = {
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_dd, 2),
            "calmar_ratio": round(calmar, 4),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 4),
            "recovery_factor": round(recovery_factor, 4),
            "avg_holding_days": round(avg_holding, 1),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "max_win": round(max_win, 2),
            "max_loss": round(max_loss, 2),
            "max_drawdown_duration": max_dd_duration,
            "recovery_time": recovery_time,
        }

        return metrics

    # ------------------------------------------------------------------
    # 最大回撤计算
    # ------------------------------------------------------------------
    @staticmethod
    def _calc_max_drawdown(equity_curve):
        """计算最大回撤百分比、持续天数、恢复天数

        最大回撤: 从历史峰值到后续谷值的最大百分比跌幅
        持续天数: 从峰值到谷值的天数
        恢复天数: 从谷值恢复到峰值的天数(未恢复返回-1)

        Returns:
            (max_dd_pct, max_dd_duration, recovery_time)
        """
        if not equity_curve:
            return 0.0, 0, 0

        peak = equity_curve[0]["equity"]
        max_dd = 0.0
        max_dd_duration = 0
        recovery_time = 0

        peak_idx = 0
        trough_idx = 0
        temp_peak_idx = 0

        for i, point in enumerate(equity_curve):
            eq = point["equity"]
            if eq > peak:
                peak = eq
                temp_peak_idx = i

            if peak > 0:
                dd = (peak - eq) / peak * 100
                if dd > max_dd:
                    max_dd = dd
                    peak_idx = temp_peak_idx
                    trough_idx = i

        # 最大回撤持续天数 = 谷值索引 - 峰值索引
        max_dd_duration = trough_idx - peak_idx if trough_idx > peak_idx else 0

        # 恢复天数: 从谷值后寻找恢复到峰值的天数
        peak_value = equity_curve[peak_idx]["equity"]
        recovered = False
        for j in range(trough_idx + 1, len(equity_curve)):
            if equity_curve[j]["equity"] >= peak_value:
                recovery_time = j - trough_idx
                recovered = True
                break
        if not recovered:
            recovery_time = -1  # 未恢复

        return max_dd, max_dd_duration, recovery_time

    @staticmethod
    def _calc_max_dd_amount(equity_curve):
        """计算最大回撤金额(用于Recovery Factor)"""
        if not equity_curve:
            return 0.0

        peak = equity_curve[0]["equity"]
        max_dd_amount = 0.0

        for point in equity_curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd_amount = peak - eq
            if dd_amount > max_dd_amount:
                max_dd_amount = dd_amount

        return max_dd_amount

    # ------------------------------------------------------------------
    # 空结果
    # ------------------------------------------------------------------
    def _empty_result(self):
        """返回空回测结果"""
        return {
            "trades": [],
            "equity_curve": [],
            "metrics": self._empty_metrics(0, 0, 0),
            "benchmark": {
                "benchmark_return": 0.0,
                "alpha": 0.0,
                "beta": 0.0,
            },
            "overfitting_check": {
                "in_sample_sharpe": 0.0,
                "out_sample_sharpe": 0.0,
                "overfitting_suspected": False,
                "warning": "无K线数据",
            },
        }

    @staticmethod
    def _empty_metrics(total_trades, winning_trades, losing_trades):
        """返回空指标(无交易或无数据时)"""
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "calmar_ratio": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "recovery_factor": 0.0,
            "avg_holding_days": 0.0,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_win": 0.0,
            "max_loss": 0.0,
            "max_drawdown_duration": 0,
            "recovery_time": 0,
        }

    # ------------------------------------------------------------------
    # 基准对比(沪深300等)
    # ------------------------------------------------------------------
    def compare_benchmark(self, result, benchmark_klines):
        """计算与基准的对比指标(Alpha/Beta)

        Args:
            result: run() 或 run_strategy() 的返回结果
            benchmark_klines: 基准K线数据

        Returns:
            更新后的result dict, 带有benchmark字段
        """
        if not benchmark_klines or not result.get("equity_curve"):
            return result

        # 基准日收益率
        bench_closes = [float(k[2]) for k in benchmark_klines]
        bench_returns = []
        for i in range(1, len(bench_closes)):
            if bench_closes[i - 1] > 0:
                bench_returns.append((bench_closes[i] - bench_closes[i - 1]) / bench_closes[i - 1])
            else:
                bench_returns.append(0.0)

        # 策略日收益率
        eq = result["equity_curve"]
        strat_returns = []
        for i in range(1, len(eq)):
            prev = eq[i - 1]["equity"]
            cur = eq[i]["equity"]
            if prev > 0:
                strat_returns.append((cur - prev) / prev)
            else:
                strat_returns.append(0.0)

        # 对齐长度
        n = min(len(strat_returns), len(bench_returns))
        strat_r = strat_returns[:n]
        bench_r = bench_returns[:n]

        if n < 2:
            result["benchmark"] = {
                "benchmark_return": 0.0,
                "alpha": 0.0,
                "beta": 0.0,
            }
            return result

        # Beta = Cov(strat, bench) / Var(bench)
        mean_s = sum(strat_r) / n
        mean_b = sum(bench_r) / n
        cov = sum((strat_r[i] - mean_s) * (bench_r[i] - mean_b) for i in range(n)) / (n - 1)
        var_b = sum((r - mean_b) ** 2 for r in bench_r) / (n - 1)

        if var_b > 0:
            beta = cov / var_b
        else:
            beta = 0.0

        # Alpha = 年化超额收益 = 年化策略收益 - Beta * 年化基准收益
        bench_total_return = (bench_closes[-1] / bench_closes[0] - 1) if bench_closes[0] > 0 else 0.0
        # 年化基准收益
        if len(bench_closes) > 1:
            bench_years = len(bench_closes) / 252.0
            if bench_years > 0 and bench_closes[-1] > 0:
                bench_annual = ((bench_closes[-1] / bench_closes[0]) ** (1.0 / bench_years) - 1)
            else:
                bench_annual = 0.0
        else:
            bench_annual = 0.0

        strat_annual = result["metrics"]["annual_return"] / 100.0
        alpha = strat_annual - beta * bench_annual

        result["benchmark"] = {
            "benchmark_return": round(bench_total_return * 100, 2),
            "alpha": round(alpha, 4),
            "beta": round(beta, 4),
        }

        return result


# ======================================================================
# 预置策略函数 — 可被run_strategy直接使用
# ======================================================================

def sma_cross_strategy(klines, idx, position, cash):
    """SMA交叉策略 — 5日均线上穿20日均线买入，下穿卖出

    Args:
        klines: 全部K线数据(到当前idx)
        idx: 当前K线索引
        position: 当前持仓数量
        cash: 当前可用资金

    Returns:
        {"action": "buy"/"sell"/"hold", "quantity": int}
    """
    if idx < 20:
        return {"action": "hold"}
    closes = [float(k[2]) for k in klines[:idx + 1]]
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    prev_ma5 = sum(closes[-6:-1]) / 5
    prev_ma20 = sum(closes[-21:-1]) / 20

    if prev_ma5 <= prev_ma20 and ma5 > ma20 and position == 0:
        # 金叉买入
        price = closes[-1]
        qty = int(cash * 0.95 / price / 100) * 100
        if qty > 0:
            return {"action": "buy", "quantity": qty}
    elif prev_ma5 >= prev_ma20 and ma5 < ma20 and position > 0:
        # 死叉卖出
        return {"action": "sell", "quantity": position}
    return {"action": "hold"}


def combo_score_strategy(klines, idx, position, cash):
    """combo_scorer评分策略 — 评分≥56(A级)买入，<35(D级)卖出

    需要导入 combo_scorer 和 technical_indicators

    Args:
        klines: 全部K线数据(到当前idx)
        idx: 当前K线索引
        position: 当前持仓数量
        cash: 当前可用资金

    Returns:
        {"action": "buy"/"sell"/"hold", "quantity": int}
    """
    from combo_scorer import ComboScorer
    from technical_indicators import calc_all

    if idx < 60:
        return {"action": "hold"}

    window = klines[:idx + 1]
    tech = calc_all(window)
    scorer = ComboScorer()
    scores = scorer.score_full(window, tech["latest"])

    rating = scores.get("rating", "C")

    if rating == "A" and position == 0:
        price = float(klines[idx][2])
        qty = int(cash * 0.95 / price / 100) * 100
        if qty > 0:
            return {"action": "buy", "quantity": qty}
    elif rating == "D" and position > 0:
        return {"action": "sell", "quantity": position}
    return {"action": "hold"}


def mean_reversion_strategy_func(klines, idx, position, cash):
    """均值回归策略适配器 — RSI<30+BOLL下轨买入, RSI>70+BOLL上轨卖出"""
    from mean_reversion_strategy import MeanReversionStrategy

    if idx < 20:
        return {"action": "hold"}

    strat = MeanReversionStrategy()
    signal = strat.generate_signal(klines[:idx + 1], idx, position)
    action = signal.get("action", "hold")
    if action == "buy" and position == 0:
        price = float(klines[idx][2])
        qty = int(cash * 0.95 / price / 100) * 100
        if qty > 0:
            return {"action": "buy", "quantity": qty}
    elif action == "sell" and position > 0:
        return {"action": "sell", "quantity": position}
    return {"action": "hold"}


def grid_trading_strategy_func(klines, idx, position, cash):
    """网格交易策略适配器 — ATR锚定布林带区间分档买卖

    网格策略的特性是有多档买卖，但在 backtest_engine 的单仓模型中
    简化为: 价格低于BOLL下轨→买入, 高于中轨+持仓盈利→卖出
    """
    from technical_indicators import boll, atr

    if idx < 20:
        return {"action": "hold"}

    closes = [float(k[2]) for k in klines[:idx + 1]]
    boll_data = boll(closes, 20, 2.0)
    atr_vals = atr(klines[:idx + 1], 14)

    boll_lower = boll_data["lower"][-1] if boll_data["lower"] else 0
    boll_mid = boll_data["mid"][-1] if boll_data["mid"] else 0
    boll_upper = boll_data["upper"][-1] if boll_data["upper"] else 0
    atr_val = atr_vals[-1] if atr_vals else 0
    current_close = closes[-1]

    if boll_lower <= 0 or atr_val <= 0:
        return {"action": "hold"}

    # 买入: 价格触及BOLL下轨
    if current_close <= boll_lower * 1.01 and position == 0:
        price = current_close
        qty = int(cash * 0.90 / price / 100) * 100  # 保守90%仓位
        if qty > 0:
            return {"action": "buy", "quantity": qty}

    # 卖出: 价格回升到BOLL中轨以上
    if current_close >= boll_mid and position > 0:
        return {"action": "sell", "quantity": position}

    # 止损: 跌破BOLL下轨 - 1 ATR
    stop_loss = boll_lower - atr_val
    if current_close <= stop_loss and position > 0:
        return {"action": "sell", "quantity": position}

    return {"action": "hold"}


def volatility_breakout_strategy_func(klines, idx, position, cash):
    """波动率突破策略适配器 — BOLL收缩+放量突破买入, RSI超买卖出"""
    from volatility_breakout_strategy import VolatilityBreakoutStrategy

    if idx < 60:
        return {"action": "hold"}

    strat = VolatilityBreakoutStrategy()
    signal = strat.generate_signal(klines[:idx + 1], idx, position)
    action = signal.get("action", "hold")
    if action == "buy" and position == 0:
        price = float(klines[idx][2])
        qty = int(cash * 0.95 / price / 100) * 100
        if qty > 0:
            return {"action": "buy", "quantity": qty}
    elif action == "sell" and position > 0:
        return {"action": "sell", "quantity": position}
    return {"action": "hold"}


def multi_factor_strategy_func(klines, idx, position, cash):
    """多因子策略适配器 — 综合评分≥80(A级)买入, <50(D级)卖出"""
    from multi_factor_scorer import MultiFactorScorer
    from technical_indicators import calc_all

    if idx < 60:
        return {"action": "hold"}

    window = klines[:idx + 1]
    tech = calc_all(window)
    scorer = MultiFactorScorer()
    result = scorer.score_multi_factor(window, tech["latest"])

    rating = result.get("rating", "C")

    if rating == "A" and position == 0:
        price = float(klines[idx][2])
        qty = int(cash * 0.95 / price / 100) * 100
        if qty > 0:
            return {"action": "buy", "quantity": qty}
    elif rating == "D" and position > 0:
        return {"action": "sell", "quantity": position}
    return {"action": "hold"}


# 策略注册表
PRESET_STRATEGIES = {
    "sma_cross": sma_cross_strategy,
    "combo_score": combo_score_strategy,
    "mean_reversion": mean_reversion_strategy_func,
    "grid": grid_trading_strategy_func,
    "volatility": volatility_breakout_strategy_func,
    "multi_factor": multi_factor_strategy_func,
}


# ======================================================================
# CLI入口
# ======================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="A股回测评估引擎")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--strategy", choices=list(PRESET_STRATEGIES.keys()), default="sma_cross")
    parser.add_argument("--count", type=int, default=250)
    parser.add_argument("--cash", type=float, default=1000000)
    parser.add_argument("--split", action="store_true", help="样本内外分割过拟合检测")
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    from data_bridge import DataBridge

    klines = DataBridge.tencent_kline(args.code, args.count)
    if not klines:
        print(json.dumps({"error": "无法获取K线数据"}))
        exit(1)

    engine = BacktestEngine(initial_cash=args.cash)
    strategy = PRESET_STRATEGIES[args.strategy]

    if args.split:
        in_sample, out_sample = engine.split_sample(klines)
        in_result = engine.run_strategy(in_sample, strategy)
        out_result = engine.run_strategy(out_sample, strategy)
        # 输出两个样本的对比
        output = {
            "code": args.code,
            "in_sample": in_result["metrics"],
            "out_sample": out_result["metrics"],
            "overfitting_check": {
                "in_sample_sharpe": in_result["metrics"]["sharpe_ratio"],
                "out_sample_sharpe": out_result["metrics"]["sharpe_ratio"],
                "overfitting_suspected": (
                    in_result["metrics"]["sharpe_ratio"] > 3 and
                    in_result["metrics"]["max_drawdown"] < 5 and
                    in_result["metrics"]["win_rate"] > 75
                ),
                "warning": (
                    "疑似过拟合: 样本内夏普>3+最大回撤<5%+胜率>75%"
                    if (in_result["metrics"]["sharpe_ratio"] > 3 and
                        in_result["metrics"]["max_drawdown"] < 5 and
                        in_result["metrics"]["win_rate"] > 75)
                    else "未见明显过拟合迹象"
                ),
            },
        }
    else:
        result = engine.run_strategy(klines, strategy)
        output = {
            "code": args.code,
            "strategy": args.strategy,
            "metrics": result["metrics"],
            "trades_count": len(result["trades"]),
            "equity_curve_length": len(result["equity_curve"]),
            "sample_trades": result["trades"][:5],  # 前5笔交易示例
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))
