# -*- coding: utf-8 -*-
"""
server.config - Server-wide settings and environment management.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

# Root directory resolution
SERVER_DIR = Path(__file__).resolve().parent
from core.config import PROJECT_ROOT

DEFAULT_DB_PATH = PROJECT_ROOT / "output" / "cache" / "chats.db"


class ServerSettings(BaseModel):
    """Configuration settings for FastAPI server and Agent runtime."""
    host: str = Field(default="127.0.0.1", description="Server listening host")
    port: int = Field(default=8000, description="Server listening port")
    reload: bool = Field(default=False, description="Enable auto-reload on code change")
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173", "*"],
        description="Allowed CORS origins"
    )
    
    # SQLite Database
    db_path: Path = Field(default=DEFAULT_DB_PATH, description="Path to SQLite chats.db")
    
    # LLM Settings
    default_model: str = Field(default="deepseek-chat", description="Default LLM model")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API Key")
    openai_base_url: Optional[str] = Field(default=None, description="OpenAI API Base URL")
    deepseek_api_key: Optional[str] = Field(default=None, description="DeepSeek API Key")
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1", description="DeepSeek Base URL")
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API Key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic Claude API Key")
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama Base URL")
    
    # Timeout and retry
    request_timeout: float = Field(default=60.0, description="LLM request timeout in seconds")


def load_server_settings() -> ServerSettings:
    """Load settings from environment variables and defaults."""
    db_str = os.getenv("A_STOCK_DB_PATH")
    db_path = Path(db_str).resolve() if db_str else DEFAULT_DB_PATH
    
    # Determine default model: if no API keys are found, default to mock or deepseek
    default_model = os.getenv("A_STOCK_DEFAULT_MODEL")
    if not default_model:
        if os.getenv("DEEPSEEK_API_KEY"):
            default_model = "deepseek-chat"
        elif os.getenv("OPENAI_API_KEY"):
            default_model = "gpt-4o"
        elif os.getenv("GEMINI_API_KEY"):
            default_model = "gemini-1.5-flash"
        elif os.getenv("ANTHROPIC_API_KEY"):
            default_model = "claude-3-5-sonnet-20241022"
        else:
            default_model = "mock"

    cors_str = os.getenv("A_STOCK_CORS_ORIGINS")
    cors_origins = [s.strip() for s in cors_str.split(",")] if cors_str else [
        "http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173", "*"
    ]

    return ServerSettings(
        host=os.getenv("A_STOCK_SERVER_HOST", "127.0.0.1"),
        port=int(os.getenv("A_STOCK_SERVER_PORT", "8000")),
        reload=os.getenv("A_STOCK_SERVER_RELOAD", "false").lower() in ("true", "1", "yes"),
        cors_origins=cors_origins,
        db_path=db_path,
        default_model=default_model,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        request_timeout=float(os.getenv("A_STOCK_LLM_TIMEOUT", "60.0")),
    )


server_settings = load_server_settings()
