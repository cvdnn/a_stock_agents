# -*- coding: utf-8 -*-
"""数据集登记册同步管线 (SPEC-DATA §5)。

- 按 §5.1 已确认外部接口渠道取数并落盘快照表；取数失败返回显式 failed/unavailable，严禁伪造值；
- 调度窗口为 §5.1 固定常量，由守护巡检 (sync_daemon) 与 CLI (`astock data dataset`) 触发；
- 字段规避原则：退市日期、指数成分历史进出、行业变更历史区间一律不入库；
- 同步/稽核范围：除 D1 交易所全量列表与 D5 指数成分、D7 全市场快照外，其余数据集以已登记标的 (P0–P2) 为范围。
"""
from __future__ import annotations

import time
from datetime import date, datetime, time as dt_time
from typing import Any, Dict, Iterable, List, Optional

from core.data.data_bridge import DataBridge
from core.data.sync_engine import DB_PATH, DataSyncEngine, MarketDataStore, TradeCalendar

#: §5.1 固定调度窗口（minute_kline 为按需回补，不设固定窗口）
DATASET_WINDOWS = {
    "base_calendar": dt_time(15, 35),
    "adjust_factor": dt_time(15, 50),
    "index_members": dt_time(16, 10),
    "financial": dt_time(16, 20),
    "valuation": dt_time(16, 30),
    "industry": dt_time(16, 40),
}

#: 中证指数可取成分的指数映射（其余核心指数源不支持，显式记 failed，不伪造）
CSINDEX_MAP = {"sh000300": "000300", "sh000016": "000016", "sh000905": "000905"}

_QUARTER_ENDS = ("03-31", "06-30", "09-30", "12-31")


def _ak():
    try:
        import akshare as ak
        return ak
    except Exception:
        return None


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return date.today().isoformat()


def _norm(symbol: str) -> str:
    return DataBridge.normalize_symbol(str(symbol), with_prefix=True)


def _digits(symbol: str) -> str:
    return str(symbol)[-6:]


def _resolve_registered() -> List[str]:
    """已登记标的 (P0 持仓 + P1 自选/关注 + P2 指数)，与覆盖表口径一致。"""
    from core.strategy.pool_manager import PoolManager

    symbols = set()
    try:
        pm = PoolManager()
        for name in ("holdings", "watchlist", "focus"):
            for item in pm.get_pool(name) or []:
                if isinstance(item, dict):
                    code = item.get("code") or item.get("symbol")
                    if code:
                        symbols.add(_norm(code))
    except Exception:
        pass
    symbols |= {_norm(idx) for idx in DataSyncEngine.DEFAULT_INDICES}
    return sorted(symbols)


def _pick(row: Dict[str, Any], *candidates: str) -> Any:
    for key in candidates:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _records(df) -> List[Dict[str, Any]]:
    if df is None:
        return []
    try:
        if df.empty:
            return []
        return df.to_dict("records")
    except Exception:
        return []


def _result(key: str, status: str, rows: int = 0, source: str = "", failed: Optional[List[str]] = None,
            audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"key": key, "status": status, "rows": rows, "source": source,
            "failed": failed or [], "audit": audit or {}}


def _write_audit(store: MarketDataStore, key: str, audit: Dict[str, Any]) -> None:
    with store._get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dataset_audit (dataset_key, batch_date, covered, total, missing, state, detail, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (key, _today(), audit.get("covered"), audit.get("total"), audit.get("missing"),
             audit.get("state"), audit.get("detail", ""), _stamp()),
        )
        conn.commit()


def _upsert(store: MarketDataStore, sql: str, rows: Iterable[tuple]) -> int:
    payload = [row for row in rows if row]
    if not payload:
        return 0
    with store._get_conn() as conn:
        conn.executemany(sql, payload)
        conn.commit()
    return len(payload)


# ---------------------------------------------------------------- D1 基础资料
def sync_stock_basic(db_path=DB_PATH) -> Dict[str, Any]:
    ak = _ak()
    if ak is None:
        return _result("base_calendar", "unavailable", source="akshare 未安装")
    store = MarketDataStore(db_path)
    rows, failed = [], []
    fetchers = (
        ("sh", lambda: ak.stock_info_sh_name_code(symbol="1")),
        ("sz", lambda: ak.stock_info_sz_name_code(symbol="A股列表")),
        ("bj", lambda: ak.stock_info_bj_name_code()),
    )
    for market, fetch in fetchers:
        try:
            for rec in _records(fetch()):
                code = _pick(rec, "证券代码", "代码", "A股代码")
                name = _pick(rec, "证券简称", "简称", "名称")
                if not code or not name:
                    continue
                rows.append((_norm(code), str(name), market,
                             str(_pick(rec, "上市日期", "上市时间") or "") or None, _stamp()))
        except Exception as exc:
            failed.append(f"{market}:{exc.__class__.__name__}")
    written = _upsert(store, "INSERT OR REPLACE INTO stock_basic (symbol, name, market, list_date, updated_at) VALUES (?, ?, ?, ?, ?)", rows)
    registered = _resolve_registered()
    with store._get_conn() as conn:
        covered = conn.execute(
            f"SELECT COUNT(*) FROM stock_basic WHERE symbol IN ({','.join('?' * len(registered))}) AND name IS NOT NULL AND list_date IS NOT NULL",
            registered,
        ).fetchone()[0] if registered else 0
    missing = max(len(registered) - covered, 0)
    audit = {"covered": covered, "total": len(registered), "missing": missing,
             "state": "complete" if missing == 0 and registered else "missing" if registered else "undetected",
             "detail": f"交易所列表 {written} 只"}
    _write_audit(store, "base_calendar", audit)
    return _result("base_calendar", "ok" if not failed else "degraded", written,
                   "交易所官方列表(akshare)", failed, audit)


# ---------------------------------------------------------------- D3 分钟K线（按需）
def sync_minute_kline(symbols: Iterable[str], freqs: Iterable[str] = ("5", "60"), db_path=DB_PATH) -> Dict[str, Any]:
    ak = _ak()
    if ak is None:
        return _result("minute_kline", "unavailable", source="akshare 未安装")
    store = MarketDataStore(db_path)
    written, failed = 0, []
    for symbol in symbols:
        for freq in freqs:
            try:
                df = ak.stock_zh_a_hist_min_em(symbol=_digits(symbol), period=str(freq), adjust="")
                batch = []
                for rec in _records(df):
                    ts = _pick(rec, "时间", "datetime")
                    open_ = _pick(rec, "开盘", "open")
                    close = _pick(rec, "收盘", "close")
                    if not ts or open_ is None or close is None:
                        continue
                    batch.append((_norm(symbol), str(freq), str(ts), float(open_), float(close),
                                  float(_pick(rec, "最高", "high") or 0.0), float(_pick(rec, "最低", "low") or 0.0),
                                  float(_pick(rec, "成交量", "volume") or 0.0), float(_pick(rec, "成交额", "amount") or 0.0)))
                written += _upsert(store, "INSERT OR REPLACE INTO minute_kline (symbol, freq, ts, open, close, high, low, volume, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
            except Exception as exc:
                failed.append(f"{symbol}/{freq}:{exc.__class__.__name__}")
    audit = {"covered": written, "total": written + len(failed), "missing": len(failed),
             "state": "complete" if not failed and written else "missing" if failed else "undetected",
             "detail": "按需回补批次"}
    _write_audit(store, "minute_kline", audit)
    return _result("minute_kline", "ok" if not failed else "degraded", written, "腾讯 mkline(akshare)", failed, audit)


# ---------------------------------------------------------------- D4 复权因子与分红
def sync_adjust_factor(symbols: Iterable[str], db_path=DB_PATH) -> Dict[str, Any]:
    ak = _ak()
    if ak is None:
        return _result("adjust_factor", "unavailable", source="akshare 未安装")
    store = MarketDataStore(db_path)
    symbols = list(symbols)
    written, failed = 0, []
    for symbol in symbols:
        try:
            df = ak.stock_zh_a_daily(symbol=_norm(symbol), adjust="qfq-factor")
            batch = [(_norm(symbol), str(rec.get("date")), float(rec.get("factor")), _stamp())
                     for rec in _records(df) if rec.get("date") is not None and rec.get("factor") is not None]
            written += _upsert(store, "INSERT OR REPLACE INTO adjust_factor (symbol, date, factor, updated_at) VALUES (?, ?, ?, ?)", batch)
        except Exception as exc:
            failed.append(f"{symbol}:{exc.__class__.__name__}")
        time.sleep(0.5)
    div = sync_dividend_event(symbols, db_path)
    missing = len(failed) + len(div["failed"])
    audit = {"covered": len(symbols) - len(failed), "total": len(symbols), "missing": missing,
             "state": "complete" if missing == 0 and symbols else "missing" if missing else "undetected",
             "detail": f"因子 {written} 行 · 分红 {div['rows']} 行"}
    _write_audit(store, "adjust_factor", audit)
    return _result("adjust_factor", "ok" if not missing else "degraded", written + div["rows"],
                   "新浪 qfq-factor + 巨潮分红(akshare)", failed + div["failed"], audit)


def sync_dividend_event(symbols: Iterable[str], db_path=DB_PATH) -> Dict[str, Any]:
    ak = _ak()
    if ak is None:
        return _result("dividend_event", "unavailable", source="akshare 未安装")
    store = MarketDataStore(db_path)
    written, failed = 0, []
    for symbol in symbols:
        try:
            batch = []
            for rec in _records(ak.stock_dividend_cninfo(symbol=_digits(symbol))):
                ex = _pick(rec, "除权除息日", "除息日", "股权登记日")
                if not ex:
                    continue
                batch.append((_norm(symbol), str(ex)[:10],
                              float(_pick(rec, "每股派息(元)", "每股股利", "派息") or 0.0),
                              float(_pick(rec, "每股送股(股)", "送股比例", "每股送股") or 0.0),
                              float(_pick(rec, "每股转增(股)", "配股比例", "每股配股") or 0.0),
                              "cninfo", _stamp()))
            written += _upsert(store, "INSERT OR REPLACE INTO dividend_event (symbol, ex_date, dividend_per_share, bonus_ratio, allot_ratio, source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        except Exception as exc:
            failed.append(f"{symbol}:{exc.__class__.__name__}")
        time.sleep(0.5)
    return _result("dividend_event", "ok" if not failed else "degraded", written, "巨潮分红(akshare)", failed)


# ---------------------------------------------------------------- D5 指数成分快照
def sync_index_members(db_path=DB_PATH) -> Dict[str, Any]:
    ak = _ak()
    if ak is None:
        return _result("index_members", "unavailable", source="akshare 未安装")
    store = MarketDataStore(db_path)
    batch_date = _today()
    written, failed = 0, []
    for index in DataSyncEngine.DEFAULT_INDICES:
        cs_code = CSINDEX_MAP.get(_norm(index))
        if not cs_code:
            failed.append(f"{index}:源不支持")
            continue
        try:
            batch = []
            for rec in _records(ak.index_stock_cons_weight_csindex(symbol=cs_code)):
                code = _pick(rec, "成分券代码", "代码")
                if not code:
                    continue
                batch.append((_norm(index), _norm(code), float(_pick(rec, "权重") or 0.0), batch_date))
            written += _upsert(store, "INSERT OR REPLACE INTO index_member (index_code, symbol, weight, batch_date) VALUES (?, ?, ?, ?)", batch)
            if not batch:
                failed.append(f"{index}:空批次")
        except Exception as exc:
            failed.append(f"{index}:{exc.__class__.__name__}")
    total = len(DataSyncEngine.DEFAULT_INDICES)
    with store._get_conn() as conn:
        covered = conn.execute("SELECT COUNT(DISTINCT index_code) FROM index_member WHERE batch_date = ?", (batch_date,)).fetchone()[0]
    missing = total - covered
    audit = {"covered": covered, "total": total, "missing": missing,
             "state": "complete" if missing == 0 else "missing",
             "detail": f"批次 {batch_date} · 成分 {written} 行"}
    _write_audit(store, "index_members", audit)
    return _result("index_members", "ok" if not failed else "degraded", written, "中证指数(akshare)", failed, audit)


# ---------------------------------------------------------------- D6 财务报表与指标
def sync_financial(symbols: Iterable[str], db_path=DB_PATH) -> Dict[str, Any]:
    ak = _ak()
    if ak is None:
        return _result("financial", "unavailable", source="akshare 未安装")
    store = MarketDataStore(db_path)
    symbols = list(symbols)
    start_year = str(date.today().year - 3)
    written, failed, missing_periods = 0, [], 0
    for symbol in symbols:
        try:
            present = set()
            batch = []
            for rec in _records(ak.stock_financial_analysis_indicator(symbol=_digits(symbol), start_year=start_year)):
                report = str(_pick(rec, "日期", "报告期") or "")[:10]
                if len(report) < 10 or report[5:] not in _QUARTER_ENDS:
                    continue
                present.add(report)
                batch.append((_norm(symbol), report, None,
                              _num(_pick(rec, "主营业务收入(元)", "主营业务收入", "营业总收入")),
                              _num(_pick(rec, "净利润(元)", "净利润")),
                              _num(_pick(rec, "净资产收益率(%)", "净资产收益率")),
                              _num(_pick(rec, "销售毛利率(%)", "销售毛利率")),
                              "sina", _stamp()))
            written += _upsert(store, "INSERT OR REPLACE INTO financial_report (symbol, report_date, disclose_date, revenue, net_profit, roe, gross_margin, source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
            missing_periods += max(len(_expected_periods(start_year)) - len(present & set(_expected_periods(start_year))), 0)
        except Exception as exc:
            failed.append(f"{symbol}:{exc.__class__.__name__}")
        time.sleep(0.5)
    audit = {"covered": len(symbols) - len(failed), "total": len(symbols), "missing": missing_periods + len(failed),
             "state": "complete" if not failed and missing_periods == 0 and symbols else "missing" if (failed or missing_periods) else "undetected",
             "detail": f"报告期序列稽核缺失 {missing_periods} 期"}
    _write_audit(store, "financial", audit)
    return _result("financial", "ok" if not failed and not missing_periods else "degraded", written,
                   "新浪财务指标(akshare)", failed, audit)


def _num(value: Any) -> Optional[float]:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _expected_periods(start_year: str) -> List[str]:
    today = _today()
    periods = []
    for year in range(int(start_year), date.today().year + 1):
        for tail in _QUARTER_ENDS:
            period = f"{year}-{tail}"
            if period <= today:
                periods.append(period)
    return periods


# ---------------------------------------------------------------- D7 估值与股本快照
def sync_capital(symbols: Optional[Iterable[str]] = None, db_path=DB_PATH) -> Dict[str, Any]:
    """全市场快照：腾讯 L1 批量快照取市值，股本 = 市值 ÷ 现价 推导（源无全市场股本直取接口）。"""
    store = MarketDataStore(db_path)
    codes = list(symbols) if symbols is not None else _full_market_codes()
    if not codes:
        codes = _resolve_registered()
    bridge = DataBridge()
    batch_date = _today()
    written, failed = 0, []
    for start in range(0, len(codes), 60):
        chunk = codes[start:start + 60]
        try:
            quotes = bridge.fetch_batch_snapshot(chunk) or []
        except Exception as exc:
            failed.append(f"chunk{start}:{exc.__class__.__name__}")
            continue
        batch = []
        for quote in quotes:
            symbol = _norm(quote.get("code") or quote.get("symbol") or "")
            price = _num(quote.get("price"))
            total_cap = _num(quote.get("total_market_cap"))
            float_cap = _num(quote.get("circulating_market_cap"))
            if not symbol or total_cap is None:
                continue
            batch.append((symbol, batch_date,
                          round(total_cap * 1e8 / price, 2) if price else None,
                          round(float_cap * 1e8 / price, 2) if price and float_cap is not None else None,
                          total_cap, float_cap, "tencent_snapshot_derived"))
        written += _upsert(store, "INSERT OR REPLACE INTO capital_snapshot (symbol, date, total_shares, float_shares, total_market_cap, float_market_cap, source) VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
    with store._get_conn() as conn:
        nulls = conn.execute("SELECT COUNT(*) FROM capital_snapshot WHERE date = ? AND total_market_cap IS NULL", (batch_date,)).fetchone()[0]
    audit = {"covered": written - nulls, "total": written, "missing": nulls + len(failed),
             "state": "complete" if written and not nulls and not failed else "missing" if written else "undetected",
             "detail": f"批次 {batch_date} 全市场快照"}
    _write_audit(store, "valuation", audit)
    return _result("valuation", "ok" if not failed and not nulls else "degraded", written,
                   "腾讯 L1 批量快照(股本推导)", failed, audit)


def _full_market_codes() -> List[str]:
    try:
        from core.data.fetch_history_fallback import get_market_stock_list
        return [_norm(item.get("code") or item.get("symbol")) for item in get_market_stock_list("all") or []
                if (item.get("code") or item.get("symbol"))]
    except Exception:
        return []


# ---------------------------------------------------------------- D8 行业分类快照
def sync_industry(symbols: Iterable[str], db_path=DB_PATH) -> Dict[str, Any]:
    ak = _ak()
    if ak is None:
        return _result("industry", "unavailable", source="akshare 未安装")
    store = MarketDataStore(db_path)
    batch_date = _today()
    symbols = list(symbols)
    written, failed = 0, []
    for symbol in symbols:
        try:
            industry = None
            df = ak.stock_individual_info_em(symbol=_digits(symbol))
            for rec in _records(df):
                if str(_pick(rec, "item", "项目") or "") == "行业":
                    industry = str(_pick(rec, "value", "值") or "") or None
                    break
            if industry:
                written += _upsert(store, "INSERT OR REPLACE INTO industry_class (symbol, industry_code, industry_name, batch_date) VALUES (?, ?, ?, ?)",
                                   [(_norm(symbol), industry, industry, batch_date)])
            else:
                failed.append(f"{symbol}:无行业字段")
        except Exception as exc:
            failed.append(f"{symbol}:{exc.__class__.__name__}")
        time.sleep(2)  # 技能 data-source-traps：东财个股信息顺序调用需间隔防卡死
    covered = len(symbols) - len(failed)
    audit = {"covered": covered, "total": len(symbols), "missing": len(failed),
             "state": "complete" if covered == len(symbols) and symbols else "missing" if symbols else "undetected",
             "detail": f"批次 {batch_date} 当前分类快照"}
    _write_audit(store, "industry", audit)
    return _result("industry", "ok" if not failed else "degraded", written, "东财个股信息(akshare)", failed, audit)


# ---------------------------------------------------------------- 调度入口
def run_dataset(key: str, symbols: Optional[Iterable[str]] = None, db_path=DB_PATH) -> Dict[str, Any]:
    registered = None
    if key == "base_calendar":
        return sync_stock_basic(db_path)
    if key == "minute_kline":
        return sync_minute_kline(symbols or _resolve_registered(), db_path=db_path)
    if key == "adjust_factor":
        return sync_adjust_factor(symbols or (registered := _resolve_registered()), db_path)
    if key == "index_members":
        return sync_index_members(db_path)
    if key == "financial":
        return sync_financial(symbols or (registered := _resolve_registered()), db_path)
    if key == "valuation":
        return sync_capital(symbols, db_path)
    if key == "industry":
        return sync_industry(symbols or (registered := _resolve_registered()), db_path)
    return _result(key, "failed", source="未知数据集键")


def run_due_datasets(now_dt: datetime, executed: Dict[str, str], db_path=DB_PATH) -> List[Dict[str, Any]]:
    """守护巡检调用：执行已到 §5.1 窗口且今日未跑的数据集（交易日判断由调用方负责）。"""
    if not TradeCalendar.is_trading_day(now_dt):
        return []
    today = now_dt.strftime("%Y-%m-%d")
    results = []
    for key, window in DATASET_WINDOWS.items():
        marker = f"ds_{key}"
        if now_dt.time() >= window and executed.get(marker) != today:
            results.append(run_dataset(key, db_path=db_path))
            executed[marker] = today
    return results
