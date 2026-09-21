# -*- coding: utf-8 -*-
from core.data.data_layer import (
    MINUTE_TS_OUT_OF_RANGE,
    MINUTE_TS_UNPARSABLE,
    normalize_minute_timestamp,
)
from core.strategy.funnel_engine import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    kleene_all,
    kleene_any,
)
from core.strategy.stock_funnel import (
    MINUTE_BAR_NOT_FINALIZED,
    MINUTE_POINTS_INSUFFICIENT,
    MINUTE_POINTS_UNAVAILABLE,
    MINUTE_SEGMENT_INSUFFICIENT,
    REQUIRED_CONFIRMATION_UNAVAILABLE,
    StockFunnelPipeline,
    derive_earliest_possible_hit_time,
    derive_open_gap,
    load_funnel_config,
)


def eligible_daily_record(code="600001"):
    closes = [10 + i * 0.02 for i in range(69)] + [12.5]
    return {
        "code": code,
        "name": "示例股份",
        "circulating_market_cap": 5_000_000_000,
        "change_pct": 4.0,
        "closes": closes,
        "volumes": [1000] * 68 + [1200, 1800],
        "main_net_inflow": 20_000_000,
    }


def turning_record():
    return {
        "code": "600001",
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


def test_default_config_is_valid_and_reorderable():
    config = load_funnel_config()
    config["stages"] = list(reversed(config["stages"]))
    pipeline = StockFunnelPipeline(config=config)
    assert pipeline.stage_ids[0] == "turning_point"
    assert "post_close" in pipeline.stage_ids


def test_post_close_accepts_matching_record_and_rejects_gain_at_7pct():
    pipeline = StockFunnelPipeline()
    accepted = pipeline.run_stage("post_close", [eligible_daily_record()])
    assert accepted["output_count"] == 1

    rejected_record = eligible_daily_record()
    rejected_record["change_pct"] = 7.0
    rejected = pipeline.run_stage("post_close", [rejected_record])
    assert rejected["output_count"] == 0
    failed = rejected["rejected_records"][0]["failed_rules"]
    assert any(item["rule_id"] == "daily_gain_below_7pct" for item in failed)


def test_breakout_lookback_can_be_changed_without_code_change():
    config = load_funnel_config()
    breakout = next(
        rule for stage in config["stages"] if stage["id"] == "post_close"
        for rule in stage["rules"] if rule["id"] == "breakout_high"
    )
    breakout["lookback"] = 60
    pipeline = StockFunnelPipeline(config=config)
    assert pipeline.run_stage("post_close", [eligible_daily_record()])["output_count"] == 1


def test_market_gate_blocks_entire_universe_below_ma20():
    pipeline = StockFunnelPipeline()
    result = pipeline.run_stage(
        "market_gate",
        [{"code": "600001"}, {"code": "600002"}],
        {"market": {"current_price": 99, "completed_closes": [100] * 20}},
    )
    assert result["status"] == "BLOCKED"
    assert result["output_count"] == 0
    assert len(result["rejected_records"]) == 2


def test_opening_gap_is_derived_and_filtered():
    pipeline = StockFunnelPipeline()
    records = derive_open_gap([
        {"code": "600001", "previous_close": 10.0, "open": 10.15},
        {"code": "600002", "previous_close": 10.0, "open": 10.30},
    ])
    result = pipeline.run_stage("opening_gap", records)
    assert [item["code"] for item in result["passed_records"]] == ["600001"]


def test_turning_point_requires_pullback_and_supply_demand_confirmation():
    pipeline = StockFunnelPipeline()
    result = pipeline.run_stage("turning_point", [turning_record()])
    assert result["output_count"] == 1
    metrics = result["passed_records"][0]["_funnel"]["rules"][0]["metrics"]
    assert metrics["confirmations"]["pullback"] is True
    assert metrics["confirmations"]["price_reversal"] is True
    assert metrics["confirmations"]["book_support"] is True


def test_turning_point_does_not_invent_signal_with_insufficient_data():
    pipeline = StockFunnelPipeline()
    record = turning_record()
    record["minute_points"] = record["minute_points"][:3]
    result = pipeline.run_stage("turning_point", [record])
    unknown = result["rejected_records"][0]["unknown_rules"][0]
    assert unknown["verdict"] == VERDICT_UNKNOWN
    assert unknown["reason_code"] == MINUTE_POINTS_INSUFFICIENT
    assert result["output_count"] == 0


def test_turning_point_shape_variant_passes_without_supply_demand_data():
    pipeline = StockFunnelPipeline()
    record = turning_record()
    for point in record["minute_points"]:
        point.pop("buy_volume")
        point.pop("sell_volume")
    # 形态版（min_confirmations=0）：缺主动买卖量不阻断，但确认项必须留痕为不可用。
    result = pipeline.run_stage("turning_point", [record])
    assert result["output_count"] == 1
    metrics = result["passed_records"][0]["_funnel"]["rules"][0]["metrics"]
    assert metrics["confirmations"]["sell_exhaustion"] is False
    assert "sell_ratio" in metrics["unavailable"]
    assert "buy_ratio" in metrics["unavailable"]


def test_turning_point_supply_demand_variant_requires_real_sell_pressure():
    config = load_funnel_config()
    for stage in config["stages"]:
        if stage["id"] != "turning_point":
            continue
        for rule in stage["rules"]:
            rule["required"] = ["pullback", "price_reversal", "sell_exhaustion"]
            rule["min_confirmations"] = 1
    pipeline = StockFunnelPipeline(config=config)
    record = turning_record()
    for point in record["minute_points"]:
        point.pop("buy_volume")
        point.pop("sell_volume")
    # A strong order book alone must not replace unavailable sell exhaustion.
    result = pipeline.run_stage("turning_point", [record])
    unknown = result["rejected_records"][0]["unknown_rules"][0]
    assert unknown["verdict"] == VERDICT_UNKNOWN
    assert unknown["reason_code"] == REQUIRED_CONFIRMATION_UNAVAILABLE
    assert result["selected_codes"] == []


def test_minute_timestamp_normalization_accepts_required_input_forms():
    epoch_seconds = 1789954560  # 2026-09-21 09:36:00+08:00
    for raw in [
        "09:36",
        "09:36:00",
        "09:36:30",
        "0936",
        "093600",
        "2026-09-21 09:36",
        "2026-09-21T09:36:00+08:00",
        "2026-09-21T01:36:00Z",
        epoch_seconds,
        epoch_seconds * 1000,
        str(epoch_seconds),
        str(epoch_seconds * 1000),
    ]:
        assert normalize_minute_timestamp(raw) == ("09:36", None), raw


def test_minute_timestamp_normalization_flags_unparsable_and_out_of_range():
    for raw in ["", "abc", None, "09:6"]:
        assert normalize_minute_timestamp(raw) == (None, MINUTE_TS_UNPARSABLE), raw
    for raw in ["25:00", "09:60"]:
        assert normalize_minute_timestamp(raw) == (None, MINUTE_TS_OUT_OF_RANGE), raw


def test_turning_point_counts_dropped_points_without_silent_loss():
    pipeline = StockFunnelPipeline()
    record = turning_record()
    record["minute_points"][0]["time"] = "09:30:00"  # 未归一化：装配层本应输出 Bar 起点 HH:MM
    result = pipeline.run_stage("turning_point", [record])
    assert result["output_count"] == 1
    metrics = result["passed_records"][0]["_funnel"]["rules"][0]["metrics"]
    assert metrics["dropped_point_count"] == 1
    assert metrics["dropped_points"][0]["field_status"] == "missing"
    assert metrics["dropped_points"][0]["reason_code"] == "MINUTE_TIMESTAMP_NOT_NORMALIZED"


def test_turning_point_returns_unknown_when_no_timestamp_is_usable():
    pipeline = StockFunnelPipeline()
    record = turning_record()
    for point in record["minute_points"]:
        point["time"] = f"{point['time']}:00"
    result = pipeline.run_stage("turning_point", [record])
    unknown = result["rejected_records"][0]["unknown_rules"][0]
    assert unknown["verdict"] == VERDICT_UNKNOWN
    assert unknown["reason_code"] == MINUTE_POINTS_UNAVAILABLE
    assert unknown["metrics"]["dropped_point_count"] == len(record["minute_points"])
    assert unknown["metrics"]["minute_points_field_status"] == "missing"


def test_turning_point_excludes_in_progress_bar_from_counts():
    pipeline = StockFunnelPipeline()
    record = turning_record()
    record["minute_points"][-1]["field_status"] = "not_ready"  # 09:37 尚未收满
    result = pipeline.run_stage("turning_point", [record])
    assert result["output_count"] == 0
    unknown = result["rejected_records"][0]["unknown_rules"][0]
    assert unknown["verdict"] == VERDICT_UNKNOWN
    assert unknown["reason_code"] == MINUTE_SEGMENT_INSUFFICIENT
    metrics = unknown["metrics"]
    assert metrics["dropped_point_count"] == 1
    assert metrics["dropped_points"][0]["field_status"] == "not_ready"
    assert metrics["dropped_points"][0]["reason_code"] == MINUTE_BAR_NOT_FINALIZED
    assert metrics["confirm_points"] == 1  # 进行中Bar不参与确认段计数
    assert metrics["min_confirm_points"] == 2


def test_turning_point_returns_unknown_when_all_points_are_in_progress():
    pipeline = StockFunnelPipeline()
    record = turning_record()
    for point in record["minute_points"]:
        point["field_status"] = "not_ready"
    result = pipeline.run_stage("turning_point", [record])
    unknown = result["rejected_records"][0]["unknown_rules"][0]
    assert unknown["verdict"] == VERDICT_UNKNOWN
    assert unknown["reason_code"] == MINUTE_POINTS_UNAVAILABLE
    assert unknown["metrics"]["minute_points_field_status"] == "not_ready"


def test_turning_point_segment_minimums_come_from_config():
    config = load_funnel_config()
    for stage in config["stages"]:
        if stage["id"] != "turning_point":
            continue
        for rule in stage["rules"]:
            rule["min_confirm_points"] = 3
    pipeline = StockFunnelPipeline(config=config)
    result = pipeline.run_stage("turning_point", [turning_record()])
    unknown = result["rejected_records"][0]["unknown_rules"][0]
    assert unknown["verdict"] == VERDICT_UNKNOWN
    assert unknown["reason_code"] == MINUTE_SEGMENT_INSUFFICIENT
    assert unknown["metrics"]["confirm_points"] == 2
    assert unknown["metrics"]["min_confirm_points"] == 3


def test_kleene_all_truth_table_matches_spec_7_7_4():
    assert kleene_all([VERDICT_PASS, VERDICT_PASS]) == VERDICT_PASS
    assert kleene_all([VERDICT_PASS, VERDICT_UNKNOWN]) == VERDICT_UNKNOWN
    assert kleene_all([VERDICT_PASS, VERDICT_FAIL]) == VERDICT_FAIL
    assert kleene_all([VERDICT_UNKNOWN, VERDICT_UNKNOWN]) == VERDICT_UNKNOWN
    assert kleene_all([VERDICT_UNKNOWN, VERDICT_FAIL]) == VERDICT_FAIL
    assert kleene_all([VERDICT_FAIL, VERDICT_FAIL]) == VERDICT_FAIL
    # FAIL 吸收：任一硬规则确定性不成立，数据缺失不能把候选“救回”。
    assert kleene_all([VERDICT_UNKNOWN, VERDICT_FAIL, VERDICT_UNKNOWN]) == VERDICT_FAIL
    assert kleene_all([]) == VERDICT_PASS


def test_kleene_any_truth_table_matches_spec_7_7_4():
    assert kleene_any([VERDICT_PASS, VERDICT_PASS]) == VERDICT_PASS
    assert kleene_any([VERDICT_PASS, VERDICT_UNKNOWN]) == VERDICT_PASS
    assert kleene_any([VERDICT_PASS, VERDICT_FAIL]) == VERDICT_PASS
    assert kleene_any([VERDICT_UNKNOWN, VERDICT_UNKNOWN]) == VERDICT_UNKNOWN
    assert kleene_any([VERDICT_UNKNOWN, VERDICT_FAIL]) == VERDICT_UNKNOWN
    assert kleene_any([VERDICT_FAIL, VERDICT_FAIL]) == VERDICT_FAIL
    # PASS 吸收：任一确认项确凿成立即满足分支，数据缺失不能把分支“拖垮”。
    assert kleene_any([VERDICT_FAIL, VERDICT_UNKNOWN, VERDICT_PASS]) == VERDICT_PASS
    assert kleene_any([]) == VERDICT_FAIL


def test_rule_result_projects_passed_from_verdict_only():
    from core.strategy.funnel_engine import RuleResult

    unknown = RuleResult("r", verdict=VERDICT_UNKNOWN, reason_code="X")
    assert unknown.passed is False
    assert RuleResult("r", verdict=VERDICT_PASS).passed is True
    assert RuleResult("r", verdict=VERDICT_FAIL).passed is False
    # two_state 永不产生 UNKNOWN：False 必须归为 FAIL 而非“数据不足”。
    assert RuleResult.two_state("r", False).verdict == VERDICT_FAIL
    assert RuleResult.two_state("r", True).verdict == VERDICT_PASS


def test_turning_point_missing_order_book_is_unknown_not_fail():
    # §7.7.7：盘口缺省不得默认 0 静默降级为“不成立”，须记 UNKNOWN。
    config = load_funnel_config()
    for stage in config["stages"]:
        if stage["id"] != "turning_point":
            continue
        for rule in stage["rules"]:
            rule["required"] = ["pullback", "price_reversal", "book_support"]
    pipeline = StockFunnelPipeline(config=config)
    record = turning_record()
    record.pop("order_book")
    result = pipeline.run_stage("turning_point", [record])
    assert result["output_count"] == 0
    unknown = result["rejected_records"][0]["unknown_rules"][0]
    assert unknown["verdict"] == VERDICT_UNKNOWN
    assert unknown["reason_code"] == REQUIRED_CONFIRMATION_UNAVAILABLE
    assert unknown["metrics"]["book_ratio"] is None
    assert "book_ratio" in unknown["metrics"]["unavailable"]


def test_earliest_possible_hit_time_is_derived_at_compile_time():
    """§5.5/§11.5：编译期由 min_points、min_pullback_points、min_confirm_points 与Bar起点语义推导。

    默认配置 window_start=09:30/min_points=6 → 09:36；min_pullback_points=3 → 09:33；
    confirm_start=09:36/min_confirm_points=2 → 09:38。取最晚者 09:38。
    Bar 以起点标识，起点 T 的Bar收满定盘于 T+1 分钟，故只计已定盘Bar。
    """
    pipeline = StockFunnelPipeline()
    assert pipeline.earliest_possible_hit_times == {
        "turning_point": {"pullback_supply_demand_turn": "09:38"}
    }
    # 非分钟窗口规则不产生该值，也不得被误标
    assert derive_earliest_possible_hit_time({"type": "field_compare", "field": "change_pct", "op": "lt", "value": 7.0}) is None
    # 三项约束皆为零 → 无时间约束
    assert derive_earliest_possible_hit_time({"window_start": "09:30", "min_points": 0}) is None


def test_earliest_possible_hit_time_follows_config_and_is_never_hand_filled():
    """该值随规则参数变化，禁止在 Web 或文档中手工填写（§5.5 第5条 / §11.5）。"""
    config = load_funnel_config()
    for stage in config["stages"]:
        if stage["id"] != "turning_point":
            continue
        for rule in stage["rules"]:
            rule["min_confirm_points"] = 3
    pipeline = StockFunnelPipeline(config=config)
    assert pipeline.earliest_possible_hit_times["turning_point"]["pullback_supply_demand_turn"] == "09:39"
    assert pipeline.run_stage("turning_point", [turning_record()])["plan"] == {
        "earliest_possible_hit_time": {"pullback_supply_demand_turn": "09:39"}
    }


def test_earliest_possible_hit_time_rejects_unnormalized_window_start():
    """起点未归一化为 HH:MM 时编译期失败关闭，不做字符串截取（§11.5 禁止事项）。"""
    config = load_funnel_config()
    for stage in config["stages"]:
        if stage["id"] != "turning_point":
            continue
        for rule in stage["rules"]:
            rule["window_start"] = "09:30:00"
    try:
        StockFunnelPipeline(config=config)
    except ValueError as exc:
        assert "MINUTE_TIMESTAMP_NOT_NORMALIZED" in str(exc)
    else:
        raise AssertionError("未归一化的 window_start 必须在编译期失败关闭")


def test_earliest_possible_hit_time_matches_actual_first_hit():
    """§14 验收：编译期 earliest_possible_hit_time 与实际首次可命中时点一致。

    09:37 这根确认Bar收满定盘于 09:38，故 09:38 之前不可能命中；
    该Bar进行中时规则为 UNKNOWN 而非 PASS，进行中Bar既不提前时点也不构成已命中证据。
    """
    pipeline = StockFunnelPipeline()
    derived = pipeline.earliest_possible_hit_times["turning_point"]["pullback_supply_demand_turn"]
    assert derived == "09:38"

    # 全部Bar已定盘 → 恰好可在推导时点命中
    assert pipeline.run_stage("turning_point", [turning_record()])["output_count"] == 1

    # 最后一根（09:37）仍在进行中 → 定盘时刻未到，不得提前命中
    in_progress = turning_record()
    in_progress["minute_points"][-1]["field_status"] = "not_ready"
    blocked = pipeline.run_stage("turning_point", [in_progress])
    assert blocked["output_count"] == 0
    assert blocked["plan"]["earliest_possible_hit_time"] == {"pullback_supply_demand_turn": derived}


def test_calendar_version_lands_in_run_metadata_and_not_in_plan():
    """§11.2/§11.7：calendar_version 记入运行元数据，且不进入 plan_hash。

    plan_hash 只覆盖模型定义、规则与参数；日历内容随运行变化，不得影响编译期计划输出。
    """
    pipeline = StockFunnelPipeline()
    first = pipeline.run_stage(
        "turning_point", [turning_record()], {"calendar_version": "cal-aaaaaaaaaaaa", "calendar_available": True}
    )
    second = pipeline.run_stage(
        "turning_point", [turning_record()], {"calendar_version": "cal-bbbbbbbbbbbb", "calendar_available": True}
    )
    assert first["run_metadata"] == {"calendar_version": "cal-aaaaaaaaaaaa", "calendar_available": True}
    assert second["run_metadata"]["calendar_version"] == "cal-bbbbbbbbbbbb"
    # 日历版本变化不得改变编译期计划输出（plan_hash 排除逻辑的可观测代理）
    assert first["plan"] == second["plan"] == {
        "earliest_possible_hit_time": {"pullback_supply_demand_turn": "09:38"}
    }

    # 未提供日历时如实记 None，不得伪造版本号
    bare = pipeline.run_stage("turning_point", [turning_record()])
    assert bare["run_metadata"]["calendar_version"] is None
    assert bare["run_metadata"]["calendar_available"] is None

    # universe_gate 以 context 兼作记录，注入日历键不得干扰门控求值
    gated = pipeline.run_stage(
        "market_gate",
        [{"code": "600001"}],
        {
            "market": {"current_price": 99, "completed_closes": [100] * 20},
            "calendar_version": "cal-aaaaaaaaaaaa",
            "calendar_available": True,
        },
    )
    assert gated["status"] == "BLOCKED"
    assert gated["run_metadata"]["calendar_version"] == "cal-aaaaaaaaaaaa"
