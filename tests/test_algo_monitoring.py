# -*- coding: utf-8 -*-
"""
Test Suite for Production Algorithm Monitoring, Alpha Decay & Regime Dispatcher (ALCM Phase 3).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.models.base_algorithm import AlgorithmLifecycleStage
from core.models.monitor_governance import (
    AlgorithmLifecycleManager,
    AlphaDecayTracker,
    DecayStatus,
    RegimeAdaptiveDispatcher,
    RegimeDispatchPlan,
)
from core.models.registry import AlgoRegistry, get_algo, get_target


class TestAlgoMonitoring(unittest.TestCase):
    """Test suite verifying alpha decay tracking, regime dispatching, and lifecycle breakers."""

    def test_rank_ic_calculation(self):
        """Verify cross-sectional Spearman Rank IC mathematical precision."""
        # 1. Perfectly monotonically aligned factor and forward returns -> IC == 1.0
        factor_scores_pos = {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0, "E": 50.0}
        forward_returns_pos = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05}
        ic_perfect = AlphaDecayTracker.calculate_rank_ic(factor_scores_pos, forward_returns_pos)
        self.assertAlmostEqual(ic_perfect, 1.0, places=3)

        # 2. Perfectly inverted factor and forward returns -> IC == -1.0
        forward_returns_neg = {"A": 0.05, "B": 0.04, "C": 0.03, "D": 0.02, "E": 0.01}
        ic_inverted = AlphaDecayTracker.calculate_rank_ic(factor_scores_pos, forward_returns_neg)
        self.assertAlmostEqual(ic_inverted, -1.0, places=3)

        # 3. Insufficient common symbols (<4) returns 0.0
        small_scores = {"A": 1.0, "B": 2.0}
        small_returns = {"A": 0.01, "B": 0.02}
        self.assertEqual(AlphaDecayTracker.calculate_rank_ic(small_scores, small_returns), 0.0)

    def test_alpha_decay_tracker_healthy_and_critical(self):
        """Verify rolling IC statistics, win rate, and decay alarm transitions."""
        tracker = AlphaDecayTracker(lookback_periods=10)

        # 1. Feed 10 periods of solid positive IC (Healthy)
        for i in range(10):
            tracker.record_period_ic("momentum_factor", 0.08 + (0.01 if i % 2 == 0 else -0.01), f"2026-08-{i+1:02d}")

        report_healthy = tracker.get_decay_report("momentum_factor")
        self.assertEqual(report_healthy["status"], DecayStatus.HEALTHY.value)
        self.assertGreater(report_healthy["mean_ic"], 0.05)
        self.assertEqual(report_healthy["win_rate_pct"], 100.0)
        self.assertGreater(report_healthy["ic_ir"], 2.0)

        # 2. Feed 5 consecutive periods of negative inverted IC (Decay Critical)
        for i in range(10, 15):
            tracker.record_period_ic("momentum_factor", -0.06, f"2026-08-{i+1:02d}")

        report_critical = tracker.get_decay_report("momentum_factor")
        self.assertIn(
            report_critical["status"],
            [DecayStatus.DECAY_WARNING.value, DecayStatus.DECAY_CRITICAL.value],
        )
        self.assertIn("decay", report_critical["alert"].lower())

    def test_regime_adaptive_dispatcher_bull(self):
        """Verify dynamic parameter adaptation under Bull regime."""
        plan = RegimeAdaptiveDispatcher.dispatch("BULL")
        self.assertIsInstance(plan, RegimeDispatchPlan)
        self.assertEqual(plan.regime, "BULL")
        self.assertGreaterEqual(plan.max_portfolio_weight, 0.80)
        self.assertIn("volatility_breakout", plan.primary_strategies)
        # Momentum factors should dominate
        self.assertGreater(plan.factor_weights.get("ret_20d", 0.0), 0.15)

    def test_regime_adaptive_dispatcher_oscillation_and_bear(self):
        """Verify dynamic parameter adaptation under Oscillation and Bear regimes."""
        # 1. Oscillation
        plan_osc = RegimeAdaptiveDispatcher.dispatch("OSCILLATION")
        self.assertEqual(plan_osc.regime, "OSCILLATION")
        self.assertEqual(plan_osc.max_portfolio_weight, 0.50)
        self.assertIn("mean_reversion", plan_osc.primary_strategies)

        # 2. Bear regime (defensive)
        plan_bear = RegimeAdaptiveDispatcher.dispatch("BEAR")
        self.assertEqual(plan_bear.regime, "BEAR")
        self.assertLessEqual(plan_bear.max_portfolio_weight, 0.25)
        self.assertIn("trapped_position", plan_bear.primary_strategies)
        self.assertLess(plan_bear.stop_loss_pct, plan_osc.stop_loss_pct)

        # 3. Dispatch from MarketAssessor dict output
        assessor_mock = {"total_score": 82.0, "state": "强势多头共振"}
        plan_from_dict = RegimeAdaptiveDispatcher.dispatch(assessor_mock)
        self.assertEqual(plan_from_dict.regime, "BULL")

    def test_lifecycle_manager_transition_and_audit_trail(self):
        """Verify audited lifecycle transitions in AlgoRegistry."""
        # 1. Transition strategy stage
        old_meta = AlgoRegistry.get_metadata("grid_trading")
        self.assertIsNotNone(old_meta)

        updated_meta = AlgorithmLifecycleManager.transition_stage(
            algo_name="grid_trading",
            target_stage=AlgorithmLifecycleStage.STAGING,
            reason="Entering shadow trading simulation verification",
            operator="qa_auditor",
        )
        self.assertEqual(updated_meta.stage, AlgorithmLifecycleStage.STAGING)

        # 2. Verify audit trail
        trail = AlgorithmLifecycleManager.get_audit_trail("grid_trading")
        self.assertGreaterEqual(len(trail), 1)
        latest_event = trail[-1]
        self.assertEqual(latest_event["new_stage"], "staging")
        self.assertIn("shadow", latest_event["reason"])

        # Revert back to PRODUCTION for system hygiene
        AlgorithmLifecycleManager.transition_stage(
            algo_name="grid_trading",
            target_stage=AlgorithmLifecycleStage.PRODUCTION,
            reason="Restoring to production status",
        )
        self.assertEqual(AlgoRegistry.get_metadata("grid_trading").stage, AlgorithmLifecycleStage.PRODUCTION)

    def test_lifecycle_retirement_circuit_breaker(self):
        """Verify automatic circuit-breaking and demotion upon performance breakdown."""
        # Ensure volatility_breakout is PRODUCTION
        AlgorithmLifecycleManager.transition_stage(
            algo_name="volatility_breakout",
            target_stage=AlgorithmLifecycleStage.PRODUCTION,
            reason="Preparation test",
        )

        # Trigger 1: Drawdown breach (current 25% exceeds 1.5x of baseline 12% = 18%)
        triggered, reason = AlgorithmLifecycleManager.evaluate_retirement_breaker(
            algo_name="volatility_breakout",
            max_drawdown_pct=25.0,
            baseline_drawdown_pct=12.0,
            consecutive_losses=2,
            auto_demote=True,
        )
        self.assertTrue(triggered)
        self.assertIn("Drawdown breach", reason)
        self.assertEqual(
            AlgoRegistry.get_metadata("volatility_breakout").stage,
            AlgorithmLifecycleStage.DEPRECATED,
        )

        # Revert back to PRODUCTION
        AlgorithmLifecycleManager.transition_stage(
            algo_name="volatility_breakout",
            target_stage=AlgorithmLifecycleStage.PRODUCTION,
            reason="Restoring back after test",
        )

    def test_registry_integration_phase3_algorithms(self):
        """Verify that Phase 3 monitoring components are properly registered in AlgoRegistry."""
        tracker_cls = get_target("alpha_decay_tracker")
        self.assertEqual(tracker_cls, AlphaDecayTracker)

        dispatcher_cls = get_target("regime_dispatcher")
        self.assertEqual(dispatcher_cls, RegimeAdaptiveDispatcher)

        lifecycle_cls = get_target("lifecycle_manager")
        self.assertEqual(lifecycle_cls, AlgorithmLifecycleManager)

        # Direct invocation via AlgoRegistry.run_algo
        plan = AlgoRegistry.run_algo("regime_dispatcher")
        self.assertIsInstance(plan, RegimeDispatchPlan)


if __name__ == "__main__":
    unittest.main()
