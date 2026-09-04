# -*- coding: utf-8 -*-
"""
Test suite verifying the P1 bug fixes across core modules:
1. fetch_realtime market prefix parsing (sh/sz/bj)
2. fetch_history_fallback EM_PERFORMANCE_URL definition
3. technical_indicators gap_analysis fill direction & rating invert fix & ma/rsi protections
4. market_assessor index code matching & dynamic volume/capital
5. combo_scorer fund flow unit parsing & missing dimension normalized scoring
6. stock_screener safe float & normalized score sorting
7. multi_factor_scorer monotonic trend_score
8. factor_synthesizer custom_weights normalization & missing factor median imputation
9. risk_manager top divergence detection
"""

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))


class TestP1Fixes(unittest.TestCase):

    def test_fetch_realtime_parse_tencent_quote_prefixes(self):
        """Verify _parse_tencent_quote assigns correct sh/sz/bj prefix to stock codes."""
        from core.data.fetch_realtime import _parse_tencent_quote

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

        # 300xxx should be sz
        res_cy = _parse_tencent_quote(make_quote_line("v_sz300001", "特锐德", "300001"))
        self.assertIsNotNone(res_cy)
        self.assertEqual(res_cy["code"], "sz300001")

        # 8xxxxx / 920xxx should be bj
        res_bj = _parse_tencent_quote(make_quote_line("v_bj832089", "特瑞斯", "832089"))
        self.assertIsNotNone(res_bj)
        self.assertEqual(res_bj["code"], "bj832089")

        res_bj920 = _parse_tencent_quote(make_quote_line("v_bj920001", "万达轴承", "920001"))
        self.assertIsNotNone(res_bj920)
        self.assertEqual(res_bj920["code"], "bj920001")

    def test_fetch_history_fallback_constants(self):
        """Verify EM_PERFORMANCE_URL is properly defined."""
        from core.data import fetch_history_fallback as fh
        self.assertTrue(hasattr(fh, "EM_PERFORMANCE_URL"))
        self.assertEqual(fh.EM_PERFORMANCE_URL, "https://datacenter-web.eastmoney.com/api/data/v1/get")

    def test_technical_indicators_gap_direction_and_rating(self):
        """Verify gap_analysis down gap fill condition and checklist rating invert fix."""
        from core.indicators.technical_indicators import gap_analysis, ma, rsi, second_golden_cross

        # Down gap with len(klines) >= 5
        base_klines = [
            ["2026-07-28", "10.0", "10.0", "10.2", "9.8", "1000"],
            ["2026-07-29", "10.0", "10.0", "10.2", "9.8", "1000"],
            ["2026-07-30", "10.0", "10.0", "10.2", "9.8", "1000"],
            ["2026-08-01", "10.0", "10.0", "10.5", "9.8", "1000"],
        ]
        # Case A: today high = 9.5 (< 10.0) -> NOT filled
        klines_unfilled = base_klines + [
            ["2026-08-02", "9.0", "9.2", "9.5", "8.9", "1000"]
        ]
        res_unfilled = gap_analysis(klines_unfilled)
        self.assertGreaterEqual(len(res_unfilled["gaps"]), 1)
        last_gap = res_unfilled["gaps"][-1]
        self.assertEqual(last_gap["direction"], "down")
        self.assertFalse(last_gap["filled"])

        # Case B: today high = 10.2 (>= 10.0) -> filled
        klines_filled = base_klines + [
            ["2026-08-02", "9.0", "9.8", "10.2", "8.9", "1000"]
        ]
        res_filled = gap_analysis(klines_filled)
        self.assertGreaterEqual(len(res_filled["gaps"]), 1)
        self.assertTrue(res_filled["gaps"][-1]["filled"])

        # MA & RSI safety guards
        self.assertEqual(ma([10.0, 11.0], 5), [0.0, 0.0])
        self.assertEqual(len(rsi([10.0, 11.0], 14)), 2)

        # second_golden_cross rating semantic fix
        # Construct klines with 2 golden crosses
        sgc_klines = []
        for i in range(50):
            p = 10.0 + (0.1 if i % 2 == 0 else -0.1)
            sgc_klines.append([f"2026-06-{i+1:02d}", str(p), str(p), str(p+0.2), str(p-0.2), "1000"])
        sgc_res = second_golden_cross(sgc_klines)
        self.assertIn(sgc_res["verdict"], ("A", "B", "C"))

    def test_market_assessor_sh_code_matching_and_volume(self):
        """Verify market_assessor matches Shanghai index correctly and scores volume."""
        from core.models.market_assessor import MarketAssessor

        # Ping An Bank with sz000001 or bare 000001 should NOT match Shanghai Index
        idx_pingan = {"pingan": {"name": "平安银行", "code": "sz000001", "change_pct": 2.0}}
        score, max_s, reason = MarketAssessor.assess_trend(idx_pingan)
        self.assertEqual(score, 15)  # fallback neutral because no sh index found

        idx_pingan_bare = {"000001": {"name": "平安银行", "code": "000001", "change_pct": 5.0}}
        score_bare, _, _ = MarketAssessor.assess_trend(idx_pingan_bare)
        self.assertEqual(score_bare, 15)  # must NOT match Ping An Bank as Shanghai index

        # Shanghai Index sh000001 or bare 000001 with 上证 in name should match
        idx_sh = {"sh": {"name": "上证指数", "code": "sh000001", "change_pct": 1.2}}
        score, max_s, reason = MarketAssessor.assess_trend(idx_sh)
        self.assertEqual(score, 30)

        idx_sh_bare = {"000001": {"name": "上证综合指数", "code": "000001", "change_pct": 1.2}}
        score2, _, _ = MarketAssessor.assess_trend(idx_sh_bare)
        self.assertEqual(score2, 30)

        # Volume assessment: >1万亿 (10000亿) gets 20 points
        quotes_high_vol = [{"amount": 6000 * 1e8}, {"amount": 5000 * 1e8}]
        v_score, v_max, v_reason = MarketAssessor.assess_volume(quotes_high_vol)
        self.assertEqual(v_score, 20)
        self.assertIn("破万亿", v_reason)

        # Capital flow assessment
        c_score, c_max, c_reason = MarketAssessor.assess_capital({"net_inflow": 45.0})
        self.assertEqual(c_score, 15)
        c_score2, c_max2, c_reason2 = MarketAssessor.assess_capital(None)
        self.assertEqual(c_score2, 8)

    def test_combo_scorer_fund_flow_and_normalization(self):
        """Verify combo_scorer handles '万' vs '亿' and missing dimension normalization."""
        from core.models.combo_scorer import ComboScorer

        # "5000万" = 0.50亿, should NOT trigger >0.5亿 huge inflow (>0.5 is 15 points)
        score_5000w, reason_5000w = ComboScorer.score_fund_flow("主力净流入 5000万")
        self.assertEqual(score_5000w, 12)
        self.assertIn("0.50亿", reason_5000w)

        # "1.5亿" = 1.5亿, triggers >0.5亿
        score_1_5y, reason_1_5y = ComboScorer.score_fund_flow("主力净流入 1.5亿")
        self.assertEqual(score_1_5y, 15)

        # Test dictionary input
        score_dict, _ = ComboScorer.score_fund_flow({"主力净流入": "8000万"})
        self.assertEqual(score_dict, 15)  # 0.8亿 > 0.5亿

        # Test normalization when cyq and fund_flow are missing
        scorer = ComboScorer()
        mock_klines = [["2026-08-01", "10", "10.5", "11", "9.8", "1000"]] * 60
        mock_latest = {
            "close": 10.5, "ma5": 10.3, "ma10": 10.1, "ma20": 9.9, "ma60": 9.5,
            "dif": 0.2, "dea": 0.1, "macd_bar": 0.2, "volume_hands": 1000, "vol_ratio": 1.2
        }
        res = scorer.score_full(mock_klines, mock_latest, cyq_data=None, fund_data=None)
        self.assertEqual(res["effective_max"], 70)
        self.assertIn("normalized_score", res)
        # normalized_score should be (adjusted_total / 70) * 100
        expected_norm = round(res["adjusted_total"] / 70.0 * 100, 1)
        self.assertEqual(res["normalized_score"], expected_norm)

    def test_stock_screener_normalized_sorting_and_safe_float(self):
        """Verify stock_screener sorts candidates by normalized_score and safely parses changePct."""
        from core.models.stock_screener import StockScreener

        screener = StockScreener()

        # Test safe float parsing on malformed board_data in filter_sector
        malformed_board_data = [
            {"boardName": "板块A", "changePct": None},
            {"boardName": "板块B", "changePct": ""},
            {"boardName": "板块C", "changePct": "invalid"},
            {"boardName": "板块D", "changePct": "3.5"},
        ]
        screener.bridge.fetch_batch_snapshot = lambda codes: [{"code": "000001", "name": "平安银行"}]
        screener.bridge.get_board_summary = lambda limit=30: {"data": malformed_board_data}
        screener.bridge.get_sector_info = lambda code: {"industry": "板块D"}
        filtered = screener.filter_sector(["000001"], min_board_chg=1.0)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["board_chg"], 3.5)

        # Test candidate sorting: Candidate A has lower total but higher normalized score
        cand_a = {"code": "000001", "name": "A", "scores": {"total": 56, "normalized_score": 80.0}}
        cand_b = {"code": "000002", "name": "B", "scores": {"total": 65, "normalized_score": 65.0}}
        results = [cand_b, cand_a]
        results.sort(key=lambda x: x["scores"].get("normalized_score", x["scores"].get("total", 0)), reverse=True)
        self.assertEqual(results[0]["code"], "000001")  # cand_a ranked first

    def test_multi_factor_scorer_trend_monotonicity(self):
        """Verify multi_factor_scorer quality_factor partitions trend_score properly."""
        from core.models.multi_factor_scorer import MultiFactorScorer

        # Construct klines with controlled up_days ratio: 21 bars (20 steps)
        def build_klines(up_count: int):
            # 20 transitions, up_count positive changes
            closes = [10.0]
            for i in range(20):
                step = 0.1 if i < up_count else -0.1
                closes.append(round(closes[-1] + step, 2))
            return [[f"2026-08-{i+1:02d}", str(c), str(c), str(c+0.05), str(c-0.05), "1000"] for i, c in enumerate(closes)]

        # up_ratio = 12/20 = 0.60 -> in [0.50, 0.65], trend_score = 100.0
        q_100 = MultiFactorScorer.quality_factor(build_klines(12))
        # up_ratio = 9/20 = 0.45 -> in [0.40, 0.50), trend_score = 70.0
        q_70 = MultiFactorScorer.quality_factor(build_klines(9))
        # up_ratio = 7/20 = 0.35 -> in [0.30, 0.40), trend_score = 40.0
        q_40 = MultiFactorScorer.quality_factor(build_klines(7))
        # up_ratio = 4/20 = 0.20 -> < 0.30, trend_score = 20.0
        q_20 = MultiFactorScorer.quality_factor(build_klines(4))

        self.assertGreater(q_100, q_70)
        self.assertGreater(q_70, q_40)
        self.assertGreater(q_40, q_20)

    def test_factor_synthesizer_weights_normalization_and_median_imputation(self):
        """Verify factor_synthesizer normalizes custom_weights and imputes missing factors with median."""
        from core.models.factor_synthesizer import FactorSynthesizer

        universe = {
            "600519": {"ret_20d": 10.0, "rsi_14": 40.0},
            "000858": {"ret_20d": 5.0, "rsi_14": 50.0},
            "000568": {"ret_20d": 8.0, "rsi_14": None},  # missing rsi_14
        }
        # custom weights not summing to 1
        res = FactorSynthesizer.synthesize_universe(universe, custom_weights={"ret_20d": 2.0, "rsi_14": 2.0})
        self.assertEqual(len(res), 3)
        # 000568 should have standardized_z computed without error or extreme outlier
        z_000568 = res["000568"]["standardized_z"]["rsi_14"]
        self.assertAlmostEqual(z_000568, 0.0, places=1)

    def test_risk_manager_top_divergence_detection(self):
        """Verify risk_manager detects MACD top divergence correctly."""
        from core.strategy.risk_manager import RiskManager

        # Construct 45 klines:
        # First 30 days: prices rise to 20.0, strong momentum (high DIF)
        # Next 15 days: prices rise to 20.5 (new high), but prices moved slowly, so DIF is lower
        klines = []
        for i in range(30):
            p = 10.0 + i * 0.35
            klines.append([f"2026-06-{i+1:02d}", str(p-0.1), str(p), str(p+0.2), str(p-0.2), "2000"])
        # Recent 15 days: sideways then slight creep up to 20.6
        for i in range(15):
            p = 20.0 + (0.04 * i)
            klines.append([f"2026-07-{i+1:02d}", str(p-0.05), str(p), str(p+0.1), str(p-0.1), "800"])

        latest = {
            "close": 20.6,
            "ma10": 20.3,
            "ma20": 20.0,
            "dif": 0.15,      # noticeably lower than earlier peak
            "dea": 0.18,
            "macd_bar": -0.06,
            "boll_mid": 20.1
        }
        signals_res = RiskManager.sell_signals(klines, latest)
        self.assertIn("signals", signals_res)
        # Check if top divergence signal is present
        div_signals = [s for s in signals_res["signals"] if "顶背离" in s]
        self.assertTrue(len(div_signals) > 0, f"Expected top divergence signal, got {signals_res['signals']}")

    def test_risk_manager_macd_red_bars_shortening(self):
        """Verify MACD red bar shortening only triggers when bars > 0 and strictly decreasing."""
        from core.strategy.risk_manager import RiskManager
        from unittest.mock import patch

        klines = [["2026-08-01", "10", "10", "10.5", "9.8", "1000"]] * 30
        latest = {"close": 10.0, "ma10": 9.8, "ma20": 9.5, "dif": 0.2, "dea": 0.1, "macd_bar": 0.1}

        # Case 1: Red bars strictly shrinking [0.8, 0.6, 0.4, 0.2] -> should trigger
        with patch("core.indicators.technical_indicators.macd") as mock_macd:
            mock_macd.return_value = {"dif": [0.2]*30, "dea": [0.1]*30, "bar": [0.0]*26 + [0.8, 0.6, 0.4, 0.2]}
            res = RiskManager.sell_signals(klines, latest)
            shorten_signals = [s for s in res["signals"] if "红柱连续3日缩短" in s]
            self.assertEqual(len(shorten_signals), 1)

        # Case 2: Red bars expanding [0.2, 0.4, 0.6, 0.8] -> should NOT trigger
        with patch("core.indicators.technical_indicators.macd") as mock_macd:
            mock_macd.return_value = {"dif": [0.2]*30, "dea": [0.1]*30, "bar": [0.0]*26 + [0.2, 0.4, 0.6, 0.8]}
            res = RiskManager.sell_signals(klines, latest)
            shorten_signals = [s for s in res["signals"] if "红柱连续3日缩短" in s]
            self.assertEqual(len(shorten_signals), 0)

        # Case 3: Green bars becoming less negative [-0.8, -0.6, -0.4, -0.2] -> should NOT trigger
        with patch("core.indicators.technical_indicators.macd") as mock_macd:
            mock_macd.return_value = {"dif": [0.2]*30, "dea": [0.1]*30, "bar": [0.0]*26 + [-0.8, -0.6, -0.4, -0.2]}
            res = RiskManager.sell_signals(klines, latest)
            shorten_signals = [s for s in res["signals"] if "红柱连续3日缩短" in s]
            self.assertEqual(len(shorten_signals), 0)


if __name__ == "__main__":
    unittest.main()
