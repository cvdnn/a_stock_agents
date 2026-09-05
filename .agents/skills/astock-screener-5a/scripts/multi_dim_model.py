# -*- coding: utf-8 -*-
"""
Single Source of Truth (SSOT) forwarding runner for 5A Multi-dimensional Model.
Delegates directly to core.models.multi_dim_model.
NOTE: For standard screening pipelines and custom pool scans, prefer `screen.py`.
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
        _target_file = _ROOT / "core/models/multi_dim_model.py"
        runpy.run_path(str(_target_file), run_name="__main__")
