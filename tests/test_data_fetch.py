# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from core.data.data_bridge import DataBridge

class TestDataFetch(unittest.TestCase):
    def setUp(self):
        self.bridge = DataBridge()

    def test_realtime_quote(self):
        q = self.bridge.get_realtime_quote("600519")
        self.assertIsNotNone(q)
        self.assertIn("price", q)
        self.assertGreater(q["price"], 0)

    def test_kline(self):
        klines = self.bridge.tencent_kline("600519", count=30)
        self.assertGreaterEqual(len(klines), 10)

if __name__ == "__main__":
    unittest.main()
