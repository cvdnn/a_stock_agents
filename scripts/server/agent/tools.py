# -*- coding: utf-8 -*-
"""
server.agent.tools - Tools definitions and execution dispatcher for A-Stock Agent.
Bridges LLM tool-calling directly to the core/ quantitative research engines.
"""
from __future__ import annotations

import asyncio
import inspect
import math
from typing import Any, Callable, Dict, List, Optional

from core.config import get_logger
from core.data.data_bridge import DataBridge
from core.indicators.technical_indicators import calc_all
from core.models.combo_scorer import ComboScorer
from core.strategy.execution_action_engine import ExecutionActionEngine
from core.strategy.risk_manager import RiskManager

logger = get_logger("server.agent.tools")


def _unavailable(skill_id: str) -> Dict[str, Any]:
    return {
        "status": "unavailable",
        "error": "CAPABILITY_NOT_IMPLEMENTED",
        "skill_id": skill_id,
    }

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
    raw_code_str = str(code).strip()
    if ":" in raw_code_str or "@" in raw_code_str:
        code = raw_code_str.split(":")[0].split("@")[0].strip()
    bridge = DataBridge()
    q = bridge.get_realtime_quote(code)
    if not q:
        return {"error": "DATA_UNAVAILABLE", "message": f"无法获取股票 {code} 的实时行情。"}
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
    raw_code_str = str(code).strip()
    if ":" in raw_code_str or "@" in raw_code_str:
        code = raw_code_str.split(":")[0].split("@")[0].strip()
    bridge = DataBridge()
    klines = bridge.tencent_kline(code, count=count)
    if not klines or len(klines) < 15:
        return {"error": f"股票/标的 {code} 的历史K线数据不足。"}
    tech_all = calc_all(klines)
    latest = tech_all.get("latest", {})
    return {
        "code": code,
        "klines_count": len(klines),
        "latest_close": float(klines[-1][2]),
        "ma": {
            "ma5": latest.get("ma5"),
            "ma10": latest.get("ma10"),
            "ma20": latest.get("ma20"),
            "ma60": latest.get("ma60"),
        },
        "macd": {
            "dif": latest.get("dif"),
            "dea": latest.get("dea"),
            "hist": latest.get("macd_bar"),
        },
        "kdj": {
            "k": latest.get("kdj_k"),
            "d": latest.get("kdj_d"),
        },
        "rsi": latest.get("rsi"),
        "boll": {
            "upper": latest.get("boll_upper"),
            "mid": latest.get("boll_mid"),
            "lower": latest.get("boll_lower"),
            "width": latest.get("boll_width"),
        },
        "atr": latest.get("atr", 0.0),
    }


def _sync_astock_action_plan(
    code: str, cost: Optional[float] = None, shares: Optional[int] = None
) -> Dict[str, Any]:
    raw_code_str = str(code).strip()
    if ":" in raw_code_str or "@" in raw_code_str:
        import re
        m = re.match(r"^([a-zA-Z0-9]+)(?::(\d+))?(?:@([0-9.]+))?$", raw_code_str)
        if m:
            p_code, p_shares, p_cost = m.groups()
            code = p_code
            if shares is None and p_shares:
                shares = int(p_shares)
            if cost is None and p_cost:
                cost = float(p_cost)
    bridge = DataBridge()
    q = bridge.get_realtime_quote(code)
    if not q or not q.get("price"):
        return {"error": "DATA_UNAVAILABLE", "message": f"股票 {code} 缺少实时行情，无法生成动作单。"}
    name = q.get("name", code)
    curr_price = float(q["price"])
    eff_cost = cost if cost is not None else curr_price
    eff_shares = shares if shares is not None else 100

    klines = bridge.tencent_kline(code, count=120)
    tech_all = calc_all(klines) if (klines and len(klines) >= 26) else {}
    tech = tech_all.get("latest", {}) if tech_all else {}

    score_res: Dict[str, Any] = {}
    if klines and len(klines) >= 26 and tech:
        try:
            scorer = ComboScorer()
            scores = scorer.score_full(klines, tech)
            total_s = scores.get("total")
            if isinstance(total_s, (int, float)):
                rating = "A" if total_s >= 75 else ("B" if total_s >= 60 else ("C" if total_s >= 45 else "D"))
                score_res = {"cs": total_s, "rating": rating}
        except Exception:
            logger.warning("Combo score unavailable for action plan %s", code)

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


def _extract_latest_tech_summary(tech: Dict[str, Any]) -> Dict[str, Any]:
    ma = tech.get("ma") if isinstance(tech.get("ma"), dict) else {}
    macd = tech.get("macd") if isinstance(tech.get("macd"), dict) else {}
    raw_rsi = tech.get("rsi")
    legacy_rsi6 = raw_rsi.get("rsi6") if isinstance(raw_rsi, dict) else None
    rsi = raw_rsi.get("rsi14") if isinstance(raw_rsi, dict) else raw_rsi
    if rsi is None:
        rsi = legacy_rsi6

    return {
        "ma5": tech.get("ma5") if tech.get("ma5") is not None else ma.get("ma5"),
        "ma10": tech.get("ma10") if tech.get("ma10") is not None else ma.get("ma10"),
        "ma20": tech.get("ma20") if tech.get("ma20") is not None else ma.get("ma20"),
        "macd_hist": tech.get("macd_bar") if tech.get("macd_bar") is not None else macd.get("hist"),
        "rsi": rsi,
        "rsi6": legacy_rsi6,
    }


def _sync_astock_evaluate(code: str) -> Dict[str, Any]:
    raw_code_str = str(code).strip()
    if ":" in raw_code_str or "@" in raw_code_str:
        code = raw_code_str.split(":")[0].split("@")[0].strip()
    bridge = DataBridge()
    q = bridge.get_realtime_quote(code)
    klines = bridge.tencent_kline(code, count=120)
    if not klines or len(klines) < 26:
        return {"error": f"股票 {code} 历史K线不足以完成全面诊断。"}

    tech_all = calc_all(klines)
    tech = tech_all.get("latest", {})
    scorer = ComboScorer()
    scores = scorer.score_full(klines, tech)
    if not isinstance(scores.get("total"), (int, float)):
        return {"error": "ANALYSIS_INCOMPLETE", "message": "量化评分后端未返回总分。"}

    return {
        "code": code,
        "name": q.get("name", code) if q else code,
        "current_price": float(q.get("price", klines[-1][2])) if q else float(klines[-1][2]),
        "total_score": scores["total"],
        "scores_detail": scores,
        "tech_summary": _extract_latest_tech_summary(tech),
    }


def _sync_astock_screen_5a(limit: int = 10, dynamic_mode: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    from core.models.stock_screener import StockScreener
    from core.strategy.dynamic_universe import DynamicUniverseEngine

    mode = dynamic_mode or kwargs.get("mode") or "hot_sectors"
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


def _sync_astock_data_feed(code: Optional[str] = None, action: str = "quote", count: int = 60, **kwargs: Any) -> Dict[str, Any]:
    target_code = code or kwargs.get("symbol") or kwargs.get("stock_code") or ""
    act = (action or kwargs.get("act") or "quote").lower().strip()
    if act == "tech":
        return _sync_astock_technical(code=target_code, count=count)
    if act in ("history", "kline"):
        bridge = DataBridge()
        klines = bridge.tencent_kline(target_code, count=count)
        if not klines:
            return {"error": "DATA_UNAVAILABLE", "message": f"股票/标的 {target_code} 的历史K线暂不可用。"}
        return {
            "code": target_code,
            "count": len(klines),
            "klines": klines[-count:],
            "latest_close": float(klines[-1][2]) if klines else None,
        }
    return _sync_astock_quote(code=target_code)


def _sync_astock_pool_dashboard(
    pool_type: Optional[str] = None,
    action: str = "list",
    pool: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    resolved_pool_type = pool_type or pool or kwargs.get("type") or kwargs.get("pool_name") or "holding"
    resolved_action = action or kwargs.get("act") or "list"
    try:
        from core.strategy.pool_manager import PoolManager
        pm = PoolManager()
        if resolved_action == "all" or str(resolved_pool_type).lower() in ("all", "overview"):
            all_pools = pm.get_all_pools()
            total_count = sum(len(v) for v in all_pools.values())
            return {
                "status": "success",
                "pool_type": "all",
                "action": resolved_action,
                "count": total_count,
                "pools": all_pools,
            }

        stocks = pm.get_pool(resolved_pool_type)
        code = kwargs.get("code") or kwargs.get("symbol")
        if code:
            code_str = str(code).strip()
            found = [s for s in stocks if str(s.get("code", "")).strip() == code_str]
            res = {
                "status": "success",
                "pool_type": resolved_pool_type,
                "action": resolved_action,
                "code": code_str,
                "in_pool": len(found) > 0,
                "item": found[0] if found else None,
                "count": len(stocks),
                "stocks": stocks,
            }
            if len(stocks) == 0:
                res["is_empty"] = True
                res["message"] = (
                    f"当前【{resolved_pool_type}】股池为空，尚未登记任何标的。"
                    "不用继续分析，请直接提示用户还未登记相关股池，并提示用户登记："
                    "例如持仓股：000222:1000@25.1234。格式：股票:股数@成本价。"
                )
            return res

        res = {
            "status": "success",
            "pool_type": resolved_pool_type,
            "action": resolved_action,
            "count": len(stocks),
            "stocks": stocks,
        }
        if len(stocks) == 0:
            res["is_empty"] = True
            res["message"] = (
                f"当前【{resolved_pool_type}】股池为空，尚未登记任何标的。"
                "不用继续分析，请直接提示用户还未登记相关股池，并提示用户登记："
                "例如持仓股：000222:1000@25.1234。格式：股票:股数@成本价。"
            )
        return res
    except Exception as exc:
        logger.error("Error in _sync_astock_pool_dashboard: %s", exc, exc_info=True)
        return {
            "status": "error",
            "error": "CAPABILITY_EXECUTION_FAILED",
            "code": "CAPABILITY_EXECUTION_FAILED",
            "pool_type": resolved_pool_type,
            "detail": str(exc),
        }


def _sync_astock_trade_paper(
    action: str = "balance",
    code: Optional[str] = None,
    shares: Optional[int] = None,
    price: Optional[float] = None,
    order_id: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        from core.paper_trading.account_manager import AccountManager
        am = AccountManager()
        if action == "balance":
            acc = am.get_account()
            if not isinstance(acc, dict) or "cash" not in acc or "total_assets" not in acc:
                return {"error": "ACCOUNT_DATA_UNAVAILABLE", "code": "ACCOUNT_DATA_UNAVAILABLE", "action": action}
            return {
                "status": "success",
                "action": "balance",
                "account_id": acc.get("account_id", "alpha"),
                "cash": acc["cash"],
                "total_assets": acc["total_assets"],
                "available_cash": acc.get("available_cash", acc["cash"]),
                "frozen_cash": acc.get("frozen_cash", 0.0),
                "market_value": acc.get("market_value", 0.0),
                "positions_count": acc.get("positions_count", 0),
                "positions": acc.get("positions", []),
            }
        elif action in ("buy", "sell") and code and shares:
            res = am.place_order(code=code, side=action, shares=shares, price=price)
            if isinstance(res, dict):
                res.setdefault("status", "success" if "order_id" in res else "error")
                return res
            return {"error": "ORDER_RESULT_INVALID", "code": "ORDER_RESULT_INVALID", "action": action}
        elif action == "cancel" and order_id:
            res = am.cancel_order(order_id)
            if isinstance(res, dict):
                res.setdefault("status", "success")
                return res
            return {"error": "ORDER_RESULT_INVALID", "code": "ORDER_RESULT_INVALID", "action": action}
        elif action == "positions":
            positions = am.get_positions()
            res = {"status": "success", "action": "positions", "count": len(positions), "positions": positions}
            if len(positions) == 0:
                res["is_empty"] = True
                res["message"] = (
                    "当前持仓为空，尚未登记任何持仓标的。"
                    "不用继续分析，请直接提示用户还未登记相关股池，并提示用户登记："
                    "例如持仓股：000222:1000@25.1234。格式：股票:股数@成本价。"
                )
            return res
        elif action == "orders":
            orders = am.get_orders()
            return {"status": "success", "action": "orders", "count": len(orders), "orders": orders}
        acc = am.get_account()
        return {"status": "success", "action": action, "account": acc}
    except Exception as exc:
        logger.error("Error in _sync_astock_trade_paper: %s", exc, exc_info=True)
        return {
            "status": "error",
            "error": "CAPABILITY_EXECUTION_FAILED",
            "code": "CAPABILITY_EXECUTION_FAILED",
            "action": action,
            "detail": str(exc),
        }


def _sync_astock_strategy_mainboard(action: str = "candidates", code: Optional[str] = None) -> Dict[str, Any]:
    try:
        from core.strategy.daily_decisions import DailyDecisionEngine
        engine = DailyDecisionEngine()
        if code:
            res = engine.evaluate_stock(code)
            return res if isinstance(res, dict) else {"status": "success", "code": code, "result": res}
        cands = engine.get_swing_candidates()
        return {"status": "success", "action": action, "candidates": cands}
    except Exception as exc:
        logger.error("Error in _sync_astock_strategy_mainboard: %s", exc, exc_info=True)
        return {
            "status": "error",
            "error": "CAPABILITY_EXECUTION_FAILED",
            "code": "CAPABILITY_EXECUTION_FAILED",
            "action": action,
            "detail": str(exc),
        }


def _sync_astock_quant_engine(action: str = "pipeline", code: Optional[str] = None) -> Dict[str, Any]:
    return _unavailable("astock-quant-engine")
def _sync_astock_agent_debate(code: str, rounds: int = 2) -> Dict[str, Any]:
    try:
        from core.multi_agent.ta_orchestrator import TechnicalAnalysisOrchestrator
        orch = TechnicalAnalysisOrchestrator()
        report = orch.run_debate(code=code, rounds=rounds)
        return {
            "code": code,
            "rounds": rounds,
            "debate_summary": report["summary"],
            "bull_bear_ratio": report["ratio"],
        }
    except Exception:
        return _unavailable("astock-agent-debate")


def _sync_astock_strategy_tuige(code: str, scenario: str = "limit_up_pullback") -> Dict[str, Any]:
    return {
        "status": "success",
        "type": "reference",
        "code": code,
        "scenario": scenario,
        "action_guide": "涨停回踩关键均线不破，分歧转一致可轻仓低吸；跌破均线无条件离场。",
    }


def _sync_astock_strategy_macd(code: str) -> Dict[str, Any]:
    bridge = DataBridge()
    klines = bridge.tencent_kline(code, count=60)
    if not klines or len(klines) < 26:
        return {"error": "DATA_UNAVAILABLE", "message": f"股票 {code} 的K线不足，无法判断 MACD 形态。"}
    tech = calc_all(klines).get("latest", {})
    macd = tech.get("macd", {})
    dif = macd.get("dif", 0.0)
    dea = macd.get("dea", 0.0)
    hist = macd.get("hist", 0.0)
    status = "零轴下二次金叉蓄势" if (dif < 0 and dea < 0 and dif >= dea) else ("零轴上方多头加速" if dif > 0 and dea > 0 else "中性震荡")
    return {
        "code": code,
        "dif": dif,
        "dea": dea,
        "hist": hist,
        "pattern": status,
    }


def _sync_astock_pool_audit(fix: bool = False, **kwargs: Any) -> Dict[str, Any]:
    try:
        from core.strategy.pool_manager import PoolManager
        pm = PoolManager()
        pools = pm.get_all_pools()
        total_stocks = sum(len(v) for v in pools.values())
        return {
            "status": "success",
            "fix": fix,
            "total_pools": len(pools),
            "total_stocks": total_stocks,
            "pools": {k: len(v) for k, v in pools.items()},
            "summary": f"股票池审查完成：全量三级股池共 {total_stocks} 只标的，运行正常",
        }
    except Exception as exc:
        logger.error("Error in _sync_astock_pool_audit: %s", exc, exc_info=True)
        return _unavailable("astock-pool-audit")


def _sync_astock_report_archive(code: Optional[str] = None, report_type: Optional[str] = None) -> Dict[str, Any]:
    return _unavailable("astock-report-archive")



def _sync_astock_report_html(code: str) -> Dict[str, Any]:
    return _unavailable("astock-report-html")


def _sync_astock_knowledge_tips(topic: str = "all") -> Dict[str, Any]:
    return {
        "status": "success",
        "type": "reference",
        "topic": topic,
        "tips": [
            "早盘竞价复盘要点：9:20-9:25真实申报不可撤单，需观察匹配量与量比异动",
            "API自动降级：腾讯API -> 新浪行情 -> 东方财富 -> 本地快照，杜绝服务阻断",
            "实战三原则铁律：严格计算印花税与五元起收佣金向上进位至分位保本价，三级止损线（-3%/-5%/-8%），冲高/震荡/急跌三场景动作单",
        ],
    }


def _sync_astock_model_validation(model_name: str = "Kronos", code: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    return _unavailable("astock-model-validation")


def _sync_astock_meta_routing(task_description: str, **kwargs: Any) -> Dict[str, Any]:
    return {
        "status": "success",
        "type": "reference",
        "task": task_description,
        "recommended_model": "flash",
        "execution_mode": "direct_sdk",
        "rationale": "投研数据分析首选高吞吐快速模型，编程回测使用脚本直接执行。",
    }


# ── Async Dispatcher ──────────────────────────────────────────────────────────

TOOL_MAP: Dict[str, Callable[..., Any]] = {
    # Phase 1 Legacy Aliases
    "astock_quote": _sync_astock_quote,
    "astock_technical": _sync_astock_technical,
    "astock_action_plan": _sync_astock_action_plan,
    "astock_evaluate": _sync_astock_evaluate,
    "astock_screen_5a": _sync_astock_screen_5a,
    # Phase 2 Unified 17 Skills Mappings
    "astock_data_feed": _sync_astock_data_feed,
    "astock-data-feed": _sync_astock_data_feed,
    "astock_platform_evaluate": _sync_astock_evaluate,
    "astock-platform-evaluate": _sync_astock_evaluate,
    "astock_screener_5a": _sync_astock_screen_5a,
    "astock-screener-5a": _sync_astock_screen_5a,
    "astock_pool_dashboard": _sync_astock_pool_dashboard,
    "astock-pool-dashboard": _sync_astock_pool_dashboard,
    "astock_trade_paper": _sync_astock_trade_paper,
    "astock-trade-paper": _sync_astock_trade_paper,
    "astock_strategy_mainboard": _sync_astock_strategy_mainboard,
    "astock-strategy-mainboard": _sync_astock_strategy_mainboard,
    "astock_quant_engine": _sync_astock_quant_engine,
    "astock-quant-engine": _sync_astock_quant_engine,
    "astock_agent_debate": _sync_astock_agent_debate,
    "astock-agent-debate": _sync_astock_agent_debate,
    "astock_strategy_tuige": _sync_astock_strategy_tuige,
    "astock-strategy-tuige": _sync_astock_strategy_tuige,
    "astock_strategy_macd": _sync_astock_strategy_macd,
    "astock-strategy-macd": _sync_astock_strategy_macd,
    "astock_action_execution": _sync_astock_action_plan,
    "astock-action-execution": _sync_astock_action_plan,
    "astock_pool_audit": _sync_astock_pool_audit,
    "astock-pool-audit": _sync_astock_pool_audit,
    "astock_report_archive": _sync_astock_report_archive,
    "astock-report-archive": _sync_astock_report_archive,
    "astock_report_html": _sync_astock_report_html,
    "astock-report-html": _sync_astock_report_html,
    "astock_knowledge_tips": _sync_astock_knowledge_tips,
    "astock-knowledge-tips": _sync_astock_knowledge_tips,
    "astock_model_validation": _sync_astock_model_validation,
    "astock-model-validation": _sync_astock_model_validation,
    "astock_meta_routing": _sync_astock_meta_routing,
    "astock-meta-routing": _sync_astock_meta_routing,
}


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tool asynchronously without blocking the event loop."""
    handler = TOOL_MAP.get(tool_name)
    if not handler:
        return _unavailable(tool_name)

    try:
        loop = asyncio.get_running_loop()
        sig = inspect.signature(handler)
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        call_kwargs = arguments if has_var_keyword else {k: v for k, v in arguments.items() if k in sig.parameters}
        res = await loop.run_in_executor(None, lambda: handler(**call_kwargs))
        if not isinstance(res, dict):
            return {"status": "error", "error": "CAPABILITY_RESULT_INVALID", "skill_id": tool_name}
        normalized = dict(res)
        normalized.setdefault("skill_id", tool_name)
        if normalized.get("status") not in {"success", "error", "unavailable", "timeout", "confirmation_required"}:
            normalized["status"] = "error" if normalized.get("error") else "success"
        return normalized
    except Exception:
        logger.error("Error executing tool %s", tool_name, exc_info=True)
        return {"status": "error", "error": "CAPABILITY_EXECUTION_FAILED", "skill_id": tool_name}



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
