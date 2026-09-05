# -*- coding: utf-8 -*-
"""
Paper trading and backtesting engines for a_stock_agents.
"""

from core.paper_trading.a_stocks_backtest import BacktestEngine as SingleBacktestEngine
from core.paper_trading.multi_backtest_engine import MultiBacktestEngine, BacktestEngine

__all__ = [
    "SingleBacktestEngine",
    "MultiBacktestEngine",
    "BacktestEngine",
]

