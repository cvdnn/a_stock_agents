# -*- coding: utf-8 -*-
"""数据集登记册同步管线测试：假 akshare 渠道 + 临时库，验证落盘、稽核与覆盖表联动。"""
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

    def stock_info_sh_name_code(symbol="1"):
        return pd.DataFrame([{"证券代码": "600519", "证券简称": "贵州茅台", "上市日期": "2001-08-27"}])

    def stock_info_sz_name_code(symbol="A股列表"):
        return pd.DataFrame([{"代码": "000001", "简称": "平安银行", "上市日期": "1991-04-03"}])

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
    assert res["rows"] == 2
    entries = {e["key"]: e for e in build_dataset_coverage(None, None, db)}
    assert entries["base_calendar"]["connected"] is True
    assert entries["base_calendar"]["scope"] == "交易所列表 2 只"


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
