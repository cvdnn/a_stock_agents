# -*- coding: utf-8 -*-
"""
server.api.health - Health check and system configuration endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter

from core.config import GLOBAL_CONFIG, VERSION
from server.config import server_settings
from server.db import check_db_health
from server.models import HealthResponse, ServerConfigResponse

router = APIRouter(tags=["Health & Config"])


@router.get("/api/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Service health and database connectivity check."""
    return HealthResponse(
        status="ok",
        version=VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        db_connected=check_db_health(),
    )


@router.get("/api/config", response_model=ServerConfigResponse)
async def get_config() -> ServerConfigResponse:
    """Return runtime server and market configuration (safely masked)."""
    supported = [
        "deepseek-chat",
        "deepseek-reasoner",
        "gpt-4o",
        "gpt-4o-mini",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "claude-3-5-sonnet-20241022",
        "ollama/qwen2.5",
        "mock",
    ]
    data_sources = GLOBAL_CONFIG.get("data_sources", {
        "primary": "tencent",
        "secondary": "eastmoney",
        "fallback": "local_cache",
    })
    return ServerConfigResponse(
        app_name="a_stock_agents",
        version=VERSION,
        default_model=server_settings.default_model,
        supported_models=supported,
        cors_origins=server_settings.cors_origins,
        data_sources=data_sources,
    )
