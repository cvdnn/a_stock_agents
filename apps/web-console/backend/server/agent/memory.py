# -*- coding: utf-8 -*-
"""
server.agent.memory - Session Memory Management & Title Extraction Engine.
Manages multi-turn conversation memory, structured task execution results,
and intelligent intent-based session title synthesis.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from core.config import get_logger
from server.db import add_session_memory, get_session_memories

logger = get_logger("server.agent.memory")

# Common A-stock market intent action patterns
INTENT_PATTERNS = [
    (r"(调研.*(?:投资策略|策略|下周|操作)|(?:投资策略|策略|下周).*调研)", "调研与下周投资策略"),
    (r"(投资策略|下周策略|操作预案|操作策略|下周操作|下周怎么操作)", "走势研判与操作策略"),
    (r"(保本价|最低卖出价|保本|止损|盈亏平衡)", "保本价与三级止损精算"),
    (r"(选股|5a|五维|主线轮动|多因子|潜力股)", "5A多因子选股与轮动"),
    (r"(大盘|上证|指数|两市|行情研判|盘面走势)", "大盘行情与市场动向研判"),
    (r"(二次金叉|底背离|水下金叉|macd)", "MACD底背离与二次金叉"),
    (r"(退哥|短线|涨停|连板|龙头首阴)", "退哥短线接力与战法筛查"),
    (r"(辩论|多空|7大分析师|多空决议)", "多空7角色对抗辩论"),
    (r"(解套|被套|持仓诊断|持股评估)", "持仓诊断与解套决策"),
    (r"(深度调研|调研报告|调研|个股调研)", "深度调研报告"),
    (r"(后市走势|后市|走势|趋势|行情走势)", "后市走势与形态分析"),
    (r"(收益|归因|夏普|最大回撤|资产净值)", "投资收益分析与归因"),
    (r"(模拟盘|买入|卖出|撤单|持仓查询)", "模拟盘实战撮合交易"),
    (r"(筹码|主力控盘|集中度)", "筹码分布与主力动向"),
    (r"(行业|板块|资金流向|热点)", "板块轮动与资金流向"),
    (r"(诊断|体检|评估|打分)", "个股量化综合体检"),
]

# Regex for A-Stock codes (6 digits, or with market prefix like sh600519/sz000001)
STOCK_CODE_PATTERN = re.compile(r"(?<![0-9a-zA-Z])((?:sh|sz|bj)?(?:00\d{4}|30\d{4}|60\d{4}|68\d{4}|43\d{4}|83\d{4}|87\d{4}|92\d{4}))(?![0-9a-zA-Z])", re.IGNORECASE)
INDEX_CODE_PATTERN = re.compile(r"(?<![0-9a-zA-Z])(sh000001|399001|399006|000688|000300|000016|000905)(?![0-9a-zA-Z])", re.IGNORECASE)

# Common known A-stock names
COMMON_STOCK_NAMES = [
    "紫金矿业", "贵州茅台", "宁德时代", "比亚迪", "海光信息", "中芯国际", "中国平安",
    "中信证券", "中际旭创", "福晶科技", "药明康德", "隆基绿能", "通威股份", "立讯精密",
    "招商银行", "五粮液", "北方华创", "寒武纪", "中科曙光", "东方财富", "赛力斯", "工业富联"
]


class SessionMemoryManager:
    """Session Memory Central Hub managing structured memories and dynamic titles."""

    @staticmethod
    def extract_session_title(message: str) -> str:
        """
        Extract a concise, standardized session title (10-20 chars) from user message.
        Deterministic, zero-latency, high precision.
        """
        raw = (message or "").strip()
        if not raw:
            return "新投研对话"

        # 1. Check for stock code or index code
        stock_match = STOCK_CODE_PATTERN.search(raw) or INDEX_CODE_PATTERN.search(raw)
        code = stock_match.group(1) if stock_match else ""

        # Remove markdown tags, operators like @, #
        cleaned = re.sub(r"[@#][^\s]+", "", raw).strip()

        # 1.1 Check for stock name from common stock list
        matched_stock_name = ""
        for sname in COMMON_STOCK_NAMES:
            if sname in cleaned:
                matched_stock_name = sname
                break

        # 1.2 Slot regex matching for stock target: e.g. "调研紫金矿业股票信息"
        if not matched_stock_name and not code:
            slot_match = re.search(r"(?:调研|分析|看下|评估|诊断|持仓|持有|买入|卖出)\s*([A-Za-z\u4e00-\u9fa50-9]{2,8}?)(?:股票|个股|标的|\(|（|\s+|,|，|$)", cleaned)
            if slot_match:
                cand = slot_match.group(1).strip()
                excluded = {"大盘", "两市", "指数", "行情", "走势", "市场", "股票", "个股", "标的", "今日", "下周", "下月"}
                if cand not in excluded and len(cand) >= 2:
                    matched_stock_name = cand

        # 2. Check for intent action
        matched_action = ""
        for pat, action_name in INTENT_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                matched_action = action_name
                break

        # 3. Formulate standard title
        target = code or matched_stock_name
        if target and matched_action:
            if re.search(r"[\u4e00-\u9fa5]", target):
                return f"{target}{matched_action}"
            return f"{target} {matched_action}"
        elif target:
            return f"{target} 标的量化诊断"
        elif matched_action:
            return matched_action

        # 4. Fallback: clean and truncate original prompt
        clean_prompt = re.sub(r"[^\w\u4e00-\u9fff]+", " ", raw).strip()
        if len(clean_prompt) > 18:
            return clean_prompt[:18] + "..."
        return clean_prompt or "投研分析会话"

    @staticmethod
    def record_task_result(
        session_id: str,
        tool_name: str,
        args: Dict[str, Any],
        status: str,
        summary: str,
        data: Optional[Dict[str, Any]] = None,
        elapsed_ms: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Record a completed task execution outcome into session memory.
        Only successful or informative task outcomes are preserved.
        """
        if not session_id:
            return None

        # Build concise structured metadata
        meta: Dict[str, Any] = {
            "tool_name": tool_name,
            "args": args,
            "status": status,
            "elapsed_ms": elapsed_ms,
        }

        # Extract domain key (e.g. stock code if available in args or data)
        key = None
        if isinstance(args, dict):
            key = args.get("code") or args.get("symbol")
        if not key and isinstance(data, dict):
            key = data.get("code") or data.get("symbol")

        if isinstance(data, dict):
            # Extract key indicators
            extracted_facts = {}
            for field in [
                "code", "name", "price", "change_pct", "breakeven_price",
                "stop_t0", "stop_t1", "stop_t2", "total_score", "selected_count",
                "consensus", "available_cash", "total_assets", "deliverables"
            ]:
                if field in data:
                    extracted_facts[field] = data[field]
            meta["facts"] = extracted_facts

        content_text = summary or f"执行能力 [{tool_name}] 完成"

        try:
            return add_session_memory(
                session_id=session_id,
                memory_type="task_result",
                content=content_text,
                key=key or tool_name,
                meta=meta,
            )
        except Exception as e:
            logger.warning("Failed to record task memory for session %s: %s", session_id, e)
            return None

    @staticmethod
    def get_memory_context_for_llm(session_id: str, limit: int = 10) -> str:
        """
        Retrieve structured memory context to inject into LLM system prompt.
        Allows the model to recall previously executed tasks and analytical facts.
        """
        if not session_id:
            return ""

        try:
            memories = get_session_memories(session_id, memory_type="task_result", limit=limit)
            if not memories:
                return ""

            lines = ["【当前会话已沉淀的任务执行与分析记忆】:"]
            for m in memories:
                meta = m.get("meta") or {}
                tool = meta.get("tool_name", m.get("key", "task"))
                facts = meta.get("facts") or {}
                fact_parts = []
                if facts.get("code"):
                    fact_parts.append(f"标的代码: {facts.get('code')}")
                if facts.get("price"):
                    fact_parts.append(f"现价: {facts.get('price')}")
                if facts.get("breakeven_price"):
                    fact_parts.append(f"保本价: {facts.get('breakeven_price')}")
                if facts.get("total_score"):
                    fact_parts.append(f"量化分: {facts.get('total_score')}")
                if facts.get("consensus"):
                    fact_parts.append(f"辩论结论: {facts.get('consensus')}")

                facts_str = f" ({', '.join(fact_parts)})" if fact_parts else ""
                lines.append(f"- [{tool}] {m.get('content')}{facts_str}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning("Failed to retrieve LLM memory context for %s: %s", session_id, e)
            return ""
