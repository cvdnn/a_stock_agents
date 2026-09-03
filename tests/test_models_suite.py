# -*- coding: utf-8 -*-
"""
Models Test Suite for core/models/ modules:
- MultiFactorScorer (Z-scores, momentum, value, quality, volatility, multi-factor score)
- ComboScorer (100-point multi-dimension technical scoring and rating)
- StockScreener (Three-layer funnel screening)
- StrategyEvaluator & EvaluationEntry
"""

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.models.multi_factor_scorer import MultiFactorScorer
from core.models.combo_scorer import ComboScorer
from core.models.stock_screener import StockScreener
from core.models.strategy_evaluator import EvaluationEntry, EvaluationReport


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


class TestModelsSuite(unittest.TestCase):

    def setUp(self):
        self.klines = _gen_mock_klines(60, 10.0)

    def test_multi_factor_momentum(self):
        mfs = MultiFactorScorer()
        val, score = mfs.momentum_factor(self.klines, period=20)
        self.assertIsInstance(val, float)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_multi_factor_value_and_quality(self):
        mfs = MultiFactorScorer()
        val_score = mfs.value_factor(pe_value=15.0, pb_value=1.5)
        self.assertGreater(val_score, 0.0)

        q_score = mfs.quality_factor(self.klines, pe_value=18.0)
        self.assertGreater(q_score, 0.0)

    def test_multi_factor_volatility_and_scoring(self):
        mfs = MultiFactorScorer()
        vol_score = mfs.volatility_factor(self.klines)
        self.assertGreater(vol_score, 0.0)

        latest = {"close": 10.5, "ma5": 10.4, "ma10": 10.2, "ma20": 10.0, "atr": 0.2}
        res = mfs.score_multi_factor(
            self.klines,
            latest=latest,
            pe_value=15.0,
            pb_value=1.5
        )
        self.assertIn("factors", res)
        self.assertIn("composite_score", res)
        self.assertIn("rating", res)

    def test_multi_factor_z_score(self):
        mfs = MultiFactorScorer()
        zs = mfs.z_score([10.0, 20.0, 30.0, 40.0, 50.0])
        self.assertEqual(len(zs), 5)
        self.assertAlmostEqual(sum(zs), 0.0, places=5)

    def test_combo_scorer_full(self):
        from core.indicators.technical_indicators import calc_all
        tech = calc_all(self.klines)
        scorer = ComboScorer()
        res = scorer.score_full(self.klines, tech["latest"])
        self.assertIn("total", res)
        self.assertIn("max_total", res)
        self.assertIn("rating", res)
        self.assertIn("rating_text", res)
        self.assertIn(res["rating"], ["A", "B", "C", "D"])

    def test_stock_screener_funnel(self):
        screener = StockScreener()
        res = screener.screen(["600519", "000858"], fetch_cyq=False)
        self.assertIn("total_input", res)
        self.assertIn("stage1_board", res)
        self.assertIn("stage2_technical", res)
        self.assertIn("stage3_scored", res)
        self.assertIn("results", res)
        self.assertEqual(res["total_input"], 2)

    def test_strategy_evaluation_data_classes(self):
        entry = EvaluationEntry(
            date="2026-06-01",
            entry_price=1250.0,
            action="buy",
            rating="A",
            score_total=82,
            ret_5d=3.5,
            direction_correct=True
        )
        self.assertEqual(entry.date, "2026-06-01")
        self.assertEqual(entry.rating, "A")
        self.assertTrue(entry.direction_correct)

        report = EvaluationReport(stock_code="600519", directional_accuracy_pct=80.0, grade="优秀")
        self.assertEqual(report.stock_code, "600519")
        self.assertEqual(report.grade, "优秀")


if __name__ == "__main__":
    unittest.main()
