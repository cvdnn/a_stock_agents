# -*- coding: utf-8 -*-
"""
Core Quantitative Models Package.

Provides unified model registration, factory instantiation, and SSOT exports.
"""
from __future__ import annotations

import importlib
import sys
import warnings
from typing import Any

from .market_assessor import MarketAssessor
from .registry import ModelRegistry, get_model, list_models

__all__ = [
    "MarketAssessor",
    "ModelRegistry",
    "get_model",
    "list_models",
]


def __getattr__(name: str) -> Any:
    """
    PEP 562 dynamic attribute dispatcher.
    Catches legacy/deprecated module imports such as 'multi_dim_model_v3'
    and transparently redirects to the canonical module with a deprecation warning.
    """
    if name == "multi_dim_model_v3":
        warnings.warn(
            "core.models.multi_dim_model_v3 is deprecated and scheduled for removal in v3.1.0. "
            "Import from core.models.multi_dim_model instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        canonical_mod = importlib.import_module("core.models.multi_dim_model")
        # Cache in sys.modules so 'import core.models.multi_dim_model_v3' succeeds
        sys.modules[f"{__name__}.{name}"] = canonical_mod
        return canonical_mod

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
