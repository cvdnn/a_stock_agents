# -*- coding: utf-8 -*-
"""
server.app - FastAPI application factory with lifespan and CORS configuration.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.config import VERSION, get_logger
from server.api import (
    chat_router,
    health_router,
    market_data_router,
    models_mgmt_router,
    sessions_router,
    skills_router,
    tasks_router,
)
from server.config import server_settings
from server.db import init_db
from server.port_utils import remove_server_lockfile

logger = get_logger("server.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize database schemas on startup, cleanup on shutdown."""
    logger.info("Initializing A-Stock Agents server database...")
    init_db(server_settings.db_path)
    logger.info(f"Database ready at: {server_settings.db_path}")
    yield
    logger.info("A-Stock Agents server shutting down.")
    remove_server_lockfile()


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
    app.include_router(skills_router)
    app.include_router(tasks_router)
    app.include_router(models_mgmt_router)
    app.include_router(market_data_router)


    # Mount Static Web UI & Assets
    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    if web_dir.exists():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        # Static mounts for relative assets in index.html (css, js, assets, etc.)
        app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="ui")
        if (web_dir / "css").exists():
            app.mount("/css", StaticFiles(directory=str(web_dir / "css")), name="css")
        if (web_dir / "js").exists():
            app.mount("/js", StaticFiles(directory=str(web_dir / "js")), name="js")
        if (web_dir / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(web_dir / "assets")), name="assets")

        # 2) 主 Web 界面: http://127.0.0.1:6300 (根路径直接提供主工作台)
        @app.get("/", tags=["Web UI"], include_in_schema=False)
        async def main_web_ui():
            return FileResponse(web_dir / "index.html")

    # 3) 对外 API 接口导航与元信息: http://127.0.0.1:6300/api
    @app.get("/api", tags=["API Root"])
    @app.get("/api/", tags=["API Root"])
    async def api_root():
        """对外 API 接口目录与可用服务导航 (http://127.0.0.1:6300/api)"""
        return {
            "name": "A-Stock Agents Web API Gateway",
            "version": VERSION,
            "status": "online",
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
            "endpoints": {
                "health": "/api/health",
                "chat_stream": "/api/chat/completions/stream",
                "chat_sessions": "/api/chat/sessions",
                "skills_governance": "/api/skills",
                "market_indices": "/api/market/indices",
                "market_sentiment": "/api/market/sentiment",
                "market_kline": "/api/market/kline",
                "market_ranks": "/api/market/ranks",
                "portfolio_overview": "/api/portfolio/overview",
                "portfolio_analysis": "/api/portfolio/analysis",
                "watchlist": "/api/watchlist",
                "monitor_stream": "/api/monitor/stream",
            },
        }

    return app


app = create_app()
