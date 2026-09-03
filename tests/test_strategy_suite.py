# -*- coding: utf-8 -*-
"""
Strategy Test Suite for core/strategy/ modules:
- TrappedPositionAnalyzer (diagnostics, Kelly criterion, decision trees, ladders)
- RiskManager (three-tier stop losses, sell signals, drawdown control)
- PortfolioRiskManager (volatility targeting, correlation matrix)
- FundamentalFilter (financial screening thresholds)
- GridTradingStrategy & MeanReversionStrategy
"""

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.strategy.trapped_position import TrappedPositionAnalyzer
from core.strategy.risk_manager import RiskManager
from core.strategy.portfolio_risk_manager import PortfolioRiskManager
from core.strategy.fundamental_filter import FundamentalFilter
from core.strategy.grid_trading_strategy import GridTradingStrategy
from core.strategy.mean_reversion_strategy import MeanReversionStrategy


def _gen_mock_klines(count=60, base_price=10.0):
    klines = []
    price = base_price
    for i in range(count):
        d = f"2026-01-{i+1:02d}" if i < 30 else f"2026-02-{i-29:02d}"
        op = price
        cl = price + (0.1 if i % 2 == 0 else -0.08)
        hi = max(op, cl) + 0.05
        lo = min(op, cl) - 0.05
        vol = 10000 + i * 100
        klines.append([d, op, cl, hi, lo, vol])
        price = cl
    return klines


class TestStrategySuite(unittest.TestCase):

    def setUp(self):
        self.klines = _gen_mock_klines(60, 10.0)

    def test_trapped_position_analyzer_diagnostic(self):
        analyzer = TrappedPositionAnalyzer(cost_price=12.0, shares=1000, klines=self.klines)
        diag = analyzer.diagnostic()
        self.assertEqual(diag["cost_price"], 12.0)
        self.assertEqual(diag["shares"], 1000)
        self.assertIn("loss_pct", diag)
        self.assertIn("atr_14", diag)
        self.assertIn("kelly_f", diag)
        self.assertIn("kelly_interpretation", diag)

    def test_trapped_position_decision_tree(self):
        # Test large loss (>25%)
        analyzer_deep = TrappedPositionAnalyzer(cost_price=20.0, shares=1000, klines=self.klines)
        dt_deep = analyzer_deep.decision_tree()
        self.assertEqual(dt_deep["recommended"], "策略A_强制")

        # Test small loss (<5%)
        analyzer_small = TrappedPositionAnalyzer(cost_price=10.2, shares=1000, klines=self.klines)
        dt_small = analyzer_small.decision_tree()
        self.assertEqual(dt_small["recommended"], "策略E_持有等待")

    def test_trapped_position_full_analysis(self):
        analyzer = TrappedPositionAnalyzer(cost_price=12.0, shares=1000, klines=self.klines)
        res = analyzer.analyze()
        self.assertIn("diagnostic", res)
        self.assertIn("decision_tree", res)
        self.assertIn("strategy_a_ladder", res)
        self.assertIn("strategy_b_grid", res)
        self.assertIn("strategy_c_replenish", res)
        self.assertIn("strategy_d_swap", res)

    def test_risk_manager_stop_losses(self):
        latest = {"ma10": 9.5, "ma20": 9.0, "atr": 0.3}
        stops = RiskManager.calc_stop_losses(entry_price=10.0, latest=latest)
        self.assertIn("t0_intraday", stops)
        self.assertIn("t1_ma10", stops)
        self.assertIn("t2_ma20", stops)
        self.assertEqual(stops["t0_intraday"]["price"], 9.5)
        self.assertEqual(stops["t1_ma10"]["price"], 9.31)
        self.assertEqual(stops["t2_ma20"]["price"], 8.82)

    def test_risk_manager_sell_signals_and_drawdown(self):
        latest = {"close": 10.5, "ma10": 10.2, "ma20": 10.0, "dif": 0.2, "dea": 0.1, "macd_bar": 0.2}
        res = RiskManager.sell_signals(self.klines, latest)
        self.assertIn("signals", res)
        self.assertIn("should_sell", res)

        dd = RiskManager.drawdown_control(current_value=90000, peak_value=100000, cost=85000)
        self.assertIn("drawdown_from_peak_pct", dd)
        self.assertEqual(dd["drawdown_from_peak_pct"], -10.0)

    def test_portfolio_risk_manager(self):
        prm = PortfolioRiskManager(target_volatility=0.15, max_single_stock=0.15)
        vol = prm.calc_annualized_volatility(self.klines)
        self.assertIsInstance(vol, float)
        self.assertGreater(vol, 0.0)

        target_pos = prm.volatility_target_position(self.klines, base_position=0.10)
        self.assertIn("adjusted_position", target_pos)
        self.assertIn("actual_vol", target_pos)

    def test_fundamental_filter_inspect(self):
        ff = FundamentalFilter()
        good_quote = {"price": 25.0, "pe": 20.0}
        good_finance = {"net_profit": 50000000, "profit_yoy": 15.0, "revenue_yoy": 12.0}
        res = ff.inspect("600000", self.klines, quote=good_quote, finance=good_finance)
        self.assertIn("passed", res)
        self.assertTrue(res["passed"])

    def test_grid_trading_strategy(self):
        strategy = GridTradingStrategy()
        grid = strategy.build_grid(self.klines, total_cash=100000)
        self.assertIn("grid_count", grid)
        self.assertIn("grid_levels", grid)
        self.assertIn("stop_loss_price", grid)
        self.assertGreaterEqual(grid["grid_count"], 4)

    def test_mean_reversion_strategy(self):
        strategy = MeanReversionStrategy()
        sig = strategy.generate_signal(self.klines, idx=len(self.klines)-1, position=0)
        self.assertIn("action", sig)
        self.assertIn("reason", sig)


if __name__ == "__main__":
    unittest.main()
