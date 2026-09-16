# -*- coding: utf-8 -*-
"""Compatibility entry point forwarding legacy a_stocks.py calls to core.cli."""
from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").exists():
            return candidate
    raise RuntimeError("A-Stock Agents project root not found")


ROOT = _project_root()
for path in (ROOT, ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.cli import main


if __name__ == "__main__":
    main()
