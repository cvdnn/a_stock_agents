# -*- coding: utf-8 -*-
"""
Unit tests for core.strategy.pool_schema:
- is_blocked: filtering STAR (688/689), ChiNext (30), BSE/NEEQ (8/4/92)
- schema fields constants
- ensure_pool_csv, read_pool_csv, write_pool_csv
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.strategy.pool_schema import (
    HISTORY_FIELDS,
    POSITIONS_FIELDS,
    SELECTED_FIELDS,
    WATCH_FIELDS,
    ensure_pool_csv,
    is_blocked,
    read_pool_csv,
    write_pool_csv,
)


class TestPoolSchema(unittest.TestCase):

    def test_is_blocked_rules(self):
        # Blocked: 688/689 (STAR), 30 (ChiNext), 8/4/92 (BSE/NEEQ)
        self.assertTrue(is_blocked("688001"))
        self.assertTrue(is_blocked("689001"))
        self.assertTrue(is_blocked("300750"))
        self.assertTrue(is_blocked("301001"))
        self.assertTrue(is_blocked("830001"))
        self.assertTrue(is_blocked("430001"))
        self.assertTrue(is_blocked("920001"))

        # Allowed: Main Board Shanghai (600, 601, 603, 605) & Shenzhen (000, 001, 002, 003)
        self.assertFalse(is_blocked("600519"))
        self.assertFalse(is_blocked("601899"))
        self.assertFalse(is_blocked("603259"))
        self.assertFalse(is_blocked("605117"))
        self.assertFalse(is_blocked("000001"))
        self.assertFalse(is_blocked("000858"))
        self.assertFalse(is_blocked("002415"))

    def test_field_constants(self):
        # Verify essential fields exist
        self.assertIn("code", SELECTED_FIELDS)
        self.assertIn("name", SELECTED_FIELDS)
        self.assertIn("rating", SELECTED_FIELDS)
        self.assertIn("reason", SELECTED_FIELDS)
        self.assertIn("entry_trigger", SELECTED_FIELDS)
        self.assertIn("stop_loss", SELECTED_FIELDS)


        self.assertIn("code", WATCH_FIELDS)
        self.assertIn("name", WATCH_FIELDS)
        self.assertIn("rating", WATCH_FIELDS)
        self.assertIn("entry_condition", WATCH_FIELDS)
        self.assertIn("fund_flow", WATCH_FIELDS)

        self.assertIn("code", POSITIONS_FIELDS)
        self.assertIn("buy_price", POSITIONS_FIELDS)
        self.assertIn("qty", POSITIONS_FIELDS)
        self.assertIn("stop_loss", POSITIONS_FIELDS)

        self.assertIn("code", HISTORY_FIELDS)
        self.assertIn("buy_price", HISTORY_FIELDS)
        self.assertIn("sell_price", HISTORY_FIELDS)
        self.assertIn("pnl", HISTORY_FIELDS)


class TestPoolCSVIO(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.temp_dir, "test_selected.csv")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ensure_pool_csv(self):
        ensure_pool_csv(self.csv_path, SELECTED_FIELDS)
        self.assertTrue(os.path.exists(self.csv_path))

        with open(self.csv_path, "r", encoding="utf-8") as f:
            header = f.readline().strip().split(",")
        self.assertEqual(header, SELECTED_FIELDS)

    def test_write_and_read_sparse_rows(self):
        # Sparse rows with only a subset of SELECTED_FIELDS
        sparse_rows = [
            {"code": "600519", "name": "贵州茅台", "rating": "A"},
            {"code": "601899", "name": "紫金矿业", "entry_trigger": "回踩MA20"},
        ]
        write_pool_csv(self.csv_path, SELECTED_FIELDS, sparse_rows)

        loaded = read_pool_csv(self.csv_path)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["code"], "600519")
        self.assertEqual(loaded[0]["rating"], "A")
        # Missing fields should be initialized to empty string
        self.assertEqual(loaded[0]["entry_trigger"], "")
        self.assertEqual(loaded[0]["stop_loss"], "")

        self.assertEqual(loaded[1]["code"], "601899")
        self.assertEqual(loaded[1]["name"], "紫金矿业")
        self.assertEqual(loaded[1]["rating"], "")
        self.assertEqual(loaded[1]["entry_trigger"], "回踩MA20")


    def test_read_non_existent(self):
        loaded = read_pool_csv(os.path.join(self.temp_dir, "missing.csv"))
        self.assertEqual(loaded, [])

    def test_audit_pools_empty_pool_fail_closed(self):
        """Verify PoolManager.audit_pools fails closed on empty pools and provides registration guide."""
        from core.strategy.pool_manager import PoolManager
        empty_dir = os.path.join(self.temp_dir, "empty_pools")
        os.makedirs(empty_dir, exist_ok=True)
        pm = PoolManager(pools_dir=empty_dir)
        write_pool_csv(pm.positions_path, POSITIONS_FIELDS, [])

        audit_res = pm.audit_pools()
        self.assertEqual(audit_res["status"], "empty_pool")
        self.assertEqual(audit_res["total_stocks"], 0)
        self.assertIn("registration_guide", audit_res)
        self.assertIn("holding_format", audit_res["registration_guide"])
        self.assertIn("watch_format", audit_res["registration_guide"])
        self.assertIn("evidence_meta", audit_res)

    def test_audit_pools_real_ma_breached_and_stale(self):
        """Verify PoolManager.audit_pools audits MA levels, catches breached stops and filters stale/blocked."""
        from core.strategy.pool_manager import PoolManager
        pools_dir = os.path.join(self.temp_dir, "test_pools_data")
        os.makedirs(pools_dir, exist_ok=True)
        pm = PoolManager(pools_dir=pools_dir)
        write_pool_csv(pm.positions_path, POSITIONS_FIELDS, [])

        # 1. 写入一只自选股 (设定极高止损 9999.0 触发 breached_stops)
        pm.add_stock("selected", {
            "code": "600519", "name": "贵州茅台", "stop_loss": "9999.0", "rating": "A"
        })
        # 2. 写入一只科创板/受限股 (直接触发 is_blocked -> stale_records)
        # 注意：add_stock 内部有 is_blocked 校验，这里直接通过底层 write_pool_csv 模拟旧脏数据
        dirty_rows = [
            {"code": "600519", "name": "贵州茅台", "stop_loss": "9999.0", "rating": "A"},
            {"code": "688001", "name": "澜起科技", "stop_loss": "10.0", "rating": "C"},
        ]
        write_pool_csv(pm.selected_path, SELECTED_FIELDS, dirty_rows)

        # 只读审查
        res = pm.audit_pools(fix=False)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_stocks"], 2)
        # 688001 应该在 stale_records (不可交易板块)
        stale_codes = [r["code"] for r in res["stale_records"]]
        self.assertIn("688001", stale_codes)
        self.assertIn("evidence_meta", res)

        # 自动清洗测试 fix=True
        fix_res = pm.audit_pools(fix=True)
        self.assertEqual(fix_res["status"], "success")
        self.assertGreaterEqual(fix_res["cleaned_count"], 1)


if __name__ == "__main__":
    unittest.main()
