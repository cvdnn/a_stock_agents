# -*- coding: utf-8 -*-
"""
Unit tests for A-Stock Data Sync Engine & SQLite Store
"""
import sys
import unittest
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))

from core.data.sync_engine import DataSyncEngine, MarketDataStore, TradeCalendar


class TestDataSyncEngine(unittest.TestCase):

    def setUp(self):
        self.test_db_path = PROJECT_ROOT / "local" / "market_data" / "test_astock_data.db"
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        self.store = MarketDataStore(db_path=self.test_db_path)
        self.engine = DataSyncEngine(store=self.store)

    def tearDown(self):
        if self.test_db_path.exists():
            try:
                self.test_db_path.unlink()
            except Exception:
                pass

    def test_trade_calendar(self):
        # 2026-06-01 (周一) 到 2026-06-07 (周日)
        days = TradeCalendar.get_trading_days_between("2026-06-01", "2026-06-07")
        # 应该包含周一至周五 (5天)，不包含周六周日
        self.assertEqual(len(days), 5)
        self.assertIn("2026-06-01", days)
        self.assertNotIn("2026-06-06", days)
        self.assertNotIn("2026-06-07", days)

    def test_upsert_and_retrieve_klines(self):
        symbol = "sh600519"
        mock_data = [
            {"date": "2026-06-01", "open": 1600.0, "close": 1620.0, "high": 1630.0, "low": 1590.0, "volume": 10000},
            {"date": "2026-06-02", "open": 1620.0, "close": 1610.0, "high": 1625.0, "low": 1605.0, "volume": 12000},
        ]
        inserted = self.store.upsert_klines(symbol, mock_data)
        self.assertEqual(inserted, 2)

        res = self.store.get_klines(symbol)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["date"], "2026-06-01")
        self.assertEqual(res[0]["close"], 1620.0)

        # 再次更新第一天数据，验证 upsert 无主键冲突
        updated_data = [
            {"date": "2026-06-01", "open": 1600.0, "close": 1625.0, "high": 1630.0, "low": 1590.0, "volume": 10500},
        ]
        self.store.upsert_klines(symbol, updated_data)
        res2 = self.store.get_klines(symbol)
        self.assertEqual(len(res2), 2)
        self.assertEqual(res2[0]["close"], 1625.0)

    def test_integrity_audit_and_gap_detection(self):
        # 构造基准交易日
        ref_symbol = "sh000001"
        ref_data = [
            {"date": "2026-06-01", "open": 3000, "close": 3010, "high": 3020, "low": 2990, "volume": 500000},
            {"date": "2026-06-02", "open": 3010, "close": 3020, "high": 3030, "low": 3000, "volume": 500000},
            {"date": "2026-06-03", "open": 3020, "close": 3030, "high": 3040, "low": 3010, "volume": 500000},
        ]
        self.store.upsert_klines(ref_symbol, ref_data)

        # 构造缺失 2026-06-02 的标的
        test_symbol = "sz000001"
        gap_data = [
            {"date": "2026-06-01", "open": 10, "close": 10.2, "high": 10.3, "low": 9.9, "volume": 10000},
            {"date": "2026-06-03", "open": 10.2, "close": 10.5, "high": 10.6, "low": 10.1, "volume": 12000},
        ]
        self.store.upsert_klines(test_symbol, gap_data)

        audits = self.engine.audit_integrity([test_symbol])
        self.assertEqual(len(audits), 1)
        audit = audits[0]
        self.assertEqual(audit["status"], "degraded")
        self.assertEqual(audit["missing_count"], 1)
        self.assertIn("2026-06-02", audit["missing_days"])


if __name__ == "__main__":
    unittest.main()
