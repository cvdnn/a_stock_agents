import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.indicators.pv_factors import PVFactors
from core.indicators.technical_indicators import second_golden_cross
from core.paper_trading.engine import calc_market_impact_bps, _apply_slippage
from core.models.factor_synthesizer import FactorSynthesizer


class TestAlgorithmOptimizations(unittest.TestCase):
    """测试 4 项算法优化功能."""

    def test_chip_cost_turnover_decay(self):
        """测试换手率衰减筹码分布与获利盘估算."""
        # 构造模拟日K线
        klines = []
        base_price = 10.0
        for i in range(120):
            p = base_price + i * 0.1
            klines.append({
                "time": f"2026-01-{(i % 28) + 1:02d}",
                "open": p - 0.05,
                "high": p + 0.1,
                "low": p - 0.1,
                "close": p,
                "volume": 10000 + (i * 100),
                "turnover": 2.5  # 2.5% 换手率
            })

        cost = PVFactors.calculate_chip_cost(klines, lookback=120)
        self.assertGreater(cost, base_price)
        self.assertLess(cost, klines[-1]["close"])

        factors = PVFactors.extract_factors(klines)
        self.assertIn("profit_ratio", factors)
        self.assertGreater(factors["profit_ratio"], 0.0)

    def test_second_golden_cross_enhanced(self):
        """测试 MACD 底背离与形态识别算法强化."""
        # 构造包含两波下探且第二次底背离抬高的 K 线序列
        klines = []
        # 前期下跌 60 天
        for i in range(60):
            p = 20.0 - i * 0.15
            klines.append(["2025-01-01", p + 0.1, p, p + 0.2, p - 0.2, 50000])

        # 第一波反抽 (金叉)
        for i in range(10):
            p = 11.0 + i * 0.2
            klines.append(["2025-04-01", p - 0.1, p, p + 0.1, p - 0.1, 80000])

        # 回踩打平或微破前低 (价格10.5)，但下跌速度更缓 (酝酿背离)
        for i in range(10):
            p = 13.0 - i * 0.25
            klines.append(["2025-05-01", p + 0.1, p, p + 0.1, p - 0.1, 40000])

        # 第二波弱反抽 (二次金叉)
        for i in range(8):
            p = 10.5 + i * 0.15
            klines.append(["2025-06-01", p - 0.1, p, p + 0.1, p - 0.1, 60000])

        res = second_golden_cross(klines)
        self.assertIn("verdict", res)
        self.assertIn("checklist", res)
        self.assertIn("is_divergence", res)
        self.assertIsInstance(res["checklist"], list)
        self.assertGreater(res["crosses_count"], 0)

    def test_market_impact_slippage(self):
        """测试平方根市场冲击成本模型."""
        base_bps = 5.0
        # 小单 (1,000 股 / 日成交 10,000,000 股 -> 占比万分之一)
        small_slip = calc_market_impact_bps(
            order_shares=1000,
            day_volume=10000000,
            daily_volatility=0.02,
            gamma=0.1,
            base_slippage_bps=base_bps
        )
        # 大单 (500,000 股 / 日成交 10,000,000 股 -> 占比 5%)
        large_slip = calc_market_impact_bps(
            order_shares=500000,
            day_volume=10000000,
            daily_volatility=0.02,
            gamma=0.1,
            base_slippage_bps=base_bps
        )
        self.assertGreater(large_slip, small_slip)
        self.assertGreaterEqual(small_slip, base_bps)

        # 验证价格方向
        price = 10.0
        buy_p = _apply_slippage(price, "buy", slippage_bps=large_slip)
        sell_p = _apply_slippage(price, "sell", slippage_bps=large_slip)
        self.assertGreater(buy_p, price)
        self.assertLess(sell_p, price)

    def test_factor_synthesizer_regimes_and_ic(self):
        """测试多因子市场状态机制权重与动态 IC 权重."""
        universe = {
            "600519": {
                "ret_20d": 5.0, "bias_20d": 2.0, "kdj_j": 25.0, "boll_pct_b": 0.3,
                "vol_surge_5_20": 1.2, "vwap_bias_5": 1.0, "pv_corr_20": 0.4,
                "norm_atr": 0.02, "profit_ratio": 12.0, "sentiment_score": 0.5
            },
            "000858": {
                "ret_20d": -2.0, "bias_20d": -1.0, "kdj_j": 70.0, "boll_pct_b": 0.8,
                "vol_surge_5_20": 0.9, "vwap_bias_5": -0.5, "pv_corr_20": -0.1,
                "norm_atr": 0.03, "profit_ratio": -5.0, "sentiment_score": -0.2
            }
        }

        # 1. 检验牛市机制权重合成
        res_bull = FactorSynthesizer.synthesize_universe(universe, regime="BULL")
        self.assertIn("600519", res_bull)
        self.assertGreater(res_bull["600519"]["composite_alpha"], res_bull["000858"]["composite_alpha"])

        # 2. 检验熊市机制权重合成
        res_bear = FactorSynthesizer.synthesize_universe(universe, regime="BEAR")
        self.assertIn("000858", res_bear)

        # 3. 检验动态 IC 权重算法
        ic_dict = {"ret_20d": 0.08, "kdj_j": 0.04, "sentiment_score": 0.06}
        ic_weights = FactorSynthesizer.calculate_ic_weights(ic_dict)
        self.assertIn("ret_20d", ic_weights)
        self.assertAlmostEqual(sum(ic_weights.values()), 1.0, places=2)


if __name__ == "__main__":
    unittest.main()
