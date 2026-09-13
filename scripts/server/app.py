# -*- coding: utf-8 -*-
"""
server.app - FastAPI application factory with lifespan and CORS configuration.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Query, Request
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
from server.models import SaveDocRequest
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
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
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

    # 2.1) 安全只读文档读取接口 (供工作区渲染 .md 交付物与指南)
    @app.get("/api/docs/read", tags=["Documents"])
    async def read_workspace_doc(path: str = Query(..., description="文档相对路径或名称")):
        workspace_root = Path(__file__).resolve().parent.parent.parent
        # 处理 file:// 前缀
        clean_path = path.strip()
        if clean_path.startswith("file://"):
            clean_path = clean_path[7:]

        target_file = Path(clean_path)
        if not target_file.is_absolute():
            target_file = (workspace_root / target_file).resolve()
        else:
            target_file = target_file.resolve()

        # 安全边界验证：严禁逃逸工作区
        try:
            target_file.relative_to(workspace_root)
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied: outside workspace boundary")

        # 若直接路径不存在，尝试在常见交付物与文档子目录下检索
        if not target_file.is_file():
            filename = Path(clean_path).name
            candidates = [
                workspace_root / "output" / "reports" / filename,
                workspace_root / "reports" / filename,
                workspace_root / "output" / filename,
                workspace_root / "docs" / filename,
                workspace_root / ".agents" / "skills" / "astock-data-feed" / "templates" / filename,
            ]
            for cand in candidates:
                if cand.is_file():
                    target_file = cand
                    break
        elif target_file.suffix.lower() in {".html", ".htm"}:
            # 若命中的文件不是真实 HTML（例如被 Markdown 覆写），但 output/reports 下存在同名真实 HTML，优先采用真实 HTML
            filename = target_file.name
            out_cand = workspace_root / "output" / "reports" / filename
            if out_cand.is_file() and out_cand != target_file:
                try:
                    cur_text = target_file.read_text(encoding="utf-8")
                    out_text = out_cand.read_text(encoding="utf-8")
                    if ("<!DOCTYPE html" in out_text or "<html" in out_text) and not ("<!DOCTYPE html" in cur_text or "<html" in cur_text):
                        target_file = out_cand
                except Exception:
                    pass

        # 扩展名限制 (支持 Markdown 与 HTML 研报及文本交付物)
        allowed_exts = {".md", ".markdown", ".txt", ".json", ".csv", ".py", ".html", ".htm"}
        if target_file.suffix.lower() not in allowed_exts:
            raise HTTPException(status_code=400, detail="Unsupported file format for workspace viewer")

        if not target_file.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {target_file.name}")

        try:
            content = target_file.read_text(encoding="utf-8")
            doc_format = "html" if target_file.suffix.lower() in {".html", ".htm"} else "markdown"

            # 强韧性保护：若文件名为 .html，但文件内容为纯 Markdown，自动转为自包含标准 HTML，杜绝 iframe 乱码
            if doc_format == "html" and not ("<!DOCTYPE html" in content or "<html" in content):
                from core.reporting.report_generator import wrap_markdown_as_html_report
                content = wrap_markdown_as_html_report(content, title=target_file.stem, filename=target_file.name)

            rel_path = target_file.relative_to(workspace_root).as_posix()
            return {
                "status": "ok",
                "path": rel_path,
                "filename": target_file.name,
                "format": doc_format,
                "size_bytes": len(content.encode("utf-8")),
                "content": content,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(exc)}")

    # 2.2) 文档保存持久化接口 (供研报交付物自动保存与工作区联动)
    @app.post("/api/docs/save", tags=["Documents"])
    async def save_workspace_doc(req: SaveDocRequest):
        workspace_root = Path(__file__).resolve().parent.parent.parent
        clean_path = req.path.strip()
        if clean_path.startswith("file://"):
            clean_path = clean_path[7:]

        # 若仅传入了文件名（如 report_600519.md 或 aStocks_600519.html），根据类型归档
        clean_p = Path(clean_path)
        if not clean_p.is_absolute() and len(clean_p.parts) == 1:
            if clean_p.suffix.lower() in {".html", ".htm"} or clean_p.name.startswith("aStocks_") or (workspace_root / "output" / "reports" / clean_p.name).is_file():
                target_file = (workspace_root / "output" / "reports" / clean_p.name).resolve()
            else:
                target_file = (workspace_root / "reports" / clean_p.name).resolve()
        elif not clean_p.is_absolute():
            target_file = (workspace_root / clean_p).resolve()
        else:
            target_file = clean_p.resolve()

        # 安全边界验证：严禁逃逸工作区
        try:
            target_file.relative_to(workspace_root)
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied: outside workspace boundary")

        allowed_exts = {".md", ".markdown", ".txt", ".json", ".csv", ".html", ".htm"}
        if target_file.suffix.lower() not in allowed_exts:
            raise HTTPException(status_code=400, detail="Unsupported file format for saving document")

        content_to_save = req.content
        if target_file.suffix.lower() in {".html", ".htm"}:
            trimmed = content_to_save.strip() if isinstance(content_to_save, str) else ""
            is_valid_html = "<!DOCTYPE html" in trimmed or "<html" in trimmed

            # 1. 如果磁盘上已存在合法的真实 HTML 报告，且传入的不是合法 HTML（比如传入的是 Markdown 摘要），严禁覆写！
            if target_file.is_file():
                try:
                    existing_text = target_file.read_text(encoding="utf-8")
                    if ("<!DOCTYPE html" in existing_text or "<html" in existing_text) and not is_valid_html:
                        return {
                            "status": "ok",
                            "path": target_file.relative_to(workspace_root).as_posix(),
                            "filename": target_file.name,
                            "size_bytes": len(existing_text.encode("utf-8")),
                            "notice": "Retained existing genuine HTML report without overwriting with Markdown"
                        }
                except Exception:
                    pass

            # 2. 如果保存的文件是 .html，但传入内容是 Markdown 格式，必须转换为标准自包含 HTML
            if not is_valid_html:
                from core.reporting.report_generator import wrap_markdown_as_html_report
                content_to_save = wrap_markdown_as_html_report(
                    content_to_save,
                    title=req.title or target_file.stem,
                    filename=target_file.name
                )

        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content_to_save, encoding="utf-8")
            rel_path = target_file.relative_to(workspace_root).as_posix()
            return {
                "status": "ok",
                "path": rel_path,
                "filename": target_file.name,
                "size_bytes": len(content_to_save.encode("utf-8")),
            }

        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save document: {str(exc)}")

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
                "docs_read": "/api/docs/read",
                "docs_save": "/api/docs/save",
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
