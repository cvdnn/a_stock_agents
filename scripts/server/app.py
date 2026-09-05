# -*- coding: utf-8 -*-
"""
server.app - FastAPI application factory with lifespan and CORS configuration.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import VERSION, get_logger
from server.api import chat_router, health_router, sessions_router
from server.config import server_settings
from server.db import init_db

logger = get_logger("server.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize database schemas on startup."""
    logger.info("Initializing A-Stock Agents server database...")
    init_db(server_settings.db_path)
    logger.info(f"Database ready at: {server_settings.db_path}")
    yield
    logger.info("A-Stock Agents server shutting down.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="A-Stock Agents Web AIChat & Governance API",
        description="Unified backend service providing Native Agent Runtime, SSE streaming, and Skill Governance.",
        version=VERSION,
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=server_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API Routers
    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)

    @app.get("/", tags=["Root"])
    async def root_index():
        return {
            "name": "A-Stock Agents Web API",
            "version": VERSION,
            "docs_url": "/docs",
            "status": "online",
        }

    return app


app = create_app()
