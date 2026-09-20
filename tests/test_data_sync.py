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

    def test_calendar_derived_from_local_klines_with_content_version(self):
        """交易日历以本地 daily_kline 实际交易日推导，并派生内容版本号（规范 §11.2）。"""
        ref_symbol = "sh000001"
        self.store.upsert_klines(ref_symbol, [
            {"date": "2026-06-01", "open": 3000, "close": 3010, "high": 3020, "low": 2990, "volume": 500000},
            {"date": "2026-06-02", "open": 3010, "close": 3020, "high": 3030, "low": 3000, "volume": 500000},
        ])

        days = TradeCalendar.trading_days_from_local("2026-06-01", "2026-06-05", db_path=self.test_db_path)
        self.assertEqual(days, ["2026-06-01", "2026-06-02"])

        # 目标区间超出本地已同步覆盖 → 空集合，调用方须按"日历不可用"失败关闭
        self.assertEqual(
            TradeCalendar.trading_days_from_local("2027-01-01", "2027-01-05", db_path=self.test_db_path), []
        )

        # 版本号为集合内容标识，与顺序无关
        version = TradeCalendar.calendar_version(days)
        self.assertEqual(version, TradeCalendar.calendar_version(reversed(days)))

        # 回填任一交易日即产生新版本
        self.store.upsert_klines(ref_symbol, [
            {"date": "2026-06-03", "open": 3020, "close": 3030, "high": 3040, "low": 3010, "volume": 500000},
        ])
        days_after = TradeCalendar.trading_days_from_local("2026-06-01", "2026-06-05", db_path=self.test_db_path)
        self.assertEqual(len(days_after), 3)
        self.assertNotEqual(version, TradeCalendar.calendar_version(days_after))

    def test_local_calendar_version_reports_coverage_and_unavailability(self):
        """`local_calendar_version` 以本地已同步区间派生日历版本，供运行元数据记录（§11.2/§11.7）。"""
        # 本地库无覆盖 → 日历不可用，调用方须失败关闭，不得把"本地无记录"当作休市
        missing = TradeCalendar.local_calendar_version(db_path=self.test_db_path.parent / "not_exists.db")
        self.assertFalse(missing["calendar_available"])
        self.assertIsNone(missing["calendar_version"])
        self.assertEqual(missing["trading_days"], 0)

        self.store.upsert_klines("sh000001", [
            {"date": "2026-06-01", "open": 3000, "close": 3010, "high": 3020, "low": 2990, "volume": 500000},
            {"date": "2026-06-02", "open": 3010, "close": 3020, "high": 3030, "low": 3000, "volume": 500000},
        ])
        meta = TradeCalendar.local_calendar_version(db_path=self.test_db_path)
        self.assertTrue(meta["calendar_available"])
        self.assertEqual(meta["coverage_start"], "2026-06-01")
        self.assertEqual(meta["coverage_end"], "2026-06-02")
        self.assertEqual(meta["trading_days"], 2)
        self.assertEqual(
            meta["calendar_version"],
            TradeCalendar.calendar_version(["2026-06-01", "2026-06-02"]),
        )

        # 回填任一交易日即产生新版本
        self.store.upsert_klines("sh000001", [
            {"date": "2026-06-03", "open": 3020, "close": 3030, "high": 3040, "low": 3010, "volume": 500000},
        ])
        self.assertNotEqual(meta["calendar_version"], TradeCalendar.local_calendar_version(db_path=self.test_db_path)["calendar_version"])

    def test_sqlite_handles_released_without_gc(self):
        """SQLite 连接须在方法返回时立即关闭，不得延迟到 GC（Windows 文件锁回归保护）。"""
        self.store.upsert_klines("sh600519", [
            {"date": "2026-06-01", "open": 1600, "close": 1620, "high": 1630, "low": 1590, "volume": 10000},
        ])
        self.store.get_klines("sh600519")
        self.store.get_dates_set("sh600519")
        self.store.get_sync_meta("sh600519")
        TradeCalendar.trading_days_from_local("2026-06-01", "2026-06-05", db_path=self.test_db_path)
        self.test_db_path.unlink()  # 句柄泄漏时在 Windows 上抛 PermissionError [WinError 32]

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
