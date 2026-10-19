# -*- coding: utf-8 -*-
"""
Technical Indicators Regression Test Suite:
Validates:
- calc_all (MA, MACD, KDJ, RSI, BOLL, ATR)
- second_golden_cross rating and checklists
- gap_analysis (upward/downward gap detection and fill direction)
- ma & rsi short series safety guards
"""

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.indicators.technical_indicators import (
    calc_all,
    second_golden_cross,
    gap_analysis,
    ma,
    rsi,
)


def _gen_mock_klines(count=60, base_price=10.0):
    klines = []
    price = base_price
    for i in range(count):
        d = f"2026-01-{i+1:02d}" if i < 30 else f"2026-02-{i-29:02d}"
        op = price
        cl = price + (0.1 if i % 2 == 0 else -0.08)
        hi = max(op, cl) + 0.05
        lo = min(op, cl) - 0.05
        vol = 10000 + i * 100
        klines.append([d, op, cl, hi, lo, vol])
        price = cl
    return klines


class TestIndicators(unittest.TestCase):

    def setUp(self):
        self.klines = _gen_mock_klines(60, 10.0)

    def test_calc_all(self):
        tech = calc_all(self.klines)
        self.assertIn("ma", tech)
        self.assertIn("macd", tech)
        self.assertIn("kdj", tech)
        self.assertIn("rsi", tech)
        self.assertIn("boll", tech)
        self.assertIn("atr", tech)
        self.assertIn("latest", tech)

    def test_golden_cross(self):
        golden = second_golden_cross(self.klines)
        self.assertIn("verdict", golden)
        self.assertIn("checklist", golden)
        self.assertIn(golden["verdict"], ("A", "B", "C", "D"))

    def test_gap_analysis_and_fill(self):
        """Verify gap_analysis detects gaps and checks fill direction correctly."""
        base_klines = [
            [f"2026-08-0{i+1}", "10.0", "10.0", "10.5", "9.8", "1000"]
            for i in range(4)
        ]

        # Case A: Downward gap, not filled
        # Yesterday close: 10.0. Today: open 9.0, high 9.5 (< 10.0) -> unfilled
        klines_unfilled = base_klines + [
            ["2026-08-05", "9.0", "9.2", "9.5", "8.9", "1000"]
        ]
        res_unfilled = gap_analysis(klines_unfilled)
        self.assertGreaterEqual(len(res_unfilled["gaps"]), 1)
        last_gap = res_unfilled["gaps"][-1]
        self.assertEqual(last_gap["direction"], "down")
        self.assertFalse(last_gap["filled"])

        # Case B: Downward gap filled
        # Today high = 10.2 (>= 10.0) -> filled
        klines_filled = base_klines + [
            ["2026-08-05", "9.0", "9.8", "10.2", "8.9", "1000"]
        ]
        res_filled = gap_analysis(klines_filled)
        self.assertGreaterEqual(len(res_filled["gaps"]), 1)
        self.assertTrue(res_filled["gaps"][-1]["filled"])

    def test_ma_rsi_short_series_guards(self):
        """Verify ma and rsi handle short series safely without exceptions."""
        self.assertEqual(ma([10.0, 11.0], 5), [0.0, 0.0])
        self.assertEqual(len(rsi([10.0, 11.0], 14)), 2)

    def test_evidence_envelope_structure_and_defaults(self):
        """Verify build_evidence_meta produces full standard envelope conforming to C2."""
        from core.data.evidence import build_evidence_meta, EvidenceEnvelope, FEE_RULE_SSOT_DEFAULT

        meta = build_evidence_meta(quote_source="L1:tencent_realtime", kline_bars_count=120)
        self.assertIn("as_of_trading_day", meta)
        self.assertEqual(meta["quote_source"], "L1:tencent_realtime")
        self.assertEqual(meta["kline_bars_count"], 120)
        self.assertTrue(meta["watermark_ready"])
        self.assertEqual(meta["fee_rule_ssot"], FEE_RULE_SSOT_DEFAULT)
        self.assertEqual(meta["fee_rule_ssot"], "stamp_0.0005_comm_0.00025_min5_ceil")

        env = EvidenceEnvelope(
            as_of_trading_day="2026-10-19",
            quote_source="L1:tencent_realtime",
            kline_bars_count=250,
            watermark_ready=True,
            fee_rule_ssot=FEE_RULE_SSOT_DEFAULT,
        )
        self.assertEqual(env.to_dict()["fee_rule_ssot"], "stamp_0.0005_comm_0.00025_min5_ceil")

    def test_sync_astock_strategy_macd_second_golden_cross_integration(self):
        """Verify _sync_astock_strategy_macd integrates second_golden_cross and fail-closed guard (G2)."""
        from unittest.mock import patch
        from core.data.data_bridge import DataBridge
        from core.execution.tools import _sync_astock_strategy_macd

        # 1. Fail-closed: K-lines < 60
        with patch.object(DataBridge, "tencent_kline", return_value=self.klines[:30]):
            res_fail = _sync_astock_strategy_macd("600519")
            self.assertEqual(res_fail.get("status"), "error")
            self.assertEqual(res_fail.get("error"), "DATA_UNAVAILABLE")
            self.assertIn("evidence_meta", res_fail)
            self.assertFalse(res_fail["evidence_meta"]["watermark_ready"])

        # 2. Success: full second_golden_cross calculation with evidence_meta
        with patch.object(DataBridge, "tencent_kline", return_value=self.klines):
            res_succ = _sync_astock_strategy_macd("600519")
            self.assertEqual(res_succ.get("status"), "success")
            self.assertIn("verdict", res_succ)
            self.assertIn("macd_analysis", res_succ)
            self.assertIn("pattern", res_succ)
            self.assertIn("evidence_meta", res_succ)
            self.assertEqual(res_succ["evidence_meta"]["kline_bars_count"], 60)

    def test_sync_astock_meta_routing_dynamic_intent(self):
        """Verify _sync_astock_meta_routing dynamically routes queries via IntentEvaluator (G4)."""
        from core.execution.tools import _sync_astock_meta_routing

        # 1. 选股意图
        res_pick = _sync_astock_meta_routing("帮我推荐几只主线突破龙头的股票")
        self.assertEqual(res_pick.get("status"), "success")
        self.assertEqual(res_pick.get("primary_intent"), "STOCK_PICKING")
        self.assertEqual(res_pick.get("target_skill"), "astock-smart-screener")
        self.assertIn("evidence_meta", res_pick)

        # 2. 解套意图
        res_trap = _sync_astock_meta_routing("深套亏损30%如何自救补仓解套")
        self.assertEqual(res_trap.get("primary_intent"), "TRAPPED_RECOVERY")
        self.assertEqual(res_trap.get("target_skill"), "astock-deep-diagnose")
        self.assertEqual(res_trap.get("recommended_model"), "pro")

        # 3. 下跌应对意图
        res_down = _sync_astock_meta_routing("大盘跳水闪崩大跌要不要割肉")
        self.assertEqual(res_down.get("primary_intent"), "DOWNSIDE_REACTION")
        self.assertEqual(res_down.get("target_skill"), "astock-tactical-signals")


if __name__ == "__main__":
    unittest.main()

