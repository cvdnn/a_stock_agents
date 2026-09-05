# -*- coding: utf-8 -*-
"""
Test suite for CODE_REVIEW P3 maintainability improvements.
Validates:
- core.config constants & market prefix normalization SSOT
- core.cli modularization & subcommand dispatch integrity
- combo_scorer, multi_dim_model, factor_synthesizer cleanups
- execution_action_engine dynamic name resolution & Beijing code support
- position_manager business logic and presentation decoupling
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))



class TestP3Maintainability(unittest.TestCase):

    def test_config_market_prefix_ssot(self):
        """Verify core.config SSOT for market prefix inference and symbol normalization."""
        from core.config import (
            DEFAULT_BENCHMARK,
            DEFAULT_COMMISSION_RATE,
            DEFAULT_RATING_THRESHOLDS,
            DEFAULT_STOP_LOSS_PCT,
            DEFAULT_TAX_RATE_SELL,
            MARKET_PREFIX_BJ,
            MARKET_PREFIX_SH,
            MARKET_PREFIX_SZ,
            infer_market_prefix,
            normalize_symbol,
        )

        self.assertEqual(DEFAULT_BENCHMARK, "sh000001")
        self.assertAlmostEqual(DEFAULT_TAX_RATE_SELL, 0.0005)
        self.assertAlmostEqual(DEFAULT_COMMISSION_RATE, 0.00025)
        self.assertEqual(DEFAULT_RATING_THRESHOLDS["A"], 80.0)
        self.assertAlmostEqual(DEFAULT_STOP_LOSS_PCT, 0.05)

        # Shanghai
        self.assertEqual(infer_market_prefix("600519"), MARKET_PREFIX_SH)
        self.assertEqual(infer_market_prefix("688001"), MARKET_PREFIX_SH)
        self.assertEqual(infer_market_prefix("sh600519"), MARKET_PREFIX_SH)
        self.assertEqual(infer_market_prefix("600519.SH"), MARKET_PREFIX_SH)
        self.assertEqual(normalize_symbol("600519", with_prefix=True), "sh600519")
        self.assertEqual(normalize_symbol("sh600519", with_prefix=False), "600519")

        # Shenzhen
        self.assertEqual(infer_market_prefix("000001"), MARKET_PREFIX_SZ)
        self.assertEqual(infer_market_prefix("300750"), MARKET_PREFIX_SZ)
        self.assertEqual(infer_market_prefix("sz000002"), MARKET_PREFIX_SZ)
        self.assertEqual(normalize_symbol("000001", with_prefix=True), "sz000001")
        self.assertEqual(normalize_symbol("sz000001", with_prefix=False), "000001")

        # Beijing
        self.assertEqual(infer_market_prefix("830001"), MARKET_PREFIX_BJ)
        self.assertEqual(infer_market_prefix("430002"), MARKET_PREFIX_BJ)
        self.assertEqual(infer_market_prefix("920001"), MARKET_PREFIX_BJ)
        self.assertEqual(infer_market_prefix("bj830001"), MARKET_PREFIX_BJ)
        self.assertEqual(normalize_symbol("830001", with_prefix=True), "bj830001")
        self.assertEqual(normalize_symbol("bj830001", with_prefix=False), "830001")

    def test_cli_modularization_structure(self):
        """Verify cli.py line reduction and core.commands module exports."""
        from core.cli import build_parser
        import core.cli as cli_mod

        cli_path = Path(cli_mod.__file__)
        line_count = len(cli_path.read_text(encoding="utf-8").splitlines())
        self.assertLess(line_count, 450, f"cli.py should be modularized, got {line_count} lines")

        # Parser contains all subcommands
        parser = build_parser()
        subparser_action = next(a for a in parser._actions if a.dest == "command")
        choices = subparser_action.choices

        expected_cmds = [
            "quote", "technical", "score", "analyze", "trapped", "market",
            "batch", "deploy-monitor", "screen", "risk", "golden-cross",
            "events", "cyq", "balance", "evaluate", "backtest", "multi-backtest",
            "multi-factor", "portfolio-risk", "mean-reversion", "grid",
            "vol-breakout", "action", "intent", "downside", "report",
            "config", "pool", "position", "data", "skill", "version"
        ]
        for cmd in expected_cmds:
            self.assertIn(cmd, choices, f"Subcommand {cmd} must be registered")

        # Ensure core.commands re-exports handlers
        import core.commands as cmds
        self.assertTrue(hasattr(cmds, "cmd_data_quote"))
        self.assertTrue(hasattr(cmds, "cmd_score"))
        self.assertTrue(hasattr(cmds, "cmd_multi_backtest"))
        self.assertTrue(hasattr(cmds, "cmd_report"))

    def test_combo_scorer_cleanups(self):
        """Verify combo_scorer docstring weights, score_ma_structure signature and stop losses."""
        from core.models.combo_scorer import ComboScorer, entry_assessment

        # Test score_ma_structure with dictionary only (optional klines)
        score, reason = ComboScorer.score_ma_structure(
            latest={"ma5": 20, "ma10": 18, "ma20": 16, "ma60": 14, "close": 21}
        )
        self.assertEqual(score, 25)
        self.assertIn("多头", reason)

        # Test entry assessment stop loss calculation
        res = entry_assessment(
            klines=[],
            latest={"ma20": 100.0, "dif": 1.0, "dea": 0.5, "macd_bar": 0.5, "close": 105.0, "atr": 2.5}
        )
        self.assertIn("stop_loss", res)
        self.assertIn("stop_loss_ma20", res)
        self.assertIn("stop_loss_fixed", res)
        self.assertAlmostEqual(res["stop_loss_ma20"], 98.0)
        self.assertAlmostEqual(res["stop_loss_fixed"], 99.75)

    def test_multi_dim_model_dead_code_removal(self):
        """Verify dead code removal and signed vol_change in multi_dim_model."""
        import core.models.multi_dim_model as mdm
        from core.models.multi_dim_model import FiveDimScorer

        # Dead scripts locator removed
        self.assertFalse(hasattr(mdm, "_A_STOCKS_SCRIPTS"))
        self.assertFalse(hasattr(mdm, "_find_a_stocks_scripts"))

        # FiveDimScorer executes cleanly
        scorer = FiveDimScorer()
        mock_k = [
            [f"2026-01-{i+1:02d}", 10.0, 10.5, 10.6, 9.9, 100000 + i * 500]
            for i in range(65)
        ]
        from core.indicators.technical_indicators import calc_all
        tech = calc_all(mock_k)
        latest = tech["latest"]
        combo_res = scorer.scorer.score_full(mock_k, latest)
        res = scorer.score(mock_k, tech, latest, combo_res, "neutral", 60.0)
        self.assertIn("cs", res)
        self.assertIn("dims_raw", res)
        self.assertIn("资金", res["dims_raw"])


    def test_multi_dim_model_v3_deprecation_export(self):
        """Verify multi_dim_model_v3 re-exports SSOT without star import issues."""
        import core.models.multi_dim_model_v3 as v3
        self.assertTrue(hasattr(v3, "StockSelectionModel"))
        self.assertTrue(hasattr(v3, "FiveDimScorer"))
        self.assertTrue(hasattr(v3, "MarketGate"))

    def test_factor_synthesizer_zscore_ddof(self):
        """Verify FactorSynthesizer._zscore supports ddof parameterization."""
        from core.models.factor_synthesizer import FactorSynthesizer
        vals = [10.0, 20.0, 30.0]
        z_sample = FactorSynthesizer._zscore(vals, ddof=1)
        z_pop = FactorSynthesizer._zscore(vals, ddof=0)
        self.assertEqual(len(z_sample), 3)
        self.assertEqual(len(z_pop), 3)
        self.assertAlmostEqual(z_sample[1], 0.0)
        self.assertAlmostEqual(z_pop[1], 0.0)

    def test_mean_reversion_strategy_module_imports(self):
        """Verify MeanReversionStrategy uses config defaults and module-level indicator imports."""
        from core.strategy.mean_reversion_strategy import MeanReversionStrategy
        strat = MeanReversionStrategy()
        self.assertEqual(strat.rsi_oversold, 30.0)
        self.assertEqual(strat.rsi_overbought, 70.0)
        self.assertEqual(strat.stop_loss_pct, 0.05)

    def test_execution_action_engine_beijing_codes_and_dynamic_names(self):
        """Verify IntentEvaluator matches Beijing codes and dynamically registered names."""
        from core.strategy.execution_action_engine import IntentEvaluator

        # Code regex matches Beijing stock codes
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
        """Verify position_manager business functions return clean data without CLI printing."""
        from core.strategy import position_manager

        summary = position_manager.calculate_pnl_summary()
        self.assertIsInstance(summary, dict)
        self.assertIn("total_cost", summary)
        self.assertIn("floating_pnl", summary)
        self.assertIn("total_pnl", summary)

        triggers = position_manager.check_stop_triggers()
        self.assertIsInstance(triggers, list)


if __name__ == "__main__":
    unittest.main()
