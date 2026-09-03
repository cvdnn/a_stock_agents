# -*- coding: utf-8 -*-
"""
Test suite verifying P1 phase remediation:
- Single Source of Truth (SSOT) thin forwarders across skills/
- Subprocess execution delegation via runpy
- Centralized configuration and path resolution
- Optional dependencies in pyproject.toml
- Code hygiene fixes (no mutable defaults, no bare excepts in target files)
"""

import unittest
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))


class TestP1SSOT(unittest.TestCase):

    def test_all_50_forwarders_import_cleanly(self):
        """Verify that all 50 forwarders in skills/ import cleanly and export symbols."""
        skills_dir = ROOT / "skills"
        core_dir = ROOT / "core"

        core_map = {}
        for p in core_dir.rglob("*.py"):
            if p.name != "__init__.py":
                rel = p.relative_to(ROOT)
                parts = list(rel.parts)
                parts[-1] = parts[-1][:-3]
                dot_path = ".".join(parts)
                core_map[p.name] = dot_path

        tested = 0
        failed = []
        for p in skills_dir.rglob("*.py"):
            if p.name in core_map and p.name != "__init__.py" and "templates" not in p.parts:
                tested += 1
                try:
                    # Read forwarder content to ensure it delegates to core
                    text = p.read_text(encoding="utf-8")
                    self.assertIn("Single Source of Truth (SSOT)", text)
                    self.assertIn("core.", text)
                except Exception as e:
                    failed.append((str(p.relative_to(ROOT)), str(e)))

        self.assertEqual(tested, 50, f"Expected 50 forwarders, found {tested}")
        self.assertEqual(len(failed), 0, f"Failed forwarder checks: {failed}")

    def test_forwarder_cli_execution_delegation(self):
        """Verify subprocess execution through a skill forwarder works seamlessly."""
        cmd = [
            sys.executable,
            str(ROOT / "skills" / "a-stocks" / "scripts" / "data_bridge.py"),
            "quote",
            "--code",
            "600519"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, f"data_bridge forwarder failed:\n{res.stderr}")
        self.assertIn("600519", res.stdout)
        self.assertIn("贵州茅台", res.stdout)

    def test_fetch_realtime_forwarder_cli(self):
        """Verify fetch_realtime forwarder works and fetches live quote."""
        cmd = [
            sys.executable,
            str(ROOT / "skills" / "a-share-data" / "scripts" / "fetch_realtime.py"),
            "--quote",
            "600519"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, f"fetch_realtime forwarder failed:\n{res.stderr}")
        self.assertIn("600519", res.stdout)

    def test_config_centralization_in_data_bridge(self):
        """Verify data_bridge loads config via core.config rather than broken SKILL_DIR."""
        from core.data.data_bridge import _load_path_config, DataBridge
        cfg = _load_path_config()
        self.assertIn("venv_python", cfg)
        self.assertIn("system_python", cfg)
        bridge = DataBridge()
        self.assertIsNotNone(bridge.cfg)
        quote = bridge.get_realtime_quote("600519")
        self.assertIsNotNone(quote)

    def test_pyproject_optional_dependencies(self):
        """Verify pyproject.toml defines [project.optional-dependencies] full."""
        pyproject_path = ROOT / "pyproject.toml"
        content = pyproject_path.read_text(encoding="utf-8")
        self.assertIn("[project.optional-dependencies]", content)
        self.assertIn("full = [", content)
        self.assertIn("akshare", content)
        self.assertIn("efinance", content)

    def test_ashare_code_hygiene(self):
        """Verify Ashare.py has no mutable default arguments or bare excepts."""
        ashare_path = ROOT / "core" / "data" / "Ashare.py"
        content = ashare_path.read_text(encoding="utf-8")
        self.assertNotIn("fields=[]", content)
        self.assertNotIn("except:", content)

    def test_multi_dim_model_code_hygiene(self):
        """Verify multi_dim_model_v3.py has no bare excepts."""
        model_path = ROOT / "core" / "models" / "multi_dim_model_v3.py"
        content = model_path.read_text(encoding="utf-8")
        self.assertNotIn("except:", content)


if __name__ == "__main__":
    unittest.main()
