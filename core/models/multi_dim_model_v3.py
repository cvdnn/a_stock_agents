# -*- coding: utf-8 -*-
"""
Deprecation wrapper for core.models.multi_dim_model_v3.
Delegates to core.models.multi_dim_model (SSOT).
"""
from __future__ import annotations

import warnings
import core.models.multi_dim_model as _core_mod
from core.models.multi_dim_model import *  # noqa: F401, F403

warnings.warn(
    "core.models.multi_dim_model_v3 is deprecated. Import from core.models.multi_dim_model instead.",
    DeprecationWarning,
    stacklevel=2,
)

if hasattr(_core_mod, "__all__"):
    __all__ = _core_mod.__all__
else:
    __all__ = [k for k in dir(_core_mod) if not k.startswith("__")]

if __name__ == "__main__":
    if hasattr(_core_mod, "main") and callable(getattr(_core_mod, "main")):
        getattr(_core_mod, "main")()