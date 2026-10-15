#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -eq 0 ] || [ "${1:0:1}" = '-' ]; then
    exec python apps/web-console/backend/server/run.py --host "${A_STOCK_SERVER_HOST:-0.0.0.0}" --port "${A_STOCK_SERVER_PORT:-6300}" "$@"
fi
if [ "$1" = "astock" ]; then
    shift
    exec python skill_bundle/runtime/cli.py "$@"
fi
exec "$@"
