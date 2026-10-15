# -*- coding: utf-8 -*-
"""
Single Source of Truth (SSOT) forwarding wrapper.
Delegates to core.governance.skill_registry.
"""
from __future__ import annotations

import sys as _astock_sys
from pathlib import Path as _AstPath
_astock_bundle = next((p for p in _AstPath(__file__).resolve().parents if (p / "bundle.json").is_file()), None)
if _astock_bundle is None:
    raise RuntimeError("Complete a_stock_agents bundle required")
_astock_runtime = _astock_bundle / "runtime"
if str(_astock_runtime) not in _astock_sys.path:
    _astock_sys.path.insert(0, str(_astock_runtime))
from core.workspace import PROJECT_ROOT, RUNTIME_ROOT
_ROOT = PROJECT_ROOT

import core.governance.skill_registry as _core_mod
from core.governance.skill_registry import *  # noqa: F401, F403

if hasattr(_core_mod, "__all__"):
    __all__ = _core_mod.__all__
else:
    __all__ = [k for k in dir(_core_mod) if not k.startswith("__")]

if __name__ == "__main__":
    if hasattr(_core_mod, "main") and callable(getattr(_core_mod, "main")):
        getattr(_core_mod, "main")()
    else:
        import runpy
        _rel = "governance.skill_registry".replace(".", "/") + ".py"
        _target_file = _AstPath(_core_mod.__file__)
        runpy.run_path(str(_target_file), run_name="__main__")
