# -*- coding: utf-8 -*-
"""
server.run - Entry point to launch the FastAPI server via Uvicorn.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import uvicorn

# Ensure project root and src in sys.path
CUR_DIR = Path(__file__).resolve().parent
def _find_project_root() -> Path:
    import os
    if os.environ.get("A_STOCK_AGENTS_ROOT"):
        return Path(os.environ["A_STOCK_AGENTS_ROOT"]).resolve()
    for p in [CUR_DIR] + list(CUR_DIR.parents):
        if (p / "pyproject.toml").exists() or (p / "AGENTS.md").exists():
            return p
    return CUR_DIR.parent.parent

PROJECT_ROOT = _find_project_root()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for p in [PROJECT_ROOT, SCRIPTS_DIR]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from server.config import server_settings
from server.port_utils import find_free_port, remove_server_lockfile, write_server_lockfile


def main():
    parser = argparse.ArgumentParser(description="Start A-Stock Agents Web API Server")
    parser.add_argument("--host", type=str, default=server_settings.host, help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=server_settings.port, help="Port to bind (default: 8000; use 0 for ephemeral auto-hunt)")
    parser.add_argument("--reload", action="store_true", default=server_settings.reload, help="Enable auto-reload")
    args = parser.parse_args()

    # Dynamic port hunting if port is 0
    actual_port = args.port
    if actual_port == 0:
        actual_port = find_free_port()
        print(f"🎯 Dynamic port hunting allocated free port: {actual_port}")

    # Write runtime lockfile for Desktop Sidecar / TUI client auto-discovery
    write_server_lockfile(port=actual_port, host=args.host)

    print(f"🚀 Starting A-Stock Agents Server on http://{args.host}:{actual_port}")
    print(f"📖 API Documentation: http://{args.host}:{actual_port}/docs")
    print(f"💬 AIChat Stream: http://{args.host}:{actual_port}/api/chat/completions/stream")
    print(f"🛠️ Skill Governance: http://{args.host}:{actual_port}/api/skills")

    try:
        uvicorn.run(
            "server.app:app",
            host=args.host,
            port=actual_port,
            reload=args.reload,
            log_level="info",
        )
    finally:
        remove_server_lockfile()


if __name__ == "__main__":
    main()

