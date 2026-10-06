# -*- coding: utf-8 -*-
"""数据集登记册同步管线 (SPEC-DATA §5)。

- 按 §5.1 已确认外部接口渠道取数并落盘快照表；取数失败返回显式 failed/unavailable，严禁伪造值；
- 调度窗口为 §5.1 固定常量，由守护巡检 (sync_daemon) 与 CLI (`astock data dataset`) 触发；
- 字段规避原则：退市日期、指数成分历史进出、行业变更历史区间一律不入库；
- 同步/稽核范围：除 D1 交易所全量列表与 D5 指数成分、D7 全市场快照外，其余数据集以已登记标的 (P0–P2) 为范围。

漏斗模型示例 (close_to_open_turning_point) 数据依赖落点：
- D7 流通市值 (W-09): 入库单位统一为**元**，腾讯快照亿元值在入库时一次性 ×1e8 并以 source 标记换算口径；
- D10 资金流 (W-07): 代理档 tencent_proxy 水位恒为 degraded，仅供排序因子与观察运行；
- §5.5 UniverseWatermark: 每次同步批次写入 dataset_audit（detail 承载 JSON），供 post_close 门控消费。
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.data.data_bridge import DataBridge
from core.data.sync_engine import DB_PATH, DataSyncEngine, MarketDataStore, TradeCalendar

#: §5.1 固定调度窗口（minute_kline 为按需回补，不设固定窗口）
#  - W-02: 流通市值是漏斗 post_close 硬门槛字段，前置到随 D2 的 15:35 定盘批次
#    （原 16:30 全市场快照与 15:35 批次合一：腾讯 L1 批量快照定盘后即为收盘口径，幂等 REPLACE）；
#  - D10 资金流随 D2 定盘之后、post_close 之前（15:35 批次内）落盘；
#  - daily_kline: §5.5 水位在 P0/P1 定盘同步（15:35/15:40）完成后计算。
DATASET_WINDOWS = {
    "base_calendar": dt_time(15, 35),
    "capital_flow": dt_time(15, 35),
    "valuation": dt_time(15, 35),
    "daily_kline": dt_time(15, 45),
    "adjust_factor": dt_time(15, 50),
    "index_members": dt_time(16, 10),
    "financial": dt_time(16, 20),
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


# ---------------------------------------------------------------- §5.5 UniverseWatermark 契约
#: post_close 门控所需数据集键（D10 精算档落地并启用 main_fund_inflow 后再加入 "capital_flow"）
POST_CLOSE_WATERMARK_KEYS = ("base_calendar", "daily_kline", "valuation")


def _watermark_status(covered: int, total: int, availability: str) -> str:
    """批次状态判定：
    - finalized：可用性 finalized 且主口径 100%；
    - degraded：批次已运行但不达标（含零覆盖——跑了批次但 0 覆盖 ≠ 未检测）；
    - undetected：无批次（空 universe 或未调用）。
    """
    if total <= 0:
        return "undetected"
    if availability == "finalized" and covered >= total:
        return "finalized"
    if covered > 0 or availability == "degraded":
        return "degraded"
    return "undetected"


def write_universe_watermark(
    store: MarketDataStore,
    dataset_key: str,
    covered: int,
    total: int,
    availability: str = "finalized",
    blocking_fields: Optional[List[str]] = None,
    trade_date: Optional[str] = None,
    coverage_mv_weighted: Optional[float] = None,
    note: str = "",
) -> Dict[str, Any]:
    """按 §5.5 写入数据集水位（复用 dataset_audit，detail 列承载 JSON，幂等覆盖）。

    - 覆盖率主口径 = covered / total（有值标的数 ÷ 候选池标的数）；mv 加权口径仅作参考观测；
    - state 列沿用控制台既有词汇（complete/missing/undetected），JSON 内 status 用 §5.5 词汇
      （finalized/degraded/undetected），两侧由本函数单点换算，禁止各自派生；
    - status 须由稽核结果派生，不接受调用方直接指定。
    """
    trade_date = trade_date or _today()
    covered, total = int(covered or 0), int(total or 0)
    status = _watermark_status(covered, total, availability)
    coverage_pct = round(covered / total * 100, 2) if total else 0.0
    payload = {
        "trade_date": trade_date,
        "dataset_key": dataset_key,
        "finalized_at": _stamp(),
        "universe_total": total,
        "covered": covered,
        "coverage_pct": coverage_pct,
        "coverage_mv_weighted": coverage_mv_weighted,
        "availability": availability if status != "undetected" else "undetected",
        "blocking_fields": blocking_fields or [],
        "status": status,
    }
    if note:
        payload["note"] = note
    state_col = {"finalized": "complete", "degraded": "missing", "undetected": "undetected"}[status]
    _write_audit(store, dataset_key, {
        "covered": covered, "total": total, "missing": max(total - covered, 0),
        "state": state_col, "detail": json.dumps(payload, ensure_ascii=False),
    })
    return payload


def get_universe_watermark(
    dataset_keys: Optional[Iterable[str]] = None,
    trade_date: Optional[str] = None,
    db_path=DB_PATH,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """读取各数据集在指定交易日（默认最新批次）的 §5.5 水位；无批次返回 None，不伪造。"""
    keys = list(dataset_keys) if dataset_keys else list(POST_CLOSE_WATERMARK_KEYS)
    path = Path(db_path)
    if not path.is_file():
        return {key: None for key in keys}
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    with sqlite3.connect(str(path), timeout=5) as conn:
        for key in keys:
            if trade_date:
                row = conn.execute(
                    "SELECT covered, total, missing, state, detail, batch_date FROM dataset_audit"
                    " WHERE dataset_key = ? AND batch_date <= ? ORDER BY batch_date DESC LIMIT 1",
                    (key, trade_date),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT covered, total, missing, state, detail, batch_date FROM dataset_audit"
                    " WHERE dataset_key = ? ORDER BY batch_date DESC LIMIT 1", (key,),
                ).fetchone()
            if not row:
                out[key] = None
                continue
            covered, total, _missing, _state, detail, batch_date = row
            try:
                payload = json.loads(detail) if detail else {}
            except (TypeError, ValueError):
                payload = {}
            if not payload:
                # 旧格式 detail（纯文本）：由列值派生最小水位，不伪造 JSON
                payload = {
                    "trade_date": batch_date, "dataset_key": key,
                    "universe_total": total, "covered": covered,
                    "coverage_pct": round((covered or 0) / total * 100, 2) if total else 0.0,
                    "availability": "unknown", "status": "degraded" if covered else "undetected",
                    "blocking_fields": [], "note": "legacy_detail",
                }
            out[key] = payload
    return out


def check_post_close_ready(
    trade_date: Optional[str] = None,
    db_path=DB_PATH,
    required_keys: Iterable[str] = POST_CLOSE_WATERMARK_KEYS,
) -> Dict[str, Any]:
    """post_close 门控判定：每个必需数据集水位 status == finalized（含主口径 100%）。

    任一缺失/未达标 → ready=False；degraded 只允许观察运行（产物须携带 not_eligible_for_signal）。
    """
    watermarks = get_universe_watermark(required_keys, trade_date=trade_date, db_path=db_path)
    missing = [key for key, wm in watermarks.items() if wm is None]
    not_finalized = [
        key for key, wm in watermarks.items()
        if wm is not None and wm.get("status") != "finalized"
    ]
    return {
        "ready": not missing and not not_finalized,
        "trade_date": trade_date or _today(),
        "required_keys": list(required_keys),
        "missing": missing,
        "not_finalized": not_finalized,
        "datasets": watermarks,
    }


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
    watermark = write_universe_watermark(
        store, "base_calendar", covered, len(registered),
        availability="finalized" if registered and missing == 0 else "degraded",
        blocking_fields=["stock_basic"] if missing else [],
        note=f"交易所列表 {written} 只",
    )
    return _result("base_calendar", "ok" if not failed else "degraded", written,
                   "交易所官方列表(akshare)", failed, watermark)


# ---------------------------------------------------------------- D3 分钟K线（按需）
#: D3 保留深度（交易日）：1m 30 / 5m 90 / 15·30·60m 180（§5.1 D3）
MINUTE_RETENTION_DAYS = {"1": 30, "5": 90, "15": 180, "30": 180, "60": 180}


def _expected_min_date(freq: str, today: date) -> Optional[str]:
    """自今日回数 N 个交易日得到"期望最早 bar 日期"（W-04 深度判据）。

    仅做保守回数（不含今日）；日历不可用返回 None → 深度校验跳过（不产出假水位也不误报）。
    """
    need = MINUTE_RETENTION_DAYS.get(str(freq))
    if not need:
        return None
    d = today
    counted, guard = 0, 0
    while counted < need and guard < need * 3 + 40:
        d = date.fromordinal(d.toordinal() - 1)
        guard += 1
        try:
            if TradeCalendar.is_trading_day(d.isoformat()):
                counted += 1
        except Exception:
            return None
    return d.isoformat() if counted >= need else None


def sync_minute_kline(symbols: Iterable[str], freqs: Iterable[str] = ("5", "60"), db_path=DB_PATH) -> Dict[str, Any]:
    """D3 盘后回补通道（按需）：仅限历史审计与回测；盘中实时消费走 intraday_archiver 前向切片。

    W-04 假水位防护：回补后校验本地最早 bar 是否覆盖该周期的保留深度；
    源深度不足时水位判 degraded 并在 note 声明，**不得以现有片段冒充完整覆盖**。
    """
    ak = _ak()
    if ak is None:
        return _result("minute_kline", "unavailable", source="akshare 未安装")
    store = MarketDataStore(db_path)
    symbols = list(symbols)
    freqs = [str(f) for f in freqs]
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

    # 深度校验（W-04）：标的须在**全部请求周期**上满足保留深度才算 covered
    today = date.today()
    expected = {freq: _expected_min_date(freq, today) for freq in freqs}
    covered_symbols = 0
    shallow: List[str] = []
    with store._get_conn() as conn:
        for symbol in symbols:
            ok = True
            for freq in freqs:
                exp = expected.get(freq)
                if exp is None:
                    continue  # 日历不可用：跳过该周期深度判定（不误报）
                min_ts = conn.execute(
                    "SELECT MIN(ts) FROM minute_kline WHERE symbol = ? AND freq = ?", (_norm(symbol), freq)
                ).fetchone()[0]
                if min_ts is None or str(min_ts)[:10] > exp:
                    ok = False
            if ok:
                covered_symbols += 1
            else:
                shallow.append(symbol)
    total = len(symbols)
    coverage_final = total and covered_symbols == total and not failed
    watermark = write_universe_watermark(
        store, "minute_kline", covered_symbols, total,
        availability="finalized" if coverage_final else "degraded",
        blocking_fields=["minute_kline.depth"] if shallow or failed else [],
        note=f"按需回补批次 · 保留深度 {MINUTE_RETENTION_DAYS} 交易日"
             + (f" · 深度不足 {len(shallow)} 只" if shallow else ""),
    )
    return _result("minute_kline", "ok" if coverage_final else "degraded", written,
                   "腾讯 mkline(akshare)", failed, watermark)


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
    """全市场快照：腾讯 L1 批量快照取市值，股本 = 市值 ÷ 现价 推导（源无全市场股本直取接口）。

    W-09 单位口径（强契约）：入库单位统一为**元**。腾讯快照市值字段原值为亿元，
    在此一次性 ×1e8 换算并以 source=tencent_snapshot_derived_yuan 标记换算口径；
    禁止在规则层各自换算。旧批次（source=tencent_snapshot_derived，值为亿）须删除后重同步。
    """
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
            # 快照原值单位亿元 → 入库统一为元（W-09）；
            # W-10: quote 层把缺失折算为 0 —— 0 市值不成立，按缺失跳过（0 ≠ 缺失）
            total_raw = _num(quote.get("total_market_cap"))
            float_raw = _num(quote.get("circulating_market_cap"))
            total_cap_yuan = total_raw * 1e8 if total_raw else None
            float_cap_yuan = float_raw * 1e8 if float_raw else None
            if not symbol or total_cap_yuan is None:
                continue
            batch.append((symbol, batch_date,
                          round(total_cap_yuan / price, 2) if price else None,
                          round(float_cap_yuan / price, 2) if price and float_cap_yuan is not None else None,
                          total_cap_yuan, float_cap_yuan, "tencent_snapshot_derived_yuan"))
        written += _upsert(store, "INSERT OR REPLACE INTO capital_snapshot (symbol, date, total_shares, float_shares, total_market_cap, float_market_cap, source) VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
    # W-10: 分母为请求标的数，缺失（无市值/拉取失败）计入 missing，不得置零放行
    with store._get_conn() as conn:
        covered = conn.execute(
            "SELECT COUNT(*) FROM capital_snapshot WHERE date = ? AND total_market_cap IS NOT NULL", (batch_date,)
        ).fetchone()[0]
    total = len(codes)
    watermark = write_universe_watermark(
        store, "valuation", covered, total,
        availability="finalized" if total and covered == total and not failed else "degraded",
        blocking_fields=["float_market_cap"] if covered < total else [],
        trade_date=batch_date,
        note=f"批次 {batch_date} 全市场快照 · 单位元(W-09)",
    )
    return _result("valuation", "ok" if total and covered == total and not failed else "degraded", written,
                   "腾讯 L1 批量快照(股本推导·元)", failed, watermark)


def _full_market_codes() -> List[str]:
    try:
        from core.data.fetch_history_fallback import get_market_stock_list
        return [_norm(item.get("code") or item.get("symbol")) for item in get_market_stock_list("all") or []
                if (item.get("code") or item.get("symbol"))]
    except Exception:
        return []


# ---------------------------------------------------------------- D10 资金流（主力净流入）
def sync_capital_flow(symbols: Optional[Iterable[str]] = None, db_path=DB_PATH) -> Dict[str, Any]:
    """D10 资金流：东财精算档（eastmoney_exact）优先，腾讯代理档（tencent_proxy）兜底。

    渠道证据（2026-10-06 实测，akshare 1.18.94 §5.3 条件 5）：`stock_individual_fund_flow(stock, market)`
    日频约 120 行（可回补历史），列"主力净流入-净额/超大单净流入-净额/大单净流入-净额"单位**元**，
    与 `capital_flow_daily` 一一对应；无成交额列，amount 由 净额 ÷ 净占比×100 推导。

    裁定 W-07：水印 availability = finalized 仅当**全部请求标的**取得精算档；
    任一标的落代理档（(外盘-内盘)×VWAP，内外盘为腾讯源侧口径）即 degraded——
    代理档仅供排序因子与观察运行，`main_fund_inflow` 规则启用的前提是精算档 finalized 水位。
    精算档逐股限频（0.5s/只），默认范围为已登记标的 (P0–P2)；
    全市场代理档可显式传 `symbols=_full_market_codes()`（仅排序用途）。
    """
    store = MarketDataStore(db_path)
    codes = [_norm(c) for c in (symbols if symbols is not None else _resolve_registered())]
    if not codes:
        watermark = write_universe_watermark(
            store, "capital_flow", 0, 0, availability="finalized",
            note="无请求标的（默认范围为已登记池 P0–P2）",
        )
        return _result("capital_flow", "empty", 0, "东财精算档+腾讯代理兜底", [], watermark)

    ak = _ak()
    bridge = DataBridge()
    exact_rows: List[tuple] = []
    proxy_rows: List[tuple] = []
    failed: List[str] = []

    # 1) 东财精算档：逐股取 120 交易日历史（含当日，非交易日为最近交易日）
    if ak is not None:
        for symbol in codes:
            try:
                df = ak.stock_individual_fund_flow(stock=_digits(symbol), market=symbol[:2])
                for rec in _records(df):
                    day = str(_pick(rec, "日期") or "")[:10]
                    main = _num(_pick(rec, "主力净流入-净额"))
                    if not day or main is None:
                        continue
                    ratio = _num(_pick(rec, "主力净流入-净占比"))
                    # 无成交额列：净占比 = 净额 / 成交额 × 100 → 反推（占比为 0 时留空）
                    amount = round(main / ratio * 100, 2) if ratio else None
                    exact_rows.append((symbol, day, main,
                                       _num(_pick(rec, "超大单净流入-净额")),
                                       _num(_pick(rec, "大单净流入-净额")),
                                       amount, "eastmoney_exact", _stamp()))
            except Exception as exc:
                failed.append(f"{symbol}:exact:{exc.__class__.__name__}")
            time.sleep(0.5)  # 东财源限频

    # 2) 缺口标的走腾讯代理档兜底（批量快照，快）
    exact_symbols = {row[0] for row in exact_rows}
    fallback_codes = [c for c in codes if c not in exact_symbols]
    if fallback_codes:
        batch_date = _today()
        for start in range(0, len(fallback_codes), 60):
            chunk = fallback_codes[start:start + 60]
            try:
                quotes = bridge.fetch_batch_snapshot(chunk) or []
            except Exception as exc:
                failed.append(f"chunk{start}:proxy:{exc.__class__.__name__}")
                continue
            for quote in quotes:
                symbol = _norm(quote.get("code") or quote.get("symbol") or "")
                price = _num(quote.get("price"))
                amount = _num(quote.get("amount"))          # 元
                outer = _num(quote.get("outer"))            # 手（≈主动买）
                inner = _num(quote.get("inner"))            # 手（≈主动卖）
                volume = _num(quote.get("volume_hands"))    # 手
                if not symbol or price is None or price <= 0:
                    continue
                if outer is None or inner is None:
                    net_inflow = None
                else:
                    vwap = (amount / (volume * 100)) if amount and volume else price
                    net_inflow = round((outer - inner) * 100 * vwap, 2)
                proxy_rows.append((symbol, batch_date, net_inflow, None, None,
                                   amount, "tencent_proxy", _stamp()))

    written = _upsert(store, "INSERT OR REPLACE INTO capital_flow_daily (symbol, date, main_net_inflow, super_large_net_inflow, large_net_inflow, amount, flow_source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", exact_rows + proxy_rows)
    total = len(codes)
    exact_covered = len(exact_symbols & set(codes))
    watermark = write_universe_watermark(
        store, "capital_flow", exact_covered, total,
        availability="finalized" if total and exact_covered == total else "degraded",
        blocking_fields=["main_net_inflow"] if exact_covered < total else [],
        note=f"精算档 {exact_covered}/{total} · 代理兜底 {len(fallback_codes)} 只 · 最新批次见 MAX(date)",
    )
    return _result("capital_flow", "ok" if total and exact_covered == total else "degraded", written,
                   "东财精算档+腾讯代理兜底", failed, watermark)


def read_capital_flow(symbols: Iterable[str], date_str: Optional[str] = None, db_path=DB_PATH) -> List[Dict[str, Any]]:
    """读取资金流行（供漏斗排序因子/观察运行消费）；代理档行携带 availability=degraded 水印。"""
    path = Path(db_path)
    if not path.is_file():
        return []
    wanted = [_norm(s) for s in symbols]
    if not wanted:
        return []
    with sqlite3.connect(str(path), timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT symbol, date, main_net_inflow, super_large_net_inflow, large_net_inflow, amount, flow_source"
            f" FROM capital_flow_daily WHERE symbol IN ({','.join('?' * len(wanted))})"
            " AND date = COALESCE(?, (SELECT MAX(date) FROM capital_flow_daily)) ORDER BY symbol",
            (*wanted, date_str),
        ).fetchall()
    return [
        {
            "symbol": r["symbol"], "date": r["date"],
            "main_net_inflow": r["main_net_inflow"],
            "super_large_net_inflow": r["super_large_net_inflow"],
            "large_net_inflow": r["large_net_inflow"],
            "amount": r["amount"],
            "flow_source": r["flow_source"],
            # W-07: 代理档水印，消费方须据此判 UNKNOWN / not_eligible_for_signal
            "availability": "degraded" if r["flow_source"] == "tencent_proxy" else "finalized",
        }
        for r in rows
    ]


# ---------------------------------------------------------------- D2 日线水位（§5.5）
def sync_daily_kline_watermark(trade_date: Optional[str] = None, db_path=DB_PATH) -> Dict[str, Any]:
    """D2 水位：已登记标的 (P0–P2) 当日**已定盘**日K行覆盖率（主口径 = 有值标的数 ÷ 候选池标的数）。

    仅统计 is_settled=1 的行（只读取已定盘本地库）；全市场 D2 覆盖属 P3 增量（16:00），
    不在本水位口径内，note 字段显式声明范围以防误读。
    """
    store = MarketDataStore(db_path)
    target = trade_date or _today()
    registered = _resolve_registered()
    if not registered:
        watermark = write_universe_watermark(
            store, "daily_kline", 0, 0, availability="finalized",
            trade_date=target, note="无登记标的，口径为已登记池(P0–P2)",
        )
        return _result("daily_kline", "empty", 0, "本地 daily_kline 定盘水位", [], watermark)
    with store._get_conn() as conn:
        covered = conn.execute(
            f"SELECT COUNT(DISTINCT symbol) FROM daily_kline"
            f" WHERE date = ? AND is_settled = 1 AND symbol IN ({','.join('?' * len(registered))})",
            (target, *registered),
        ).fetchone()[0]
    total = len(registered)
    watermark = write_universe_watermark(
        store, "daily_kline", covered, total,
        availability="finalized" if covered == total else "degraded",
        blocking_fields=["daily_kline.settled"] if covered < total else [],
        trade_date=target,
        note="口径为已登记池(P0–P2)当日定盘行；全市场属 P3 增量",
    )
    return _result("daily_kline", "ok" if covered == total else "degraded", covered,
                   "本地 daily_kline 定盘水位", [], watermark)


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
    if key == "capital_flow":
        return sync_capital_flow(symbols, db_path)
    if key == "daily_kline":
        return sync_daily_kline_watermark(db_path=db_path)
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
