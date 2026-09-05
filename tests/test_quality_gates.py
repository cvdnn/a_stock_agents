# -*- coding: utf-8 -*-
"""
Test Suite for Quantitative Algorithm Quality Gates & Overfitting Guard (ALCM Phase 2).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.models.quality_gates import (
    AShareComplianceGuard,
    AlgorithmQualityGate,
    LookaheadGuard,
    OverfittingGuard,
    QualityGateReport,
    QualityGateStatus,
)
from core.models.registry import AlgoRegistry, get_algo


class TestQualityGates(unittest.TestCase):
    """Test suite verifying quality gate compliance, anti-lookahead probes, and DSR."""

    def test_lookahead_static_ast_audit(self):
        """Verify static AST scanning catches suspicious forward slices."""
        # 1. Code snippet with forward slice leakage
        leaky_code = """
        def leaky_function(klines, i):
            future_data = klines[i + 1 :]
            return sum(future_data)
        """
        is_clean, violations = LookaheadGuard.audit_source_code(leaky_code)
        self.assertFalse(is_clean)
        self.assertTrue(any("forward slice" in v for v in violations))

        # 2. Clean causal code snippet
        causal_code = """
        def causal_function(klines, i):
            past_data = klines[: i + 1]
            return sum(past_data)
        """
        is_clean_causal, violations_causal = LookaheadGuard.audit_source_code(causal_code)
        self.assertTrue(is_clean_causal)
        self.assertEqual(len(violations_causal), 0)

    def test_lookahead_dynamic_temporal_probe(self):
        """Verify dynamic perturbation probe identifies future data leakage."""
        sample_klines = [[f"2026-08-{i+1:02d}", 10.0, 10.5, 11.0, 9.5, 1000.0] for i in range(30)]

        # 1. Clean causal indicator: uses only up to current slice
        def clean_moving_average(klines):
            closes = [float(k[2]) for k in klines]
            return sum(closes[-5:]) / min(5, len(closes))

        is_ok, msg = LookaheadGuard.probe_temporal_integrity(clean_moving_average, sample_klines, bar_index=15)
        self.assertTrue(is_ok)
        self.assertIn("Passed", msg)

        # 2. Leaky indicator: cheats by peeking at the end of the global sequence
        def cheating_indicator(klines, idx=None):
            # Leaks future data if full sequence is passed
            if idx is not None:
                # Cheats by reading the very last bar in the sequence
                return float(klines[-1][2])
            return float(klines[-1][2])

        is_leaky_ok, leaky_msg = LookaheadGuard.probe_temporal_integrity(cheating_indicator, sample_klines, bar_index=15)
        self.assertFalse(is_leaky_ok)
        self.assertIn("Lookahead Bias", leaky_msg)

    def test_a_share_compliance_guard_t_plus_one(self):
        """Verify A-Share T+1 settlement enforcement."""
        # 1. Illegal intraday round-trip trade without overnight inventory
        illegal_trades = [
            {"date": "2026-08-01", "code": "600519", "action": "buy", "qty": 100},
            {"date": "2026-08-01", "code": "600519", "action": "sell", "qty": 100},  # Same-day sell!
        ]
        is_compliant, violations = AShareComplianceGuard.audit_trade_log(illegal_trades)
        self.assertFalse(is_compliant)
        self.assertTrue(any("T+1 Violation" in v for v in violations))

        # 2. Compliant trade held overnight
        legal_trades = [
            {"date": "2026-08-01", "code": "600519", "action": "buy", "qty": 100},
            {"date": "2026-08-02", "code": "600519", "action": "sell", "qty": 100},  # Next-day sell
        ]
        is_legal_ok, legal_violations = AShareComplianceGuard.audit_trade_log(legal_trades)
        self.assertTrue(is_legal_ok)
        self.assertEqual(len(legal_violations), 0)

    def test_a_share_limit_price_and_suspension_guard(self):
        """Verify prohibition of trading on unyielding one-word limits and zero-volume days."""
        market_context = {
            "2026-08-01": {
                "open": 11.0, "close": 11.0, "high": 11.0, "low": 11.0,
                "prev_close": 10.0, "volume": 100.0,  # One-word limit-up locked
            },
            "2026-08-02": {
                "open": 10.0, "close": 10.0, "high": 10.0, "low": 10.0,
                "prev_close": 10.0, "volume": 0.0,    # Halted/suspended
            }
        }
        test_trades = [
            {"date": "2026-08-01", "code": "000001", "action": "buy", "qty": 100},
            {"date": "2026-08-02", "code": "000001", "action": "buy", "qty": 100},
        ]
        is_compliant, violations = AShareComplianceGuard.audit_trade_log(test_trades, market_context)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Limit-up violation" in v for v in violations))
        self.assertTrue(any("Suspension execution violation" in v for v in violations))

    def test_overfitting_oos_decay(self):
        """Verify calculation of Out-of-Sample decay ratio."""
        # 1. Acceptable decay (10% Sharpe decay)
        in_sample = {"annual_return_pct": 30.0, "sharpe_ratio": 2.0}
        out_sample = {"annual_return_pct": 27.0, "sharpe_ratio": 1.8}
        is_ok, ret_decay, sr_decay, details = OverfittingGuard.calculate_oos_decay(in_sample, out_sample)
        self.assertTrue(is_ok)
        self.assertAlmostEqual(sr_decay, 0.10, places=2)

        # 2. Unacceptable severe decay (70% Sharpe decay)
        in_sample_bad = {"annual_return_pct": 50.0, "sharpe_ratio": 2.5}
        out_sample_bad = {"annual_return_pct": 5.0, "sharpe_ratio": 0.5}
        is_ok_bad, _, sr_decay_bad, _ = OverfittingGuard.calculate_oos_decay(in_sample_bad, out_sample_bad)
        self.assertFalse(is_ok_bad)
        self.assertGreater(sr_decay_bad, 0.35)

    def test_deflated_sharpe_ratio(self):
        """Verify Marcos López de Prado's Deflated Sharpe Ratio calculation."""
        # Create a sample of daily returns
        import random
        random.seed(42)
        daily_returns = [0.001 + random.gauss(0, 0.01) for _ in range(250)]

        # 1. Single trial with solid Sharpe
        dsr_prob, exp_max_sr, summary = OverfittingGuard.calculate_deflated_sharpe_ratio(
            observed_sharpe=1.8, daily_returns=daily_returns, num_trials=1
        )
        self.assertGreaterEqual(dsr_prob, 0.90)
        self.assertIn("DSR Confidence", summary)

        # 2. Multiple trial discount (100 independent trials reduces confidence for modest Sharpe)
        dsr_prob_multi, _, _ = OverfittingGuard.calculate_deflated_sharpe_ratio(
            observed_sharpe=1.0, daily_returns=daily_returns, num_trials=100
        )
        self.assertLess(dsr_prob_multi, dsr_prob)

    def test_algorithm_quality_gate_composite_report(self):
        """Verify end-to-end audit report generation by AlgorithmQualityGate."""
        sample_klines = [[f"2026-08-{i+1:02d}", 10.0, 10.5, 11.0, 9.5, 1000.0] for i in range(30)]

        def compliant_factor(klines):
            closes = [float(k[2]) for k in klines]
            return closes[-1] / (sum(closes[-10:]) / 10.0)

        legal_trades = [
            {"date": "2026-08-01", "code": "600519", "action": "buy", "qty": 100},
            {"date": "2026-08-02", "code": "600519", "action": "sell", "qty": 100},
        ]
        in_sample = {"annual_return_pct": 25.0, "sharpe_ratio": 1.6}
        out_sample = {"annual_return_pct": 22.0, "sharpe_ratio": 1.4}
        daily_returns = [0.001 + (0.002 if i % 2 == 0 else -0.0005) for i in range(100)]

        # Audit compliant algorithm
        report = AlgorithmQualityGate.audit_algorithm(
            name_or_func=compliant_factor,
            sample_klines=sample_klines,
            trade_log=legal_trades,
            in_sample_metrics=in_sample,
            out_sample_metrics=out_sample,
            daily_returns=daily_returns,
        )
        self.assertIsInstance(report, QualityGateReport)
        self.assertEqual(report.status, QualityGateStatus.PASSED)
        self.assertGreaterEqual(report.score, 85.0)
        self.assertTrue(report.is_passed())

        # Audit blocked algorithm (with illegal same-day sell)
        illegal_trades = [
            {"date": "2026-08-01", "code": "600519", "action": "buy", "qty": 100},
            {"date": "2026-08-01", "code": "600519", "action": "sell", "qty": 100},
        ]
        blocked_report = AlgorithmQualityGate.audit_algorithm(
            name_or_func="leaky_strategy",
            trade_log=illegal_trades,
        )
        self.assertEqual(blocked_report.status, QualityGateStatus.BLOCKED)
        self.assertFalse(blocked_report.is_passed())
        self.assertGreater(len(blocked_report.violations), 0)

        # Test registered quality gate in AlgoRegistry
        from core.models.registry import get_target
        gate_obj = get_algo("quality_gate")
        self.assertIsInstance(gate_obj, AlgorithmQualityGate)
        gate_cls = get_target("quality_gate")
        self.assertEqual(gate_cls, AlgorithmQualityGate)


if __name__ == "__main__":
    unittest.main()
