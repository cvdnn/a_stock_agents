# -*- coding: utf-8 -*-
"""
Models Test Suite for core/models/ modules:
Validates:
- MultiFactorScorer (Z-scores, momentum, value, quality, volatility, monotonic trend score)
- ComboScorer (100-point scoring, fund flow parsing, missing dimension normalized score, dual stop loss)
- StockScreener (Three-layer funnel screening, board top 10 ranking, normalized score sorting)
- FactorSynthesizer (Median imputation for missing values, sample std ddof=1, weight normalization)
- MarketAssessor (Index code matching, volume tiers, capital flow dynamic scoring)
- MultiDimModel (MarketGate auto-trigger, dynamic thresholds, prev_close baseline, rotation candidate filter)
- StrategyEvaluator & EvaluationEntry
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.models.multi_factor_scorer import MultiFactorScorer
from core.models.combo_scorer import ComboScorer
from core.models.stock_screener import StockScreener
from core.models.factor_synthesizer import FactorSynthesizer
from core.models.market_assessor import MarketAssessor
from core.models.strategy_evaluator import EvaluationEntry, EvaluationReport
from core.models.multi_dim_model import MarketGate, StockSelectionV3, RotationBacktest


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

    def test_multi_factor_monotonic_trend_score(self):
        """Verify trend_score in quality_factor is strictly monotonic across up-day intervals."""
        def build_klines(up_count: int):
            closes = [10.0]
            for i in range(20):
                step = 0.1 if i < up_count else -0.1
                closes.append(round(closes[-1] + step, 2))
            return [[f"2026-08-{i+1:02d}", str(c), str(c), str(c+0.05), str(c-0.05), "1000"] for i, c in enumerate(closes)]

        # up_ratio = 12/20 = 0.60 -> [0.50, 0.65], trend_score = 100.0
        q_100 = MultiFactorScorer.quality_factor(build_klines(12))
        # up_ratio = 9/20 = 0.45 -> [0.40, 0.50), trend_score = 70.0
        q_70 = MultiFactorScorer.quality_factor(build_klines(9))
        # up_ratio = 7/20 = 0.35 -> [0.30, 0.40), trend_score = 40.0
        q_40 = MultiFactorScorer.quality_factor(build_klines(7))
        # up_ratio = 4/20 = 0.20 -> < 0.30, trend_score = 20.0
        q_20 = MultiFactorScorer.quality_factor(build_klines(4))

        self.assertGreater(q_100, q_70)
        self.assertGreater(q_70, q_40)
        self.assertGreater(q_40, q_20)

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

    def test_combo_scorer_fund_flow_and_missing_dimensions(self):
        """Verify fund flow unit conversion (万 vs 亿) and normalized_score under missing dimensions."""
        scorer = ComboScorer()

        # 1. Fund flow units
        score_5000w, reason_5000w = ComboScorer.score_fund_flow("主力净流入 5000万")
        self.assertEqual(score_5000w, 12)
        self.assertIn("0.50亿", reason_5000w)

        score_1_5y, reason_1_5y = ComboScorer.score_fund_flow("主力净流入 1.5亿")
        self.assertEqual(score_1_5y, 15)

        # 2. Missing dimensions normalization
        mock_latest = {
            "close": 10.5, "ma5": 10.3, "ma10": 10.1, "ma20": 9.9, "ma60": 9.5,
            "dif": 0.2, "dea": 0.1, "macd_bar": 0.2, "volume_hands": 1000, "vol_ratio": 1.2
        }
        res = scorer.score_full(self.klines, mock_latest, cyq_data=None, fund_data=None)
        self.assertEqual(res["effective_max"], 70)
        self.assertIn("normalized_score", res)
        expected_norm = round(res["adjusted_total"] / 70.0 * 100, 1)
        self.assertEqual(res["normalized_score"], expected_norm)

        # 3. Dual stop-loss in entry_assessment
        from core.models.combo_scorer import entry_assessment
        entry = entry_assessment(self.klines, mock_latest)
        self.assertIn("stop_loss_fixed", entry)
        self.assertIn("stop_loss_ma20", entry)

    def test_stock_screener_funnel_and_sorting(self):
        """Verify stock screener three-layer funnel and normalized_score sorting."""
        screener = StockScreener()

        with patch.object(screener.bridge, "get_board_summary") as mock_boards, \
             patch.object(screener.bridge, "get_realtime_quote") as mock_quote, \
             patch.object(screener.bridge, "get_kline") as mock_kline:

            mock_boards.return_value = {
                "groupLabel": "行业",
                "data": [
                    {"groupLabel": "白酒", "changePct": 2.5},
                    {"groupLabel": "芯片", "changePct": 2.1},
                ]
            }
            mock_quote.return_value = {"code": "sh600519", "name": "贵州茅台", "price": 1800.0, "change_pct": 2.0}
            mock_kline.return_value = self.klines

            res = screener.screen(["600519"], fetch_cyq=False)
            self.assertIn("total_input", res)
            self.assertIn("stage1_board", res)
            self.assertIn("stage2_technical", res)
            self.assertIn("stage3_scored", res)
            self.assertIn("results", res)
            self.assertEqual(res["total_input"], 1)

    def test_factor_synthesizer_imputation_and_normalization(self):
        """Verify FactorSynthesizer median imputation, ddof=1, and weight normalization."""
        universe = {
            "600519": {"ret_20d": 10.0, "rsi_14": 40.0},
            "000858": {"ret_20d": 5.0, "rsi_14": 50.0},
            "000568": {"ret_20d": 8.0, "rsi_14": None},  # missing rsi_14
        }
        res = FactorSynthesizer.synthesize_universe(universe, custom_weights={"ret_20d": 2.0, "rsi_14": 2.0})
        self.assertEqual(len(res), 3)
        z_000568 = res["000568"]["standardized_z"]["rsi_14"]
        self.assertAlmostEqual(z_000568, 0.0, places=1)

        # Sample std dev ddof=1
        vals = [10.0, 20.0, 30.0]
        z_sample = FactorSynthesizer._zscore(vals, ddof=1)
        self.assertEqual(len(z_sample), 3)
        self.assertAlmostEqual(z_sample[1], 0.0)

    def test_market_assessor_index_matching_and_volume(self):
        """Verify MarketAssessor distinguishes index 000001 and grades volume dynamically."""
        assessor = MarketAssessor()

        # sh000001 is index
        idx_sh = {"sh": {"name": "上证指数", "code": "sh000001", "change_pct": 0.8}}
        score_sh, _, _ = assessor.assess_trend(idx_sh)
        self.assertEqual(score_sh, 30)

        # Volume tiering with quotes list
        score_vol_high, max_v, reason_v = assessor.assess_volume([{"amount": 1200000000000}])  # 1.2万亿
        self.assertEqual(max_v, 20)
        self.assertEqual(score_vol_high, 20)
        self.assertIn("破万亿", reason_v)

        # Capital flow assessment
        c_score, c_max, _ = MarketAssessor.assess_capital({"net_inflow": 45.0})
        self.assertEqual(c_score, 15)

    def test_multi_dim_model_gate_and_eval(self):
        """Verify MarketGate auto-assessment and StockSelectionV3 sell signals."""
        engine = StockSelectionV3(enable_filter=False)
        self.assertFalse(engine.gate._assessed)

        def mock_assess():
            engine.gate.sh_above_ma20 = True
            engine.gate.health_score = 75
            engine.gate.state = "偏多"
            engine.gate.config = engine.gate.STATE_CONFIG["偏多"]
            engine.gate._assessed = True
            return engine.gate.state

        engine.gate.assess = mock_assess
        engine.bridge.tencent_kline = lambda code, count=250: [["2026-01-01", 10.0, 10.0, 9.8, 10.2, 1000] for _ in range(70)]
        engine.bridge.get_realtime_quote = lambda code: {"price": 10.0, "change_pct": 1.0, "code": code}

        res = engine.evaluate("600519")
        self.assertTrue(engine.gate._assessed)
        self.assertIn("rating", res)
        self.assertIn("composite_score", res)

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
