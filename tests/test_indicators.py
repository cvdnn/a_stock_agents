# -*- coding: utf-8 -*-
"""
Technical Indicators Regression Test Suite:
Validates:
- calc_all (MA, MACD, KDJ, RSI, BOLL, ATR)
- second_golden_cross rating and checklists
- gap_analysis (upward/downward gap detection and fill direction)
- ma & rsi short series safety guards
"""

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.indicators.technical_indicators import (
    calc_all,
    second_golden_cross,
    gap_analysis,
    ma,
    rsi,
)


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


class TestIndicators(unittest.TestCase):

    def setUp(self):
        self.klines = _gen_mock_klines(60, 10.0)

    def test_calc_all(self):
        tech = calc_all(self.klines)
        self.assertIn("ma", tech)
        self.assertIn("macd", tech)
        self.assertIn("kdj", tech)
        self.assertIn("rsi", tech)
        self.assertIn("boll", tech)
        self.assertIn("atr", tech)
        self.assertIn("latest", tech)

    def test_golden_cross(self):
        golden = second_golden_cross(self.klines)
        self.assertIn("verdict", golden)
        self.assertIn("checklist", golden)
        self.assertIn(golden["verdict"], ("A", "B", "C", "D"))

    def test_gap_analysis_and_fill(self):
        """Verify gap_analysis detects gaps and checks fill direction correctly."""
        base_klines = [
            [f"2026-08-0{i+1}", "10.0", "10.0", "10.5", "9.8", "1000"]
            for i in range(4)
        ]

        # Case A: Downward gap, not filled
        # Yesterday close: 10.0. Today: open 9.0, high 9.5 (< 10.0) -> unfilled
        klines_unfilled = base_klines + [
            ["2026-08-05", "9.0", "9.2", "9.5", "8.9", "1000"]
        ]
        res_unfilled = gap_analysis(klines_unfilled)
        self.assertGreaterEqual(len(res_unfilled["gaps"]), 1)
        last_gap = res_unfilled["gaps"][-1]
        self.assertEqual(last_gap["direction"], "down")
        self.assertFalse(last_gap["filled"])

        # Case B: Downward gap filled
        # Today high = 10.2 (>= 10.0) -> filled
        klines_filled = base_klines + [
            ["2026-08-05", "9.0", "9.8", "10.2", "8.9", "1000"]
        ]
        res_filled = gap_analysis(klines_filled)
        self.assertGreaterEqual(len(res_filled["gaps"]), 1)
        self.assertTrue(res_filled["gaps"][-1]["filled"])

    def test_ma_rsi_short_series_guards(self):
        """Verify ma and rsi handle short series safely without exceptions."""
        self.assertEqual(ma([10.0, 11.0], 5), [0.0, 0.0])
        self.assertEqual(len(rsi([10.0, 11.0], 14)), 2)


if __name__ == "__main__":
    unittest.main()
