# -*- coding: utf-8 -*-
"""
Core configuration module for a_stock_agents (v3).
Handles dynamic project root resolution, output user data isolation, and settings loading.
Version naming rule: v2, v3, v4...
"""

import os
import sys
import yaml
import logging
from pathlib import Path

VERSION = "3.0.0"


def get_logger(name: str = "a_stock") -> logging.Logger:
    """获取带统一配置的分级日志器。

    可通过环境变量 ASTOCK_LOG_LEVEL 控制级别 (DEBUG, INFO, WARNING, ERROR)，默认为 WARNING。
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        level_name = os.environ.get("ASTOCK_LOG_LEVEL", "WARNING").upper()
        level = getattr(logging, level_name, logging.WARNING)
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


_config_logger = get_logger("core.config")

# ═══════════════════════════════════════════════════
#  Market Prefixes & Normalization (SSOT)
# ═══════════════════════════════════════════════════

MARKET_PREFIX_SH = "sh"
MARKET_PREFIX_SZ = "sz"
MARKET_PREFIX_BJ = "bj"
DEFAULT_BENCHMARK = "sh000001"

# Standard Market Fee & Trading Defaults
DEFAULT_TAX_RATE_SELL = 0.0005        # 印花税 (卖出单边万5)
DEFAULT_COMMISSION_RATE = 0.00025     # 佣金率 (万2.5)
DEFAULT_TRANSFER_FEE_RATE = 0.00001   # 过户费 (万0.1)
DEFAULT_MIN_COMMISSION = 5.0          # 最低起收佣金 (5元)

# Outsource Magic Numbers & Standard Thresholds
DEFAULT_RATING_THRESHOLDS = {
    "A": 80.0,
    "B": 65.0,
    "C": 50.0,
}
DEFAULT_STOP_LOSS_PCT = 0.05          # 默认日内硬止损 -5%
DEFAULT_WARN_LOSS_PCT = 0.03          # 默认T0警戒线 -3%
DEFAULT_MA_BUFFER_PCT = 0.02          # 均线支撑/防守缓冲 2%
DEFAULT_BIAS_THRESHOLD = 8.0          # 乖离率偏离警戒线 8%
DEFAULT_RSI_OVERSOLD = 30.0           # RSI 超卖反弹线
DEFAULT_RSI_OVERBOUGHT = 70.0         # RSI 超买风险线


def infer_market_prefix(code: str) -> str:
    """推断市场前缀 (sh/sz/bj) — 单点真实源 (SSOT)"""
    s = str(code).strip().lower()
    if s.startswith("sh") or s.endswith((".sh", ".ss")):
        return MARKET_PREFIX_SH
    if s.startswith("bj") or s.endswith(".bj"):
        return MARKET_PREFIX_BJ
    if s.startswith("sz") or s.endswith(".sz"):
        return MARKET_PREFIX_SZ
    clean = s.replace("sh", "").replace("sz", "").replace("bj", "").split(".")[0]
    if clean.startswith(("8", "4", "92")):
        return MARKET_PREFIX_BJ
    elif clean.startswith(("6", "5", "9")):
        return MARKET_PREFIX_SH
    else:
        return MARKET_PREFIX_SZ



def normalize_symbol(code: str, with_prefix: bool = True) -> str:
    """标准化股票代码为带前缀或纯数字格式，如 sh600519 或 600519"""
    clean = str(code).strip().lower().replace("sh", "").replace("sz", "").replace("bj", "").split(".")[0]
    if not with_prefix:
        return clean
    prefix = infer_market_prefix(code)
    return f"{prefix}{clean}"


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
        except Exception as exc:
            _config_logger.debug(f"Failed to load .env: {exc}")

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
            "breakeven_ceil_cent": True,
            "is_user_configured": False
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

IS_CUSTOM_OUTPUT = OUTPUT_DIR.resolve() != (PROJECT_ROOT / "output").resolve()

# Output Subpaths
paths_cfg = GLOBAL_CONFIG.get("paths", {})
OUTPUT_POOLS_DIR = OUTPUT_DIR / paths_cfg.get("pools_dir", "pools")
OUTPUT_POSITIONS_DIR = OUTPUT_POOLS_DIR  # Unified with pools (positions.csv lives in pools_dir)
OUTPUT_REPORTS_DIR = OUTPUT_DIR / paths_cfg.get("reports_dir", "reports")
OUTPUT_CACHE_DIR = OUTPUT_DIR / paths_cfg.get("cache_dir", "cache")
OUTPUT_BACKTEST_DIR = OUTPUT_DIR / paths_cfg.get("backtest_dir", "backtest")
BACKUPS_DIR = PROJECT_ROOT / paths_cfg.get("backups_dir", "backups")

# Initialize required directories safely
for p in [OUTPUT_DIR, OUTPUT_POOLS_DIR, OUTPUT_REPORTS_DIR, OUTPUT_CACHE_DIR, OUTPUT_BACKTEST_DIR, BACKUPS_DIR]:
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

def get_pool_path(filename: str = "positions.csv") -> Path:
    """Get absolute path to a specific pool file under current OUTPUT_POOLS_DIR."""
    if not filename.endswith(".csv"):
        filename = f"{filename}.csv"
    return OUTPUT_POOLS_DIR / filename

def get_cache_path(filename: str) -> Path:
    """Get absolute path to a cache file under current OUTPUT_CACHE_DIR."""
    return OUTPUT_CACHE_DIR / filename

def get_report_path(filename: str) -> Path:
    """Get absolute path to a report file under current OUTPUT_REPORTS_DIR."""
    return OUTPUT_REPORTS_DIR / filename

def get_backtest_path(filename: str) -> Path:
    """Get absolute path to a backtest file under current OUTPUT_BACKTEST_DIR."""
    return OUTPUT_BACKTEST_DIR / filename

def init_output_templates(target_pools_dir: Path = None):
    """Initialize output data templates and pool CSV files if not already present."""
    import shutil
    import csv

    pools_dir = target_pools_dir or OUTPUT_POOLS_DIR
    pools_dir.mkdir(parents=True, exist_ok=True)

    # Standard default fields
    default_headers = {
        "positions.csv": ["code", "name", "buy_date", "buy_price", "qty", "stop_loss", "take_profit",
                          "sector", "reason", "status", "strategy", "entry_trigger", "expected_days",
                          "risk_level", "ma_status", "market_context", "backtest_result", "notes"],
        "selected_pool.csv": ["code", "name", "added_date", "rating", "reason", "sector", "pe", "change_pct",
                              "ma_status", "entry_trigger", "stop_loss", "take_profit", "risk_level",
                              "market_context", "notes", "ta_decision", "ta_analysis_date", "ta_report_path",
                              "consensus_rating"],
        "watch_pool.csv": ["code", "name", "added_date", "rating", "reason", "sector", "pe", "change_pct",
                           "fund_flow", "entry_condition", "market_context", "ta_analysis_date"],
    }

    # Possible template source directories to copy .example files from
    template_sources = [
        PROJECT_ROOT / "skills" / "a-share-dashboard" / "data",
        PROJECT_ROOT / "output" / "pools",
    ]

    for filename, headers in default_headers.items():
        example_name = f"{filename}.example"
        target_example = pools_dir / example_name
        target_file = pools_dir / filename

        # 1. Copy .example file if not present in target directory
        if not target_example.exists():
            for src_dir in template_sources:
                src_example = src_dir / example_name
                if src_example.exists() and src_example.resolve() != target_example.resolve():
                    try:
                        shutil.copy2(src_example, target_example)
                        break
                    except Exception as exc:
                        _config_logger.debug(f"Failed copying example {src_example}: {exc}")

        # 2. Initialize target CSV file if missing
        if not target_file.exists():
            if target_example.exists():
                try:
                    shutil.copy2(target_example, target_file)
                except Exception as exc:
                    _config_logger.debug(f"Failed copying {target_example} to {target_file}: {exc}")
            # Fallback: create empty CSV with standard headers
            if not target_file.exists():
                try:
                    with open(target_file, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(headers)
                except Exception as exc:
                    _config_logger.warning(f"Failed initializing default CSV {target_file}: {exc}")

init_output_templates()

def get_active_paths() -> dict:
    """Return a dictionary of all actively resolved workspace and output paths."""
    return {
        "project_root": str(PROJECT_ROOT),
        "output_dir": str(OUTPUT_DIR),
        "pools_dir": str(OUTPUT_POOLS_DIR),
        "positions_dir": str(OUTPUT_POSITIONS_DIR),
        "reports_dir": str(OUTPUT_REPORTS_DIR),
        "cache_dir": str(OUTPUT_CACHE_DIR),
        "backtest_dir": str(OUTPUT_BACKTEST_DIR),
        "backups_dir": str(BACKUPS_DIR),
        "is_custom_output": IS_CUSTOM_OUTPUT,
    }

def get_market_config() -> dict:
    """Return active market fee & cost configuration."""
    global GLOBAL_CONFIG
    m = GLOBAL_CONFIG.get("market", {})
    return {
        "default_benchmark": m.get("default_benchmark", "sh000001"),
        "tax_rate_sell": float(m.get("tax_rate_sell", 0.0005)),
        "commission_rate": float(m.get("commission_rate", 0.00025)),
        "transfer_fee_rate": float(m.get("transfer_fee_rate", 0.00001)),
        "min_commission": float(m.get("min_commission", 5.0)),
        "breakeven_ceil_cent": bool(m.get("breakeven_ceil_cent", True)),
        "is_user_configured": bool(m.get("is_user_configured", False)),
    }

def save_market_config(commission_rate: float = None,
                       min_commission: float = None,
                       tax_rate_sell: float = None,
                       transfer_fee_rate: float = None,
                       is_user_configured: bool = True) -> dict:
    """Update and persist market configuration to config.yaml and reload GLOBAL_CONFIG."""
    global GLOBAL_CONFIG
    cfg_file = CONFIG_DIR / "config.yaml"
    cfg_data = {}
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg_data = yaml.safe_load(f) or {}
        except Exception:
            cfg_data = {}
    
    if "market" not in cfg_data or not isinstance(cfg_data["market"], dict):
        cfg_data["market"] = {}
    
    if commission_rate is not None:
        cfg_data["market"]["commission_rate"] = float(commission_rate)
    if min_commission is not None:
        cfg_data["market"]["min_commission"] = float(min_commission)
    if tax_rate_sell is not None:
        cfg_data["market"]["tax_rate_sell"] = float(tax_rate_sell)
    if transfer_fee_rate is not None:
        cfg_data["market"]["transfer_fee_rate"] = float(transfer_fee_rate)
    if is_user_configured is not None:
        cfg_data["market"]["is_user_configured"] = bool(is_user_configured)
        
    try:
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg_data, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        print(f"[Error] Failed to write config.yaml: {e}")
        
    GLOBAL_CONFIG = load_config()
    return get_market_config()

def check_market_config_prompt() -> tuple:
    """
    Check whether market commission is configured by user.
    Returns: (needs_prompt: bool, message: str)
    """
    m = get_market_config()
    if not m.get("is_user_configured", False):
        comm_pct = m['commission_rate'] * 10000.0
        msg = (
            f"[费率未确认提醒] 当前使用默认券商佣金参数 (万{comm_pct:.1f}，最低 {m['min_commission']:.1f} 元起收)。\n"
            f"  若实际佣金不同（如万1、万1.5、免5等），将直接影响最低保本卖出价/做T成本计算精度。\n"
            f"  可在命令行一键配置: python core/cli.py config market --commission {m['commission_rate']} --min-commission {m['min_commission']}"
        )
        return True, msg
    return False, ""


