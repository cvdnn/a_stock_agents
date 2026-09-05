# -*- coding: utf-8 -*-
"""
A股股票池与持仓数据规范 (Pool Schema & Validation)

定义:
1. 标的权限校验与阻断过滤 (is_blocked)
2. 自选池 (selected_pool.csv)、关注池 (watch_pool.csv)、持仓池 (positions.csv) 的统一字段规范
3. 健壮的 CSV 读写辅助函数，杜绝因外部工具 (如 tdx_sync) 导致的 Schema 漂移和字段截断
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Dict, List, Union


# ── 1. 标的权限规则 ──
def is_blocked(code: str) -> bool:
    """判断是否为受权限限制或不可交易的标的。
    
    默认阻断:
      - 688xxx, 689xxx (科创板)
      - 30xxxx, 301xxx (创业板)
      - 8xxxxx, 4xxxxx, 92xxxx (北交所 / 新三板)
    """
    raw = str(code).strip()
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) >= 6:
        core_code = digits[-6:]
    else:
        core_code = digits

    return core_code.startswith(("688", "689", "30", "8", "4", "92"))


# 兼容既有命名
_is_blocked = is_blocked


# ── 2. 标准 CSV 字段规约 ──
SELECTED_FIELDS: List[str] = [
    "code", "name", "added_date", "rating", "reason", "sector", "pe", "change_pct",
    "ma_status", "entry_trigger", "stop_loss", "take_profit", "risk_level", "market_context", "notes",
    "ta_decision", "ta_analysis_date", "ta_report_path", "consensus_rating"
]

WATCH_FIELDS: List[str] = [
    "code", "name", "added_date", "rating", "reason", "sector", "pe", "change_pct",
    "fund_flow", "entry_condition", "market_context", "ta_analysis_date"
]

POSITIONS_FIELDS: List[str] = [
    "code", "name", "buy_date", "buy_price", "qty",
    "stop_loss", "take_profit", "sector", "reason", "status",
    "strategy", "entry_trigger", "expected_days", "risk_level",
    "ma_status", "market_context", "backtest_result", "notes",
]

HISTORY_FIELDS: List[str] = [
    "code", "name", "buy_date", "sell_date", "buy_price", "sell_price",
    "qty", "pnl", "pnl_pct", "sector", "reason",
    "strategy", "entry_trigger", "hold_days", "risk_level", "notes",
]


# ── 3. 安全读写辅助函数 ──
def ensure_pool_csv(path: Union[str, Path], fields: List[str]) -> None:
    """确保目标 CSV 文件及其父目录存在，若不存在则初始化写入表头。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(fields)


def read_pool_csv(path: Union[str, Path]) -> List[Dict[str, str]]:
    """安全读取股票池 CSV 文件，若不存在则返回空列表。"""
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader if row]


def write_pool_csv(
    path: Union[str, Path],
    rows: Any,
    fields: Any = None,
) -> None:
    """安全覆盖写入股票池 CSV 文件，缺失字段自动赋空串，多余字段自动忽略。

    兼容 (path, rows, fields) 与 (path, fields, rows) 两种传参习惯。
    """
    rows_is_dicts = isinstance(rows, (list, tuple)) and any(isinstance(r, dict) for r in rows)
    fields_is_dicts = isinstance(fields, (list, tuple)) and any(isinstance(r, dict) for r in fields)

    rows_is_str_list = isinstance(rows, (list, tuple)) and bool(rows) and all(isinstance(r, str) for r in rows)
    fields_is_str_list = isinstance(fields, (list, tuple)) and bool(fields) and all(isinstance(f, str) for f in fields)

    if fields_is_dicts or (rows_is_str_list and not rows_is_dicts and not fields_is_str_list):
        # 传参习惯为 (path, fields, rows)
        actual_fields = list(rows) if isinstance(rows, (list, tuple)) else []
        actual_rows = list(fields) if isinstance(fields, (list, tuple)) else []
    else:
        # 标准传参顺序为 (path, rows, fields)
        actual_rows = list(rows) if isinstance(rows, (list, tuple)) else []
        actual_fields = list(fields) if isinstance(fields, (list, tuple)) else []

    # 若未指定 fields 但有 rows，自动提取字段
    if not actual_fields and actual_rows and isinstance(actual_rows[0], dict):
        actual_fields = list(actual_rows[0].keys())

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=actual_fields, extrasaction="ignore")
        writer.writeheader()
        for r in actual_rows:
            if isinstance(r, dict):
                row_dict = {k: r.get(k, "") for k in actual_fields}
                writer.writerow(row_dict)



__all__ = [
    "is_blocked",
    "_is_blocked",
    "SELECTED_FIELDS",
    "WATCH_FIELDS",
    "POSITIONS_FIELDS",
    "HISTORY_FIELDS",
    "ensure_pool_csv",
    "read_pool_csv",
    "write_pool_csv",
]
