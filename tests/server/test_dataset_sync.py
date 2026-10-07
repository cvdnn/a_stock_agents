# -*- coding: utf-8 -*-
"""数据集登记册同步管线测试：假 akshare 渠道 + 临时库，验证落盘、稽核与覆盖表联动。"""
import sqlite3
import sys
import types
from datetime import datetime

import pandas as pd
import pytest


@pytest.fixture()
def fake_akshare(monkeypatch):
    stub = types.ModuleType("akshare")

    def stock_individual_info_em(symbol):
        return pd.DataFrame([{"item": "行业", "value": "白酒"}, {"item": "上市时间", "value": "20010827"}])

    def index_stock_cons_weight_csindex(symbol):
        return pd.DataFrame([{"成分券代码": "600519", "成分券名称": "贵州茅台", "权重": 3.5}])

    #: akshare 1.18.x 上交所接口按中文键查表，传内部代码 "1" 直接 KeyError（回归护栏）
    sh_indicator_map = {"主板A股": "1", "主板B股": "2", "科创板": "8"}

    def stock_info_sh_name_code(symbol="主板A股"):
        indicator = sh_indicator_map[symbol]
        if indicator == "1":
            return pd.DataFrame([{"证券代码": "600519", "证券简称": "贵州茅台", "上市日期": "2001-08-27"}])
        if indicator == "8":
            return pd.DataFrame([{"证券代码": "688001", "证券简称": "华兴源创", "上市日期": "2019-07-22"}])
        return pd.DataFrame([])

    def stock_info_sz_name_code(symbol="A股列表"):
        # 深交所真实列名为 A股代码/A股简称/A股上市日期（旧桩用"代码/简称"掩盖了整表静默丢弃）
        return pd.DataFrame([{"板块": "主板", "A股代码": "000001", "A股简称": "平安银行",
                              "A股上市日期": "1991-04-03", "所属行业": "J 金融业"}])

    def stock_info_bj_name_code():
        return pd.DataFrame([])

    def stock_zh_a_daily(symbol, start_date=None, end_date=None, adjust=""):
        assert adjust == "qfq-factor"
        return pd.DataFrame([{"date": "2026-09-29", "factor": 12.3}])

    def stock_dividend_cninfo(symbol):
        return pd.DataFrame([{"除权除息日": "2026-06-19", "每股派息(元)": 2.5}])

    def stock_financial_analysis_indicator(symbol, start_year="2023"):
        return pd.DataFrame([{"日期": "2025-12-31", "净利润(元)": 100.0, "净资产收益率(%)": 20.0}])

    stub.stock_individual_info_em = stock_individual_info_em
    stub.index_stock_cons_weight_csindex = index_stock_cons_weight_csindex
    stub.stock_info_sh_name_code = stock_info_sh_name_code
    stub.stock_info_sz_name_code = stock_info_sz_name_code
    stub.stock_info_bj_name_code = stock_info_bj_name_code
    stub.stock_zh_a_daily = stock_zh_a_daily
    stub.stock_dividend_cninfo = stock_dividend_cninfo
    stub.stock_financial_analysis_indicator = stock_financial_analysis_indicator
    monkeypatch.setitem(sys.modules, "akshare", stub)
    return stub


@pytest.fixture()
def registered(monkeypatch):
    from core.data import dataset_sync

    monkeypatch.setattr(dataset_sync, "_resolve_registered", lambda: ["sh600519"])
    return ["sh600519"]


def test_industry_sync_writes_snapshot_and_flips_coverage(tmp_path, fake_akshare, registered):
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore
    from server.services.data_sync_overview import build_dataset_coverage

    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("industry", symbols=["600519"], db_path=db)
    assert res["status"] == "ok"
    assert res["rows"] == 1

    entries = {e["key"]: e for e in build_dataset_coverage(None, None, db)}
    industry = entries["industry"]
    assert industry["connected"] is True
    assert industry["scope"] == "已登记范围 1 只"
    assert industry["completeness"]["state"] == "complete"


def test_index_members_sync_skips_unsupported_indices_explicitly(tmp_path, fake_akshare):
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore

    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("index_members", db_path=db)
    assert res["rows"] == 1
    assert any("源不支持" in item for item in res["failed"])


def test_stock_basic_sync_and_coverage(tmp_path, fake_akshare, registered):
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore
    from server.services.data_sync_overview import build_dataset_coverage

    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("base_calendar", db_path=db)
    assert res["rows"] == 3  # 沪主板 600519 + 科创板 688001 + 深 A 000001
    assert not any(item.startswith("sh:") for item in res["failed"]), res["failed"]
    entries = {e["key"]: e for e in build_dataset_coverage(None, None, db)}
    assert entries["base_calendar"]["connected"] is True
    assert entries["base_calendar"]["scope"] == "交易所列表 3 只"


def test_adjust_factor_and_dividend_pipeline(tmp_path, fake_akshare, registered):
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore

    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("adjust_factor", db_path=db)
    assert res["rows"] == 2  # 因子 1 行 + 分红 1 行
    assert res["audit"]["state"] == "complete"


def test_run_due_datasets_respects_window(tmp_path, fake_akshare, registered, monkeypatch):
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore

    monkeypatch.setattr(
        dataset_sync, "sync_capital",
        lambda symbols=None, db_path=None: dataset_sync._result("valuation", "ok", 1, "stub"),
    )
    monkeypatch.setattr(
        dataset_sync, "sync_capital_flow",
        lambda symbols=None, db_path=None: dataset_sync._result("capital_flow", "degraded", 1, "stub"),
    )
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    morning = datetime(2026, 10, 9, 10, 0)  # 周五交易日，早于全部窗口
    assert dataset_sync.run_due_datasets(morning, {}, db_path=db) == []
    evening = datetime(2026, 10, 9, 17, 0)
    executed: dict = {}
    results = dataset_sync.run_due_datasets(evening, executed, db_path=db)
    assert {r["key"] for r in results} == set(dataset_sync.DATASET_WINDOWS)
    assert dataset_sync.run_due_datasets(evening, executed, db_path=db) == []  # 每日一次
@pytest.fixture()
def holiday_clock(monkeypatch):
    """把时钟钉在国庆休市：裸日历日 2026-10-07，最近交易日 2026-09-30。"""
    from core.data import dataset_sync

    monkeypatch.setattr(dataset_sync, "_today", lambda: "2026-10-07")
    monkeypatch.setattr(
        dataset_sync.TradeCalendar, "last_trading_day",
        staticmethod(lambda d=None, db_path=None, max_lookback=30: "2026-09-30"),
    )
    return "2026-09-30"


def _patch_snapshot(monkeypatch, quotes):
    from core.data import dataset_sync

    monkeypatch.setattr(
        dataset_sync.DataBridge, "fetch_batch_snapshot",
        lambda self, codes: [q for q in quotes if q["code"] in list(codes)],
    )


def test_stock_basic_reports_column_drift_instead_of_silent_zero(tmp_path, fake_akshare, registered, monkeypatch):
    """源列名漂移导致整表被过滤时必须记失败，不得静默按 0 覆盖放行。"""
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore

    monkeypatch.setattr(
        fake_akshare, "stock_info_sz_name_code",
        lambda symbol="A股列表": pd.DataFrame([{"renamed_code": "000001", "renamed_name": "平安银行"}]),
    )
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("base_calendar", db_path=db)
    assert res["status"] == "degraded"
    assert any("列名不匹配" in item for item in res["failed"]), res["failed"]


def test_base_calendar_universe_excludes_indices(tmp_path, fake_akshare, monkeypatch):
    """D1 分母只算个股：指数无证券简称/上市日期，计入会让 post_close 门控永久 degraded。"""
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore

    monkeypatch.setattr(
        dataset_sync, "_resolve_registered",
        lambda: ["sh000001", "sh000300", "sh600519", "sz000858"],
    )
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    wm = dataset_sync.run_dataset("base_calendar", db_path=db)["audit"]
    assert wm["universe_total"] == 2          # 剔除 sh000001/sh000300 两个指数
    assert wm["covered"] == 1                 # 仅 sh600519 在假交易所列表内
    assert wm["availability"] == "degraded"   # 真缺的个股仍然拦住门控
    assert "已剔除指数" in wm["note"]


def test_capital_flow_proxy_rows_are_dated_by_trading_calendar(tmp_path, fake_akshare, registered, monkeypatch, holiday_clock):
    """代理档行级 date 必须与水位 batch_date 同口径，节假日不得盖裸日历日。"""
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore

    _patch_snapshot(monkeypatch, [{"code": "sh600519", "price": 1500.0, "amount": 4.8e9,
                                   "outer": 12000, "inner": 9000, "volume_hands": 21000}])
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("capital_flow", symbols=["sh600519"], db_path=db)
    with sqlite3.connect(str(db)) as conn:
        dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM capital_flow_daily")]
        net = conn.execute("SELECT main_net_inflow FROM capital_flow_daily").fetchone()[0]
    assert dates == [holiday_clock]
    assert res["audit"]["trade_date"] == holiday_clock
    assert net > 0  # 外盘 > 内盘，代理档给出真实推导值


def test_capital_flow_proxy_refuses_zero_net_inflow_without_evidence(tmp_path, fake_akshare, registered, monkeypatch, holiday_clock):
    """内外盘双零（指数/休市快照）= 无证据，写 0.0 等于伪造"主力净流入为零"的实测值。"""
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore

    _patch_snapshot(monkeypatch, [{"code": "sh000300", "price": 4100.0, "amount": 3.5e11,
                                   "outer": 0, "inner": 0, "volume_hands": 0}])
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    dataset_sync.run_dataset("capital_flow", symbols=["sh000300"], db_path=db)
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute("SELECT main_net_inflow, amount FROM capital_flow_daily").fetchone()
    assert row[0] is None
    assert row[1] == 3.5e11  # 成交额为源侧实测值，照常保留


def test_valuation_snapshot_rows_share_watermark_batch_date(tmp_path, fake_akshare, registered, monkeypatch, holiday_clock):
    """估值快照行级 date 与水位 batch_date 必须一致，否则按水位日期回查命中 0 行。"""
    from core.data import dataset_sync
    from core.data.sync_engine import MarketDataStore

    _patch_snapshot(monkeypatch, [{"code": "sh600519", "price": 1500.0,
                                   "total_market_cap": 18800.0, "circulating_market_cap": 18800.0}])
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("valuation", symbols=["sh600519"], db_path=db)
    with sqlite3.connect(str(db)) as conn:
        dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM capital_snapshot")]
    assert dates == [holiday_clock]
    assert res["audit"]["trade_date"] == holiday_clock
