# -*- coding: utf-8 -*-
"""
Test Suite for Unified Algorithm Registry & Base Framework (AlgoRegistry 2.0).
"""
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.models.base_algorithm import (
    AlgorithmCategory,
    AlgorithmLifecycleStage,
    AlgorithmMetadata,
    BaseAlgorithm,
)
from core.models.registry import (
    AlgoRegistry,
    ModelRegistry,
    get_algo,
    get_model,
    list_algos,
    list_models,
    run_algo,
)


class TestAlgoRegistry(unittest.TestCase):
    """Test suite verifying unified algorithm registration, taxonomy, and execution."""

    def test_registry_coverage_and_categories(self):
        """Verify that algorithms across all 7 taxonomy categories are registered."""
        all_algos = list_algos()
        self.assertGreaterEqual(len(all_algos), 25)

        categories_found = {a["category"] for a in all_algos}
        expected_categories = {
            AlgorithmCategory.INDICATOR.value,
            AlgorithmCategory.ALPHA_FACTOR.value,
            AlgorithmCategory.SCORING_MODEL.value,
            AlgorithmCategory.STRATEGY.value,
            AlgorithmCategory.RISK_SIZING.value,
            AlgorithmCategory.EXECUTION.value,
            AlgorithmCategory.EVALUATOR.value,
        }
        for exp_cat in expected_categories:
            self.assertIn(exp_cat, categories_found, f"Category {exp_cat} should have registered algorithms")

    def test_category_and_stage_filtering(self):
        """Verify filtering algorithms by category and lifecycle stage."""
        indicators = list_algos(category=AlgorithmCategory.INDICATOR)
        self.assertTrue(len(indicators) >= 8)
        for ind in indicators:
            self.assertEqual(ind["category"], AlgorithmCategory.INDICATOR.value)

        strategies = list_algos(category=AlgorithmCategory.STRATEGY)
        self.assertTrue(len(strategies) >= 5)
        for st in strategies:
            self.assertEqual(st["category"], AlgorithmCategory.STRATEGY.value)

        prod_algos = list_algos(stage=AlgorithmLifecycleStage.PRODUCTION)
        self.assertTrue(len(prod_algos) >= 20)

    def test_metadata_lookup_and_serialization(self):
        """Verify metadata completeness and to_dict serialization."""
        meta = AlgoRegistry.get_metadata("volatility_breakout")
        self.assertIsNotNone(meta)
        self.assertEqual(meta.name, "volatility_breakout")
        self.assertEqual(meta.category, AlgorithmCategory.STRATEGY)
        self.assertEqual(meta.stage, AlgorithmLifecycleStage.PRODUCTION)
        self.assertIn("boll_breakout", meta.aliases)

        meta_dict = meta.to_dict()
        self.assertIn("algo_id", meta_dict)
        self.assertIn("version", meta_dict)
        self.assertIn("author", meta_dict)

    def test_function_algorithm_execution(self):
        """Verify invocation of function-based algorithms (indicators, factors, metrics)."""
        # 1. Technical indicator: MACD
        closes = [float(10 + i * 0.2 + (1 if i % 2 == 0 else -1) * 0.1) for i in range(40)]
        macd_fn = AlgoRegistry.get("macd")
        macd_res = macd_fn(closes)
        self.assertIn("dif", macd_res)
        self.assertIn("dea", macd_res)
        self.assertIn("bar", macd_res)

        # 2. Run algo helper: RSI
        rsi_res = run_algo("rsi", closes, 14)
        self.assertEqual(len(rsi_res), len(closes))

        # 3. Alpha factor: calculate_chip_cost
        sample_klines = []
        for i in range(30):
            sample_klines.append({
                "date": f"2026-08-{i+1:02d}",
                "open": 10.0 + i * 0.1,
                "close": 10.2 + i * 0.1,
                "high": 10.5 + i * 0.1,
                "low": 9.8 + i * 0.1,
                "volume": 10000.0,
                "turnover": 2.5,
            })
        chip_cost = run_algo("chip_cost", sample_klines)
        self.assertIsInstance(chip_cost, float)
        self.assertGreater(chip_cost, 0)

        # 4. Evaluator: backtest_metrics
        curve = [{"date": f"2026-08-{i+1:02d}", "equity": 100000.0 + i * 500} for i in range(10)]
        trades = [{"action": "buy", "price": 10.0, "qty": 100, "date": "2026-08-01"},
                  {"action": "sell", "price": 11.0, "qty": 100, "date": "2026-08-05", "profit": 100.0}]
        metrics = run_algo("backtest_metrics", curve, trades, initial_cash=100000.0, final_equity=104500.0, days=10)
        self.assertIn("total_return_pct", metrics)
        self.assertIn("sharpe_ratio", metrics)
        self.assertIn("win_rate_pct", metrics)

    def test_class_algorithm_instantiation(self):
        """Verify factory instantiation of strategy and model classes."""
        # 1. Strategy class
        strategy = get_algo("volatility_breakout")
        self.assertTrue(hasattr(strategy, "detect_squeeze"))

        # 2. Alias resolution
        strategy_alias = get_algo("boll_breakout")
        self.assertEqual(type(strategy), type(strategy_alias))

        # 3. Risk sizing class
        sizer = get_algo("position_sizer")
        self.assertTrue(hasattr(sizer, "calculate_stock_allocation"))

    def test_aliases_and_deprecation_warning(self):
        """Verify alias lookup, case-insensitivity, and deprecation warnings."""
        # 1. Case-insensitive lookup
        meta1 = AlgoRegistry.get_metadata("VOLATILITY_BREAKOUT")
        self.assertIsNotNone(meta1)
        self.assertEqual(meta1.name, "volatility_breakout")

        # 2. Deprecated alias warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always", DeprecationWarning)
            model = AlgoRegistry.get("multi_dim_v3", enable_filter=False)
            self.assertIsNotNone(model)
            dep_warnings = [item for item in w if issubclass(item.category, DeprecationWarning)]
            self.assertGreaterEqual(len(dep_warnings), 1)
            self.assertIn("deprecated", str(dep_warnings[-1].message).lower())

        # 3. Non-existent algorithm raises KeyError
        with self.assertRaises(KeyError):
            AlgoRegistry.get("totally_unknown_algorithm_xyz")

    def test_model_registry_backward_compatibility(self):
        """Verify that legacy ModelRegistry and get_model/list_models are 100% compatible."""
        # 1. Legacy ModelRegistry.get
        from core.models.multi_dim_model import StockSelectionModel
        m1 = ModelRegistry.get("multi_dim", enable_filter=False)
        self.assertIsInstance(m1, StockSelectionModel)

        m2 = get_model("5a", enable_filter=False)
        self.assertIsInstance(m2, StockSelectionModel)

        # 2. Legacy list_models
        models = list_models()
        self.assertGreaterEqual(len(models), 7)
        model_names = [m["name"] for m in models]
        self.assertIn("multi_dim", model_names)
        self.assertIn("combo_scorer", model_names)
        self.assertIn("multi_factor_scorer", model_names)
        self.assertIn("factor_synthesizer", model_names)
        self.assertIn("market_assessor", model_names)

        # Verify dict schema of list_models
        sample = models[0]
        for k in ["name", "description", "version", "module", "aliases", "deprecated_aliases"]:
            self.assertIn(k, sample)


if __name__ == "__main__":
    unittest.main()
