# -*- coding: utf-8 -*-
"""
Algorithm & Model Registry Center (AlgoRegistry 2.0).

Provides centralized algorithm governance, taxonomic classification,
lifecycle tracking, alias resolution, and factory/execution dispatcher.
Guarantees 100% backward compatibility with legacy ModelRegistry.
"""
from __future__ import annotations

import importlib
import logging
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from core.models.base_algorithm import (
    AlgorithmCategory,
    AlgorithmLifecycleStage,
    AlgorithmMetadata,
)

logger = logging.getLogger("core.models.registry")


@dataclass
class ModelMetadata:
    """Metadata describing a registered quantitative model (Backward compatibility shim)."""
    name: str
    description: str
    target_class: Union[Type[Any], str]
    module_path: str
    aliases: List[str] = field(default_factory=list)
    deprecated_aliases: Dict[str, str] = field(default_factory=dict)
    version: str = "1.0.0"


class AlgoRegistry:
    """
    Unified Algorithm & Model Registry.

    Manages full-lifecycle algorithms across 7 taxonomy categories:
    indicators, alpha factors, scoring models, trading strategies,
    risk sizing, execution/matching, and performance evaluators.
    """
    _registry: Dict[str, AlgorithmMetadata] = {}
    _alias_map: Dict[str, str] = {}
    _loaded_cache: Dict[str, Any] = {}

    @classmethod
    def register(
        cls,
        name: str,
        module_path: str,
        target_name: Union[str, Callable[..., Any], Type[Any]],
        category: Union[AlgorithmCategory, str] = AlgorithmCategory.SCORING_MODEL,
        is_class: bool = True,
        description: str = "",
        version: str = "1.0.0",
        author: str = "astocks",
        stage: Union[AlgorithmLifecycleStage, str] = AlgorithmLifecycleStage.PRODUCTION,
        regime_suitability: Optional[List[str]] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        benchmark_metrics: Optional[Dict[str, Any]] = None,
        aliases: Optional[List[str]] = None,
        deprecated_aliases: Optional[Dict[str, str]] = None,
        algo_id: Optional[str] = None,
    ) -> None:
        """Register an algorithm or model with rich metadata and aliases."""
        clean_name = name.lower().strip()
        cat_enum = AlgorithmCategory(category) if isinstance(category, str) else category
        stg_enum = AlgorithmLifecycleStage(stage) if isinstance(stage, str) else stage
        alias_list = [a.lower().strip() for a in (aliases or [])]
        dep_dict = {k.lower().strip(): v for k, v in (deprecated_aliases or {}).items()}

        meta = AlgorithmMetadata(
            algo_id=algo_id or f"{cat_enum.value}:{clean_name}",
            name=clean_name,
            category=cat_enum,
            description=description,
            version=version,
            author=author,
            stage=stg_enum,
            module_path=module_path,
            target_name=target_name if isinstance(target_name, str) else target_name.__name__,
            is_class=is_class,
            regime_suitability=regime_suitability or ["DEFAULT", "BULL", "BEAR", "OSCILLATION"],
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            benchmark_metrics=benchmark_metrics or {},
            aliases=alias_list,
            deprecated_aliases=dep_dict,
        )

        cls._registry[clean_name] = meta
        cls._alias_map[clean_name] = clean_name

        for alias in alias_list:
            cls._alias_map[alias] = clean_name

        for dep_alias in dep_dict:
            cls._alias_map[dep_alias] = clean_name

        # If object was passed directly, cache it immediately
        if not isinstance(target_name, str):
            cls._loaded_cache[clean_name] = target_name

    @classmethod
    def resolve_target(cls, name_or_alias: str) -> Tuple[Any, AlgorithmMetadata]:
        """Resolve and lazily load the algorithm class or function target."""
        clean_key = name_or_alias.lower().strip()
        canonical_name = cls._alias_map.get(clean_key)
        if not canonical_name or canonical_name not in cls._registry:
            valid_keys = sorted(cls._alias_map.keys())
            raise KeyError(
                f"Algorithm/Model '{name_or_alias}' is not registered. Available: {valid_keys}"
            )

        meta = cls._registry[canonical_name]

        # Check deprecation
        if clean_key in meta.deprecated_aliases:
            sunset_msg = meta.deprecated_aliases[clean_key]
            warnings.warn(
                f"Algorithm/Model alias '{clean_key}' is deprecated. {sunset_msg}. Use '{canonical_name}' instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        if canonical_name in cls._loaded_cache:
            return cls._loaded_cache[canonical_name], meta

        # Lazy dynamic import
        mod = importlib.import_module(meta.module_path)
        target_path = meta.target_name
        # Support dotted target path, e.g. "PVFactors.calculate_chip_cost"
        obj: Any = mod
        for part in target_path.split("."):
            obj = getattr(obj, part)

        cls._loaded_cache[canonical_name] = obj
        return obj, meta

    @classmethod
    def get_target(cls, name_or_alias: str) -> Any:
        """Resolve and return the underlying class or function target directly without invoking."""
        obj, _ = cls.resolve_target(name_or_alias)
        return obj

    @classmethod
    def get(cls, name_or_alias: str, *args: Any, **kwargs: Any) -> Any:
        """Factory method to instantiate a registered model/strategy, or invoke function."""
        obj, meta = cls.resolve_target(name_or_alias)
        if meta.is_class:
            return obj(*args, **kwargs)
        if args or kwargs:
            return obj(*args, **kwargs)
        return obj

    @classmethod
    def get_class(cls, name_or_alias: str) -> Type[Any]:
        """Resolve and return the target class (legacy ModelRegistry compatible)."""
        obj, meta = cls.resolve_target(name_or_alias)
        return obj

    @classmethod
    def run_algo(cls, name_or_alias: str, *args: Any, **kwargs: Any) -> Any:
        """Execute an algorithm regardless of whether it is a function or class."""
        obj, meta = cls.resolve_target(name_or_alias)
        if not meta.is_class:
            return obj(*args, **kwargs)
        
        # If it is a class, instantiate and call execute() if available, else instantiate
        instance = obj(*args, **kwargs)
        if hasattr(instance, "execute") and callable(instance.execute):
            return instance.execute()
        return instance

    @classmethod
    def get_metadata(cls, name_or_alias: str) -> Optional[AlgorithmMetadata]:
        """Retrieve rich algorithm metadata by canonical name or alias."""
        clean_key = name_or_alias.lower().strip()
        canonical_name = cls._alias_map.get(clean_key)
        if canonical_name and canonical_name in cls._registry:
            return cls._registry[canonical_name]
        return None

    @classmethod
    def list_algos(
        cls,
        category: Optional[Union[AlgorithmCategory, str]] = None,
        stage: Optional[Union[AlgorithmLifecycleStage, str]] = None,
    ) -> List[Dict[str, Any]]:
        """List registered algorithms with optional category and lifecycle filtering."""
        target_cat = AlgorithmCategory(category) if isinstance(category, str) else category
        target_stg = AlgorithmLifecycleStage(stage) if isinstance(stage, str) else stage

        results = []
        for name in sorted(cls._registry.keys()):
            meta = cls._registry[name]
            if target_cat and meta.category != target_cat:
                continue
            if target_stg and meta.stage != target_stg:
                continue
            results.append(meta.to_dict())
        return results

    @classmethod
    def list_models(cls) -> List[Dict[str, Any]]:
        """Backward-compatible listing for scoring models."""
        models = cls.list_algos(category=AlgorithmCategory.SCORING_MODEL)
        out = []
        for m in models:
            out.append({
                "name": m["name"],
                "description": m["description"],
                "version": m["version"],
                "module": m["module_path"],
                "aliases": m["aliases"],
                "deprecated_aliases": m["deprecated_aliases"],
            })
        return out


class ModelRegistry:
    """
    100% Backward-compatible facade for legacy ModelRegistry.
    Delegates registration and queries to AlgoRegistry.
    """
    _registry: Dict[str, ModelMetadata] = {}

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
        """Register a model (delegates to AlgoRegistry)."""
        clean_name = name.lower().strip()
        meta = ModelMetadata(
            name=clean_name,
            description=description,
            target_class=target_class,
            module_path=module_path,
            aliases=aliases or [],
            deprecated_aliases=deprecated_aliases or {},
            version=version,
        )
        cls._registry[clean_name] = meta

        AlgoRegistry.register(
            name=name,
            module_path=module_path,
            target_name=target_class,
            category=AlgorithmCategory.SCORING_MODEL,
            is_class=True,
            description=description,
            version=version,
            aliases=aliases,
            deprecated_aliases=deprecated_aliases,
        )

    @classmethod
    def get_class(cls, name_or_alias: str) -> Type[Any]:
        return AlgoRegistry.get_class(name_or_alias)

    @classmethod
    def get(cls, name_or_alias: str, *args: Any, **kwargs: Any) -> Any:
        return AlgoRegistry.get(name_or_alias, *args, **kwargs)

    @classmethod
    def list_models(cls) -> List[Dict[str, Any]]:
        return AlgoRegistry.list_models()

    @classmethod
    def get_metadata(cls, name_or_alias: str) -> Optional[ModelMetadata]:
        clean_key = name_or_alias.lower().strip()
        canonical_name = AlgoRegistry._alias_map.get(clean_key)
        if canonical_name and canonical_name in cls._registry:
            return cls._registry[canonical_name]
        # Build ModelMetadata from AlgoRegistry if not in legacy dict
        algo_meta = AlgoRegistry.get_metadata(name_or_alias)
        if algo_meta:
            return ModelMetadata(
                name=algo_meta.name,
                description=algo_meta.description,
                target_class=algo_meta.target_name,
                module_path=algo_meta.module_path,
                aliases=algo_meta.aliases,
                deprecated_aliases=algo_meta.deprecated_aliases,
                version=algo_meta.version,
            )
        return None


# ============================================================
# Pre-register built-in core algorithms (40+ items)
# ============================================================

# ── 1. 基础技术指标算法族 (INDICATORS) ─────────────────────────
AlgoRegistry.register(
    name="ma",
    module_path="core.indicators.technical_indicators",
    target_name="ma",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Simple Moving Average (SMA)",
    version="1.0.0",
    aliases=["sma_line"],
)

AlgoRegistry.register(
    name="ema",
    module_path="core.indicators.technical_indicators",
    target_name="ema",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Exponential Moving Average",
    version="1.0.0",
)

AlgoRegistry.register(
    name="macd",
    module_path="core.indicators.technical_indicators",
    target_name="macd",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Moving Average Convergence Divergence (DIF, DEA, Bar)",
    version="1.0.0",
    aliases=["dif_dea"],
)

AlgoRegistry.register(
    name="kdj",
    module_path="core.indicators.technical_indicators",
    target_name="kdj",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Stochastic Oscillator (KDJ)",
    version="1.0.0",
)

AlgoRegistry.register(
    name="rsi",
    module_path="core.indicators.technical_indicators",
    target_name="rsi",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Relative Strength Index (RSI-14)",
    version="1.0.0",
)

AlgoRegistry.register(
    name="boll",
    module_path="core.indicators.technical_indicators",
    target_name="boll",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Bollinger Bands (Mid, Upper, Lower, Bandwidth)",
    version="1.0.0",
    aliases=["bollinger"],
)

AlgoRegistry.register(
    name="atr",
    module_path="core.indicators.technical_indicators",
    target_name="atr",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Average True Range (ATR-14)",
    version="1.0.0",
)

AlgoRegistry.register(
    name="calc_all",
    module_path="core.indicators.technical_indicators",
    target_name="calc_all",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Comprehensive Technical Indicator Snapshot Calculator",
    version="1.0.0",
    aliases=["technical_snapshot"],
)

AlgoRegistry.register(
    name="gap_analysis",
    module_path="core.indicators.technical_indicators",
    target_name="gap_analysis",
    category=AlgorithmCategory.INDICATOR,
    is_class=False,
    description="Price Gap Jump & Fill Analyzer",
    version="1.0.0",
    aliases=["gap"],
)

# ── 2. 量价形态与高级 Alpha 因子算法族 (ALPHA_FACTORS) ────────
AlgoRegistry.register(
    name="second_golden_cross",
    module_path="core.indicators.technical_indicators",
    target_name="second_golden_cross",
    category=AlgorithmCategory.ALPHA_FACTOR,
    is_class=False,
    description="MACD Zero-line Double Golden Cross & Bullish Divergence Pattern Detector",
    version="2.0.0",
    aliases=["divergence", "macd_divergence", "bottom_divergence"],
)

AlgoRegistry.register(
    name="pv_factors",
    module_path="core.indicators.pv_factors",
    target_name="PVFactors",
    category=AlgorithmCategory.ALPHA_FACTOR,
    is_class=True,
    description="Price-Volume Alpha Factor Calculation Suite",
    version="2.0.0",
    aliases=["pv_suite"],
)

AlgoRegistry.register(
    name="calculate_chip_cost",
    module_path="core.indicators.pv_factors",
    target_name="PVFactors.calculate_chip_cost",
    category=AlgorithmCategory.ALPHA_FACTOR,
    is_class=False,
    description="Turnover-decay Volume-by-Price Chip Distribution Weighted Cost Model",
    version="2.0.0",
    aliases=["chip_cost", "chip_distribution"],
)

AlgoRegistry.register(
    name="extract_factors",
    module_path="core.indicators.pv_factors",
    target_name="PVFactors.extract_factors",
    category=AlgorithmCategory.ALPHA_FACTOR,
    is_class=False,
    description="15-Dimension Full Price-Volume Alpha Feature Extractor",
    version="2.0.0",
    aliases=["extract_pv_factors"],
)

# ── 3. 多维评分与多因子模型算法族 (SCORING_MODELS) ───────────
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

# ── 4. 交易策略与执行动作算法族 (STRATEGIES) ───────────────────
AlgoRegistry.register(
    name="volatility_breakout",
    module_path="core.strategy.volatility_breakout_strategy",
    target_name="VolatilityBreakoutStrategy",
    category=AlgorithmCategory.STRATEGY,
    is_class=True,
    description="Bollinger Squeeze with Volume Breakout Strategy",
    version="1.0.0",
    aliases=["boll_breakout"],
)

AlgoRegistry.register(
    name="mean_reversion",
    module_path="core.strategy.mean_reversion_strategy",
    target_name="MeanReversionStrategy",
    category=AlgorithmCategory.STRATEGY,
    is_class=True,
    description="RSI & Bollinger Bands Overbought/Oversold Reversion Strategy",
    version="1.0.0",
    aliases=["reversion"],
)

AlgoRegistry.register(
    name="grid_trading",
    module_path="core.strategy.grid_trading_strategy",
    target_name="GridTradingStrategy",
    category=AlgorithmCategory.STRATEGY,
    is_class=True,
    description="ATR-anchored Bollinger Range Grid Trading Strategy",
    version="1.0.0",
    aliases=["grid"],
)

AlgoRegistry.register(
    name="trapped_position",
    module_path="core.strategy.trapped_position",
    target_name="TrappedPositionAnalyzer",
    category=AlgorithmCategory.STRATEGY,
    is_class=True,
    description="Trapped Position Recovery & Multi-stage Grid-T Tactical Analyzer",
    version="1.0.0",
    aliases=["trapped_analyzer"],
)

AlgoRegistry.register(
    name="dynamic_universe",
    module_path="core.strategy.dynamic_universe",
    target_name="DynamicUniverseEngine",
    category=AlgorithmCategory.STRATEGY,
    is_class=True,
    description="Dynamic Trading Universe & Market Leading Sector Engine",
    version="1.0.0",
    aliases=["universe_engine"],
)

AlgoRegistry.register(
    name="fundamental_filter",
    module_path="core.strategy.fundamental_filter",
    target_name="FundamentalFilter",
    category=AlgorithmCategory.STRATEGY,
    is_class=True,
    description="Fundamental Financial Quality Gate & ST/Risk Filtering Engine",
    version="1.0.0",
    aliases=["filter_st"],
)

AlgoRegistry.register(
    name="intent_evaluator",
    module_path="core.strategy.execution_action_engine",
    target_name="IntentEvaluator",
    category=AlgorithmCategory.STRATEGY,
    is_class=True,
    description="Natural Language Trading Intent Router & Semantic Classifier",
    version="2.0.0",
    aliases=["intent_router"],
)

# ── 5. 仓位管理与组合风控算法族 (RISK_SIZING) ──────────────────
AlgoRegistry.register(
    name="position_sizer",
    module_path="core.strategy.risk_position_manager",
    target_name="PositionSizer",
    category=AlgorithmCategory.RISK_SIZING,
    is_class=True,
    description="Target Volatility Sizing & Fractional Kelly Board-Lot Position Sizer",
    version="2.0.0",
    aliases=["sizer", "kelly_sizer"],
)

AlgoRegistry.register(
    name="portfolio_risk_manager",
    module_path="core.strategy.portfolio_risk_manager",
    target_name="PortfolioRiskManager",
    category=AlgorithmCategory.RISK_SIZING,
    is_class=True,
    description="Portfolio Risk Manager (Volatility Target, Drawdown Breakers, Exposure Caps)",
    version="1.0.0",
    aliases=["risk_manager"],
)

# ── 6. 交易撮合、回测与效能度量 (EXECUTION & EVALUATORS) ───────
AlgoRegistry.register(
    name="market_impact_slippage",
    module_path="core.paper_trading.engine",
    target_name="calc_market_impact_bps",
    category=AlgorithmCategory.EXECUTION,
    is_class=False,
    description="Almgren-Chriss Square-Root Market Impact Cost Slippage Model",
    version="2.0.0",
    aliases=["slippage_impact"],
)

AlgoRegistry.register(
    name="paper_trading_engine",
    module_path="core.paper_trading.engine",
    target_name="PaperTradingEngine",
    category=AlgorithmCategory.EXECUTION,
    is_class=True,
    description="A-Share Paper Trading Engine with T+1 and Limit Price Settlement",
    version="2.0.0",
    aliases=["matching_engine"],
)

AlgoRegistry.register(
    name="backtest_metrics",
    module_path="core.paper_trading.backtest_metrics",
    target_name="calc_metrics",
    category=AlgorithmCategory.EVALUATOR,
    is_class=False,
    description="Zero-dependency Full Quantitative Performance Metrics Suite (Sharpe, Calmar, etc.)",
    version="1.0.0",
    aliases=["calc_metrics", "metrics_suite"],
)

AlgoRegistry.register(
    name="strategy_evaluator",
    module_path="core.models.strategy_evaluator",
    target_name="StrategyEvaluator",
    category=AlgorithmCategory.EVALUATOR,
    is_class=True,
    description="Post-Trade Strategy Accuracy & Forward Rating Calibration Evaluator",
    version="1.0.0",
    aliases=["post_evaluator"],
)

AlgoRegistry.register(
    name="rotation_backtest",
    module_path="core.models.multi_dim_model",
    target_name="RotationBacktest",
    category=AlgorithmCategory.EVALUATOR,
    is_class=True,
    description="Long-horizon Multi-stock Rotation Historical Backtest Engine",
    version="3.1.0",
    aliases=["rotation_bt"],
)

AlgoRegistry.register(
    name="quality_gate",
    module_path="core.models.quality_gates",
    target_name="AlgorithmQualityGate",
    category=AlgorithmCategory.EVALUATOR,
    is_class=True,
    description="Full-Lifecycle Algorithm Quality Gates & Overfitting Auditor",
    version="1.0.0",
    aliases=["quality_gates", "algo_auditor"],
)

AlgoRegistry.register(
    name="alpha_decay_tracker",
    module_path="core.models.monitor_governance",
    target_name="AlphaDecayTracker",
    category=AlgorithmCategory.EVALUATOR,
    is_class=True,
    description="Cross-Sectional Rank IC & Rolling Alpha Factor Decay Tracker",
    version="1.0.0",
    aliases=["decay_tracker", "ic_tracker"],
)

AlgoRegistry.register(
    name="regime_dispatcher",
    module_path="core.models.monitor_governance",
    target_name="RegimeAdaptiveDispatcher",
    category=AlgorithmCategory.RISK_SIZING,
    is_class=True,
    description="Market Regime Adaptive Factor & Strategy Route Dispatcher",
    version="1.0.0",
    aliases=["regime_adaptive", "adaptive_dispatcher"],
)

AlgoRegistry.register(
    name="lifecycle_manager",
    module_path="core.models.monitor_governance",
    target_name="AlgorithmLifecycleManager",
    category=AlgorithmCategory.EVALUATOR,
    is_class=True,
    description="Algorithm Lifecycle State Machine & Retirement Breaker",
    version="1.0.0",
    aliases=["alcm_manager", "retirement_breaker"],
)


# ============================================================
# Convenience helper functions
# ============================================================
def get_algo(name_or_alias: str, *args: Any, **kwargs: Any) -> Any:
    """Convenience helper to instantiate or invoke an algorithm."""
    return AlgoRegistry.get(name_or_alias, *args, **kwargs)


def get_target(name_or_alias: str) -> Any:
    """Convenience helper to get underlying class/function target without invoking."""
    return AlgoRegistry.get_target(name_or_alias)


def run_algo(name_or_alias: str, *args: Any, **kwargs: Any) -> Any:
    """Convenience helper to execute an algorithm regardless of whether it is a function or class."""
    return AlgoRegistry.run_algo(name_or_alias, *args, **kwargs)


def list_algos(
    category: Optional[Union[AlgorithmCategory, str]] = None,
    stage: Optional[Union[AlgorithmLifecycleStage, str]] = None,
) -> List[Dict[str, Any]]:
    """Convenience helper to list registered algorithms."""
    return AlgoRegistry.list_algos(category=category, stage=stage)


def get_model(name_or_alias: str, *args: Any, **kwargs: Any) -> Any:
    """Convenience helper to instantiate a model from the registry (legacy compatible)."""
    return ModelRegistry.get(name_or_alias, *args, **kwargs)


def list_models() -> List[Dict[str, Any]]:
    """Convenience helper to list all registered models (legacy compatible)."""
    return ModelRegistry.list_models()
