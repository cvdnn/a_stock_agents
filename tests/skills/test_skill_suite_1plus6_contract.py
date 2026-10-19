# -*- coding: utf-8 -*-
"""
tests/skills/test_skill_suite_1plus6_contract.py
Verification gate for SPEC-SKILL-002 S2-06:
- 1 + 6 physical directories structure verification
- skills_manifest.json 6 business skills and legacy_aliases conformance
- doctor.py health check (total_skills: 7, business_skills: 6, is_healthy: true)
- SkillRegistry 1+6 registration & 19 legacy aliases lookup
- CLI skill list --json contract
- Tools async execution of 1+6 skills and legacy aliases
"""
import json
import subprocess
import sys
from pathlib import Path
import pytest

from core.workspace import PACKAGE_ROOT, SKILLS_ROOT, MANIFEST_PATH, check_workspace_health
from core.governance.skill_registry import SkillRegistry, LEGACY_SKILL_ALIASES
from core.execution.tools import TOOL_MAP, execute_tool

EXPECTED_7_SKILLS = {
    "a-stock-agents",
    "astock-market-data",
    "astock-smart-screener",
    "astock-tactical-signals",
    "astock-deep-diagnose",
    "astock-portfolio-action",
    "astock-paper-backtest",
}

EXPECTED_6_BUSINESS_SKILLS = {
    "astock-market-data",
    "astock-smart-screener",
    "astock-tactical-signals",
    "astock-deep-diagnose",
    "astock-portfolio-action",
    "astock-paper-backtest",
}

OLD_19_SKILLS = {
    "astock-data-feed",
    "astock-platform-evaluate",
    "astock-screener-5a",
    "astock-quant-engine",
    "astock-action-execution",
    "astock-strategy-macd",
    "astock-strategy-tuige",
    "astock-strategy-chenxiaoqun",
    "astock-strategy-mainboard",
    "astock-pool-dashboard",
    "astock-pool-audit",
    "astock-trade-paper",
    "astock-agent-debate",
    "astock-report-html",
    "astock-report-archive",
    "astock-meta-routing",
    "astock-knowledge-tips",
    "astock-model-validation",
    "astock-selection-model",
}


def test_skills_directory_structure_is_strictly_1plus6():
    """验证 skill_bundle/skills 下物理精确为 1+6 共 7 个目录，旧 19 目录已完全清退。"""
    actual_dirs = {d.name for d in SKILLS_ROOT.iterdir() if d.is_dir() and not d.name.startswith(".")}
    assert actual_dirs == EXPECTED_7_SKILLS, f"Skills 目录不符合 1+6 预期: {actual_dirs ^ EXPECTED_7_SKILLS}"

    for s_name in EXPECTED_7_SKILLS:
        s_dir = SKILLS_ROOT / s_name
        skill_md = s_dir / "SKILL.md"
        assert skill_md.is_file(), f"{s_name} 缺少 SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{s_name} SKILL.md 缺少 Frontmatter"
        assert f"name: {s_name}" in content, f"{s_name} SKILL.md name 声明不匹配"

        if s_name != "a-stock-agents":
            ref_dir = s_dir / "references"
            assert ref_dir.is_dir(), f"{s_name} 缺少 references 目录"
            refs = list(ref_dir.glob("*.md"))
            assert len(refs) >= 4, f"{s_name} references 文档少于 4 篇: {len(refs)}"


def test_skills_manifest_json_conformance():
    """验证 skills_manifest.json 权威清单声明 6 项业务技能，并完整包含 research_stage 与 legacy_aliases。"""
    assert MANIFEST_PATH.is_file(), "skills_manifest.json 缺失"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("total_skills") == 6
    skills = data.get("skills", [])
    assert len(skills) == 6

    declared_ids = {item["id"] for item in skills}
    assert declared_ids == EXPECTED_6_BUSINESS_SKILLS

    collected_aliases = set()
    for item in skills:
        assert "research_stage" in item, f"{item['id']} 缺少 research_stage 字段"
        assert "legacy_aliases" in item, f"{item['id']} 缺少 legacy_aliases 字段"
        for alias in item["legacy_aliases"]:
            collected_aliases.add(alias)

    # 包含 a-stock-agents 的两项别名
    collected_aliases.update(["astock-meta-routing", "astock-knowledge-tips"])
    assert collected_aliases == OLD_19_SKILLS, f"旧 19 别名覆盖不全: {OLD_19_SKILLS ^ collected_aliases}"


def test_doctor_workspace_health_is_healthy():
    """验证 check_workspace_health 输出 total_skills: 7, business_skills: 6, is_healthy: True。"""
    health = check_workspace_health()
    assert health["total_skills"] == 7
    assert health["business_skills"] == 6
    assert health["skills_manifest"] is True
    assert health["cli_launcher"] is True
    assert health["is_healthy"] is True


def test_skill_registry_aliases_and_lookup():
    """验证 SkillRegistry 正确加载 6 项业务技能，并支持 19 项旧别名无损查询。"""
    registry = SkillRegistry()
    skills = registry.list_skills()
    assert len(skills) == 6

    # 1. 验证 6 项业务技能可查询
    for sid in EXPECTED_6_BUSINESS_SKILLS:
        meta = registry.get_skill(sid)
        assert meta is not None, f"无法查询 1+6 技能: {sid}"
        assert meta.id == sid

    # 2. 验证 19 项旧别名映射全部生效
    assert set(LEGACY_SKILL_ALIASES.keys()) == OLD_19_SKILLS
    for old_id, new_id in LEGACY_SKILL_ALIASES.items():
        if new_id != "a-stock-agents":
            meta = registry.get_skill(old_id)
            assert meta is not None, f"旧别名无法解析: {old_id}"
            assert meta.id == new_id, f"旧别名 {old_id} 未映射到 {new_id}，实际映射为 {meta.id}"


def test_tools_map_and_execution_resolution():
    """验证 TOOL_MAP 与 execute_tool 正确注册 1+6 技能并在旧别名下安全执行。"""
    for sid in EXPECTED_6_BUSINESS_SKILLS:
        assert sid in TOOL_MAP or sid.replace("-", "_") in TOOL_MAP

    for old_id in OLD_19_SKILLS:
        assert old_id in TOOL_MAP or old_id.replace("-", "_") in TOOL_MAP


@pytest.mark.asyncio
async def test_async_execute_tool_new_and_legacy():
    """测试通过 execute_tool 异步执行新旧技能名称。"""
    # 1. 执行新技能 astock_market_data
    res_new = await execute_tool("astock_market_data", {"code": "600519", "action": "quote"})
    assert res_new.get("status") == "success"
    assert res_new.get("code") == "600519"

    # 2. 执行旧别名 astock_data_feed
    res_old = await execute_tool("astock_data_feed", {"code": "600519", "action": "quote"})
    assert res_old.get("status") == "success"
    assert res_old.get("code") == "600519"
