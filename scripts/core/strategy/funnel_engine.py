# -*- coding: utf-8 -*-
"""Config-driven, domain-neutral funnel execution primitives.

The engine deliberately contains no market-data access.  A stage consumes a
list of records plus an optional context dictionary and returns an auditable
result.  Business rules are supplied through a registry, so stages and rules
can be reordered or replaced from YAML without changing orchestration code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_UNKNOWN = "UNKNOWN"
VALID_VERDICTS = (VERDICT_PASS, VERDICT_FAIL, VERDICT_UNKNOWN)

REASON_RULE_INPUT_MISSING = "RULE_INPUT_MISSING"


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
        if stage.get("logic", "all") not in {"all", "any"}:
            raise ValueError(f"stage {stage_id}: logic must be all or any")
        rules = stage.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ValueError(f"stage {stage_id}: at least one rule is required")
        seen = set()
        for rule in rules:
            rule_id = str(rule.get("id", "")).strip()
            if not rule_id or rule_id in seen:
                raise ValueError(f"stage {stage_id}: rule ids must be non-empty and unique")
            seen.add(rule_id)
            self.registry.get(str(rule.get("type", "")))

    def run_stage(
        self,
        stage: Mapping[str, Any],
        records: Iterable[Mapping[str, Any]],
        context: Optional[Mapping[str, Any]] = None,
    ) -> StageResult:
        self.validate_stage(stage)
        input_records = [dict(item) for item in records]
        ctx: Mapping[str, Any] = context or {}
        stage_id = str(stage["id"])
        name = str(stage.get("name") or stage_id)
        scope = str(stage.get("scope", "candidate_filter"))
        logic = str(stage.get("logic", "all"))
        enabled_rules = [r for r in stage["rules"] if r.get("enabled", True)]

        def aggregate(outcomes: List[RuleResult]) -> str:
            verdicts = [item.verdict for item in outcomes]
            return kleene_all(verdicts) if logic == "all" else kleene_any(verdicts)

        def reject_evidence(candidate: Mapping[str, Any], outcomes: List[RuleResult], verdict: str) -> Dict[str, Any]:
            # 只有 FAIL 才是淘汰结论；UNKNOWN 单独留痕，审计不得用布尔字段反推 UNKNOWN（§7.7.2）。
            return {
                "candidate": candidate,
                "candidate_verdict": verdict,
                "failed_rules": [asdict(item) for item in outcomes if item.verdict == VERDICT_FAIL],
                "unknown_rules": [asdict(item) for item in outcomes if item.verdict == VERDICT_UNKNOWN],
            }

        if not enabled_rules:
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
            outcomes = [self._evaluate(rule, ctx, ctx) for rule in enabled_rules]
            verdict = aggregate(outcomes)
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
            outcomes = [self._evaluate(rule, candidate, ctx) for rule in enabled_rules]
            verdict = aggregate(outcomes)
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
