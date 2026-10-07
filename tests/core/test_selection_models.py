# -*- coding: utf-8 -*-
"""批次一（M-02 核心引擎）核心契约测试：A1～A8。

覆盖：v2 Schema 与 v1→v2 迁移、确定性哈希、嵌套 AND/OR/NOT AST、
模型类型注册、编译产物、规则参数 Schema、版本仓库与悲观锁、按依赖编排。
"""
from __future__ import annotations

import json

import pytest

from core.selection_models import schemas
from core.selection_models.definition_repository import (
    DefinitionRepository,
    DraftConflictError,
)
from core.selection_models.hash import (
    canonical_json,
    definition_hash,
    plan_hash,
)
from core.selection_models.model_compiler import (
    ModelCompilerError,
    compile_definition,
)
from core.selection_models.model_type_registry import (
    ModelTypeError,
    build_default_type_registry,
)
from core.selection_models.orchestrator import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_EMPTY,
    SelectionModelOrchestrator,
)
from core.selection_models.rule_registry import (
    RULE_METADATA,
    RuleMetadataError,
    RuleMetadataRegistry,
    build_default_rule_registry,
)
from core.selection_models.version_repository import (
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_RETIRED,
    VersionConflictError,
    VersionRepository,
)
from core.strategy.funnel_engine import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    FunnelEngine,
    RuleRegistry,
    RuleResult,
    evaluate_expression,
    expression_depth,
    expression_leaves,
    kleene_not,
    validate_expression,
)
from core.strategy.stock_funnel import DEFAULT_CONFIG_PATH, build_stock_rule_registry


# ------------------------------------------------------------------ 测试夹具
def _pass_rule(record, spec, ctx):
    return RuleResult.two_state("", True)


def _fail_rule(record, spec, ctx):
    return RuleResult.two_state("", False)


def _unknown_rule(record, spec, ctx):
    return RuleResult("", verdict=VERDICT_UNKNOWN, reason_code="X")


def _engine_with(rules):
    registry = RuleRegistry()
    for name, evaluator in rules.items():
        registry.register(name, evaluator)
    return FunnelEngine(registry)


def _migrated_config():
    definition, _ = schemas.load_definition(DEFAULT_CONFIG_PATH)
    return definition


def _condition_tree_definition():
    return {
        "schema_version": 2,
        "model": {
            "id": "cond_demo",
            "name": "条件示例",
            "model_type": "condition_tree",
            "version": 1,
        },
        "groups": [
            {
                "id": "tech",
                "name": "技术面",
                "logic": "all",
                "rules": [{"id": "t1", "type": "rolling_high", "field": "closes", "lookback": 20}],
            },
            {
                "id": "risk",
                "name": "风险面",
                "logic": "all",
                "rules": [{"id": "r1", "type": "text_exclude", "field": "name", "tokens": ["ST"]}],
            },
        ],
        "expression": {"op": "and", "children": [{"ref": "tech"}, {"op": "not", "child": {"ref": "risk"}}]},
    }


# ================================================================== A3
def test_kleene_not_follows_strong_three_valued_logic():
    assert kleene_not(VERDICT_PASS) == VERDICT_FAIL
    assert kleene_not(VERDICT_FAIL) == VERDICT_PASS
    # S-04：NOT UNKNOWN = UNKNOWN，不回绕为 PASS
    assert kleene_not(VERDICT_UNKNOWN) == VERDICT_UNKNOWN


def test_nested_expression_truth_table_matches_kleene():
    table = {VERDICT_PASS: "P", VERDICT_FAIL: "F", VERDICT_UNKNOWN: "U"}
    lexicon = {name: verdict for verdict, name in table.items()}

    def resolve(leaf):
        return lexicon[leaf["ref"]]

    def expected_and(values):
        if VERDICT_FAIL in values:
            return VERDICT_FAIL
        if VERDICT_UNKNOWN in values:
            return VERDICT_UNKNOWN
        return VERDICT_PASS

    def expected_or(values):
        if VERDICT_PASS in values:
            return VERDICT_PASS
        if VERDICT_UNKNOWN in values:
            return VERDICT_UNKNOWN
        return VERDICT_FAIL

    names = ["P", "F", "U"]
    for a in names:
        for b in names:
            for c in names:
                expression = {
                    "op": "or",
                    "children": [
                        {"op": "and", "children": [{"ref": a}, {"op": "not", "child": {"ref": b}}]},
                        {"ref": c},
                    ],
                }
                inner = expected_and([lexicon[a], kleene_not(lexicon[b])])
                assert evaluate_expression(expression, resolve) == expected_or([inner, lexicon[c]])


def test_expression_rejects_depth_over_three_and_leaf_over_limit():
    deep = {"ref": "a"}
    for _ in range(4):
        deep = {"op": "and", "children": [deep]}
    assert expression_depth(deep) == 4
    with pytest.raises(ValueError, match="深度"):
        validate_expression(deep)

    wide = {"op": "and", "children": [{"ref": f"r{index}"} for index in range(201)]}
    with pytest.raises(ValueError, match="叶子总数"):
        validate_expression(wide)
    assert len(expression_leaves({"op": "and", "children": [{"ref": "r0"}]})) == 1


def test_expression_rejects_unknown_operator_and_dangling_ref():
    with pytest.raises(ValueError, match="算子"):
        validate_expression({"op": "xor", "children": [{"ref": "a"}]})

    engine = _engine_with({"k": _pass_rule})
    stage = {
        "id": "s",
        "scope": "candidate_filter",
        "expression": {"op": "and", "children": [{"ref": "missing"}]},
        "rules": [{"id": "a", "type": "k"}],
    }
    with pytest.raises(ValueError, match="未声明的规则"):
        engine.validate_stage(stage)


def test_engine_executes_nested_expression_and_keeps_all_any_shortcut():
    engine = _engine_with({"k": _pass_rule, "n": _fail_rule, "u": _unknown_rule})
    rules = [
        {"id": "a", "type": "k"},
        {"id": "b", "type": "n"},
        {"id": "c", "type": "u"},
    ]
    stage = {
        "id": "s",
        "scope": "candidate_filter",
        "logic": "all",
        "rules": rules,
        "expression": {
            "op": "and",
            "children": [{"ref": "a"}, {"op": "not", "child": {"ref": "b"}}],
        },
    }
    result = engine.run_stage(stage, [{"code": "600001"}])
    assert result.status == "PASSED"
    assert result.output_count == 1

    # not UNKNOWN 传播：把 b 换成未判定规则，整链转 UNKNOWN，候选不得被“救回”为 PASS
    stage_unknown = dict(stage, expression={"op": "and", "children": [{"ref": "a"}, {"op": "not", "child": {"ref": "c"}}]})
    unknown_result = engine.run_stage(stage_unknown, [{"code": "600001"}])
    assert unknown_result.output_count == 0
    assert unknown_result.rejected_records[0]["candidate_verdict"] == VERDICT_UNKNOWN

    # `all/any` 仍是合法快捷写法（向后兼容）
    flat_all = {"id": "s2", "scope": "candidate_filter", "logic": "all", "rules": [{"id": "a", "type": "k"}]}
    assert engine.run_stage(flat_all, [{"code": "x"}]).output_count == 1
    flat_any = {"id": "s3", "scope": "candidate_filter", "logic": "any", "rules": [{"id": "b", "type": "n"}]}
    assert engine.run_stage(flat_any, [{"code": "x"}]).output_count == 0


# ================================================================== A1
def test_v1_config_migrates_to_v2_idempotently_with_warnings():
    definition, warnings = schemas.load_definition(DEFAULT_CONFIG_PATH)
    assert definition["schema_version"] == schemas.SCHEMA_VERSION
    assert warnings, "v1 加载必须输出迁移告警（T-06）"
    assert definition["model"]["id"] == "close_to_open_turning_point"
    assert definition["model"]["model_type"] == "funnel"
    assert [stage["id"] for stage in definition["stages"]] == [
        "post_close",
        "market_gate",
        "opening_gap",
        "turning_point",
    ]
    # 行为不变：规则与 all/any 语义原样保留，层级按顺序链式绑定
    assert definition["stages"][0]["input_binding"] == schemas.ROOT_INPUT_BINDING
    assert definition["stages"][1]["input_binding"] == "post_close.candidates"
    assert definition["stages"][1]["logic"] == "all"

    again, second_warnings = schemas.migrate_to_v2(definition)
    assert second_warnings == []
    assert again == definition, "迁移必须幂等"


def test_v1_migration_preserves_rule_semantics_via_compiler():
    definition = _migrated_config()
    plan = compile_definition(definition)
    # post_close 全部 10 条规则（含 enabled=false 的 2 条）原样进入编译计划
    post_close = plan.stages[0]
    assert len(post_close.rules) == 10
    assert {rule["type"] for rule in post_close.rules} >= {"text_exclude", "rolling_high", "above_sma"}
    assert post_close.expression["op"] == "and"
    assert len(post_close.expression["children"]) == 8  # 仅 8 条启用规则参与表达式


def test_migrator_fails_closed_on_unsupported_version():
    with pytest.raises(schemas.SelectionSchemaError, match="不支持的配置版本"):
        schemas.migrate_to_v2({"version": 99, "stages": []})


# ================================================================== A2
def test_canonical_json_is_key_order_and_number_literal_invariant():
    left = {"b": 1e2, "a": [1e2, {"y": None, "x": "值"}]}
    right = {"a": [100, {"x": "值", "y": None}], "b": 100}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_json(left) == '{"a":[100,{"x":"值","y":null}],"b":100}'


def test_plan_hash_is_deterministic_and_excludes_runtime_metadata():
    definition = _migrated_config()
    first = compile_definition(definition)
    second = compile_definition(definition)
    assert first.plan_hash == second.plan_hash
    assert first.plan_hash.startswith("sha256:")

    payload = first.payload()
    assert "calendar_version" not in canonical_json(payload)
    assert "generated_at" not in payload
    # 可由规范文本独立复算
    assert plan_hash(payload) == first.plan_hash


def test_definition_hash_ignores_key_order_and_tracks_params():
    definition = _migrated_config()
    same = json.loads(json.dumps(definition, ensure_ascii=False))
    assert definition_hash(definition) == definition_hash(same)

    changed = json.loads(json.dumps(definition, ensure_ascii=False))
    changed["stages"][0]["rules"][4]["lookback"] = 60  # breakout_high
    assert definition_hash(definition) != definition_hash(changed)
    assert compile_definition(definition).plan_hash != compile_definition(changed).plan_hash


def test_plan_hash_changes_when_rule_caliber_version_changes():
    definition = _migrated_config()
    baseline = compile_definition(definition)

    metadata = {key: dict(value) for key, value in RULE_METADATA.items()}
    metadata["rolling_high"] = {**metadata["rolling_high"], "version": 2}
    registry = RuleMetadataRegistry()
    for type_id, meta in metadata.items():
        registry.register(type_id, meta)
    bumped = compile_definition(definition, rule_registry=registry)

    assert bumped.plan_hash != baseline.plan_hash
    assert bumped.stages[0].rules[4]["version"] == 2


# ================================================================== A7
def test_rule_registry_covers_all_executable_rule_types():
    metadata = build_default_rule_registry()
    assert set(metadata.names) == set(build_stock_rule_registry().names)
    for type_id in metadata.names:
        meta = metadata.get(type_id)
        assert meta.version >= 1
        assert meta.parameter_schema, f"{type_id} 缺少参数 Schema"
        assert meta.required_inputs


def test_rule_param_schema_accepts_real_config_and_rejects_illegal_values():
    registry = build_default_rule_registry()
    definition = _migrated_config()
    for stage in definition["stages"]:
        for rule in stage["rules"]:
            registry.validate_rule_spec(rule)  # 存量配置必须全部合法

    with pytest.raises(RuleMetadataError, match="必须是整数"):
        registry.validate_params("rolling_high", {"field": "closes", "lookback": "20"})
    with pytest.raises(RuleMetadataError, match="大于上限"):
        registry.validate_params("rolling_high", {"lookback": 600})
    with pytest.raises(RuleMetadataError, match="未知参数"):
        registry.validate_params("rolling_high", {"lookback": 20, "typo": 1})
    with pytest.raises(RuleMetadataError, match="缺少必填参数"):
        registry.validate_params("text_exclude", {"field": "name"})
    with pytest.raises(RuleMetadataError, match="不在允许取值"):
        registry.validate_params("field_compare", {"field": "x", "op": "approx", "value": 1})


def test_rule_form_annotations_are_derived_from_schema():
    registry = build_default_rule_registry()
    annotations = registry.form_annotations("rolling_high")
    assert annotations["lookback"]["x-quick-presets"] == [10, 20, 30, 60]  # D-01/S-06
    assert annotations["lookback"]["default"] == 20
    assert annotations["lookback"]["type"] == "integer"
    assert annotations["field"]["x-ui-widget"] == "field-selector"


# ================================================================== A5
def test_type_registry_registers_four_types_and_p2_is_not_publishable():
    registry = build_default_type_registry()
    assert registry.names == ["composite", "condition_tree", "funnel", "scoring_rank"]
    assert registry.publishable_names == ["condition_tree", "funnel"]
    with pytest.raises(ModelTypeError, match="不可发布"):
        registry.require_publishable("scoring_rank")
    with pytest.raises(ModelTypeError, match="未知模型类型"):
        registry.get("nope")
    assert registry.get("funnel").supported_node_kinds == ("filter", "gate", "output")


# ================================================================== A4
def test_compiler_produces_stable_funnel_plan_by_dependency():
    definition = _migrated_config()
    plan = compile_definition(definition)
    assert plan.engine == "hierarchical_funnel"
    assert plan.source_model["model_type"] == "funnel"
    assert [(stage.id, stage.kind, stage.scope) for stage in plan.stages] == [
        ("post_close", "filter", "candidate_filter"),
        ("market_gate", "gate", "universe_gate"),
        ("opening_gap", "filter", "candidate_filter"),
        ("turning_point", "filter", "candidate_filter"),
    ]
    assert [stage.input for stage in plan.stages] == [
        "market.daily_universe",
        "post_close.candidates",
        "market_gate.candidates",
        "opening_gap.candidates",
    ]
    assert plan.stages[-1].expression == {"ref": "pullback_supply_demand_turn"}
    assert json.loads(json.dumps(plan.to_dict(), ensure_ascii=False))["plan_hash"] == plan.plan_hash


def test_compiler_rejects_p2_types_and_unexecutable_node_kinds():
    p2 = {
        "schema_version": 2,
        "model": {"id": "rank_demo", "name": "评分", "model_type": "scoring_rank", "version": 1},
        "stages": [
            {"id": "score", "kind": "score", "rules": [{"id": "a", "type": "rolling_high", "lookback": 20}]}
        ],
    }
    with pytest.raises(ModelCompilerError, match="不可发布"):
        compile_definition(p2)

    bad_kind = _migrated_config()
    bad_kind["stages"][0]["kind"] = "score"
    with pytest.raises(ModelCompilerError, match="不可执行"):
        compile_definition(bad_kind)


def test_compiler_expands_condition_tree_and_detects_cycles():
    plan = compile_definition(_condition_tree_definition())
    assert len(plan.stages) == 1
    stage = plan.stages[0]
    assert stage.kind == "filter"
    assert stage.expression == {
        "op": "and",
        "children": [{"ref": "t1"}, {"op": "not", "child": {"ref": "r1"}}],
    }

    cyclic = _condition_tree_definition()
    cyclic["groups"] = [
        {"id": "g1", "expression": {"ref": "g2"}},
        {"id": "g2", "expression": {"ref": "g1"}},
    ]
    cyclic["expression"] = {"ref": "g1"}
    with pytest.raises(ModelCompilerError, match="循环引用"):
        compile_definition(cyclic)


# ================================================================== A6
def _repos(tmp_path):
    return (
        DefinitionRepository(base_dir=tmp_path / "cfg", lock_dir=tmp_path / "locks", lock_timeout_s=0.2),
        VersionRepository(base_dir=tmp_path / "cfg"),
    )


def test_publish_versions_are_monotonic_and_immutable(tmp_path):
    drafts, versions = _repos(tmp_path)
    definition = _migrated_config()
    plan = compile_definition(definition)

    first = versions.publish("demo_model", definition, plan, operator="u1")
    second = versions.publish("demo_model", definition, plan, operator="u1")
    assert [first["version"], second["version"]] == [1, 2]
    assert first["definition_hash"].startswith("sha256:")
    assert first["plan_hash"] == plan.plan_hash
    assert versions.definition_of("demo_model", 1)["schema_version"] == 2
    assert versions.plan_of("demo_model", 1)["plan_hash"] == plan.plan_hash

    definition_path = versions.definition_path("demo_model", 1)
    published_content = definition_path.read_text(encoding="utf-8")
    versions.publish("demo_model", definition, plan, operator="u1")
    assert [record["version"] for record in versions.list_versions("demo_model")] == [1, 2, 3]
    # 已发布版本内容不可原地覆盖（§7.6 第2条）
    assert definition_path.read_text(encoding="utf-8") == published_content


def test_draft_conflict_is_rejected_and_revision_increments(tmp_path):
    drafts, _ = _repos(tmp_path)
    definition = _migrated_config()
    created = drafts.create_draft("demo_model", definition, base_version=None, operator="u1")
    assert created["draft_revision"] == 1

    with pytest.raises(DraftConflictError):
        drafts.save_draft("demo_model", definition, base_version=None, draft_revision=5)
    with pytest.raises(DraftConflictError):
        drafts.save_draft("demo_model", definition, base_version=99, draft_revision=1)

    saved = drafts.save_draft("demo_model", definition, base_version=None, draft_revision=1, operator="u2")
    assert saved["draft_revision"] == 2
    assert drafts.load_draft("demo_model")["draft_revision"] == 2


def test_publish_rejects_stale_draft_revision(tmp_path):
    drafts, versions = _repos(tmp_path)
    definition = _migrated_config()
    plan = compile_definition(definition)
    drafts.create_draft("demo_model", definition, base_version=None, operator="u1")
    with pytest.raises(DraftConflictError):
        versions.publish(
            "demo_model", definition, plan, base_version=None, draft_revision=9, draft_repository=drafts
        )


def test_activate_switches_pointer_and_rollback_restores(tmp_path):
    _, versions = _repos(tmp_path)
    definition = _migrated_config()
    plan = compile_definition(definition)
    versions.publish("demo_model", definition, plan)
    versions.publish("demo_model", definition, plan)

    activated = versions.activate("demo_model", 1, operator="u1")
    assert activated["pointer_revision"] == 1
    assert versions.active_version("demo_model") == 1
    assert versions.get_version("demo_model", 1)["status"] == STATUS_ACTIVE

    rolled = versions.rollback("demo_model", 2, operator="u1")
    assert rolled["previous_version"] == 1
    assert versions.get_version("demo_model", 1)["status"] == STATUS_RETIRED
    assert versions.get_version("demo_model", 2)["status"] == STATUS_ACTIVE

    with pytest.raises(VersionConflictError, match="不能归档"):
        versions.archive("demo_model", 2)
    archived = versions.archive("demo_model", 1, operator="u1")
    assert archived["status"] == STATUS_ARCHIVED
    with pytest.raises(VersionConflictError, match="已归档"):
        versions.activate("demo_model", 1)
    # 归档不物理删除，定义与计划文件仍在
    assert versions.definition_path("demo_model", 1).exists()
    assert versions.plan_path("demo_model", 1).exists()


def test_pessimistic_lock_is_exclusive_with_holder_visibility(tmp_path):
    drafts, _ = _repos(tmp_path)
    definition = _migrated_config()
    drafts.create_draft("demo_model", definition)

    lock = drafts.acquire_lock("demo_model", operator="u1", timeout_s=0.2)
    assert lock is not None and lock.held
    holder = drafts.lock_status("demo_model")
    assert holder["operator"] == "u1" and holder["draft_revision"] == 1

    assert drafts.acquire_lock("demo_model", operator="u2", timeout_s=0.1) is None  # 独占

    assert drafts.release_lock("demo_model") is True
    assert drafts.lock_status("demo_model") is None
    regained = drafts.acquire_lock("demo_model", operator="u2", timeout_s=0.2)
    assert regained is not None
    drafts.release_lock("demo_model")


# ================================================================== A8
def _full_record(code="600001"):
    closes = [10 + index * 0.02 for index in range(69)] + [12.5]
    return {
        "code": code,
        "name": "示例股份",
        "circulating_market_cap": 5_000_000_000,
        "change_pct": 4.0,
        "closes": closes,
        "volumes": [1000] * 68 + [1200, 1800],
        "gap_pct": 1.5,
        "minute_points": [
            {"time": "09:30", "price": 10.20, "volume": 800, "buy_volume": 500, "sell_volume": 300},
            {"time": "09:31", "price": 10.30, "volume": 900, "buy_volume": 550, "sell_volume": 350},
            {"time": "09:32", "price": 10.25, "volume": 700, "buy_volume": 250, "sell_volume": 450},
            {"time": "09:33", "price": 10.20, "volume": 600, "buy_volume": 200, "sell_volume": 400},
            {"time": "09:34", "price": 10.18, "volume": 500, "buy_volume": 180, "sell_volume": 320},
            {"time": "09:35", "price": 10.17, "volume": 400, "buy_volume": 160, "sell_volume": 240},
            {"time": "09:36", "price": 10.18, "volume": 450, "buy_volume": 300, "sell_volume": 150},
            {"time": "09:37", "price": 10.21, "volume": 650, "buy_volume": 520, "sell_volume": 130},
        ],
        "order_book": {"bid_volume": 1500, "ask_volume": 1000},
    }


def _market_context(current_price=101):
    return {"market": {"current_price": current_price, "completed_closes": [100] * 20}}


def test_run_all_executes_four_stage_funnel_by_dependency():
    plan = compile_definition(_migrated_config())
    orchestrator = SelectionModelOrchestrator()
    result = orchestrator.run_all(plan, [_full_record()], _market_context())

    assert result["status"] == STATUS_COMPLETED
    assert result["selected_codes"] == ["600001"]
    assert result["final_stage"] == "turning_point"
    assert [stage["stage_id"] for stage in result["stages"]] == [
        "post_close",
        "market_gate",
        "opening_gap",
        "turning_point",
    ]
    assert [stage["output_count"] for stage in result["stages"]] == [1, 1, 1, 1]
    assert result["plan_hash"] == plan.plan_hash
    assert result["run_id"].startswith("selection_")
    assert result["run_metadata"] == {"calendar_version": None, "calendar_available": None}


def test_run_all_blocks_whole_pipeline_on_market_gate_failure():
    plan = compile_definition(_migrated_config())
    result = SelectionModelOrchestrator().run_all(plan, [_full_record()], _market_context(98))
    assert result["status"] == STATUS_BLOCKED
    assert result["final_stage"] == "market_gate"
    assert result["selected_codes"] == []
    assert [stage["status"] for stage in result["stages"]] == ["PASSED", "BLOCKED"]


def test_run_all_returns_empty_without_fabricating_candidates():
    plan = compile_definition(_migrated_config())
    record = _full_record()
    record["change_pct"] = 9.9  # 触发涨幅硬规则淘汰
    result = SelectionModelOrchestrator().run_all(plan, [record], _market_context())
    assert result["status"] == STATUS_EMPTY
    assert result["selected_codes"] == []
    assert result["final_stage"] == "post_close"


def test_run_all_metadata_marks_calendar_without_fabrication():
    plan = compile_definition(_migrated_config())
    result = SelectionModelOrchestrator().run_all(
        plan,
        [_full_record()],
        {"calendar_version": "cal-aaaaaaaaaaaa", "calendar_available": True},
    )
    assert result["run_metadata"]["calendar_version"] == "cal-aaaaaaaaaaaa"
    assert result["run_metadata"]["calendar_available"] is True