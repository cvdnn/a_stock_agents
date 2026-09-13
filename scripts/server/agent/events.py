# -*- coding: utf-8 -*-
"""
server.agent.events - Universal Domain Event Model for Agent Runtime.
Decouples ReAct engine reasoning & execution from wire transmission protocols (SSE / TUI / IPC).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class AgentEvent(BaseModel):
    """Base domain event emitted during agent deliberation and execution."""
    event_type: str = Field(..., description="Canonical event identifier")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ConversationStartEvent(AgentEvent):
    """Event emitted at the beginning of a conversation turn."""
    event_type: Literal["conversation_start"] = "conversation_start"
    session_id: str
    model: str
    title: Optional[str] = None


class ThoughtEvent(AgentEvent):
    """Event emitted when LLM streams internal reasoning or Chain of Thought."""
    event_type: Literal["thought"] = "thought"
    content: str


class ToolCallStartEvent(AgentEvent):
    """Event emitted when the agent begins invoking an external tool/skill."""
    event_type: Literal["tool_call_start"] = "tool_call_start"
    call_id: str
    skill_id: str
    action: str
    args: Dict[str, Any] = Field(default_factory=dict)


class ToolCallCompleteEvent(AgentEvent):
    """Event emitted when a tool invocation concludes with observation data."""
    event_type: Literal["tool_call_complete"] = "tool_call_complete"
    call_id: str
    skill_id: str
    status: str  # "success", "error", "timeout", "confirmation_required"
    summary: str
    data: Optional[Dict[str, Any]] = None


class RiskCardEvent(AgentEvent):
    """
    Event emitted when risk metrics or action plan orders are produced.
    Follows real-world 3 principles: ceil cent breakeven, 3-tier stop loss, 3 action scenarios.
    """
    event_type: Literal["risk_card"] = "risk_card"
    breakeven_price: float
    stop_t0: float
    stop_t1: float
    stop_t2: float
    code: Optional[str] = None
    name: Optional[str] = None
    current_price: Optional[float] = None
    cost: Optional[float] = None
    shares: Optional[int] = None
    actions: Optional[Union[Dict[str, Any], List[Any]]] = None


class ContentDeltaEvent(AgentEvent):
    """Event emitted for assistant typewriter text streaming chunk."""
    event_type: Literal["content_delta"] = "content_delta"
    text: str


class DoneEvent(AgentEvent):
    """Event emitted when conversation turn finishes with final token usage and latency."""
    event_type: Literal["done"] = "done"
    total_tokens: int
    elapsed_ms: int
    finish_reason: str = "stop"


class ErrorEvent(AgentEvent):
    """Event emitted when an unexpected runtime exception occurs."""
    event_type: Literal["error"] = "error"
    error: str
    code: Optional[str] = None


AgentEventUnion = Union[
    ConversationStartEvent,
    ThoughtEvent,
    ToolCallStartEvent,
    ToolCallCompleteEvent,
    RiskCardEvent,
    ContentDeltaEvent,
    DoneEvent,
    ErrorEvent,
]


def sse_format(event: AgentEvent) -> str:
    """
    Protocol Adapter: Serialize an AgentEvent domain object into SSE format:
    event: <type>\\ndata: <json>\\n\\n
    """
    payload = event.model_dump(exclude={"event_type", "timestamp"})
    # Retain required top-level fields for spec compliance
    return f"event: {event.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
