#!/usr/bin/env bash
set -e

# Ensure required runtime directories exist inside container
mkdir -p /app/output/pools /app/output/reports /app/output/cache /app/output/backtest /app/backups

# If no arguments provided or starts with flag, default to launching the web server
if [ "$#" -eq 0 ] || [ "${1:0:1}" = '-' ]; then
    echo "======================================================================"
    echo " [A-Stock Agents Container] 正在启动服务..."
    echo " Web 访问入口:   http://0.0.0.0:6300"
    echo " API 接口文档:   http://0.0.0.0:6300/docs"
    echo "======================================================================"
    exec python scripts/server/run.py --host "${A_STOCK_SERVER_HOST:-0.0.0.0}" --port "${A_STOCK_SERVER_PORT:-6300}" "$@"
fi

# Support running CLI directly: e.g. docker run ... astock data quote 600519 --json
if [ "$1" = "astock" ]; then
    shift
    exec python scripts/core/cli.py "$@"
fi

exec "$@"
