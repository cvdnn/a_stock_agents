# -*- coding: utf-8 -*-
"""确定性哈希：规范化 JSON + SHA-256（S-02 / T-02）。

哈希契约（§7.2 编译契约第1条）：

- **键按字典序排序**、**去除无意义空白**、**数值统一为十进制字面量**（不使用科学计数法）、
  `null` 显式保留；
- 同一语义的 `1e2` / `100` / `100.0` 归一为同一字面量，键序与缩进差异不影响结果；
- `definition_hash` 覆盖规范化定义（规则结构与参数、依赖声明）；
- `plan_hash` 覆盖编译产物层计划 × `compiler_version` × 数据快照契约；
- **不含**运行时刻、数据环境或 `calendar_version` 等随运行变化的值。
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Iterable, Mapping

HASH_ALGORITHM = "sha256"
#: 计算 `plan_hash` 时应剔除的自身字段，保证复算幂等。
PLAN_HASH_FIELD = "plan_hash"
DEFINITION_HASH_FIELD = "definition_hash"


def _number_literal(value: Any) -> str:
    """把数值统一为十进制字面量：整数原样，浮点去科学计数法并按值归一。"""
    if isinstance(value, bool):  # bool 是 int 的子类，必须先拦截
        raise TypeError("bool 不是数值")
    if isinstance(value, int):
        return str(value)
    decimal_value = Decimal(repr(value))
    if not decimal_value.is_finite():
        raise ValueError(f"无法哈希非有限数值: {value!r}")
    if decimal_value == decimal_value.to_integral_value():
        return str(int(decimal_value))
    return format(decimal_value.normalize(), "f")


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _number_literal(value)
    if isinstance(value, Decimal):
        return _number_literal(float(value))
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, Mapping):
        items = []
        for key in sorted(value.keys(), key=lambda item: str(item)):
            if not isinstance(key, str):
                raise TypeError(f"JSON 对象键必须是字符串: {key!r}")
            items.append(f"{json.dumps(key, ensure_ascii=False)}:{_encode(value[key])}")
        return "{" + ",".join(items) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    raise TypeError(f"不支持的 JSON 值类型: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """返回确定性规范化 JSON 文本（键序/空白/数值写法无关）。"""
    return _encode(value)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(value: Any) -> str:
    """`sha256:<hex>` 形式的摘要，直接可由规范化文本独立复算。"""
    return f"{HASH_ALGORITHM}:{sha256_hex(canonical_json(value))}"


def _strip(payload: Mapping[str, Any], drop: Iterable[str]) -> dict:
    if not isinstance(payload, Mapping):
        raise TypeError("待哈希对象必须是映射结构")
    drop_set = set(drop)
    return {key: value for key, value in payload.items() if key not in drop_set}


def definition_hash(definition: Mapping[str, Any]) -> str:
    """已发布定义内容的哈希；发布后永久不变（§7.6）。"""
    return digest(_strip(definition, (DEFINITION_HASH_FIELD,)))


def plan_hash(plan: Mapping[str, Any]) -> str:
    """编译产物层计划的哈希：覆盖 `compiler_version` 与数据快照契约，可由规范文本复算。"""
    return digest(_strip(plan, (PLAN_HASH_FIELD,)))


def short_hash(digest_value: str, length: int = 12) -> str:
    """从 `sha256:<hex>` 摘要中取短哈希，供内容派生 `run_id` 使用（T-03）。"""
    raw = digest_value.split(":", 1)[-1]
    return raw[:length]


__all__ = [
    "DEFINITION_HASH_FIELD",
    "HASH_ALGORITHM",
    "PLAN_HASH_FIELD",
    "canonical_json",
    "definition_hash",
    "digest",
    "plan_hash",
    "sha256_hex",
    "short_hash",
]