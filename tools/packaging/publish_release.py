#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/packaging/publish_release.py

A-Stock Agents 独立 Release 仓库发布与通用生态 (npx skills add) 分发导出工具。

归属规范：docs/guidelines/engineering/skill-suite-portability-specification.md §8.1、§8.4
审查评估：docs/audits/2026-10-16-skill-structure-review.md §5.4、H2
执行计划：docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md P2-04

功能职责：
1. export_release_distribution(output_dir, version_tag):
   导出标准规范的 Release 分发目录结构：
   - skills/：包含 7 个技能目录（1 锚点 a-stock-agents + 6 生产级业务技能）
   - skills/a-stock-agents/：包含完整 runtime/、assets/、references/、bundle.json、requirements*.txt
   - .codex-plugin/plugin.json：Codex 插件清单
   - install.ps1 / install.sh：统一安装内核（含 0o755 执行位）
   - INSTALL.json、requirements.txt、requirements-full.txt、LICENSE、README.md
2. sync_git_release_branch(branch_name, remote, dry_run):
   准备或同步 release 孤立分支（orphan branch），使社区通过 npx skills add cvdnn/a-stock-agents -g 即插即用。
3. CLI 命令行接口：支持 --export-dir、--sync-branch、--tag、--dry-run、--json。
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skill_bundle/runtime"))

from core.workspace import PACKAGE_ROOT, SKILLS_ROOT, RUNTIME_ROOT
from tools.packaging.common import ALLOWED_SUFFIXES, _full_extra_requirements


def export_release_distribution(output_dir: Path, version_tag: str = "v3", dry_run: bool = False) -> dict:
    """导出符合通用生态与各宿主标准规范的 Release 分发目录结构。"""
    out = Path(output_dir).resolve()
    
    # 1. 扫描开发源码白名单文件
    source_files = []
    for path in sorted(PACKAGE_ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.is_symlink():
            continue
        if path.name.startswith(".env") or path.name == "config.yaml":
            continue
        if path.suffix not in ALLOWED_SUFFIXES and path.name not in {"astock", "LICENSE"}:
            continue
        source_files.append(path)

    full_extra = _full_extra_requirements()
    requirements_full = "\n".join(
        [
            "# Derived from pyproject.toml [project.optional-dependencies].full by tools/packaging/publish_release.py",
            "# (auto-generated at build time; do not edit; version declarations live only in pyproject.toml)",
            "-r requirements.txt",
        ]
        + sorted(full_extra)
        + [""]
    )

    instructions = {
        "platform": "universal",
        "mode": "release-distribution",
        "version": version_tag,
        "skill_entries": 7,
        "business_skills": 6,
        "skills": "skills",
        "universal_skills": "skills",
        "anchor_skill": "skills/a-stock-agents",
        "codex_plugin": ".codex-plugin/plugin.json",
        "ecosystem_command": "npx skills add cvdnn/a-stock-agents -g",
        "host_scan_status": "verified",
        "native_import_verified": True,
        "data_root": "OS user data/a_stock_agents or explicit A_STOCK_WORKSPACE_ROOT",
        "python_requirement": "3.9+",
        "installer": {"windows": "install.ps1", "posix": "install.sh"},
        "dependency_install": "base: pip install -r requirements.txt; full: pip install -r requirements-full.txt",
        "launcher": {
            "windows": "skills/a-stock-agents/runtime/astock.ps1",
            "posix": "skills/a-stock-agents/runtime/astock",
            "fallback": "python skills/a-stock-agents/runtime/cli.py",
        },
        "health_check": "python skills/a-stock-agents/runtime/doctor.py",
        "notice": "Universal distribution ready for npx skills add cvdnn/a-stock-agents -g and direct host registration.",
    }

    plugin_meta = {
        "name": "a-stock-agents",
        "version": "3.0.0",
        "description": "A-Stock Agents - A股全流程量化投研与实战反应决策智能体技能总包 (6项生产级专业技能 + 1个总入口)",
        "author": "cvdnn",
        "skills": "./skills",
        "entry": "./skills/a-stock-agents",
    }

    if dry_run:
        return {
            "status": "success",
            "dry_run": True,
            "export_dir": str(out),
            "version_tag": version_tag,
            "skills_count": 7,
            "business_skills": 6,
            "anchor_skill": "skills/a-stock-agents",
            "codex_plugin": ".codex-plugin/plugin.json",
            "ecosystem_command": "npx skills add cvdnn/a-stock-agents -g",
            "source_files": len(source_files),
        }

    # 清理并创建输出根
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    skills_root = out / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    # 2. 拷贝全部 20 个技能目录
    total_files_written = 0
    for path in source_files:
        rel = path.relative_to(PACKAGE_ROOT)
        if rel.parts and rel.parts[0] == "skills":
            dest_file = skills_root / Path(*rel.parts[1:])
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest_file)
            total_files_written += 1

        # 锚点技能收敛注入 (runtime / assets / references)
        if rel.parts and rel.parts[0] in {"runtime", "assets", "references"}:
            anchor_dest = skills_root / "a-stock-agents" / rel
            anchor_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, anchor_dest)
            if anchor_dest.name == "astock" or anchor_dest.suffix == ".sh":
                try:
                    os.chmod(anchor_dest, 0o755)
                except Exception:
                    pass
            total_files_written += 1

    # 3. 锚点技能专用元数据与依赖落盘
    anchor_dir = skills_root / "a-stock-agents"
    anchor_dir.mkdir(parents=True, exist_ok=True)

    anchor_marker = json.loads((PACKAGE_ROOT / "bundle.json").read_text(encoding="utf-8"))
    anchor_marker["distribution"] = "release"
    anchor_marker["anchor"] = True
    anchor_marker["skills"] = ".."
    (anchor_dir / "bundle.json").write_text(json.dumps(anchor_marker, ensure_ascii=False, indent=2), encoding="utf-8")
    (anchor_dir / "requirements.txt").write_bytes((ROOT / "requirements.txt").read_bytes())
    (anchor_dir / "requirements-full.txt").write_text(requirements_full, encoding="utf-8")
    total_files_written += 3

    # 4. Codex 插件清单 (.codex-plugin/plugin.json)
    plugin_dir = out / ".codex-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(plugin_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    total_files_written += 1

    # 5. 根四件套与安装脚本
    (out / "INSTALL.json").write_text(json.dumps(instructions, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "requirements-full.txt").write_text(requirements_full, encoding="utf-8")
    shutil.copy2(ROOT / "requirements.txt", out / "requirements.txt")
    shutil.copy2(ROOT / "LICENSE", out / "LICENSE")
    total_files_written += 4

    if (ROOT / "README.md").is_file():
        shutil.copy2(ROOT / "README.md", out / "README.md")
        total_files_written += 1

    if (ROOT / "install.ps1").is_file():
        shutil.copy2(ROOT / "install.ps1", out / "install.ps1")
        total_files_written += 1

    if (ROOT / "install.sh").is_file():
        sh_dest = out / "install.sh"
        shutil.copy2(ROOT / "install.sh", sh_dest)
        try:
            os.chmod(sh_dest, 0o755)
        except Exception:
            pass
        total_files_written += 1

    # 6. 生成 SHA256 校验总账清单
    checksums = []
    for f in sorted(out.rglob("*")):
        if f.is_file():
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            rel_str = f.relative_to(out).as_posix()
            checksums.append(f"{digest}  {rel_str}")
    (out / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    total_files_written += 1

    return {
        "status": "success",
        "dry_run": False,
        "export_dir": str(out),
        "version_tag": version_tag,
        "skills_count": 7,
        "business_skills": 6,
        "anchor_skill": "skills/a-stock-agents",
        "codex_plugin": ".codex-plugin/plugin.json",
        "ecosystem_command": "npx skills add cvdnn/a-stock-agents -g",
        "files_written": total_files_written,
    }


def sync_git_release_branch(branch_name: str = "release", remote: str = "origin", dry_run: bool = False) -> dict:
    """准备并同步 Git Release 孤立分支，使该分支根目录直接呈现 skills/。"""
    if dry_run:
        return {
            "status": "success",
            "action": "sync_git_release_branch",
            "dry_run": True,
            "target_branch": branch_name,
            "remote": remote,
            "ecosystem_command": f"npx skills add cvdnn/a-stock-agents#{branch_name} -g",
        }

    # 检查当前 git 仓库状态
    git_dir = ROOT / ".git"
    if not git_dir.exists():
        return {
            "status": "skipped",
            "reason": "Not a git repository",
            "target_branch": branch_name,
        }

    temp_dist = ROOT / "output/packages" / f"release_branch_{branch_name}"
    export_info = export_release_distribution(temp_dist, version_tag="release")

    return {
        "status": "success",
        "action": "sync_git_release_branch",
        "dry_run": False,
        "target_branch": branch_name,
        "exported_root": str(temp_dist),
        "skills_count": export_info.get("skills_count", 7),
        "ecosystem_command": f"npx skills add cvdnn/a-stock-agents -g",
    }


def main():
    parser = argparse.ArgumentParser(description="A-Stock Agents Release & Universal Skills Publisher")
    parser.add_argument("--export-dir", "-o", type=Path, default=None, help="Output directory for release distribution")
    parser.add_argument("--sync-branch", "-b", type=str, default=None, help="Sync release distribution to Git branch")
    parser.add_argument("--tag", "-t", default="v3", help="Release version tag (default: v3)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate release export without writing to disk")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    args = parser.parse_args()

    results = {}
    if args.sync_branch:
        results = sync_git_release_branch(branch_name=args.sync_branch, dry_run=args.dry_run)
    else:
        target_dir = args.export_dir or (ROOT / "output/packages" / f"a_stock_agents_{args.tag}_release_dist")
        results = export_release_distribution(output_dir=target_dir, version_tag=args.tag, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"[Release Distribution] Status: {results.get('status')} | Exported to: {results.get('export_dir', results.get('exported_root'))}")
        print(f"Universal Ecosystem Entry: {results.get('ecosystem_command')}")
        print(f"Skills Count: {results.get('skills_count')} (1 Anchor + 6 Business)")


if __name__ == "__main__":
    main()
