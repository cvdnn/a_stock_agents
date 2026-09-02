# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from core.data.data_bridge import DataBridge
from core.models.combo_scorer import ComboScorer

class TestScorer(unittest.TestCase):
    def setUp(self):
        self.bridge = DataBridge()
        self.q = self.bridge.get_realtime_quote("600519")
        self.klines = self.bridge.tencent_kline("600519", count=60)
        self.scorer = ComboScorer()

    def test_combo_scorer(self):
        res = self.scorer.score_full(klines=self.klines, latest=self.q)
        self.assertIn("total", res)
        self.assertTrue(0 <= res["total"] <= 100)

if __name__ == "__main__":
    unittest.main()
