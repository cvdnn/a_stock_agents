# -*- coding: utf-8 -*-
"""
Global pytest fixtures and sys.path initialization.
Ensures src/ and src/core/ are always on sys.path for test runners.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

for p in [ROOT, SCRIPTS, SCRIPTS / "core", ROOT / "core"]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))
