# -*- coding: utf-8 -*-
"""
Global pytest fixtures and sys.path initialization.
Ensures src/ and src/core/ are always on sys.path for test runners.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

_TEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="astock-pytest-"))
os.environ.setdefault("A_STOCK_RUNTIME_MODE", "test")
os.environ.setdefault("A_STOCK_DEFAULT_MODEL", "mock")
os.environ.setdefault("A_STOCK_DB_PATH", str(_TEST_RUNTIME_ROOT / "chats.db"))
atexit.register(shutil.rmtree, _TEST_RUNTIME_ROOT, ignore_errors=True)

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

for p in [ROOT, SCRIPTS, SCRIPTS / "core", ROOT / "core"]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))
