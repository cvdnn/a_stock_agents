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

from .base_algorithm import (
    AlgorithmCategory,
    AlgorithmLifecycleStage,
    AlgorithmMetadata,
    BaseAlgorithm,
    BaseFactor,
    BaseIndicator,
    BaseRiskManager,
    BaseStrategy,
)
from .monitor_governance import (
    AlgorithmLifecycleManager,
    AlphaDecayTracker,
    DecayStatus,
    RegimeAdaptiveDispatcher,
    RegimeDispatchPlan,
)
from .quality_gates import (
    AShareComplianceGuard,
    AlgorithmQualityGate,
    LookaheadGuard,
    OverfittingGuard,
    QualityGateReport,
    QualityGateStatus,
)
from .registry import (
    AlgoRegistry,
    ModelRegistry,
    get_algo,
    get_model,
    get_target,
    list_algos,
    list_models,
    run_algo,
)

__all__ = [
    "AlgorithmCategory",
    "AlgorithmLifecycleStage",
    "AlgorithmMetadata",
    "BaseAlgorithm",
    "BaseFactor",
    "BaseIndicator",
    "BaseRiskManager",
    "BaseStrategy",
    "AlgoRegistry",
    "ModelRegistry",
    "MarketAssessor",
    "get_algo",
    "get_model",
    "get_target",
    "list_algos",
    "list_models",
    "run_algo",
    "AlgorithmQualityGate",
    "LookaheadGuard",
    "AShareComplianceGuard",
    "OverfittingGuard",
    "QualityGateReport",
    "QualityGateStatus",
    "AlphaDecayTracker",
    "RegimeAdaptiveDispatcher",
    "AlgorithmLifecycleManager",
    "DecayStatus",
    "RegimeDispatchPlan",
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
