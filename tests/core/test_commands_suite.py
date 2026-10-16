# -*- coding: utf-8 -*-
"""
Commands & CLI Regression Test Suite:
Validates:
- core/commands/ modular command registration and argument mapping
- core/cli.py full subcommand parser registration and dispatching
- skills/ CLI forwarders delegation to core.cli (Single Source of Truth)
- subprocess execution of version and command help
"""

import json
import sys
import unittest
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
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
            "strategy", "quant", "shortline", "tips", "validate-model",
            "config", "pool", "position", "data", "skill", "trade", "version",
            # 2026-10-15 补齐：与 build_parser 实际注册的 46 个子命令对齐（此前缺失 8 个）
            "funnel", "pattern", "chenxiaoqun", "debate", "dataset",
            "screen-model", "server", "ui"
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
        """Run cli.py version via subprocess."""
        cli_path = ROOT / "skill_bundle" / "runtime" / "core" / "cli.py" if (ROOT / "skill_bundle" / "runtime" / "core" / "cli.py").exists() else ROOT / "core" / "cli.py"
        cmd = [sys.executable, str(cli_path), "version"]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, f"cli.py version failed:\n{res.stderr}")
        self.assertIn("A-Stock Agents", res.stdout)
        self.assertIn("3.0.0", res.stdout)

    def test_a_stocks_forwarder_via_subprocess(self):
        """Run a_stocks.py forwarder --help via subprocess."""
        astock_script = ROOT / "skill_bundle" / "skills" / "astock-platform-evaluate" / "scripts" / "a_stocks.py"
        if not astock_script.exists():
            astock_script = ROOT / "skills" / "astock-platform-evaluate" / "scripts" / "a_stocks.py"
        cmd = [
            sys.executable,
            str(astock_script),
            "--help"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res.returncode, 0, f"a_stocks.py forwarder failed:\n{res.stderr}")
        self.assertIn("A-Stock Agents", res.stdout)
        self.assertIn("multi-backtest", res.stdout)

    def test_skills_forwarders_import_cleanly(self):
        """Verify skills forwarders delegate to core modules."""
        skills_dir = ROOT / "skill_bundle" / "skills" if (ROOT / "skill_bundle" / "skills").exists() else ROOT / "skills"
        core_dir = ROOT / "skill_bundle" / "runtime" / "core" if (ROOT / "skill_bundle" / "runtime" / "core").exists() else ROOT / "core"

        core_names = {p.name for p in core_dir.rglob("*.py") if p.name != "__init__.py"}

        tested = 0
        failed = []
        for p in skills_dir.rglob("*.py"):
            if p.name in core_names and p.name != "__init__.py":
                tested += 1
                try:
                    text = p.read_text(encoding="utf-8")
                    self.assertIn("Single Source of Truth (SSOT)", text)
                    self.assertIn("core.", text)
                except Exception as e:
                    failed.append((str(p.relative_to(ROOT)), str(e)))

        self.assertGreaterEqual(tested, 50, f"Expected at least 50 forwarders, found {tested}")
        self.assertEqual(len(failed), 0, f"Failed forwarder checks: {failed}")

    def test_cli_skill_list_execution(self):
        """P1-06: 验证 astock skill list 与 skill list --json 输出结构与 manifest 条目数对齐。"""
        cli_path = ROOT / "skill_bundle" / "runtime" / "core" / "cli.py" if (ROOT / "skill_bundle" / "runtime" / "core" / "cli.py").exists() else ROOT / "core" / "cli.py"
        manifest_path = ROOT / "skill_bundle" / "assets" / "config" / "skills_manifest.json" if (ROOT / "skill_bundle" / "assets" / "config" / "skills_manifest.json").exists() else ROOT / "assets" / "config" / "skills_manifest.json"

        # 1. 验证纯文本模式输出包含 20 个已注册技能
        cmd_text = [sys.executable, str(cli_path), "skill", "list"]
        res_text = subprocess.run(cmd_text, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res_text.returncode, 0, f"skill list failed:\n{res_text.stderr}")
        self.assertIn("已注册技能模块 (20 个)", res_text.stdout)
        self.assertIn("a-stock-agents", res_text.stdout)

        # 2. 验证 --json 模式输出为合法 JSON，且条目与 manifest 对齐 (19 业务技能 + 1 锚点技能 = 20)
        cmd_json = [sys.executable, str(cli_path), "skill", "list", "--json"]
        res_json = subprocess.run(cmd_json, capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(res_json.returncode, 0, f"skill list --json failed:\n{res_json.stderr}")

        payload = json.loads(res_json.stdout)
        self.assertIn("skills", payload)
        self.assertEqual(len(payload["skills"]), 20)
        self.assertEqual(payload.get("total"), 20)
        self.assertIn("a-stock-agents", payload["skills"])

        manifest_skills = {item["id"] for item in json.loads(manifest_path.read_text(encoding="utf-8"))["skills"]}
        self.assertEqual(len(manifest_skills), 19)
        self.assertEqual(set(payload["skills"]), manifest_skills | {"a-stock-agents"})

    def test_cli_json_structural_contract_and_trade_principles(self):
        """P1-06: 验证 representative CLI 命令执行后输出纯合法 JSON，并断言实战交易三原则字段。"""
        cli_path = ROOT / "skill_bundle" / "runtime" / "core" / "cli.py" if (ROOT / "skill_bundle" / "runtime" / "core" / "cli.py").exists() else ROOT / "core" / "cli.py"

        # 待验证的代表性命令矩阵 (并发执行以保证在 10s 内快速同步完成)
        test_matrix = [
            ("tips", [sys.executable, str(cli_path), "tips", "--json"]),
            ("validate-model", [sys.executable, str(cli_path), "validate-model", "--model", "Kronos", "--code", "600519", "--json"]),
            ("intent", [sys.executable, str(cli_path), "intent", "分析贵州茅台走势", "--json"]),
            ("funnel", [sys.executable, str(cli_path), "funnel", "validate", "--json"]),
            ("pool_list", [sys.executable, str(cli_path), "pool", "list", "--json"]),
            ("pool_audit", [sys.executable, str(cli_path), "pool", "audit", "--json"]),
            ("trade_balance", [sys.executable, str(cli_path), "trade", "balance", "--json"]),
            ("shortline", [sys.executable, str(cli_path), "shortline", "check", "--code", "600519", "--json"]),
            ("action", [sys.executable, str(cli_path), "action", "--code", "600519", "--cost", "1600", "--shares", "100", "--json"]),
            ("chenxiaoqun", [sys.executable, str(cli_path), "pattern", "chenxiaoqun", "600519", "--json"]),
            ("report", [sys.executable, str(cli_path), "report", "600519", "--json"]),
        ]

        with ThreadPoolExecutor(max_workers=min(6, len(test_matrix))) as pool:
            futures = [
                (name, pool.submit(subprocess.run, cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=30))
                for name, cmd in test_matrix
            ]
            results = {name: fut.result() for name, fut in futures}

        # 逐项严格断言合法 JSON 与业务结构契约
        for name, res in results.items():
            self.assertEqual(res.returncode, 0, f"Command [{name}] exited with code {res.returncode}:\nstderr: {res.stderr}\nstdout: {res.stdout}")
            # 断言纯 JSON 输出 (无额外 print/log 污染)
            clean_stdout = res.stdout.strip()
            self.assertTrue(clean_stdout.startswith("{"), f"Command [{name}] output does not start with '{{':\n{res.stdout}")
            self.assertTrue(clean_stdout.endswith("}"), f"Command [{name}] output does not end with '}}':\n{res.stdout}")
            try:
                data = json.loads(clean_stdout)
            except Exception as exc:
                self.fail(f"Command [{name}] output failed json.loads: {exc}\nstdout:\n{res.stdout}")

            # 专用契约断言
            if name == "tips":
                self.assertEqual(data.get("status"), "success")
                self.assertGreaterEqual(len(data.get("tips", [])), 3)
            elif name == "validate-model":
                self.assertEqual(data.get("status"), "success")
                self.assertEqual(data.get("model_name"), "Kronos")
            elif name == "intent":
                self.assertIn("primary_intent", data)
                self.assertIn("600519", data.get("detected_codes", []))
            elif name == "funnel":
                self.assertEqual(data.get("status"), "valid")
                self.assertIn("stages", data)
            elif name in ("pool_list", "pool_audit"):
                self.assertEqual(data.get("status"), "success")
                self.assertIn("pools", data)
            elif name == "trade_balance":
                self.assertEqual(data.get("status"), "success")
                self.assertIn("total_asset", data.get("data", {}))
            elif name == "report":
                self.assertEqual(data.get("status"), "success")
                self.assertTrue(data.get("report_path", "").endswith(".html"))
            elif name == "action":
                # 实战交易三原则之一：精确最低保本卖出价
                self.assertGreater(data.get("breakeven_price", 0), 0)
                self.assertIn("action_items", data)
                self.assertIn("downside_diagnosis", data)
            elif name == "chenxiaoqun":
                # 实战交易三原则强制断言：保本价 + 三级止损 + 三场景动作单
                self.assertGreater(data.get("breakeven_price", 0), 0)
                risk_ctrl = data.get("risk_control", {})
                self.assertIn("t0_warning_line", risk_ctrl)
                self.assertIn("t1_reduce_line", risk_ctrl)
                self.assertIn("t2_cut_line", risk_ctrl)
                scenarios = data.get("three_scenario_actions", {})
                self.assertIn("open_rush", scenarios)
                self.assertIn("intraday_consolidation", scenarios)
                self.assertIn("sudden_drop", scenarios)


if __name__ == "__main__":
    unittest.main()
