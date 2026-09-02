# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from core.config import OUTPUT_CACHE_DIR
from core.paper_trading.engine import PaperTradingEngine

class TestPaperTrading(unittest.TestCase):
    def setUp(self):
        self.db_path = str(OUTPUT_CACHE_DIR / "test_pt_unit.db")
        self.engine = PaperTradingEngine(db_path=self.db_path)


    def test_account(self):
        try:
            acc = self.engine.get_account("test_user")
        except Exception:
            acc = self.engine.create_account("test_user", initial_cash=500000.0)
        self.assertIsNotNone(acc)

if __name__ == "__main__":
    unittest.main()
