# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from core.data.data_bridge import DataBridge
from core.indicators.technical_indicators import calc_all, second_golden_cross, gap_analysis

class TestIndicators(unittest.TestCase):
    def setUp(self):
        self.bridge = DataBridge()
        self.klines = self.bridge.tencent_kline("600519", count=60)

    def test_calc_all(self):
        tech = calc_all(self.klines)
        self.assertIn("ma", tech)
        self.assertIn("macd", tech)
        self.assertIn("kdj", tech)

    def test_golden_cross(self):
        golden = second_golden_cross(self.klines)
        self.assertIn("verdict", golden)
        self.assertIn("checklist", golden)

if __name__ == "__main__":
    unittest.main()
