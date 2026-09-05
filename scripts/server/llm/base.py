# -*- coding: utf-8 -*-
"""
server.llm.base - Unified abstraction for LLM streaming and tool-calling providers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolCallDelta(BaseModel):
    index: int = 0
    id: Optional[str] = None
    name: Optional[str] = None
    arguments_delta: str = ""


class LLMStreamChunk(BaseModel):
    delta_text: Optional[str] = None
    thought: Optional[str] = None
    tool_call_deltas: Optional[List[ToolCallDelta]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    def __init__(self, model_name: str, **kwargs: Any) -> None:
        self.model_name = model_name
        self.extra_kwargs = kwargs

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        """
        Stream chat completions and tool calls from the underlying LLM provider.
        Yields LLMStreamChunk instances.
        """
        pass
