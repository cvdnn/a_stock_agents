# -*- coding: utf-8 -*-
"""Truthful REST projections for market, portfolio, pool, and monitor state.

P0 deliberately fails closed for dashboard capabilities that do not yet have a
canonical backend. Local portfolio and pool files are exposed without enriching
them with synthetic or network-derived values.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query
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
    """A股四大核心指数实时行情与走势（只交付真实抓取或真实缓存）。

    历史缺陷：源不可达时整块回落 `BASELINE_INDICES` 冻结快照（上证 3888.11 / 深证 13471.26 …）
    并标 `status="success"`，把某一天的收盘画面当成"今日实时行情"喂给前端；无日K时还用
    昨收/开/低/中点/高 拼一条假的 sparkline。快照与拼线均已删除：无源即 `unavailable` + 空数组，
    有缓存即 `stale` 并给出陈旧时长，前端据此走 `markMarketIndicesUnavailable()` 诚实空态。
    """
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

            # 走势只来自真实日K收盘序列；取不到就留空，严禁用 昨收/开/低/中点/高 拼一条"看起来像"的曲线
            spark = list(cached_sparks.get(code) or [])
            sparkline = (spark[:-1] + [price]) if len(spark) >= 2 else []

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

        if indices:
            payload = {
                "status": "success" if len(indices) == len(INDEX_DEFINITIONS) else "partial",
                "source": "data_bridge.tencent_quote",
                "as_of": _as_of(),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(indices),
                "indices": indices,
            }
            _indices_cache["data"] = payload
            _indices_cache["last_updated"] = now
            return payload

    except Exception:
        pass

    cached = _indices_cache["data"]
    if cached:
        # 缓存来自上一次真实抓取，可以复用，但必须显式标注为陈旧而不是"实时"
        return {
            **cached,
            "status": "stale",
            "stale": True,
            "cached_as_of": cached["as_of"],
            "cache_age_seconds": round(now - _indices_cache["last_updated"], 1),
        }

    return {
        "status": "unavailable",
        "source": "empty",
        "as_of": _as_of(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": 0,
        "indices": [],
        "message": "指数实时源不可达且无可用缓存；按零虚假数据铁律不回落任何静态快照，前端显示 '--'。",
    }


@router.get("/market/sentiment")
async def get_market_sentiment():
    """全市场情绪量化研判（涨跌家数/涨停跌停/两市成交/领涨板块）。

    当前无任何真实数据源可支撑该口径：涨跌家数与涨停统计需全市场快照聚合，
    板块与概念涨幅需行业分类行情源。既有实现曾整块写死 score=78、
    total_turnover="1.28万亿"、sectors/concepts 榜单，并把 source 标为
    "market_sentiment_engine"（并不存在该引擎），属伪造运行态。
    按零虚假数据铁律改为 fail-closed，待真实数据源接入后再实现。
    """
    return _unavailable("market.sentiment")


@router.get("/market/kline")
async def get_market_kline(
    code: str = Query(default="000001", min_length=6, max_length=10),
    period: str = Query(default="day"),
) -> Dict[str, Any]:
    """获取指定标的或指数的日K线及均线系统数据"""
    normalized = DataBridge.normalize_symbol(code, with_prefix=True)
    klines: List[List[Any]] = []
    try:
        raw_klines = DataBridge.tencent_kline(normalized, count=35)
        if raw_klines and len(raw_klines) >= 5:
            # 格式: [date, open, close, high, low, volume]
            klines = raw_klines
    except Exception:
        pass

    source = "data_bridge.tencent_kline" if klines else ""

    # 若外网不可用，优先无缝切换至本地已同步的 SQLite 真实历史库
    if not klines:
        try:
            from core.data.sync_engine import MarketDataStore
            store = MarketDataStore()
            local_klines = store.get_klines(normalized, count=35)
            if local_klines and len(local_klines) >= 1:
                klines = [
                    [k["date"], k["open"], k["close"], k["high"], k["low"], k["volume"]]
                    for k in local_klines
                ]
                source = "local.market_data_store"
        except Exception:
            pass

    # 【零虚假数据原则】：本地库与网络均无数据时，直接返回空切片与明确提示，严禁合成伪造假数据
    if not klines:
        return {
            "status": "warning",
            "source": "empty",
            "message": "网络不可用且本地数据库暂无该标的历史K线数据，无法展示走势（系统已彻底禁用合成虚拟数据）",
            "as_of": _as_of(),
            "code": code,
            "period": period,
            "klines": [],
            "ma5": 0.0,
            "ma10": 0.0,
            "ma20": 0.0,
        }

    # 计算真实均线
    closes = [float(k[2]) for k in klines]
    ma5 = round(sum(closes[-5:]) / min(5, len(closes)), 2) if closes else 0.0
    ma10 = round(sum(closes[-10:]) / min(10, len(closes)), 2) if closes else 0.0
    ma20 = round(sum(closes[-20:]) / min(20, len(closes)), 2) if closes else 0.0

    return {
        "status": "success",
        "source": source,
        "as_of": _as_of(),
        "code": code,
        "period": period,
        "klines": klines,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
    }


@router.get("/market/ranks")
async def get_market_ranks():
    """两市涨幅榜、跌幅榜与资金流向榜。

    真实榜单需全市场快照排序（涨跌幅榜）与北向/主力资金流数据源，当前均无接入。
    既有实现把 gainers/losers/northbound 三张榜单整块写死，仅用真实报价刷新
    northbound 的最新价，并把 source 标为 "market_ranks_engine"（并不存在该引擎），
    属"半真半假"的伪造榜单——比全假更具误导性。
    按零虚假数据铁律改为 fail-closed，待全市场快照与资金流数据源接入后再实现。
    """
    return _unavailable("market.ranks")


def _money(value: Optional[float]) -> Optional[str]:
    """金额格式化；无数据源即 None，由前端显示 '--'，绝不格式化一个编造出来的数。"""
    return None if value is None else f"¥{value:,.2f}"


@router.get("/portfolio/overview")
async def get_portfolio_overview() -> Dict[str, Any]:
    """持仓总览：只交付 positions.csv 与实时行情能够证实的口径。

    历史缺陷：① 汇总读的是 `h["price"]` / `h["shares"]`，而 position_manager 的真实字段是
    `cur_price` / `qty` / `market_value`，键名不匹配使持仓市值恒为 ¥0.00、仓位占比恒为 0%；
    ② 现金写死 100000、今日盈亏写死 `+¥1,850.00 / 1.45%`、总收益 18.5%、年化 22.3%，
    空仓分支照样报"总资产 ¥100,000.00、可用现金 100%"。
    账户级现金与逐日净值序列在本端点没有任何已接入数据源，现一律留 None；
    只保留能由真实持仓成本与现价推出的市值、成本与浮动盈亏。
    """
    holdings = get_open_positions(enrich_quote=True)

    market_value = round(sum(float(h.get("market_value") or 0.0) for h in holdings), 2)
    cost = round(sum(
        float(h.get("cost") or (float(h.get("buy_price") or 0.0) * int(h.get("qty") or 0)))
        for h in holdings
    ), 2)
    floating_pnl = round(market_value - cost, 2)

    return {
        "status": "empty" if not holdings else "success",
        "source": "core.strategy.position_manager.get_open_positions",
        "as_of": _as_of(),
        "count": len(holdings),
        "holdings": holdings,
        # 持仓侧：成本与市值来自 positions.csv 真实字段 + 实时现价
        "position_cost": _money(cost),
        "position_market_value": _money(market_value),
        "floating_pnl": floating_pnl,
        "floating_pnl_pct": round(floating_pnl / cost * 100, 2) if cost > 0 else None,
        # 账户侧：现金台账与净值序列未接入本端点（模拟盘账户是另一套 SQLite 账本），
        # 因此总资产、可用资金、仓位占比、当日与累计/年化收益一律不可知
        "account_state": "not_wired",
        "total_assets": None,
        "available_cash": None,
        "position_ratio": None,
        "cash_ratio": None,
        "today_pnl": None,
        "today_pnl_pct": None,
        "total_return_pct": None,
        "annualized_return_pct": None,
        "donut_data": [],
        "risk_status": "空仓观望" if not holdings else None,
        "cushion_desc": (
            "positions.csv 中当前无持仓记录" if not holdings
            else "风控判定需止损位与账户暴露口径，尚未接入"
        ),
    }


@router.get("/portfolio/analysis")
async def get_portfolio_analysis():
    """投资组合全景收益分析（KPI/收益走势/收益构成/月度盈亏/资产分布/胜率）。

    该口径需要真实成交流水与逐日净值序列做归因计算，当前并无任何数据源接入。
    既有实现整块写死 total_return=28.56、sharpe_ratio=2.36、win_rate="68.23%"、
    50 点收益走势与 13 个月盈亏，并把 source 标为 "quant_engine"（并不存在该引擎），
    属伪造运行态；前端还把它当"真实接口成功"渲染，危害大于显式报错。
    按零虚假数据铁律改为 fail-closed，待真实净值与成交流水接入后再实现。
    """
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
            if not code or code in seen:
                continue
            seen.add(code)
            entries.append({"code": code, "name": name, "pool_type": str(pool_name)})
    return entries


#: 自选列表唯一声明式来源；股池为空时如实上报该来源为空，不得伪造标的
WATCHLIST_POOL_SOURCE = "config/stock_pools.yaml"


def _quote_number(quote: Dict[str, Any], key: str, *, positive_only: bool = False) -> Optional[float]:
    """取行情字段为定点数；缺失/非法/（可选）非正一律 None，交由前端显示 '--'。"""
    raw = quote.get(key)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if positive_only and value <= 0:
        return None
    return round(value, 2)


def _active_stock_detail(
    active_code: str,
    stocks: List[Dict[str, Any]],
    quote_lookup,
) -> Optional[Dict[str, Any]]:
    """当前选中个股画像：只装配行情真实返回的字段，无来源者一律留 None。

    取不到现价时返回 None，让前端 Hero 卡按"数据源不可用"渲染；
    绝不用演示价与演示系数合成 OHLC 冒充真实盘口。
    """
    target_code = str(active_code or "").strip() or (stocks[0]["code"] if stocks else "")
    if not target_code:
        return None
    tq = quote_lookup(target_code)
    price = _quote_number(tq, "price", positive_only=True)
    if price is None:
        return None

    name = str(tq.get("name") or next(
        (s["name"] for s in stocks if s["code"] == target_code), target_code
    ))
    volume_hands = _quote_number(tq, "volume_hands", positive_only=True)
    amount_wan = _quote_number(tq, "amount_wan", positive_only=True)
    circ_cap = _quote_number(tq, "circulating_market_cap", positive_only=True)
    total_cap = _quote_number(tq, "total_market_cap", positive_only=True)
    pe = _quote_number(tq, "pe")

    return {
        "code": target_code,
        "name": name,
        "badge": name[:2] if len(name) >= 2 else target_code[:2],
        "badgeBg": "#003B99" if "宁德" in name else "#1677FF",
        "price": price,
        "change": _quote_number(tq, "change"),
        "change_pct": _quote_number(tq, "change_pct"),
        "open": _quote_number(tq, "open", positive_only=True),
        "high": _quote_number(tq, "high", positive_only=True),
        "low": _quote_number(tq, "low", positive_only=True),
        "pre_close": _quote_number(tq, "prev_close", positive_only=True),
        "volume": f"{volume_hands / 10000:.2f}万手" if volume_hands else None,
        "amount": f"{amount_wan / 10000:.2f}亿元" if amount_wan else None,
        "quote_time": tq.get("time"),
        "circ_market_val": f"{circ_cap:,.2f}亿" if circ_cap else None,
        "total_market_val": f"{total_cap:,.2f}亿" if total_cap else None,
        "pe_ttm": pe,
        # 以下口径当前没有任何已接入的真实数据源（行业/概念/PB/52周/均线/资金流/
        # 北向/主力持仓），必须留 None 由前端显示 '--'，严禁写死演示值。
        "industry": None,
        "concepts": None,
        "pb": None,
        "high_52w": None,
        "low_52w": None,
        "ma": None,
        "capital_flow": None,
        "northbound": None,
        "main_control": None,
    }


@router.get("/watchlist")
async def get_watchlist(active_code: str = Query(default="")) -> Dict[str, Any]:
    """自选股池列表及当前选中股票画像（零虚假数据：只交付可证实字段）。

    历史缺陷：池为空时回填 8 只硬编码"核心自选候选"，并对取到的行情缺失项兜底成
    328.56 / 2.77 / '+1.28亿'，active_detail 更写死 volume/amount/industry/pe/pb/ma
    与资金流、北向、主力持仓全套画像，把"没有数据"伪装成"数据很好"。
    """
    pool_entries = _configured_pool_entries(load_stock_pools())
    if not pool_entries:
        return {
            "status": "empty",
            "source": WATCHLIST_POOL_SOURCE,
            "as_of": _as_of(),
            "count": 0,
            "stocks": [],
            "active_stock_detail": None,
        }

    # 批量拉取实时行情；失败即视为无行情，对应字段留 None（不降级为假值）
    symbols = [DataBridge.normalize_symbol(s["code"], with_prefix=True) for s in pool_entries]
    try:
        quotes = DataBridge.tencent_quote(symbols) or {}
    except Exception:
        quotes = {}

    def quote_lookup(code: str) -> Dict[str, Any]:
        sym = DataBridge.normalize_symbol(code, with_prefix=True)
        return quotes.get(sym) or quotes.get(code) or {}

    stocks: List[Dict[str, Any]] = []
    seen_codes = set()
    for s in pool_entries:
        c = s["code"]
        if not c or c in seen_codes:
            continue
        seen_codes.add(c)
        q = quote_lookup(c)
        price = _quote_number(q, "price", positive_only=True)
        name = str(q.get("name") or s.get("name") or c)
        stocks.append({
            "code": c,
            "name": name,
            "pool": s.get("pool_type", "watchlist"),
            "price": price,
            "change_pct": _quote_number(q, "change_pct") if price is not None else None,
            "badge": name[:2] if len(name) >= 2 else c[:2],
            "badgeBg": "#003B99" if "宁德" in name else "#1677FF",
            "net_inflow": None,
        })

    return {
        "status": "success",
        "source": WATCHLIST_POOL_SOURCE,
        "quote_source": "data_bridge.tencent_quote" if quotes else "empty",
        "as_of": _as_of(),
        "count": len(stocks),
        "stocks": stocks,
        "active_stock_detail": _active_stock_detail(active_code, stocks, quote_lookup),
    }


@router.get("/monitor/stream")
async def get_monitor_stream() -> Dict[str, Any]:
    """盘中实时盯盘流：当前版本未接入真实盘中事件采集源。

    零虚假数据原则（SPEC-DATA-001 / SPEC-UI-003）：历史版本返回固定示例事件、
    恒真 is_monitoring 与伪造 latency_ms=12，属于演示数据，已整体移除；
    无真实源时必须返回空数组与明确可用性字段，由前端展示"未接入"空状态。
    """
    from core.data.sync_engine import TradeCalendar
    phase = TradeCalendar.get_market_phase()
    return {
        "status": "not_running",
        "source": "server_runtime",
        "as_of": _as_of(),
        "latency_ms": None,
        "is_monitoring": False,
        "events": [],
        "strategies": [],
        "market_phase": phase["phase"],
        "availability": {
            "event_feed": False,
            "reason": "服务端尚未接入真实盘中逐笔/大单事件采集源，为避免误导不回放任何示例事件",
        },
    }



# ============================================================================
# 数据同步与行情中枢 REST 端点 (Data Sync & Market Hub API)
# ============================================================================

@router.get("/market_data/clock")
async def get_market_data_clock() -> Dict[str, Any]:
    """获取当前市场时钟与定盘状态机"""
    from core.data.sync_engine import TradeCalendar
    phase_info = TradeCalendar.get_market_phase()
    is_settled = phase_info.get("is_settled", False)
    return {
        "status": "success",
        "source": "core.data.sync_engine.TradeCalendar",
        "date": phase_info["date_str"],
        "time": phase_info["time_str"],
        "is_trading_day": phase_info["is_trading_day"],
        "is_market_open": phase_info["is_market_open"],
        "is_settled": is_settled,
        "phase": phase_info["phase"],
        "phase_label": phase_info["phase_label"],
        "description": "当日行情已完成收盘与交易所清算，历史 Bar 数据已稳固归档。" if is_settled else "当前处于交易或清算时段，盘后 15:35 守护进程将自动固化定盘。",
    }


@router.get("/market_data/ping")
async def ping_market_data_feeds() -> Dict[str, Any]:
    """一键测速 4 级行情链路：L1腾讯、L2新浪、L3东财与本地 SQLite 数据库"""
    import asyncio
    import time
    import urllib.request
    from core.data.sync_engine import MarketDataStore

    res = {
        "status": "success",
        "source": "network_probe",
        "tencent_ms": None,
        "sina_ms": None,
        "eastmoney_ms": None,
        "local_db": False,
        "local_ms": 0.0,
        "timestamp": datetime.now().isoformat(),
    }

    # 1. 本地 SQLite 测速
    t0 = time.perf_counter()
    try:
        store = MarketDataStore()
        _ = store.get_klines("sh000001", count=1)
        res["local_db"] = True
        res["local_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    except Exception:
        res["local_db"] = False
        # 异常路径的耗时不是查询耗时，返回数值会被前端误读为"本地库延迟"
        res["local_ms"] = None

    # 2. 外部链路非阻塞并发测速
    def _probe_url(url: str) -> Optional[int]:
        t_start = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                _ = resp.read(64)
            return max(1, int((time.perf_counter() - t_start) * 1000))
        except Exception:
            return None

    loop = asyncio.get_running_loop()
    t_task = loop.run_in_executor(None, lambda: _probe_url("http://qt.gtimg.cn/q=sh000001"))
    s_task = loop.run_in_executor(None, lambda: _probe_url("http://hq.sinajs.cn/list=sh000001"))
    e_task = loop.run_in_executor(None, lambda: _probe_url("http://push2.eastmoney.com/api/qt/stock/get?secid=1.000001"))

    t_ms, s_ms, e_ms = await asyncio.gather(t_task, s_task, e_task, return_exceptions=True)

    # 探测失败必须如实返回 None。早期版本会回落 68/124/150 三个假延迟常量，
    # 导致完全断网时前端仍显示"4 级链路全部就绪"，属于伪造数据。
    res["tencent_ms"] = t_ms if isinstance(t_ms, int) else None
    res["sina_ms"] = s_ms if isinstance(s_ms, int) else None
    res["eastmoney_ms"] = e_ms if isinstance(e_ms, int) else None
    res["online"] = any(isinstance(x, int) for x in (t_ms, s_ms, e_ms))
    return res


@router.post("/market_data/daemon/control")
async def control_market_data_daemon(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """服务内自动定盘巡检的启停与调度参数控制（启停与参数写穿持久化设置）。

    真实生效对象是 app.py 的 `_market_post_settle_cron` 协程：两者读写同一份
    core.data.sync_daemon.SERVER_SYNC_RUNTIME，因此关闭后协程当轮即跳过；
    start/stop 同时持久化 `daemon.enabled`，服务重启后开关状态不回跳。
    """
    from core.data.sync_daemon import apply_sync_runtime_control
    from server.services.data_sync_settings import apply_to_runtime, effective_settings, save_settings

    data = payload or {}
    act = str(data.get("action", "status")).strip().lower()
    interval = data.get("interval")
    workers = data.get("workers")

    patch: Dict[str, Any] = {}
    if act in ("start", "restart"):
        patch["daemon"] = {"enabled": True}
    elif act == "stop":
        patch["daemon"] = {"enabled": False}
    if interval not in (None, ""):
        patch.setdefault("daemon", {})["interval_seconds"] = int(interval)
    if workers not in (None, ""):
        patch.setdefault("base", {})["concurrency"] = int(workers)

    persisted = True
    if patch:
        errors, _effective = save_settings(patch)
        if errors:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail={
                "error": "SETTINGS_VALIDATION_FAILED", "errors": errors,
            })
        apply_to_runtime()
    else:
        try:
            apply_to_runtime(effective_settings())
        except Exception:
            persisted = False

    snapshot = apply_sync_runtime_control(
        action=act,
        interval=None,  # 参数已由设置通道生效，这里只做跃迁留痕
        workers=None,
    )
    return {
        "status": "success",
        "executor": "in_process_cron",
        "executor_label": "服务内自动巡检协程 (server.app)",
        "daemon_running": snapshot["enabled"],
        "persisted": persisted,
        "pid": os.getpid(),
        "available_actions": ["status", "start", "stop", "restart"],
        "note": "独立 CLI 守护进程 DataSyncDaemon 运行在另一进程，不受此开关控制",
        **snapshot,
    }


@router.get("/market_data/daemon/logs")
async def get_market_data_daemon_logs(tail: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    """汇总自动定盘同步的真实日志：服务内协程 [Cron] 行 + 独立 CLI 守护进程日志。"""
    from core.config import LOG_DIR
    from core.data.sync_daemon import sync_runtime_snapshot

    sources: Dict[str, List[str]] = {}
    for name, marker in (("server.app", "[Cron]"), ("core.data.sync_daemon", None)):
        directory = LOG_DIR / name
        collected: List[str] = []
        if directory.exists():
            for path in sorted(directory.glob("*.log"), key=os.path.getmtime, reverse=True)[:2]:
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                        raw = [ln.rstrip() for ln in handle.readlines()]
                except OSError:
                    continue
                if marker:
                    raw = [ln for ln in raw if marker in ln]
                collected = raw[-tail:] + collected
        if collected:
            sources[name] = collected[-tail:]

    label_of = {"server.app": "服务内巡检", "core.data.sync_daemon": "CLI守护"}
    merged: List[str] = []
    for name, lines in sources.items():
        merged.extend(f"[{label_of.get(name, name)}] {line}" for line in lines)
    merged = merged[-tail:]

    snapshot = sync_runtime_snapshot()
    runtime_lines = [
        f"[运行时状态] 自动巡检={'启用' if snapshot['enabled'] else '暂停'} | 轮询间隔={snapshot['interval']}s"
        f" | 并发={snapshot['workers']} | 最近巡检={snapshot['last_check'] or '尚未执行'}"
    ]
    history = list(snapshot.get("history") or [])
    if history:
        runtime_lines.extend(f"[巡检事件] {line}" for line in history[-15:])
    else:
        runtime_lines.append(
            "[巡检事件] 本次服务启动后尚无事件：协程按轮询间隔运行，启停操作与交易日 15:35 的同步结果都会在此留痕。"
        )
    if snapshot.get("skipped_reason"):
        runtime_lines.append(f"[运行时状态] 跳过原因：{snapshot['skipped_reason']}")

    if not merged:
        merged = [
            "[日志] 文件日志中暂无自动同步记录：core.config 默认日志级别为 WARNING，"
            "巡检协程的 info 级明细不会落盘；上方「巡检事件」为进程内真实记录，不依赖日志级别。"
        ]

    return {
        "status": "success",
        "count": len(merged),
        "log_sources": sorted(sources.keys()),
        "history_count": len(history),
        "runtime": runtime_lines,
        "lines": runtime_lines + merged,
    }


@router.post("/settings/datafeed")
async def update_datafeed_settings(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """更新服务内自动巡检的并发线程数：白名单校验后持久化到有效设置并回灌运行时。

    历史兼容入口（等价 PUT /api/data-sync/settings 的 base.concurrency 单字段）；
    参数非法返回 400 与字段级原因，不再静默夹紧，重启后设置保持不回退。
    """
    from server.services.data_sync_settings import apply_to_runtime, effective_settings, save_settings

    try:
        workers = int(payload.get("sync_max_workers", 4))
    except (TypeError, ValueError):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={
            "error": "SETTINGS_VALIDATION_FAILED",
            "errors": [{"field": "sync_max_workers", "reason": "必须为 1–16 的整数"}],
        })
    errors, _effective = save_settings({"base": {"concurrency": workers}})
    if errors:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"error": "SETTINGS_VALIDATION_FAILED", "errors": errors})
    snapshot = apply_to_runtime(effective_settings())
    return {
        "success": True,
        "sync_max_workers": snapshot["workers"],
        "applied_to": "in_process_cron",
        "persisted": True,
        "message": (
            f"并发调度参数已校验并持久化为 {snapshot['workers']} 线程（作用于服务内自动巡检与 P0/P1 定盘；"
            "P3 全市场并发由高级设置 p3.concurrency 独立控制）"
        ),
    }


@router.post("/pools/import_tdx")
async def import_tdx_pool(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """从通达信自选文件文本解析并导入指定股池"""
    import re
    from core.strategy.pool_manager import PoolManager
    from server.services.data_sync_settings import effective_settings

    # 目标股池未显式指定时取有效设置 cooperation.tdx_target_pool（此前恒为硬编码 watchlist）
    target_pool = str(
        payload.get("pool") or effective_settings()["cooperation"]["tdx_target_pool"]
    ).strip()
    raw_content = str(payload.get("content") or "").strip()

    if not raw_content:
        return {
            "status": "warning",
            "imported_count": 0,
            "duplicates": 0,
            "failed": 0,
            "message": "导入内容为空，请提供自选股文本或代码列表",
        }

    # 提取 6 位股票代码及可选名称
    lines = raw_content.splitlines()
    imported_stocks = []
    seen = set()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.search(r"(\d{6})", line)
        if match:
            code = match.group(1)
            if code in seen:
                continue
            seen.add(code)
            parts = re.split(r"[\s,	]+", line)
            name = ""
            for p in parts:
                p_clean = p.strip()
                if p_clean and p_clean != code and not re.match(r"^(sh|sz|bj)\d{6}$", p_clean, re.I):
                    name = p_clean
                    break
            imported_stocks.append({"code": code, "name": name or code})

    pool_type_map = {
        "watchlist": "selected",
        "focus": "watch",
        "holdings": "holding",
    }
    pt = pool_type_map.get(target_pool, "selected")
    pm = PoolManager()

    success_count = 0
    duplicate_count = 0
    for s in imported_stocks:
        added = pm.add_stock(pt, {"code": s["code"], "name": s["name"], "source": "tdx_import"})
        if added:
            success_count += 1
        else:
            duplicate_count += 1

    return {
        "status": "success",
        "pool": target_pool,
        "imported_count": success_count,
        "duplicates": duplicate_count,
        "failed": 0,
        "total_parsed": len(imported_stocks),
        "stocks": imported_stocks[:10],
        "message": f"通达信自选导入成功：解析 {len(imported_stocks)} 只标的，新增入库 {success_count} 只，去重 {duplicate_count} 只",
    }
