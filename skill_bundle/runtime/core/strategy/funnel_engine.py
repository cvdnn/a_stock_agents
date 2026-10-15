# -*- coding: utf-8 -*-
"""Config-driven, domain-neutral funnel execution primitives.

The engine deliberately contains no market-data access.  A stage consumes a
list of records plus an optional context dictionary and returns an auditable
result.  Business rules are supplied through a registry, so stages and rules
can be reordered or replaced from YAML without changing orchestration code.

层内判定使用受限 AST（§7.2/§7.7）：`and` / `or` / `not` 组合三态叶子，
`all` / `any` 只是编辑器快捷写法（编译期归一为同一 AST）。Kleene 强三值
真值表见 §7.7.4，`NOT UNKNOWN = UNKNOWN`，不回绕为 PASS（S-04）。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Set, Tuple

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_UNKNOWN = "UNKNOWN"
VALID_VERDICTS = (VERDICT_PASS, VERDICT_FAIL, VERDICT_UNKNOWN)

REASON_RULE_INPUT_MISSING = "RULE_INPUT_MISSING"

#: 层内表达式的受限算子白名单（S-04）：只允许 AND/OR/NOT，禁止任意表达式求值。
EXPR_OP_AND = "and"
EXPR_OP_OR = "or"
EXPR_OP_NOT = "not"
VALID_EXPR_OPS = (EXPR_OP_AND, EXPR_OP_OR, EXPR_OP_NOT)
#: `all`/`any` 是 `and`/`or` 的编辑器快捷写法（§7.2 编译契约第4条）。
LOGIC_TO_EXPR_OP = {"all": EXPR_OP_AND, "any": EXPR_OP_OR}

#: 嵌套深度与叶子总数上限（S-05 / T-01）：超限在编译期报错，不得延迟到运行期。
MAX_EXPRESSION_DEPTH = 3
MAX_EXPRESSION_LEAVES = 200


def kleene_all(verdicts: Iterable[str]) -> str:
    """Kleene 强三值 AND（§7.7.4）：FAIL 吸收，UNKNOWN 传播。"""
    result = VERDICT_PASS
    for verdict in verdicts:
        if verdict == VERDICT_FAIL:
            return VERDICT_FAIL
        if verdict == VERDICT_UNKNOWN:
            result = VERDICT_UNKNOWN
    return result


def kleene_any(verdicts: Iterable[str]) -> str:
    """Kleene 强三值 OR（§7.7.4）：PASS 吸收，UNKNOWN 不被 FAIL 拖垮。"""
    result = VERDICT_FAIL
    for verdict in verdicts:
        if verdict == VERDICT_PASS:
            return VERDICT_PASS
        if verdict == VERDICT_UNKNOWN:
            result = VERDICT_UNKNOWN
    return result


def kleene_not(verdict: str) -> str:
    """Kleene 强三值 NOT（§7.7.4 / S-04）：`NOT UNKNOWN = UNKNOWN`，不回绕为 PASS。"""
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"invalid verdict: {verdict}")
    if verdict == VERDICT_PASS:
        return VERDICT_FAIL
    if verdict == VERDICT_FAIL:
        return VERDICT_PASS
    return VERDICT_UNKNOWN


def normalize_expression(expression: Mapping[str, Any]) -> Dict[str, Any]:
    """校验并归一化层内表达式 AST，返回算子小写化的规范嵌套字典。

    节点形态（§7.2）：
    - 布尔节点：`{"op": "and"|"or", "children": [...]}`
    - 取反节点：`{"op": "not", "child": {...}}`（`children` 单元素写法亦接受）
    - 叶子谓词：`{"ref": "<rule_id>"}` 或 `{"rule": "<type>", "params": {...}, "id": ...}`

    任何未知算子或结构一律失败关闭，不得在运行期猜测处理（§7.2 第8条）。
    """
    if not isinstance(expression, Mapping):
        raise ValueError("表达式节点必须是映射结构")
    if "op" in expression:
        op = str(expression.get("op", "")).strip().lower()
        if op not in VALID_EXPR_OPS:
            raise ValueError(f"不支持的表达式算子: {expression.get('op')!r}")
        if op == EXPR_OP_NOT:
            if "child" in expression:
                child = expression["child"]
            elif isinstance(expression.get("children"), list) and len(expression["children"]) == 1:
                child = expression["children"][0]
            else:
                raise ValueError("NOT 节点必须且只能携带一个子节点")
            return {"op": EXPR_OP_NOT, "child": normalize_expression(child)}
        children = expression.get("children")
        if not isinstance(children, list) or not children:
            raise ValueError(f"{op} 节点必须携带非空 children 列表")
        return {"op": op, "children": [normalize_expression(item) for item in children]}
    if "ref" in expression:
        ref = expression.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("叶子引用 ref 必须是非空字符串")
        return {"ref": ref.strip()}
    if "rule" in expression:
        rule_type = expression.get("rule")
        if not isinstance(rule_type, str) or not rule_type.strip():
            raise ValueError("叶子 rule 必须是非空规则类型字符串")
        params = expression.get("params", {})
        if not isinstance(params, Mapping):
            raise ValueError("叶子 params 必须是映射结构")
        node: Dict[str, Any] = {"rule": rule_type.strip(), "params": dict(params)}
        leaf_id = expression.get("id")
        if leaf_id is not None:
            if not isinstance(leaf_id, str) or not leaf_id.strip():
                raise ValueError("叶子 id 必须是非空字符串")
            node["id"] = leaf_id.strip()
        return node
    raise ValueError(f"无法识别的表达式节点: {expression!r}")


def expression_depth(expression: Mapping[str, Any]) -> int:
    """表达式层数（含顶层）：布尔/取反节点计一层，叶子谓词不计层。"""
    node = normalize_expression(expression)
    if "op" not in node:
        return 0
    if node["op"] == EXPR_OP_NOT:
        return 1 + expression_depth(node["child"])
    return 1 + max((expression_depth(child) for child in node["children"]), default=0)


def expression_leaves(expression: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """按先序遍历返回全部叶子谓词节点。"""
    node = normalize_expression(expression)
    return list(_iter_leaves(node))


def _iter_leaves(node: Mapping[str, Any]) -> Iterator[Dict[str, Any]]:
    if "op" not in node:
        yield dict(node)
        return
    if node["op"] == EXPR_OP_NOT:
        yield from _iter_leaves(node["child"])
        return
    for child in node["children"]:
        yield from _iter_leaves(child)


def expression_refs(expression: Mapping[str, Any]) -> Set[str]:
    """表达式引用的 stage 规则 ID 集合（内联 `rule` 叶子不计入）。"""
    return {leaf["ref"] for leaf in expression_leaves(expression) if "ref" in leaf}


def validate_expression(expression: Mapping[str, Any]) -> Dict[str, Any]:
    """校验表达式深度（≤3）与叶子总数（≤200），返回归一化后的 AST。"""
    node = normalize_expression(expression)
    leaves = list(_iter_leaves(node))
    if not leaves:
        raise ValueError("表达式至少需要一个叶子谓词")
    if len(leaves) > MAX_EXPRESSION_LEAVES:
        raise ValueError(f"表达式叶子总数 {len(leaves)} 超过上限 {MAX_EXPRESSION_LEAVES}（S-05）")
    depth = expression_depth(node)
    if depth > MAX_EXPRESSION_DEPTH:
        raise ValueError(f"表达式嵌套深度 {depth} 超过上限 {MAX_EXPRESSION_DEPTH}（S-05）")
    return node


def evaluate_expression(
    expression: Mapping[str, Any],
    resolve_leaf: Callable[[Mapping[str, Any]], str],
) -> str:
    """以 Kleene 强三值求值受限 AST；叶子 verdict 由 `resolve_leaf` 提供。"""
    return _evaluate_node(normalize_expression(expression), resolve_leaf)


def _evaluate_node(node: Mapping[str, Any], resolve_leaf: Callable[[Mapping[str, Any]], str]) -> str:
    op = node.get("op")
    if op is None:
        verdict = resolve_leaf(node)
        if verdict not in VALID_VERDICTS:
            raise ValueError(f"叶子谓词返回非法 verdict: {verdict!r}")
        return verdict
    if op == EXPR_OP_NOT:
        return kleene_not(_evaluate_node(node["child"], resolve_leaf))
    verdicts = [_evaluate_node(child, resolve_leaf) for child in node["children"]]
    return kleene_all(verdicts) if op == EXPR_OP_AND else kleene_any(verdicts)


@dataclass
class RuleResult:
    """单条规则的求值结论。

    `verdict` 是一等判定字段（§7.7.2）；`passed` 仅为兼容投影
    （`passed == (verdict == "PASS")`，兼容期一个版本）；`reason_code`
    承载原因码，与 `passed` 一样不得反过来承担布尔语义。
    """

    rule_id: str
    verdict: str
    reason_code: str = ""
    reason: str = ""
    observed: Any = None
    expected: Any = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    field_status: Dict[str, str] = field(default_factory=dict)
    passed: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(f"invalid verdict: {self.verdict}")
        self.passed = self.verdict == VERDICT_PASS

    @classmethod
    def two_state(cls, rule_id: str, passed: bool, **kwargs: Any) -> "RuleResult":
        """由布尔条件构造结论：True → PASS，False → FAIL，永不产生 UNKNOWN。"""
        return cls(rule_id, VERDICT_PASS if passed else VERDICT_FAIL, **kwargs)


@dataclass
class CandidateResult:
    candidate: Dict[str, Any]
    passed: bool
    rule_results: List[RuleResult]


@dataclass
class StageResult:
    stage_id: str
    name: str
    scope: str
    status: str
    input_count: int
    output_count: int
    passed_records: List[Dict[str, Any]]
    rejected_records: List[Dict[str, Any]]
    gate_results: List[RuleResult] = field(default_factory=list)
    verdict: str = VERDICT_UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


RuleEvaluator = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], RuleResult]


class RuleRegistry:
    """Named rule evaluators used by configuration files."""

    def __init__(self) -> None:
        self._evaluators: Dict[str, RuleEvaluator] = {}

    def register(self, name: str, evaluator: RuleEvaluator) -> None:
        if not name or not callable(evaluator):
            raise ValueError("rule name and callable evaluator are required")
        self._evaluators[name] = evaluator

    def get(self, name: str) -> RuleEvaluator:
        try:
            return self._evaluators[name]
        except KeyError as exc:
            raise ValueError(f"unknown funnel rule type: {name}") from exc

    @property
    def names(self) -> List[str]:
        return sorted(self._evaluators)


@dataclass
class _StagePlan:
    """单阶段执行计划：表达式（或 `all/any` 快捷聚合）与可用规则索引。"""

    stage_id: str
    name: str
    scope: str
    logic: str
    enabled_rules: List[Mapping[str, Any]]
    specs_by_id: Dict[str, Mapping[str, Any]]
    expression: Optional[Dict[str, Any]]


class FunnelEngine:
    """Execute one configured stage while preserving rejection evidence."""

    VALID_SCOPES = {"candidate_filter", "universe_gate"}

    def __init__(self, registry: RuleRegistry) -> None:
        self.registry = registry

    def validate_stage(self, stage: Mapping[str, Any]) -> None:
        stage_id = str(stage.get("id", "")).strip()
        if not stage_id:
            raise ValueError("every funnel stage requires a non-empty id")
        scope = stage.get("scope", "candidate_filter")
        if scope not in self.VALID_SCOPES:
            raise ValueError(f"stage {stage_id}: unsupported scope {scope}")
        if stage.get("logic", "all") not in LOGIC_TO_EXPR_OP:
            raise ValueError(f"stage {stage_id}: logic must be all or any")
        rules = stage.get("rules")
        if rules is None:
            rules = []
        if not isinstance(rules, list):
            raise ValueError(f"stage {stage_id}: rules must be a list")
        seen: Set[str] = set()
        specs_by_id: Dict[str, Mapping[str, Any]] = {}
        for rule in rules:
            rule_id = str(rule.get("id", "")).strip()
            if not rule_id or rule_id in seen:
                raise ValueError(f"stage {stage_id}: rule ids must be non-empty and unique")
            seen.add(rule_id)
            specs_by_id[rule_id] = rule
            self.registry.get(str(rule.get("type", "")))
        expression = stage.get("expression")
        if expression is None:
            if not rules:
                raise ValueError(f"stage {stage_id}: at least one rule is required")
            return
        node = validate_expression(expression)
        for leaf in _iter_leaves(node):
            if "ref" in leaf:
                ref = leaf["ref"]
                if ref not in specs_by_id:
                    raise ValueError(f"stage {stage_id}: 表达式引用了未声明的规则 {ref}")
                if not specs_by_id[ref].get("enabled", True):
                    raise ValueError(f"stage {stage_id}: 表达式引用了已停用规则 {ref}")
            else:
                self.registry.get(str(leaf["rule"]))

    def _prepare(self, stage: Mapping[str, Any]) -> _StagePlan:
        rules = list(stage.get("rules") or [])
        enabled = [rule for rule in rules if rule.get("enabled", True)]
        # 表达式与 `all/any` 快捷写法归一为同一 AST：`all` → and，`any` → or（§7.2 第4条）。
        expression = stage.get("expression")
        node = validate_expression(expression) if expression is not None else None
        return _StagePlan(
            stage_id=str(stage["id"]),
            name=str(stage.get("name") or stage["id"]),
            scope=str(stage.get("scope", "candidate_filter")),
            logic=str(stage.get("logic", "all")),
            enabled_rules=enabled,
            specs_by_id={str(rule["id"]): rule for rule in rules},
            expression=node,
        )

    def run_stage(
        self,
        stage: Mapping[str, Any],
        records: Iterable[Mapping[str, Any]],
        context: Optional[Mapping[str, Any]] = None,
    ) -> StageResult:
        self.validate_stage(stage)
        plan = self._prepare(stage)
        input_records = [dict(item) for item in records]
        ctx: Mapping[str, Any] = context or {}
        stage_id = plan.stage_id
        name = plan.name
        scope = plan.scope

        def verdict_for(record: Mapping[str, Any]) -> Tuple[List[RuleResult], str]:
            if plan.expression is None:
                outcomes = [self._evaluate(rule, record, ctx) for rule in plan.enabled_rules]
                verdicts = [item.verdict for item in outcomes]
                return outcomes, (kleene_all(verdicts) if plan.logic == "all" else kleene_any(verdicts))
            outcomes: List[RuleResult] = []

            def resolve_leaf(leaf: Mapping[str, Any]) -> str:
                result = self._evaluate(self._leaf_spec(plan, leaf), record, ctx)
                outcomes.append(result)
                return result.verdict

            return outcomes, evaluate_expression(plan.expression, resolve_leaf)

        def reject_evidence(candidate: Mapping[str, Any], outcomes: List[RuleResult], verdict: str) -> Dict[str, Any]:
            # 只有 FAIL 才是淘汰结论；UNKNOWN 单独留痕，审计不得用布尔字段反推 UNKNOWN（§7.7.2）。
            return {
                "candidate": candidate,
                "candidate_verdict": verdict,
                "failed_rules": [asdict(item) for item in outcomes if item.verdict == VERDICT_FAIL],
                "unknown_rules": [asdict(item) for item in outcomes if item.verdict == VERDICT_UNKNOWN],
            }

        if plan.expression is None and not plan.enabled_rules:
            return StageResult(
                stage_id=stage_id,
                name=name,
                scope=scope,
                status="SKIPPED",
                input_count=len(input_records),
                output_count=len(input_records),
                passed_records=input_records,
                rejected_records=[],
                verdict=VERDICT_PASS,
            )

        if scope == "universe_gate":
            outcomes, verdict = verdict_for(ctx)
            passed = verdict == VERDICT_PASS
            rejected = [] if passed else [
                reject_evidence(item, outcomes, verdict) for item in input_records
            ]
            return StageResult(
                stage_id=stage_id,
                name=name,
                scope=scope,
                status="PASSED" if passed else "BLOCKED",
                input_count=len(input_records),
                output_count=len(input_records) if passed else 0,
                passed_records=input_records if passed else [],
                rejected_records=rejected,
                gate_results=outcomes,
                verdict=verdict,
            )

        passed_records: List[Dict[str, Any]] = []
        rejected_records: List[Dict[str, Any]] = []
        rejected_verdicts: List[str] = []
        for candidate in input_records:
            outcomes, verdict = verdict_for(candidate)
            if verdict == VERDICT_PASS:
                enriched = dict(candidate)
                history = list(enriched.get("_funnel_history", []))
                if enriched.get("_funnel"):
                    history.append(enriched["_funnel"])
                current_audit = {
                    "stage": stage_id,
                    "verdict": verdict,
                    "rules": [asdict(item) for item in outcomes],
                }
                enriched["_funnel"] = current_audit
                enriched["_funnel_history"] = history
                passed_records.append(enriched)
            else:
                rejected_verdicts.append(verdict)
                rejected_records.append(reject_evidence(candidate, outcomes, verdict))

        if not input_records:
            status, verdict = "EMPTY", VERDICT_UNKNOWN
        elif passed_records:
            status, verdict = "PASSED", VERDICT_PASS
        else:
            status, verdict = "NO_MATCH", kleene_any(rejected_verdicts)
        return StageResult(
            stage_id=stage_id,
            name=name,
            scope=scope,
            status=status,
            input_count=len(input_records),
            output_count=len(passed_records),
            passed_records=passed_records,
            rejected_records=rejected_records,
            verdict=verdict,
        )

    @staticmethod
    def _leaf_spec(plan: _StagePlan, leaf: Mapping[str, Any]) -> Mapping[str, Any]:
        if "ref" in leaf:
            return plan.specs_by_id[leaf["ref"]]
        spec: Dict[str, Any] = {"type": leaf["rule"], **dict(leaf.get("params") or {})}
        spec["id"] = str(leaf.get("id") or leaf["rule"])
        return spec

    def _evaluate(
        self,
        rule: Mapping[str, Any],
        record: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> RuleResult:
        evaluator = self.registry.get(str(rule["type"]))
        try:
            result = evaluator(record, rule, context)
        except (KeyError, TypeError, ValueError) as exc:
            # 数据不足不得隐性判为淘汰（§7.7.7），一律返回 UNKNOWN 由聚合点按策略处置。
            return RuleResult(
                rule_id=str(rule["id"]),
                verdict=VERDICT_UNKNOWN,
                reason_code=REASON_RULE_INPUT_MISSING,
                reason=f"规则输入不足: {exc}",
                field_status={"rule_input": "missing"},
            )
        result.rule_id = str(rule["id"])
        return result