# -*- coding: utf-8 -*-
"""
Tests for DynamicUniverseEngine and dynamic market-inferred stock pools.
Verifies that universe generation is driven by real-time market data and time rules
instead of static hardcoded stock lists.
"""
import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from core.strategy.dynamic_universe import DynamicUniverseEngine


class TestDynamicUniverse(unittest.TestCase):
    """验证动态宇宙与市场主线推断引擎"""

    def setUp(self):
        self.mock_bridge = MagicMock()
        self.engine = DynamicUniverseEngine(bridge=self.mock_bridge)

    def test_infer_leading_sectors(self):
        """测试领涨主线板块动态推断：排序、过滤垃圾板块、计算成交量"""
        mock_board_summary = {
            "data": [
                {"groupLabel": "半导体", "changePct": 3.5, "totalTurnoverYuan": 250e8, "count": 85},
                {"groupLabel": "ST板块", "changePct": 4.0, "totalTurnoverYuan": 10e8, "count": 50},  # 应被过滤
                {"groupLabel": "光通信", "changePct": 2.8, "totalTurnoverYuan": 180e8, "count": 40},
                {"groupLabel": "房地产", "changePct": -1.5, "totalTurnoverYuan": 120e8, "count": 90},
            ]
        }
        self.mock_bridge.get_board_summary.return_value = mock_board_summary

        sectors = self.engine.infer_leading_sectors(top_n=3, min_change_pct=0.0)
        self.assertEqual(len(sectors), 2)
        self.assertEqual(sectors[0]["name"], "半导体")
        self.assertEqual(sectors[0]["change_pct"], 3.5)
        self.assertEqual(sectors[1]["name"], "光通信")
        # ST板块被成功过滤
        self.assertFalse(any("ST" in s["name"] for s in sectors))

    def test_infer_active_stocks_with_board_permissions(self):
        """测试全市场流动性标的动态提取与板块权限控制"""
        mock_quotes = [
            {"code": "sh600519", "name": "贵州茅台", "price": 1400.0, "volume": 50000, "amount": 70e8},
            {"code": "sz300750", "name": "宁德时代", "price": 200.0, "volume": 80000, "amount": 60e8},
            {"code": "sh688981", "name": "中芯国际", "price": 50.0, "volume": 90000, "amount": 45e8},
            {"code": "sh600000", "name": "浦发银行", "price": 10.0, "volume": 0, "amount": 0},      # 停牌应过滤
        ]
        self.mock_bridge.get_active_market_quotes.return_value = mock_quotes

        # 1. 默认主板模式：300750 与 688981 阻断
        stocks_mainboard = self.engine.infer_active_stocks(top_n=10, allow_all_boards=False)
        self.assertIn("600519", stocks_mainboard)
        self.assertNotIn("300750", stocks_mainboard)
        self.assertNotIn("688981", stocks_mainboard)
        self.assertNotIn("600000", stocks_mainboard)  # 零成交被过滤

        # 2. 跨板块全市场模式：放行双创
        stocks_all = self.engine.infer_active_stocks(top_n=10, allow_all_boards=True)
        self.assertIn("600519", stocks_all)
        self.assertIn("300750", stocks_all)
        self.assertIn("688981", stocks_all)

    def test_generate_dynamic_universe_hot_sectors_mode(self):
        """测试主线板块驱动的动态宇宙生成"""
        self.mock_bridge.get_board_summary.return_value = {
            "data": [
                {"groupLabel": "AI算力", "changePct": 4.2, "totalTurnoverYuan": 300e8, "count": 30},
                {"groupLabel": "半导体", "changePct": 3.1, "totalTurnoverYuan": 200e8, "count": 40},
            ]
        }
        self.mock_bridge.get_board_detail.side_effect = lambda group_key, limit: {
            "data": [
                {"code": "601138", "name": "工业富联"},
                {"code": "000977", "name": "浪潮信息"},
            ] if group_key == "AI算力" else [
                {"code": "603986", "name": "兆易创新"},
                {"code": "002371", "name": "北方华创"},
            ]
        }
        self.mock_bridge.get_active_market_quotes.return_value = []

        result = self.engine.generate_dynamic_universe(mode="hot_sectors", size=10)
        self.assertEqual(result["mode"], "hot_sectors")
        self.assertFalse(result["is_fallback"])
        self.assertIn("601138", result["stocks"])
        self.assertIn("000977", result["stocks"])
        self.assertIn("603986", result["stocks"])
        self.assertIn("002371", result["stocks"])
        self.assertIn("AI算力", result["rationale"])

    def test_generate_dynamic_universe_offline_fallback(self):
        """测试离线断网时优雅降级至基准测试池，明确标注 fallback"""
        self.mock_bridge.get_board_summary.return_value = None
        self.mock_bridge.get_board_detail.return_value = None
        self.mock_bridge.get_active_market_quotes.return_value = None

        result = self.engine.generate_dynamic_universe(mode="hot_sectors", size=15)
        self.assertTrue(result["is_fallback"])
        self.assertIn("离线模式降级", result["rationale"])
        self.assertGreater(len(result["stocks"]), 0)


if __name__ == "__main__":
    unittest.main()
