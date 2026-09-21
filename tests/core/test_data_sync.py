# -*- coding: utf-8 -*-
"""
Unit tests for A-Stock Data Sync Engine & SQLite Store
"""
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))

from core.data.data_bridge import DataBridge
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

    def test_trading_day_and_holiday_rules(self):
        # 周末休市
        self.assertFalse(TradeCalendar.is_trading_day("2026-06-06"))  # 周六
        self.assertFalse(TradeCalendar.is_trading_day("2026-06-07"))  # 周日
        # 法定节假日休市
        self.assertFalse(TradeCalendar.is_trading_day("2026-10-01"))  # 国庆节
        self.assertFalse(TradeCalendar.is_trading_day("2026-01-01"))  # 元旦
        # 正常交易日
        self.assertTrue(TradeCalendar.is_trading_day("2026-06-01"))   # 周一

    def test_calendar_derived_from_local_klines_with_content_version(self):
        """交易日历以本地 daily_kline 实际交易日推导，并派生内容版本号（规范 §11.2）。"""
        ref_symbol = "sh000001"
        self.store.upsert_klines(ref_symbol, [
            {"date": "2026-06-01", "open": 3000, "close": 3010, "high": 3020, "low": 2990, "volume": 500000},
            {"date": "2026-06-02", "open": 3010, "close": 3020, "high": 3030, "low": 3000, "volume": 500000},
        ])

        days = TradeCalendar.trading_days_from_local("2026-06-01", "2026-06-05", db_path=self.test_db_path)
        self.assertEqual(days, ["2026-06-01", "2026-06-02"])

        # 目标区间超出本地已同步覆盖 → 空集合，调用方须按'日历不可用'失败关闭
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

        self.store.upsert_klines("sh000001", [
            {"date": "2026-06-03", "open": 3020, "close": 3030, "high": 3040, "low": 3010, "volume": 500000},
        ])
        self.assertNotEqual(meta["calendar_version"], TradeCalendar.local_calendar_version(db_path=self.test_db_path)["calendar_version"])

    def test_sqlite_wal_mode_enabled(self):
        """验证 SQLite WAL 并发读写模式是否已成功开启"""
        conn = sqlite3.connect(str(self.test_db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal")

    def test_sqlite_handles_released_without_gc(self):
        """SQLite 连接须在方法返回时立即关闭，不得延迟到 GC（Windows 文件锁回归保护）。"""
        self.store.upsert_klines("sh600519", [
            {"date": "2026-06-01", "open": 1600, "close": 1620, "high": 1630, "low": 1590, "volume": 10000},
        ])
        self.store.get_klines("sh600519")
        self.store.get_dates_set("sh600519")
        self.store.get_sync_meta("sh600519")
        TradeCalendar.trading_days_from_local("2026-06-01", "2026-06-05", db_path=self.test_db_path)
        self.test_db_path.unlink()

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

    def test_zero_fake_data_policy(self):
        """【零虚假数据原则】：断网或上游无数据时，严禁合成伪造数据，返回空列表或失败"""
        test_code = "sz000999_zero_fake_test"
        # 模拟外部远程数据源不可用
        with patch.object(DataBridge, "fetch_remote_kline_strictly", return_value=[]):
            res = self.engine.sync_symbol(test_code)
            self.assertEqual(res["status"], "failed")
            self.assertEqual(res["synced_count"], 0)
            self.assertIn("未能从外部数据源获取真实K线", res["error"])
            # 库内必须 0 行，绝不写入任何假数据
            self.assertEqual(len(self.store.get_klines(test_code)), 0)

            # 当所有外部数据源均断网且本地无数据时，DataBridge.get_kline_robust 绝不得伪造合成假数据
            with patch.object(DataBridge, "tencent_kline", return_value=[]), \
                 patch.object(DataBridge, "sina_kline", return_value=[]):
                # 清除内存缓存以模拟全新网络请求
                DataBridge._KLINE_CACHE.clear()
                robust_res = DataBridge.get_kline_robust(test_code, count=30)
                self.assertEqual(robust_res, [])

    def test_realtime_sync_marking_and_post_settlement_transition(self):
        """实时同步精细状态标记（如午间或盘中评估）与盘后定盘跃迁测试"""
        symbol = "sh600519"
        mock_midday_phase = {
            "phase": "LUNCH_BREAK",
            "phase_label": "午间休市(午后策略评估窗口)",
            "is_trading_day": True,
            "is_market_open": False,
            "is_settled": False,
            "time_str": "11:45:00",
            "date_str": "2026-06-01",
        }
        mock_midday_kline = [
            ["2026-06-01", "1600.0", "1620.0", "1630.0", "1590.0", "10000", "16200.0"]
        ]

        # 1. 模拟午间休市时发起实时同步
        with patch.object(TradeCalendar, "get_market_phase", return_value=mock_midday_phase):
            with patch.object(DataBridge, "fetch_remote_kline_strictly", return_value=mock_midday_kline):
                res = self.engine.sync_symbol(symbol, mode="incremental")
                self.assertEqual(res["status"], "success")
                self.assertFalse(res["is_settled"])
                self.assertEqual(res["sync_phase"], "LUNCH_BREAK")
                self.assertEqual(res["snapshot_time"], "11:45:00")

                # 校验库内元数据标记
                meta = self.store.get_sync_meta(symbol)
                self.assertIsNotNone(meta)
                self.assertEqual(meta["is_settled"], 0)
                self.assertEqual(meta["sync_phase"], "LUNCH_BREAK")
                self.assertEqual(meta["snapshot_time"], "11:45:00")

        # 2. 模拟盘后 15:35 定盘再次触发增量同步
        mock_settled_phase = {
            "phase": "SETTLED",
            "phase_label": "盘后定盘完成",
            "is_trading_day": True,
            "is_market_open": False,
            "is_settled": True,
            "time_str": "15:40:00",
            "date_str": "2026-06-01",
        }
        mock_settled_kline = [
            ["2026-06-01", "1600.0", "1635.0", "1640.0", "1590.0", "22000", "35800.0"]
        ]

        with patch.object(TradeCalendar, "get_market_phase", return_value=mock_settled_phase):
            with patch.object(DataBridge, "fetch_remote_kline_strictly", return_value=mock_settled_kline):
                # 因为此前是未定盘状态 (is_settled=0)，本次必须覆盖刷新，绝不能跳过
                res2 = self.engine.sync_symbol(symbol, mode="incremental")
                self.assertEqual(res2["status"], "success")
                self.assertTrue(res2["is_settled"])
                self.assertEqual(res2["sync_phase"], "SETTLED")

                # 校验收盘价已被定盘数据更新为 1635.0
                klines = self.store.get_klines(symbol)
                self.assertEqual(len(klines), 1)
                self.assertEqual(klines[0]["close"], 1635.0)
                self.assertEqual(klines[0]["is_settled"], 1)

                meta2 = self.store.get_sync_meta(symbol)
                self.assertEqual(meta2["is_settled"], 1)
                self.assertEqual(meta2["sync_phase"], "SETTLED")

                # 3. 再次增量同步，此时由于已经定盘，应当安全跳过 (up_to_date)
                res3 = self.engine.sync_symbol(symbol, mode="incremental")
                self.assertEqual(res3["status"], "up_to_date")
                self.assertEqual(res3["synced_count"], 0)

    def test_sync_today_snapshot_weekend_guard(self):
        """非交易日（周末/法定节假日）拒绝写入当日快照脏数据"""
        mock_weekend_phase = {
            "phase": "WEEKEND",
            "phase_label": "周末休市",
            "is_trading_day": False,
            "is_market_open": False,
            "is_settled": True,
            "time_str": "10:00:00",
            "date_str": "2026-06-06",
        }
        with patch.object(TradeCalendar, "get_market_phase", return_value=mock_weekend_phase):
            res = self.engine.sync_today_snapshot(["sh600519"])
            self.assertEqual(res["status"], "skipped")
            self.assertIn("非交易日", res["message"])
            self.assertEqual(len(self.store.get_klines("sh600519")), 0)

    def test_amount_precision_from_turnover(self):
        """腾讯接口第6项真实成交额万元解析精度验证"""
        mock_kline = [
            ["2026-06-01", "10.0", "10.5", "10.8", "9.9", "1000", "520.5"]
        ]
        with patch.object(DataBridge, "fetch_remote_kline_strictly", return_value=mock_kline):
            res = self.engine.fetch_remote_klines("sz000001")
            self.assertEqual(len(res), 1)
            # 520.5 万元 * 10000 = 5205000.0 元
            self.assertEqual(res[0]["amount"], 5205000.0)

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


    def test_concurrent_batch_sync(self):
        """测试多线程并发批量同步及顺序保序性"""
        symbols = ["sh600519", "sz000001", "sz000002", "sh600036"]
        mock_kline = [
            ["2026-06-01", "10.0", "10.5", "10.8", "9.9", "1000", "520.5"]
        ]
        with patch.object(DataBridge, "fetch_remote_kline_strictly", return_value=mock_kline):
            res = self.engine.sync_batch(symbols, mode="full", count=10, max_workers=4)
            self.assertEqual(res["total_requested"], 4)
            self.assertEqual(res["success_count"], 4)
            self.assertEqual(res["workers"], 4)
            # 保证返回结果顺序与输入完全一致
            for i, sym in enumerate(symbols):
                self.assertEqual(res["details"][i]["symbol"], DataBridge.normalize_symbol(sym, with_prefix=True))

    def test_suspension_detection_and_repair(self):
        """测试停牌标的智能识别与完整性状态自愈"""
        ref_symbol = "sh000001"
        ref_data = [
            {"date": "2026-06-01", "open": 3000, "close": 3010, "high": 3020, "low": 2990, "volume": 500000},
            {"date": "2026-06-02", "open": 3010, "close": 3020, "high": 3030, "low": 3000, "volume": 500000},
            {"date": "2026-06-03", "open": 3020, "close": 3030, "high": 3040, "low": 3010, "volume": 500000},
        ]
        self.store.upsert_klines(ref_symbol, ref_data)

        # 某股票在 2026-06-02 合规停牌
        susp_symbol = "sz000008"
        actual_klines = [
            {"date": "2026-06-01", "open": 10, "close": 10.2, "high": 10.3, "low": 9.9, "volume": 10000},
            {"date": "2026-06-03", "open": 10.2, "close": 10.5, "high": 10.6, "low": 10.1, "volume": 12000},
        ]
        self.store.upsert_klines(susp_symbol, actual_klines)

        # 初次稽核标记为 degraded
        audits = self.engine.audit_integrity([susp_symbol])
        self.assertEqual(audits[0]["status"], "degraded")
        self.assertEqual(audits[0]["missing_count"], 1)

        # 远程真实数据本身亦无 2026-06-02 数据（确认为合规停牌）
        remote_susp_klines = [
            ["2026-06-01", "10", "10.2", "10.3", "9.9", "10000"],
            ["2026-06-03", "10.2", "10.5", "10.6", "10.1", "12000"],
        ]
        with patch.object(DataBridge, "fetch_remote_kline_strictly", return_value=remote_susp_klines):
            repair_res = self.engine.repair_gaps([susp_symbol])
            self.assertTrue(repair_res[0]["repaired"])
            self.assertIn("合规停牌", repair_res[0]["message"])

        # 再次稽核，应自动识别已知合规停牌，状态评级恢复为 healthy
        re_audits = self.engine.audit_integrity([susp_symbol])
        self.assertEqual(re_audits[0]["status"], "healthy")
        self.assertEqual(re_audits[0]["suspended_count"], 1)
        self.assertIn("2026-06-02", re_audits[0]["suspended_days"])
        self.assertIn("合规停牌", re_audits[0]["message"])

    def test_dynamic_calendar_extension(self):
        """测试基于本地历史数据库的交易日历动态真值延伸"""
        mock_future_day = "2029-03-05"  # 周一
        ref_symbol = "sh000001"
        self.store.upsert_klines(ref_symbol, [{
            "date": mock_future_day, "open": 3500, "close": 3520, "high": 3530, "low": 3490, "volume": 100000
        }])

        is_td = TradeCalendar.is_trading_day_dynamic(mock_future_day, db_path=self.test_db_path)
        self.assertTrue(is_td)
        self.assertFalse(TradeCalendar.is_trading_day_dynamic("2029-03-04", db_path=self.test_db_path))

    def test_sync_daemon_workflow(self):
        """测试数据同步守护进程的时钟状态触发"""
        from core.data.sync_daemon import DataSyncDaemon
        daemon = DataSyncDaemon(pools=["holdings"], check_interval=10, max_workers=2)

        # 1. 非交易日：跳过
        mock_weekend = {
            "phase": "WEEKEND", "phase_label": "周末休市",
            "is_trading_day": False, "is_market_open": False,
            "is_settled": True, "time_str": "15:40:00", "date_str": "2026-06-06"
        }
        with patch.object(TradeCalendar, "get_market_phase", return_value=mock_weekend):
            res_weekend = daemon.run_once()
            self.assertEqual(res_weekend["status"], "skipped")
            self.assertEqual(res_weekend["reason"], "non_trading_day")

        # 2. 盘中未到定盘时间 (例如 10:30)：等待
        mock_intraday = {
            "phase": "CONTINUOUS_TRADING", "phase_label": "早盘连续竞价",
            "is_trading_day": True, "is_market_open": True,
            "is_settled": False, "time_str": "10:30:00", "date_str": "2026-06-01"
        }
        with patch.object(TradeCalendar, "get_market_phase", return_value=mock_intraday),              patch("core.data.sync_daemon.datetime") as mock_dt:
            from datetime import datetime as real_dt
            mock_dt.now.return_value = real_dt(2026, 6, 1, 10, 30, 0)
            res_waiting = daemon.run_once()
            self.assertEqual(res_waiting["status"], "waiting")
            self.assertEqual(res_waiting["reason"], "before_settlement_window")


if __name__ == "__main__":
    unittest.main()
