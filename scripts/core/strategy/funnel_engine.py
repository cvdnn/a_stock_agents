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


@dataclass
class RuleResult:
    rule_id: str
    passed: bool
    status: str = "PASS"
    reason: str = ""
    observed: Any = None
    expected: Any = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.passed and self.status == "PASS":
            self.status = "FAIL"


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

        def rules_pass(outcomes: List[RuleResult]) -> bool:
            return all(item.passed for item in outcomes) if logic == "all" else any(item.passed for item in outcomes)

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
            )

        if scope == "universe_gate":
            outcomes = [self._evaluate(rule, ctx, ctx) for rule in enabled_rules]
            passed = rules_pass(outcomes)
            rejected = [] if passed else [
                {
                    "candidate": item,
                    "failed_rules": [asdict(r) for r in outcomes if not r.passed],
                }
                for item in input_records
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
            )

        passed_records: List[Dict[str, Any]] = []
        rejected_records: List[Dict[str, Any]] = []
        for candidate in input_records:
            outcomes = [self._evaluate(rule, candidate, ctx) for rule in enabled_rules]
            if rules_pass(outcomes):
                enriched = dict(candidate)
                history = list(enriched.get("_funnel_history", []))
                if enriched.get("_funnel"):
                    history.append(enriched["_funnel"])
                current_audit = {
                    "stage": stage_id,
                    "rules": [asdict(item) for item in outcomes],
                }
                enriched["_funnel"] = current_audit
                enriched["_funnel_history"] = history
                passed_records.append(enriched)
            else:
                rejected_records.append({
                    "candidate": candidate,
                    "failed_rules": [asdict(item) for item in outcomes if not item.passed],
                })

        if not input_records:
            status = "EMPTY"
        elif passed_records:
            status = "PASSED"
        else:
            status = "NO_MATCH"
        return StageResult(
            stage_id=stage_id,
            name=name,
            scope=scope,
            status=status,
            input_count=len(input_records),
            output_count=len(passed_records),
            passed_records=passed_records,
            rejected_records=rejected_records,
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
            return RuleResult(
                rule_id=str(rule["id"]),
                passed=False,
                status="INSUFFICIENT_DATA",
                reason=f"规则输入不足: {exc}",
            )
        result.rule_id = str(rule["id"])
        return result
