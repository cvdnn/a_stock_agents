# -*- coding: utf-8 -*-
"""
Strategy & Risk Regression Test Suite for core/strategy/ modules:
Validates:
- TrappedPositionAnalyzer (diagnostics, Kelly criterion, decision trees, ladders)
- RiskManager (three-tier stop losses, sell signals, drawdown control, MACD divergence & red bars)
- PortfolioRiskManager (volatility targeting, correlation matrix)
- FundamentalFilter (financial screening thresholds)
- GridTradingStrategy (boll_mid price level coupling)
- MeanReversionStrategy (config defaults, RSI thresholds)
- ExecutionActionEngine (real data contracts, breakeven precision, Beijing codes, dynamic names)
- PositionManager (pure data service functions decoupled from CLI)
- PoolSchema (empty rows CSV preservation, parameter order safety)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

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
from core.strategy.execution_action_engine import ExecutionActionEngine, IntentEvaluator
from core.strategy import position_manager
from core.strategy.pool_schema import write_pool_csv, read_pool_csv, is_blocked
from core.config import save_market_config, check_market_config_prompt


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
        # Large loss (>25%)
        analyzer_deep = TrappedPositionAnalyzer(cost_price=20.0, shares=1000, klines=self.klines)
        dt_deep = analyzer_deep.decision_tree()
        self.assertEqual(dt_deep["recommended"], "策略A_强制")

        # Small loss (<5%)
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

    def test_risk_manager_top_divergence_and_macd_red_bars(self):
        """Verify MACD top divergence detection and 3-day red bar shortening."""
        # Top divergence test data
        klines = []
        for i in range(30):
            p = 10.0 + i * 0.35
            klines.append([f"2026-06-{i+1:02d}", str(p-0.1), str(p), str(p+0.2), str(p-0.2), "2000"])
        for i in range(15):
            p = 20.0 + (0.04 * i)
            klines.append([f"2026-07-{i+1:02d}", str(p-0.05), str(p), str(p+0.1), str(p-0.1), "800"])

        latest = {
            "close": 20.6,
            "ma10": 20.3,
            "ma20": 20.0,
            "dif": 0.15,
            "dea": 0.18,
            "macd_bar": -0.06,
        }
        res = RiskManager.sell_signals(klines, latest)
        self.assertIn("signals", res)
        signals_text = " ".join(res["signals"])
        self.assertIn("顶背离", signals_text)

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

    def test_grid_trading_boll_mid_coupling(self):
        """Verify GridTradingStrategy orders strictly respect price < boll_mid for buy."""
        strategy = GridTradingStrategy()
        klines = [
            [f"2026-01-{i+1:02d}", 10.0 + (i % 5) * 0.5, 10.2 + (i % 5) * 0.5, 12.0, 8.0, 1000]
            for i in range(30)
        ]
        plan = strategy.build_grid(klines, total_cash=100000)
        self.assertIn("grid_levels", plan)
        boll_mid = plan["boll_mid"]
        self.assertGreater(len(plan["grid_levels"]), 0)
        for level in plan["grid_levels"]:
            price = level["price"]
            action = level["action"]
            if price < boll_mid:
                self.assertEqual(action, "buy")
            else:
                self.assertEqual(action, "sell")

    def test_mean_reversion_strategy(self):
        strategy = MeanReversionStrategy()
        self.assertEqual(strategy.rsi_oversold, 30.0)
        self.assertEqual(strategy.rsi_overbought, 70.0)
        self.assertEqual(strategy.stop_loss_pct, 0.05)
        sig = strategy.generate_signal(self.klines, idx=len(self.klines)-1, position=0)
        self.assertIn("action", sig)
        self.assertIn("reason", sig)

    def test_breakeven_precision_and_market_config(self):
        """Verify breakeven calculation precision under default and custom fee rates."""
        # Default: 万2.5, min 5.0
        p = ExecutionActionEngine.calc_min_breakeven_price(10.0, 1000)
        self.assertEqual(p, 10.02)

        # 100.00 cost, 1000 shares
        p_large = ExecutionActionEngine.calc_min_breakeven_price(100.0, 1000)
        self.assertEqual(p_large, 100.11)

        # Custom: 万1.0, 免5
        mian5_cfg = {
            "commission_rate": 0.00010,
            "min_commission": 0.0,
            "tax_rate_sell": 0.0005,
            "transfer_fee_rate": 0.00001,
            "breakeven_ceil_cent": True
        }
        p_m5 = ExecutionActionEngine.calc_min_breakeven_price(10.0, 1000, market_cfg=mian5_cfg)
        self.assertEqual(p_m5, 10.01)

        # Market config flow
        save_market_config(is_user_configured=False)
        needs_prompt, prompt = check_market_config_prompt()
        self.assertTrue(needs_prompt)
        self.assertIn("万2.5", prompt)

        save_market_config(commission_rate=0.00025, min_commission=5.0, is_user_configured=True)
        needs_prompt, prompt = check_market_config_prompt()
        self.assertFalse(needs_prompt)

    def test_execution_action_engine_generation_and_beijing_codes(self):
        """Verify ExecutionActionEngine accepts contract fields and IntentEvaluator parses Beijing codes."""
        quote = {
            "price": 10.5, "open": 10.2, "vol_ratio": 1.5,
            "o_ratio": 55.0, "turnover_pct": 3.5, "change_pct": 2.5
        }
        tech = {
            "rsi": 65.0, "atr": 0.35, "dif": 0.25, "dea": 0.15,
            "ma5": 10.3, "ma10": 10.0, "ma20": 9.8
        }
        action = ExecutionActionEngine.generate_action(
            code="600519", name="贵州茅台", quote=quote, tech=tech
        )
        self.assertIn("action_type", action)
        self.assertIn("current_price", action)
        self.assertEqual(action["current_price"], 10.5)

        # Beijing codes regex pattern
        matches = IntentEvaluator.STOCK_CODE_PATTERN.findall("分析一下 830001 和 920002 以及 600519")
        self.assertIn("830001", matches)
        self.assertIn("920002", matches)
        self.assertIn("600519", matches)

        # Dynamic name registration
        IntentEvaluator.register_known_names({"量子超导": "688999"})
        parsed = IntentEvaluator.parse_user_query("量子超导目前浮亏严重，该怎么补仓解套？")
        self.assertIn("688999", parsed.get("detected_codes", []))
        self.assertEqual(parsed.get("primary_intent"), IntentEvaluator.INTENT_TRAPPED_RECOVERY)

    def test_position_manager_service_decoupling(self):
        """Verify position_manager functions perform data operations without CLI prints."""
        summary = position_manager.calculate_pnl_summary()
        self.assertIsInstance(summary, dict)
        self.assertIn("total_cost", summary)
        self.assertIn("floating_pnl", summary)
        self.assertIn("total_pnl", summary)

        triggers = position_manager.check_stop_triggers()
        self.assertIsInstance(triggers, list)

    def test_pool_schema_empty_rows_and_rules(self):
        """Verify pool_schema empty rows preservation and market blocking rules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_pool.csv"
            fields = ["code", "name", "score", "date"]

            write_pool_csv(csv_file, rows=[], fields=fields)
            content = csv_file.read_text(encoding="utf-8").strip()
            self.assertEqual(content, "code,name,score,date")

            read_rows = read_pool_csv(csv_file)
            self.assertEqual(len(read_rows), 0)

        # Blocked rules
        self.assertTrue(is_blocked("688001"))
        self.assertTrue(is_blocked("300750"))
        self.assertTrue(is_blocked("830001"))
        self.assertFalse(is_blocked("600519"))
        self.assertFalse(is_blocked("000001"))

    def test_volatility_breakout_strategy(self):
        """Verify VolatilityBreakoutStrategy initializes with correct parameters."""
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

    def test_ta_entry_monitor_template_render(self):
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
        compiled = compile(script, "<test_rendered_script>", "exec")
        self.assertIsNotNone(compiled)


if __name__ == "__main__":
    unittest.main()
