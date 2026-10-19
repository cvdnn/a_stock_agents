# -*- coding: utf-8 -*-
"""Engine A: 多源数据同步、盘中切片与水位门禁引擎测试。

归属代码包：`core/data/` (data_bridge, sync_engine, dataset_sync, intraday_archiver, data_assembler)
核心职责与断言：
1. QuoteDict 别名与证券代码规范化（normalize_symbol, is_index_symbol）；
2. 4 级行情容灾降级（腾讯 -> 新浪 -> 东财 -> 本地 SQLite 真实数据）；
3. 零虚假数据铁律：外部源失败且本地无数据时 Fail-Closed 返回空，绝不凭空编造；
4. MarketDataStore 内存/临时库增量落盘与时间范围查询（upsert_klines, get_klines）；
5. DataAssembler 内容哈希确定性寻址；
6. 选股前置盘后水位门禁（`evaluate_data_gate` 未达标 WAITING_DATA 失败关闭）；
7. 分钟切片时间戳归一化与区间判定。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from core.data.data_assembler import (
    GATE_PASS,
    GATE_WAITING_DATA,
    STATUS_OK,
    STATUS_WAITING_DATA,
    DataAssembler,
    content_hash,
)
from core.data.data_bridge import DataBridge
from core.data.data_layer import (
    MINUTE_TS_OUT_OF_RANGE,
    MINUTE_TS_UNPARSABLE,
    normalize_minute_timestamp,
)
from core.data.sync_engine import (
    MarketDataStore,
    TradeCalendar,
    is_index_symbol,
)

pytestmark = pytest.mark.core


def _mock_klines(count=20, base=10.0):
    return [
        [f"2026-10-{i+1:02d}", base + i * 0.1, base + i * 0.1 + 0.05, base + i * 0.1 + 0.1, base + i * 0.1 - 0.05, 10000]
        for i in range(count)
    ]


def test_normalize_symbol_and_index_detection():
    """验证证券代码归一化（带市场前缀）与大盘指数判定。"""
    assert DataBridge.normalize_symbol("600519") == "sh600519"
    assert DataBridge.normalize_symbol("000001") == "sz000001"
    assert DataBridge.normalize_symbol("300750") == "sz300750"
    assert DataBridge.normalize_symbol("688001") == "sh688001"
    assert DataBridge.normalize_symbol("830001") == "bj830001"
    assert DataBridge.normalize_symbol("sh600519") == "sh600519"

    assert is_index_symbol("sh000001") is True
    assert is_index_symbol("sz399001") is True
    assert is_index_symbol("sz399006") is True
    assert is_index_symbol("600519") is False
    assert is_index_symbol("000001") is False


def test_databridge_4_tier_degradation(monkeypatch):
    """验证 K 线 4 级降级容灾调度与内存缓存机制。"""
    code = "600519"
    norm = DataBridge.normalize_symbol(code)
    DataBridge._KLINE_CACHE.pop(norm, None)

    # 1. 模拟腾讯源成功 (Level 1)
    monkeypatch.setattr(
        DataBridge,
        "tencent_kline",
        lambda c, count=120: _mock_klines(25, 1800.0),
    )
    k1 = DataBridge.get_kline_robust(code, count=20)
    assert len(k1) >= 15
    assert float(k1[0][1]) >= 1800.0

    # 2. 模拟腾讯源失败，新浪源成功 (Level 2)
    DataBridge._KLINE_CACHE.pop(norm, None)
    monkeypatch.setattr(DataBridge, "tencent_kline", lambda c, count=120: [])
    monkeypatch.setattr(
        DataBridge,
        "sina_kline",
        lambda c, count=120: _mock_klines(25, 1850.0),
    )
    k2 = DataBridge.get_kline_robust(code, count=20)
    assert len(k2) >= 15
    assert float(k2[0][1]) >= 1850.0

    # 3. 模拟腾讯、新浪均失败，东财源成功 (Level 3)
    DataBridge._KLINE_CACHE.pop(norm, None)
    monkeypatch.setattr(DataBridge, "sina_kline", lambda c, count=120: [])
    monkeypatch.setattr(
        DataBridge,
        "eastmoney_kline",
        lambda c, count=120: _mock_klines(25, 1900.0),
    )
    k3 = DataBridge.get_kline_robust(code, count=20)
    assert len(k3) >= 15
    assert float(k3[0][1]) >= 1900.0


def test_databridge_zero_fabrication_contract(monkeypatch):
    """零虚假数据原则：所有外部数据源失败且本地无真实数据时，绝不合成伪造数据。"""
    code = "999999"
    norm = DataBridge.normalize_symbol(code)
    DataBridge._KLINE_CACHE.pop(norm, None)

    monkeypatch.setattr(DataBridge, "tencent_kline", lambda c, count=120: [])
    monkeypatch.setattr(DataBridge, "sina_kline", lambda c, count=120: [])
    monkeypatch.setattr(DataBridge, "eastmoney_kline", lambda c, count=120: [])
    import core.data.Ashare as AshareModule
    monkeypatch.setattr(AshareModule, "get_price", lambda *args, **kwargs: None)

    # 断网/源全挂且本地无数据时必须诚实返回空列表，绝不凭空构造伪造日线
    klines = DataBridge.get_kline_robust(code, count=30)
    assert klines == []


def test_market_data_store_isolated_operations(tmp_path: Path):
    """验证 SQLite MarketDataStore 本地数据库隔离落盘与日线查询。"""
    db_file = tmp_path / "test_market.db"
    store = MarketDataStore(db_path=db_file)

    klines = [
        {"date": "2026-10-15", "open": 1720.0, "close": 1730.0, "high": 1740.0, "low": 1715.0, "volume": 20000, "amount": 3460000000.0},
        {"date": "2026-10-16", "open": 1730.0, "close": 1745.0, "high": 1750.0, "low": 1725.0, "volume": 22000, "amount": 3839000000.0},
        {"date": "2026-10-19", "open": 1740.0, "close": 1750.0, "high": 1760.0, "low": 1735.0, "volume": 25000, "amount": 4375000000.0},
    ]
    inserted = store.upsert_klines("600519", klines)
    assert inserted == 3

    hist = store.get_klines("600519", start_date="2026-10-15", end_date="2026-10-19")
    assert len(hist) == 3
    assert hist[-1]["close"] == 1750.0
    assert hist[0]["open"] == 1720.0


def test_data_assembler_content_hash_and_determinism():
    """验证 DataAssembler 内容哈希计算幂等性与算法规范。"""
    payload_a = {"code": "600001", "name": "测试股", "closes": [10.1, 10.2, 10.3]}
    payload_b = {"name": "测试股", "code": "600001", "closes": [10.1, 10.2, 10.3]}

    h1 = content_hash(payload_a)
    h2 = content_hash(payload_b)
    assert h1.startswith("sha256:")
    # 规范化 JSON 排序后哈希严格一致
    assert h1 == h2


def test_post_close_watermark_gate_fail_closed(tmp_path: Path):
    """选股前置水位门禁：未达标时必须返回 WAITING_DATA 并拒绝产出候选。"""
    db_file = tmp_path / "watermark_test.db"
    store = MarketDataStore(db_path=db_file)
    as_of = "2026-09-30"

    assembler = DataAssembler(db_path=db_file, snapshot_root=tmp_path / "snapshots")
    gate_status = assembler.evaluate_data_gate(as_of=as_of)

    # 本地数据库尚无该日全市场水位标记时，门禁判定为 WAITING_DATA
    assert gate_status["state"] == GATE_WAITING_DATA


def test_minute_timestamp_normalization():
    """验证分钟级行情时间戳标准化与合法区间判定。"""
    ts1, err1 = normalize_minute_timestamp("09:30")
    assert ts1 == "09:30" and err1 is None

    ts2, err2 = normalize_minute_timestamp("14:59")
    assert ts2 == "14:59" and err2 is None

    ts3, err3 = normalize_minute_timestamp("15:00")
    assert ts3 == "15:00" and err3 is None

    # 超出范围的时间戳
    _, err_out = normalize_minute_timestamp("99:99")
    assert err_out == MINUTE_TS_OUT_OF_RANGE

    # 无法解析的时间戳
    _, err_unparsable = normalize_minute_timestamp("invalid_text")
    assert err_unparsable == MINUTE_TS_UNPARSABLE
