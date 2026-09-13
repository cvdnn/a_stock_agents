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
    (r"(保本价|最低卖出价|保本|止损|盈亏平衡)", "保本价与三级止损精算"),
    (r"(选股|5a|五维|主线轮动|多因子)", "5A多因子选股与轮动"),
    (r"(大盘|上证|指数|两市|行情研判|盘面走势)", "大盘行情与市场动向研判"),
    (r"(二次金叉|底背离|水下金叉|macd)", "MACD底背离与二次金叉"),
    (r"(退哥|短线|涨停|连板|龙头首阴)", "退哥短线接力与战法筛查"),
    (r"(辩论|多空|7大分析师|多空决议)", "多空7角色对抗辩论"),
    (r"(解套|被套|持仓诊断|持股评估)", "持仓诊断与解套决策"),
    (r"(收益|归因|夏普|最大回撤|资产净值)", "投资收益分析与归因"),
    (r"(模拟盘|买入|卖出|撤单|持仓查询)", "模拟盘实战撮合交易"),
    (r"(筹码|主力控盘|集中度)", "筹码分布与主力动向"),
    (r"(行业|板块|资金流向|热点)", "板块轮动与资金流向"),
    (r"(诊断|体检|评估|打分)", "个股量化综合体检"),
]

# Regex for A-Stock codes (6 digits, or with market prefix like sh600519/sz000001)
STOCK_CODE_PATTERN = re.compile(r"\b((?:sh|sz|bj)?(?:00\d{4}|30\d{4}|60\d{4}|68\d{4}|43\d{4}|83\d{4}|87\d{4}|92\d{4}))\b", re.IGNORECASE)
INDEX_CODE_PATTERN = re.compile(r"\b(sh000001|399001|399006|000688|000300|000016|000905)\b", re.IGNORECASE)


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

        # 2. Check for intent action
        matched_action = ""
        for pat, action_name in INTENT_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                matched_action = action_name
                break

        # 3. Formulate standard title
        if code and matched_action:
            return f"{code} {matched_action}"
        elif code:
            return f"{code} 标的量化诊断"
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
