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

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def setup_workspace_mount() -> Tuple[bool, str]:
    """
    Ensures .agents/skills is mapped to ./skills in a cross-platform manner.
    Returns (success: bool, message: str).
    """
    agents_dir = PROJECT_ROOT / ".agents"
    skills_dir = PROJECT_ROOT / "skills"
    mount_target = agents_dir / "skills"

    if not skills_dir.exists():
        return False, f"Source skills directory missing: {skills_dir}"

    agents_dir.mkdir(exist_ok=True)

    # Check if junction/symlink exists and is valid
    is_link = mount_target.is_symlink() or (hasattr(mount_target, 'is_junction') and mount_target.is_junction())
    if is_link:
        try:
            resolved = mount_target.resolve()
            if resolved == skills_dir.resolve():
                return True, f".agents/skills is already correctly mounted to {skills_dir.name}"
        except Exception:
            pass
        # Broken link, remove and recreate
        try:
            if mount_target.is_dir() and not mount_target.is_symlink():
                os.rmdir(mount_target)
            else:
                mount_target.unlink()
        except Exception:
            pass

    if mount_target.exists():
        if mount_target.resolve() == skills_dir.resolve():
            return True, ".agents/skills points to skills"

    is_windows = platform.system() == "Windows"

    if is_windows:
        # On Windows, try Directory Junction first (no elevated privileges needed)
        try:
            cmd = f'cmd /c mklink /J "{mount_target}" "{skills_dir}"'
            ret = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if ret.returncode == 0 and mount_target.exists():
                return True, "Created Windows Directory Junction: .agents/skills -> skills"
        except Exception:
            pass

        # Fallback to python os.symlink
        try:
            os.symlink(str(skills_dir), str(mount_target), target_is_directory=True)
            return True, "Created Windows Symlink: .agents/skills -> skills"
        except Exception as e:
            return False, f"Windows link creation failed (privilege required or dev mode): {e}"
    else:
        # Unix / macOS: create relative symlink ../skills
        try:
            mount_target.symlink_to("../skills", target_is_directory=True)
            return True, "Created POSIX symlink: .agents/skills -> ../skills"
        except Exception:
            try:
                mount_target.symlink_to(skills_dir, target_is_directory=True)
                return True, f"Created absolute POSIX symlink: .agents/skills -> {skills_dir}"
            except Exception as e2:
                return False, f"Failed to create symlink: {e2}"


def check_workspace_health() -> Dict[str, Any]:
    """
    Checks the workspace health for in-place third-party AI execution.
    """
    agents_md = PROJECT_ROOT / "AGENTS.md"
    claude_md = PROJECT_ROOT / "CLAUDE.md"
    agents_skills = PROJECT_ROOT / ".agents" / "skills"
    skills_manifest = PROJECT_ROOT / "config" / "skills_manifest.json"
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
