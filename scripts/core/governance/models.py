# -*- coding: utf-8 -*-
"""
core.governance.models - Pydantic models and schemas for Skill Governance Subsystem.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SkillRiskLevel(str, Enum):
    """Risk tier classification for skill execution and security gatekeeping."""
    READONLY = "readonly"          # 只读研判 (行情/选股/评分/诊断)
    SIMULATION = "simulation"      # 模拟交易 (模拟盘下单/调仓/撤单，默认需要二次确认)
    DESTRUCTIVE = "destructive"    # 高危变更 (清空数据/策略参数重置)


class SkillMeta(BaseModel):
    """Unified runtime metadata contract for an A-Stock Agent Skill."""
    id: str = Field(..., description="Unique skill identifier (e.g. astock-data-feed)")
    name: str = Field(..., description="Internal skill directory name")
    title: str = Field(..., description="Human-readable title for UI and console")
    category: str = Field(default="general", description="Domain category (data, platform, screener, etc.)")
    description: str = Field(..., description="Detailed capability description")
    risk_level: SkillRiskLevel = Field(default=SkillRiskLevel.READONLY, description="Security risk tier")
    enabled: bool = Field(default=True, description="Whether the skill is enabled for agent use")
    triggers: List[str] = Field(default_factory=list, description="Natural language semantic trigger keywords")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for function calling arguments")
    timeout_seconds: int = Field(default=30, description="Execution timeout fuse in seconds")
    require_confirmation: bool = Field(default=False, description="Whether execution requires human-in-the-loop confirmation")
    entry_point: Optional[str] = Field(default=None, description="Module entry point or script path")
    cli_command: Optional[str] = Field(default=None, description="Unified CLI invocation template")
    skill_doc: Optional[str] = Field(default=None, description="Path to SKILL.md specification")
    recommended_model: Optional[str] = Field(default="inherit", description="Model routing recommendation (flash, pro, inherit)")


class SkillUpdateRequest(BaseModel):
    """Payload for PATCH /api/skills/{skill_id} configuration update."""
    enabled: Optional[bool] = Field(default=None, description="Enable or disable the skill")
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=600, description="Update execution timeout in seconds")
    require_confirmation: Optional[bool] = Field(default=None, description="Update whether confirmation is required")


class SkillTestRequest(BaseModel):
    """Payload for POST /api/skills/{skill_id}/test execution."""
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Arguments matching the skill schema")
    confirmed: bool = Field(default=False, description="User confirmation flag for simulation/destructive actions")


class SkillTestResponse(BaseModel):
    """Execution response of skill test call."""
    skill_id: str
    status: str = Field(..., description="'success', 'error', 'confirmation_required', or 'timeout'")
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: int = 0
    message: Optional[str] = None


class SkillAuditRecord(BaseModel):
    id: Optional[int] = None
    skill_id: str
    action: str
    status: str
    latency_ms: int = 0
    error_message: Optional[str] = None
    tokens: int = 0
    created_at: str


class SkillAuditStats(BaseModel):
    total_calls: int
    today_calls: int
    success_count: int
    error_count: int
    error_rate: float
    avg_latency_ms: float
    p95_latency_ms: int
    by_skill: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
