# -*- coding: utf-8 -*-
"""A-share rule plug-ins and orchestration for the configurable funnel."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

from scripts.core.workspace import OUTPUT_DIR, PROJECT_ROOT
#: 分钟时间戳原因码的唯一权威定义在装配层（`data_layer`），规则层只引用不重定义，
#: 否则「超出范围」会在两处各有一份字面量，任一处改动即令两端原因码静默分叉。
from core.data.data_layer import MINUTE_TS_OUT_OF_RANGE
from core.strategy.funnel_engine import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    FunnelEngine,
    RuleRegistry,
    RuleResult,
)

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "funnel_strategy.yaml"

#: 信号定性档位（A-04 / §7.4）：候选 ≠ 正式信号。`selected_codes` 为观察候选清单，
#: 只有不携带 `not_eligible_for_signal` 的候选才可作为正式信号发布。
SIGNAL_CLASS_FORMAL = "formal_signal_candidate"
SIGNAL_CLASS_OBSERVATION = "observation_candidate"

#: 代理口径数据源（§7.5 第2条）：缺真实主动买卖量/盘口契约时以分钟涨跌量透明代理，
#: 只允许调试预演。引擎强制标记 `not_eligible_for_signal`，不得进入正式候选列表。
PROXY_FLOW_SOURCES = frozenset({"price_direction_volume_proxy"})


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
    return RuleResult.two_state("", passed, reason=f"{field}={observed!r}", observed=observed, expected=expected)


def rule_symbol_prefix_exclude(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    code = str(_path_get(record, str(spec.get("field", "code")))).lower()
    clean = code.replace("sh", "").replace("sz", "").replace("bj", "")
    excluded = tuple(str(item) for item in spec.get("prefixes", []))
    passed = not clean.startswith(excluded)
    return RuleResult.two_state("", passed, reason=f"代码={clean}", observed=clean, expected=f"不以{excluded}开头")


def rule_text_exclude(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    text = str(_path_get(record, str(spec.get("field", "name")))).upper()
    tokens = [str(item).upper() for item in spec.get("tokens", [])]
    matched = [token for token in tokens if token in text]
    return RuleResult.two_state("", not matched, reason=f"命中排除词: {matched}" if matched else "未命中排除词", observed=text, expected=tokens)


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
    return RuleResult.two_state("", passed, reason=f"最新收盘={current:.4f}, 前期高点={threshold:.4f}", observed=current, expected=threshold)


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
    return RuleResult.two_state("", passed, reason=f"价格={price:.4f}, MA{period}={sma:.4f}", observed=price, expected=sma)


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
    return RuleResult.two_state("", passed, reason=f"MA{period}斜率={slope_pct:.4f}%", observed=slope_pct, expected=min_slope_pct)


def rule_series_compare(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    series = _numbers(_path_get(record, str(spec.get("field", "volumes"))))
    left_offset = int(spec.get("left_offset", -1))
    right_offset = int(spec.get("right_offset", -2))
    # 序列长度不足必须报"数据不足"（→ UNKNOWN），不得让越界索引把整阶段求值打断。
    # 负向偏移 `-k` 至少要 `k` 个元素；非负偏移 `k` 至少要 `k + 1` 个元素。
    needed = max(abs(offset) if offset < 0 else offset + 1
                 for offset in (left_offset, right_offset))
    if needed > len(series):
        raise ValueError(f"至少需要 {needed} 个数据点，当前 {len(series)} 个")
    left, right = series[left_offset], series[right_offset]
    passed = _compare(left, str(spec.get("op", "gt")), right)
    return RuleResult.two_state("", passed, reason=f"序列比较: {left} vs {right}", observed=left, expected=right)


def rule_volume_sustained_expansion(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    """量能持续放大：近 N 日均量相对前 M 日均量的放大倍数。

    与单日放量 `series_compare` 区分：本规则判定的是"一段时间重心上移"，
    而非仅"今日量 > 昨日量"。`window` / `baseline_window` / `min_ratio`
    全部参数化，可在可视化配置中微调。
    """
    series = _numbers(_path_get(record, str(spec.get("field", "volumes"))))
    window = int(spec.get("window", 3))
    baseline_window = int(spec.get("baseline_window", 5))
    min_ratio = float(spec.get("min_ratio", 1.0))
    if window < 1 or baseline_window < 1:
        raise ValueError("window 与 baseline_window 必须为正整数")
    if len(series) < window + baseline_window:
        raise ValueError(f"至少需要 {window + baseline_window} 个数据点")
    recent = mean(series[-window:])
    baseline = mean(series[-window - baseline_window:-window])
    ratio = recent / baseline if baseline else float("inf")
    passed = ratio > min_ratio if bool(spec.get("strict", True)) else ratio >= min_ratio
    return RuleResult.two_state(
        "",
        passed,
        reason=f"近{window}日均量/前{baseline_window}日均量={ratio:.4f}",
        observed=ratio,
        expected=min_ratio,
    )


def rule_range(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    field = str(spec["field"])
    value = float(_path_get(record, field))
    min_value = spec.get("min")
    max_value = spec.get("max")
    min_ok = True if min_value is None else value >= float(min_value)
    max_ok = True if max_value is None else value <= float(max_value)
    return RuleResult.two_state("", min_ok and max_ok, reason=f"{field}={value:.4f}", observed=value, expected={"min": min_value, "max": max_value})


def rule_market_above_sma(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    price = float(_path_get(record, str(spec.get("price_field", "market.current_price"))))
    closes = _numbers(_path_get(record, str(spec.get("series_field", "market.completed_closes"))))
    period = int(spec.get("period", 20))
    if len(closes) < period:
        raise ValueError(f"大盘至少需要 {period} 根已完成日K")
    sma = mean(closes[-period:])
    passed = price > sma if bool(spec.get("strict", True)) else price >= sma
    return RuleResult.two_state("", passed, reason=f"指数现价={price:.4f}, 前收盘MA{period}={sma:.4f}", observed=price, expected=sma)


MINUTE_TS_NOT_NORMALIZED = "MINUTE_TIMESTAMP_NOT_NORMALIZED"
MINUTE_BAR_NOT_FINALIZED = "MINUTE_BAR_NOT_FINALIZED"

#: 分钟窗口起止的唯一默认值来源（§11.5 / T-04）：编译期推导、取点窗口与规则求值三处必须同源。
#: 三处各写一份字面量时，同一份配置会出现"编译期推得的可命中时点"与"运行期实际窗口"不一致。
DEFAULT_MINUTE_WINDOW: Dict[str, str] = {
    "window_start": "09:30",
    "window_end": "09:40",
    "pullback_end": "09:35",
    "confirm_start": "09:35",
}

#: 拐点窗口判定参数默认值（T-04）：均价回溯点数与量能对比窗口，均可由 stage spec 覆盖。
#: 默认值与参数化之前的字面量逐一对应（3 / 2 / 2），改参数不影响既有默认口径。
DEFAULT_TURNING_POINT_PARAMS: Dict[str, int] = {
    "price_mean_window": 3,
    "flow_recent_window": 2,
    "flow_baseline_window": 2,
}

# 拐点规则的 UNKNOWN 原因码（§7.7.2：原 status 退化为 reason_code，不承担布尔语义）。
MINUTE_POINTS_UNAVAILABLE = "MINUTE_POINTS_UNAVAILABLE"
MINUTE_POINTS_INSUFFICIENT = "MINUTE_POINTS_INSUFFICIENT"
MINUTE_SEGMENT_INSUFFICIENT = "MINUTE_SEGMENT_INSUFFICIENT"
REQUIRED_CONFIRMATION_UNAVAILABLE = "REQUIRED_CONFIRMATION_UNAVAILABLE"
OPTIONAL_CONFIRMATION_UNAVAILABLE = "OPTIONAL_CONFIRMATION_UNAVAILABLE"


def _minute_timestamp_reason(timestamp: Any) -> Optional[str]:
    """校验时间戳是否已是装配层归一化的 Bar 起点 `HH:MM`（规范 §11.5）。

    规则层只做格式与范围校验：自行解析、截取或比较原始时间字符串会把
    `HH:MM:SS` 截成 `36:00` 并被窗口静默排除，故障表现为恒不出信号且无告警。
    """
    if not isinstance(timestamp, str) or len(timestamp) != 5 or timestamp[2] != ":":
        return MINUTE_TS_NOT_NORMALIZED
    if not (timestamp[:2].isdigit() and timestamp[3:].isdigit()):
        return MINUTE_TS_NOT_NORMALIZED
    if not "00:00" <= timestamp <= "23:59":
        return MINUTE_TS_OUT_OF_RANGE
    return None


# 分钟窗口规则的参数键：命中时点受"Bar 定盘"约束，须在编译期推导 earliest_possible_hit_time。
MINUTE_WINDOW_SPEC_KEYS = (
    "window_start",
    "confirm_start",
    "min_points",
    "min_pullback_points",
    "min_confirm_points",
)


def is_minute_window_spec(spec: Mapping[str, Any]) -> bool:
    """判断规则参数是否为分钟窗口规则。"""
    return any(key in spec for key in MINUTE_WINDOW_SPEC_KEYS)


def _finalized_bar_time(bar_start: str, bars: int) -> str:
    """自 `bar_start` 起连续排布的 `bars` 根Bar全部定盘的最早时刻。

    Bar 以**起点**标识：起点 T 的Bar覆盖 T:00–T:59，收满 60 秒才定盘于 T+1 分钟。
    故第 `bars` 根Bar起点为 T+(bars-1)，其定盘时刻为 T+bars。
    起点未归一化为 `HH:MM` 时失败关闭，不做任何字符串截取（§11.5 禁止事项）。
    """
    reason = _minute_timestamp_reason(bar_start)
    if reason is not None:
        raise ValueError(f"分钟窗口起点 {bar_start!r} 不是已归一化的 HH:MM: {reason}")
    total = int(bar_start[:2]) * 60 + int(bar_start[3:]) + int(bars)
    if total > 23 * 60 + 59:
        raise ValueError(f"最早可命中时点超出 23:59: {bar_start} + {bars} 分钟")
    return f"{total // 60:02d}:{total % 60:02d}"


def derive_earliest_possible_hit_time(spec: Mapping[str, Any]) -> Optional[str]:
    """编译期推导"最早可命中时点"（§5.5 编译约束第5条 / §11.5）。

    只计**已定盘**Bar：进行中Bar既不提前该时点，也不构成"已命中"证据。
    取三项约束的最晚者（`n <= 0` 视为该项无约束，三项皆无约束时返回 None）：

    - 窗口整体：`window_start + min_points`
    - 回调段：`window_start + min_pullback_points`（回调段是窗口子集，通常被上一项支配）
    - 确认段：`confirm_start + min_confirm_points`

    该值必须由编译期推导输出，Web 与文档不得手工填写。
    """
    if not is_minute_window_spec(spec):
        return None
    window_start = str(spec.get("window_start", DEFAULT_MINUTE_WINDOW["window_start"]))
    # 确认段起点的默认值必须与运行期规则同源（DEFAULT_MINUTE_WINDOW），否则编译期会按
    # "从窗口起点开始确认"推导，而运行期实际从 09:35 起算，earliest_possible_hit_time 被低估。
    confirm_start = str(spec.get("confirm_start", DEFAULT_MINUTE_WINDOW["confirm_start"]))
    # 起点合法性先行校验：即使该项无约束，未归一化的起点也会让窗口比较静默失效。
    for base in (window_start, confirm_start):
        reason = _minute_timestamp_reason(base)
        if reason is not None:
            raise ValueError(f"分钟窗口起点 {base!r} 不是已归一化的 HH:MM: {reason}")
    terms = [
        _finalized_bar_time(base, count)
        for base, count in (
            (window_start, int(spec.get("min_points", 0))),
            (window_start, int(spec.get("min_pullback_points", 0))),
            (confirm_start, int(spec.get("min_confirm_points", 0))),
        )
        if count > 0
    ]
    return max(terms) if terms else None


def _minute_points(
    record: Mapping[str, Any], spec: Mapping[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回窗口内的分钟点，以及被剔除点及其 field_status 与原因码。

    被剔除点包含两类：时间戳未按 §11.5 归一化的点（`missing`），以及
    进行中尚未收满的Bar（`not_ready`，见 §11.5 进行中Bar与定盘）；两类都必须
    计入 `dropped_point_count`，不得静默丢弃。
    """
    points = _path_get(record, str(spec.get("points_field", "minute_points")))
    if not isinstance(points, list):
        raise ValueError("minute_points 必须是列表")
    start = str(spec.get("window_start", DEFAULT_MINUTE_WINDOW["window_start"]))
    end = str(spec.get("window_end", DEFAULT_MINUTE_WINDOW["window_end"]))
    result = []
    dropped = []
    for point in points:
        timestamp = point.get("time")
        reason = _minute_timestamp_reason(timestamp)
        if reason is not None:
            dropped.append({"raw_time": timestamp, "field_status": "missing", "reason_code": reason})
            continue
        if point.get("field_status") == "not_ready":
            dropped.append({"raw_time": timestamp, "field_status": "not_ready", "reason_code": MINUTE_BAR_NOT_FINALIZED})
            continue
        if start <= timestamp <= end:
            normalized = dict(point)
            normalized["time"] = timestamp
            normalized["price"] = float(point["price"])
            normalized["volume"] = float(point.get("volume", 0))
            result.append(normalized)
    result.sort(key=lambda item: item["time"])
    return result, dropped


def _minute_points_field_status(points: Sequence[Dict[str, Any]], dropped: Sequence[Dict[str, Any]]) -> str:
    """给出分钟点字段的整体 field_status，供 §7.7 三态判定与审计使用。"""
    if points:
        return "present"
    if dropped and all(item["field_status"] == "not_ready" for item in dropped):
        return "not_ready"
    return "missing"


def _ratio(recent: Sequence[float], previous: Sequence[float]) -> Optional[float]:
    if not recent or not previous:
        return None
    denominator = mean(previous)
    if denominator <= 0:
        return None
    return mean(recent) / denominator


def rule_intraday_turning_point(record: Mapping[str, Any], spec: Mapping[str, Any], _: Mapping[str, Any]) -> RuleResult:
    points, dropped = _minute_points(record, spec)
    diagnostics = {
        "dropped_point_count": len(dropped),
        "dropped_points": dropped,
        "minute_points_field_status": _minute_points_field_status(points, dropped),
    }
    min_points = int(spec.get("min_points", 6))
    if not points and dropped:
        return RuleResult(
            "",
            verdict=VERDICT_UNKNOWN,
            reason_code=MINUTE_POINTS_UNAVAILABLE,
            reason=f"窗口内 {len(dropped)} 个分钟点全部不可用",
            metrics=diagnostics,
        )
    if len(points) < min_points:
        return RuleResult(
            "",
            verdict=VERDICT_UNKNOWN,
            reason_code=MINUTE_POINTS_INSUFFICIENT,
            reason=f"分钟数据不足: {len(points)}/{min_points}",
            metrics=diagnostics,
        )

    pullback_end = str(spec.get("pullback_end", DEFAULT_MINUTE_WINDOW["pullback_end"]))
    confirm_start = str(spec.get("confirm_start", DEFAULT_MINUTE_WINDOW["confirm_start"]))
    pullback = [p for p in points if p["time"] <= pullback_end]
    confirm = [p for p in points if p["time"] >= confirm_start]
    min_pullback_points = int(spec.get("min_pullback_points", 3))
    min_confirm_points = int(spec.get("min_confirm_points", 2))
    if len(pullback) < min_pullback_points or len(confirm) < min_confirm_points:
        return RuleResult(
            "",
            verdict=VERDICT_UNKNOWN,
            reason_code=MINUTE_SEGMENT_INSUFFICIENT,
            reason=f"回调段或确认段分钟数不足: {len(pullback)}/{min_pullback_points}, {len(confirm)}/{min_confirm_points}",
            metrics={
                **diagnostics,
                "pullback_points": len(pullback),
                "confirm_points": len(confirm),
                "min_pullback_points": min_pullback_points,
                "min_confirm_points": min_confirm_points,
            },
        )

    peak_idx = max(range(len(pullback)), key=lambda i: pullback[i]["price"])
    after_peak = pullback[peak_idx:]
    peak = pullback[peak_idx]["price"]
    trough = min(p["price"] for p in after_peak)
    drawdown_pct = (peak - trough) / peak * 100 if peak else 0.0
    min_pullback = float(spec.get("min_pullback_pct", 0.2))
    max_pullback = float(spec.get("max_pullback_pct", 2.0))
    pullback_ok = peak_idx < len(pullback) - 1 and min_pullback <= drawdown_pct <= max_pullback

    # T-04 全量参数化：以下三处窗口长度全部由 stage spec 配置，默认值与参数化前一致。
    price_mean_window = int(spec.get("price_mean_window", DEFAULT_TURNING_POINT_PARAMS["price_mean_window"]))
    flow_recent_window = int(spec.get("flow_recent_window", DEFAULT_TURNING_POINT_PARAMS["flow_recent_window"]))
    flow_baseline_window = int(spec.get("flow_baseline_window", DEFAULT_TURNING_POINT_PARAMS["flow_baseline_window"]))
    if min(price_mean_window, flow_recent_window, flow_baseline_window) < 1:
        raise ValueError("price_mean_window / flow_recent_window / flow_baseline_window 必须为正整数")
    # 判定窗口长度下界：价格反转至少需 2 根 Bar 比较，量能对比至少需 近端段+基线段 的合长。
    flow_span = flow_recent_window + flow_baseline_window
    needed_points = max(2, flow_span)
    if len(points) < needed_points:
        raise ValueError(f"分钟点不足以构成判定窗口: {len(points)} < {needed_points}")

    prices = [p["price"] for p in points]
    price_reversal = prices[-1] > prices[-2] and prices[-1] > mean(prices[-price_mean_window:])

    # Prefer explicit active buy/sell volume.  If unavailable, use up/down
    # minute volume as a transparent proxy rather than fabricating order flow.
    recent = points[-flow_recent_window:]
    previous = points[-flow_span:-flow_recent_window]
    explicit_flow = all("buy_volume" in p and "sell_volume" in p for p in points[-flow_span:])
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

    book = record.get("order_book")
    bid_volume = book.get("bid_volume") if isinstance(book, Mapping) else None
    ask_volume = book.get("ask_volume") if isinstance(book, Mapping) else None
    # 盘口缺失或卖盘为 0 时比值无定义：留空交由三态判定（§7.7.7），
    # 不得默认 0 把“缺失”静默降级成“不成立”。
    if bid_volume is None or ask_volume is None or float(ask_volume) <= 0:
        book_ratio = None
    else:
        book_ratio = float(bid_volume) / float(ask_volume)
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
    # 三态判定（§7.7.5）：只数 PASS；数据不可用不产生 FAIL，一律记 UNKNOWN。
    if passed:
        verdict, reason_code = VERDICT_PASS, ""
    elif required_unavailable:
        verdict, reason_code = VERDICT_UNKNOWN, REQUIRED_CONFIRMATION_UNAVAILABLE
    elif optional_count < min_confirmations and unavailable:
        verdict, reason_code = VERDICT_UNKNOWN, OPTIONAL_CONFIRMATION_UNAVAILABLE
    else:
        verdict, reason_code = VERDICT_FAIL, ""
    metrics = {
        **diagnostics,
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
    if verdict == VERDICT_PASS:
        reason = "拐点确认"
    elif verdict == VERDICT_UNKNOWN:
        reason = f"拐点待定（数据未就绪）: {reason_code}"
    else:
        reason = "拐点条件不成立"
    return RuleResult(
        "",
        verdict=verdict,
        reason_code=reason_code,
        reason=reason,
        observed=confirmations,
        expected={"required": required, "min_confirmations": min_confirmations},
        metrics=metrics,
    )


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
        "volume_sustained_expansion": rule_volume_sustained_expansion,
        "range": rule_range,
        "market_above_sma": rule_market_above_sma,
        "intraday_turning_point": rule_intraday_turning_point,
    }.items():
        registry.register(name, evaluator)
    return registry


#: 阶段 `schedule` 的形态为 `HH:MM-HH:MM`。声明了却不被任何代码读取的时间窗等于死配置，
#: 因此加载期即读取并校验，避免"看起来生效、实际无人读"。
def _is_hhmm(value: str) -> bool:
    return (
        len(value) == 5
        and value[2] == ":"
        and value[:2].isdigit()
        and value[3:].isdigit()
        and 0 <= int(value[:2]) <= 23
        and 0 <= int(value[3:]) <= 59
    )


def _validate_stage_schedule(stage_id: str, schedule: Any) -> None:
    if not isinstance(schedule, str) or schedule.count("-") != 1:
        raise ValueError(f"stage {stage_id}: schedule 必须是 'HH:MM-HH:MM' 形态，实际 {schedule!r}")
    start, end = schedule.split("-")
    if not _is_hhmm(start) or not _is_hhmm(end):
        raise ValueError(f"stage {stage_id}: schedule 起止时间不是合法 HH:MM，实际 {schedule!r}")
    if end <= start:
        raise ValueError(f"stage {stage_id}: schedule 结束时间不得早于或等于开始时间，实际 {schedule!r}")


#: 规则级策略键的合法取值：读取并校验，不得作为无人读的装饰性配置留下。
RULE_POLICY_VALUES: Dict[str, frozenset] = {
    "output_policy": frozenset({"converge_at_window_end"}),
    "metric_policy": frozenset({"real_only_for_signal"}),
}


def _validate_rule_policies(stage_id: str, rule: Mapping[str, Any]) -> None:
    for key, allowed in RULE_POLICY_VALUES.items():
        if key not in rule:
            continue
        if rule[key] not in allowed:
            raise ValueError(
                f"stage {stage_id} rule {rule.get('id')}: {key}={rule[key]!r} 不在允许取值 {sorted(allowed)} 内"
            )


#: 与 stages 同级、已冻结但引擎尚未实现对应 Stage 的参数块（参数蓝本 §9）。
#: 引擎落地前只登记不执行，但必须被读取：缺失或未标注 `status: declared` 即失败关闭。
DECLARED_BLOCK_KEYS = ("ranking", "risk_exit")
DECLARED_STATUS = "declared"


def _read_declared_blocks(config: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    declared: Dict[str, Dict[str, Any]] = {}
    for key in DECLARED_BLOCK_KEYS:
        block = config.get(key)
        if block is None:
            continue
        if not isinstance(block, Mapping):
            raise ValueError(f"declared block {key} 必须是映射结构")
        if block.get("status") != DECLARED_STATUS:
            raise ValueError(
                f"declared block {key}: status 必须为 {DECLARED_STATUS!r}，实际 {block.get('status')!r}"
            )
        declared[key] = {
            "status": DECLARED_STATUS,
            "name": block.get("name"),
            "stage": block.get("stage"),
        }
    return declared


def load_funnel_config(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = Path(path or DEFAULT_CONFIG_PATH)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data.get("stages"), list) or not data["stages"]:
        raise ValueError("funnel config requires a non-empty stages list")
    # 逐阶段读取 schedule 与规则级策略键：声明即被读取，不允许静默留存无人消费的配置项。
    for stage in data["stages"]:
        stage_id = str(stage.get("id", ""))
        if "schedule" in stage:
            _validate_stage_schedule(stage_id, stage["schedule"])
        for rule in stage.get("rules") or []:
            _validate_rule_policies(stage_id, rule)
    data["declared_blocks"] = _read_declared_blocks(data)
    return data


def _record_flow_sources(record: Mapping[str, Any]) -> List[str]:
    """汇总候选在全部阶段留痕中的 `flow_source`（规则 metrics，§7.5）。"""
    audits: List[Mapping[str, Any]] = []
    history = record.get("_funnel_history")
    if isinstance(history, list):
        audits.extend(item for item in history if isinstance(item, Mapping))
    current = record.get("_funnel")
    if isinstance(current, Mapping):
        audits.append(current)
    sources: List[str] = []
    for audit in audits:
        for rule in audit.get("rules") or []:
            if not isinstance(rule, Mapping):
                continue
            metrics = rule.get("metrics")
            if not isinstance(metrics, Mapping):
                continue
            source = metrics.get("flow_source")
            if source is not None:
                sources.append(str(source))
    return sources


def classify_signal_record(record: Mapping[str, Any]) -> Tuple[str, bool]:
    """引擎强制的信号定性（A-04 / §7.4 / §7.5 第2条），不随配置开关绕过。

    返回 `(signal_class, not_eligible_for_signal)`：候选留痕中一旦出现代理口径
    （`flow_source` ∈ `PROXY_FLOW_SOURCES`），即为观察候选并强制携带
    `not_eligible_for_signal=True`，在发布阶段被阻断，不得作为正式信号下发。
    """
    if any(source in PROXY_FLOW_SOURCES for source in _record_flow_sources(record)):
        return SIGNAL_CLASS_OBSERVATION, True
    return SIGNAL_CLASS_FORMAL, False


class StockFunnelPipeline:
    """Run configured A-share stages and optionally archive handoff results."""

    def __init__(self, config: Optional[Mapping[str, Any]] = None, config_path: Optional[Path] = None) -> None:
        self.config = dict(config or load_funnel_config(config_path))
        self.registry = build_stock_rule_registry()
        self.engine = FunnelEngine(self.registry)
        all_stage_ids = [str(stage["id"]) for stage in self.config["stages"]]
        if len(set(all_stage_ids)) != len(all_stage_ids):
            raise ValueError("stage ids must be unique")
        # 编译期：逐阶段校验规则契约，并推导 earliest_possible_hit_time（§5.5 / §11.5）。
        self.earliest_possible_hit_times: Dict[str, Dict[str, Optional[str]]] = {}
        for stage in self.config["stages"]:
            self.engine.validate_stage(stage)
            derived = {
                str(rule["id"]): derive_earliest_possible_hit_time(rule)
                for rule in stage["rules"]
                if rule.get("enabled", True) and is_minute_window_spec(rule)
            }
            if derived:
                self.earliest_possible_hit_times[str(stage["id"])] = derived
        self._stages = {
            str(stage["id"]): stage
            for stage in self.config["stages"]
            if stage.get("enabled", True)
        }

    @property
    def stage_ids(self) -> List[str]:
        return list(self._stages)

    @property
    def stage_schedules(self) -> Dict[str, Any]:
        """各阶段声明的时间窗：加载期已读取并校验形态，此处供 CLI/Web 展示。"""
        return {
            stage_id: stage.get("schedule")
            for stage_id, stage in self._stages.items()
            if stage.get("schedule")
        }

    @property
    def declared_blocks(self) -> Dict[str, Dict[str, Any]]:
        """声明态参数块（ranking/risk_exit）：已冻结但尚未参与执行，读取后原样登记。"""
        return dict(self.config.get("declared_blocks") or {})

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
        # 信号定性（A-04 / §7.4 / §7.5 第2条）：逐候选显式标注档位；代理档在发布阶段
        # 即阻断——只进入观察清单，不进入正式候选 `eligible_signal_codes`。
        selected_codes: List[str] = []
        eligible_signal_codes: List[str] = []
        for item in payload["passed_records"]:
            signal_class, not_eligible = classify_signal_record(item)
            item["signal_class"] = signal_class
            item["not_eligible_for_signal"] = not_eligible
            code = str(item.get("code", ""))
            if not code:
                continue
            selected_codes.append(code)
            if not not_eligible:
                eligible_signal_codes.append(code)
        payload["selected_codes"] = selected_codes
        payload["eligible_signal_codes"] = eligible_signal_codes
        # 输出整体携带降级标记（§7.4）：清单内存在任一不可下单项即置 True。
        payload["not_eligible_for_signal"] = len(eligible_signal_codes) != len(selected_codes)
        payload["strategy"] = self.config.get("strategy", {})
        payload["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        # 编译期计划输出（§5.5/§11.5）：由规则参数推导，Web 与文档不得手工填写。
        payload["plan"] = {
            "earliest_possible_hit_time": self.earliest_possible_hit_times.get(stage_id, {}),
        }
        # 运行元数据（§11.2/§11.7）：calendar_version 随本地交易日集合内容变化，
        # 只记录在运行快照清单与运行元数据中，**不进入 plan_hash**——plan_hash 只覆盖
        # 模型定义、规则与参数，不得包含运行时刻、数据环境或日历内容等随运行变化的值。
        run_context = dict(context or {})
        run_metadata = {
            "calendar_version": run_context.get("calendar_version"),
            "calendar_available": run_context.get("calendar_available"),
        }
        # §11.7 快照溯源：仅当装配层真实交付清单时才记入，未装配时不得伪造空清单字段。
        for key in ("data_snapshots", "data_gate"):
            if run_context.get(key) is not None:
                run_metadata[key] = run_context[key]
        payload["run_metadata"] = run_metadata
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
    "DECLARED_BLOCK_KEYS",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_MINUTE_WINDOW",
    "DEFAULT_TURNING_POINT_PARAMS",
    "PROXY_FLOW_SOURCES",
    "RULE_POLICY_VALUES",
    "SIGNAL_CLASS_FORMAL",
    "SIGNAL_CLASS_OBSERVATION",
    "StockFunnelPipeline",
    "build_stock_rule_registry",
    "classify_signal_record",
    "derive_earliest_possible_hit_time",
    "derive_open_gap",
    "is_minute_window_spec",
    "load_funnel_config",
]