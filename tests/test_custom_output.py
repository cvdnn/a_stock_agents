# -*- coding: utf-8 -*-
"""
Unit tests for custom output directory isolation, environment variable overrides,
automatic template initialization, and stock pool / position CRUD routing.
"""

import os
import sys
import shutil
import unittest
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
            "from core.config import get_active_paths, OUTPUT_DIR, OUTPUT_POOLS_DIR\n"
            "paths = get_active_paths()\n"
            "assert paths['is_custom_output'] is True, 'Expected is_custom_output to be True'\n"
            "assert Path(paths['output_dir']).resolve() == Path(sys.argv[1]).resolve()\n"
            "assert (OUTPUT_POOLS_DIR / 'positions.csv').exists(), 'positions.csv should exist'\n"
            "print('SUCCESS_CUSTOM_RESOLVED')\n"
        )
        
        cmd = [sys.executable, "-c", code_str, custom_path]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)
        self.assertEqual(res.returncode, 0, f"Subprocess failed:\nstdout:{res.stdout}\nstderr:{res.stderr}")
        self.assertIn("SUCCESS_CUSTOM_RESOLVED", res.stdout)


if __name__ == "__main__":
    unittest.main()
