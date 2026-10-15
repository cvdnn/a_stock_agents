# -*- coding: utf-8 -*-
"""
Single Source of Truth (SSOT) forwarding runner for 5A Multi-dimensional Model.
Delegates directly to core.models.multi_dim_model.
NOTE: For standard screening pipelines and custom pool scans, prefer `screen.py`.
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


import sys
from pathlib import Path

# Find project root dynamically
_cur = Path(__file__).resolve().parent
while _cur.parent != _cur:
    if (_cur / "pyproject.toml").exists() or (_cur / "AGENTS.md").exists():
        _ROOT = _cur
        break
    _cur = _cur.parent
else:
    _ROOT = Path(__file__).resolve().parents[3]

for _p in [_ROOT, _ROOT / "skill_bundle" / "runtime", _ROOT / "skill_bundle" / "runtime" / "core", _ROOT / "core"]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import core.models.multi_dim_model as _core_mod
from core.models.multi_dim_model import (
    FiveDimScorer,
    MarketGate,
    RotationBacktest,
    StockSelectionModel,
    StockSelectionV3,
)

__all__ = [
    "MarketGate",
    "FiveDimScorer",
    "StockSelectionModel",
    "StockSelectionV3",
    "RotationBacktest",
]

if __name__ == "__main__":
    if hasattr(_core_mod, "main") and callable(getattr(_core_mod, "main")):
        getattr(_core_mod, "main")()
    else:
        import runpy
        _target_file = (_ROOT / "skill_bundle" / "runtime" / "core" if (_ROOT / "skill_bundle" / "runtime" / "core").exists() else _ROOT / "core") / "models/multi_dim_model.py"
        runpy.run_path(str(_target_file), run_name="__main__")
