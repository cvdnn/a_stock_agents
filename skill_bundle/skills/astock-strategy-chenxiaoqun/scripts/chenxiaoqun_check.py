import sys as _astock_sys
from pathlib import Path as _AstPath
_astock_bundle = next((p for p in _AstPath(__file__).resolve().parents if (p / "bundle.json").is_file()), None)
if _astock_bundle is None:
    raise RuntimeError("Complete a_stock_agents bundle required")
_astock_runtime = _astock_bundle / "runtime"
if str(_astock_runtime) not in _astock_sys.path:
    _astock_sys.path.insert(0, str(_astock_runtime))
from core.strategy.chenxiaoqun import *
if __name__ == "__main__":
    main()
