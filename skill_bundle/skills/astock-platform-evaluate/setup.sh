#!/usr/bin/env bash
set -euo pipefail

# 1. 自定位：自身及父级向上查找 bundle.json
PROBE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT=""
while [ "$PROBE" != "/" ] && [ "$PROBE" != "." ]; do
  if [ -f "$PROBE/bundle.json" ]; then
    BUNDLE_ROOT="$PROBE"
    break
  fi
  PARENT="$(dirname "$PROBE")"
  if [ "$PARENT" = "$PROBE" ]; then break; fi
  PROBE="$PARENT"
done

# 2. 兄弟定位：查找兄弟目录 a-stock-agents/bundle.json
if [ -z "$BUNDLE_ROOT" ]; then
  PROBE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  while [ "$PROBE" != "/" ] && [ "$PROBE" != "." ]; do
    PARENT="$(dirname "$PROBE")"
    if [ -f "$PARENT/a-stock-agents/bundle.json" ]; then
      BUNDLE_ROOT="$PARENT/a-stock-agents"
      break
    fi
    if [ "$PARENT" = "$PROBE" ]; then break; fi
    PROBE="$PARENT"
  done
fi

# 3. 收据定位：查找 install.json
if [ -z "$BUNDLE_ROOT" ]; then
  RECEIPT=""
  if [ -n "${A_STOCK_WORKSPACE_ROOT:-}" ] && [ -f "$A_STOCK_WORKSPACE_ROOT/install.json" ]; then
    RECEIPT="$A_STOCK_WORKSPACE_ROOT/install.json"
  elif [ -n "${LOCALAPPDATA:-}" ] && [ -f "$LOCALAPPDATA/a_stock_agents/install.json" ]; then
    RECEIPT="$LOCALAPPDATA/a_stock_agents/install.json"
  elif [ -f "$HOME/.local/share/a_stock_agents/install.json" ]; then
    RECEIPT="$HOME/.local/share/a_stock_agents/install.json"
  elif [ -f "$HOME/Library/Application Support/a_stock_agents/install.json" ]; then
    RECEIPT="$HOME/Library/Application Support/a_stock_agents/install.json"
  fi
  if [ -n "$RECEIPT" ]; then
    ROOT_FROM_RECEIPT=$(grep -o '"bundle_root"[[:space:]]*:[[:space:]]*"[^"]*"' "$RECEIPT" | head -n1 | cut -d'"' -f4 || true)
    if [ -z "$ROOT_FROM_RECEIPT" ]; then
      ROOT_FROM_RECEIPT=$(grep -o '"runtime_root"[[:space:]]*:[[:space:]]*"[^"]*"' "$RECEIPT" | head -n1 | cut -d'"' -f4 || true)
      if [ -n "$ROOT_FROM_RECEIPT" ]; then
        ROOT_FROM_RECEIPT="$(dirname "$ROOT_FROM_RECEIPT")"
      fi
    fi
    if [ -n "$ROOT_FROM_RECEIPT" ] && [ -f "$ROOT_FROM_RECEIPT/bundle.json" ]; then
      BUNDLE_ROOT="$ROOT_FROM_RECEIPT"
    fi
  fi
fi

if [ -z "$BUNDLE_ROOT" ]; then
  echo "错误: ANCHOR_SKILL_MISSING (未找到 bundle.json 或 a-stock-agents 锚点)" >&2
  exit 1
fi

PYTHON_EXEC="${A_STOCK_PYTHON:-python3}"
exec "$PYTHON_EXEC" "$BUNDLE_ROOT/runtime/doctor.py"
