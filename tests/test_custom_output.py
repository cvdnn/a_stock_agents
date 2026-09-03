# -*- coding: utf-8 -*-
"""
Unit tests for custom output directory isolation, environment variable overrides,
automatic template initialization, and stock pool / position CRUD routing.
"""

import os
import sys
import shutil
import unittest
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))


class TestCustomOutputIsolation(unittest.TestCase):
    def setUp(self):
        self.test_custom_dir = ROOT / "cache" / "_unit_test_custom_output"
        if self.test_custom_dir.exists():
            shutil.rmtree(self.test_custom_dir)

    def tearDown(self):
        if self.test_custom_dir.exists():
            try:
                shutil.rmtree(self.test_custom_dir)
            except Exception:
                pass

    def test_default_output_paths(self):
        from core.config import get_active_paths, OUTPUT_DIR, OUTPUT_POOLS_DIR
        paths = get_active_paths()
        self.assertIn("project_root", paths)
        self.assertIn("output_dir", paths)
        self.assertIn("pools_dir", paths)
        self.assertTrue(OUTPUT_DIR.exists())
        self.assertTrue(OUTPUT_POOLS_DIR.exists())

    def test_custom_output_init_templates(self):
        from core.config import init_output_templates
        target_pools = self.test_custom_dir / "pools"
        self.assertFalse(target_pools.exists())
        
        init_output_templates(target_pools_dir=target_pools)
        self.assertTrue(target_pools.exists())
        
        for f in ["positions.csv", "selected_pool.csv", "watch_pool.csv"]:
            csv_path = target_pools / f
            self.assertTrue(csv_path.exists(), f"File {f} was not created in custom output dir")
            content = csv_path.read_text(encoding="utf-8")
            self.assertTrue(len(content.strip()) > 0, f"File {f} is empty")

    def test_env_override_resolution(self):
        import subprocess
        env = os.environ.copy()
        custom_path = str(self.test_custom_dir)
        env["A_STOCK_OUTPUT_DIR"] = custom_path
        
        code_str = (
            "import sys\n"
            "from pathlib import Path\n"
            "ROOT = Path('.').resolve()\n"
            "sys.path.insert(0, str(ROOT))\n"
            "from core.config import get_active_paths, OUTPUT_DIR, OUTPUT_POOLS_DIR, IS_CUSTOM_OUTPUT\n"
            "paths = get_active_paths()\n"
            "assert paths['is_custom_output'] is True, 'Expected is_custom_output to be True'\n"
            "assert IS_CUSTOM_OUTPUT is True\n"
            "assert Path(paths['output_dir']).resolve() == Path(sys.argv[1]).resolve()\n"
            "assert (OUTPUT_POOLS_DIR / 'positions.csv').exists(), 'positions.csv should exist'\n"
            "print('SUCCESS_CUSTOM_RESOLVED')\n"
        )
        
        cmd = [sys.executable, "-c", code_str, custom_path]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)
        self.assertEqual(res.returncode, 0, f"Subprocess failed:\nstdout:{res.stdout}\nstderr:{res.stderr}")
        self.assertIn("SUCCESS_CUSTOM_RESOLVED", res.stdout)

    def test_custom_output_prioritization_and_isolation(self):
        """Verify that when a custom output directory is configured, all CLI commands and skill scripts read ONLY custom data and ignore default output/."""
        custom_pools = self.test_custom_dir / "pools"
        custom_pools.mkdir(parents=True, exist_ok=True)
        
        # Write unique mock data to custom output
        (custom_pools / "positions.csv").write_text(
            "code,name,buy_date,buy_price,qty,stop_loss,take_profit,sector,reason,status,strategy,entry_trigger,expected_days,risk_level,ma_status,market_context,backtest_result,notes\n"
            "000001,平安银行,2026-09-01,10.50,1000,10.00,12.00,银行,自定义测试持仓,持仓中,trend_pullback,MA20突破,5,低,多头,震荡偏多,PASS,测试持仓\n",
            encoding="utf-8"
        )
        (custom_pools / "selected_pool.csv").write_text(
            "code,name,added_date,rating,reason,sector,pe,change_pct,ma_status,entry_trigger,stop_loss,take_profit,risk_level,market_context,notes,ta_decision,ta_analysis_date,ta_report_path,consensus_rating\n"
            "000002,万科A,2026-09-01,A,自定义自选测试,房地产,8.5,1.2,多头,突破买入,8.0,10.0,中,回暖,自选测试,BUY,2026-09-01,,A\n",
            encoding="utf-8"
        )
        (custom_pools / "watch_pool.csv").write_text(
            "code,name,added_date,rating,reason,sector,pe,change_pct,fund_flow,entry_condition,market_context,ta_analysis_date\n"
            "000063,中兴通讯,2026-09-01,B,自定义关注测试,通信,15.0,2.1,流入,突破MA20,主线,2026-09-01\n",
            encoding="utf-8"
        )

        env = os.environ.copy()
        env["A_STOCK_OUTPUT_DIR"] = str(self.test_custom_dir)
        python_exec = sys.executable

        scripts_to_verify = [
            ("core.cli position list", [python_exec, "core/cli.py", "position", "list"], ["000001", "平安银行"]),
            ("core.cli pool list", [python_exec, "core/cli.py", "pool", "list"], ["000002", "万科A"]),
            ("core pool_manager list", [python_exec, "core/strategy/pool_manager.py", "list"], ["000002", "万科A"]),
            ("core position_manager list", [python_exec, "core/strategy/position_manager.py", "list"], ["000001", "平安银行"]),
            ("core position_stop_monitor", [python_exec, "core/strategy/position_stop_monitor.py", "--show"], ["000001", "平安银行"]),
            ("core investment_report selected", [python_exec, "core/reporting/investment_report.py", "--pool", "selected"], ["000002", "万科A"]),
            ("skills pool_manager list", [python_exec, "skills/astock-pool-dashboard/scripts/pool_manager.py", "list"], ["000002", "万科A"]),
            ("skills position_manager list", [python_exec, "skills/astock-pool-dashboard/scripts/position_manager.py", "list"], ["000001", "平安银行"]),
            ("skills sandbox", [python_exec, "skills/astock-pool-dashboard/scripts/sandbox.py"], ["000001", "平安银行"]),
            ("skills investment_report selected", [python_exec, "skills/astock-pool-dashboard/scripts/investment_report.py", "--pool", "selected"], ["000002", "万科A"]),
            ("skills position_stop_monitor", [python_exec, "skills/astock-pool-dashboard/scripts/position_stop_monitor.py", "--show"], ["000001", "平安银行"]),
            ("skills ta_orchestrator check-pool", [python_exec, "skills/astock-agent-debate/scripts/ta_orchestrator.py", "--mode", "check-pool"], ["000002", "万科A"]),
            ("skills pool_audit", [python_exec, "skills/astock-pool-audit/scripts/pool_audit.py"], ["000063", "中兴通讯"]),
        ]


        for name, cmd, expected_keywords in scripts_to_verify:
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)
            self.assertEqual(res.returncode, 0, f"Script [{name}] failed with returncode {res.returncode}:\nstderr: {res.stderr}\nstdout: {res.stdout}")
            for kw in expected_keywords:
                self.assertIn(kw, res.stdout, f"Script [{name}] did not find expected keyword '{kw}' from custom output.\nstdout:\n{res.stdout}")

    def test_default_output_untouched(self):
        """Verify that modifying data in custom output directory leaves default project output directory untouched."""
        default_pos = ROOT / "output" / "pools" / "positions.csv"
        default_content_before = default_pos.read_text(encoding="utf-8") if default_pos.exists() else ""

        custom_pools = self.test_custom_dir / "pools"
        custom_pools.mkdir(parents=True, exist_ok=True)
        
        env = os.environ.copy()
        env["A_STOCK_OUTPUT_DIR"] = str(self.test_custom_dir)

        # Initialize and add stock in custom output dir
        cmd = [sys.executable, "core/strategy/pool_manager.py", "add", "--pool", "selected", "--code", "600000", "--name", "浦发银行", "--reason", "测试隔离", "--sector", "银行"]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)
        self.assertEqual(res.returncode, 0, f"Add to custom pool failed:\n{res.stderr}")

        # Verify custom selected_pool has 600000
        custom_sel = custom_pools / "selected_pool.csv"
        self.assertTrue(custom_sel.exists())
        self.assertIn("600000", custom_sel.read_text(encoding="utf-8"))

        # Verify default output positions.csv is unmodified
        default_content_after = default_pos.read_text(encoding="utf-8") if default_pos.exists() else ""
        self.assertEqual(default_content_before, default_content_after, "Default project output was modified when custom output was active!")


if __name__ == "__main__":
    unittest.main()
