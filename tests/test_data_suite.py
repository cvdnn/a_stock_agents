# -*- coding: utf-8 -*-
"""
Data & Infrastructure Regression Test Suite:
Validates:
- QuoteDict (code-primary key, alias lookup, name collision immunity)
- _validate_stock_code command injection defense
- core.config SSOT: VERSION (3.0.0), fee constants, prefix inference, normalize_symbol
- core.data.data_layer: clean_kline_df and forwarder SSOT
- core.data.fetch_realtime: Tencent quote parsing for SH/SZ/BJ prefixes
- core.data.fetch_history_fallback: EM_PERFORMANCE_URL definition
- DataBridge: index_snapshot invocation & lazy third-party import safety
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.config import (
    VERSION,
    DEFAULT_BENCHMARK,
    DEFAULT_COMMISSION_RATE,
    DEFAULT_TAX_RATE_SELL,
    DEFAULT_TRANSFER_FEE_RATE,
    DEFAULT_MIN_COMMISSION,
    DEFAULT_RATING_THRESHOLDS,
    DEFAULT_STOP_LOSS_PCT,
    MARKET_PREFIX_SH,
    MARKET_PREFIX_SZ,
    MARKET_PREFIX_BJ,
    infer_market_prefix,
    normalize_symbol,
    get_logger,
)
from core.data.data_bridge import (
    QuoteDict,
    _validate_stock_code,
    DataBridge,
)
from core.data.data_layer import clean_kline_df
from core.data.fetch_realtime import _parse_tencent_quote


class TestDataSuite(unittest.TestCase):

    def test_version_and_config_ssot(self):
        """Verify unified version 3.0.0 and financial fee constants."""
        self.assertEqual(VERSION, "3.0.0")
        self.assertEqual(DEFAULT_BENCHMARK, "sh000001")
        self.assertAlmostEqual(DEFAULT_TAX_RATE_SELL, 0.0005)
        self.assertAlmostEqual(DEFAULT_COMMISSION_RATE, 0.00025)
        self.assertAlmostEqual(DEFAULT_TRANSFER_FEE_RATE, 0.00001)
        self.assertAlmostEqual(DEFAULT_MIN_COMMISSION, 5.0)
        self.assertEqual(DEFAULT_RATING_THRESHOLDS["A"], 80.0)
        self.assertAlmostEqual(DEFAULT_STOP_LOSS_PCT, 0.05)

        logger = get_logger("test.data")
        self.assertIsNotNone(logger)

    def test_market_prefix_inference_and_normalization(self):
        """Verify market prefix inference and symbol normalization for SH/SZ/BJ."""
        # Shanghai
        self.assertEqual(infer_market_prefix("600519"), MARKET_PREFIX_SH)
        self.assertEqual(infer_market_prefix("688001"), MARKET_PREFIX_SH)
        self.assertEqual(infer_market_prefix("900901"), MARKET_PREFIX_SH)
        self.assertEqual(infer_market_prefix("sh600519"), MARKET_PREFIX_SH)
        self.assertEqual(infer_market_prefix("600519.SH"), MARKET_PREFIX_SH)
        self.assertEqual(normalize_symbol("600519", with_prefix=True), "sh600519")
        self.assertEqual(normalize_symbol("sh600519", with_prefix=False), "600519")

        # Shenzhen
        self.assertEqual(infer_market_prefix("000001"), MARKET_PREFIX_SZ)
        self.assertEqual(infer_market_prefix("002415"), MARKET_PREFIX_SZ)
        self.assertEqual(infer_market_prefix("300750"), MARKET_PREFIX_SZ)
        self.assertEqual(infer_market_prefix("sz000002"), MARKET_PREFIX_SZ)
        self.assertEqual(infer_market_prefix("000001.SZ"), MARKET_PREFIX_SZ)
        self.assertEqual(normalize_symbol("000001", with_prefix=True), "sz000001")
        self.assertEqual(normalize_symbol("sz000001", with_prefix=False), "000001")

        # Beijing
        self.assertEqual(infer_market_prefix("830001"), MARKET_PREFIX_BJ)
        self.assertEqual(infer_market_prefix("430001"), MARKET_PREFIX_BJ)
        self.assertEqual(infer_market_prefix("920001"), MARKET_PREFIX_BJ)
        self.assertEqual(infer_market_prefix("bj830001"), MARKET_PREFIX_BJ)
        self.assertEqual(normalize_symbol("830001", with_prefix=True), "bj830001")
        self.assertEqual(normalize_symbol("bj830001", with_prefix=False), "830001")

    def test_validate_stock_code_injection_defense(self):
        """Verify _validate_stock_code allows valid codes and rejects malicious inputs."""
        # Valid codes
        self.assertEqual(_validate_stock_code("600519"), "600519")
        self.assertEqual(_validate_stock_code("sh600519"), "sh600519")
        self.assertEqual(_validate_stock_code("000001"), "000001")
        self.assertEqual(_validate_stock_code("sz000001"), "sz000001")
        self.assertEqual(_validate_stock_code("830001"), "830001")
        self.assertEqual(_validate_stock_code("bj830001"), "bj830001")
        self.assertEqual(_validate_stock_code("920002"), "920002")

        # Injections or invalid codes
        with self.assertRaises(ValueError):
            _validate_stock_code("600519; rm -rf /")

        with self.assertRaises(ValueError):
            _validate_stock_code("import os; os.system('ls')")

        with self.assertRaises(ValueError):
            _validate_stock_code("600519' OR '1'='1")

        with self.assertRaises(ValueError):
            _validate_stock_code("")

    def test_quote_dict_multi_alias_and_collision_immunity(self):
        """Verify QuoteDict keys by stock code and supports multi-alias lookup without collision."""
        qd = QuoteDict()
        qd.add({"code": "sh600519", "name": "贵州茅台", "price": 1800.0})
        qd.add({"code": "sz000001", "name": "平安银行", "price": 12.5})

        # Lookup by pure code
        self.assertEqual(qd["600519"]["name"], "贵州茅台")
        self.assertEqual(qd["000001"]["name"], "平安银行")

        # Lookup by prefixed code
        self.assertEqual(qd["sh600519"]["price"], 1800.0)
        self.assertEqual(qd["sz000001"]["price"], 12.5)

        # Lookup by Chinese stock name
        self.assertEqual(qd["贵州茅台"]["price"], 1800.0)
        self.assertEqual(qd["平安银行"]["price"], 12.5)

        # Membership
        self.assertIn("600519", qd)
        self.assertIn("贵州茅台", qd)
        self.assertNotIn("999999", qd)

        # Non-existent key
        self.assertIsNone(qd.get("non_existent"))

        # Collision prevention: Multiple stocks
        qd.add({"code": "sh600000", "name": "浦发银行", "price": 8.5})
        self.assertEqual(len(list(qd.values())), 3)

    def test_parse_tencent_quote_prefixes(self):
        """Verify _parse_tencent_quote accurately parses SH/SZ/BJ market prefixes."""
        def make_quote_line(prefix_var: str, name: str, code: str) -> str:
            parts = [""] * 55
            parts[0] = f'{prefix_var}="1'
            parts[1] = name
            parts[2] = code
            parts[3] = "10.50"
            parts[4] = "10.00"
            parts[5] = "10.10"
            parts[6] = "10000"
            parts[30] = "2026-09-04 15:00:00"
            parts[33] = "10.60"
            parts[34] = "9.90"
            parts[37] = "10500"
            parts[38] = "1.20"
            return "~".join(parts)

        # 600xxx should be sh
        res_sh = _parse_tencent_quote(make_quote_line("v_sh600000", "浦发银行", "600000"))
        self.assertIsNotNone(res_sh)
        self.assertEqual(res_sh["code"], "sh600000")

        # 688xxx should be sh
        res_star = _parse_tencent_quote(make_quote_line("v_sh688001", "澜起科技", "688001"))
        self.assertIsNotNone(res_star)
        self.assertEqual(res_star["code"], "sh688001")

        # 000xxx should be sz
        res_sz = _parse_tencent_quote(make_quote_line("v_sz000001", "平安银行", "000001"))
        self.assertIsNotNone(res_sz)
        self.assertEqual(res_sz["code"], "sz000001")

        # 83xxxx should be bj
        res_bj = _parse_tencent_quote(make_quote_line("v_bj830001", "测试北交", "830001"))
        self.assertIsNotNone(res_bj)
        self.assertEqual(res_bj["code"], "bj830001")

    def test_fetch_history_fallback_constants(self):
        """Verify fetch_history_fallback defines EM_PERFORMANCE_URL without NameError."""
        import core.data.fetch_history_fallback as fh
        self.assertTrue(hasattr(fh, "EM_PERFORMANCE_URL"))
        self.assertIn("eastmoney.com", fh.EM_PERFORMANCE_URL)

    def test_clean_kline_df(self):
        """Verify DataLayer clean_kline_df sanitizes column names and formats."""
        # Empty df
        empty_res = clean_kline_df(pd.DataFrame())
        self.assertTrue(empty_res.empty)

        # Raw dataframe with Chinese column names
        dates = pd.date_range("2026-01-01", periods=5, freq="D")
        raw = pd.DataFrame({
            "日期": dates.strftime("%Y-%m-%d"),
            "开盘": [10.0, 10.5, 10.2, 10.8, 11.0],
            "最高": [10.6, 10.7, 10.9, 11.2, 11.5],
            "最低": [9.9, 10.1, 10.0, 10.5, 10.8],
            "收盘": [10.5, 10.2, 10.8, 11.0, 11.2],
            "成交量": [10000, 12000, 15000, 11000, 13000],
            "成交额": [100000, 125000, 160000, 120000, 140000],
        })

        cleaned = clean_kline_df(raw)
        self.assertFalse(cleaned.empty)
        for col in ["date", "open", "high", "low", "close", "volume", "amount"]:
            self.assertIn(col, cleaned.columns)
        self.assertEqual(len(cleaned), 5)

    def test_data_bridge_index_snapshot_dispatch(self):
        """Verify DataBridge index_snapshot is accessible without AttributeError."""
        from core.data.data_bridge import index_snapshot, DataBridge
        with patch.object(DataBridge, "tencent_index") as mock_index:
            mock_index.return_value = {
                "sh": {"name": "上证指数", "price": 3100.0, "change_pct": 0.5},
                "sz": {"name": "深证成指", "price": 10500.0, "change_pct": 0.8},
                "cy": {"name": "创业板指", "price": 2100.0, "change_pct": 1.2},
            }
            res = index_snapshot()
            self.assertIn("sh", res)
            self.assertIn("sz", res)
            self.assertIn("cy", res)
            self.assertEqual(res["sh"]["price"], 3100.0)

    def test_lazy_third_party_dependencies(self):
        """Verify data fetchers handle absence of akshare/efinance gracefully."""
        from core.data import fetch_realtime, fetch_ah_ipo_timeline, fetch_ah_stocks, fetch_stock_events
        self.assertTrue(hasattr(fetch_realtime, "ak"))
        self.assertTrue(hasattr(fetch_realtime, "ef"))
        self.assertTrue(hasattr(fetch_ah_ipo_timeline, "ak"))
        self.assertTrue(hasattr(fetch_ah_stocks, "ak"))
        self.assertTrue(hasattr(fetch_stock_events, "ak"))


if __name__ == "__main__":
    unittest.main()
