# -*- coding: utf-8 -*-
"""
server.api - API routes package.
"""
from server.api.chat import router as chat_router
from server.api.health import router as health_router
from server.api.market_data import router as market_data_router
from server.api.models_mgmt import router as models_mgmt_router
from server.api.sessions import router as sessions_router
from server.api.skills import router as skills_router
from server.api.tasks import router as tasks_router

__all__ = [
    "health_router",
    "sessions_router",
    "chat_router",
    "skills_router",
    "tasks_router",
    "models_mgmt_router",
    "market_data_router",
]

