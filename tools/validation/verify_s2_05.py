#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Verification script for Task S2-05:
Verifies astock-deep-diagnose, astock-portfolio-action, astock-paper-backtest, and upgraded a-stock-agents.
"""
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = PROJECT_ROOT / "skill_bundle" / "skills"

TARGET_SKILLS = [
    "a-stock-agents",
    "astock-deep-diagnose",
    "astock-portfolio-action",
    "astock-paper-backtest",
]

ALL_1PLUS6_SKILLS = [
    "a-stock-agents",
    "astock-market-data",
    "astock-smart-screener",
    "astock-tactical-signals",
    "astock-deep-diagnose",
    "astock-portfolio-action",
    "astock-paper-backtest",
]

def verify_skill(skill_name: str) -> None:
    sdir = SKILLS_ROOT / skill_name
    assert sdir.is_dir(), f"Skill directory missing: {sdir}"
    skill_md = sdir / "SKILL.md"
    assert skill_md.is_file(), f"SKILL.md missing: {skill_md}"
    
    content = skill_md.read_text(encoding="utf-8")
    
    # 1. Frontmatter check
    assert content.startswith("---"), f"{skill_name}: Frontmatter missing opening ---"
    parts = content.split("---", 2)
    assert len(parts) >= 3, f"{skill_name}: Frontmatter malformed"
    fm = parts[1]
    assert "name:" in fm, f"{skill_name}: Frontmatter missing 'name'"
    assert "description:" in fm, f"{skill_name}: Frontmatter missing 'description'"
    assert "compatibility:" in fm, f"{skill_name}: Frontmatter missing 'compatibility'"
    assert "metadata:" in fm, f"{skill_name}: Frontmatter missing 'metadata'"
    
    # 2. Check setup.sh & requirements.txt
    setup_sh = sdir / "setup.sh"
    req_txt = sdir / "requirements.txt"
    if skill_name != "a-stock-agents":
        assert setup_sh.is_file(), f"{skill_name}: setup.sh missing"
        assert req_txt.is_file(), f"{skill_name}: requirements.txt missing"
        
        # 3. Check references directory
        ref_dir = sdir / "references"
        assert ref_dir.is_dir(), f"{skill_name}: references dir missing"
        ref_files = list(ref_dir.glob("*.md"))
        assert len(ref_files) >= 4, f"{skill_name}: references markdown count < 4 (found {len(ref_files)})"
        
        # 4. Check scripts directory
        scripts_dir = sdir / "scripts"
        assert scripts_dir.is_dir(), f"{skill_name}: scripts dir missing"
        script_files = list(scripts_dir.glob("*.py"))
        assert len(script_files) >= 4, f"{skill_name}: scripts count < 4 (found {len(script_files)})"

    # 5. Check markdown relative links
    links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
    for text, link in links:
        if link.startswith("http://") or link.startswith("https://") or link.startswith("#") or link.startswith("mailto:"):
            continue
        # Strip anchors
        clean_link = link.split("#")[0]
        if not clean_link:
            continue
        target_path = (sdir / clean_link).resolve()
        assert target_path.exists(), f"{skill_name}: Broken link '{link}' -> '{target_path}'"

    print(f"  [PASS] {skill_name}: SKILL.md, frontmatter, references & scripts verified")

def main():
    print(f"=== S2-05 Verification: 1 + 6 Skills Audit ===")
    for s in ALL_1PLUS6_SKILLS:
        verify_skill(s)
    print("\nAll 1 + 6 Skills fully conform to structural & link requirements!")

if __name__ == "__main__":
    main()
