# -*- coding: utf-8 -*-
"""
Skill execution runner for a_stock_agents.
Executes scripts belonging to specific skills dynamically.
"""

import sys
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / 'skills'

def list_skills():
    print("Available Skills:")
    for s in sorted(SKILLS_DIR.iterdir()):
        if s.is_dir() and (s / 'SKILL.md').exists():
            print(f"  - {s.name}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_skill.py <skill-name> [script-args...]")
        print("       python run_skill.py --list")
        sys.exit(1)
        
    if sys.argv[1] in ['--list', '-l', 'list']:
        list_skills()
        return

    skill_name = sys.argv[1]
    skill_path = SKILLS_DIR / skill_name
    if not skill_path.exists():
        print(f"Error: Skill '{skill_name}' not found in {SKILLS_DIR}")
        list_skills()
        sys.exit(1)

    print(f"[Skill Runner] Executing skill: {skill_name}")
    skill_md = skill_path / 'SKILL.md'
    if skill_md.exists():
        print(f"Skill definition: {skill_md}")

if __name__ == '__main__':
    main()
