# -*- coding: utf-8 -*-
"""Selection model definition schema (v2) and the v1 → v2 in-memory migrator.

权威依据：[`SPEC-ALGO-ISS-001`](../../../docs/guidelines/algorithm/selection-system-specification.md)
§7.1（模型定义）与 §7.6（存储与版本控制）。

设计要点（S-01 / T-06）：

1. 统一 **v2** 结构：`schema_version` + `model`（模型元信息）+ `data_requirements`
   + `stages`（有序层级）+ 声明态参数块；
2. v1 加载时**内存迁移**为 v2 结构，原文件**不被自动改写**，并返回 WARNING 级告警；
3. 迁移函数**幂等**：已是 v2 的输入原样归一返回，不产生二次改写；
4. 归一化输出只保留可复现的确定性字段，**不含**运行时刻、数据环境等随运行变化的值
   （`calendar_version` 等运行元数据不得进入 `definition_hash`）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1

CONDITION_TREE_TYPE = "condition_tree"
DEFAULT_MODEL_TYPE = "funnel"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_EXCHANGE_CALENDAR = "CN_STOCK"
DEFAULT_MISSING_DATA_POLICY = "reject"

#: 阶段 scope → 首期层级 kind 的默认映射（§7.2：首期仅 filter/gate/output 可执行）。
SCOPE_TO_KIND = {"universe_gate": "gate", "candidate_filter": "filter"}
#: Schema 层允许声明的节点类型；**可执行性**由编译器按模型类型单独判定，
#: 因此 P2 的 score/rank/branch/merge 只能是合法的 Schema 节点而非可运行层级。
VALID_STAGE_KINDS = ("filter", "gate", "output", "score", "rank", "branch", "merge")
VALID_SCOPES = ("candidate_filter", "universe_gate", "scoring", "output_gate")
VALID_LOGIC = ("all", "any")
VALID_MISSING_DATA_POLICIES = ("reject", "wait", "skip_rule", "fail_stage")

#: 声明态参数块（与 stages 同级，冻结但尚未参与执行）。
DECLARED_BLOCK_KEYS = ("ranking", "risk_exit")
DECLARED_STATUS = "declared"
ROOT_INPUT_BINDING = "market.daily_universe"


class SelectionSchemaError(ValueError):
    """配置 Schema 校验失败；`code` 为稳定错误码，供 CLI/API 透出。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def detect_schema_version(definition: Mapping[str, Any]) -> int:
    """识别配置版本：`schema_version` 优先，其次回退到旧字段 `version`。"""
    if not isinstance(definition, Mapping):
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "模型定义必须是映射结构")
    if "schema_version" in definition:
        try:
            return int(definition["schema_version"])
        except (TypeError, ValueError) as exc:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "schema_version 必须是整数") from exc
    if "version" in definition:
        try:
            return int(definition["version"])
        except (TypeError, ValueError) as exc:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "version 必须是整数") from exc
    raise SelectionSchemaError("MODEL_CONFIG_INVALID", "模型定义缺少 schema_version/version")


def migrate_to_v2(definition: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """把任意受支持的配置版本迁移为 v2 结构；幂等，返回 `(定义, 告警列表)`。"""
    version = detect_schema_version(definition)
    if version == SCHEMA_VERSION:
        return normalize_definition(definition), []
    if version != LEGACY_SCHEMA_VERSION:
        raise SelectionSchemaError(
            "MODEL_CONFIG_INVALID", f"不支持的配置版本: {version}"
        )
    migrated, warnings = _migrate_v1(definition)
    return normalize_definition(migrated), warnings


def _migrate_v1(definition: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    strategy = definition.get("strategy") or {}
    if not isinstance(strategy, Mapping):
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "v1 strategy 必须是映射结构")
    model_id = str(strategy.get("id") or "").strip()
    if not model_id:
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "v1 strategy 缺少 id")

    warnings = [
        f"配置为 v1 Schema（version: 1），已在内存中迁移为 v2（schema_version: 2），"
        f"原文件未被改写（T-06）。model_id={model_id}",
        "字段重映射：strategy → model；version:1 → schema_version:2（S-01）。",
    ]

    migrated: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model": {
            "id": model_id,
            "name": str(strategy.get("name") or model_id),
            "model_type": str(definition.get("model_type") or DEFAULT_MODEL_TYPE),
            "version": int(strategy.get("version", 1) or 1),
            "enabled": bool(strategy.get("enabled", True)),
            "timezone": str(strategy.get("timezone") or DEFAULT_TIMEZONE),
            "exchange_calendar": str(strategy.get("exchange_calendar") or DEFAULT_EXCHANGE_CALENDAR),
            "description": strategy.get("description"),
        },
        "data_requirements": list(definition.get("data_requirements") or []),
        "stages": _migrate_v1_stages(definition.get("stages") or []),
    }
    notes = strategy.get("notes")
    if notes:
        migrated["notes"] = list(notes)
    declared = {
        key: definition[key]
        for key in DECLARED_BLOCK_KEYS
        if isinstance(definition.get(key), Mapping)
    }
    if declared:
        migrated["declared_blocks"] = declared
    return migrated, warnings


def _migrate_v1_stages(stages: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    migrated: List[Dict[str, Any]] = []
    previous_id: Optional[str] = None
    for index, stage in enumerate(stages):
        if not isinstance(stage, Mapping):
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "v1 stage 必须是映射结构")
        stage_id = str(stage.get("id") or "").strip()
        if not stage_id:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "v1 stage 缺少 id")
        scope = str(stage.get("scope", "candidate_filter"))
        item: Dict[str, Any] = {
            "id": stage_id,
            "name": stage.get("name"),
            "enabled": bool(stage.get("enabled", True)),
            "order": int(stage.get("order", (index + 1) * 10)),
            "scope": scope,
            "kind": str(stage.get("kind") or SCOPE_TO_KIND.get(scope, "filter")),
            "logic": str(stage.get("logic", "all")),
            # 保持 v1 紧凑时间窗形态（`HH:MM-HH:MM`）；结构化触发器在编译期由编译器接管。
            "schedule": stage.get("schedule"),
            "input_binding": str(
                stage.get("input_binding")
                or (f"{previous_id}.candidates" if previous_id else ROOT_INPUT_BINDING)
            ),
            "missing_data_policy": str(
                stage.get("missing_data_policy", DEFAULT_MISSING_DATA_POLICY)
            ),
            "rules": [dict(rule) for rule in (stage.get("rules") or [])],
        }
        if stage.get("expression") is not None:
            item["expression"] = stage["expression"]
        migrated.append(item)
        previous_id = stage_id
    return migrated


def normalize_definition(definition: Mapping[str, Any]) -> Dict[str, Any]:
    """校验并返回规范化的 v2 定义（确定性字段、层级按 `order` 排序）。"""
    if not isinstance(definition, Mapping):
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "模型定义必须是映射结构")
    if int(definition.get("schema_version", 0)) != SCHEMA_VERSION:
        raise SelectionSchemaError(
            "MODEL_CONFIG_INVALID",
            f"normalize_definition 只接受 schema_version={SCHEMA_VERSION} 的定义",
        )
    model = definition.get("model")
    if not isinstance(model, Mapping):
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "v2 定义缺少 model 块")
    model_id = str(model.get("id") or "").strip()
    if not model_id:
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "model.id 不能为空")
    model_type = str(model.get("model_type") or "").strip()
    if not model_type:
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "model.model_type 不能为空")

    normalized_model = {
        "id": model_id,
        "name": str(model.get("name") or model_id),
        "model_type": model_type,
        "version": int(model.get("version", 1) or 1),
        "enabled": bool(model.get("enabled", True)),
        "timezone": str(model.get("timezone") or DEFAULT_TIMEZONE),
        "exchange_calendar": str(model.get("exchange_calendar") or DEFAULT_EXCHANGE_CALENDAR),
        "description": model.get("description"),
    }

    result: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model": normalized_model,
        "data_requirements": _normalize_data_requirements(definition.get("data_requirements")),
    }
    # 两类 P0 结构：漏斗模型用有序 stages；条件模型用维度组 + 根表达式树（SSOT-MT §3.4）。
    if "groups" in definition or model_type == CONDITION_TREE_TYPE:
        result["groups"] = _normalize_groups(definition.get("groups"))
        root_expression = definition.get("expression")
        if not isinstance(root_expression, Mapping):
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "条件模型需要根 expression 表达式树")
        result["expression"] = dict(root_expression)
    else:
        stages = definition.get("stages")
        if not isinstance(stages, list) or not stages:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "v2 定义需要非空 stages 列表")
        result["stages"] = _normalize_stages(stages)
    notes = definition.get("notes")
    if notes:
        result["notes"] = [str(item) for item in notes]
    declared = _normalize_declared_blocks(definition.get("declared_blocks"))
    if declared:
        result["declared_blocks"] = declared
    return result


def _normalize_data_requirements(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "data_requirements 必须是列表")
    requirements: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "data_requirements 条目必须是映射结构")
        requirements.append(dict(item))
    return requirements


def _normalize_declared_blocks(value: Any) -> Dict[str, Dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "declared_blocks 必须是映射结构")
    declared: Dict[str, Dict[str, Any]] = {}
    for key in DECLARED_BLOCK_KEYS:
        block = value.get(key)
        if block is None:
            continue
        if not isinstance(block, Mapping):
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", f"声明块 {key} 必须是映射结构")
        if block.get("status") != DECLARED_STATUS:
            raise SelectionSchemaError(
                "MODEL_CONFIG_INVALID",
                f"声明块 {key}: status 必须为 {DECLARED_STATUS!r}，实际 {block.get('status')!r}",
            )
        declared[key] = dict(block)
    return declared


def _normalize_stages(stages: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    seen: set = set()
    for index, stage in enumerate(stages):
        if not isinstance(stage, Mapping):
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "stage 必须是映射结构")
        stage_id = str(stage.get("id") or "").strip()
        if not stage_id:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "stage.id 不能为空")
        if stage_id in seen:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", f"stage.id 重复: {stage_id}")
        seen.add(stage_id)
        scope = str(stage.get("scope", "candidate_filter"))
        if scope not in VALID_SCOPES:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", f"stage {stage_id}: 非法 scope {scope}")
        kind = str(stage.get("kind") or SCOPE_TO_KIND.get(scope, "filter"))
        if kind not in VALID_STAGE_KINDS:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", f"stage {stage_id}: 非法 kind {kind}")
        logic = str(stage.get("logic", "all"))
        if logic not in VALID_LOGIC:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", f"stage {stage_id}: logic 必须为 all/any")
        policy = str(stage.get("missing_data_policy", DEFAULT_MISSING_DATA_POLICY))
        if policy not in VALID_MISSING_DATA_POLICIES:
            raise SelectionSchemaError(
                "MODEL_CONFIG_INVALID", f"stage {stage_id}: 非法 missing_data_policy {policy}"
            )
        rules = stage.get("rules")
        if rules is None:
            rules = []
        if not isinstance(rules, list):
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", f"stage {stage_id}: rules 必须是列表")
        item: Dict[str, Any] = {
            "id": stage_id,
            "name": str(stage.get("name") or stage_id),
            "enabled": bool(stage.get("enabled", True)),
            "order": int(stage.get("order", (index + 1) * 10)),
            "scope": scope,
            "kind": kind,
            "logic": logic,
            "schedule": stage.get("schedule"),
            "input_binding": str(stage.get("input_binding") or ROOT_INPUT_BINDING),
            "missing_data_policy": policy,
            "rules": [dict(rule) for rule in rules],
        }
        if stage.get("expression") is not None:
            item["expression"] = stage["expression"]
        normalized.append(item)
    normalized.sort(key=lambda item: (item["order"],))
    return normalized


def _normalize_groups(groups: Any) -> List[Dict[str, Any]]:
    """校验并归一化条件模型的维度组（SSOT-MT §3.4）。"""
    if not isinstance(groups, list) or not groups:
        raise SelectionSchemaError("MODEL_CONFIG_INVALID", "条件模型需要非空 groups 列表")
    normalized: List[Dict[str, Any]] = []
    seen: set = set()
    for group in groups:
        if not isinstance(group, Mapping):
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "维度组必须是映射结构")
        group_id = str(group.get("id") or "").strip()
        if not group_id or group_id in seen:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", "维度组 id 必须唯一且非空")
        seen.add(group_id)
        logic = str(group.get("logic", "all"))
        if logic not in VALID_LOGIC:
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", f"维度组 {group_id}: logic 必须为 all/any")
        rules = group.get("rules")
        if rules is None:
            rules = []
        if not isinstance(rules, list):
            raise SelectionSchemaError("MODEL_CONFIG_INVALID", f"维度组 {group_id}: rules 必须是列表")
        item: Dict[str, Any] = {
            "id": group_id,
            "name": str(group.get("name") or group_id),
            "logic": logic,
            "rules": [dict(rule) for rule in rules],
        }
        if group.get("expression") is not None:
            item["expression"] = group["expression"]
        normalized.append(item)
    return normalized


def load_definition(path: Path) -> Tuple[Dict[str, Any], List[str]]:
    """读取 YAML/JSON 定义文件并迁移为 v2；返回 `(定义, 告警列表)`。"""
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return migrate_to_v2(data)


def load_definition_dict(definition: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """对已在内存中的定义执行迁移与归一化。"""
    return migrate_to_v2(definition)


__all__ = [
    "CONDITION_TREE_TYPE",
    "DEFAULT_EXCHANGE_CALENDAR",
    "DEFAULT_MODEL_TYPE",
    "DEFAULT_MISSING_DATA_POLICY",
    "DEFAULT_TIMEZONE",
    "DECLARED_BLOCK_KEYS",
    "LEGACY_SCHEMA_VERSION",
    "ROOT_INPUT_BINDING",
    "SCHEMA_VERSION",
    "SCOPE_TO_KIND",
    "VALID_MISSING_DATA_POLICIES",
    "VALID_SCOPES",
    "VALID_STAGE_KINDS",
    "SelectionSchemaError",
    "detect_schema_version",
    "load_definition",
    "load_definition_dict",
    "migrate_to_v2",
    "normalize_definition",
]