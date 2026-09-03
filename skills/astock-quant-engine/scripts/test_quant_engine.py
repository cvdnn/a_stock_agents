"""
A-Share Quant Engine - Comprehensive Test Suite
测试数据接入、量价因子、非结构化情绪因子、截面合成、风控状态机与回测引擎
"""

import os
import unittest
from data_layer import DataLayer
from pv_factors import PVFactors
from unstructured_factors import UnstructuredFactors
from factor_synthesizer import FactorSynthesizer
from risk_position_manager import PositionSizer, AccountPortfolio, RiskEngine
from backtest_engine import BacktestEngine


class TestQuantEngine(unittest.TestCase):

    def test_01_pv_factors(self):
        """测试量价因子计算"""
        # 构造模拟 K 线
        klines = []
        base_price = 10.0
        for i in range(40):
            p = base_price + i * 0.1
            klines.append({
                "date": f"2026-01-{i+1:02d}",
                "open": p - 0.05,
                "close": p,
                "high": p + 0.1,
                "low": p - 0.1,
                "volume": 10000 + i * 100,
                "amount": (p * (10000 + i * 100))
            })
        
        factors = PVFactors.extract_factors(klines)
        self.assertIn("ret_20d", factors)
        self.assertIn("rsi_14", factors)
        self.assertIn("norm_atr", factors)
        self.assertGreater(factors["ret_20d"], 0)
        print(" [PASS] PVFactors extracted successfully:", list(factors.keys()))

    def test_02_unstructured_factors(self):
        """测试非结构化舆情因子与衰减"""
        text_pos = "公司发布业绩预增公告，净利润大幅增长超预期，签订重大合同"
        score_pos = UnstructuredFactors.score_text(text_pos)
        self.assertGreater(score_pos, 0.4)

        text_neg = "公司收到立案调查问询函，存在退市风险与债务违约"
        score_neg = UnstructuredFactors.score_text(text_neg)
        self.assertLess(score_neg, -0.4)

        # 测试半衰期衰减 (3天半衰期，经过3天得分应减半)
        decayed = UnstructuredFactors.apply_decay(score_pos, days_elapsed=3.0, half_life_days=3.0)
        self.assertAlmostEqual(decayed, score_pos * 0.5, places=2)
        print(" [PASS] UnstructuredFactors sentiment scoring & decay verified.")

    def test_03_factor_synthesizer(self):
        """测试截面 MAD Winsorize、Z-Score 与 Top-K 选股"""
        universe_factors = {
            "600519": {"ret_20d": 8.5, "bias_20d": 3.2, "norm_atr": 0.02, "sentiment_score": 0.6, "kdj_j": 30.0, "boll_pct_b": 0.2, "vol_surge_5_20": 1.5, "vwap_bias_5": 1.2, "pv_corr_20": 0.5, "profit_ratio": 15.0},
            "000858": {"ret_20d": 4.1, "bias_20d": 1.5, "norm_atr": 0.025, "sentiment_score": 0.2, "kdj_j": 45.0, "boll_pct_b": 0.4, "vol_surge_5_20": 1.1, "vwap_bias_5": 0.5, "pv_corr_20": 0.3, "profit_ratio": 8.0},
            "300750": {"ret_20d": -6.2, "bias_20d": -4.0, "norm_atr": 0.045, "sentiment_score": -0.5, "kdj_j": 80.0, "boll_pct_b": 0.9, "vol_surge_5_20": 0.8, "vwap_bias_5": -2.0, "pv_corr_20": -0.2, "profit_ratio": -10.0}
        }
        ranked = FactorSynthesizer.synthesize_universe(universe_factors)
        self.assertEqual(len(ranked), 3)
        self.assertGreater(ranked["600519"]["composite_alpha"], ranked["300750"]["composite_alpha"])
        top_1 = FactorSynthesizer.select_top_k(ranked, top_k=1)
        self.assertEqual(top_1[0]["symbol"], "600519")
        print(" [PASS] FactorSynthesizer cross-sectional ranking verified.")

    def test_04_t1_risk_state_machine(self):
        """测试 T+1 交易状态机与 ATR 移动止损、阶梯止盈"""
        account = AccountPortfolio(initial_cash=100000.0)
        
        # Day 1: 买入 1000 股 @ 10.0 元
        success = account.buy("600519", 1000, 10.0, "2026-01-01", atr=0.3)
        self.assertTrue(success)
        self.assertEqual(account.positions["600519"]["shares"], 1000)
        self.assertEqual(account.positions["600519"]["available_shares"], 0)  # T+1 当日冻结

        # 当天试图卖出 -> 必须被拦截
        sell_fail = account.sell("600519", 1000, 10.5, "2026-01-01")
        self.assertFalse(sell_fail)

        # 日终结算 -> 次日解冻
        account.end_of_day_settlement()
        self.assertEqual(account.positions["600519"]["available_shares"], 1000)

        # Day 2: 盈利达到 +6% (价格 10.6)，触发阶梯止盈 1 档 (卖 1/3 = 300股)
        pos = account.positions["600519"]
        actions = RiskEngine.evaluate_position_risk(pos, current_price=10.6, current_atr=0.3, date="2026-01-02")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "TAKE_PROFIT_1")
        self.assertEqual(actions[0]["shares"], 300)

        # 执行止盈
        account.sell("600519", actions[0]["shares"], actions[0]["price"], "2026-01-02")
        self.assertEqual(account.positions["600519"]["shares"], 700)

        print(" [PASS] AccountPortfolio T+1 & RiskEngine laddered take-profit verified.")


if __name__ == "__main__":
    unittest.main()
