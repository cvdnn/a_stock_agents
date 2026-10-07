# -*- coding: utf-8 -*-
"""规则类型元数据注册表：参数 Schema（JSON Schema 2020-12 子集）+ UI 注解（S-06 / A7）。

权威依据：SSOT §7.4（规则配置能力）与 S-06（参数元数据裁定）。

- 每个规则类型必须声明 `version`（计算口径版本）、`parameter_schema`、`required_inputs`
  与 `output_metrics`；
- `parameter_schema` 采用 JSON Schema 2020-12 的**子集**（type/min/max/enum/default/
  required/minItems/items/nullable），并叠加 UI 扩展注解（`x-ui-widget` /
  `x-quick-presets` / `x-unit` / `x-default`）；
- Web 表单由 `parameter_schema` **动态生成**，不为每种规则硬编码独立表单；
- 规则 `version` 参与 `plan_hash`：计算方式、边界或输出含义变化时必须递增，
  仅参数取值变化不递增（§7.4）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

#: 规则 spec 中非参数的**结构键**：其余键一律视为参数并参与参数 Schema 校验。
STRUCTURAL_RULE_KEYS = ("id", "type", "enabled", "version")

#: 参数 Schema 支持的 JSON Schema 子集类型。
SUPPORTED_PARAM_TYPES = ("integer", "number", "boolean", "string", "array", "field_ref", "any")


class RuleMetadataError(ValueError):
    """规则类型/参数元数据相关错误；`code` 为稳定错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _param(schema_type: str, **extra: Any) -> Dict[str, Any]:
    return {"type": schema_type, **extra}


def _number_param(default: Any, *, minimum: Any = None, maximum: Any = None, **extra: Any) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "number", "default": default, "x-default": default}
    if minimum is not None:
        schema["min"] = minimum
    if maximum is not None:
        schema["max"] = maximum
    schema.update(extra)
    return schema


def _int_param(default: Any, *, minimum: Any = None, maximum: Any = None, **extra: Any) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "integer", "default": default, "x-default": default}
    if minimum is not None:
        schema["min"] = minimum
    if maximum is not None:
        schema["max"] = maximum
    schema.update(extra)
    return schema


_OFFSETS = ("gt", "gte", "lt", "lte", "eq", "ne", "contains", "not_contains")

CONFIRMATION_NAMES = ("pullback", "price_reversal", "sell_exhaustion", "buy_strengthening", "book_support")

#: 全量规则元数据：与 `build_stock_rule_registry()` 注册的规则类型一一对应。
RULE_METADATA: Dict[str, Dict[str, Any]] = {
    "field_compare": {
        "version": 1,
        "label": "字段比较",
        "category": "通用",
        "description": "按运算符比较记录中的单值与期望值",
        "required_inputs": ["field"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "field": _param("field_ref", required=True, **{"x-ui-widget": "field-selector"}),
            "op": _param("string", default="eq", enum=list(_OFFSETS), **{"x-ui-widget": "select"}),
            "value": _param("any", required=True, **{"x-ui-widget": "value-input"}),
        },
    },
    "symbol_prefix_exclude": {
        "version": 1,
        "label": "代码前缀排除",
        "category": "风险面",
        "description": "按证券代码前缀排除（如北交所 4/8/92）",
        "required_inputs": ["code"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "field": _param("string", default="code", **{"x-ui-widget": "field-selector"}),
            "prefixes": _param(
                "array", required=True, minItems=1,
                items=_param("any"), **{"x-ui-widget": "tag-input"},
            ),
        },
    },
    "text_exclude": {
        "version": 1,
        "label": "文本词元排除",
        "category": "风险面",
        "description": "证券名称命中任一词元即排除（如 ST、退）",
        "required_inputs": ["name"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "field": _param("string", default="name", **{"x-ui-widget": "field-selector"}),
            "tokens": _param(
                "array", required=True, minItems=1,
                items=_param("string"), **{"x-ui-widget": "tag-input"},
            ),
        },
    },
    "rolling_high": {
        "version": 1,
        "label": "滚动新高",
        "category": "日线技术",
        "description": "最新值是否突破此前 N 个交易日高点",
        "required_inputs": ["series"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "field": _param("string", default="closes", **{"x-ui-widget": "field-selector"}),
            "lookback": _int_param(
                20, minimum=2, maximum=500,
                **{"x-quick-presets": [10, 20, 30, 60], "x-unit": "交易日"},
            ),
            "strict": _param("boolean", default=True, **{"x-ui-widget": "checkbox"}),
        },
    },
    "above_sma": {
        "version": 1,
        "label": "价格高于均线",
        "category": "日线技术",
        "description": "价格（或序列末值）是否高于 N 期简单均线",
        "required_inputs": ["series"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "series_field": _param("string", default="closes", **{"x-ui-widget": "field-selector"}),
            "period": _int_param(60, minimum=2, maximum=500, **{"x-unit": "日"}),
            "price_field": _param("field_ref", nullable=True, **{"x-ui-widget": "field-selector"}),
            "completed_bars_only": _param("boolean", default=False, **{"x-ui-widget": "checkbox"}),
            "strict": _param("boolean", default=True, **{"x-ui-widget": "checkbox"}),
        },
    },
    "sma_slope": {
        "version": 1,
        "label": "均线斜率",
        "category": "日线技术",
        "description": "N 期均线相对 lag 个交易日前的变化百分比",
        "required_inputs": ["series"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "field": _param("string", default="closes", **{"x-ui-widget": "field-selector"}),
            "period": _int_param(60, minimum=2, maximum=500, **{"x-unit": "日"}),
            "lag": _int_param(1, minimum=1, maximum=250, **{"x-unit": "日"}),
            "min_slope_pct": _number_param(0.0, **{"x-unit": "%"}),
            "strict": _param("boolean", default=True, **{"x-ui-widget": "checkbox"}),
        },
    },
    "series_compare": {
        "version": 1,
        "label": "序列间比较",
        "category": "日线技术",
        "description": "比较同一序列两个偏移位置的取值（如今日量 > 昨日量）",
        "required_inputs": ["series"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "field": _param("string", default="volumes", **{"x-ui-widget": "field-selector"}),
            "left_offset": _int_param(-1),
            "right_offset": _int_param(-2),
            "op": _param("string", default="gt", enum=list(_OFFSETS), **{"x-ui-widget": "select"}),
        },
    },
    "volume_sustained_expansion": {
        "version": 1,
        "label": "量能持续放大",
        "category": "日线技术",
        "description": "近 N 日均量相对前 M 日均量的放大倍数",
        "required_inputs": ["series"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "field": _param("string", default="volumes", **{"x-ui-widget": "field-selector"}),
            "window": _int_param(3, minimum=1, maximum=120, **{"x-unit": "日"}),
            "baseline_window": _int_param(5, minimum=1, maximum=250, **{"x-unit": "日"}),
            "min_ratio": _number_param(1.0, **{"x-unit": "倍"}),
            "strict": _param("boolean", default=True, **{"x-ui-widget": "checkbox"}),
        },
    },
    "range": {
        "version": 1,
        "label": "区间过滤",
        "category": "通用",
        "description": "字段值是否落在闭区间内（上下限可留空表示不设限）",
        "required_inputs": ["field"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "field": _param("field_ref", required=True, **{"x-ui-widget": "field-selector"}),
            "min": _number_param(None, nullable=True),
            "max": _number_param(None, nullable=True),
        },
    },
    "market_above_sma": {
        "version": 1,
        "label": "大盘高于均线",
        "category": "市场面",
        "description": "指数现价是否高于其前收盘 N 期均线（大盘门控）",
        "required_inputs": ["market.current_price", "market.completed_closes"],
        "output_metrics": ["observed", "expected"],
        "parameter_schema": {
            "benchmark": _param("string", default="sh000001", **{"x-ui-widget": "select"}),
            "price_field": _param("string", default="market.current_price", **{"x-ui-widget": "field-selector"}),
            "series_field": _param("string", default="market.completed_closes", **{"x-ui-widget": "field-selector"}),
            "period": _int_param(20, minimum=2, maximum=500, **{"x-unit": "日"}),
            "strict": _param("boolean", default=True, **{"x-ui-widget": "checkbox"}),
        },
    },
    "intraday_turning_point": {
        "version": 1,
        "label": "早盘拐点确认",
        "category": "盘中技术",
        "description": "回调 + 价格反转（可选供需确认）的分钟级拐点判定",
        "required_inputs": ["minute_points"],
        "output_metrics": ["drawdown_pct", "confirmations", "flow_source"],
        "parameter_schema": {
            "points_field": _param("string", default="minute_points", **{"x-ui-widget": "field-selector"}),
            "window_start": _param("string", default="09:30", **{"x-ui-widget": "time", "x-unit": "HH:MM"}),
            "window_end": _param("string", default="09:40", **{"x-ui-widget": "time", "x-unit": "HH:MM"}),
            "pullback_end": _param("string", default="09:35", **{"x-ui-widget": "time", "x-unit": "HH:MM"}),
            "confirm_start": _param("string", default="09:36", **{"x-ui-widget": "time", "x-unit": "HH:MM"}),
            "min_points": _int_param(6, minimum=1, **{"x-unit": "根"}),
            "min_pullback_pct": _number_param(0.20, **{"x-unit": "%"}),
            "max_pullback_pct": _number_param(2.00, **{"x-unit": "%"}),
            "max_sell_ratio": _number_param(0.75),
            "min_buy_ratio": _number_param(1.20),
            "min_book_ratio": _number_param(1.20),
            "min_pullback_points": _int_param(3, minimum=1, **{"x-unit": "根"}),
            "min_confirm_points": _int_param(2, minimum=1, **{"x-unit": "根"}),
            "price_mean_window": _int_param(3, minimum=1, **{"x-unit": "根"}),
            "flow_recent_window": _int_param(2, minimum=1, **{"x-unit": "根"}),
            "flow_baseline_window": _int_param(2, minimum=1, **{"x-unit": "根"}),
            "required": _param(
                "array", default=["pullback", "price_reversal"],
                items=_param("string", enum=list(CONFIRMATION_NAMES)), **{"x-ui-widget": "multi-select"},
            ),
            "confirmations": _param(
                "array", default=["sell_exhaustion", "buy_strengthening", "book_support"],
                items=_param("string", enum=list(CONFIRMATION_NAMES)), **{"x-ui-widget": "multi-select"},
            ),
            "min_confirmations": _int_param(0, minimum=0, maximum=len(CONFIRMATION_NAMES), **{"x-unit": "项"}),
            "output_policy": _param(
                "string", default="converge_at_window_end",
                enum=["converge_at_window_end"], **{"x-ui-widget": "select"},
            ),
            "metric_policy": _param(
                "string", default="real_only_for_signal",
                enum=["real_only_for_signal"], **{"x-ui-widget": "select"},
            ),
        },
    },
}


@dataclass
class RuleTypeMetadata:
    type_id: str
    version: int
    label: str
    category: str
    description: str
    parameter_schema: Dict[str, Any] = field(default_factory=dict)
    required_inputs: List[str] = field(default_factory=list)
    output_metrics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type_id,
            "version": self.version,
            "label": self.label,
            "category": self.category,
            "description": self.description,
            "parameter_schema": dict(self.parameter_schema),
            "required_inputs": list(self.required_inputs),
            "output_metrics": list(self.output_metrics),
        }


class RuleMetadataRegistry:
    """规则类型元数据注册表：参数 Schema 校验与 UI 表单注解来源。"""

    def __init__(self) -> None:
        self._metadata: Dict[str, RuleTypeMetadata] = {}

    def register(self, type_id: str, meta: Mapping[str, Any]) -> RuleTypeMetadata:
        if not type_id:
            raise RuleMetadataError("MODEL_RULE_UNKNOWN", "规则类型 ID 不能为空")
        schema = meta.get("parameter_schema")
        if not isinstance(schema, Mapping):
            raise RuleMetadataError("MODEL_RULE_UNKNOWN", f"规则 {type_id} 缺少 parameter_schema")
        self._validate_schema(type_id, schema)
        metadata = RuleTypeMetadata(
            type_id=type_id,
            version=int(meta.get("version", 1)),
            label=str(meta.get("label") or type_id),
            category=str(meta.get("category") or ""),
            description=str(meta.get("description") or ""),
            parameter_schema={str(key): dict(value) for key, value in schema.items()},
            required_inputs=[str(item) for item in meta.get("required_inputs", [])],
            output_metrics=[str(item) for item in meta.get("output_metrics", [])],
        )
        self._metadata[type_id] = metadata
        return metadata

    def get(self, type_id: str) -> RuleTypeMetadata:
        try:
            return self._metadata[type_id]
        except KeyError as exc:
            raise RuleMetadataError("MODEL_RULE_UNKNOWN", f"未知规则类型: {type_id}") from exc

    @property
    def names(self) -> List[str]:
        return sorted(self._metadata)

    def rule_version(self, type_id: str) -> int:
        return self.get(type_id).version

    def parameter_schema(self, type_id: str) -> Dict[str, Any]:
        return dict(self.get(type_id).parameter_schema)

    def defaults(self, type_id: str) -> Dict[str, Any]:
        schema = self.get(type_id).parameter_schema
        return {
            name: spec.get("default")
            for name, spec in schema.items()
            if "default" in spec
        }

    def form_annotations(self, type_id: str) -> Dict[str, Dict[str, Any]]:
        """供 Web 表单动态渲染的字段注解（类型 + 默认值 + `x-*` UI 扩展）。"""
        schema = self.get(type_id).parameter_schema
        annotations: Dict[str, Dict[str, Any]] = {}
        for name, spec in schema.items():
            annotation = {key: value for key, value in spec.items() if key != "items"}
            annotation["name"] = name
            annotation["default"] = spec.get("default", spec.get("x-default"))
            if "items" in spec:
                annotation["items"] = dict(spec["items"])
            annotations[name] = annotation
        return annotations

    def validate_params(self, type_id: str, params: Mapping[str, Any]) -> None:
        """按参数 Schema 校验规则参数；非法或缺参一律失败关闭。"""
        if not isinstance(params, Mapping):
            raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id} 参数必须是映射结构")
        schema = self.get(type_id).parameter_schema
        for name in params:
            if name not in schema:
                raise RuleMetadataError(
                    "MODEL_CONFIG_INVALID", f"规则 {type_id}: 未知参数 {name}"
                )
        for name, spec in schema.items():
            if spec.get("required") and name not in params:
                raise RuleMetadataError(
                    "MODEL_CONFIG_INVALID", f"规则 {type_id}: 缺少必填参数 {name}"
                )
            if name not in params:
                continue
            self._validate_value(type_id, name, params[name], spec)

    def validate_rule_spec(self, spec: Mapping[str, Any]) -> None:
        """校验一条规则 spec：结构键之外的字段全部按参数 Schema 校验。"""
        type_id = str(spec.get("type") or "")
        structural = {key: spec[key] for key in STRUCTURAL_RULE_KEYS if key in spec}
        declared_version = structural.get("version")
        if declared_version is not None and int(declared_version) != self.rule_version(type_id):
            raise RuleMetadataError(
                "MODEL_CONFIG_INVALID",
                f"规则 {type_id}: version={declared_version} 与注册口径版本 "
                f"{self.rule_version(type_id)} 不一致",
            )
        params = {key: value for key, value in spec.items() if key not in STRUCTURAL_RULE_KEYS}
        self.validate_params(type_id, params)

    # ------------------------------------------------------------ 内部校验
    def _validate_schema(self, type_id: str, schema: Mapping[str, Any]) -> None:
        for name, spec in schema.items():
            if not isinstance(spec, Mapping):
                raise RuleMetadataError("MODEL_RULE_UNKNOWN", f"规则 {type_id}: 参数 {name} 的 Schema 必须是映射")
            param_type = spec.get("type")
            if param_type not in SUPPORTED_PARAM_TYPES:
                raise RuleMetadataError(
                    "MODEL_RULE_UNKNOWN", f"规则 {type_id}: 参数 {name} 使用了不支持的 Schema 类型 {param_type!r}"
                )

    def _validate_value(self, type_id: str, name: str, value: Any, spec: Mapping[str, Any]) -> None:
        if value is None:
            if spec.get("nullable") or spec.get("type") == "any":
                return
            raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id}: 参数 {name} 不能为 null")

        param_type = spec["type"]
        if param_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id}: 参数 {name} 必须是整数")
        elif param_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id}: 参数 {name} 必须是数值")
        elif param_type == "boolean":
            if not isinstance(value, bool):
                raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id}: 参数 {name} 必须是布尔值")
        elif param_type in ("string", "field_ref"):
            if not isinstance(value, str):
                raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id}: 参数 {name} 必须是字符串")
        elif param_type == "array":
            if not isinstance(value, list):
                raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id}: 参数 {name} 必须是数组")
            if spec.get("minItems") is not None and len(value) < int(spec["minItems"]):
                raise RuleMetadataError(
                    "MODEL_CONFIG_INVALID",
                    f"规则 {type_id}: 参数 {name} 至少需要 {spec['minItems']} 项",
                )
            item_spec = spec.get("items")
            if isinstance(item_spec, Mapping):
                for item in value:
                    self._validate_value(type_id, f"{name}[]", item, item_spec)

        if "min" in spec and value < spec["min"]:
            raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id}: 参数 {name} 小于下限 {spec['min']}")
        if "max" in spec and value > spec["max"]:
            raise RuleMetadataError("MODEL_CONFIG_INVALID", f"规则 {type_id}: 参数 {name} 大于上限 {spec['max']}")
        if "enum" in spec and value not in spec["enum"]:
            raise RuleMetadataError(
                "MODEL_CONFIG_INVALID",
                f"规则 {type_id}: 参数 {name}={value!r} 不在允许取值 {list(spec['enum'])} 内",
            )


def build_default_rule_registry() -> RuleMetadataRegistry:
    registry = RuleMetadataRegistry()
    for type_id, meta in RULE_METADATA.items():
        registry.register(type_id, meta)
    return registry


__all__ = [
    "CONFIRMATION_NAMES",
    "RULE_METADATA",
    "STRUCTURAL_RULE_KEYS",
    "SUPPORTED_PARAM_TYPES",
    "RuleMetadataError",
    "RuleMetadataRegistry",
    "RuleTypeMetadata",
    "build_default_rule_registry",
]