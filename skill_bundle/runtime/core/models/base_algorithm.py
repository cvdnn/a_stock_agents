# -*- coding: utf-8 -*-
"""
Core Quantitative Algorithm Base Interfaces & Metadata Standards.

Provides standard abstract base classes (ABC), category taxonomy, lifecycle stages,
and metadata specifications for the Unified Algorithm Library (AlgoRegistry 2.0).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class AlgorithmCategory(str, Enum):
    """Algorithm taxonomic category."""
    INDICATOR = "indicator"          # Technical indicator calculation (MA, MACD, etc.)
    ALPHA_FACTOR = "alpha_factor"    # Quantitative cross-sectional / time-series Alpha factor
    SCORING_MODEL = "scoring_model"  # Composite multi-dimensional scoring & screening model
    STRATEGY = "strategy"            # Alpha timing & order generation strategy
    RISK_SIZING = "risk_sizing"      # Position sizing, volatility targeting & risk control
    EXECUTION = "execution"          # Slippage, order matching & trade execution
    EVALUATOR = "evaluator"          # Performance metrics, backtesting & strategy evaluation
    MULTI_AGENT = "multi_agent"      # Multi-agent reasoning, consensus debate & expert rules


class AlgorithmLifecycleStage(str, Enum):
    """Full lifecycle management stage of a quantitative algorithm."""
    RESEARCH = "research"            # In initial exploration or mathematical definition
    BACKTESTED = "backtested"        # Passed offline backtesting & historical verification
    STAGING = "staging"              # Running in shadow mode / paper trading environment
    PRODUCTION = "production"        # Actively serving live production trading & screening
    DEPRECATED = "deprecated"        # Sunset warning issued, pending replacement
    RETIRED = "retired"              # Formally decommissioned and archived


@dataclass
class AlgorithmMetadata:
    """Metadata describing a registered quantitative algorithm or model."""
    algo_id: str
    name: str
    category: AlgorithmCategory
    description: str = ""
    version: str = "1.0.0"
    author: str = "astocks"
    stage: AlgorithmLifecycleStage = AlgorithmLifecycleStage.PRODUCTION
    module_path: str = ""
    target_name: str = ""
    is_class: bool = True
    regime_suitability: List[str] = field(default_factory=lambda: ["DEFAULT", "BULL", "BEAR", "OSCILLATION"])
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    benchmark_metrics: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    deprecated_aliases: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to a clean dictionary representation."""
        return {
            "algo_id": self.algo_id,
            "name": self.name,
            "category": self.category.value if isinstance(self.category, AlgorithmCategory) else str(self.category),
            "version": self.version,
            "stage": self.stage.value if isinstance(self.stage, AlgorithmLifecycleStage) else str(self.stage),
            "description": self.description,
            "author": self.author,
            "module_path": self.module_path,
            "target_name": self.target_name,
            "is_class": self.is_class,
            "regime_suitability": list(self.regime_suitability),
            "aliases": list(self.aliases),
            "deprecated_aliases": list(self.deprecated_aliases.keys()),
        }


class BaseAlgorithm(ABC):
    """Abstract base class for all quantitative algorithms."""

    def __init__(self, metadata: Optional[AlgorithmMetadata] = None, **kwargs: Any) -> None:
        self.metadata = metadata

    @property
    def algo_name(self) -> str:
        return self.metadata.name if self.metadata else self.__class__.__name__

    @property
    def version(self) -> str:
        return self.metadata.version if self.metadata else "1.0.0"

    @property
    def category(self) -> Optional[AlgorithmCategory]:
        return self.metadata.category if self.metadata else None

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the primary algorithm pipeline."""
        raise NotImplementedError("Subclasses must implement execute()")


class BaseIndicator(BaseAlgorithm):
    """Abstract base class for technical indicators."""

    @abstractmethod
    def calculate(self, klines: List[Any], **kwargs: Any) -> Any:
        """Compute indicator values across historical K-line sequence."""
        raise NotImplementedError("Indicators must implement calculate()")

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self.calculate(*args, **kwargs)


class BaseFactor(BaseAlgorithm):
    """Abstract base class for quantitative Alpha factors."""

    @abstractmethod
    def extract(self, data: Any, **kwargs: Any) -> Any:
        """Extract or normalize factor values."""
        raise NotImplementedError("Factors must implement extract()")

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self.extract(*args, **kwargs)


class BaseStrategy(BaseAlgorithm):
    """Abstract base class for trading strategies."""

    @abstractmethod
    def generate_signal(self, klines: List[Any], idx: int, **kwargs: Any) -> Dict[str, Any]:
        """Generate trading signals at a specified bar index."""
        raise NotImplementedError("Strategies must implement generate_signal()")

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self.generate_signal(*args, **kwargs)


class BaseRiskManager(BaseAlgorithm):
    """Abstract base class for risk management and position sizing."""

    @abstractmethod
    def evaluate_risk(self, *args: Any, **kwargs: Any) -> Any:
        """Perform risk assessment or position sizing calculation."""
        raise NotImplementedError("Risk managers must implement evaluate_risk()")

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self.evaluate_risk(*args, **kwargs)
