# -*- coding: utf-8 -*-
"""
server.agent.tools - Tools definitions and execution dispatcher for A-Stock Agent.
Bridges LLM tool-calling directly to the core/ quantitative research engines.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any, Callable, Dict, List, Optional

from core.config import get_logger
from core.data.data_bridge import DataBridge
from core.indicators.technical_indicators import calc_all
from core.models.combo_scorer import ComboScorer
from core.strategy.execution_action_engine import ExecutionActionEngine
from core.strategy.risk_manager import RiskManager

logger = get_logger("server.agent.tools")

# ── Function Calling Tool Schemas (OpenAI specification format) ──────────────

TOOLS_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "astock_quote",
            "description": "查询 A 股实时行情报价快照（包含现价、涨跌幅、成交量、换手率、PE、最高最低价等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位A股股票代码，如 600519、000001、300750",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "astock_technical",
            "description": "查询 A 股技术指标（MA、MACD、KDJ、RSI、BOLL、ATR）与近期日K线趋势特征。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位A股股票代码",
                    },
                    "count": {
                        "type": "integer",
                        "description": "获取日K线根数，默认 60",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "astock_action_plan",
            "description": (
                "实战交易反应动作单与精确保本价进位决策引擎。"
                "严格按印花税0.05%、佣金万2.5最低5元起收向上进位至分位（math.ceil）核算最低保本卖出价，"
                "并计算三级止损阶梯（T0 -3% / T1 -5% / T2 -8%）与三场景即时动作单（开盘冲高、震荡、急跌）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位A股股票代码",
                    },
                    "cost": {
                        "type": "number",
                        "description": "持仓买入成本价（若未持有可留空，将以现价作为参考成本）",
                    },
                    "shares": {
                        "type": "integer",
                        "description": "持仓股数，默认 100 股",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "astock_evaluate",
            "description": "全流程股票诊断与量化综合打分（100分制）：多因子共振评分、技术形态诊断、均线多空排列。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位A股股票代码",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "astock_screen_5a",
            "description": "A 股五维共振旋转选股引擎：动态筛选当前市场热点板块与高综合评分优质标的。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回优质标的数量上限，默认 10",
                    },
                    "dynamic_mode": {
                        "type": "string",
                        "description": "选股模式：hot_sectors (热点板块) 或 high_momentum (高动量)",
                    },
                },
            },
        },
    },
]


# ── Tool Handlers Implementation ─────────────────────────────────────────────

def _sync_astock_quote(code: str) -> Dict[str, Any]:
    bridge = DataBridge()
    q = bridge.get_realtime_quote(code)
    if not q:
        return {"error": f"无法获取股票 {code} 的实时行情，请检查代码是否正确。"}
    return {
        "code": q.get("code", code),
        "name": q.get("name", code),
        "price": float(q.get("price", 0.0)),
        "change_pct": float(q.get("change_pct", 0.0)),
        "high": float(q.get("high", 0.0)),
        "low": float(q.get("low", 0.0)),
        "open": float(q.get("open", 0.0)),
        "prev_close": float(q.get("prev_close", 0.0)),
        "turnover_pct": q.get("turnover_pct"),
        "pe": q.get("pe"),
        "market_cap": q.get("market_cap"),
        "time": q.get("time"),
    }


def _sync_astock_technical(code: str, count: int = 60) -> Dict[str, Any]:
    bridge = DataBridge()
    klines = bridge.tencent_kline(code, count=count)
    if not klines or len(klines) < 15:
        return {"error": f"股票 {code} 的历史K线数据不足。"}
    tech_all = calc_all(klines)
    latest = tech_all.get("latest", {})
    return {
        "code": code,
        "klines_count": len(klines),
        "latest_close": float(klines[-1][2]),
        "ma": latest.get("ma", {}),
        "macd": latest.get("macd", {}),
        "kdj": latest.get("kdj", {}),
        "rsi": latest.get("rsi", {}),
        "boll": latest.get("boll", {}),
        "atr": latest.get("atr", 0.0),
    }


def _sync_astock_action_plan(
    code: str, cost: Optional[float] = None, shares: Optional[int] = None
) -> Dict[str, Any]:
    bridge = DataBridge()
    q = bridge.get_realtime_quote(code) or {
        "price": cost or 10.0,
        "open": cost or 10.0,
        "high": cost or 10.0,
        "low": cost or 10.0,
        "change_pct": 0.0,
        "name": code,
        "code": code,
    }
    name = q.get("name", code)
    curr_price = float(q.get("price", cost or 10.0))
    eff_cost = cost if cost is not None else curr_price
    eff_shares = shares if shares is not None else 100

    klines = bridge.tencent_kline(code, count=120)
    tech_all = calc_all(klines) if (klines and len(klines) >= 26) else {}
    tech = tech_all.get("latest", {}) if tech_all else {}

    score_res = {"cs": 65, "rating": "B"}
    if klines and len(klines) >= 26 and tech:
        try:
            scorer = ComboScorer()
            scores = scorer.score_full(klines, tech)
            total_s = scores.get("total", 65)
            rating = "A" if total_s >= 75 else ("B" if total_s >= 60 else ("C" if total_s >= 45 else "D"))
            score_res = {"cs": total_s, "rating": rating}
        except Exception:
            pass

    holding = {
        "cost": eff_cost,
        "shares": eff_shares,
        "max_high": max(float(q.get("high", 0) or 0), eff_cost),
    }
    result = ExecutionActionEngine.generate_action(
        code=code,
        name=name,
        quote=q,
        tech=tech,
        holding=holding,
        model_score=score_res,
    )

    # Ensure precision stops and breakeven
    rm = RiskManager()
    stops = rm.calc_stop_losses(eff_cost, tech)
    breakeven = result.get("breakeven_price")
    if breakeven is None:
        breakeven = math.ceil(eff_cost * 1.001 * 100) / 100.0

    stop_t0 = round(stops.get("t0_warning", {}).get("price", eff_cost * 0.97), 2)
    stop_t1 = round(stops.get("t1_ma10", {}).get("price", eff_cost * 0.95), 2)
    stop_t2 = round(stops.get("t2_ma20", {}).get("price", eff_cost * 0.92), 2)

    result["breakeven_price"] = breakeven
    result["stop_t0"] = stop_t0
    result["stop_t1"] = stop_t1
    result["stop_t2"] = stop_t2
    result["cost"] = eff_cost
    result["shares"] = eff_shares
    return result


def _sync_astock_evaluate(code: str) -> Dict[str, Any]:
    bridge = DataBridge()
    q = bridge.get_realtime_quote(code)
    klines = bridge.tencent_kline(code, count=120)
    if not klines or len(klines) < 26:
        return {"error": f"股票 {code} 历史K线不足以完成全面诊断。"}

    tech_all = calc_all(klines)
    tech = tech_all.get("latest", {})
    scorer = ComboScorer()
    scores = scorer.score_full(klines, tech)

    return {
        "code": code,
        "name": q.get("name", code) if q else code,
        "current_price": float(q.get("price", klines[-1][2])) if q else float(klines[-1][2]),
        "total_score": scores.get("total", 60),
        "scores_detail": scores,
        "tech_summary": {
            "ma5": tech.get("ma", {}).get("ma5"),
            "ma10": tech.get("ma", {}).get("ma10"),
            "ma20": tech.get("ma", {}).get("ma20"),
            "macd_hist": tech.get("macd", {}).get("hist"),
            "rsi6": tech.get("rsi", {}).get("rsi6"),
        },
    }


def _sync_astock_screen_5a(limit: int = 10, dynamic_mode: Optional[str] = None) -> Dict[str, Any]:
    from core.models.stock_screener import StockScreener
    from core.strategy.dynamic_universe import DynamicUniverseEngine

    mode = dynamic_mode or "hot_sectors"
    dyn_engine = DynamicUniverseEngine()
    dyn_res = dyn_engine.generate_dynamic_universe(mode=mode, size=max(limit * 2, 20))
    codes = dyn_res.get("stocks", [])

    screener = StockScreener()
    res = screener.screen(codes, fetch_cyq=False)
    results = res.get("results", [])
    top_candidates = []
    for r in results[:limit]:
        top_candidates.append({
            "code": r.get("code"),
            "name": r.get("name"),
            "total_score": r.get("total_score"),
            "price": r.get("price"),
            "change_pct": r.get("change_pct"),
            "board": r.get("board"),
            "rating": r.get("rating"),
        })

    return {
        "mode": mode,
        "rationale": dyn_res.get("rationale", ""),
        "total_screened": res.get("total_input", len(codes)),
        "selected_count": len(top_candidates),
        "top_stocks": top_candidates,
    }


# ── Async Dispatcher ──────────────────────────────────────────────────────────

TOOL_MAP: Dict[str, Callable[..., Any]] = {
    "astock_quote": _sync_astock_quote,
    "astock_technical": _sync_astock_technical,
    "astock_action_plan": _sync_astock_action_plan,
    "astock_evaluate": _sync_astock_evaluate,
    "astock_screen_5a": _sync_astock_screen_5a,
}


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tool asynchronously without blocking the event loop."""
    handler = TOOL_MAP.get(tool_name)
    if not handler:
        return {"error": f"未知工具: {tool_name}"}

    try:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: handler(**arguments))
        return res
    except Exception as exc:
        logger.error(f"Error executing tool {tool_name} with args {arguments}: {exc}", exc_info=True)
        return {"error": f"工具执行异常: {str(exc)}"}


def extract_risk_card(tool_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract RiskCardData payload if tool result contains risk control metrics."""
    if not isinstance(tool_result, dict):
        return None

    if "breakeven_price" in tool_result and "stop_t0" in tool_result:
        return {
            "code": tool_result.get("code"),
            "name": tool_result.get("name"),
            "current_price": tool_result.get("current_price"),
            "cost": tool_result.get("cost"),
            "shares": tool_result.get("shares"),
            "breakeven_price": tool_result.get("breakeven_price"),
            "stop_t0": tool_result.get("stop_t0"),
            "stop_t1": tool_result.get("stop_t1"),
            "stop_t2": tool_result.get("stop_t2"),
            "actions": tool_result.get("action_items") or {},
        }
    return None
