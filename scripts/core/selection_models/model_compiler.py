# -*- coding: utf-8 -*-
"""模型编译器：把用户模型统一编译为 `CompiledSelectionPlan`（A4 / SSOT §7.2）。

编译契约（§7.2）：

1. 相同模型版本 + 相同编译器版本必须生成相同 `plan_hash`；
2. 条件模型的维度组被展开为层内表达式节点；漏斗模型的层级按 `order` 编译为多个 stage；
3. `all/any` 只是 `and/or` 的编辑器快捷写法，运行时统一使用表达式 AST；
4. 任何无法解析的规则、数据集、触发器或节点类型都必须在**发布阶段失败**，
   不得延迟到正式运行时猜测处理（首期层级类型仅 `filter`/`gate`/`output` 可执行）。

编译器只做结构转换与静态检查，不读取行情、不产生选股结果（§6.1）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.selection_models import schemas
from core.selection_models.hash import plan_hash as compute_plan_hash
from core.selection_models.model_type_registry import (
    ModelTypeError,
    SelectionModelTypeRegistry,
    build_default_type_registry,
)
from core.selection_models.rule_registry import (
    RuleMetadataError,
    RuleMetadataRegistry,
    build_default_rule_registry,
)
from core.strategy.funnel_engine import (
    LOGIC_TO_EXPR_OP,
    expression_refs,
    validate_expression,
)

#: 编译器版本：编译器逻辑变更时手工递增；参与 `plan_hash`（S-02）。
COMPILER_VERSION = "1"
PLAN_SCHEMA_VERSION = 1
ENGINE_NAME = "hierarchical_funnel"
CONDITION_STAGE_ID = "condition_filter"


class ModelCompilerError(ValueError):
    """编译失败；`code` 为稳定错误码，供 CLI/API 透出。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CompiledStage:
    id: str
    name: str
    kind: str
    order: int
    scope: str
    input: str
    expression: Dict[str, Any]
    rules: Tuple[Dict[str, Any], ...]
    missing_data_policy: str
    trigger: Any = None
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "order": self.order,
            "scope": self.scope,
            "input": self.input,
            "trigger": self.trigger,
            "expression": self.expression,
            "rules": [dict(rule) for rule in self.rules],
            "missing_data_policy": self.missing_data_policy,
            "enabled": self.enabled,
        }

    def to_engine_stage(self) -> Dict[str, Any]:
        """转换为层级漏斗引擎可执行的 stage 映射。"""
        stage: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "scope": self.scope,
            "rules": [dict(rule) for rule in self.rules],
            "expression": self.expression,
        }
        if self.scope == "universe_gate":
            stage["logic"] = "all"
        return stage


@dataclass(frozen=True)
class CompiledSelectionPlan:
    plan_schema_version: int
    engine: str
    compiler_version: str
    source_model: Dict[str, Any]
    data_contract: Tuple[Dict[str, Any], ...]
    stages: Tuple[CompiledStage, ...]
    plan_hash: str = ""
    declared_blocks: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def payload(self) -> Dict[str, Any]:
        """不含 `plan_hash` 的规范化计划载荷（`plan_hash` 的哈希输入）。"""
        return {
            "plan_schema_version": self.plan_schema_version,
            "engine": self.engine,
            "compiler_version": self.compiler_version,
            "source_model": dict(self.source_model),
            "data_contract": [dict(item) for item in self.data_contract],
            "stages": [stage.to_dict() for stage in self.stages],
            "declared_blocks": [dict(item) for item in self.declared_blocks],
        }

    def to_dict(self) -> Dict[str, Any]:
        payload = self.payload()
        payload["plan_hash"] = self.plan_hash
        return payload

    def to_engine_stages(self) -> List[Dict[str, Any]]:
        return [stage.to_engine_stage() for stage in self.stages]


def compile_definition(
    definition: Mapping[str, Any],
    *,
    type_registry: Optional[SelectionModelTypeRegistry] = None,
    rule_registry: Optional[RuleMetadataRegistry] = None,
) -> CompiledSelectionPlan:
    """把 v2 模型定义编译为不可变 `CompiledSelectionPlan`。"""
    types = type_registry or build_default_type_registry()
    rules_meta = rule_registry or build_default_rule_registry()
    normalized = schemas.normalize_definition(definition)
    model = normalized["model"]
    model_type = model["model_type"]
    try:
        capability = types.require_publishable(model_type)
    except ModelTypeError as exc:
        raise ModelCompilerError(exc.code, str(exc)) from exc

    if model_type == "funnel":
        stages = _compile_funnel_stages(normalized, capability.supported_node_kinds, rules_meta)
    elif model_type == "condition_tree":
        stages = _compile_condition_tree_stages(normalized, capability.supported_node_kinds, rules_meta)
    else:  # pragma: no cover - 注册中心已限定可发布类型
        raise ModelCompilerError("MODEL_TYPE_UNKNOWN", f"暂不支持编译模型类型 {model_type}")

    plan = CompiledSelectionPlan(
        plan_schema_version=PLAN_SCHEMA_VERSION,
        engine=ENGINE_NAME,
        compiler_version=COMPILER_VERSION,
        source_model={
            "model_id": model["id"],
            "model_type": model_type,
            "model_version": int(model["version"]),
        },
        data_contract=tuple(dict(item) for item in normalized.get("data_requirements", [])),
        stages=tuple(stages),
        declared_blocks=tuple(
            {"block": key, **dict(value)} for key, value in normalized.get("declared_blocks", {}).items()
        ),
    )
    return CompiledSelectionPlan(
        plan_schema_version=plan.plan_schema_version,
        engine=plan.engine,
        compiler_version=plan.compiler_version,
        source_model=plan.source_model,
        data_contract=plan.data_contract,
        stages=plan.stages,
        plan_hash=compute_plan_hash(plan.payload()),
        declared_blocks=plan.declared_blocks,
    )


def _validate_rule(spec: Mapping[str, Any], rule_registry: RuleMetadataRegistry) -> Dict[str, Any]:
    type_id = str(spec.get("type") or "")
    try:
        rule_registry.validate_rule_spec(spec)
    except RuleMetadataError as exc:
        code = "MODEL_RULE_UNKNOWN" if "未知规则类型" in str(exc) else "MODEL_CONFIG_INVALID"
        raise ModelCompilerError(code, f"规则 {spec.get('id') or type_id}: {exc}") from exc
    compiled = dict(spec)
    # 规则计算口径版本参与 plan_hash（§7.4）：仅参数变化不递增，口径变化必递增。
    compiled["version"] = rule_registry.rule_version(type_id)
    return compiled


def _compile_funnel_stages(
    definition: Mapping[str, Any],
    supported_kinds: Sequence[str],
    rule_registry: RuleMetadataRegistry,
) -> List[CompiledStage]:
    stages: List[CompiledStage] = []
    previous_id: Optional[str] = None
    for index, stage in enumerate(definition["stages"]):
        kind = str(stage.get("kind") or "filter")
        if kind not in supported_kinds:
            raise ModelCompilerError(
                "MODEL_CONFIG_INVALID",
                f"stage {stage['id']}: 层级类型 {kind!r} 在首期不可执行（允许 {list(supported_kinds)}）",
            )
        rules = tuple(_validate_rule(rule, rule_registry) for rule in stage.get("rules") or [])
        enabled_ids = [str(rule["id"]) for rule in rules if rule.get("enabled", True)]
        expression = _build_expression(stage, enabled_ids)
        binding = stage.get("input_binding")
        if index > 0 and (not binding or binding == schemas.ROOT_INPUT_BINDING):
            binding = f"{previous_id}.candidates"
        if not binding:
            binding = schemas.ROOT_INPUT_BINDING
        compiled = CompiledStage(
            id=str(stage["id"]),
            name=str(stage.get("name") or stage["id"]),
            kind=kind,
            order=int(stage.get("order", (index + 1) * 10)),
            scope=str(stage.get("scope", "candidate_filter")),
            input=str(binding),
            expression=expression,
            rules=rules,
            missing_data_policy=str(stage.get("missing_data_policy", schemas.DEFAULT_MISSING_DATA_POLICY)),
            trigger=stage.get("schedule"),
            enabled=bool(stage.get("enabled", True)),
        )
        stages.append(compiled)
        previous_id = compiled.id
    return stages


def _compile_condition_tree_stages(
    definition: Mapping[str, Any],
    supported_kinds: Sequence[str],
    rule_registry: RuleMetadataRegistry,
) -> List[CompiledStage]:
    if "filter" not in supported_kinds:
        raise ModelCompilerError("MODEL_CONFIG_INVALID", "condition_tree 首期需要 filter 层级")
    groups = definition.get("groups")
    root_expression = definition.get("expression")
    if not isinstance(groups, list) or not groups:
        raise ModelCompilerError("MODEL_CONFIG_INVALID", "condition_tree 需要非空 groups 列表")
    if root_expression is None:
        raise ModelCompilerError("MODEL_CONFIG_INVALID", "condition_tree 需要根 expression")

    group_by_id: Dict[str, Mapping[str, Any]] = {}
    rules: List[Dict[str, Any]] = []
    seen_rule_ids: set = set()
    for group in groups:
        group_id = str(group.get("id") or "").strip()
        if not group_id or group_id in group_by_id:
            raise ModelCompilerError("MODEL_CONFIG_INVALID", "condition_tree group.id 必须唯一且非空")
        group_by_id[group_id] = group
        for rule in group.get("rules") or []:
            rule_id = str(rule.get("id") or "").strip()
            if not rule_id or rule_id in seen_rule_ids:
                raise ModelCompilerError(
                    "MODEL_CONFIG_INVALID", f"condition_tree 规则 ID 必须跨组唯一: {rule_id!r}"
                )
            seen_rule_ids.add(rule_id)
            rules.append(_validate_rule(rule, rule_registry))

    group_expressions = {group_id: _group_expression(group) for group_id, group in group_by_id.items()}
    _assert_acyclic(group_by_id, group_expressions)
    expanded = _expand_groups(root_expression, group_expressions, set())
    validate_expression(expanded)
    _assert_expression_refs_known(expanded, seen_rule_ids)

    stage = CompiledStage(
        id=CONDITION_STAGE_ID,
        name=str(definition["model"].get("name") or CONDITION_STAGE_ID),
        kind="filter",
        order=10,
        scope="candidate_filter",
        input=schemas.ROOT_INPUT_BINDING,
        expression=expanded,
        rules=tuple(rules),
        missing_data_policy=schemas.DEFAULT_MISSING_DATA_POLICY,
        trigger=None,
        enabled=True,
    )
    return [stage]


def _build_expression(stage: Mapping[str, Any], enabled_rule_ids: Sequence[str]) -> Dict[str, Any]:
    provided = stage.get("expression")
    if provided is not None:
        return validate_expression(provided)
    if not enabled_rule_ids:
        raise ModelCompilerError("MODEL_CONFIG_INVALID", f"stage {stage.get('id')}: 至少需要一条启用规则")
    op = LOGIC_TO_EXPR_OP[str(stage.get("logic", "all"))]
    children = [{"ref": rule_id} for rule_id in enabled_rule_ids]
    if len(children) == 1:
        return children[0]
    return {"op": op, "children": children}


def _group_expression(group: Mapping[str, Any]) -> Dict[str, Any]:
    provided = group.get("expression")
    if provided is not None:
        return validate_expression(provided)
    rule_ids = [str(rule["id"]) for rule in group.get("rules") or [] if rule.get("enabled", True)]
    if not rule_ids:
        raise ModelCompilerError("MODEL_CONFIG_INVALID", f"维度组 {group.get('id')}: 至少需要一条启用规则")
    op = LOGIC_TO_EXPR_OP[str(group.get("logic", "all"))]
    children = [{"ref": rule_id} for rule_id in rule_ids]
    if len(children) == 1:
        return children[0]
    return {"op": op, "children": children}


def _expand_groups(
    expression: Mapping[str, Any],
    group_expressions: Mapping[str, Dict[str, Any]],
    visiting: set,
) -> Dict[str, Any]:
    """把根表达式中的 `{ref: group_id}` 叶子展开为对应维度组表达式（可嵌套引用）。"""
    node = validate_expression(expression) if "op" in expression else _leaf(expression)
    if "op" not in node:
        if "ref" in node and node["ref"] in group_expressions:
            group_id = node["ref"]
            if group_id in visiting:
                raise ModelCompilerError("MODEL_CONFIG_INVALID", f"维度组存在循环引用: {group_id}")
            return _expand_groups(
                group_expressions[group_id], group_expressions, visiting | {group_id}
            )
        return node
    if node["op"] == "not":
        return {"op": "not", "child": _expand_groups(node["child"], group_expressions, visiting)}
    return {
        "op": node["op"],
        "children": [_expand_groups(child, group_expressions, visiting) for child in node["children"]],
    }


def _leaf(expression: Mapping[str, Any]) -> Dict[str, Any]:
    from core.strategy.funnel_engine import normalize_expression

    return normalize_expression(expression)


def _assert_acyclic(
    group_by_id: Mapping[str, Mapping[str, Any]],
    group_expressions: Mapping[str, Dict[str, Any]],
) -> None:
    def refs_of(group_id: str) -> set:
        return {
            ref
            for ref in expression_refs(group_expressions[group_id])
            if ref in group_by_id
        }

    order: Dict[str, int] = {}
    on_stack: set = set()

    def visit(group_id: str) -> None:
        state = order.get(group_id, 0)
        if state == 1:
            raise ModelCompilerError("MODEL_CONFIG_INVALID", f"维度组存在循环引用: {group_id}")
        if state == 2:
            return
        order[group_id] = 1
        on_stack.add(group_id)
        for ref in refs_of(group_id):
            visit(ref)
        on_stack.discard(group_id)
        order[group_id] = 2

    for group_id in group_by_id:
        visit(group_id)


def _assert_expression_refs_known(expression: Mapping[str, Any], known_rule_ids: set) -> None:
    unknown = sorted(ref for ref in expression_refs(expression) if ref not in known_rule_ids)
    if unknown:
        raise ModelCompilerError("MODEL_CONFIG_INVALID", f"表达式引用了未声明的规则: {unknown}")


__all__ = [
    "COMPILER_VERSION",
    "CONDITION_STAGE_ID",
    "ENGINE_NAME",
    "PLAN_SCHEMA_VERSION",
    "CompiledSelectionPlan",
    "CompiledStage",
    "ModelCompilerError",
    "compile_definition",
]