# -*- coding: utf-8 -*-
"""
server.llm.claude_provider - Anthropic Claude Messages API provider.
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

from server.llm.base import BaseLLMProvider, LLMStreamChunk, ToolCallDelta


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider implementing streaming Messages API."""

    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"

    def __init__(
        self,
        model_name: str = "claude-3-5-sonnet-20241022",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name, **kwargs)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        self.base_url = (base_url or os.getenv("ANTHROPIC_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        # Separate system message if present
        system_content = ""
        claude_messages = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                system_content += m.get("content", "") + "\n"
            else:
                # Map assistant tool calls or user messages
                claude_messages.append({
                    "role": role if role in ("user", "assistant") else "user",
                    "content": m.get("content", ""),
                })

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": claude_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": True,
            "temperature": temperature,
        }
        if system_content.strip():
            payload["system"] = system_content.strip()

        # Transform tools to Claude format if provided
        if tools:
            claude_tools = []
            for t in tools:
                if t.get("type") == "function":
                    fn = t.get("function", {})
                    claude_tools.append({
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                    })
                else:
                    claude_tools.append(t)
            payload["tools"] = claude_tools

        tool_calls_acc: Dict[int, Dict[str, Any]] = {}
        current_block_type = ""
        current_block_index = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_bytes = await response.aread()
                    raise RuntimeError(
                        f"Claude API Error [{response.status_code}]: {error_bytes.decode('utf-8', errors='ignore')}"
                    )

                event_type = ""
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        try:
                            data = json.loads(data_str)
                        except Exception:
                            continue

                        if event_type == "content_block_start":
                            cb = data.get("content_block", {})
                            current_block_type = cb.get("type", "")
                            current_block_index = data.get("index", 0)
                            if current_block_type == "tool_use":
                                tool_calls_acc[current_block_index] = {
                                    "id": cb.get("id"),
                                    "type": "function",
                                    "function": {
                                        "name": cb.get("name"),
                                        "arguments": "",
                                    },
                                }

                        elif event_type == "content_block_delta":
                            delta = data.get("delta", {})
                            delta_type = delta.get("type", "")
                            if delta_type == "text_delta":
                                yield LLMStreamChunk(delta_text=delta.get("text", ""))
                            elif delta_type == "thinking_delta":
                                yield LLMStreamChunk(thought=delta.get("thinking", ""))
                            elif delta_type == "input_json_delta":
                                partial = delta.get("partial_json", "")
                                if current_block_index in tool_calls_acc:
                                    tool_calls_acc[current_block_index]["function"]["arguments"] += partial
                                yield LLMStreamChunk(
                                    tool_call_deltas=[
                                        ToolCallDelta(
                                            index=current_block_index,
                                            arguments_delta=partial,
                                        )
                                    ]
                                )

                        elif event_type == "message_delta":
                            delta = data.get("delta", {})
                            stop_reason = delta.get("stop_reason")
                            usage = data.get("usage")
                            completed_calls = None
                            if stop_reason == "tool_use" or (stop_reason and tool_calls_acc):
                                completed_calls = list(tool_calls_acc.values())
                            yield LLMStreamChunk(
                                finish_reason=stop_reason,
                                usage=usage,
                                tool_calls=completed_calls,
                            )
