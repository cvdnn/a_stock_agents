# -*- coding: utf-8 -*-
"""
Core configuration module for a_stock_agents (v2.0.0).
Handles dynamic project root resolution, user data isolation, and settings loading.
"""

import os
import sys
import yaml
from pathlib import Path

VERSION = "2.0.0"

# 1. Resolve Project Root
if os.environ.get("A_STOCK_AGENTS_ROOT"):
    PROJECT_ROOT = Path(os.environ["A_STOCK_AGENTS_ROOT"]).resolve()
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = PROJECT_ROOT / "config"
SKILLS_DIR = PROJECT_ROOT / "skills"
DOCS_DIR = PROJECT_ROOT / "docs"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
BIN_DIR = PROJECT_ROOT / "bin"

# Ensure PROJECT_ROOT and core in sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core"))

def load_config() -> dict:
    """Load config.yaml with fallback defaults."""
    cfg_file = CONFIG_DIR / "config.yaml"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[Warning] Failed to load config.yaml: {e}")
    return {
        "version": VERSION,
        "app_name": "a_stock_agents",
        "paths": {
            "user_data_dir": "user_data",
            "pools_dir": "pools",
            "positions_dir": "positions",
            "reports_dir": "reports",
            "cache_dir": "cache",
            "backtest_dir": "backtest",
            "backups_dir": "backups"
        },
        "market": {
            "default_benchmark": "sh000001",
            "tax_rate_sell": 0.0005,
            "commission_rate": 0.00025,
            "transfer_fee_rate": 0.00001,
            "min_commission": 5.0,
            "breakeven_ceil_cent": True
        }
    }

GLOBAL_CONFIG = load_config()

# 2. Resolve User Data Directory (Complete Isolation)
# Priority: ENV VAR A_STOCK_USER_DATA_DIR > config.yaml paths.user_data_dir > default PROJECT_ROOT / "user_data"
env_user_data = os.environ.get("A_STOCK_USER_DATA_DIR")
if env_user_data:
    USER_DATA_DIR = Path(env_user_data).resolve()
else:
    cfg_user_dir = GLOBAL_CONFIG.get("paths", {}).get("user_data_dir", "user_data")
    user_p = Path(cfg_user_dir)
    USER_DATA_DIR = user_p if user_p.is_absolute() else (PROJECT_ROOT / user_p).resolve()

# User Data Subpaths
paths_cfg = GLOBAL_CONFIG.get("paths", {})
USER_POOLS_DIR = USER_DATA_DIR / paths_cfg.get("pools_dir", "pools")
USER_POSITIONS_DIR = USER_DATA_DIR / paths_cfg.get("positions_dir", "positions")
USER_REPORTS_DIR = USER_DATA_DIR / paths_cfg.get("reports_dir", "reports")
USER_CACHE_DIR = USER_DATA_DIR / paths_cfg.get("cache_dir", "cache")
USER_BACKTEST_DIR = USER_DATA_DIR / paths_cfg.get("backtest_dir", "backtest")
USER_BACKUPS_DIR = PROJECT_ROOT / paths_cfg.get("backups_dir", "backups")

# Initialize required directories safely
for p in [USER_DATA_DIR, USER_POOLS_DIR, USER_POSITIONS_DIR, USER_REPORTS_DIR, USER_CACHE_DIR, USER_BACKTEST_DIR, USER_BACKUPS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Backward-compatibility aliases
POOLS_DIR = USER_POOLS_DIR
POSITIONS_DIR = USER_POSITIONS_DIR
CACHE_DIR = USER_CACHE_DIR
REPORTS_DIR = USER_REPORTS_DIR

def init_user_data_templates():
    """Initialize user data templates if not already present."""
    pos_file = USER_POOLS_DIR / "positions.csv"
    if not pos_file.exists():
        example = USER_POOLS_DIR / "positions.csv.example"
        if example.exists():
            import shutil
            shutil.copy2(example, pos_file)

init_user_data_templates()
