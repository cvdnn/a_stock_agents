# -*- coding: utf-8 -*-
"""
server.api.skills - REST API endpoints for Skill Governance and Audit Subsystem.
Provides skill discovery, dynamic hot-swapping, parameter debugging, and audit metrics.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from core.governance.auditor import default_auditor
from core.governance.models import (
    SkillAuditStats,
    SkillMeta,
    SkillTestRequest,
    SkillTestResponse,
    SkillUpdateRequest,
)
from core.governance.skill_registry import get_skill_registry

router = APIRouter(prefix="/api/skills", tags=["Skills Governance"])


@router.get("", response_model=List[SkillMeta])
async def list_skills(
    category: Optional[str] = Query(None, description="Filter skills by domain category"),
    enabled_only: bool = Query(False, description="Filter only enabled skills"),
):
    """Retrieve list of registered skills with metadata, schemas, and status."""
    registry = get_skill_registry()
    return registry.list_skills(category=category, enabled_only=enabled_only)


@router.get("/audit/stats", response_model=SkillAuditStats)
async def get_audit_stats():
    """Retrieve skill invocation counts, P95 latency, error rate, and per-skill breakdown."""
    return default_auditor.get_stats()


@router.get("/{skill_id}", response_model=SkillMeta)
async def get_skill_detail(skill_id: str):
    """Retrieve detailed metadata and JSON Schema for a single skill."""
    registry = get_skill_registry()
    skill = registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return skill


@router.patch("/{skill_id}", response_model=SkillMeta)
async def update_skill_config(skill_id: str, req: SkillUpdateRequest):
    """Dynamically enable/disable a skill or adjust its timeout/safety parameters."""
    registry = get_skill_registry()
    updated = registry.update_skill(
        skill_id=skill_id,
        enabled=req.enabled,
        timeout_seconds=req.timeout_seconds,
        require_confirmation=req.require_confirmation,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return updated


@router.post("/{skill_id}/test", response_model=SkillTestResponse)
async def test_skill_execution(skill_id: str, req: SkillTestRequest):
    """
    Test and debug a skill execution with specified arguments.
    Enforces parameter schema validation, security gate checks, and timeout fuses.
    """
    registry = get_skill_registry()
    skill = registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    response = await registry.execute_skill(
        skill_id=skill.id,
        params=req.parameters,
        confirmed=req.confirmed,
    )
    return response
