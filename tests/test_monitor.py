# -*- coding: utf-8 -*-
"""
Unit tests for core.monitor module:
- schedule_gate: market hours, auction hours, phases, trading day detection
- state_store: atomic load/save, deduplication
- notifier: toast notification and logging fallback
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.monitor.schedule_gate import (
    get_market_phase,
    is_market_hours,
    is_trading_day,
)
from core.monitor.state_store import (
    StateDeduplicator,
    load_state,
    save_state,
)
from core.monitor.notifier import notify, send_windows_toast


class TestScheduleGate(unittest.TestCase):

    def test_weekend(self):
        # 2026-08-29 is Saturday
        sat = datetime(2026, 8, 29, 10, 0, 0)
        self.assertFalse(is_trading_day(sat))
        self.assertFalse(is_market_hours(now=sat))
        self.assertEqual(get_market_phase(sat), "WEEKEND")

        # 2026-08-30 is Sunday
        sun = datetime(2026, 8, 30, 14, 0, 0)
        self.assertFalse(is_trading_day(sun))
        self.assertFalse(is_market_hours(now=sun))
        self.assertEqual(get_market_phase(sun), "WEEKEND")

    def test_weekday_market_hours(self):
        # 2026-08-28 is Friday
        # 09:10 - pre-market
        dt_pre = datetime(2026, 8, 28, 9, 10, 0)
        self.assertFalse(is_market_hours(now=dt_pre))
        self.assertEqual(get_market_phase(dt_pre), "PRE_MARKET")

        # 09:20 - call auction
        dt_auction = datetime(2026, 8, 28, 9, 20, 0)
        self.assertFalse(is_market_hours(now=dt_auction, include_auction=False))
        self.assertTrue(is_market_hours(now=dt_auction, include_auction=True))
        self.assertEqual(get_market_phase(dt_auction), "CALL_AUCTION")

        # 09:30 - morning open
        dt_morning_open = datetime(2026, 8, 28, 9, 30, 0)
        self.assertTrue(is_market_hours(now=dt_morning_open))
        self.assertEqual(get_market_phase(dt_morning_open), "CONTINUOUS_MORNING")

        # 10:30 - morning session
        dt_morning = datetime(2026, 8, 28, 10, 30, 0)
        self.assertTrue(is_market_hours(now=dt_morning))
        self.assertEqual(get_market_phase(dt_morning), "CONTINUOUS_MORNING")

        # 11:30 - morning close boundary
        dt_morning_close = datetime(2026, 8, 28, 11, 30, 0)
        self.assertTrue(is_market_hours(now=dt_morning_close))
        self.assertEqual(get_market_phase(dt_morning_close), "CONTINUOUS_MORNING")

        # 12:00 - lunch break
        dt_lunch = datetime(2026, 8, 28, 12, 0, 0)
        self.assertFalse(is_market_hours(now=dt_lunch))
        self.assertEqual(get_market_phase(dt_lunch), "LUNCH_BREAK")

        # 13:00 - afternoon open
        dt_afternoon_open = datetime(2026, 8, 28, 13, 0, 0)
        self.assertTrue(is_market_hours(now=dt_afternoon_open))
        self.assertEqual(get_market_phase(dt_afternoon_open), "CONTINUOUS_AFTERNOON")

        # 14:30 - afternoon continuous auction
        dt_afternoon = datetime(2026, 8, 28, 14, 30, 0)
        self.assertTrue(is_market_hours(now=dt_afternoon))
        self.assertEqual(get_market_phase(dt_afternoon), "CONTINUOUS_AFTERNOON")

        # 14:59 - closing call auction (14:57-15:00)
        dt_closing_auction = datetime(2026, 8, 28, 14, 59, 0)
        self.assertTrue(is_market_hours(now=dt_closing_auction))
        self.assertEqual(get_market_phase(dt_closing_auction), "CLOSING_AUCTION")


        # 15:00 - close
        dt_close = datetime(2026, 8, 28, 15, 0, 0)
        self.assertTrue(is_market_hours(now=dt_close))

        # 15:01 - post market
        dt_post = datetime(2026, 8, 28, 15, 1, 0)
        self.assertFalse(is_market_hours(now=dt_post))
        self.assertEqual(get_market_phase(dt_post), "POST_MARKET")



class TestStateStore(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "test_state.json")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_non_existent(self):
        res = load_state(self.state_file, default={"count": 0})
        self.assertEqual(res, {"count": 0})

    def test_load_corrupted_json(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            f.write("invalid json {[[")
        res = load_state(self.state_file, default={"status": "fallback"})
        self.assertEqual(res, {"status": "fallback"})

    def test_save_and_load_roundtrip(self):
        data = {"ticker": "600519", "price": 1600.5, "fired": ["tp1", "stop"]}
        save_state(self.state_file, data)
        loaded = load_state(self.state_file)
        self.assertEqual(loaded, data)

    def test_state_deduplicator(self):
        dedup = StateDeduplicator(self.state_file)
        # First fire should be allowed
        self.assertTrue(dedup.should_fire("600519", "tp1", today="2026-08-28"))
        dedup.record_fire("600519", "tp1", today="2026-08-28")

        # Second fire on same day should be blocked
        self.assertFalse(dedup.should_fire("600519", "tp1", today="2026-08-28"))

        # Different action on same day should be allowed
        self.assertTrue(dedup.should_fire("600519", "stop", today="2026-08-28"))

        # Next day should be allowed
        self.assertTrue(dedup.should_fire("600519", "tp1", today="2026-08-29"))


class TestNotifier(unittest.TestCase):

    @patch("subprocess.run")
    def test_send_windows_toast(self, mock_sub):
        mock_sub.return_value = MagicMock(returncode=0)
        # Should not raise exception
        send_windows_toast("Test Alert", "Price reached MA20")
        if sys.platform == "win32":
            mock_sub.assert_called_once()
            args = mock_sub.call_args[0][0]
            self.assertIn("powershell", args[0].lower())


    @patch("subprocess.run")
    def test_notify(self, mock_sub):
        mock_sub.return_value = MagicMock(returncode=0)
        notify("Title", "Message")


if __name__ == "__main__":
    unittest.main()
