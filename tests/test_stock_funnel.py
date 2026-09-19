# -*- coding: utf-8 -*-
from core.strategy.stock_funnel import StockFunnelPipeline, derive_open_gap, load_funnel_config


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
    failed = result["rejected_records"][0]["failed_rules"][0]
    assert failed["status"] == "INSUFFICIENT_DATA"
    assert result["output_count"] == 0


def test_turning_point_requires_sell_pressure_data():
    pipeline = StockFunnelPipeline()
    record = turning_record()
    for point in record["minute_points"]:
        point.pop("buy_volume")
        point.pop("sell_volume")
    # A strong order book alone must not replace unavailable sell exhaustion.
    result = pipeline.run_stage("turning_point", [record])
    failed = result["rejected_records"][0]["failed_rules"][0]
    assert failed["status"] == "INSUFFICIENT_DATA"
    assert result["selected_codes"] == []
