# -*- coding: utf-8 -*-
"""
server.models - Pydantic schemas for API requests, responses, and events.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(default=None, description="Optional conversation title")
    model: Optional[str] = Field(default=None, description="Model identifier to use")
    meta: Optional[Dict[str, Any]] = Field(default=None, description="Extra metadata")


class SessionResponse(BaseModel):
    session_id: str
    title: str
    model: str
    created_at: str
    updated_at: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]
    total: int


class MessageItem(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    thought: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    risk_card: Optional[Dict[str, Any]] = None
    created_at: str = ""


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    messages: List[MessageItem]


class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="User prompt or question")
    session_id: Optional[str] = Field(default=None, description="Existing session id or null to create new")
    model: Optional[str] = Field(default=None, description="Override model for this conversation turn")
    tools_enabled: bool = Field(default=True, description="Whether to allow agent to invoke tools")


class RiskCardData(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    current_price: Optional[float] = None
    cost: Optional[float] = None
    shares: Optional[int] = None
    breakeven_price: float
    stop_t0: float
    stop_t1: float
    stop_t2: float
    actions: Optional[Dict[str, str]] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    db_connected: bool


class ServerConfigResponse(BaseModel):
    app_name: str
    version: str
    default_model: str
    supported_models: List[str]
    cors_origins: List[str]
    data_sources: Dict[str, Any]
