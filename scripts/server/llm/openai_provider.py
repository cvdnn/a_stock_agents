# -*- coding: utf-8 -*-
"""
server.llm.openai_provider - Provider supporting OpenAI, DeepSeek, and OpenAI-compatible endpoints.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

from server.llm.base import BaseLLMProvider, LLMStreamChunk, ToolCallDelta


class OpenAIProvider(BaseLLMProvider):
    """Handles standard OpenAI-compatible endpoints including DeepSeek."""

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name, **kwargs)
        self.api_key = api_key or ""
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Merge extra payload args
        for k, v in kwargs.items():
            if k not in payload:
                payload[k] = v

        tool_calls_accumulator: Dict[int, Dict[str, Any]] = {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(
                        f"OpenAI/DeepSeek API Error [{response.status_code}]: {error_text.decode('utf-8', errors='ignore')}"
                    )

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except Exception:
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            # Might be usage chunk
                            usage = data.get("usage")
                            if usage:
                                yield LLMStreamChunk(usage=usage)
                            continue

                        choice = choices[0]
                        delta = choice.get("delta", {})
                        finish_reason = choice.get("finish_reason")

                        # DeepSeek R1 / Reasoning content
                        thought_content = delta.get("reasoning_content") or delta.get("thought")
                        text_content = delta.get("content")

                        # Tool calls parsing
                        raw_tool_deltas = delta.get("tool_calls")
                        parsed_tool_deltas = []
                        if raw_tool_deltas:
                            for td in raw_tool_deltas:
                                idx = td.get("index", 0)
                                fn = td.get("function", {})
                                name = fn.get("name")
                                args_delta = fn.get("arguments", "")
                                call_id = td.get("id")

                                if idx not in tool_calls_accumulator:
                                    tool_calls_accumulator[idx] = {
                                        "id": call_id or f"call_{idx}",
                                        "type": "function",
                                        "function": {
                                            "name": name or "",
                                            "arguments": "",
                                        },
                                    }
                                else:
                                    if call_id:
                                        tool_calls_accumulator[idx]["id"] = call_id
                                    if name:
                                        tool_calls_accumulator[idx]["function"]["name"] = name

                                if args_delta:
                                    tool_calls_accumulator[idx]["function"]["arguments"] += args_delta

                                parsed_tool_deltas.append(
                                    ToolCallDelta(
                                        index=idx,
                                        id=call_id,
                                        name=name,
                                        arguments_delta=args_delta,
                                    )
                                )

                        completed_calls = None
                        if finish_reason == "tool_calls" or (finish_reason and tool_calls_accumulator):
                            completed_calls = list(tool_calls_accumulator.values())

                        yield LLMStreamChunk(
                            delta_text=text_content,
                            thought=thought_content,
                            tool_call_deltas=parsed_tool_deltas if parsed_tool_deltas else None,
                            tool_calls=completed_calls,
                            finish_reason=finish_reason,
                            usage=data.get("usage"),
                        )
