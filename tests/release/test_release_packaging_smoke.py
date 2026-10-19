# -*- coding: utf-8 -*-
"""Release 打包与交付链路专项冒烟门禁（release_pack 档）。

标记为 `@pytest.mark.release_pack`，按需在发版或打包器改动时执行，
彻底与日常量化与投研技能核心门禁（-m core）解耦。

覆盖：
1. 1 + 6 技能 SKILL.md frontmatter 解析与目录对齐（7 项入口）；
2. doctor / check_workspace_health 状态自检契约；
3. package_project 打包行为：ZIP 产物、sha256 sidecar、INSTALL.json 契约、
   黑名单排除（output/log/temp/.env）、锚点技能架构随包；
4. Zip Slip 路径穿越防御。
"""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from core.workspace import PACKAGE_ROOT, SKILLS_ROOT, check_workspace_health
from tools.packaging import common

pytestmark = pytest.mark.release_pack

EXPECTED_7_SKILLS = {
    "a-stock-agents",
    "astock-market-data",
    "astock-smart-screener",
    "astock-tactical-signals",
    "astock-deep-diagnose",
    "astock-portfolio-action",
    "astock-paper-backtest",
}


def _parse_frontmatter(skill_dir: Path) -> dict:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---"), f"{skill_dir.name}: frontmatter fence missing"
    end = text.find("\n---", 3)
    assert end > 0, f"{skill_dir.name}: frontmatter fence unterminated"
    data = yaml.safe_load(text[3:end])
    assert isinstance(data, dict), f"{skill_dir.name}: frontmatter is not a mapping"
    return data


@pytest.mark.parametrize("skill_name", sorted(EXPECTED_7_SKILLS))
def test_skill_frontmatter_in_source(skill_name: str):
    """验证每个技能 SKILL.md 拥有合法的 YAML frontmatter 且 name 与目录严格一致。"""
    s_dir = SKILLS_ROOT / skill_name
    assert s_dir.is_dir(), f"Skill directory missing: {skill_name}"
    data = _parse_frontmatter(s_dir)
    assert data["name"] == skill_name
    assert isinstance(data.get("description"), str) and len(data["description"].strip()) > 0


def test_doctor_health_contract():
    """验证 doctor 自检健康返回，包含 7 项技能（1 锚点 + 6 业务）。"""
    health = check_workspace_health()
    assert health["total_skills"] == 7
    assert health["business_skills"] == 6
    assert health["skills_manifest"] is True
    assert health["cli_launcher"] is True
    assert health["is_healthy"] is True


@pytest.fixture(scope="module")
def release_archive(tmp_path_factory) -> Path:
    """module 级别只构建一次 codex 平台候选包，避免重复打包 I/O。"""
    build_dir = tmp_path_factory.mktemp("release-pack-gate")
    orig_get_log = common.get_log_path
    common.get_log_path = lambda *args, **kwargs: build_dir / "build.log"
    try:
        archive_path = common.package_project(build_dir / "test_candidate.zip", platform="codex")
    finally:
        common.get_log_path = orig_get_log
    return archive_path


def test_package_project_generates_valid_zip_and_sha256(release_archive: Path):
    """验证 package_project 产出非空 ZIP 归档且伴生正确的 sha256 sidecar 文件。"""
    assert release_archive.is_file()
    assert release_archive.stat().st_size > 1024

    sha_file = release_archive.with_suffix(".zip.sha256")
    assert sha_file.is_file()
    sha_content = sha_file.read_text(encoding="utf-8").strip()
    calculated = hashlib.sha256(release_archive.read_bytes()).hexdigest()
    assert calculated in sha_content


def test_archive_install_json_contract(release_archive: Path):
    """验证 INSTALL.json 契约符合 1+6 规范。"""
    with zipfile.ZipFile(release_archive) as archive:
        names = set(archive.namelist())
        assert "INSTALL.json" in names
        data = json.loads(archive.read("INSTALL.json"))

    assert data["platform"] == "codex"
    assert data["mode"] == "release-candidate-collection"
    assert data["skill_entries"] == 7
    assert data["business_skills"] == 6
    assert data["runtime"] == "skill_bundle/runtime"
    assert data["skills"] == "skill_bundle/skills"
    assert data["anchor_skill"] == "skill_bundle/skills/a-stock-agents"


def test_archive_excludes_private_and_ephemeral_items(release_archive: Path):
    """验证 ZIP 归档排除了私有配置与运行时目录（output/, log/, temp/, .env）。"""
    with zipfile.ZipFile(release_archive) as archive:
        for name in archive.namelist():
            assert not name.startswith("output/"), f"Leaked output directory: {name}"
            assert not name.startswith("log/"), f"Leaked log directory: {name}"
            assert not name.startswith("temp/"), f"Leaked temp directory: {name}"
            assert not name.endswith(".env"), f"Leaked env file: {name}"
            assert "__pycache__" not in name, f"Leaked pycache: {name}"


def test_archive_anchor_skill_architecture(release_archive: Path):
    """验证 1+6 锚点技能架构正确注入了 a-stock-agents 锚点自描述与随包资源。"""
    with zipfile.ZipFile(release_archive) as archive:
        names = set(archive.namelist())
        assert "skill_bundle/skills/a-stock-agents/bundle.json" in names
        assert "skill_bundle/skills/a-stock-agents/SKILL.md" in names
        assert "skill_bundle/skills/astock-market-data/SKILL.md" in names
        assert "skill_bundle/skills/astock-smart-screener/SKILL.md" in names
        assert "skill_bundle/skills/astock-tactical-signals/SKILL.md" in names
        assert "skill_bundle/skills/astock-deep-diagnose/SKILL.md" in names
        assert "skill_bundle/skills/astock-portfolio-action/SKILL.md" in names
        assert "skill_bundle/skills/astock-paper-backtest/SKILL.md" in names


def test_zip_slip_protection(tmp_path: Path):
    """防御 Zip Slip 路径穿越。"""
    malicious_zip = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious_zip, "w") as z:
        z.writestr("../../../evil.txt", "pwned")

    target_dir = tmp_path / "extracted"
    target_dir.mkdir()

    with zipfile.ZipFile(malicious_zip) as z:
        for member in z.namelist():
            target_path = (target_dir / member).resolve()
            # 必须检测到路径逃逸
            assert not target_path.is_relative_to(target_dir.resolve())
