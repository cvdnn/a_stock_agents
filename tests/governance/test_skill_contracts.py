"""Contract tests for the 18 project-local A-stock skills."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from core.cli import build_parser
from core.governance.models import SkillRiskLevel
from core.governance.skill_registry import SKILL_SCHEMAS, SkillRegistry
from server.agent.tools import TOOL_MAP


ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".agents" / "skills"
MANIFEST_PATH = ROOT / "config" / "skills_manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action.choices


def test_all_18_skills_have_explicit_schema_and_tool_mapping() -> None:
    manifest_ids = {item["id"] for item in _manifest()["skills"]}

    assert len(manifest_ids) == 18
    assert set(SKILL_SCHEMAS) == manifest_ids
    for skill_id in manifest_ids:
        assert skill_id in TOOL_MAP
        assert skill_id.replace("-", "_") in TOOL_MAP

    chen_schema = SKILL_SCHEMAS["astock-strategy-chenxiaoqun"]
    assert chen_schema["required"] == ["code"]
    assert {"code", "cost", "shares", "count"} <= set(chen_schema["properties"])


def test_manifest_cli_contracts_parse_with_canonical_examples() -> None:
    parser = build_parser()
    expected_cli = {
        "astock-data-feed": "astock data quote {code}",
        "astock-platform-evaluate": "astock evaluate {code}",
        "astock-screener-5a": "astock screen --dynamic hot_sectors",
        "astock-pool-dashboard": "astock pool list",
        "astock-trade-paper": "astock trade balance",
        "astock-strategy-mainboard": "astock strategy swing",
        "astock-quant-engine": "astock quant pipeline",
        "astock-agent-debate": "astock debate {code}",
        "astock-strategy-tuige": "astock shortline check --code {code}",
        "astock-strategy-macd": "astock pattern macd {code}",
        "astock-action-execution": "astock action --code {code} --cost {cost} --shares {shares}",
        "astock-pool-audit": "astock pool audit",
        "astock-report-archive": "astock report {code}",
        "astock-report-html": "astock report {code}",
        "astock-knowledge-tips": "astock tips",
        "astock-model-validation": "astock validate-model --model {model_name} --code {code}",
        "astock-meta-routing": 'astock intent "{task_description}"',
        "astock-strategy-chenxiaoqun": "astock pattern chenxiaoqun {code}",
    }
    examples = {
        "astock-data-feed": ["data", "quote", "600519", "--json"],
        "astock-platform-evaluate": ["evaluate", "600519", "--json"],
        "astock-screener-5a": ["screen", "--dynamic", "hot_sectors", "--json"],
        "astock-pool-dashboard": ["pool", "list", "--json"],
        "astock-trade-paper": ["trade", "balance", "--json"],
        "astock-strategy-mainboard": ["strategy", "swing", "--code", "600519", "--json"],
        "astock-quant-engine": ["quant", "pipeline", "--code", "600519", "--json"],
        "astock-agent-debate": ["debate", "600519", "--json"],
        "astock-strategy-tuige": ["shortline", "check", "--code", "600519", "--json"],
        "astock-strategy-macd": ["pattern", "macd", "600519", "--json"],
        "astock-action-execution": ["action", "--code", "600519", "--cost", "10", "--shares", "100", "--json"],
        "astock-pool-audit": ["pool", "audit", "--json"],
        "astock-report-archive": ["report", "600519", "--json"],
        "astock-report-html": ["report", "600519", "--json"],
        "astock-knowledge-tips": ["tips", "--json"],
        "astock-model-validation": ["validate-model", "--model", "Kronos", "--code", "600519", "--json"],
        "astock-meta-routing": ["intent", "分析这项任务", "--json"],
        "astock-strategy-chenxiaoqun": ["pattern", "chenxiaoqun", "600519", "--json"],
    }

    manifest_cli = {item["id"]: item["cli_command"] for item in _manifest()["skills"]}
    assert manifest_cli == expected_cli
    assert set(examples) == set(manifest_cli)
    for skill_id, argv in examples.items():
        args = parser.parse_args(argv)
        assert args.command, skill_id


def test_write_capable_skills_are_not_classified_readonly() -> None:
    registry = SkillRegistry()

    assert registry.get_skill("astock-pool-audit").risk_level is SkillRiskLevel.FILESYSTEM_WRITE
    assert registry.get_skill("astock-report-archive").risk_level is SkillRiskLevel.FILESYSTEM_WRITE
    assert registry.get_skill("astock-report-html").risk_level is SkillRiskLevel.FILESYSTEM_WRITE
    assert registry.get_skill("astock-trade-paper").risk_level is SkillRiskLevel.SIMULATION
    assert registry.get_skill("astock-pool-audit").require_confirmation is True


def test_skill_directories_do_not_track_runtime_pool_csv_files() -> None:
    runtime_csv = [
        path
        for path in SKILLS_DIR.rglob("*.csv")
        if not path.name.endswith(".csv.example")
    ]
    assert runtime_csv == []


def test_skill_markdown_has_no_broken_relative_links_or_legacy_roots() -> None:
    broken: list[str] = []
    legacy: list[str] = []
    banned = (
        r"skills/a-stocks",
        r"(?<!\.agents/)skills/astock-",
        r"\$HOME/my_holdings",
        r"~/多智能体辩论框架",
    )

    for path in SKILLS_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            target = target.strip().strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "file:", "#")):
                continue
            resolved = path.parent / target.split("#", 1)[0]
            if not resolved.exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
        for marker in banned:
            if re.search(marker, text):
                legacy.append(f"{path.relative_to(ROOT)} -> {marker}")

    assert broken == []
    assert legacy == []


def test_skill_runtime_assets_do_not_reference_global_runtime_roots() -> None:
    banned = (
        ".AI-Platform",
        "AppData/Local/AI-Platform",
        "a-share-dashboard/data",
        "skills/a-share-data",
    )
    violations: list[str] = []
    text_suffixes = {".md", ".py", ".sh", ".yaml", ".yml"}
    for scan_root in (SKILLS_DIR, ROOT / "scripts" / "core"):
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in banned:
                if marker in text:
                    violations.append(f"{path.relative_to(ROOT)} -> {marker}")

    assert violations == []


def test_cli_exposes_missing_skill_command_groups() -> None:
    commands = _subcommands(build_parser())
    assert {"strategy", "quant", "shortline", "tips", "validate-model"} <= set(commands)
    assert "audit" in _subcommands(commands["pool"])


def test_large_skill_entrypoints_use_progressive_disclosure() -> None:
    for skill_id in ("astock-data-feed", "astock-platform-evaluate"):
        skill_dir = SKILLS_DIR / skill_id
        entry_lines = (skill_dir / "SKILL.md").read_text(encoding="utf-8").splitlines()
        assert len(entry_lines) <= 180, f"{skill_id} entrypoint is too large: {len(entry_lines)} lines"
        assert (skill_dir / "references" / "full-reference.md").exists()
