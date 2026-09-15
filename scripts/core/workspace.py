# -*- coding: utf-8 -*-
"""
Workspace in-place discovery manager for a_stock_agents.
Handles cross-platform setup of .agents/skills link (symlink/junction)
and verifies that third-party AI platforms (Antigravity, Hermes, Codex, Claude Code)
can discover and execute skills without polluting global system skill directories.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Tuple

def _find_project_root() -> Path:
    if os.environ.get("A_STOCK_AGENTS_ROOT"):
        return Path(os.environ["A_STOCK_AGENTS_ROOT"]).resolve()
    curr = Path(__file__).resolve().parent
    for p in [curr] + list(curr.parents):
        if (p / "pyproject.toml").exists() or (p / "AGENTS.md").exists():
            return p
    return curr.parent.parent

PROJECT_ROOT = _find_project_root()


# ---------------------------------------------------------------------------
# 三大运行时目录常量 (Three-Bucket Discipline)
# ---------------------------------------------------------------------------
# output/  用户最终交付物唯一落盘区（报告/股池/持仓/回测/缓存）
# log/     运行时观测唯一沉淀区（系统日志/CLI 轨迹/监控/审计）
# temp/    可重建中间产物暂存区（导出/下载/临时缓存，会话结束清理）
OUTPUT_DIR: Path = PROJECT_ROOT / "output"
LOG_DIR: Path = PROJECT_ROOT / "log"
TEMP_DIR: Path = PROJECT_ROOT / "temp"


def ensure_workspace_dirs() -> None:
    """惰性创建 output/log/temp 三大目录，避免空目录缺失影响下游 IO。"""
    for d in (OUTPUT_DIR, LOG_DIR, TEMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def get_log_path(module: str = "app", session_id: str | None = None) -> Path:
    """生成按 (模块名 + 会话 ID 或日期) 分文件的日志路径，统一落入 log/。"""
    ensure_workspace_dirs()
    sub = LOG_DIR / module
    sub.mkdir(parents=True, exist_ok=True)
    tag = session_id or __import__("datetime").datetime.now().strftime("%Y%m%d")
    return sub / f"{module}-{tag}.log"


def get_temp_path(name: str = "scratch") -> Path:
    """生成 temp/ 下的子目录路径，用于可重建的中间产物；会话结束应清理。"""
    ensure_workspace_dirs()
    p = TEMP_DIR / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup_workspace_mount() -> Tuple[bool, str]:
    """
    Ensures .agents/skills is present and root skills compatibility link exists.
    Returns (success: bool, message: str).
    """
    agents_dir = PROJECT_ROOT / ".agents"
    agents_skills = agents_dir / "skills"
    root_skills = PROJECT_ROOT / "skills"

    agents_dir.mkdir(exist_ok=True)

    # 1. If .agents/skills is already a physical directory with skills
    if agents_skills.exists() and agents_skills.is_dir() and not agents_skills.is_symlink():
        return True, ".agents/skills is physical primary entity"

    # 2. Legacy fallback: if root_skills exists physically, map .agents/skills to it
    if root_skills.exists() and not root_skills.is_symlink():
        mount_target = agents_skills
        is_link = mount_target.is_symlink() or (hasattr(mount_target, 'is_junction') and mount_target.is_junction())
        if is_link:
            try:
                if mount_target.resolve() == root_skills.resolve():
                    return True, f".agents/skills is already correctly mounted to {root_skills.name}"
            except Exception:
                pass
            try:
                mount_target.unlink()
            except Exception:
                pass

        is_windows = platform.system() == "Windows"
        if is_windows:
            try:
                cmd = f'cmd /c mklink /J "{mount_target}" "{root_skills}"'
                ret = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if ret.returncode == 0 and mount_target.exists():
                    return True, "Created Windows Directory Junction: .agents/skills -> skills"
            except Exception:
                pass
            try:
                os.symlink(str(root_skills), str(mount_target), target_is_directory=True)
                return True, "Created Windows Symlink: .agents/skills -> skills"
            except Exception as e:
                return False, f"Windows link creation failed: {e}"
        else:
            try:
                mount_target.symlink_to("../skills", target_is_directory=True)
                return True, "Created POSIX symlink: .agents/skills -> ../skills"
            except Exception as e:
                return False, f"Failed to create symlink: {e}"

    return False, f"Neither .agents/skills nor root skills directory found in {PROJECT_ROOT}"


def check_workspace_health() -> Dict[str, Any]:
    """
    Checks the workspace health for in-place third-party AI execution.
    """
    agents_md = PROJECT_ROOT / "AGENTS.md"
    claude_md = PROJECT_ROOT / "CLAUDE.md"
    agents_skills = PROJECT_ROOT / ".agents" / "skills"
    skills_manifest = PROJECT_ROOT / "config" / "skills_manifest.json"
    if not skills_manifest.exists():
        skills_manifest = PROJECT_ROOT / ".agents" / "manifests" / "skills_manifest.json"
    cli_bin = PROJECT_ROOT / "bin" / ("astock.cmd" if platform.system() == "Windows" else "astock")

    status = {
        "agents_md": agents_md.exists(),
        "claude_md": claude_md.exists(),
        "agents_skills_mounted": agents_skills.exists(),
        "skills_manifest": skills_manifest.exists(),
        "cli_launcher": cli_bin.exists(),
        "total_skills": 0,
    }

    if agents_skills.exists():
        skills = [d.name for d in agents_skills.iterdir() if d.is_dir() and not d.name.startswith(".")]
        status["total_skills"] = len(skills)

    status["is_healthy"] = all([
        status["agents_md"],
        status["agents_skills_mounted"],
        status["skills_manifest"],
        status["cli_launcher"],
        status["total_skills"] >= 15,
    ])
    return status


if __name__ == "__main__":
    ok, msg = setup_workspace_mount()
    print(f"Mount Status: {'OK' if ok else 'FAIL'} - {msg}")
    health = check_workspace_health()
    print(f"Workspace In-Place Health: {health}")
    sys.exit(0 if health["is_healthy"] else 1)
