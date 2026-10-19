# -*- coding: utf-8 -*-
"""
Paper Trading & Multi-Asset Backtest Regression Test Suite:
Validates:
- MultiBacktestEngine (limit-up/limit-down trading price calculation, board limits 10%/20%/30%)
- AccountPortfolio (T+1 available_shares restriction, buy/sell lifecycle)
- Simulated multi-asset backtest run with synthetic data
- PaperTradingEngine account creation and SQLite isolation
- backtest_metrics (Calmar negative return protection, 100% win rate profit factor, zero-division safety)
- Forwarder SSOT verification for backtest_engine.py
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.paper_trading.multi_backtest_engine import MultiBacktestEngine, AccountPortfolio
from core.paper_trading.backtest_metrics import calc_metrics, _safe_div
from core.paper_trading.engine import PaperTradingEngine
import core.paper_trading as pt


class TestPaperTradingSuite(unittest.TestCase):

    def test_backtest_forwarder_and_exports(self):
        """Verify backtest_engine.py forwarder and core.paper_trading exports."""
        forwarder = ROOT / "skill_bundle" / "skills" / "astock-quant-engine" / "scripts" / "backtest_engine.py"
        if not forwarder.exists():
            forwarder = ROOT / "skills" / "astock-quant-engine" / "scripts" / "backtest_engine.py"
        self.assertTrue(forwarder.exists(), "backtest_engine.py forwarder must exist")
        text = forwarder.read_text(encoding="utf-8")
        self.assertIn("Single Source of Truth (SSOT)", text)
        self.assertIn("core.paper_trading.multi_backtest_engine", text)

        self.assertTrue(hasattr(pt, "MultiBacktestEngine"))
        self.assertTrue(hasattr(pt, "BacktestEngine"))
        self.assertTrue(hasattr(pt, "SingleBacktestEngine"))

    def test_limit_prices_by_board(self):
        """Verify board-based limit up/down prices (Main 10%, ChiNext/STAR 20%, BSE 30%)."""
        prev_close = 10.0

        # Main board (600xxx, 000xxx): 10%
        up_main, down_main = MultiBacktestEngine._limit_prices("600519", prev_close)
        self.assertEqual(up_main, 11.0)
        self.assertEqual(down_main, 9.0)

        # ChiNext (300xxx) & STAR (688xxx): 20%
        up_star, down_star = MultiBacktestEngine._limit_prices("688001", prev_close)
        self.assertEqual(up_star, 12.0)
        self.assertEqual(down_star, 8.0)

        up_chinext, down_chinext = MultiBacktestEngine._limit_prices("300750", prev_close)
        self.assertEqual(up_chinext, 12.0)
        self.assertEqual(down_chinext, 8.0)

        # BSE (83xxxx, 92xxxx): 30%
        up_bse, down_bse = MultiBacktestEngine._limit_prices("830001", prev_close)
        self.assertEqual(up_bse, 13.0)
        self.assertEqual(down_bse, 7.0)

        up_bse92, down_bse92 = MultiBacktestEngine._limit_prices("920001", prev_close)
        self.assertEqual(up_bse92, 13.0)
        self.assertEqual(down_bse92, 7.0)

    def test_account_portfolio_t_plus_1(self):
        """Verify T+1 trading rules: shares bought today cannot be sold until next day."""
        acc = AccountPortfolio(initial_cash=100000.0)

        # Day 1: Buy 1000 shares of 600519
        success = acc.buy("600519", shares=1000, price=10.0, date="2026-09-01", atr=0.3)
        self.assertTrue(success)
        self.assertIn("600519", acc.positions)
        self.assertEqual(acc.positions["600519"]["shares"], 1000)
        self.assertEqual(acc.positions["600519"]["available_shares"], 0)  # T+0 cannot sell!

        # Try selling on Day 1 (should fail)
        sold = acc.sell("600519", shares=1000, price=10.5, date="2026-09-01")
        self.assertFalse(sold)
        self.assertEqual(acc.positions["600519"]["shares"], 1000)

        # Day 2: Next trading day, roll positions
        acc.end_of_day_settlement()
        self.assertEqual(acc.positions["600519"]["available_shares"], 1000)  # T+1 unlocked!

        # Now can sell on Day 2
        sold_day2 = acc.sell("600519", shares=1000, price=10.5, date="2026-09-02")
        self.assertTrue(sold_day2)
        self.assertNotIn("600519", acc.positions)

    def test_simulated_multi_backtest_run(self):
        """Run simulated multi-symbol backtest with synthetic data."""
        dates = pd.date_range("2026-01-01", periods=40, freq="B").strftime("%Y-%m-%d").tolist()
        np.random.seed(42)

        def make_kline(base_price):
            prices = [base_price]
            for _ in range(39):
                change = np.random.normal(0.002, 0.015)
                prices.append(prices[-1] * (1 + change))
            df = pd.DataFrame({
                "date": dates,
                "open": [p * 0.995 for p in prices],
                "high": [p * 1.01 for p in prices],
                "low": [p * 0.99 for p in prices],
                "close": prices,
                "volume": [1000000 + int(np.random.rand() * 500000) for _ in prices],
                "amount": [p * 1000000 for p in prices],
            })
            return df

        price_data = {
            "sh600519": make_kline(1500.0),
            "sz000858": make_kline(130.0),
        }

        def mock_strategy(date_str, hist_dict, current_pos):
            signals = []
            for code in ["sh600519", "sz000858"]:
                df = hist_dict.get(code)
                if df is None or len(df) < 5:
                    continue
                row = df.iloc[-1]
                if row["close"] > row["open"] and code not in current_pos:
                    signals.append({"code": code, "action": "buy", "target_pct": 0.4})
                elif row["close"] < row["open"] and code in current_pos:
                    signals.append({"code": code, "action": "sell", "target_pct": 0.0})
            return signals

        engine = MultiBacktestEngine(
            initial_cash=1000000.0,
            commission_rate=0.0003,
            slippage_rate=0.001,
            max_positions=3,
        )

        res = engine.run(price_data=price_data, strategy_func=mock_strategy)

        self.assertIn("initial_cash", res)
        self.assertIn("final_equity", res)
        self.assertIn("total_return_pct", res)
        self.assertIn("annualized_cagr_pct", res)
        self.assertIn("sharpe_ratio", res)
        self.assertIn("max_drawdown_pct", res)
        self.assertIn("win_rate_pct", res)
        self.assertIn("trade_count", res)
        self.assertIn("daily_records", res)
        self.assertEqual(res["initial_cash"], 1000000.0)

    def test_backtest_metrics_calculation_and_edge_cases(self):
        """Verify calc_metrics handles negative Calmar, 100% win rate, and empty datasets."""
        # 1. Negative return -> negative Calmar
        equity_curve = [
            {"date": "2026-01-01", "equity": 100000.0},
            {"date": "2026-01-02", "equity": 90000.0},
            {"date": "2026-01-03", "equity": 80000.0},
        ]
        trades = [
            {"action": "buy", "date": "2026-01-01", "price": 100, "qty": 1000, "amount": 100000},
            {"action": "sell", "date": "2026-01-03", "price": 80, "qty": 1000, "amount": 80000, "profit": -20000},
        ]
        metrics = calc_metrics(
            equity_curve=equity_curve,
            trades=trades,
            initial_cash=100000.0,
            final_equity=80000.0,
            days=3,
        )
        self.assertLess(metrics["annual_return_pct"], 0)
        self.assertLess(metrics["calmar_ratio"], 0)
        self.assertEqual(metrics["profit_factor"], 0.0)

        # 2. 100% win rate (no losses)
        winning_trades = [
            {"action": "buy", "date": "2026-01-01", "price": 100, "qty": 1000, "amount": 100000},
            {"action": "sell", "date": "2026-01-03", "price": 120, "qty": 1000, "amount": 120000, "profit": 20000},
        ]
        winning_curve = [
            {"date": "2026-01-01", "equity": 100000.0},
            {"date": "2026-01-03", "equity": 120000.0},
        ]
        win_metrics = calc_metrics(
            equity_curve=winning_curve,
            trades=winning_trades,
            initial_cash=100000.0,
            final_equity=120000.0,
            days=2,
        )
        self.assertEqual(win_metrics["profit_factor"], 999.0)

        # 3. Empty dataset / 0 days boundary
        empty_metrics = calc_metrics(
            equity_curve=[],
            trades=[],
            initial_cash=0.0,
            final_equity=0.0,
            days=0,
        )
        self.assertEqual(empty_metrics["turnover_ratio"], 0.0)
        self.assertEqual(empty_metrics["calmar_ratio"], 0.0)
        self.assertEqual(empty_metrics["profit_factor"], 0.0)

    def test_paper_trading_engine_sqlite_lifecycle(self):
        """Verify PaperTradingEngine initializes SQLite cleanly without errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_pt.db")
            engine = PaperTradingEngine(db_path=db_path)
            acc = engine.create_account("test_user_qa", initial_cash=200000.0)
            self.assertIsNotNone(acc)
            self.assertEqual(acc["account_id"], "test_user_qa")
            self.assertEqual(acc["cash"], 200000.0)

    def test_paper_trading_service_imports(self):
        """Verify all paper_trading modules import cleanly."""
        import core.paper_trading.paper_trade_cli as pt_cli
        import core.paper_trading.paper_trading_ctl as pt_ctl
        import core.paper_trading.paper_trading_service as pt_svc
        import core.paper_trading.service as svc
        import core.paper_trading.engine as eng
        self.assertIsNotNone(pt_cli.request_json)
        self.assertIsNotNone(pt_ctl.SERVICE_SCRIPT)
        self.assertIsNotNone(eng.PaperTradingEngine)

    def test_rolling_oos_validator_and_triple_alerts(self):
        """Verify RollingOOSValidator calculations and triple overfitting alerts."""
        from core.paper_trading.rolling_oos import RollingOOSValidator

        # 1. Splitting test
        dummy_klines = [[f"2026-01-{i:02d}", 10, 10, 11, 9, 1000] for i in range(1, 101)]
        is_k, oos_k = RollingOOSValidator.split_samples(dummy_klines, oos_ratio=0.3)
        self.assertEqual(len(is_k), 70)
        self.assertEqual(len(oos_k), 30)

        # 2. Triple alert test: case A (extreme Sharpe > 3.5)
        res_a = RollingOOSValidator.evaluate_overfitting(
            in_sample_metrics={"sharpe_ratio": 3.8, "win_rate": 60.0, "annual_return": 20.0, "max_drawdown": 8.0},
            out_sample_metrics={"sharpe_ratio": 2.5, "win_rate": 55.0, "annual_return": 18.0, "max_drawdown": 10.0},
        )
        self.assertTrue(res_a["overfitting_suspected"])
        self.assertTrue(res_a["triple_alerts"]["sharpe_gt_3_5"])
        self.assertFalse(res_a["triple_alerts"]["win_rate_gt_75"])
        self.assertFalse(res_a["triple_alerts"]["decay_gt_50"])

        # 3. Triple alert test: case B (extreme WinRate > 75%)
        res_b = RollingOOSValidator.evaluate_overfitting(
            in_sample_metrics={"sharpe_ratio": 2.0, "win_rate": 82.0, "annual_return": 25.0, "max_drawdown": 5.0},
            out_sample_metrics={"sharpe_ratio": 1.8, "win_rate": 60.0, "annual_return": 20.0, "max_drawdown": 8.0},
        )
        self.assertTrue(res_b["overfitting_suspected"])
        self.assertFalse(res_b["triple_alerts"]["sharpe_gt_3_5"])
        self.assertTrue(res_b["triple_alerts"]["win_rate_gt_75"])
        self.assertFalse(res_b["triple_alerts"]["decay_gt_50"])

        # 4. Triple alert test: case C (IS-to-OOS decay > 50%)
        res_c = RollingOOSValidator.evaluate_overfitting(
            in_sample_metrics={"sharpe_ratio": 2.5, "win_rate": 65.0, "annual_return": 40.0, "max_drawdown": 10.0},
            out_sample_metrics={"sharpe_ratio": 0.8, "win_rate": 45.0, "annual_return": 12.0, "max_drawdown": 18.0},
        )
        self.assertTrue(res_c["overfitting_suspected"])
        self.assertFalse(res_c["triple_alerts"]["sharpe_gt_3_5"])
        self.assertFalse(res_c["triple_alerts"]["win_rate_gt_75"])
        self.assertTrue(res_c["triple_alerts"]["decay_gt_50"])
        self.assertGreater(res_c["return_decay_pct"], 50.0)

        # 5. Non-overfitting case
        res_d = RollingOOSValidator.evaluate_overfitting(
            in_sample_metrics={"sharpe_ratio": 1.8, "win_rate": 58.0, "annual_return": 18.0, "max_drawdown": 12.0},
            out_sample_metrics={"sharpe_ratio": 1.5, "win_rate": 54.0, "annual_return": 15.0, "max_drawdown": 14.0},
        )
        self.assertFalse(res_d["overfitting_suspected"])
        self.assertFalse(res_d["triple_alerts"]["sharpe_gt_3_5"])
        self.assertFalse(res_d["triple_alerts"]["win_rate_gt_75"])
        self.assertFalse(res_d["triple_alerts"]["decay_gt_50"])
        self.assertIn("通过过拟合三重检验", res_d["summary"])

    def test_backtest_engine_run_oos_validation(self):
        """Verify BacktestEngine.run_oos_validation integration."""
        from core.paper_trading.a_stocks_backtest import BacktestEngine, sma_cross_strategy

        # Synthetic trending price bars
        prices = [10.0 + i * 0.1 for i in range(100)]
        klines = [
            [f"2026-01-{i:02d}", p, p + 0.05, p + 0.1, p - 0.1, 10000]
            for i, p in enumerate(prices)
        ]
        engine = BacktestEngine(initial_cash=100000.0)
        res = engine.run_oos_validation(klines, sma_cross_strategy, oos_ratio=0.3)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["in_sample_bars"], 70)
        self.assertEqual(res["out_sample_bars"], 30)
        self.assertIn("in_sample", res)
        self.assertIn("out_sample", res)
        self.assertIn("decay", res)
        self.assertIn("overfitting_check", res)
        self.assertIn("triple_alerts", res)


if __name__ == "__main__":
    unittest.main()

