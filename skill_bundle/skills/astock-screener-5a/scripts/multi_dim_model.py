# -*- coding: utf-8 -*-
"""
Single Source of Truth (SSOT) forwarding runner for 5A Multi-dimensional Model.
Delegates directly to core.models.multi_dim_model.
NOTE: For standard screening pipelines and custom pool scans, prefer `screen.py`.
"""
from __future__ import annotations

import sys as _astock_sys
import os as _astock_os
import json as _astock_json
from pathlib import Path as _AstPath

def _astock_resolve_bundle():
    _file_path = _AstPath(__file__).resolve()
    # 1. 自定位：自身及父目录向上查找 bundle.json
    for _p in _file_path.parents:
        if (_p / "bundle.json").is_file():
            return _p
    # 2. 兄弟定位：查找兄弟目录 a-stock-agents/bundle.json（未解析/已解析上级均探测）
    for _base in (_AstPath(__file__), _file_path):
        for _p in _base.parents:
            for _candidate in (_p / "a-stock-agents", _p.parent / "a-stock-agents"):
                if (_candidate / "bundle.json").is_file():
                    return _candidate.resolve()
    # 3. 收据定位：读取系统固定安装收据 install.json
    _receipts = []
    _env_root = _astock_os.environ.get("A_STOCK_WORKSPACE_ROOT") or _astock_os.environ.get("A_STOCK_AGENTS_ROOT")
    if _env_root:
        _receipts.append(_AstPath(_env_root) / "install.json")
    if _astock_sys.platform == "win32":
        _local = _astock_os.environ.get("LOCALAPPDATA") or (_AstPath.home() / "AppData/Local")
        _receipts.append(_AstPath(_local) / "a_stock_agents" / "install.json")
    elif _astock_sys.platform == "darwin":
        _receipts.append(_AstPath.home() / "Library/Application Support" / "a_stock_agents" / "install.json")
    else:
        _xdg = _astock_os.environ.get("XDG_DATA_HOME") or (_AstPath.home() / ".local/share")
        _receipts.append(_AstPath(_xdg) / "a_stock_agents" / "install.json")
    for _rp in _receipts:
        if _rp.is_file():
            try:
                _data = _astock_json.loads(_rp.read_text(encoding="utf-8"))
                _target = _data.get("bundle_root") or _data.get("runtime_root") or _data.get("anchor_root")
                if _target:
                    _tp = _AstPath(_target).resolve()
                    if (_tp / "bundle.json").is_file():
                        return _tp
                    if (_tp / "a-stock-agents" / "bundle.json").is_file():
                        return (_tp / "a-stock-agents").resolve()
                    if _tp.name == "runtime" and (_tp.parent / "bundle.json").is_file():
                        return _tp.parent
            except Exception:
                pass
    raise RuntimeError("ANCHOR_SKILL_MISSING: Complete a_stock_agents bundle or a-stock-agents anchor skill required")

_astock_bundle = _astock_resolve_bundle()
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
