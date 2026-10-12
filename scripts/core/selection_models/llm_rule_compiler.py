# -*- coding: utf-8 -*-
"""将 LLM 的受限意图 JSON 编译为可校验的选股草稿；本模块不调用网络。"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Mapping

from core.selection_models import schemas
from core.selection_models.catalog import blank_funnel_definition
from core.selection_models.model_compiler import compile_definition


class LLMRuleCompilerError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


INTENT_KINDS = (
    "market_hs_a", "exclude_st", "exclude_bse", "close_new_high",
    "close_above_sma", "sma_rising", "volume_gt_yesterday",
    "main_net_inflow_positive", "float_market_cap_gt", "daily_change_lte",
    "unresolved",
)


def split_clauses(text: str) -> List[str]:
    """只拆明确的并列条件；每个片段都必须由模型逐条交代。"""
    raw = str(text or "").strip().strip("` ")
    if not raw or len(raw) > 4000:
        raise LLMRuleCompilerError("MODEL_CONFIG_INVALID", "选股文案须为 1～4000 个字符")
    parts = [part.strip(" 。. `") for part in re.split(r"[，,、；;。\n]+|并且|(?<!而)且", raw)]
    clauses = [part for part in parts if part]
    if not clauses or len(clauses) > 40:
        raise LLMRuleCompilerError("MODEL_CONFIG_INVALID", "选股文案条件数量须为 1～40 条")
    return clauses


def _invalid(message: str) -> LLMRuleCompilerError:
    return LLMRuleCompilerError("MODEL_LLM_INVALID_OUTPUT", message)


def _number(params: Mapping[str, Any], key: str, clause: str, *, low: float, high: float) -> float:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(f"条件 {clause!r} 的 {key} 必须是数字")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise _invalid(f"条件 {clause!r} 的 {key} 超出允许范围")
    return value


def _integer(params: Mapping[str, Any], key: str, clause: str, *, low: int, high: int) -> int:
    value = _number(params, key, clause, low=low, high=high)
    if not value.is_integer():
        raise _invalid(f"条件 {clause!r} 的 {key} 必须是整数")
    return int(value)


def _literal_numbers(clause: str) -> List[float]:
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", clause)]


def _require(clause: str, pattern: str, kind: str) -> None:
    if not re.search(pattern, clause, flags=re.IGNORECASE):
        raise _invalid(f"模型把条件 {clause!r} 误映射为 {kind}")


def _make_rule(index: int, kind: str, params: Mapping[str, Any], clause: str) -> Dict[str, Any]:
    if kind not in INTENT_KINDS or kind == "unresolved":
        raise _invalid(f"未知意图类型: {kind}")
    if kind == "market_hs_a":
        _require(clause, r"沪深\s*A\s*股|上海.*深圳.*A\s*股", kind)
        rule = {"type": "market_include", "markets": ["sh", "sz"]}
    elif kind == "exclude_st":
        _require(clause, r"(?:非|排除|剔除).*\*?ST", kind)
        rule = {"type": "text_exclude", "tokens": ["ST"]}
    elif kind == "exclude_bse":
        _require(clause, r"(?:非|排除|剔除).*(?:北交所|北证)", kind)
        rule = {"type": "field_compare", "field": "market", "op": "ne", "value": "bj"}
    elif kind == "close_new_high":
        _require(clause, r"收盘价.*新高", kind)
        window = _integer(params, "window", clause, low=2, high=500)
        match = re.search(r"(\d+)\s*(?:个)?\s*(?:交易)?日.*收盘价.*新高|"
                          r"收盘价.*?(\d+)\s*(?:个)?\s*(?:交易)?日.*新高", clause)
        if not match or window != int(match.group(1) or match.group(2)):
            raise _invalid("收盘新高窗口与原文不一致")
        rule = {"type": "close_new_high", "field": "closes", "lookback": window, "strict": True}
    elif kind == "close_above_sma":
        _require(clause, r"(?:收盘价|股价).*(?:大于|高于|站上|>)\s*\d+\s*(?:日|天)均线", kind)
        period = _integer(params, "period", clause, low=2, high=500)
        match = re.search(r"(?:大于|高于|站上|>)\s*(\d+)\s*(?:日|天)均线", clause)
        if not match or period != int(match.group(1)):
            raise _invalid("均线周期与原文不一致")
        rule = {"type": "above_sma", "series_field": "closes", "period": period, "strict": True}
    elif kind == "sma_rising":
        _require(clause, r"均线.*(?:上升|向上|上行|抬升)", kind)
        period = _integer(params, "period", clause, low=2, high=500)
        lag = _integer(params, "lag", clause, low=1, high=250)
        match = re.search(r"(\d+)\s*(?:日|天)均线\s*近\s*(\d+)\s*(?:个)?\s*(?:交易)?日", clause)
        if not match or (period, lag) != (int(match.group(1)), int(match.group(2))):
            raise _invalid("均线上升周期或回看天数与原文不一致")
        rule = {"type": "sma_slope", "field": "closes", "period": period, "lag": lag,
                "min_slope_pct": 0.0, "strict": True}
    elif kind == "volume_gt_yesterday":
        _require(clause, r"(?:成交量|交易量).*(?:大于|超过|>)\s*(?:昨日|昨天|前一交易日)", kind)
        rule = {"type": "series_compare", "field": "volumes", "left_offset": -1,
                "right_offset": -2, "op": "gt"}
    elif kind == "main_net_inflow_positive":
        _require(clause, r"主力.*净流入", kind)
        numbers = _literal_numbers(clause)
        if numbers and (len(numbers) != 1 or numbers[0] != 0 or
                        not re.search(r"(?:大于|>)\s*0(?:\D|$)", clause)):
            raise _invalid("主力资金净流入只支持大于 0 的口径")
        if re.search(r"小于|低于|负|流出|<=|<", clause):
            raise _invalid("主力资金方向与大于 0 的口径冲突")
        rule = {"type": "field_compare", "field": "main_net_inflow", "op": "gt", "value": 0}
    elif kind == "float_market_cap_gt":
        _require(clause, r"流通市值.*(?:大于|超过|>)", kind)
        amount = _number(params, "yuan", clause, low=0.01, high=1e15)
        match = re.search(r"(\d+(?:\.\d+)?)\s*(万亿|亿|万|元)", clause)
        if not match:
            raise _invalid(f"流通市值条件 {clause!r} 缺少明确单位")
        unit = {"万亿": 1e12, "亿": 1e8, "万": 1e4, "元": 1}[match.group(2)]
        if not math.isclose(amount, float(match.group(1)) * unit, rel_tol=1e-9):
            raise _invalid("流通市值单位换算与原文不一致")
        rule = {"type": "field_compare", "field": "circulating_market_cap", "op": "gt",
                "value": amount, "require_present": True}
    else:  # daily_change_lte
        _require(clause, r"涨幅.*(?:小于等于|不超过|至多|≤|<=)", kind)
        pct = _number(params, "percent", clause, low=-100, high=100)
        match = re.search(r"(?:小于等于|不超过|至多|≤|<=)\s*(-?\d+(?:\.\d+)?)\s*%", clause)
        if not match or not math.isclose(pct, float(match.group(1)), rel_tol=0, abs_tol=1e-9):
            raise _invalid("涨幅上限与原文不一致")
        rule = {"type": "field_compare", "field": "change_pct", "op": "lte", "value": pct}
    return {"id": f"r_{kind}_{index}", **rule}


def compile_llm_draft(text: str, parsed: Mapping[str, Any], *, model_name: str) -> Dict[str, Any]:
    """模型只能选择已注册语义；未知/漏项保留歧义，永不自动保存或激活。"""
    clauses = split_clauses(text)
    items = parsed.get("clauses") if isinstance(parsed, Mapping) else None
    if not isinstance(items, list) or len(items) != len(clauses):
        raise _invalid("LLM 必须逐条返回全部原文条件")
    by_id: Dict[int, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping) or isinstance(item.get("id"), bool) or not isinstance(item.get("id"), int):
            raise _invalid("LLM 条件编号无效")
        index = item["id"]
        if index < 0 or index >= len(clauses) or index in by_id:
            raise _invalid("LLM 条件编号重复或越界")
        by_id[index] = item

    matched: List[Dict[str, Any]] = []
    ambiguities: List[str] = []
    for index, clause in enumerate(clauses):
        item = by_id[index]
        kind = str(item.get("kind") or "")
        if kind == "unresolved":
            reason = str(item.get("reason") or "无法确定规则口径").strip()[:200]
            ambiguities.append(f"{clause}：{reason}")
            continue
        params = item.get("params") or {}
        if not isinstance(params, Mapping):
            raise _invalid(f"条件 {clause!r} 的参数必须是对象")
        rule = _make_rule(index, kind, params, clause)
        matched.append({"clause_id": index, "text": clause, "rule": rule})

    if not matched:
        raise LLMRuleCompilerError("MODEL_CONFIG_INVALID", "没有任何可编译条件；请补充明确的规则")

    definition = blank_funnel_definition("__draft__", "LLM 选股草稿", None, template="blank")
    stage = definition["stages"][0]
    stage.update({"id": "post_close", "name": "收盘后初筛", "schedule": "15:35-23:59",
                  "missing_data_policy": "reject", "rules": [item["rule"] for item in matched]})
    definition["model"]["name"] = str(text).strip()[:24]
    definition["notes"] = [
        "由 LLM 规则编译生成；仅保留模型草稿，未自动发布或激活。",
        f"原始文案：{str(text).strip()}",
        f"解析模型：{model_name}",
    ]
    normalized, warnings = schemas.migrate_to_v2(definition)
    normalized["model"]["id"] = "__draft_pending__"
    compile_definition(normalized)
    return {
        "definition": normalized,
        "matched_rules": matched,
        "ambiguities": ambiguities,
        "warnings": list(warnings),
        "parser_mode": "llm",
        "model_name": model_name,
        "source_clauses": [{"id": i, "text": clause} for i, clause in enumerate(clauses)],
        "complete": not ambiguities,
        "activated": False,
    }
