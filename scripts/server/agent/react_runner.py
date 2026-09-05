# -*- coding: utf-8 -*-
"""
server.agent.react_runner - Agent ReAct Execution Runtime.
Coordinates LLM streaming, thoughts, tool calling, and SSE event streaming.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from core.config import get_logger
from server.agent.prompts import AGENT_SYSTEM_PROMPT
from server.agent.tools import (
    TOOLS_DEFINITIONS,
    execute_tool,
    extract_risk_card,
)
from server.config import server_settings
from server.db import add_message, create_session, get_messages, get_session
from server.llm.factory import LLMProviderFactory

logger = get_logger("server.agent.react_runner")


class AgentReActRunner:
    """Agent runtime managing multi-turn conversation and tool execution loop."""

    MAX_REACT_STEPS = 5

    def __init__(self, default_model: Optional[str] = None) -> None:
        self.default_model = default_model or server_settings.default_model

    async def run_chat_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        tools_enabled: bool = True,
    ) -> AsyncIterator[str]:
        """
        Stream chat responses formatted as Server-Sent Events (SSE).
        Yields strings formatted according to the spec:
        event: <type>\\ndata: <json>\\n\\n
        """
        start_time = time.time()
        selected_model = model or self.default_model

        # 1. Resolve or create session
        sid = session_id
        if sid:
            sess = get_session(sid)
            if not sess:
                sess = create_session(session_id=sid, title=message[:20], model=selected_model)
        else:
            title = message[:25] + ("..." if len(message) > 25 else "")
            sess = create_session(title=title, model=selected_model)
            sid = sess["session_id"]

        # 2. Record User message in database
        add_message(session_id=sid, role="user", content=message)

        # 3. Emit conversation_start event
        yield (
            f"event: conversation_start\n"
            f"data: {json.dumps({'session_id': sid, 'model': selected_model}, ensure_ascii=False)}\n\n"
        )

        try:
            # 4. Prepare message history for LLM
            history_rows = get_messages(session_id=sid, limit=30)
            llm_messages: List[Dict[str, Any]] = [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT}
            ]
            for row in history_rows:
                r = row["role"]
                if r == "user":
                    llm_messages.append({"role": "user", "content": row["content"]})
                elif r == "assistant":
                    msg_obj: Dict[str, Any] = {"role": "assistant", "content": row["content"]}
                    if row.get("tool_calls"):
                        msg_obj["tool_calls"] = row["tool_calls"]
                    llm_messages.append(msg_obj)
                elif r == "tool":
                    llm_messages.append({
                        "role": "tool",
                        "tool_call_id": row.get("tool_call_id") or "call_0",
                        "name": row.get("tool_name") or "",
                        "content": row["content"],
                    })

            provider = LLMProviderFactory.get_provider(model=selected_model)
            total_tokens = 0
            step = 0

            # 5. ReAct iteration loop
            while step < self.MAX_REACT_STEPS:
                step += 1
                accumulated_text = ""
                accumulated_thought = ""
                accumulated_tool_calls: List[Dict[str, Any]] = []

                tools_to_pass = TOOLS_DEFINITIONS if tools_enabled else None

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
                        yield (
                            f"event: thought\n"
                            f"data: {json.dumps({'content': chunk.thought}, ensure_ascii=False)}\n\n"
                        )

                    # Stream text delta
                    if chunk.delta_text:
                        accumulated_text += chunk.delta_text
                        yield (
                            f"event: content_delta\n"
                            f"data: {json.dumps({'text': chunk.delta_text}, ensure_ascii=False)}\n\n"
                        )

                    # Stream tool calls
                    if chunk.tool_calls:
                        accumulated_tool_calls.extend(chunk.tool_calls)

                # If assistant generated text, add to LLM context
                if accumulated_text or accumulated_thought or accumulated_tool_calls:
                    asst_msg: Dict[str, Any] = {
                        "role": "assistant",
                        "content": accumulated_text,
                    }
                    if accumulated_tool_calls:
                        asst_msg["tool_calls"] = accumulated_tool_calls
                    llm_messages.append(asst_msg)

                # If no tool calls were requested, conversation turn is complete
                if not accumulated_tool_calls:
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

                    # Emit tool_call_start
                    yield (
                        f"event: tool_call_start\n"
                        f"data: {json.dumps({'call_id': call_id, 'skill_id': fn_name, 'action': fn_name, 'args': args}, ensure_ascii=False)}\n\n"
                    )

                    # Execute tool asynchronously
                    tool_res = await execute_tool(fn_name, args)

                    # Check for risk card data
                    risk_card = extract_risk_card(tool_res)
                    if risk_card:
                        yield (
                            f"event: risk_card\n"
                            f"data: {json.dumps(risk_card, ensure_ascii=False)}\n\n"
                        )

                    # Summary for complete event
                    summary = "完成调用"
                    if "price" in tool_res and "change_pct" in tool_res:
                        summary = f"现价 {tool_res['price']} ({tool_res['change_pct']:+.2f}%)"
                    elif "breakeven_price" in tool_res:
                        summary = f"保本价 {tool_res['breakeven_price']} (止损T0: {tool_res.get('stop_t0')})"
                    elif "total_score" in tool_res:
                        summary = f"量化总分 {tool_res['total_score']} 分"
                    elif "selected_count" in tool_res:
                        summary = f"初选入围 {tool_res['selected_count']} 只标的"

                    # Emit tool_call_complete
                    yield (
                        f"event: tool_call_complete\n"
                        f"data: {json.dumps({'call_id': call_id, 'skill_id': fn_name, 'status': 'success', 'summary': summary, 'data': tool_res}, ensure_ascii=False)}\n\n"
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

            # 6. Emit done event
            elapsed_ms = int((time.time() - start_time) * 1000)
            if total_tokens == 0:
                total_tokens = max(100, int(len(message) * 1.5))
            yield (
                f"event: done\n"
                f"data: {json.dumps({'total_tokens': total_tokens, 'elapsed_ms': elapsed_ms, 'finish_reason': 'stop'}, ensure_ascii=False)}\n\n"
            )

        except Exception as exc:
            logger.error(f"ReAct runtime error: {exc}", exc_info=True)
            yield (
                f"event: error\n"
                f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            )
