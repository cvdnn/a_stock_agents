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
