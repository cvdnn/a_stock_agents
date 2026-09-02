#!/usr/bin/env python3
"""Backtest performance metrics — zero external dependency.

Computes the full suite of industry-standard risk/return metrics from an
equity curve and trade log.  Uses only Python stdlib (math + statistics).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# A-share approximate trading days per year
TRADING_DAYS_PER_YEAR = 250
RISK_FREE_RATE = 0.02  # 2% annual, configurable


def _safe_div(numer: float, denom: float, default: float = 0.0) -> float:
    if abs(denom) < 1e-12:
        return default
    return numer / denom


def _annualize(total_return_pct: float, days: int) -> float:
    """Convert total return to annualized return."""
    if days <= 0:
        return 0.0
    ratio = 1.0 + total_return_pct / 100.0
    if ratio <= 0:
        return -100.0
    return (ratio ** (TRADING_DAYS_PER_YEAR / days) - 1.0) * 100.0


def _daily_returns(equity_curve: List[Dict]) -> List[float]:
    """Extract daily return series from equity curve."""
    rets: List[float] = []
    for i in range(1, len(equity_curve)):
        prev_eq = equity_curve[i - 1]["equity"]
        curr_eq = equity_curve[i]["equity"]
        if prev_eq > 1e-9:
            rets.append((curr_eq - prev_eq) / prev_eq)
    return rets


def _mean(data: List[float]) -> float:
    return sum(data) / len(data) if data else 0.0


def _stdev(data: List[float], ddof: int = 1) -> float:
    if len(data) < 2:
        return 0.0
    avg = _mean(data)
    var = sum((x - avg) ** 2 for x in data) / (len(data) - ddof) if len(data) > ddof else 0.0
    return math.sqrt(var)


def _max_drawdown_detail(equity_curve: List[Dict]) -> Tuple[float, int, int]:
    """Return (max_drawdown_pct, peak_date, trough_date)."""
    if not equity_curve:
        return (0.0, 0, 0)
    peak = 0.0
    max_dd = 0.0
    peak_idx = 0
    trough_idx = 0
    best_peak_idx = 0

    for i, item in enumerate(equity_curve):
        eq = item["equity"]
        if eq > peak:
            peak = eq
            best_peak_idx = i
        if peak > 0:
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
                trough_idx = i
                peak_idx = best_peak_idx
    return (max_dd * 100.0, peak_idx, trough_idx)


def _max_drawdown_duration(equity_curve: List[Dict]) -> int:
    """Max consecutive days below peak (underwater duration)."""
    if not equity_curve:
        return 0
    peak = 0.0
    underwater = 0
    max_underwater = 0
    for item in equity_curve:
        eq = item["equity"]
        if eq >= peak:
            peak = eq
            underwater = 0
        else:
            underwater += 1
            max_underwater = max(max_underwater, underwater)
    return max_underwater


def _max_consecutive_losses(sell_profits: List[float]) -> int:
    max_seq = 0
    current = 0
    for p in sell_profits:
        if p <= 0:
            current += 1
            max_seq = max(max_seq, current)
        else:
            current = 0
    return max_seq


def calc_metrics(
    equity_curve: List[Dict],
    trades: List[Dict],
    initial_cash: float,
    final_equity: float,
    days: int = 0,
    buy_hold_return_pct: Optional[float] = None,
    risk_free_rate: float = RISK_FREE_RATE,
) -> Dict[str, Any]:
    """Compute full metrics suite from backtest results.

    Args:
        equity_curve: List of {"date": str, "equity": float}, full series.
        trades:       List of trade dicts with "action"/"price"/"qty"/"profit".
        initial_cash: Starting capital.
        final_equity: Ending equity (cash + position value).
        days:         Number of calendar/trading days in the backtest period.
        buy_hold_return_pct: Return of buy-and-hold same asset (optional).
        risk_free_rate:      Annualized risk-free rate (default 2%).
    """
    total_return_pct = ((final_equity - initial_cash) / initial_cash) * 100.0 if initial_cash > 0 else 0.0
    annual_return = _annualize(total_return_pct, days) if days > 0 else 0.0

    # Daily returns
    d_rets = _daily_returns(equity_curve)

    # Excess daily returns over risk-free daily
    rf_daily = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess_rets = [r - rf_daily for r in d_rets]

    # Volatility (annualized)
    vol = _stdev(d_rets) * math.sqrt(TRADING_DAYS_PER_YEAR) if d_rets else 0.0

    # Downside deviation (only negative returns)
    downside = [r for r in d_rets if r < 0]
    downside_dev = _stdev(downside) * math.sqrt(TRADING_DAYS_PER_YEAR) if downside else 0.0

    # Sharpe ratio
    mean_excess = _mean(excess_rets)
    sharpe = _safe_div(mean_excess * TRADING_DAYS_PER_YEAR, vol) if vol > 1e-9 else 0.0

    # Sortino ratio
    sortino = _safe_div(mean_excess * TRADING_DAYS_PER_YEAR, downside_dev) if downside_dev > 1e-9 else 0.0

    # Max drawdown
    max_dd_pct, peak_idx, trough_idx = _max_drawdown_detail(equity_curve)
    calmar = _safe_div(abs(annual_return), abs(max_dd_pct)) if max_dd_pct > 1e-9 else 0.0

    # Drawdown duration
    dd_duration = _max_drawdown_duration(equity_curve)

    # Trade statistics
    sell_profits: List[float] = [t.get("profit", 0.0) for t in trades if t.get("action") == "sell"]
    wins = [p for p in sell_profits if p > 0]
    losses = [p for p in sell_profits if p <= 0]
    win_rate = _safe_div(len(wins), len(sell_profits)) * 100.0 if sell_profits else 0.0
    avg_win = _mean(wins) if wins else 0.0
    avg_loss = abs(_mean(losses)) if losses else 0.0
    profit_factor = _safe_div(avg_win * len(wins), avg_loss * len(losses)) if losses and avg_loss > 0 else 0.0
    max_consec_loss = _max_consecutive_losses(sell_profits)

    # Turnover (total trade volume / initial / years)
    years = _safe_div(days, TRADING_DAYS_PER_YEAR) if days > 0 else 1.0
    total_trade_amount = sum(t.get("amount", 0.0) for t in trades)
    turnover = _safe_div(total_trade_amount, initial_cash) / years if years > 0 else 0.0

    # Average holding days (between buy and sell)
    buy_dates: List[str] = []
    holding_days_list: List[int] = []
    for t in trades:
        if t.get("action") == "buy":
            buy_dates.append(t.get("date", ""))
        elif t.get("action") == "sell" and buy_dates:
            buy_date = buy_dates.pop(0)
            # Find indices in equity curve for date difference
            try:
                eq_dates = [item["date"] for item in equity_curve]
                if buy_date in eq_dates and t.get("date") in eq_dates:
                    bi = eq_dates.index(buy_date)
                    si = eq_dates.index(t["date"])
                    holding_days_list.append(si - bi)
            except (ValueError, IndexError):
                pass
    avg_hold_days = _mean(holding_days_list) if holding_days_list else 0.0

    # Excess return (alpha vs buy_hold)
    excess_vs_buyhold = None
    if buy_hold_return_pct is not None:
        excess_vs_buyhold = round(total_return_pct - buy_hold_return_pct, 2)

    return {
        # Return
        "total_return_pct": round(total_return_pct, 2),
        "annual_return_pct": round(annual_return, 2),
        "excess_vs_buyhold_pct": excess_vs_buyhold,
        # Risk
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_duration_days": dd_duration,
        "annual_volatility_pct": round(vol * 100, 2),
        "downside_volatility_pct": round(downside_dev * 100, 2),
        # Risk-adjusted
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "calmar_ratio": round(calmar, 3),
        # Trade stats
        "total_trades": len(trades),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "max_consecutive_losses": max_consec_loss,
        "avg_holding_days": round(avg_hold_days, 1),
        "turnover_ratio": round(turnover, 2),
        # Components
        "trading_days": days,
        "risk_free_rate": risk_free_rate,
    }