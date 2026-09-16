# -*- coding: utf-8 -*-
"""
server.api.audit - Authentication audit log read endpoint (super admin only).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from server.auth.dependencies import AuthContext, require_super_admin
from server.db import list_auth_audit

router = APIRouter(prefix="/api/audit", tags=["Audit Logs"])


@router.get("/auth")
async def list_auth_audit_endpoint(
    limit: int = Query(50, ge=1, le=500),
    _: AuthContext = Depends(require_super_admin),
):
    items = list_auth_audit(limit=limit)
    return {"status": "ok", "items": items, "total": len(items)}
