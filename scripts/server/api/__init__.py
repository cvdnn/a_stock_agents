# -*- coding: utf-8 -*-
"""
server.api - API routes package.
"""
from server.api.chat import router as chat_router
from server.api.health import router as health_router
from server.api.sessions import router as sessions_router

__all__ = ["health_router", "sessions_router", "chat_router"]
