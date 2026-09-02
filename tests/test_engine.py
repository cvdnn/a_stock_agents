# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from core.strategy.execution_action_engine import ExecutionActionEngine

class TestEngine(unittest.TestCase):
    def test_breakeven_precision(self):
        # 10.00 cost, 1000 shares -> 10.02
        p = ExecutionActionEngine.calc_min_breakeven_price(10.0, 1000)
        self.assertEqual(p, 10.02)

if __name__ == "__main__":
    unittest.main()
