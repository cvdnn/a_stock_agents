#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="${A_STOCK_PYTHON:-}"
if [ -z "$PYTHON_EXEC" ]; then
  if [ -x "$SCRIPT_DIR/../../.venv/bin/python" ]; then PYTHON_EXEC="$SCRIPT_DIR/../../.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then PYTHON_EXEC=python3
  else PYTHON_EXEC=python; fi
fi
exec "$PYTHON_EXEC" "$SCRIPT_DIR/manage.py" setup "$@"
