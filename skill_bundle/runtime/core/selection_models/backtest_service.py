# -*- coding: utf-8 -*-
"""信号标记分析与事件驱动交易策略回测（E2 / SSOT §12.2 / §13.7）。

两类回测**必须分别展示、口径严格分离**（§12.2 / §22.1）：

1. **信号标记分析（Markout）**：不假设真实交易，只观察入选后 T+1/T+3/T+5/T+10/T+20
   交易日的收盘价收益路径、MFE/MAE 与区间回撤；
2. **交易策略回测**：应用 `PositionPolicy` 的建仓/仓位/止盈止损/持有规则，逐日事件驱动
   模拟可成交的资金曲线与交易记录。

交易策略回测满足（发布门禁 15）：
- A股 T+1、100 股整手、涨跌停不可成交、停牌（缺 bar）跳过；
- 交易成本参数化（佣金及最低收费、印花税、过户费、滑点），复用 `market_config`；
- 输出 CAGR / 最大回撤 / Sharpe / Calmar / 胜率 / 盈亏比 / 换手率 / 平均持有期 / MFE / MAE；
- **未来数据检测**：给定 `as_of` 时，任何晚于 `as_of` 的 bar 即拒绝回测。

本模块只做纯计算，不读库、不写盘、不下单。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.selection_models.market_view import (
    Bar,
    annualized_volatility_pct,
    detect_future_data,
    limit_prices,
    max_drawdown_pct,
    market_config,
    mfe_mae_pct,
    nth_trading_date,
)

DEFAULT_HORIZONS = (1, 3, 5, 10, 20)
TRADING_DAYS_PER_YEAR = 250


class BacktestServiceError(ValueError):
    def __init__(self, message: str, code: str = "MODEL_CONFIG_INVALID") -> None:
        super().__init__(message)
        self.code = code


def _index_on_or_before(bars: Sequence[Bar], day: str) -> Optional[int]:
    target = str(day)[:10]
    found: Optional[int] = None
    for idx, bar in enumerate(bars):
        if bar.date <= target:
            found = idx
        else:
            break
    return found


def _bar_on(bars: Sequence[Bar], day: str) -> Optional[Bar]:
    target = str(day)[:10]
    for bar in bars:
        if bar.date == target:
            return bar
    return None


# ------------------------------------------------------------------ 信号标记分析
def markout_analysis(
    bars: Sequence[Bar],
    *,
    signal_date: str,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    as_of: Optional[str] = None,
) -> Dict[str, Any]:
    """入选后 T+N 的纯观察口径（不假设交易）。"""
    future = detect_future_data(bars, as_of) if as_of else []
    if future:
        raise BacktestServiceError(
            f"未来数据检测失败：行情包含晚于 as_of({as_of}) 的 bar {future[:3]}", "MODEL_DATA_UNSUPPORTED"
        )
    base_idx = _index_on_or_before(bars, signal_date)
    if base_idx is None:
        raise BacktestServiceError(f"行情不含信号日 {signal_date} 或其之前的 bar", "MODEL_DATA_MISSING")
    base_bar = bars[base_idx]
    base_price = base_bar.close

    points: List[Dict[str, Any]] = []
    available_closes: List[float] = []
    for horizon in horizons:
        target_date = nth_trading_date(base_bar.date, int(horizon))
        entry: Dict[str, Any] = {"horizon": int(horizon), "target_trade_date": target_date, "available": False}
        if target_date is not None:
            target_bar = _bar_on(bars, target_date)
            if target_bar is not None:
                entry.update(
                    {
                        "available": True,
                        "close": target_bar.close,
                        "close_return_pct": round((target_bar.close / base_price - 1.0) * 100.0, 4),
                    }
                )
                open_return = (
                    round((target_bar.open / base_price - 1.0) * 100.0, 4)
                    if target_bar.open
                    else None
                )
                entry["open_return_pct"] = open_return
                available_closes.append(target_bar.close)
        points.append(entry)

    window = bars[base_idx:]
    profile = mfe_mae_pct(window, base_price=base_price)
    available = [bar.close for bar in window]
    return {
        "caliber": "close",
        "signal_date": base_bar.date,
        "base_price": round(base_price, 4),
        "horizons": points,
        "mfe_pct": profile["mfe_pct"],
        "mae_pct": profile["mae_pct"],
        "mfe_mae_caliber": profile["caliber"],
        "window_max_drawdown_pct": max_drawdown_pct(available),
        "window_volatility_pct": annualized_volatility_pct(available),
        "max_holding_window_trade_days": len(window) - 1,
        "future_data": future,
    }


# ------------------------------------------------------------------ 交易策略回测
def _fee_profile(cfg: Mapping[str, Any]) -> Dict[str, float]:
    return {
        "commission_rate": float(cfg.get("commission_rate", 0.00025)),
        "min_commission": float(cfg.get("min_commission", 5.0)),
        "stamp_tax": float(cfg.get("tax_rate_sell", 0.0005)),
        "transfer_rate": float(cfg.get("transfer_fee_rate", 0.00001)),
    }


def _buy_cost(gross: float, fees: Mapping[str, float]) -> float:
    commission = max(gross * fees["commission_rate"], fees["min_commission"])
    return gross + commission + gross * fees["transfer_rate"]


def _sell_net(gross: float, fees: Mapping[str, float]) -> float:
    commission = max(gross * fees["commission_rate"], fees["min_commission"])
    return gross - commission - gross * fees["stamp_tax"] - gross * fees["transfer_rate"]


def event_backtest(
    bars: Sequence[Bar],
    policy: Mapping[str, Any],
    *,
    code: str,
    signal_date: str,
    initial_cash: float = 1_000_000.0,
    slippage_rate: Optional[float] = None,
    as_of: Optional[str] = None,
    cfg: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """单标的、逐日事件驱动的 `PositionPolicy` 回测（发布门禁 15）。"""
    future = detect_future_data(bars, as_of) if as_of else []
    if future:
        raise BacktestServiceError(
            f"未来数据检测失败：行情包含晚于 as_of({as_of}) 的 bar {future[:3]}", "MODEL_DATA_UNSUPPORTED"
        )
    if not bars:
        raise BacktestServiceError("回测行情为空", "MODEL_DATA_MISSING")

    position = dict(policy.get("position") or {})
    risk = dict(policy.get("risk") or {})
    exit_cfg = dict(policy.get("exit") or {})
    entry_cfg = dict(policy.get("entry") or {})
    entry_price_planned = entry_cfg.get("planned_entry_price")
    weight = position.get("initial_weight")
    if not weight or float(weight) <= 0:
        raise BacktestServiceError(
            "建仓策略缺少可用仓位（缺账户规模/成交价），不生成伪精确回测",
            "MODEL_DATA_MISSING",
        )

    entry_date = nth_trading_date(signal_date, 1)
    entry_bar = _bar_on(bars, entry_date) if entry_date else None
    checked = bool(as_of)
    if entry_bar is None:
        return _empty_backtest(code, signal_date, entry_date, reason="ENTRY_DATE_NO_DATA", future=future, checked=checked)

    prev_idx = _index_on_or_before(bars, signal_date)
    prev_close = bars[prev_idx].close if prev_idx is not None else entry_bar.close
    limit_up, limit_down = limit_prices(code, prev_close)

    fee_cfg = market_config() if cfg is None else dict(cfg)
    fees = _fee_profile(fee_cfg)
    slip = float(slippage_rate if slippage_rate is not None else 0.001)

    entry_open = entry_bar.open if entry_bar.open else entry_bar.close
    if entry_open >= limit_up - 1e-9:
        return _empty_backtest(code, signal_date, entry_date, reason="ENTRY_LIMIT_UP_UNFILLABLE", future=future, checked=checked)
    fill_price = entry_open * (1.0 + slip)
    equity_before = float(initial_cash)
    target_value = equity_before * float(weight) / 100.0
    shares = int(math.floor(target_value / fill_price / 100.0) * 100)
    if shares <= 0:
        return _empty_backtest(code, signal_date, entry_date, reason="ENTRY_SIZE_BELOW_ONE_LOT", future=future, checked=checked)

    cash = equity_before - _buy_cost(fill_price * shares, fees)
    remaining = shares
    trades: List[Dict[str, Any]] = [
        {"date": entry_bar.date, "action": "BUY", "price": round(fill_price, 4), "shares": shares}
    ]

    stop_price = risk.get("initial_stop_price")
    atr = risk.get("atr")
    max_holding = int(risk.get("max_holding_trade_days") or 10)
    steps = [float(s) for s in (exit_cfg.get("take_profit_steps") or [])]
    sold_steps: set = set()
    entry_idx = bars.index(entry_bar)
    equity_curve: List[Dict[str, Any]] = []
    daily_returns: List[float] = []
    exit_reason = "MAX_HOLDING"
    holding_days = 0

    for offset, bar in enumerate(bars[entry_idx:]):
        holding_days = offset
        # 逐日盯市净值
        equity = cash + remaining * bar.close
        prev_equity = equity_curve[-1]["equity"] if equity_curve else equity_before
        daily_returns.append((equity - prev_equity) / prev_equity if prev_equity else 0.0)
        equity_curve.append({"date": bar.date, "equity": round(equity, 2), "shares": remaining})

        if offset == 0:
            continue  # T+1：建仓当日不可卖
        low = bar.low if bar.low is not None else bar.close
        high = bar.high if bar.high is not None else bar.close
        tradable_down = low > limit_down + 1e-9

        # ① 止损（初始 -5%/-2ATR 或 ATR 移动止损）
        trailing = None
        if atr:
            trailing = bar.close - 2.0 * float(atr)
        threshold = max([p for p in (stop_price, trailing) if p is not None], default=None)
        if threshold is not None and low <= float(threshold):
            if not tradable_down:
                continue  # 跌停不可成交，顺延
            sell_price = min(float(threshold), bar.close) * (1.0 - slip)
            cash += _sell_net(sell_price * remaining, fees)
            trades.append({"date": bar.date, "action": "SELL", "price": round(sell_price, 4),
                           "shares": remaining, "reason": "STOP_LOSS"})
            remaining = 0
            exit_reason = "STOP_LOSS"
            break

        # ② 分批止盈（按步长各减原仓位的等份）
        for index, step in enumerate(steps):
            if index in sold_steps:
                continue
            trigger = (entry_price_planned or fill_price) * (1.0 + step)
            if high >= trigger and remaining > 0:
                lot = max(100, int(shares / len(steps) / 100) * 100)
                lot = min(lot, remaining)
                if lot <= 0:
                    continue
                sell_price = trigger * (1.0 - slip)
                cash += _sell_net(sell_price * lot, fees)
                trades.append({"date": bar.date, "action": "SELL", "price": round(sell_price, 4),
                               "shares": lot, "reason": f"TAKE_PROFIT_{int(step * 100)}"})
                remaining -= lot
                sold_steps.add(index)

        if remaining <= 0:
            exit_reason = "TAKE_PROFIT"
            break
        if holding_days >= max_holding:
            if bar.close <= limit_down + 1e-9:
                continue  # 跌停顺延
            sell_price = bar.close * (1.0 - slip)
            cash += _sell_net(sell_price * remaining, fees)
            trades.append({"date": bar.date, "action": "SELL", "price": round(sell_price, 4),
                           "shares": remaining, "reason": "MAX_HOLDING"})
            remaining = 0
            exit_reason = "MAX_HOLDING"
            break

    if remaining > 0 and bars:
        last = bars[-1]
        sell_price = last.close * (1.0 - slip)
        cash += _sell_net(sell_price * remaining, fees)
        trades.append({"date": last.date, "action": "SELL", "price": round(sell_price, 4),
                       "shares": remaining, "reason": "PERIOD_END"})
        remaining = 0
        exit_reason = exit_reason if exit_reason != "MAX_HOLDING" else "PERIOD_END"
        final_equity = cash
        equity_curve[-1] = {"date": last.date, "equity": round(final_equity, 2), "shares": 0}

    metrics = _performance_metrics(equity_curve, daily_returns, trades, initial_cash)
    window = bars[entry_idx:]
    profile = mfe_mae_pct(window, base_price=fill_price)
    held_days = [
        offset for offset, bar in enumerate(window) if bar.date <= (trades[-1]["date"] if trades else bars[-1].date)
    ]
    metrics.update(
        {
            "mfe_pct": profile["mfe_pct"],
            "mae_pct": profile["mae_pct"],
            "mfe_mae_caliber": profile["caliber"],
            "average_holding_trade_days": round((len(held_days) - 1) if len(held_days) > 1 else 0, 2),
        }
    )
    return {
        "code": str(code),
        "signal_date": str(signal_date)[:10],
        "entry_date": entry_bar.date,
        "exit_date": trades[-1]["date"] if trades else None,
        "exit_reason": exit_reason,
        "fill_price": round(fill_price, 4),
        "shares": shares,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "trade_history": trades,
        "fee_profile": {
            "commission_rate": fees["commission_rate"],
            "min_commission": fees["min_commission"],
            "stamp_tax": fees["stamp_tax"],
            "transfer_rate": fees["transfer_rate"],
            "slippage_rate": slip,
        },
        "future_data": future,
        "future_data_checked": bool(as_of),
    }


def _empty_backtest(
    code: str, signal_date: str, entry_date: Optional[str], *, reason: str, future: List[str], checked: bool
) -> Dict[str, Any]:
    return {
        "code": str(code),
        "signal_date": str(signal_date)[:10],
        "entry_date": entry_date,
        "tradable": False,
        "reason_code": reason,
        "metrics": {},
        "equity_curve": [],
        "trade_history": [],
        "future_data": future,
        "future_data_checked": checked,
    }


def _performance_metrics(
    equity_curve: Sequence[Mapping[str, Any]],
    daily_returns: Sequence[float],
    trades: Sequence[Mapping[str, Any]],
    initial_cash: float,
) -> Dict[str, Any]:
    if not equity_curve:
        return {}
    equities = [float(item["equity"]) for item in equity_curve]
    final_equity = equities[-1]
    total_return = (final_equity - initial_cash) / initial_cash * 100.0
    years = len(equities) / TRADING_DAYS_PER_YEAR
    cagr = (
        (math.pow(final_equity / initial_cash, 1.0 / years) - 1.0) * 100.0
        if final_equity > 0 and initial_cash > 0 and years > 0
        else 0.0
    )
    max_dd = max_drawdown_pct(equities)
    sharpe = 0.0
    if len(daily_returns) >= 2:
        rf_daily = 0.02 / TRADING_DAYS_PER_YEAR
        excess = [r - rf_daily for r in daily_returns]
        mean = sum(excess) / len(excess)
        var = sum((r - mean) ** 2 for r in excess) / (len(excess) - 1)
        std = math.sqrt(var)
        sharpe = (mean / std * math.sqrt(TRADING_DAYS_PER_YEAR)) if std > 0 else 0.0
    calmar = (cagr / max_dd) if max_dd > 0 else 0.0

    sells = [t for t in trades if t.get("action") == "SELL"]
    pnls: List[float] = []
    for sell in sells:
        buys = [t for t in trades if t.get("action") == "BUY"]
        buy_price = buys[0]["price"] if buys else sell["price"]
        pnls.append((float(sell["price"]) - float(buy_price)) * int(sell["shares"]))
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / len(pnls) * 100.0) if pnls else 0.0
    total_gain = sum(wins)
    total_loss = abs(sum(losses))
    pl_ratio = (total_gain / total_loss) if total_loss > 0 else (99.0 if total_gain > 0 else 1.0)

    turnover = 0.0
    if equities:
        traded_value = sum(float(t["price"]) * int(t["shares"]) for t in trades)
        turnover = round(traded_value / initial_cash, 4)

    return {
        "initial_cash": round(initial_cash, 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "annualized_cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(calmar, 2),
        "win_rate_pct": round(win_rate, 2),
        "profit_loss_ratio": round(pl_ratio, 2),
        "turnover_ratio": turnover,
        "trade_count": len(pnls),
    }


__all__ = [
    "DEFAULT_HORIZONS",
    "BacktestServiceError",
    "event_backtest",
    "markout_analysis",
]