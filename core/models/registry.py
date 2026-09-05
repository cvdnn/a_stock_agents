# -*- coding: utf-8 -*-
"""
Model Registry & Factory Paradigm for Quant Models.
Provides centralized registration, alias resolution, metadata lookup,
and graceful deprecation redirection for models.
"""
from __future__ import annotations

import importlib
import logging
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, Union

logger = logging.getLogger("core.models.registry")


@dataclass
class ModelMetadata:
    """Metadata describing a registered quantitative model."""
    name: str
    description: str
    target_class: Union[Type[Any], str]
    module_path: str
    aliases: List[str] = field(default_factory=list)
    deprecated_aliases: Dict[str, str] = field(default_factory=dict)
    version: str = "1.0.0"


class ModelRegistry:
    """
    Central model registry providing factory instantiation, alias resolution,
    and decoupling algorithm evolution from physical filenames.
    """
    _registry: Dict[str, ModelMetadata] = {}
    _alias_map: Dict[str, str] = {}
    _instance_cache: Dict[str, Any] = {}

    @classmethod
    def register(
        cls,
        name: str,
        module_path: str,
        target_class: Union[Type[Any], str],
        description: str = "",
        aliases: Optional[List[str]] = None,
        deprecated_aliases: Optional[Dict[str, str]] = None,
        version: str = "1.0.0",
    ) -> None:
        """Register a model with primary name, module, class, and aliases."""
        clean_name = name.lower().strip()
        aliases = [a.lower().strip() for a in (aliases or [])]
        deprecated_aliases = {
            k.lower().strip(): v for k, v in (deprecated_aliases or {}).items()
        }

        meta = ModelMetadata(
            name=clean_name,
            description=description,
            target_class=target_class,
            module_path=module_path,
            aliases=aliases,
            deprecated_aliases=deprecated_aliases,
            version=version,
        )

        cls._registry[clean_name] = meta
        cls._alias_map[clean_name] = clean_name

        for alias in aliases:
            cls._alias_map[alias] = clean_name

        for dep_alias in deprecated_aliases:
            cls._alias_map[dep_alias] = clean_name

    @classmethod
    def get_class(cls, name_or_alias: str) -> Type[Any]:
        """Resolve and load the model class by name or alias."""
        clean_key = name_or_alias.lower().strip()
        canonical_name = cls._alias_map.get(clean_key)
        if not canonical_name or canonical_name not in cls._registry:
            valid_keys = sorted(cls._alias_map.keys())
            raise KeyError(
                f"Model '{name_or_alias}' is not registered. Available models/aliases: {valid_keys}"
            )

        meta = cls._registry[canonical_name]

        # Check if caller used a deprecated alias
        if clean_key in meta.deprecated_aliases:
            sunset_msg = meta.deprecated_aliases[clean_key]
            warnings.warn(
                f"Model alias '{clean_key}' is deprecated. {sunset_msg}. Use '{canonical_name}' instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        target = meta.target_class
        if isinstance(target, str):
            mod = importlib.import_module(meta.module_path)
            model_cls = getattr(mod, target)
            meta.target_class = model_cls
            return model_cls

        return target

    @classmethod
    def get(cls, name_or_alias: str, *args: Any, **kwargs: Any) -> Any:
        """Factory method to instantiate a registered model."""
        model_cls = cls.get_class(name_or_alias)
        return model_cls(*args, **kwargs)

    @classmethod
    def list_models(cls) -> List[Dict[str, Any]]:
        """Return information about all registered models."""
        result = []
        for name, meta in sorted(cls._registry.items()):
            result.append({
                "name": name,
                "description": meta.description,
                "version": meta.version,
                "module": meta.module_path,
                "aliases": meta.aliases,
                "deprecated_aliases": list(meta.deprecated_aliases.keys()),
            })
        return result

    @classmethod
    def get_metadata(cls, name_or_alias: str) -> Optional[ModelMetadata]:
        """Retrieve model metadata by name or alias."""
        clean_key = name_or_alias.lower().strip()
        canonical_name = cls._alias_map.get(clean_key)
        if canonical_name and canonical_name in cls._registry:
            return cls._registry[canonical_name]
        return None


# ============================================================
# Pre-register built-in core models
# ============================================================
ModelRegistry.register(
    name="multi_dim",
    module_path="core.models.multi_dim_model",
    target_class="StockSelectionModel",
    description="5A Multi-Dimensional Resonance & Rotation Stock Selection Model",
    aliases=["5a", "resonance", "stock_selection"],
    deprecated_aliases={
        "multi_dim_model_v3": "Scheduled for removal in v3.1.0",
        "multi_dim_v3": "Scheduled for removal in v3.1.0",
        "v3": "Scheduled for removal in v3.1.0",
    },
    version="3.1.0",
)

ModelRegistry.register(
    name="combo_scorer",
    module_path="core.models.combo_scorer",
    target_class="ComboScorer",
    description="100-point Comprehensive Technical & Multi-dimensional Scorer",
    aliases=["combo"],
    version="2.0.0",
)

ModelRegistry.register(
    name="multi_factor_scorer",
    module_path="core.models.multi_factor_scorer",
    target_class="MultiFactorScorer",
    description="Alpha Multi-factor Z-score Cross-sectional Ranking Scorer",
    aliases=["multi_factor", "alpha_scorer"],
    version="2.0.0",
)

ModelRegistry.register(
    name="stock_screener",
    module_path="core.models.stock_screener",
    target_class="StockScreener",
    description="Three-layer Funnel Stock Screener",
    aliases=["screener"],
    version="1.0.0",
)

ModelRegistry.register(
    name="factor_synthesizer",
    module_path="core.models.factor_synthesizer",
    target_class="FactorSynthesizer",
    description="Cross-sectional Factor Normalization & Synthesis Pipeline",
    aliases=["synthesizer"],
    version="1.0.0",
)

ModelRegistry.register(
    name="market_assessor",
    module_path="core.models.market_assessor",
    target_class="MarketAssessor",
    description="Five-dimension Overall Market Health & Sentiment Assessor",
    aliases=["market_gate_assessor"],
    version="2.0.0",
)

ModelRegistry.register(
    name="unstructured_factors",
    module_path="core.models.unstructured_factors",
    target_class="UnstructuredFactors",
    description="News & Event Sentiment Unstructured Factor Evaluator",
    aliases=["sentiment"],
    version="1.0.0",
)


def get_model(name_or_alias: str, *args: Any, **kwargs: Any) -> Any:
    """Convenience helper to instantiate a model from the registry."""
    return ModelRegistry.get(name_or_alias, *args, **kwargs)


def list_models() -> List[Dict[str, Any]]:
    """Convenience helper to list all registered models."""
    return ModelRegistry.list_models()
