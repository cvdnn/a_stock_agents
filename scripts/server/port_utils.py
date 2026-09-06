# -*- coding: utf-8 -*-
"""
server.port_utils - Dynamic port hunting, allocation, and runtime lockfile management.
Supports --port 0 ephemeral port negotiation for Desktop Sidecar and TUI clients.
"""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import PROJECT_ROOT, get_logger

logger = get_logger("server.port_utils")

DEFAULT_LOCKFILE_PATH = PROJECT_ROOT / ".server.port"


def find_free_port() -> int:
    """Dynamically probe the OS to obtain an available ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = s.getsockname()[1]
        return port


def write_server_lockfile(
    port: int,
    host: str = "127.0.0.1",
    pid: Optional[int] = None,
    lockfile_path: Optional[Path] = None,
) -> Path:
    """Write active server port and runtime process information to lockfile."""
    path = lockfile_path or DEFAULT_LOCKFILE_PATH
    data = {
        "port": port,
        "host": host,
        "url": f"http://{host}:{port}",
        "pid": pid or os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Server port lockfile written to: {path} (port={port})")
    except Exception as exc:
        logger.error(f"Failed to write server lockfile to {path}: {exc}")
    return path


def remove_server_lockfile(lockfile_path: Optional[Path] = None) -> bool:
    """Remove active server lockfile upon graceful shutdown."""
    path = lockfile_path or DEFAULT_LOCKFILE_PATH
    try:
        if path.exists():
            path.unlink()
            logger.info(f"Server port lockfile removed: {path}")
            return True
    except Exception as exc:
        logger.warning(f"Failed to remove server lockfile {path}: {exc}")
    return False


def read_server_lockfile(lockfile_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read and validate the current running server lockfile."""
    path = lockfile_path or DEFAULT_LOCKFILE_PATH
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as exc:
        logger.warning(f"Failed to parse server lockfile {path}: {exc}")
        return None
