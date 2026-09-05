# -*- coding: utf-8 -*-
"""Forwarding wrapper to scripts/tools/pack.py"""
from __future__ import annotations
import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import tools.pack as _mod
from tools.pack import *  # noqa: F401, F403

if hasattr(_mod, "__all__"):
    __all__ = _mod.__all__
else:
    __all__ = [k for k in dir(_mod) if not k.startswith("__")]

if __name__ == "__main__":
    if hasattr(_mod, "main") and callable(getattr(_mod, "main")):
        getattr(_mod, "main")()
