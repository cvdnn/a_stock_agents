# -*- coding: utf-8 -*-
"""Read-only daily K-line freshness summary for the data sync console."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable

from core.data.sync_engine import DataBridge, TradeCalendar


def _settled_target(phase: Dict[str, Any]) -> tuple[str, str]:
    today = date.fromisoformat(phase["date_str"])
    if phase.get("is_trading_day") and phase.get("is_settled"):
        return today.isoformat(), "今日已定盘"
    candidate = today - timedelta(days=1)
    while not TradeCalendar.is_trading_day(candidate):
        candidate -= timedelta(days=1)
    note = "今日未定盘，按上一交易日判断" if phase.get("is_trading_day") else "非交易日，按上一交易日判断"
    return candidate.isoformat(), note


def _symbols(values: Iterable[str]) -> set[str]:
    return {
        DataBridge.normalize_symbol(str(value), with_prefix=True)
        for value in values if value and str(value).strip()
    }


def build_daily_health(
    phase: Dict[str, Any], pools: Dict[str, Iterable[str]], indices: Iterable[str], db_path: Path,
) -> Dict[str, Any]:
    """Summarize registered P0/P1/P2 symbols from real sync_meta watermarks."""
    target, note = _settled_target(phase)
    tiers = {
        "P0": _symbols(pools.get("holdings") or []),
        "P1": _symbols(pools.get("watchlist") or []) | _symbols(pools.get("focus") or []),
        "P2": _symbols(indices),
    }
    registered = set().union(*tiers.values())
    path = Path(db_path)
    meta: Dict[str, Dict[str, Any]] = {}
    read_error = None
    if path.is_file() and registered:
        try:
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as conn:
                for start in range(0, len(registered), 900):
                    batch = sorted(registered)[start:start + 900]
                    placeholders = ",".join("?" for _ in batch)
                    rows = conn.execute(
                        f"SELECT symbol, max_date, is_settled FROM sync_meta WHERE symbol IN ({placeholders})", batch,
                    ).fetchall()
                    meta.update({row[0]: {"max_date": row[1], "is_settled": row[2]} for row in rows})
        except (sqlite3.Error, OSError) as exc:
            read_error = str(exc)

    def summarize(symbols: set[str]) -> Dict[str, Any]:
        total = len(symbols)
        if read_error:
            return {"total": total, "covered": None, "fresh": None, "pending": None,
                    "without_data": None, "watermark_min": None, "watermark_max": None, "state": "unknown"}
        dates = [meta[s]["max_date"] for s in symbols if s in meta and meta[s]["max_date"]]
        fresh = sum(
            1 for symbol in symbols
            if symbol in meta and meta[symbol]["max_date"] and (
                meta[symbol]["max_date"] > target or
                (meta[symbol]["max_date"] == target and meta[symbol]["is_settled"] == 1)
            )
        )
        covered = len(dates)
        state = "empty" if not total else "no_data" if not covered else "fresh" if fresh == total else "pending"
        return {
            "total": total,
            "covered": covered,
            "fresh": fresh,
            "pending": total - fresh,
            "without_data": total - covered,
            "watermark_min": min(dates) if dates else None,
            "watermark_max": max(dates) if dates else None,
            "state": state,
        }

    return {
        "target_date": target,
        "target_note": note,
        "registered": summarize(registered),
        "tiers": {tier: summarize(symbols) for tier, symbols in tiers.items()},
        "availability": {"local_meta": path.is_file() and read_error is None, "reason": read_error},
    }


#: 控制台覆盖表数据集登记册：顺序即展示顺序；planned_scope 仅作为“未接入”占位的规划说明，不作为真实水位
DATASET_REGISTRY = (
    {"key": "base_calendar", "name": "基础资料与交易日历", "planned_scope": "2024–2027 规则日历"},
    {"key": "daily_kline", "name": "日线行情", "planned_scope": "已登记股池与指数成分"},
    {"key": "minute_kline", "name": "分钟K线", "planned_scope": "沪深北全市场 · 1/5/15/30/60 分钟"},
    {"key": "adjust_factor", "name": "复权因子与分红", "planned_scope": "沪深北全市场复权因子与分红事件"},
    {"key": "index_members", "name": "指数与成分股", "planned_scope": "核心指数最新成分与权重快照"},
    {"key": "financial", "name": "财务报表与指标", "planned_scope": "报告期 · 披露时间"},
    {"key": "valuation", "name": "估值与股本", "planned_scope": "沪深北全市场 · 每日估值快照"},
    {"key": "industry", "name": "行业分类", "planned_scope": "沪深北全市场当前行业分类快照"},
)


def _calendar_coverage_entry(spec: Dict[str, str]) -> Dict[str, Any]:
    """交易日历为确定性规则日历（2024–2027），无缺漏概念；批次为规则版本真实描述。"""
    holidays = len(TradeCalendar.STATUTORY_HOLIDAYS_CLOSED)
    return {
        "key": spec["key"],
        "name": spec["name"],
        "connected": True,
        "scope": "2024-01-01 ～ 2027-12-31 规则日历",
        "as_of": None,
        "batch": f"2024–2027 法定休市 {holidays} 天已内置",
        "completeness": {"state": "complete", "missing": 0, "label": "齐全"},
        "state": "fresh",
    }


def _daily_kline_coverage_entry(
    spec: Dict[str, str], daily_health: Dict[str, Any] | None, last_audit: Dict[str, Any] | None,
) -> Dict[str, Any]:
    registered = (daily_health or {}).get("registered") or {}
    total = registered.get("total")
    as_of = registered.get("watermark_max") or registered.get("watermark_min")
    audit = last_audit if isinstance(last_audit, dict) else None
    audit_applies = bool(audit) and audit.get("scope") == "registered_pools_and_indices"
    if audit_applies and audit.get("missing_gaps") is not None:
        missing = int(audit.get("missing_gaps") or 0)
        completeness = {
            "state": "missing" if missing else "complete",
            "missing": missing,
            "label": f"缺漏 {missing} 处" if missing else "审计通过",
        }
    else:
        completeness = {"state": "undetected", "missing": None, "label": "未检测"}
    return {
        "key": spec["key"],
        "name": spec["name"],
        "connected": True,
        "scope": f"已登记范围 {total if total is not None else '—'} 只",
        "as_of": as_of,
        "batch": None,
        "completeness": completeness,
        "state": registered.get("state") or "unknown",
    }


def _unconnected_coverage_entry(spec: Dict[str, str]) -> Dict[str, Any]:
    """无真实数据源的数据集：显式未接入，无水位、无完整性结论，严禁填充演示值。"""
    return {
        "key": spec["key"],
        "name": spec["name"],
        "connected": False,
        "scope": f"未接入（规划：{spec['planned_scope']}）",
        "as_of": None,
        "batch": None,
        "completeness": {"state": "undetected", "missing": None, "label": "未检测"},
        "state": "unavailable",
    }


def _probe_dataset_watermarks(db_path: Path | None) -> Dict[str, Dict[str, Any]]:
    """只读探测各数据集快照表与稽核快照的真实水位；库不存在或读取失败返回空（保持未接入占位）。"""
    out: Dict[str, Dict[str, Any]] = {}
    path = Path(db_path) if db_path else None
    if path is None or not path.is_file():
        return out
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row

            def one(sql: str) -> Dict[str, Any]:
                cursor = conn.execute(sql)
                row = cursor.fetchone()
                return dict(zip([col[0] for col in cursor.description], row)) if row else {}

            audits = {
                row["dataset_key"]: dict(row) for row in conn.execute(
                    "SELECT dataset_key, covered, total, missing, state, detail FROM dataset_audit d"
                    " WHERE batch_date = (SELECT MAX(batch_date) FROM dataset_audit WHERE dataset_key = d.dataset_key)"
                ).fetchall()
            }
            basic = one("SELECT COUNT(*) AS c, MAX(updated_at) AS u FROM stock_basic")
            minute = one("SELECT COUNT(*) AS c, MAX(ts) AS m, COUNT(DISTINCT freq) AS f FROM minute_kline")
            factor = one("SELECT COUNT(*) AS c, COUNT(DISTINCT symbol) AS s, MAX(date) AS m FROM adjust_factor")
            dividend = one("SELECT COUNT(*) AS c FROM dividend_event")
            member = one("SELECT COUNT(DISTINCT index_code) AS i, COUNT(*) AS c, MAX(batch_date) AS b FROM index_member")
            financial = one("SELECT COUNT(DISTINCT symbol) AS s, MAX(report_date) AS m FROM financial_report")
            capital = one("SELECT COUNT(*) AS c, MAX(date) AS d FROM capital_snapshot")
            industry = one("SELECT COUNT(*) AS c, MAX(batch_date) AS b FROM industry_class")
        out = {
            "base_calendar": {"water": basic, "audit": audits.get("base_calendar")},
            "minute_kline": {"water": minute, "audit": audits.get("minute_kline")},
            "adjust_factor": {"water": {**factor, "dividend": dividend.get("c")}, "audit": audits.get("adjust_factor")},
            "index_members": {"water": member, "audit": audits.get("index_members")},
            "financial": {"water": financial, "audit": audits.get("financial")},
            "valuation": {"water": capital, "audit": audits.get("valuation")},
            "industry": {"water": industry, "audit": audits.get("industry")},
        }
    except (sqlite3.Error, OSError):
        return {}
    return out


def _connected_override(key: str, probe: Dict[str, Any]) -> Dict[str, Any] | None:
    """快照表存在真实水位时，生成覆盖表行的接入态字段；无水位返回 None（保持占位）。"""
    water = probe.get("water") or {}
    audit = probe.get("audit") or {}
    if not water.get("c") and not water.get("s") and not water.get("i"):
        return None
    scope_map = {
        "base_calendar": f"交易所列表 {water.get('c')} 只",
        "minute_kline": f"已同步 {water.get('f')} 个周期",
        "adjust_factor": f"已登记范围 {water.get('s')} 只 · 分红事件 {water.get('dividend') or 0} 行",
        "index_members": f"{water.get('i')} 只指数 · {water.get('c')} 条成分",
        "financial": f"已登记范围 {water.get('s')} 只",
        "valuation": f"全市场 {water.get('c')} 只",
        "industry": f"已登记范围 {water.get('c')} 只",
    }
    asof_map = {
        "base_calendar": None,
        "minute_kline": water.get("m"),
        "adjust_factor": water.get("m"),
        "index_members": water.get("b"),
        "financial": water.get("m"),
        "valuation": water.get("d"),
        "industry": water.get("b"),
    }
    batch_map = {"base_calendar": (water.get("u") or "")[:10] or None}
    missing = audit.get("missing")
    state = audit.get("state")
    if state == "missing" and missing:
        completeness = {"state": "missing", "missing": missing, "label": f"缺漏 {missing} 处"}
    elif state == "complete":
        completeness = {"state": "complete", "missing": 0, "label": "齐全"}
    else:
        completeness = {"state": "undetected", "missing": None, "label": "未检测"}
    return {
        "connected": True,
        "scope": scope_map.get(key, "—"),
        "as_of": asof_map.get(key),
        "batch": batch_map.get(key),
        "completeness": completeness,
        "state": "pending" if completeness["state"] == "missing" else "fresh",
    }


def build_dataset_coverage(
    daily_health: Dict[str, Any] | None, last_audit: Dict[str, Any] | None, db_path: Path | None = None,
) -> list[Dict[str, Any]]:
    """按数据集逐条聚合覆盖条目：真实水位优先，未接入数据集显式占位。"""
    probes = _probe_dataset_watermarks(db_path)
    entries: list[Dict[str, Any]] = []
    for spec in DATASET_REGISTRY:
        if spec["key"] == "base_calendar":
            entry = _calendar_coverage_entry(spec)
        elif spec["key"] == "daily_kline":
            entry = _daily_kline_coverage_entry(spec, daily_health, last_audit)
        else:
            entry = _unconnected_coverage_entry(spec)
        override = _connected_override(spec["key"], probes.get(spec["key"]) or {}) if spec["key"] in probes else None
        if override:
            entry.update(override)
        entries.append(entry)
    return entries
