#!/usr/bin/env python3
"""Runtime defaults and paths for the paper trading service."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765
APP_NAME = "a-share-paper-trading"
DB_FILENAME = "paper_trading.db"
LOG_FILENAME = "service.log"
PID_FILENAME = "service.pid"
LAUNCH_AGENT_LABEL = "ai.openclaw.a-share-paper-trading"


def _find_project_root() -> Path:
    if os.environ.get("A_STOCK_AGENTS_ROOT"):
        return Path(os.environ["A_STOCK_AGENTS_ROOT"]).resolve()
    curr = Path(__file__).resolve().parent
    for p in [curr] + list(curr.parents):
        if (p / "pyproject.toml").exists() or (p / "AGENTS.md").exists():
            return p
    return curr.parent.parent.parent


_PROJECT_ROOT = _find_project_root()
# 默认归位项目内 log/paper_trading/（运行时观测唯一沉淀区）
LOG_SUBDIR = _PROJECT_ROOT / "log" / "paper_trading"
# 数据库与 PID 仍保留在 output/cache/paper_trading/（用户最终交付物/会话状态）
OUTPUT_SUBDIR = _PROJECT_ROOT / "output" / "cache" / "paper_trading"


def get_app_data_dir() -> Path:
    """兼容旧 API：返回 output/cache/paper_trading（用于存放 DB 与运行时状态）。"""
    OUTPUT_SUBDIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_SUBDIR


def get_default_db_path() -> Path:
    return get_app_data_dir() / DB_FILENAME


def get_default_log_path() -> Path:
    """服务运行日志统一落入项目内 log/paper_trading/，便于事后追溯与 .gitignore 隔离。"""
    LOG_SUBDIR.mkdir(parents=True, exist_ok=True)
    return LOG_SUBDIR / LOG_FILENAME


def get_default_pid_path() -> Path:
    return get_app_data_dir() / PID_FILENAME


def get_launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def ensure_runtime_dir(path: Path | None = None) -> Path:
    target = path or get_app_data_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target
