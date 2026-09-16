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
    audit_router,
    auth_router,
    chat_router,
    health_router,
    market_data_router,
    menus_router,
    models_mgmt_router,
    roles_router,
    sessions_router,
    skills_router,
    tasks_router,
    users_router,
)
from server.config import server_settings
from server.db import init_db, sync_super_admin_from_config
from server.models import SaveDocRequest
from server.port_utils import remove_server_lockfile

logger = get_logger("server.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize database schemas on startup, cleanup on shutdown."""
    logger.info("Initializing A-Stock Agents server database...")
    init_db(server_settings.db_path)
    # Defensive: ensure the locally configured super admin is persisted to the DB on every boot.
    try:
        sync_super_admin_from_config()
    except Exception as exc:
        logger.warning(f"sync_super_admin_from_config failed: {exc}")
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
        allow_headers=["Accept", "Content-Type", "Authorization"],
    )

    # Authentication Middleware: prefers user session tokens (Bearer or `access_token` cookie),
    # with optional fallback to a static `server_settings.api_token` for machine integrations.
    @app.middleware("http")
    async def api_token_auth_middleware(request: Request, call_next):
        # 豁免 OPTIONS 预检请求以支持 CORS
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # 1. 白名单：完全不需要鉴权 (登录、注册不可用提示、健康检查、Web UI)
        public_prefixes = (
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/config",
            "/api/health",
        )
        if any(path == p or path.startswith(p + "/") for p in public_prefixes):
            return await call_next(request)

        # Web UI 与静态资源
        if path in {"/", "/favicon.ico"} or path.startswith(("/ui", "/css", "/js", "/assets")):
            return await call_next(request)

        # 2. 用户会话 Token (优先于静态 API Token)
        from server.db import lookup_auth_token
        provided_token = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            provided_token = auth_header[7:].strip()
        if not provided_token:
            provided_token = request.cookies.get("access_token")

        if provided_token:
            record = lookup_auth_token(provided_token)
            if record:
                return await call_next(request)
            # token 存在但无效 → 401（不要静默 fallback 到静态 token，避免泄漏）
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": {"error": "invalid_token", "message": "会话已过期，请重新登录"}},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. 兜底：可选静态 API Token（兼容旧版机器集成）
        static_token = getattr(server_settings, "api_token", None)
        if static_token:
            if auth_header and (
                (auth_header.startswith("Bearer ") and auth_header[7:].strip() == static_token)
                or (auth_header.startswith("bearer ") and auth_header[7:].strip() == static_token)
                or auth_header.strip() == static_token
            ):
                return await call_next(request)
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing Bearer token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 4. 没有任何凭证可用 → 401
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={"detail": {"error": "unauthorized", "message": "请先登录"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Register API Routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(menus_router)
    app.include_router(audit_router)
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

        # 扩展名限制 (支持 Markdown 与 HTML 研报及文本交付物，彻底排除 .py 格式)
        allowed_exts = {".md", ".markdown", ".txt", ".json", ".csv", ".html", ".htm"}
        if target_file.suffix.lower() not in allowed_exts:
            raise HTTPException(status_code=400, detail="Unsupported file format for workspace viewer")

        # 敏感目录黑名单拦截：严禁探测 scripts、tests、.git、.venv、.env 等核心目录
        forbidden_roots = {"scripts", "tests", ".git", ".github", ".venv", "venv", "node_modules"}
        rel_parts = target_file.relative_to(workspace_root).parts
        if any(part in forbidden_roots for part in rel_parts) or any(part.startswith(".") and part not in {".agents"} for part in rel_parts):
            raise HTTPException(status_code=403, detail="Access denied: access to restricted directory")
        if target_file.name in {".env", "docker-compose.yml"}:
            raise HTTPException(status_code=403, detail="Access denied: access to sensitive configuration is forbidden")

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

        # 校验最终命中的文件是否在受信任的文档根目录下
        allowed_dirs = [
            workspace_root / "output",
            workspace_root / "reports",
            workspace_root / "docs",
            workspace_root / ".agents" / "skills",
        ]
        is_in_allowed_dir = False
        for allowed_dir in allowed_dirs:
            try:
                target_file.relative_to(allowed_dir)
                is_in_allowed_dir = True
                break
            except ValueError:
                continue

        if not is_in_allowed_dir:
            raise HTTPException(status_code=403, detail="Access denied: file outside permitted document directories")

        if not target_file.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {target_file.name}")

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
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(exc)}")

    # 2.2) 文档保存持久化接口 (供研报交付物自动保存与工作区联动)
    @app.post("/api/docs/save", tags=["Documents"])
    async def save_workspace_doc(req: SaveDocRequest):
        workspace_root = Path(__file__).resolve().parent.parent.parent
        reports_dir = (workspace_root / "output" / "reports").resolve()
        reports_dir.mkdir(parents=True, exist_ok=True)

        clean_path = req.path.strip()
        if clean_path.startswith("file://"):
            clean_path = clean_path[7:]

        clean_p = Path(clean_path)

        # 严格防御路径穿越与目录逃逸：拦截包含 .. 或尝试写入受保护系统目录的请求
        forbidden_prefixes = {"web", "config", "scripts", "tests", ".git", ".agents", ".gemini", "node_modules"}
        if any(part in forbidden_prefixes for part in clean_p.parts) or ".." in clean_p.parts:
            raise HTTPException(status_code=403, detail="Access denied: write operation restricted to reports directory")

        # 扩展名限制
        allowed_exts = {".md", ".markdown", ".txt", ".json", ".csv", ".html", ".htm"}
        if clean_p.suffix.lower() not in allowed_exts:
            raise HTTPException(status_code=400, detail="Unsupported file format for saving document")

        # 强制将保存文件锁定在 output/reports 目录，仅提取安全文件名，拒绝包含路径分隔符
        safe_filename = clean_p.name
        if not safe_filename or safe_filename in {".", ".."} or "/" in safe_filename or "\\" in safe_filename:
            raise HTTPException(status_code=400, detail="Invalid filename for document save")

        target_file = (reports_dir / safe_filename).resolve()

        # 安全边界验证：严禁逃逸 output/reports 沙箱目录
        try:
            target_file.relative_to(reports_dir)
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied: outside reports boundary")

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
                "auth_login": "/api/auth/login",
                "auth_logout": "/api/auth/logout",
                "auth_me": "/api/auth/me",
                "auth_change_password": "/api/auth/change-password",
                "users": "/api/users",
                "roles": "/api/roles",
                "menus": "/api/menus",
                "audit_auth": "/api/audit/auth",
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
