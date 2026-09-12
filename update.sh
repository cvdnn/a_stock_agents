#!/usr/bin/env bash
# ==============================================================================
# a_stock_agents 安全升级脚本 (Linux / macOS)
# ==============================================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

if [ -f ".venv/bin/python" ]; then
    PY_BIN=".venv/bin/python"
elif command -v python3 &> /dev/null; then
    PY_BIN="python3"
else
    PY_BIN="python"
fi

"${PY_BIN}" bin/update.py "$@"
