#!/usr/bin/env python3
"""Pluggable backtest strategy interface.

Each strategy receives the full bar DataFrame + current index and returns
a signal: "buy" | "sell" | "hold".  The engine calls on_bar() each iteration.

To add a custom strategy:
  1. Subclass BacktestStrategy
  2. Implement on_bar(self, i, row, bars, position) -> str
  3. Register in STRATEGY_REGISTRY (or pass the object directly)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ═══════════════════════════════════════════════════════════════
#  Base class
# ═══════════════════════════════════════════════════════════════

class BacktestStrategy:
    """Base class for all backtest strategies."""

    name: str = "base"

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self.params = params or {}

    def prepare(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Pre-compute indicators on the full bars DataFrame.

        Override to add columns (e.g. MA, RSI, BOLL) before the bar loop.
        Default: return bars unchanged.
        """
        return bars

    def on_bar(self, i: int, row: pd.Series, bars: pd.DataFrame, position: int) -> str:
        """Return signal for this bar.

        Args:
            i: Current bar index (0-based, matches DataFrame index after reset).
            row: Current bar as a Series (open/high/low/close/volume/...).
            bars: Full DataFrame (with all indicator columns from prepare()).
            position: Current holding quantity (0 = flat, >0 = long).

        Returns:
            "buy" | "sell" | "hold"
        """
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════
#  Built-in strategies (ported from engine.py run_backtest)
# ═══════════════════════════════════════════════════════════════

class BuyHoldStrategy(BacktestStrategy):
    name = "buy_and_hold"

    def on_bar(self, i: int, row: pd.Series, bars: pd.DataFrame, position: int) -> str:
        if i == 0 and position == 0:
            return "buy"
        return "hold"


class SmaCrossStrategy(BacktestStrategy):
    name = "sma_cross"

    def prepare(self, bars: pd.DataFrame) -> pd.DataFrame:
        fast = int(self.params.get("fast", 5))
        slow = int(self.params.get("slow", 20))
        bars = bars.copy()
        bars["ma_fast"] = bars["close"].rolling(fast).mean()
        bars["ma_slow"] = bars["close"].rolling(slow).mean()
        return bars

    def on_bar(self, i: int, row: pd.Series, bars: pd.DataFrame, position: int) -> str:
        if i == 0:
            return "hold"
        if pd.isna(row["ma_fast"]) or pd.isna(row["ma_slow"]):
            return "hold"
        prev = bars.iloc[i - 1]
        if prev["ma_fast"] <= prev["ma_slow"] and row["ma_fast"] > row["ma_slow"]:
            return "buy"
        if prev["ma_fast"] >= prev["ma_slow"] and row["ma_fast"] < row["ma_slow"]:
            return "sell"
        return "hold"


class RsiRevertStrategy(BacktestStrategy):
    name = "rsi_revert"

    def prepare(self, bars: pd.DataFrame) -> pd.DataFrame:
        bars = bars.copy()
        delta = bars["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        bars["rsi"] = 100 - (100 / (1 + rs))
        return bars

    def on_bar(self, i: int, row: pd.Series, bars: pd.DataFrame, position: int) -> str:
        if pd.isna(row.get("rsi")):
            return "hold"
        buy_rsi = float(self.params.get("buy_rsi", 30))
        sell_rsi = float(self.params.get("sell_rsi", 70))
        if row["rsi"] < buy_rsi and position == 0:
            return "buy"
        if row["rsi"] > sell_rsi and position > 0:
            return "sell"
        return "hold"


class BollReversionStrategy(BacktestStrategy):
    """Bollinger Band mean-reversion: buy below lower band, sell at/above mid."""

    name = "boll_reversion"

    def prepare(self, bars: pd.DataFrame) -> pd.DataFrame:
        bars = bars.copy()
        period = int(self.params.get("boll_period", 20))
        num_std = float(self.params.get("boll_std", 2.0))
        bars["boll_mid"] = bars["close"].rolling(period).mean()
        bars["boll_std"] = bars["close"].rolling(period).std()
        bars["boll_upper"] = bars["boll_mid"] + num_std * bars["boll_std"]
        bars["boll_lower"] = bars["boll_mid"] - num_std * bars["boll_std"]
        # Also compute RSI for confirmation
        delta = bars["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        bars["rsi"] = 100 - (100 / (1 + rs))
        # Volume ratio (current vs 5-day average)
        bars["vol_avg5"] = bars["volume"].rolling(5).mean()
        bars["vol_ratio"] = bars["volume"] / bars["vol_avg5"].replace(0, pd.NA)
        return bars

    def on_bar(self, i: int, row: pd.Series, bars: pd.DataFrame, position: int) -> str:
        if pd.isna(row.get("boll_lower")) or pd.isna(row.get("rsi")):
            return "hold"
        rsi_thresh = float(self.params.get("buy_rsi", 30))
        sell_rsi = float(self.params.get("sell_rsi", 70))
        vol_thresh = float(self.params.get("vol_ratio_max", 0.8))

        # Buy: close < lower band + RSI oversold + shrinking volume + flat
        if (row["close"] < row["boll_lower"]
                and row["rsi"] < rsi_thresh
                and row.get("vol_ratio", 1.0) < vol_thresh
                and position == 0):
            return "buy"

        # Sell: close >= mid band (partial exit signal) or RSI overbought
        if position > 0:
            if row["close"] >= row["boll_mid"] or row["rsi"] > sell_rsi:
                return "sell"
        return "hold"


# ═══════════════════════════════════════════════════════════════
#  Registry
# ═══════════════════════════════════════════════════════════════

STRATEGY_REGISTRY: Dict[str, type] = {
    "buy_and_hold": BuyHoldStrategy,
    "sma_cross": SmaCrossStrategy,
    "rsi_revert": RsiRevertStrategy,
    "boll_reversion": BollReversionStrategy,
}


def get_strategy(strategy: str, params: Optional[Dict[str, Any]] = None) -> BacktestStrategy:
    """Look up a strategy by name and instantiate it with params."""
    cls = STRATEGY_REGISTRY.get(strategy)
    if cls is None:
        raise ValueError(f"unsupported strategy: {strategy!r}. "
                         f"Available: {list(STRATEGY_REGISTRY.keys())}")
    return cls(params)