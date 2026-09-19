# -*- coding: utf-8 -*-
"""A-share rule plug-ins and orchestration for the configurable funnel."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import yaml

from scripts.core.workspace import OUTPUT_DIR, PROJECT_ROOT
from core.strategy.funnel_engine import FunnelEngine, RuleRegistry, RuleResult

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "funnel_strategy.yaml"


def _path_get(data: Mapping[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def _numbers(values: Sequence[Any]) -> List[float]:
    result = []
    for value in values:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("series contains a non-finite number")
        result.append(number)
    return result


def _compare(left: Any, op: str, right: Any) -> bool:
    operations = {
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
        "contains": lambda a, b: b in a,
        "not_contains": lambda a, b: b not in a,
    }
    if op not in operations:
        raise ValueError(f"unsupported comparison operator: {op}")
    return bool(operations[op](left, right))


def rule_field_compare(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    field = str(spec["field"])
    observed = _path_get(record, field)
    expected = spec.get("value")
    passed = _compare(observed, str(spec.get("op", "eq")), expected)
    return RuleResult("", passed, reason=f"{field}={observed!r}", observed=observed, expected=expected)


def rule_symbol_prefix_exclude(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    code = str(_path_get(record, str(spec.get("field", "code")))).lower()
    clean = code.replace("sh", "").replace("sz", "").replace("bj", "")
    excluded = tuple(str(item) for item in spec.get("prefixes", []))
    passed = not clean.startswith(excluded)
    return RuleResult("", passed, reason=f"代码={clean}", observed=clean, expected=f"不以{excluded}开头")


def rule_text_exclude(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    text = str(_path_get(record, str(spec.get("field", "name")))).upper()
    tokens = [str(item).upper() for item in spec.get("tokens", [])]
    matched = [token for token in tokens if token in text]
    return RuleResult("", not matched, reason=f"命中排除词: {matched}" if matched else "未命中排除词", observed=text, expected=tokens)


def rule_rolling_high(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    series = _numbers(_path_get(record, str(spec.get("field", "closes"))))
    lookback = int(spec.get("lookback", 20))
    if lookback < 2 or len(series) < lookback:
        raise ValueError(f"至少需要 {lookback} 个数据点")
    current = series[-1]
    previous = series[-lookback:-1]
    threshold = max(previous)
    strict = bool(spec.get("strict", True))
    passed = current > threshold if strict else current >= threshold
    return RuleResult("", passed, reason=f"最新收盘={current:.4f}, 前期高点={threshold:.4f}", observed=current, expected=threshold)


def rule_above_sma(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    series = _numbers(_path_get(record, str(spec.get("series_field", "closes"))))
    period = int(spec.get("period", 60))
    if len(series) < period:
        raise ValueError(f"至少需要 {period} 个数据点")
    price_field = spec.get("price_field")
    price = float(_path_get(record, str(price_field))) if price_field else series[-1]
    completed_only = bool(spec.get("completed_bars_only", False))
    base = series[-period:] if not completed_only else series[-period-1:-1]
    if len(base) < period:
        raise ValueError(f"至少需要 {period + 1} 个数据点")
    sma = mean(base)
    passed = price > sma if bool(spec.get("strict", True)) else price >= sma
    return RuleResult("", passed, reason=f"价格={price:.4f}, MA{period}={sma:.4f}", observed=price, expected=sma)


def rule_sma_slope(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    series = _numbers(_path_get(record, str(spec.get("field", "closes"))))
    period = int(spec.get("period", 60))
    lag = int(spec.get("lag", 1))
    if len(series) < period + lag:
        raise ValueError(f"至少需要 {period + lag} 个数据点")
    current = mean(series[-period:])
    previous = mean(series[-period-lag:-lag])
    min_slope_pct = float(spec.get("min_slope_pct", 0.0))
    slope_pct = (current / previous - 1.0) * 100 if previous else float("-inf")
    passed = slope_pct > min_slope_pct if bool(spec.get("strict", True)) else slope_pct >= min_slope_pct
    return RuleResult("", passed, reason=f"MA{period}斜率={slope_pct:.4f}%", observed=slope_pct, expected=min_slope_pct)


def rule_series_compare(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    series = _numbers(_path_get(record, str(spec.get("field", "volumes"))))
    left_offset = int(spec.get("left_offset", -1))
    right_offset = int(spec.get("right_offset", -2))
    left, right = series[left_offset], series[right_offset]
    passed = _compare(left, str(spec.get("op", "gt")), right)
    return RuleResult("", passed, reason=f"序列比较: {left} vs {right}", observed=left, expected=right)


def rule_range(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    field = str(spec["field"])
    value = float(_path_get(record, field))
    min_value = spec.get("min")
    max_value = spec.get("max")
    min_ok = True if min_value is None else value >= float(min_value)
    max_ok = True if max_value is None else value <= float(max_value)
    return RuleResult("", min_ok and max_ok, reason=f"{field}={value:.4f}", observed=value, expected={"min": min_value, "max": max_value})


def rule_market_above_sma(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    price = float(_path_get(record, str(spec.get("price_field", "market.current_price"))))
    closes = _numbers(_path_get(record, str(spec.get("series_field", "market.completed_closes"))))
    period = int(spec.get("period", 20))
    if len(closes) < period:
        raise ValueError(f"大盘至少需要 {period} 根已完成日K")
    sma = mean(closes[-period:])
    passed = price > sma if bool(spec.get("strict", True)) else price >= sma
    return RuleResult("", passed, reason=f"指数现价={price:.4f}, 前收盘MA{period}={sma:.4f}", observed=price, expected=sma)


def _minute_points(record: Mapping[str, Any], spec: Mapping[str, Any]) -> List[Dict[str, Any]]:
    points = _path_get(record, str(spec.get("points_field", "minute_points")))
    if not isinstance(points, list):
        raise ValueError("minute_points 必须是列表")
    start = str(spec.get("window_start", "09:30"))
    end = str(spec.get("window_end", "09:40"))
    result = []
    for point in points:
        timestamp = str(point.get("time", ""))[-5:]
        if len(timestamp) == 4 and timestamp.isdigit():
            timestamp = f"{timestamp[:2]}:{timestamp[2:]}"
        if start <= timestamp <= end:
            normalized = dict(point)
            normalized["time"] = timestamp
            normalized["price"] = float(point["price"])
            normalized["volume"] = float(point.get("volume", 0))
            result.append(normalized)
    result.sort(key=lambda item: item["time"])
    return result


def _ratio(recent: Sequence[float], previous: Sequence[float]) -> Optional[float]:
    if not recent or not previous:
        return None
    denominator = mean(previous)
    if denominator <= 0:
        return None
    return mean(recent) / denominator


def rule_intraday_turning_point(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    points = _minute_points(record, spec)
    min_points = int(spec.get("min_points", 6))
    if len(points) < min_points:
        return RuleResult("", False, status="INSUFFICIENT_DATA", reason=f"分钟数据不足: {len(points)}/{min_points}")

    pullback_end = str(spec.get("pullback_end", "09:35"))
    confirm_start = str(spec.get("confirm_start", "09:35"))
    pullback = [p for p in points if p["time"] <= pullback_end]
    confirm = [p for p in points if p["time"] >= confirm_start]
    if len(pullback) < 3 or len(confirm) < 2:
        return RuleResult("", False, status="INSUFFICIENT_DATA", reason="回调段或确认段分钟数不足")

    peak_idx = max(range(len(pullback)), key=lambda i: pullback[i]["price"])
    after_peak = pullback[peak_idx:]
    peak = pullback[peak_idx]["price"]
    trough = min(p["price"] for p in after_peak)
    drawdown_pct = (peak - trough) / peak * 100 if peak else 0.0
    min_pullback = float(spec.get("min_pullback_pct", 0.2))
    max_pullback = float(spec.get("max_pullback_pct", 2.0))
    pullback_ok = peak_idx < len(pullback) - 1 and min_pullback <= drawdown_pct <= max_pullback

    prices = [p["price"] for p in points]
    price_reversal = prices[-1] > prices[-2] and prices[-1] > mean(prices[-3:])

    # Prefer explicit active buy/sell volume.  If unavailable, use up/down
    # minute volume as a transparent proxy rather than fabricating order flow.
    recent = points[-2:]
    previous = points[-4:-2]
    explicit_flow = all("buy_volume" in p and "sell_volume" in p for p in points[-4:])
    if explicit_flow:
        sell_ratio = _ratio([float(p["sell_volume"]) for p in recent], [float(p["sell_volume"]) for p in previous])
        buy_ratio = _ratio([float(p["buy_volume"]) for p in recent], [float(p["buy_volume"]) for p in previous])
        flow_source = "active_buy_sell"
    else:
        point_positions = {id(point): idx for idx, point in enumerate(points)}

        def signed_volume(segment: Sequence[Mapping[str, Any]], upward: bool) -> List[float]:
            values = []
            for p in segment:
                global_idx = point_positions[id(p)]
                if global_idx == 0:
                    continue
                delta = p["price"] - points[global_idx - 1]["price"]
                if (delta > 0) == upward and delta != 0:
                    values.append(float(p["volume"]))
            return values
        sell_ratio = _ratio(signed_volume(recent, False), signed_volume(previous, False))
        buy_ratio = _ratio(signed_volume(recent, True), signed_volume(previous, True))
        flow_source = "price_direction_volume_proxy"

    sell_exhaustion = sell_ratio is not None and sell_ratio <= float(spec.get("max_sell_ratio", 0.75))
    buy_strengthening = buy_ratio is not None and buy_ratio >= float(spec.get("min_buy_ratio", 1.20))

    book = record.get("order_book") or {}
    bid_volume = float(book.get("bid_volume", 0) or 0)
    ask_volume = float(book.get("ask_volume", 0) or 0)
    book_ratio = bid_volume / ask_volume if ask_volume > 0 else None
    book_support = book_ratio is not None and book_ratio >= float(spec.get("min_book_ratio", 1.20))

    confirmations = {
        "pullback": pullback_ok,
        "price_reversal": price_reversal,
        "sell_exhaustion": sell_exhaustion,
        "buy_strengthening": buy_strengthening,
        "book_support": book_support,
    }
    required = list(spec.get("required", ["pullback", "price_reversal"]))
    required_ok = all(confirmations.get(item, False) for item in required)
    optional_names = list(spec.get("confirmations", ["sell_exhaustion", "buy_strengthening", "book_support"]))
    optional_count = sum(bool(confirmations.get(item)) for item in optional_names)
    min_confirmations = int(spec.get("min_confirmations", 2))
    passed = required_ok and optional_count >= min_confirmations
    unavailable = [
        name for name, value in {
            "sell_ratio": sell_ratio,
            "buy_ratio": buy_ratio,
            "book_ratio": book_ratio,
        }.items() if value is None
    ]
    required_unavailable = (
        ("sell_exhaustion" in required and sell_ratio is None)
        or ("buy_strengthening" in required and buy_ratio is None)
        or ("book_support" in required and book_ratio is None)
    )
    insufficient = required_unavailable or (optional_count < min_confirmations and bool(unavailable))
    status = "PASS" if passed else ("INSUFFICIENT_DATA" if insufficient else "FAIL")
    metrics = {
        "drawdown_pct": round(drawdown_pct, 4),
        "sell_ratio": None if sell_ratio is None else round(sell_ratio, 4),
        "buy_ratio": None if buy_ratio is None else round(buy_ratio, 4),
        "book_ratio": None if book_ratio is None else round(book_ratio, 4),
        "flow_source": flow_source,
        "confirmations": confirmations,
        "optional_count": optional_count,
        "minimum_optional_confirmations": min_confirmations,
        "unavailable": unavailable,
    }
    reason = "拐点确认" if passed else "拐点尚未满足或数据不足"
    return RuleResult("", passed, status=status, reason=reason, observed=confirmations, expected={"required": required, "min_confirmations": min_confirmations}, metrics=metrics)


def build_stock_rule_registry() -> RuleRegistry:
    registry = RuleRegistry()
    for name, evaluator in {
        "field_compare": rule_field_compare,
        "symbol_prefix_exclude": rule_symbol_prefix_exclude,
        "text_exclude": rule_text_exclude,
        "rolling_high": rule_rolling_high,
        "above_sma": rule_above_sma,
        "sma_slope": rule_sma_slope,
        "series_compare": rule_series_compare,
        "range": rule_range,
        "market_above_sma": rule_market_above_sma,
        "intraday_turning_point": rule_intraday_turning_point,
    }.items():
        registry.register(name, evaluator)
    return registry


def load_funnel_config(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = Path(path or DEFAULT_CONFIG_PATH)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data.get("stages"), list) or not data["stages"]:
        raise ValueError("funnel config requires a non-empty stages list")
    return data


class StockFunnelPipeline:
    """Run configured A-share stages and optionally archive handoff results."""

    def __init__(self, config: Optional[Mapping[str, Any]] = None, config_path: Optional[Path] = None) -> None:
        self.config = dict(config or load_funnel_config(config_path))
        self.registry = build_stock_rule_registry()
        self.engine = FunnelEngine(self.registry)
        all_stage_ids = [str(stage["id"]) for stage in self.config["stages"]]
        if len(set(all_stage_ids)) != len(all_stage_ids):
            raise ValueError("stage ids must be unique")
        for stage in self.config["stages"]:
            self.engine.validate_stage(stage)
        self._stages = {
            str(stage["id"]): stage
            for stage in self.config["stages"]
            if stage.get("enabled", True)
        }

    @property
    def stage_ids(self) -> List[str]:
        return list(self._stages)

    def run_stage(
        self,
        stage_id: str,
        records: Iterable[Mapping[str, Any]],
        context: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if stage_id not in self._stages:
            raise ValueError(f"unknown stage {stage_id}; available: {', '.join(self.stage_ids)}")
        result = self.engine.run_stage(self._stages[stage_id], records, context)
        payload = result.to_dict()
        payload["selected_codes"] = [
            str(item.get("code", ""))
            for item in payload["passed_records"]
            if item.get("code")
        ]
        payload["strategy"] = self.config.get("strategy", {})
        payload["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        return payload

    def save_result(self, payload: Mapping[str, Any], trade_date: Optional[str] = None) -> Path:
        date_tag = trade_date or datetime.now().strftime("%Y%m%d")
        stage_id = str(payload.get("stage_id", "stage"))
        target_dir = OUTPUT_DIR / "pools" / "funnel" / date_tag
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{stage_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def derive_open_gap(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Return copies with gap_pct derived from open and previous close."""
    result = []
    for item in records:
        record = dict(item)
        previous_close = float(record["previous_close"])
        opening = float(record["open"])
        if previous_close <= 0:
            raise ValueError(f"{record.get('code', '')}: previous_close must be positive")
        record["gap_pct"] = (opening / previous_close - 1.0) * 100
        result.append(record)
    return result


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "StockFunnelPipeline",
    "build_stock_rule_registry",
    "derive_open_gap",
    "load_funnel_config",
]
