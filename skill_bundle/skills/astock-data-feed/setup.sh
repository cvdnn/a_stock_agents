#!/usr/bin/env bash
set -euo pipefail
BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ ! -f "$BUNDLE_ROOT/bundle.json" ]; do
  PARENT="$(dirname "$BUNDLE_ROOT")"
  if [ "$PARENT" = "$BUNDLE_ROOT" ]; then echo "Complete A-Stock bundle required" >&2; exit 1; fi
  BUNDLE_ROOT="$PARENT"
done
PYTHON_EXEC="${A_STOCK_PYTHON:-python3}"
exec "$PYTHON_EXEC" "$BUNDLE_ROOT/runtime/doctor.py"
