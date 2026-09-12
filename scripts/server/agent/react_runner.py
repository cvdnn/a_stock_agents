# -*- coding: utf-8 -*-
"""
server.agent.react_runner - Agent ReAct Execution Runtime.
Coordinates LLM streaming, thoughts, tool calling, and emits universal AgentEvent objects.
Completely decouples internal deliberation from transport layer protocols.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from core.config import get_logger
from core.governance.skill_registry import get_skill_registry
from server.agent.events import (
    AgentEvent,
    ContentDeltaEvent,
    ConversationStartEvent,
    DoneEvent,
    ErrorEvent,
    RiskCardEvent,
    ThoughtEvent,
    ToolCallCompleteEvent,
    ToolCallStartEvent,
    sse_format,
)
from server.agent.prompts import AGENT_SYSTEM_PROMPT
from server.agent.tools import (
    execute_tool,
    extract_risk_card,
)
from server.config import server_settings
from server.db import add_message, create_session, get_messages, get_session, update_session_model
from server.llm.factory import LLMProviderFactory
from server.llm.errors import LLMReadinessError
from server.llm.readiness import classify_provider_error

logger = get_logger("server.agent.react_runner")


def sanitize_history_for_llm(history_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sanitize and construct an OpenAI-compliant messages list from database history.
    Strictly guarantees:
    1. A 'tool' role message can ONLY follow an 'assistant' message whose 'tool_calls'
       contains a matching 'id'. Orphaned tool messages are dropped.
    2. An 'assistant' message with 'tool_calls' has its tool_calls filtered to only those
       that were answered, or stripped entirely if no tool answers follow.
    3. Prevents 400 Bad Request 'Messages with role tool must be a response to a preceding message with tool_calls'.
    """
    parsed: List[Dict[str, Any]] = []
    for row in history_rows:
        r = row.get("role")
        if r == "user":
            parsed.append({"role": "user", "content": row.get("content") or ""})
        elif r == "assistant":
            tc = row.get("tool_calls")
            if isinstance(tc, str):
                try:
                    tc = json.loads(tc)
                except Exception:
                    tc = None
            parsed.append({
                "role": "assistant",
                "content": row.get("content") or "",
                "tool_calls": tc if isinstance(tc, list) else None,
            })
        elif r == "tool":
            parsed.append({
                "role": "tool",
                "tool_call_id": row.get("tool_call_id") or "",
                "name": row.get("tool_name") or "",
                "content": row.get("content") or "{}",
            })

    result: List[Dict[str, Any]] = []
    i = 0
    while i < len(parsed):
        item = parsed[i]
        if item["role"] == "user":
            result.append(item)
            i += 1
        elif item["role"] == "tool":
            # Orphaned tool message! Skip to avoid OpenAI 400 Bad Request
            logger.warning("Dropping orphaned tool message from LLM context: %s", item.get("tool_call_id"))
            i += 1
        elif item["role"] == "assistant":
            tc = item.get("tool_calls")
            if not tc:
                result.append({"role": "assistant", "content": item["content"]})
                i += 1
            else:
                needed_ids = {c["id"] for c in tc if isinstance(c, dict) and "id" in c}
                tool_msgs: List[Dict[str, Any]] = []
                j = i + 1
                while j < len(parsed) and parsed[j]["role"] == "tool":
                    if parsed[j]["tool_call_id"] in needed_ids:
                        tool_msgs.append(parsed[j])
                    j += 1

                answered_ids = {tm["tool_call_id"] for tm in tool_msgs}
                if answered_ids:
                    filtered_tc = [c for c in tc if c.get("id") in answered_ids]
                    result.append({
                        "role": "assistant",
                        "content": item["content"],
                        "tool_calls": filtered_tc,
                    })
                    result.extend(tool_msgs)
                    i = j
                else:
                    content = item["content"].strip()
                    if content:
                        result.append({"role": "assistant", "content": content})
                    i = j

    return result


class AgentReActRunner:
    """Agent runtime managing multi-turn conversation, Skill Governance, and typed AgentEvents."""

    MAX_REACT_STEPS = 5

    def __init__(self, default_model: Optional[str] = None) -> None:
        self.default_model = default_model

    async def run_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        tools_enabled: bool = True,
    ) -> AsyncIterator[AgentEvent]:
        """
        Execute ReAct loop and yield strongly-typed AgentEvent domain objects.
        Directly consumable by in-process clients (TUI / Desktop Sidecar).
        """
        start_time = time.time()
        requested_model = model or self.default_model

        try:
            provider = LLMProviderFactory.get_provider(
                model=requested_model,
                role=None if requested_model else "chat",
                require_tools=tools_enabled,
            )
        except Exception as exc:
            failure = classify_provider_error(exc)
            logger.error("LLM readiness gate failed: %s", failure.code)
            yield ErrorEvent(error=str(failure), code=failure.code)
            return

        selected_model = provider.model_name

        # 1. Resolve or create session
        sid = session_id
        if sid:
            sess = get_session(sid)
            if not sess:
                sess = create_session(session_id=sid, title=message[:20], model=selected_model)
            elif sess.get("model") != selected_model and selected_model:
                try:
                    update_session_model(session_id=sid, model=selected_model)
                except Exception:
                    pass
        else:
            title = message[:25] + ("..." if len(message) > 25 else "")
            sess = create_session(title=title, model=selected_model)
            sid = sess["session_id"]

        # 2. Record User message in database
        add_message(session_id=sid, role="user", content=message)

        # 3. Emit conversation_start event
        yield ConversationStartEvent(session_id=sid, model=selected_model)

        try:
            # 4. Prepare message history for LLM with state machine sanitization
            history_rows = get_messages(session_id=sid, limit=30)
            clean_history = sanitize_history_for_llm(history_rows)
            llm_messages: List[Dict[str, Any]] = [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT}
            ] + clean_history

            total_tokens = 0
            step = 0
            had_tool_failure = False

            # Obtain tools from Skill Governance Registry
            registry = get_skill_registry()
            tools_to_pass = registry.to_openai_tools(enabled_only=True) if tools_enabled else None

            # 5. ReAct iteration loop
            while step < self.MAX_REACT_STEPS:
                step += 1
                accumulated_text = ""
                accumulated_thought = ""
                accumulated_tool_calls: List[Dict[str, Any]] = []

                stream_gen = provider.stream_chat(
                    messages=llm_messages,
                    tools=tools_to_pass,
                    temperature=0.2,
                )

                async for chunk in stream_gen:
                    if chunk.usage:
                        total_tokens = chunk.usage.get("total_tokens", total_tokens)

                    # Stream thought/reasoning
                    if chunk.thought:
                        accumulated_thought += chunk.thought
                        yield ThoughtEvent(content=chunk.thought)

                    # Stream text delta
                    if chunk.delta_text:
                        accumulated_text += chunk.delta_text
                        yield ContentDeltaEvent(text=chunk.delta_text)

                    # Stream tool calls
                    if chunk.tool_calls:
                        accumulated_tool_calls.extend(chunk.tool_calls)

                # Deduplicate tool calls if provider emitted multiple or duplicates
                deduped_tool_calls: List[Dict[str, Any]] = []
                seen_call_ids = set()
                for tc in accumulated_tool_calls:
                    cid = tc.get("id")
                    if cid:
                        if cid in seen_call_ids:
                            continue
                        seen_call_ids.add(cid)
                    deduped_tool_calls.append(tc)
                accumulated_tool_calls = deduped_tool_calls

                # If assistant generated text, add to LLM context
                if accumulated_text or accumulated_thought or accumulated_tool_calls:
                    asst_msg: Dict[str, Any] = {
                        "role": "assistant",
                        "content": accumulated_text,
                    }
                    if accumulated_tool_calls:
                        asst_msg["tool_calls"] = accumulated_tool_calls
                    llm_messages.append(asst_msg)

                # Persist assistant step to database
                if accumulated_tool_calls:
                    add_message(
                        session_id=sid,
                        role="assistant",
                        content=accumulated_text,
                        thought=accumulated_thought if accumulated_thought else None,
                        tool_calls=accumulated_tool_calls,
                    )
                else:
                    add_message(
                        session_id=sid,
                        role="assistant",
                        content=accumulated_text,
                        thought=accumulated_thought if accumulated_thought else None,
                    )
                    break

                # Otherwise, execute requested tools and feed back observations
                for tc in accumulated_tool_calls:
                    call_id = tc.get("id", f"call_{step}")
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    raw_args = fn.get("arguments", "{}")

                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args = {}

                    # Emit ToolCallStartEvent
                    yield ToolCallStartEvent(
                        call_id=call_id,
                        skill_id=fn_name,
                        action=fn_name,
                        args=args if isinstance(args, dict) else {},
                    )

                    # Execute tool via executor
                    tool_res = await execute_tool(fn_name, args if isinstance(args, dict) else {})

                    status = tool_res.get("status", "error") if isinstance(tool_res, dict) else "error"
                    if status != "success":
                        had_tool_failure = True

                    # Risk cards are success artifacts and must never be emitted for failed observations.
                    risk_card = extract_risk_card(tool_res) if status == "success" else None
                    if risk_card:
                        yield RiskCardEvent(
                            breakeven_price=risk_card["breakeven_price"],
                            stop_t0=risk_card["stop_t0"],
                            stop_t1=risk_card["stop_t1"],
                            stop_t2=risk_card["stop_t2"],
                            code=risk_card.get("code"),
                            name=risk_card.get("name"),
                            cost=risk_card.get("cost"),
                            shares=risk_card.get("shares"),
                            actions=risk_card.get("actions"),
                        )

                    # Summary for complete event
                    summary = {
                        "unavailable": "能力当前不可用",
                        "timeout": "调用超时",
                        "error": "调用失败",
                        "confirmation_required": "等待用户确认",
                    }.get(status, "调用成功")
                    if status == "success" and "price" in tool_res and "change_pct" in tool_res:
                        summary = f"现价 {tool_res['price']} ({tool_res['change_pct']:+.2f}%)"
                    elif status == "success" and "breakeven_price" in tool_res:
                        summary = f"保本价 {tool_res['breakeven_price']} (止损T0: {tool_res.get('stop_t0')})"
                    elif status == "success" and "total_score" in tool_res:
                        summary = f"量化总分 {tool_res['total_score']} 分"
                    elif status == "success" and "selected_count" in tool_res:
                        summary = f"初选入围 {tool_res['selected_count']} 只标的"
                    elif status == "success" and "pool_type" in tool_res and "count" in tool_res:
                        summary = f"股票池 [{tool_res['pool_type']}] 查询完成 (共 {tool_res['count']} 只标的)"
                    elif status == "success" and tool_res.get("action") == "positions":
                        summary = f"持仓标的查询完成 (共 {tool_res.get('count', len(tool_res.get('positions', [])))} 只标的)"
                    elif status == "success" and "total_pools" in tool_res:
                        summary = tool_res.get("summary") or f"股票池审查完成 (共 {tool_res.get('total_stocks', 0)} 只标的)"
                    elif status == "success" and tool_res.get("action") == "balance" and "available_cash" in tool_res:
                        summary = f"可用资金 ¥{tool_res['available_cash']:,.2f} | 总资产 ¥{tool_res.get('total_assets', 0.0):,.2f}"

                    # Emit ToolCallCompleteEvent
                    yield ToolCallCompleteEvent(
                        call_id=call_id,
                        skill_id=fn_name,
                        status=status,
                        summary=summary,
                        data=tool_res if isinstance(tool_res, dict) else None,
                    )

                    # Store tool execution in DB
                    tool_json_str = json.dumps(tool_res, ensure_ascii=False)
                    add_message(
                        session_id=sid,
                        role="tool",
                        content=tool_json_str,
                        tool_call_id=call_id,
                        tool_name=fn_name,
                        risk_card=risk_card,
                    )

                    # Append tool message to context for next ReAct step
                    llm_messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": fn_name,
                        "content": tool_json_str,
                    })

            # 6. Emit DoneEvent
            elapsed_ms = int((time.time() - start_time) * 1000)
            yield DoneEvent(
                total_tokens=total_tokens,
                elapsed_ms=elapsed_ms,
                finish_reason="tool_failure" if had_tool_failure else "stop",
            )

        except Exception as exc:
            logger.error(f"ReAct runtime error: {exc}", exc_info=True)
            failure = classify_provider_error(exc)
            yield ErrorEvent(error=str(failure), code=failure.code)

    async def run_chat_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        tools_enabled: bool = True,
    ) -> AsyncIterator[str]:
        """
        Protocol Adapter for Server-Sent Events (SSE).
        Wraps run_chat domain event generator and formats to wire specification:
        event: <type>\\ndata: <json>\\n\\n
        """
        async for event in self.run_chat(
            message=message,
            session_id=session_id,
            model=model,
            tools_enabled=tools_enabled,
        ):
            yield sse_format(event)
