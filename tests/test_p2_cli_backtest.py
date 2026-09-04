# -*- coding: utf-8 -*-
"""
Test suite verifying P2 phase remediation:
- Core CLI unification: Full subcommands merged into core/cli.py with 100% core.* imports
- a_stocks.py thin SSOT forwarder delegating to core.cli
- Multi-asset event-driven backtest engine relocated to core/paper_trading/multi_backtest_engine.py
- backtest_engine.py thin SSOT forwarder delegating to core.paper_trading.multi_backtest_engine
- DataLayer relocated to core/data/data_layer.py and data_layer.py forwarder
- End-to-end integration and dispatching tests
"""

import unittest
import sys
import subprocess
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))


class TestP2DataLayer(unittest.TestCase):
    """Test DataLayer normalization, cleaning, and forwarder."""

    def test_datalayer_forwarder_ssot(self):
        """Verify data_layer.py in skills/ is a valid SSOT forwarder."""
        forwarder = ROOT / "skills" / "astock-quant-engine" / "scripts" / "data_layer.py"
        self.assertTrue(forwarder.exists(), "data_layer.py forwarder must exist")
        text = forwarder.read_text(encoding="utf-8")
        self.assertIn("Single Source of Truth (SSOT)", text)
        self.assertIn("core.data.data_layer", text)

    def test_normalize_symbol(self):
        """Test symbol code normalization."""
        from core.data.data_layer import normalize_symbol
        self.assertEqual(normalize_symbol("600519"), "sh600519")
        self.assertEqual(normalize_symbol("000001"), "sz000001")
        self.assertEqual(normalize_symbol("300750"), "sz300750")
        self.assertEqual(normalize_symbol("688981"), "sh688981")
        self.assertEqual(normalize_symbol("830001"), "bj830001")
        self.assertEqual(normalize_symbol("sh600519"), "sh600519")
        self.assertEqual(normalize_symbol("SZ000001"), "sz000001")
        self.assertEqual(normalize_symbol("600519.SH"), "sh600519")
        self.assertEqual(normalize_symbol("000001.SZ"), "sz000001")

    def test_clean_kline_df(self):
        """Test kline cleaning and standard column renaming."""
        from core.data.data_layer import clean_kline_df

        # Empty df
        empty_res = clean_kline_df(pd.DataFrame())
        self.assertTrue(empty_res.empty)

        # Raw dataframe with mixed names
        dates = pd.date_range("2026-01-01", periods=5, freq="D")
        raw = pd.DataFrame({
            "日期": dates.strftime("%Y-%m-%d"),
            "开盘": [10.0, 10.5, 10.2, 10.8, 11.0],
            "最高": [10.6, 10.7, 10.9, 11.2, 11.5],
            "最低": [9.9, 10.1, 10.0, 10.5, 10.8],
            "收盘": [10.5, 10.2, 10.8, 11.0, 11.2],
            "成交量": [10000, 12000, 15000, 11000, 13000],
            "成交额": [100000, 125000, 160000, 120000, 140000],
        })

        cleaned = clean_kline_df(raw)
        self.assertFalse(cleaned.empty)
        for col in ["date", "open", "high", "low", "close", "volume", "amount"]:
            self.assertIn(col, cleaned.columns)
        self.assertEqual(len(cleaned), 5)


class TestP2MultiBacktestEngine(unittest.TestCase):
    """Test MultiBacktestEngine core logic and backtest_engine.py forwarder."""

    def test_backtest_forwarder_ssot(self):
        """Verify backtest_engine.py in skills/ is a valid SSOT forwarder."""
        forwarder = ROOT / "skills" / "astock-quant-engine" / "scripts" / "backtest_engine.py"
        self.assertTrue(forwarder.exists(), "backtest_engine.py forwarder must exist")
        text = forwarder.read_text(encoding="utf-8")
        self.assertIn("Single Source of Truth (SSOT)", text)
        self.assertIn("core.paper_trading.multi_backtest_engine", text)

    def test_engine_export_in_paper_trading(self):
        """Verify core.paper_trading exports MultiBacktestEngine and BacktestEngine."""
        import core.paper_trading as pt
        self.assertTrue(hasattr(pt, "MultiBacktestEngine"))
        self.assertTrue(hasattr(pt, "BacktestEngine"))
        self.assertTrue(hasattr(pt, "SingleBacktestEngine"))

    def test_simulated_multi_backtest(self):
        """Run simulated multi-symbol backtest with synthetic data."""
        from core.paper_trading.multi_backtest_engine import MultiBacktestEngine

        # Generate 40 days of synthetic price data for 2 stocks
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

        # Strategy function generating deterministic signals
        def mock_strategy(date_str, hist_dict, current_pos):
            signals = []
            for code in ["sh600519", "sz000858"]:
                df = hist_dict.get(code)
                if df is None or len(df) < 5:
                    continue
                # Simple momentum: if close > open buy, else sell
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

        # Check required metrics
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
        self.assertGreater(len(res["daily_records"]), 0)


class TestP2CoreCLI(unittest.TestCase):
    """Test core/cli.py unification and a_stocks.py forwarder."""

    def test_a_stocks_forwarder_ssot(self):
        """Verify a_stocks.py in skills/ is a valid SSOT forwarder."""
        forwarder = ROOT / "skills" / "astock-platform-evaluate" / "scripts" / "a_stocks.py"
        self.assertTrue(forwarder.exists(), "a_stocks.py forwarder must exist")
        text = forwarder.read_text(encoding="utf-8")
        self.assertIn("Single Source of Truth (SSOT)", text)
        self.assertIn("core.cli", text)

    def test_cli_parser_all_subcommands_registered(self):
        """Verify build_parser registers both core and a_stocks commands."""
        from core.cli import build_parser
        parser = build_parser()
        subparser_action = None
        for action in parser._actions:
            if action.dest == "command":
                subparser_action = action
                break
        self.assertIsNotNone(subparser_action, "Must have 'command' subparser action")

        expected_commands = [
            "quote", "technical", "score", "analyze", "trapped", "market",
            "batch", "deploy-monitor", "screen", "risk", "golden-cross",
            "events", "cyq", "balance", "evaluate", "backtest", "multi-backtest",
            "multi-factor", "portfolio-risk", "mean-reversion", "grid",
            "vol-breakout", "action", "intent", "downside", "report",
            "config", "pool", "position", "data", "skill", "version"
        ]

        registered_commands = subparser_action.choices.keys()
        for cmd in expected_commands:
            self.assertIn(cmd, registered_commands, f"Subcommand '{cmd}' must be registered in core.cli")

    def test_cli_parse_args_dispatch(self):
        """Verify CLI argument parsing succeeds for various command syntaxes."""
        from core.cli import build_parser
        parser = build_parser()

        # quote
        args = parser.parse_args(["quote", "600519"])
        self.assertEqual(args.command, "quote")
        self.assertEqual(args.code, "600519")

        # trapped
        args = parser.parse_args(["trapped", "600760", "--cost", "50", "--shares", "1000"])
        self.assertEqual(args.command, "trapped")
        self.assertEqual(args.code, "600760")
        self.assertEqual(args.cost, 50.0)
        self.assertEqual(args.shares, 1000)

        # multi-backtest
        args = parser.parse_args(["multi-backtest", "--days", "100", "--top", "5"])
        self.assertEqual(args.command, "multi-backtest")
        self.assertEqual(args.days, 100)
        self.assertEqual(args.top, 5)

        # evaluate (compat mode with a_stocks flags)
        args = parser.parse_args(["evaluate", "--auto", "--days", "60"])
        self.assertEqual(args.command, "evaluate")
        self.assertTrue(args.auto)
        self.assertEqual(args.count, 60)


    def test_cli_version_via_subprocess(self):
        """Run core/cli.py version via subprocess."""
        cmd = [sys.executable, str(ROOT / "core" / "cli.py"), "version"]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, f"core/cli.py version failed:\n{res.stderr}")
        self.assertIn("A-Stock Agents", res.stdout)

    def test_a_stocks_forwarder_via_subprocess(self):
        """Run a_stocks.py forwarder --help via subprocess."""
        cmd = [
            sys.executable,
            str(ROOT / "skills" / "astock-platform-evaluate" / "scripts" / "a_stocks.py"),
            "--help"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, f"a_stocks.py forwarder failed:\n{res.stderr}")
        self.assertIn("A-Stock Agents", res.stdout)
        self.assertIn("multi-backtest", res.stdout)



if __name__ == "__main__":
    unittest.main()
