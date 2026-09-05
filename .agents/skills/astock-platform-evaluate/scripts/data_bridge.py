# -*- coding: utf-8 -*-
"""
Single Source of Truth (SSOT) forwarding wrapper.
Delegates to core.data.data_bridge.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Find project root dynamically
_cur = Path(__file__).resolve().parent
while _cur.parent != _cur:
    if (_cur / "pyproject.toml").exists() and (_cur / "core").exists():
        _ROOT = _cur
        break
    _cur = _cur.parent
else:
    _ROOT = Path(__file__).resolve().parents[3]

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(_ROOT / "core"))

import core.data.data_bridge as _core_mod
from core.data.data_bridge import *  # noqa: F401, F403

if hasattr(_core_mod, "__all__"):
    __all__ = _core_mod.__all__
else:
    __all__ = [k for k in dir(_core_mod) if not k.startswith("__")]

if __name__ == "__main__":
    if hasattr(_core_mod, "main") and callable(getattr(_core_mod, "main")):
        getattr(_core_mod, "main")()
    else:
        import runpy
        _target_file = _ROOT / "core/data/data_bridge.py"
        runpy.run_path(str(_target_file), run_name="__main__")
