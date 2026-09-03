# -*- coding: utf-8 -*-
"""
Test suite verifying the P0 bug fixes across core modules:
- Multi-agent ta_analyze & ta_entry_monitor
- Strategy lab & daily decisions
- Volatility breakout strategy
- Stock screener funnel
- Data bridge & lazy third-party dependencies (akshare/efinance)
- Paper trading relative/absolute import consistency
"""

import unittest
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))


class TestP0Fixes(unittest.TestCase):

    def test_ta_entry_monitor_render(self):
        """Verify ta_entry_monitor renders valid Python code from template."""
        from core.multi_agent.ta_entry_monitor import render_monitor_script
        script = render_monitor_script(
            ticker="600519",
            entry_price=1250.0,
            stop_price=1200.0,
            account="test_acc",
            mode="stop"
        )
        self.assertIn('"code": "600519"', script)
        self.assertIn('"entry_price": 1250.0', script)
        self.assertIn('"stop_price": 1200.0', script)
        self.assertIn('"account": "test_acc"', script)
        self.assertIn('MODE = os.environ.get("MONITOR_MODE", "stop")', script)
        
        # Test that the rendered string is valid Python bytecode
        compiled = compile(script, "<test_rendered_script>", "exec")
        self.assertIsNotNone(compiled)

    def test_ta_analyze_identifier_syntax(self):
        """Verify ta_analyze has no syntax errors and exports key functions."""
        import core.multi_agent.ta_analyze as ta
        self.assertTrue(hasattr(ta, "AI_PLATFORM_SKILLS"))
        self.assertTrue(hasattr(ta, "_call_ai_platform"))

    def test_stock_screener_instantiation(self):
        """Verify StockScreener imports and initializes without data_bridge error."""
        from core.models.stock_screener import StockScreener
        screener = StockScreener()
        self.assertIsNotNone(screener.bridge)
        self.assertIsNotNone(screener.scorer)

    def test_volatility_breakout_strategy_instantiation(self):
        """Verify VolatilityBreakoutStrategy imports without technical_indicators error."""
        from core.strategy.volatility_breakout_strategy import VolatilityBreakoutStrategy
        strat = VolatilityBreakoutStrategy()
        self.assertEqual(strat.boll_period, 20)
        self.assertEqual(strat.boll_k, 2.0)

    def test_strategy_lab_trend_pullback_execution(self):
        """Verify strategy_lab strategies and parameters work properly."""
        from core.strategy.strategy_lab.strategies import trend_pullback
        from core.strategy.strategy_lab import strategy_params
        dates = pd.date_range("2026-01-01", periods=60)
        mock_df = pd.DataFrame({
            "time": dates,
            "open": np.linspace(10, 20, 60),
            "high": np.linspace(10.5, 20.5, 60),
            "low": np.linspace(9.5, 19.5, 60),
            "close": np.linspace(10, 20, 60),
            "volume": np.random.randint(100, 1000, 60)
        })
        res = trend_pullback(mock_df, strategy_params.TREND_PULLBACK_PARAMS)
        self.assertIn("entry", res.columns)
        self.assertIn("exit", res.columns)
        self.assertIn("score", res.columns)

    def test_data_fetchers_lazy_fallback(self):
        """Verify data fetchers handle absence of akshare/efinance gracefully."""
        from core.data import fetch_realtime, fetch_ah_ipo_timeline, fetch_ah_stocks, fetch_stock_events
        # Check that attributes exist and do not cause uncaught ImportError
        self.assertTrue(hasattr(fetch_realtime, "ak"))
        self.assertTrue(hasattr(fetch_realtime, "ef"))
        self.assertTrue(hasattr(fetch_ah_ipo_timeline, "ak"))
        self.assertTrue(hasattr(fetch_ah_stocks, "ak"))
        self.assertTrue(hasattr(fetch_stock_events, "ak"))

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


if __name__ == "__main__":
    unittest.main()
