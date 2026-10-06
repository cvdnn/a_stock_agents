# -*- coding: utf-8 -*-
"""漏斗模型示例数据同步回归测试（SPEC-DATA §5.1 D3/D7/D9/D10/D11/D12 + §5.4/§5.5）。

覆盖裁定级回归保护：
- W-09 流通市值入库单位统一为元（亿元源值一次性 ×1e8，source 标记换算口径）；
- W-10 缺失禁置零（0 ≠ 缺失；分母为请求标的数，缺失计入 missing）；
- W-07 资金流代理档恒 degraded，100% 覆盖也不得判 finalized；
- §5.5 UniverseWatermark 写入/读取与 post_close 门控判定；
- 盘中前向采集归档器 append-only 去重、竞价切片与封存水位。
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from core.data import dataset_sync
from core.data.sync_engine import MarketDataStore

# ---------------------------------------------------------------- 测试用行情快照桩
#: 腾讯快照原值口径：市值亿元 / amount 元 / 内外盘与量为手（键为 6 位数字代码）
QUOTES = {
    "600519": {
        "code": "sh600519", "name": "贵州茅台", "price": 1600.0, "prev_close": 1580.0,
        "total_market_cap": 20000.0, "circulating_market_cap": 16000.0,
        "amount": 5.0e9, "volume_hands": 50000, "outer": 30000, "inner": 20000,
        "pe": 25.0, "turnover_pct": 0.5,
    },
    "600000": {  # 市值缺失（quote 层折算为 0）：W-10 须判缺失而非放行
        "code": "sh600000", "name": "浦发银行", "price": 8.0, "prev_close": 8.0,
        "total_market_cap": 0, "circulating_market_cap": 0,
        "amount": 1.0e8, "volume_hands": 20000, "outer": 10000, "inner": 9000,
        "pe": None, "turnover_pct": 0.1,
    },
}


@pytest.fixture()
def bridge_stub(monkeypatch):
    from core.data.data_bridge import DataBridge as _RealBridge

    class StubBridge:
        # dataset_sync._norm 借用 DataBridge.normalize_symbol 做代码规范化，保留真实实现
        normalize_symbol = _RealBridge.normalize_symbol

        def __init__(self):
            pass

        def fetch_batch_snapshot(self, codes):
            out = []
            for c in codes:
                q = QUOTES.get(str(c)[-6:])
                if q:
                    out.append(dict(q))
            return out

    monkeypatch.setattr(dataset_sync, "DataBridge", StubBridge)
    return StubBridge


def _read_row(db_path, table, symbol, date=None):
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if date:
            row = conn.execute(f"SELECT * FROM {table} WHERE symbol=? AND date=?", (symbol, date)).fetchone()
        else:
            row = conn.execute(f"SELECT * FROM {table} WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------- W-09 单位口径
def test_capital_snapshot_persisted_in_yuan(tmp_path, bridge_stub):
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("valuation", symbols=["600519"], db_path=db)

    row = _read_row(db, "capital_snapshot", "sh600519")
    assert row is not None
    # 亿元源值 → 入库元（一次性 ×1e8）
    assert row["total_market_cap"] == pytest.approx(20000.0 * 1e8)
    assert row["float_market_cap"] == pytest.approx(16000.0 * 1e8)
    assert row["source"] == "tencent_snapshot_derived_yuan"
    # 股本 = 市值(元) ÷ 现价
    assert row["total_shares"] == pytest.approx(20000.0 * 1e8 / 1600.0)
    assert res["status"] == "ok"


# ---------------------------------------------------------------- W-10 缺失禁置零
def test_capital_missing_market_cap_counts_as_missing(tmp_path, bridge_stub):
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("valuation", symbols=["600519", "600000"], db_path=db)

    # 缺失标的不入库、不置零，计入 watermark missing
    assert _read_row(db, "capital_snapshot", "sh600000") is None
    wm = dataset_sync.get_universe_watermark(["valuation"], db_path=db)["valuation"]
    assert wm["universe_total"] == 2
    assert wm["covered"] == 1
    assert wm["status"] == "degraded"
    assert "float_market_cap" in wm["blocking_fields"]
    assert res["status"] == "degraded"


def test_fundamentals_missing_fields_return_none_not_zero():
    """W-10：get_fundamentals 缺失字段返回 None + blocking_fields，禁止以 0 参与比较。"""
    from core.data.data_bridge import DataBridge

    quote = {"code": "600000", "pe": None, "circulating_market_cap": 0,
             "total_market_cap": 0, "turnover_pct": 0.1}
    with patch.object(DataBridge, "get_realtime_quote", return_value=quote):
        res = DataBridge().get_fundamentals("600000")
    assert res["pe"] is None
    assert res["circulating_market_cap"] is None
    assert res["total_market_cap"] is None
    assert set(res["blocking_fields"]) >= {"pe", "circulating_market_cap", "total_market_cap"}

    with patch.object(DataBridge, "get_realtime_quote", return_value=None):
        res2 = DataBridge().get_fundamentals("600000")
    assert res2["source"] == "L1_unavailable"
    assert res2["circulating_market_cap"] is None
    assert "turnover_pct" in res2["blocking_fields"]


def test_fundamentals_invalid_code_returns_all_none():
    from core.data.data_bridge import DataBridge

    res = DataBridge().get_fundamentals("")
    assert res["source"] == "invalid_code"
    assert res["circulating_market_cap"] is None
    assert len(res["blocking_fields"]) == 4


# ---------------------------------------------------------------- D10 资金流：精算档与代理档
def _no_akshare(monkeypatch):
    """模拟 akshare 不可用（精算档缺席 → 全部落腾讯代理档兜底）。"""
    monkeypatch.setattr(dataset_sync, "_ak", lambda: None)


def test_capital_flow_exact_tier_eastmoney(tmp_path, monkeypatch, bridge_stub):
    """D10 精算档（eastmoney_exact）：东财列一一映射、amount 反推、水印 finalized。"""
    import types

    import pandas as pd

    stub = types.ModuleType("akshare")

    def stock_individual_fund_flow(stock, market):
        assert market == "sh"
        return pd.DataFrame([
            {"日期": "2026-09-30", "收盘价": 1258.62, "涨跌幅": 1.86,
             "主力净流入-净额": 533565520.0, "主力净流入-净占比": 11.12,
             "超大单净流入-净额": 412137616.0, "大单净流入-净额": 121427904.0},
            {"日期": "2026-09-29", "收盘价": 1235.58, "涨跌幅": -0.67,
             "主力净流入-净额": 324185776.0, "主力净流入-净占比": 9.94,
             "超大单净流入-净额": 309318064.0, "大单净流入-净额": 14867712.0},
        ])

    stub.stock_individual_fund_flow = stock_individual_fund_flow
    monkeypatch.setitem(sys.modules, "akshare", stub)

    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("capital_flow", symbols=["600519"], db_path=db)

    row = _read_row(db, "capital_flow_daily", "sh600519", "2026-09-30")
    assert row is not None
    assert row["main_net_inflow"] == pytest.approx(533565520.0)
    assert row["super_large_net_inflow"] == pytest.approx(412137616.0)
    assert row["large_net_inflow"] == pytest.approx(121427904.0)
    # amount 反推：净额 ÷ 净占比 × 100
    assert row["amount"] == pytest.approx(533565520.0 / 11.12 * 100)
    assert row["flow_source"] == "eastmoney_exact"
    assert res["status"] == "ok"

    # 全部标的取得精算档 → 水印 finalized（W-07：可启用 main_fund_inflow 的前提）
    wm = dataset_sync.get_universe_watermark(["capital_flow"], db_path=db)["capital_flow"]
    assert wm["covered"] == 1 and wm["universe_total"] == 1
    assert wm["status"] == "finalized"
    assert dataset_sync.read_capital_flow(["sh600519"], db_path=db)[0]["availability"] == "finalized"


def test_capital_flow_proxy_fallback_when_exact_fails(tmp_path, monkeypatch, bridge_stub):
    """精算档失败/缺席 → 腾讯代理档兜底，水印 degraded（W-07：代理档不得进正式规则）。"""
    import types

    import pandas as pd

    stub = types.ModuleType("akshare")

    def stock_individual_fund_flow(stock, market):
        if stock == "600000":
            raise RuntimeError("eastmoney down")  # 600000 精算失败 → 走代理兜底
        return pd.DataFrame([
            {"日期": "2026-09-30", "主力净流入-净额": 100.0, "主力净流入-净占比": 1.0,
             "超大单净流入-净额": 60.0, "大单净流入-净额": 40.0},
        ])

    stub.stock_individual_fund_flow = stock_individual_fund_flow
    monkeypatch.setitem(sys.modules, "akshare", stub)

    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("capital_flow", symbols=["600519", "600000"], db_path=db)

    # 600519 精算档、600000 代理档共存一表，以 flow_source 区分
    exact_row = _read_row(db, "capital_flow_daily", "sh600519", "2026-09-30")
    proxy_row = _read_row(db, "capital_flow_daily", "sh600000")
    assert exact_row["flow_source"] == "eastmoney_exact"
    assert proxy_row["flow_source"] == "tencent_proxy"
    # 代理档口径：(外盘-内盘)×100×VWAP；VWAP = 1e8 / (20000×100) = 50
    assert proxy_row["main_net_inflow"] == pytest.approx((10000 - 9000) * 100 * 50.0)

    wm = dataset_sync.get_universe_watermark(["capital_flow"], db_path=db)["capital_flow"]
    assert wm["covered"] == 1 and wm["universe_total"] == 2
    assert wm["status"] == "degraded"
    assert "main_net_inflow" in wm["blocking_fields"]
    assert res["status"] == "degraded"


def test_capital_flow_proxy_tier_without_akshare(tmp_path, monkeypatch, bridge_stub):
    """akshare 不可用 → 纯代理档，水印恒 degraded（排序因子与观察运行专用）。"""
    _no_akshare(monkeypatch)
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    res = dataset_sync.run_dataset("capital_flow", symbols=["600519"], db_path=db)

    row = _read_row(db, "capital_flow_daily", "sh600519")
    assert row is not None
    # (外盘-内盘)手 × 100股/手 × VWAP(元/股)；VWAP = 5e9 / (50000×100) = 1000
    assert row["main_net_inflow"] == pytest.approx((30000 - 20000) * 100 * 1000.0)
    assert row["flow_source"] == "tencent_proxy"
    assert row["amount"] == pytest.approx(5.0e9)

    wm = dataset_sync.get_universe_watermark(["capital_flow"], db_path=db)["capital_flow"]
    assert wm["covered"] == 0 and wm["universe_total"] == 1
    assert wm["status"] == "degraded"
    assert "代理兜底" in wm["note"]

    rows = dataset_sync.read_capital_flow(["sh600519"], db_path=db)
    assert rows and rows[0]["availability"] == "degraded"


# ---------------------------------------------------------------- §5.5 水位与门控
def test_post_close_watermark_gate(tmp_path):
    db = tmp_path / "astock_data.db"
    store = MarketDataStore(db)

    # 三键全部 finalized + 100% → ready
    for key in dataset_sync.POST_CLOSE_WATERMARK_KEYS:
        dataset_sync.write_universe_watermark(store, key, 5, 5, availability="finalized")
    res = dataset_sync.check_post_close_ready(db_path=db)
    assert res["ready"] is True
    assert res["missing"] == [] and res["not_finalized"] == []

    # 一键 degraded → not ready 且显式列出
    dataset_sync.write_universe_watermark(store, "valuation", 3, 5, availability="degraded",
                                          blocking_fields=["float_market_cap"])
    res2 = dataset_sync.check_post_close_ready(db_path=db)
    assert res2["ready"] is False
    assert res2["not_finalized"] == ["valuation"]

    # 无批次键 → missing
    res3 = dataset_sync.check_post_close_ready(
        db_path=db, required_keys=(*dataset_sync.POST_CLOSE_WATERMARK_KEYS, "capital_flow")
    )
    assert res3["ready"] is False
    assert res3["missing"] == ["capital_flow"]


def test_daily_kline_watermark_counts_settled_rows_only(tmp_path, monkeypatch):
    db = tmp_path / "astock_data.db"
    store = MarketDataStore(db)
    monkeypatch.setattr(dataset_sync, "_resolve_registered", lambda: ["sh600519", "sz000001"])

    # 一只已定盘、一只缺当日行 → degraded
    store.upsert_klines("sh600519", [{
        "date": "2026-10-09", "open": 1600, "close": 1610, "high": 1620, "low": 1590, "volume": 10000,
    }])
    res = dataset_sync.sync_daily_kline_watermark(trade_date="2026-10-09", db_path=db)
    wm = dataset_sync.get_universe_watermark(["daily_kline"], trade_date="2026-10-09", db_path=db)["daily_kline"]
    assert wm["covered"] == 1 and wm["universe_total"] == 2
    assert wm["status"] == "degraded"
    assert res["status"] == "degraded"

    # 补齐第二只（定盘）→ finalized
    store.upsert_klines("sz000001", [{
        "date": "2026-10-09", "open": 10, "close": 10.2, "high": 10.3, "low": 9.9, "volume": 5000,
    }])
    dataset_sync.sync_daily_kline_watermark(trade_date="2026-10-09", db_path=db)
    wm2 = dataset_sync.get_universe_watermark(["daily_kline"], trade_date="2026-10-09", db_path=db)["daily_kline"]
    assert wm2["status"] == "finalized"


# ---------------------------------------------------------------- D3 深度校验（W-04）
def _fake_akshare_min_kline(monkeypatch, bars_by_call):
    """注入假 akshare 分钟源：bars_by_call 为返回 DataFrame 的函数。"""
    import types

    import pandas as pd

    stub = types.ModuleType("akshare")

    def stock_zh_a_hist_min_em(symbol, period="", adjust=""):
        return pd.DataFrame(bars_by_call(symbol, period))

    stub.stock_zh_a_hist_min_em = stock_zh_a_hist_min_em
    monkeypatch.setitem(sys.modules, "akshare", stub)
    return stub


def test_minute_kline_depth_guard_marks_shallow_history(tmp_path, monkeypatch):
    """W-04 假水位防护：源深度不足时水位判 degraded，不得以片段冒充完整覆盖。"""
    from datetime import date as _date

    db = tmp_path / "astock_data.db"
    MarketDataStore(db)

    today = _date.today().isoformat()
    # 场景 1：仅回补到近 2 日 → 深度不足（1m 保留深度 30 交易日）
    _fake_akshare_min_kline(
        monkeypatch,
        lambda symbol, period: [
            {"时间": f"{today} 09:31:00", "开盘": 10.0, "收盘": 10.1, "最高": 10.2, "最低": 9.9,
             "成交量": 100, "成交额": 1000.0},
        ],
    )
    res = dataset_sync.sync_minute_kline(["600519"], freqs=("1",), db_path=db)
    assert res["status"] == "degraded"
    wm = dataset_sync.get_universe_watermark(["minute_kline"], db_path=db)["minute_kline"]
    assert wm["covered"] == 0 and wm["universe_total"] == 1
    assert wm["status"] == "degraded"
    assert "minute_kline.depth" in wm["blocking_fields"]
    assert "深度不足" in wm["note"]

    # 场景 2：最老 bar 恰落在期望深度起点 → 水位 finalized
    exp = dataset_sync._expected_min_date("1", _date.today())
    assert exp is not None  # 规则日历 2024–2027 覆盖测试日期区间
    _fake_akshare_min_kline(
        monkeypatch,
        lambda symbol, period: [
            {"时间": f"{exp} 09:31:00", "开盘": 10.0, "收盘": 10.1, "最高": 10.2, "最低": 9.9,
             "成交量": 100, "成交额": 1000.0},
            {"时间": f"{today} 14:55:00", "开盘": 10.1, "收盘": 10.0, "最高": 10.2, "最低": 9.9,
             "成交量": 80, "成交额": 800.0},
        ],
    )
    res2 = dataset_sync.sync_minute_kline(["600519"], freqs=("1",), db_path=db)
    assert res2["status"] == "ok"
    wm2 = dataset_sync.get_universe_watermark(["minute_kline"], db_path=db)["minute_kline"]
    assert wm2["status"] == "finalized"
    assert "minute_kline.depth" not in wm2["blocking_fields"]


# ---------------------------------------------------------------- 盘中前向采集归档器
_ORDER_BOOK = {"bids": [{"price": 1687.0, "volume": 12}], "asks": [{"price": 1688.0, "volume": 10}],
               "bid_volume": 12, "ask_volume": 10}


def _make_archiver(tmp_path, db, now=None):
    from core.data.intraday_archiver import IntradayArchiver

    minute_bars = [
        {"ts": "2026-10-09 09:31", "open": 1600.0, "close": 1601.0, "high": 1602.0, "low": 1599.0, "volume": 1000},
        {"ts": "2026-10-09 09:32", "open": 1601.0, "close": 1602.0, "high": 1603.0, "low": 1600.0, "volume": 1200},
    ]
    ticks = [
        {"seq": 1, "time": "09:31:05", "price": 1600.5, "volume": 10, "amount": 16005.0, "direction": "B"},
        {"seq": 2, "time": "09:31:20", "price": 1601.0, "volume": 5, "amount": 8005.0, "direction": "S"},
    ]

    archiver = IntradayArchiver(
        symbols=["sh600519"],
        out_root=tmp_path / "intraday",
        db_path=db,
        snapshot_fetcher=lambda codes: [{**QUOTES["600519"], "order_book": _ORDER_BOOK}],
        minute_fetcher=lambda code: list(minute_bars),
        tick_fetcher=lambda code: list(ticks),
    )
    if now:
        archiver._now = lambda: now  # 时钟注入
    return archiver


def test_intraday_archiver_append_only_and_dedup(tmp_path):
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    archiver = _make_archiver(tmp_path, db, now=datetime(2026, 10, 9, 10, 0, 0))

    counts1 = archiver.run_cycle()
    assert counts1["snapshot"] == 1
    assert counts1["minute"] == 2
    assert counts1["tick"] == 2

    # 第二轮：相同数据不重复追加（ts/seq 水位去重；未到分钟周期时键缺席）
    counts2 = archiver.run_cycle()
    assert counts2.get("minute", 0) == 0
    assert counts2.get("tick", 0) == 0
    assert counts2["snapshot"] == 1  # 快照为时间戳流，允许重复采样

    minute_path = tmp_path / "intraday" / "minute_1m.jsonl"
    lines = minute_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["symbol"] == "sh600519" and rec["ts"] == "2026-10-09 09:31"

    # tick 切片 direction 保留源侧推断口径
    tick_rec = json.loads((tmp_path / "intraday" / "tick.jsonl").read_text(encoding="utf-8").strip().splitlines()[0])
    assert tick_rec["direction"] in ("B", "S", "M")

    # T-09: 快照切片透传五档 order_book（B2 委买卖比可直接计算）
    snap_rec = json.loads((tmp_path / "intraday" / "snapshot.jsonl").read_text(encoding="utf-8").strip().splitlines()[0])
    assert snap_rec["order_book"]["bid_volume"] == 12
    assert snap_rec["order_book"]["ask_volume"] == 10


def test_intraday_archiver_auction_slice_and_seal(tmp_path):
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    # 09:20 处于 D12 竞价窗口：快照切片同时落 auction.jsonl；分钟/分笔未开盘不触发
    archiver = _make_archiver(tmp_path, db, now=datetime(2026, 10, 9, 9, 20, 0))
    counts = archiver.run_cycle()
    assert counts.get("minute", 0) == 0
    auction_path = tmp_path / "intraday" / "auction.jsonl"
    rec = json.loads(auction_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert rec["phase"] == "auction"
    # T-09 已落地：竞价切片透传五档；缺失时为 None，消费方判 UNKNOWN
    assert rec["order_book"] is not None and rec["order_book"]["ask_volume"] == 10

    manifest = archiver.seal()
    assert manifest["sealed"] is True
    assert manifest["watermark"]["covered"] == 1
    assert manifest["watermark"]["availability"] == "finalized"
    # 封存水位写入 dataset_audit（§5.5），不翻正控制台接入状态
    wm = dataset_sync.get_universe_watermark(["intraday_snapshot"], db_path=db)["intraday_snapshot"]
    assert wm is not None and wm["status"] == "finalized"


def test_intraday_archiver_records_failures_explicitly(tmp_path):
    db = tmp_path / "astock_data.db"
    MarketDataStore(db)
    from core.data.intraday_archiver import IntradayArchiver

    def boom(codes):
        raise RuntimeError("network down")

    archiver = IntradayArchiver(
        symbols=["sh600519"], out_root=tmp_path / "intraday", db_path=db,
        snapshot_fetcher=boom, minute_fetcher=boom, tick_fetcher=boom,
    )
    archiver.run_cycle()
    assert archiver.manifest["errors"]
    assert any(e.startswith("snapshot:") for e in archiver.manifest["errors"])
