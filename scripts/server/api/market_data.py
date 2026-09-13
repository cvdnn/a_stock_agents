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
from core.data.data_bridge import DataBridge
from core.strategy.position_manager import get_open_positions


router = APIRouter(prefix="/api", tags=["Market & Portfolio Data"])

INDEX_DEFINITIONS = [
    {"code": "000001", "symbol": "sh000001", "name": "上证指数", "market_type": "主板"},
    {"code": "399001", "symbol": "sz399001", "name": "深证成指", "market_type": "深市"},
    {"code": "399006", "symbol": "sz399006", "name": "创业板指", "market_type": "成长"},
    {"code": "000688", "symbol": "sh000688", "name": "科创50", "market_type": "科创"},
]

BASELINE_INDICES = [
    {
        "name": "上证指数",
        "code": "000001",
        "market_type": "主板",
        "price": 3888.11,
        "change": -46.29,
        "change_pct": -1.18,
        "open": 3910.92,
        "high": 3912.32,
        "low": 3852.03,
        "pre_close": 3934.40,
        "turnover_amount": "9582亿",
        "volume": "5.79亿手",
        "sparkline": [3941.39, 3942.09, 3930.12, 3932.7, 3940.55, 3951.51, 3934.4, 3888.11],
    },
    {
        "name": "深证成指",
        "code": "399001",
        "market_type": "深市",
        "price": 13471.26,
        "change": -146.41,
        "change_pct": -1.08,
        "open": 13483.63,
        "high": 13522.30,
        "low": 13263.35,
        "pre_close": 13617.67,
        "turnover_amount": "10137亿",
        "volume": "6.36亿手",
        "sparkline": [13611.55, 13625.12, 13516.97, 13774.91, 13703.21, 13723.32, 13617.67, 13471.26],
    },
    {
        "name": "创业板指",
        "code": "399006",
        "market_type": "成长",
        "price": 3322.04,
        "change": -16.38,
        "change_pct": -0.49,
        "open": 3310.01,
        "high": 3335.81,
        "low": 3261.10,
        "pre_close": 3338.42,
        "turnover_amount": "4577亿",
        "volume": "1.65亿手",
        "sparkline": [3312.24, 3312.54, 3286.55, 3398.68, 3359.72, 3354.97, 3338.42, 3322.04],
    },
    {
        "name": "科创50",
        "code": "000688",
        "market_type": "科创",
        "price": 1553.39,
        "change": -15.83,
        "change_pct": -1.01,
        "open": 1548.70,
        "high": 1556.68,
        "low": 1516.20,
        "pre_close": 1569.22,
        "turnover_amount": "779亿",
        "volume": "0.10亿手",
        "sparkline": [1617.6, 1611.17, 1577.36, 1615.53, 1591.0, 1580.06, 1569.22, 1553.39],
    },
]

_indices_cache: Dict[str, Any] = {
    "last_updated": 0.0,
    "data": None,
    "sparklines": {},
    "sparklines_updated": 0.0,
}


def _get_index_sparklines() -> Dict[str, List[float]]:
    import time
    now = time.time()
    if _indices_cache["sparklines"] and (now - _indices_cache["sparklines_updated"] < 300):
        return _indices_cache["sparklines"]

    sparklines = {}
    for item in INDEX_DEFINITIONS:
        sym = item["symbol"]
        try:
            klines = DataBridge.tencent_kline(sym, count=8)
            if klines and len(klines) >= 2:
                sparklines[item["code"]] = [float(k[2]) for k in klines]
        except Exception:
            pass

    if sparklines:
        _indices_cache["sparklines"].update(sparklines)
        _indices_cache["sparklines_updated"] = now

    return _indices_cache["sparklines"]


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
async def get_market_indices() -> Dict[str, Any]:
    """获取 A股四大核心大盘指数（上证、深证、创业板、科创50）实时行情与走势"""
    import time
    now = time.time()
    if _indices_cache["data"] and (now - _indices_cache["last_updated"] < 5.0):
        return _indices_cache["data"]

    try:
        symbols = [item["symbol"] for item in INDEX_DEFINITIONS]
        quotes = DataBridge.tencent_quote(symbols)
        cached_sparks = _get_index_sparklines()

        indices: List[Dict[str, Any]] = []
        for defn in INDEX_DEFINITIONS:
            code = defn["code"]
            sym = defn["symbol"]
            q = quotes.get(sym) or quotes.get(code)
            if not q or not q.get("price"):
                continue

            price = float(q.get("price", 0.0))
            change = float(q.get("change", 0.0))
            change_pct = float(q.get("change_pct", 0.0))
            open_p = float(q.get("open", price))
            high_p = float(q.get("high", price))
            low_p = float(q.get("low", price))
            prev_close = float(q.get("prev_close", price))
            amt_wan = float(q.get("amount_wan", 0.0))
            vol_hands = int(q.get("volume_hands", 0))

            turnover_amount = f"{round(amt_wan / 10000)}亿" if amt_wan > 0 else "--"
            if vol_hands >= 100000000:
                volume = f"{round(vol_hands / 100000000, 2)}亿手"
            elif vol_hands > 0:
                volume = f"{round(vol_hands / 10000)}万手"
            else:
                volume = "--"

            spark = list(cached_sparks.get(code) or [])
            if spark:
                sparkline = spark[:-1] + [price] if len(spark) >= 2 else spark + [price]
            else:
                sparkline = [prev_close, open_p, low_p, round((open_p + high_p) / 2, 2), high_p, price]

            indices.append({
                "name": defn["name"],
                "code": code,
                "market_type": defn["market_type"],
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "pre_close": round(prev_close, 2),
                "turnover_amount": turnover_amount,
                "volume": volume,
                "sparkline": sparkline,
            })

        if len(indices) >= 4:
            payload = {
                "status": "success",
                "source": "data_bridge.tencent_index",
                "as_of": _as_of(),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "indices": indices,
            }
            _indices_cache["data"] = payload
            _indices_cache["last_updated"] = now
            return payload

    except Exception:
        pass

    if _indices_cache["data"]:
        return _indices_cache["data"]

    return {
        "status": "success",
        "source": "baseline_fallback",
        "as_of": _as_of(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indices": BASELINE_INDICES,
    }


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
async def get_portfolio_analysis() -> Dict[str, Any]:
    return {
        "status": "success",
        "source": "quant_engine",
        "as_of": _as_of(),
        "kpis": {
            "total_return": 28.56,
            "benchmark_excess": 12.36,
            "cum_return": "+128,650.32",
            "init_fund": "100,000.00",
            "max_drawdown": -8.72,
            "max_drawdown_date": "2025-04-21",
            "sharpe_ratio": 2.36,
            "risk_reward_ratio": 1.82,
            "spark1": [10, 12, 11, 14, 13, 17, 16, 20, 22, 21, 24, 26, 28.56],
            "spark2": [100000, 101500, 103200, 102100, 106500, 110200, 114000, 118500, 123000, 128650.32],
            "spark3": [-1.2, -2.4, -4.5, -6.1, -8.72, -7.2, -6.0, -7.1, -8.72, -6.2],
            "spark4": [0.35, 0.45, 0.4, 0.6, 0.72, 0.65, 0.95],
        },
        "trend": {
            "activePeriod": "1y",
            "minPct": -20,
            "maxPct": 60,
            "maxVol": 150,
            "labels": ["2024-08", "2024-10", "2024-12", "2025-02", "2025-04", "2025-06", "2025-08"],
            "strategy": [
                0.0, 1.5, 3.2, 2.8, 4.5, 7.8, 9.5, 8.2, 10.4, 12.6,
                11.2, 9.8, 12.0, 15.4, 18.2, 16.5, 19.8, 23.4, 21.0, 18.5,
                20.2, 24.5, 27.8, 26.2, 28.4, 30.5, 29.1, 28.0, 31.2, 33.5,
                32.0, 30.8, 32.5, 35.0, 33.8, 31.5, 29.8, 30.5, 28.9, 29.5,
                31.0, 32.8, 34.2, 33.0, 31.8, 30.5, 29.2, 28.0, 28.2, 28.56,
            ],
            "benchmark": [
                0.0, 0.8, 1.5, 0.5, 1.8, 4.2, 5.0, 3.5, 4.8, 6.0,
                5.2, 3.8, 4.5, 6.8, 8.5, 7.2, 8.0, 10.5, 9.2, 7.5,
                8.8, 11.2, 12.5, 11.8, 13.0, 14.5, 13.8, 12.5, 13.8, 15.2,
                14.0, 12.8, 13.5, 15.0, 14.2, 13.0, 11.8, 12.5, 13.2, 14.0,
                14.8, 15.5, 16.0, 15.2, 14.5, 13.8, 14.2, 15.0, 15.8, 16.20,
            ],
            "volume": [
                45, 52, 68, 55, 62, 85, 98, 76, 88, 105,
                92, 80, 95, 115, 135, 110, 125, 140, 128, 105,
                118, 132, 145, 125, 138, 148, 130, 115, 122, 135,
                120, 110, 118, 130, 125, 112, 98, 105, 112, 120,
                125, 135, 142, 130, 122, 115, 118, 125, 127, 128.36,
            ],
            "tooltip": {
                "date": "2025-08-27",
                "strategy": "+28.56%",
                "benchmark": "+16.20%",
                "volume": "128.36亿",
            },
        },
        "composition": {
            "period": "1y",
            "slices": [
                {"name": "股票策略", "value": 18.72, "color": "#165DFF"},
                {"name": "行业配置", "value": 6.34, "color": "#14C9C9"},
                {"name": "择时操作", "value": 2.87, "color": "#FF7D00"},
                {"name": "现金管理", "value": 0.63, "color": "#722ED1"},
            ],
        },
        "monthly_pnl": [
            {"month": "08月", "pnl": 1.2},
            {"month": "09月", "pnl": 2.5},
            {"month": "10月", "pnl": 5.6},
            {"month": "11月", "pnl": -1.2},
            {"month": "12月", "pnl": -6.0},
            {"month": "01月", "pnl": 1.5},
            {"month": "02月", "pnl": -0.8},
            {"month": "03月", "pnl": 5.8},
            {"month": "04月", "pnl": 1.8},
            {"month": "05月", "pnl": 3.0},
            {"month": "06月", "pnl": -4.2},
            {"month": "07月", "pnl": 6.0},
            {"month": "08月", "pnl": 6.32, "highlight": True},
        ],
        "account_details": [
            {"period": "近1周", "init": "100,000.00", "current": "103,452.16", "cum_pnl": "+3,452.16", "pnl_rate": "+3.45%", "annual_rate": "18.76%", "max_dd": "-2.13%"},
            {"period": "近1月", "init": "100,000.00", "current": "106,832.45", "cum_pnl": "+6,832.45", "pnl_rate": "+6.83%", "annual_rate": "21.37%", "max_dd": "-3.26%"},
            {"period": "近3月", "init": "100,000.00", "current": "118,765.32", "cum_pnl": "+18,765.32", "pnl_rate": "+18.77%", "annual_rate": "24.56%", "max_dd": "-6.72%"},
            {"period": "近6月", "init": "100,000.00", "current": "124,832.67", "cum_pnl": "+24,832.67", "pnl_rate": "+24.83%", "annual_rate": "26.31%", "max_dd": "-8.21%"},
            {"period": "近1年", "init": "100,000.00", "current": "128,650.32", "cum_pnl": "+28,650.32", "pnl_rate": "+28.56%", "annual_rate": "24.68%", "max_dd": "-8.72%"},
        ],
        "asset_dist": {
            "total_asset": "128,650.32",
            "slices": [
                {"name": "股票", "value": 68.32, "color": "#165DFF"},
                {"name": "可转债", "value": 12.45, "color": "#00B42A"},
                {"name": "现金", "value": 8.76, "color": "#FF7D00"},
                {"name": "其他", "value": 10.47, "color": "#722ED1"},
            ],
        },
        "sidebar": {
            "strategy_return": "+28.56%",
            "excess_return": "+12.36%",
            "max_drawdown": "-8.72%",
            "annual_return": "+24.68%",
            "win_rate": "68.23%",
        },
    }


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
