"""Validated local daily-K import shared by preview and commit endpoints."""
from __future__ import annotations

import base64
import binascii
import csv
import io
import math
import re
from contextlib import closing
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

from core.data.sync_engine import DB_PATH, DataBridge, MarketDataStore

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
REQUIRED = ("symbol", "date", "open", "high", "low", "close", "volume")
ALIASES = {
    "symbol": ("symbol", "code", "stock_code", "股票代码", "证券代码"),
    "date": ("date", "trade_date", "日期", "交易日期"),
    "open": ("open", "开盘", "开盘价"),
    "high": ("high", "最高", "最高价"),
    "low": ("low", "最低", "最低价"),
    "close": ("close", "收盘", "收盘价"),
    "volume": ("volume", "vol", "成交量"),
    "amount": ("amount", "成交额"),
}


def _read_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    name = str(payload.get("name") or "").lower()
    if not name.endswith((".csv", ".xlsx", ".xls")):
        raise ValueError("仅支持 CSV / XLSX / XLS 文件")
    if payload.get("data_type") != "daily":
        raise ValueError("当前导入执行层仅支持日线行情；其他类型可保存规则，暂不可导入")
    encoded = payload.get("content_base64")
    if not isinstance(encoded, str) or len(encoded) > MAX_FILE_BYTES * 2:
        raise ValueError("文件内容无效或超出 5 MB 上限")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("文件内容不是有效的 Base64") from exc
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError("文件为空或超出 5 MB 上限")
    if name.endswith(".csv"):
        text = None
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("CSV 编码不受支持，请使用 UTF-8 或 GB18030")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    else:
        try:
            import pandas as pd
            frame = pd.read_excel(io.BytesIO(raw), dtype=str).fillna("")
            rows = frame.to_dict(orient="records")
        except (ImportError, ValueError) as exc:
            raise ValueError(f"Excel 文件读取失败，请确认工作簿格式和解析依赖：{exc}") from exc
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError(f"文件须包含 1–{MAX_ROWS} 条数据记录")
    return rows


def _date(value: Any) -> str:
    raw = str(value or "").strip()
    if re.fullmatch(r"\d{8}", raw):
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError("日期须为 YYYY-MM-DD 或 YYYYMMDD") from exc


def _number(value: Any, label: str, positive: bool = True) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须为数字") from exc
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        raise ValueError(f"{label}须为{'正数' if positive else '非负数'}")
    return number


def validate_import(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    rows = _read_rows(payload)
    headers = {str(key).strip().lower(): key for key in rows[0]}
    columns = {name: next((headers[alias.lower()] for alias in variants if alias.lower() in headers), None) for name, variants in ALIASES.items()}
    missing = [name for name in REQUIRED if columns[name] is None]
    if missing:
        raise ValueError(f"缺少必填列：{', '.join(missing)}")
    valid: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    seen = set()
    duplicates = 0
    for number, raw in enumerate(rows, start=2):
        try:
            symbol = str(raw.get(columns["symbol"]) or "").strip()
            if not re.fullmatch(r"(?:(?:sh|sz|bj))?\d{6}", symbol, re.I):
                raise ValueError("股票代码须为 6 位数字或带 sh/sz/bj 前缀")
            symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
            day = _date(raw.get(columns["date"]))
            item = {"symbol": symbol, "date": day}
            for key in ("open", "high", "low", "close", "volume"):
                item[key] = _number(raw.get(columns[key]), key, key != "volume")
            item["amount"] = _number(raw.get(columns["amount"]), "amount", False) if columns["amount"] and str(raw.get(columns["amount"]) or "").strip() else 0.0
            if item["high"] < max(item["open"], item["close"], item["low"]) or item["low"] > min(item["open"], item["close"]):
                raise ValueError("最高/最低价与开收盘价不一致")
            key = (symbol, day)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            valid.append(item)
        except ValueError as exc:
            errors.append({"row": number, "reason": str(exc)})
    return valid, errors, duplicates


def preview_import(payload: Dict[str, Any]) -> Dict[str, Any]:
    valid, errors, duplicates = validate_import(payload)
    return {
        "status": "success", "valid_count": len(valid), "error_count": len(errors),
        "duplicate_count": duplicates, "errors": errors[:50], "sample": valid[:5],
        "ready": bool(valid) and not errors,
    }


def commit_import(payload: Dict[str, Any]) -> Dict[str, Any]:
    valid, errors, duplicates = validate_import(payload)
    if errors or not valid:
        raise ValueError("文件包含无效记录，请先完成校验并修正后重试")
    mode = payload.get("mode")
    if mode not in ("missing", "overwrite"):
        raise ValueError("导入方式须为 missing 或 overwrite")
    store = MarketDataStore(DB_PATH)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in valid:
        grouped.setdefault(row["symbol"], []).append(row)
    imported = 0
    skipped = duplicates
    for symbol, items in grouped.items():
        if mode == "missing":
            with closing(store._get_conn()) as conn:
                existing = {row[0] for row in conn.execute("SELECT date FROM daily_kline WHERE symbol = ?", (symbol,))}
            skipped += sum(row["date"] in existing for row in items)
            items = [row for row in items if row["date"] not in existing]
        if items:
            imported += store.upsert_klines(symbol, items)
    return {"status": "success", "imported_count": imported, "skipped_count": skipped, "symbol_count": len(grouped), "completed_at": datetime.now().isoformat(timespec="seconds")}
