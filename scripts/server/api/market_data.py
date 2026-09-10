# -*- coding: utf-8 -*-
"""Truthful REST projections for market, portfolio, pool, and monitor state.

P0 deliberately fails closed for dashboard capabilities that do not yet have a
canonical backend. Local portfolio and pool files are exposed without enriching
them with synthetic or network-derived values.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from core.config import load_stock_pools
from core.strategy.position_manager import get_open_positions


router = APIRouter(prefix="/api", tags=["Market & Portfolio Data"])


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unavailable(capability: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "status": "unavailable",
            "error": "CAPABILITY_NOT_IMPLEMENTED",
            "capability": capability,
            "source": "none",
        },
    )


@router.get("/market/indices")
async def get_market_indices() -> JSONResponse:
    return _unavailable("market.indices")


@router.get("/market/sentiment")
async def get_market_sentiment() -> JSONResponse:
    return _unavailable("market.sentiment")


@router.get("/market/kline")
async def get_market_kline(
    code: str = Query(..., min_length=6, max_length=6),
    period: str = Query(default="day"),
) -> JSONResponse:
    del code, period
    return _unavailable("market.kline")


@router.get("/market/ranks")
async def get_market_ranks() -> JSONResponse:
    return _unavailable("market.ranks")


@router.get("/portfolio/overview")
async def get_portfolio_overview() -> Dict[str, Any]:
    holdings = get_open_positions(enrich_quote=False)
    return {
        "status": "success" if holdings else "empty",
        "source": "core.strategy.position_manager.get_open_positions",
        "as_of": _as_of(),
        "count": len(holdings),
        "holdings": holdings,
    }


@router.get("/portfolio/analysis")
async def get_portfolio_analysis() -> JSONResponse:
    return _unavailable("portfolio.analysis")


def _configured_pool_entries(config: Dict[str, Any]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    seen = set()
    pools = config.get("pools", {}) if isinstance(config, dict) else {}
    for pool_name, pool in pools.items():
        stocks = pool.get("stocks", []) if isinstance(pool, dict) else []
        for item in stocks:
            if isinstance(item, dict):
                code = str(item.get("code") or item.get("symbol") or "").strip()
                name = str(item.get("name") or "").strip()
            else:
                code = str(item).strip()
                name = ""
            key = (str(pool_name), code)
            if not code or key in seen:
                continue
            seen.add(key)
            entries.append({"code": code, "name": name, "pool_type": str(pool_name)})
    return entries


@router.get("/watchlist")
async def get_watchlist(active_code: str = Query(default="")) -> Dict[str, Any]:
    del active_code
    stocks = _configured_pool_entries(load_stock_pools())
    return {
        "status": "success" if stocks else "empty",
        "source": "config/stock_pools.yaml",
        "as_of": _as_of(),
        "count": len(stocks),
        "stocks": stocks,
    }


@router.get("/monitor/stream")
async def get_monitor_stream() -> Dict[str, Any]:
    return {
        "status": "not_running",
        "source": "server_runtime",
        "as_of": _as_of(),
        "is_monitoring": False,
        "events": [],
        "strategies": [],
    }
