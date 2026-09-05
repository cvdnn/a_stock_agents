# -*- coding: utf-8 -*-
"""
Commands & CLI Regression Test Suite:
Validates:
- core/commands/ modular command registration and argument mapping
- core/cli.py full subcommand parser registration and dispatching
- skills/ CLI forwarders delegation to core.cli (Single Source of Truth)
- subprocess execution of version and command help
"""

import sys
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

from core.cli import build_parser, main
import core.commands.backtest_cmds as backtest_cmds
import core.commands.data_cmds as data_cmds
import core.commands.model_cmds as model_cmds
import core.commands.portfolio_cmds as portfolio_cmds
import core.commands.strategy_cmds as strategy_cmds


class TestCommandsSuite(unittest.TestCase):

    def test_cli_parser_all_subcommands_registered(self):
        """Verify build_parser registers all expected subcommands across all modules."""
        parser = build_parser()
        subparser_action = None
        for action in parser._actions:
            if action.dest == "command":
                subparser_action = action
                break
        self.assertIsNotNone(subparser_action, "Must have 'command' subparser action")

        expected_commands = [
            "quote", "technical", "score", "analyze", "trapped", "market",
            "batch", "deploy-monitor", "screen", "risk", "golden-cross",
            "events", "cyq", "balance", "evaluate", "backtest", "multi-backtest",
            "multi-factor", "portfolio-risk", "mean-reversion", "grid",
            "vol-breakout", "action", "intent", "downside", "report",
            "config", "pool", "position", "data", "skill", "version"
        ]

        registered_commands = set(subparser_action.choices.keys())
        for cmd in expected_commands:
            self.assertIn(cmd, registered_commands, f"Subcommand '{cmd}' must be registered in core.cli")

    def test_cli_parse_args_dispatch(self):
        """Verify CLI argument parsing succeeds for various command syntaxes."""
        parser = build_parser()

        # quote
        args = parser.parse_args(["quote", "600519"])
        self.assertEqual(args.command, "quote")
        self.assertEqual(args.code, "600519")

        # trapped
        args = parser.parse_args(["trapped", "600760", "--cost", "50", "--shares", "1000"])
        self.assertEqual(args.command, "trapped")
        self.assertEqual(args.code, "600760")
        self.assertEqual(args.cost, 50.0)
        self.assertEqual(args.shares, 1000)

        # multi-backtest
        args = parser.parse_args(["multi-backtest", "--days", "100", "--top", "5"])
        self.assertEqual(args.command, "multi-backtest")
        self.assertEqual(args.days, 100)
        self.assertEqual(args.top, 5)

        # evaluate (compat mode with a_stocks flags)
        args = parser.parse_args(["evaluate", "--auto", "--days", "60"])
        self.assertEqual(args.command, "evaluate")
        self.assertTrue(args.auto)
        self.assertEqual(args.count, 60)

        # grid
        args = parser.parse_args(["grid", "600519", "--cash", "200000"])
        self.assertEqual(args.command, "grid")
        self.assertEqual(args.code, "600519")
        self.assertEqual(args.cash, 200000.0)

    def test_cli_version_via_subprocess(self):
        """Run core/cli.py version via subprocess."""
        cmd = [sys.executable, str(ROOT / "core" / "cli.py"), "version"]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, f"core/cli.py version failed:\n{res.stderr}")
        self.assertIn("A-Stock Agents", res.stdout)
        self.assertIn("3.0.0", res.stdout)

    def test_a_stocks_forwarder_via_subprocess(self):
        """Run a_stocks.py forwarder --help via subprocess."""
        cmd = [
            sys.executable,
            str(ROOT / "skills" / "astock-platform-evaluate" / "scripts" / "a_stocks.py"),
            "--help"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, f"a_stocks.py forwarder failed:\n{res.stderr}")
        self.assertIn("A-Stock Agents", res.stdout)
        self.assertIn("multi-backtest", res.stdout)

    def test_skills_forwarders_import_cleanly(self):
        """Verify skills forwarders delegate to core modules."""
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
                    text = p.read_text(encoding="utf-8")
                    self.assertIn("Single Source of Truth (SSOT)", text)
                    self.assertIn("core.", text)
                except Exception as e:
                    failed.append((str(p.relative_to(ROOT)), str(e)))

        self.assertGreaterEqual(tested, 50, f"Expected at least 50 forwarders, found {tested}")
        self.assertEqual(len(failed), 0, f"Failed forwarder checks: {failed}")


if __name__ == "__main__":
    unittest.main()
