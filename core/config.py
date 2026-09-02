# -*- coding: utf-8 -*-
"""
Core configuration module for a_stock_agents (v3).
Handles dynamic project root resolution, output user data isolation, and settings loading.
Version naming rule: v2, v3, v4...
"""

import os
import sys
import yaml
from pathlib import Path

VERSION = "v3"

# 1. Resolve Project Root
if os.environ.get("A_STOCK_AGENTS_ROOT"):
    PROJECT_ROOT = Path(os.environ["A_STOCK_AGENTS_ROOT"]).resolve()
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Auto-load local .env if present (gitignored, for local private overrides like A_STOCK_OUTPUT_DIR)
def _load_dotenv():
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_dotenv()

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
            "output_dir": "output",
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

# 2. Resolve Output / User Data Directory (Complete Isolation)
# Priority: ENV VAR A_STOCK_OUTPUT_DIR > A_STOCK_USER_DATA_DIR > config.yaml paths.output_dir > default PROJECT_ROOT / "output"
env_output = os.environ.get("A_STOCK_OUTPUT_DIR") or os.environ.get("A_STOCK_USER_DATA_DIR")
if env_output:
    OUTPUT_DIR = Path(env_output) if Path(env_output).is_absolute() else (PROJECT_ROOT / env_output).resolve()
else:
    cfg_out_dir = GLOBAL_CONFIG.get("paths", {}).get("output_dir", "output")
    out_p = Path(cfg_out_dir)
    OUTPUT_DIR = out_p if out_p.is_absolute() else (PROJECT_ROOT / out_p).resolve()

# Output Subpaths
paths_cfg = GLOBAL_CONFIG.get("paths", {})
OUTPUT_POOLS_DIR = OUTPUT_DIR / paths_cfg.get("pools_dir", "pools")
OUTPUT_POSITIONS_DIR = OUTPUT_DIR / paths_cfg.get("positions_dir", "positions")
OUTPUT_REPORTS_DIR = OUTPUT_DIR / paths_cfg.get("reports_dir", "reports")
OUTPUT_CACHE_DIR = OUTPUT_DIR / paths_cfg.get("cache_dir", "cache")
OUTPUT_BACKTEST_DIR = OUTPUT_DIR / paths_cfg.get("backtest_dir", "backtest")
BACKUPS_DIR = PROJECT_ROOT / paths_cfg.get("backups_dir", "backups")

# Initialize required directories safely
for p in [OUTPUT_DIR, OUTPUT_POOLS_DIR, OUTPUT_POSITIONS_DIR, OUTPUT_REPORTS_DIR, OUTPUT_CACHE_DIR, OUTPUT_BACKTEST_DIR, BACKUPS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Backward-compatibility aliases
USER_DATA_DIR = OUTPUT_DIR
USER_POOLS_DIR = OUTPUT_POOLS_DIR
USER_POSITIONS_DIR = OUTPUT_POSITIONS_DIR
USER_REPORTS_DIR = OUTPUT_REPORTS_DIR
USER_CACHE_DIR = OUTPUT_CACHE_DIR
USER_BACKTEST_DIR = OUTPUT_BACKTEST_DIR
POOLS_DIR = OUTPUT_POOLS_DIR
POSITIONS_DIR = OUTPUT_POSITIONS_DIR
CACHE_DIR = OUTPUT_CACHE_DIR
REPORTS_DIR = OUTPUT_REPORTS_DIR

def init_output_templates():
    """Initialize output data templates if not already present."""
    pos_file = OUTPUT_POOLS_DIR / "positions.csv"
    if not pos_file.exists():
        example = OUTPUT_POOLS_DIR / "positions.csv.example"
        if example.exists():
            import shutil
            shutil.copy2(example, pos_file)

init_output_templates()
