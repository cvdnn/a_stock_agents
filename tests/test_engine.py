# -*- coding: utf-8 -*-
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from core.strategy.execution_action_engine import ExecutionActionEngine
from core.config import get_market_config, save_market_config, check_market_config_prompt

class TestEngine(unittest.TestCase):
    def test_breakeven_precision_default(self):
        # Default: commission 万2.5, min 5.0 RMB
        p = ExecutionActionEngine.calc_min_breakeven_price(10.0, 1000)
        self.assertEqual(p, 10.02)
        
        # 100.00 cost, 1000 shares (100k principal)
        p_large = ExecutionActionEngine.calc_min_breakeven_price(100.0, 1000)
        self.assertEqual(p_large, 100.11)

    def test_breakeven_custom_rates(self):
        # Custom: 万1.2, min 5.0
        custom_cfg = {
            "commission_rate": 0.00012,
            "min_commission": 5.0,
            "tax_rate_sell": 0.0005,
            "transfer_fee_rate": 0.00001,
            "breakeven_ceil_cent": True
        }
        p = ExecutionActionEngine.calc_min_breakeven_price(100.0, 1000, market_cfg=custom_cfg)
        self.assertEqual(p, 100.08)

        # Custom: 万1.0, 免5 (min_commission = 0.0)
        mian5_cfg = {
            "commission_rate": 0.00010,
            "min_commission": 0.0,
            "tax_rate_sell": 0.0005,
            "transfer_fee_rate": 0.00001,
            "breakeven_ceil_cent": True
        }
        p_m5 = ExecutionActionEngine.calc_min_breakeven_price(10.0, 1000, market_cfg=mian5_cfg)
        self.assertEqual(p_m5, 10.01)

    def test_market_config_flow(self):
        # Test prompt when is_user_configured is False
        save_market_config(is_user_configured=False)
        needs_prompt, prompt = check_market_config_prompt()
        self.assertTrue(needs_prompt)
        self.assertIn("万2.5", prompt)

        # Test prompt when is_user_configured is True
        save_market_config(commission_rate=0.00025, min_commission=5.0, is_user_configured=True)
        needs_prompt, prompt = check_market_config_prompt()
        self.assertFalse(needs_prompt)

if __name__ == "__main__":
    unittest.main()
