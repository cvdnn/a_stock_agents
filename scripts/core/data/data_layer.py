# -*- coding: utf-8 -*-
"""
A-Share Quant Engine - Data Layer (数据接入与缓存层)

功能:
1. 腾讯高速行情 (L1 qt.gtimg.cn 实时快照 + ifzq.gtimg.cn 日K线) 零依赖接入
2. 本地 JSON 缓存加速 (4小时自动失效)
3. 前复权日K线清洗、数据结构标准化、ST/停牌过滤
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from core.config import OUTPUT_CACHE_DIR
    CACHE_DIR = Path(OUTPUT_CACHE_DIR) / "data_layer"
except ImportError:
    CACHE_DIR = Path(__file__).resolve().parents[3] / "output" / "cache" / "data_layer"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

try:  # 腾讯 L1 快照解析的唯一权威实现（SSOT），本模块不再重复定义字段下标
    from core.data.tencent_fields import parse_tencent_quote as _parse_tencent_quote
except ImportError:  # pragma: no cover - 兼容 scripts/core 直接入 sys.path 的场景
    from data.tencent_fields import parse_tencent_quote as _parse_tencent_quote

try:  # Windows 缺少 tzdata 时回退；中国无夏令时，UTC+8 与 Asia/Shanghai 等价
    from zoneinfo import ZoneInfo

    _SHANGHAI_TZ: Any = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    _SHANGHAI_TZ = timezone(timedelta(hours=8))

MINUTE_TS_UNPARSABLE = "MINUTE_TIMESTAMP_UNPARSABLE"
MINUTE_TS_OUT_OF_RANGE = "MINUTE_TIMESTAMP_OUT_OF_RANGE"


def _compose_minute(hour: int, minute: int) -> Tuple[Optional[str], Optional[str]]:
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None, MINUTE_TS_OUT_OF_RANGE
    return f"{hour:02d}:{minute:02d}", None


def _minute_from_epoch(seconds: float) -> Tuple[Optional[str], Optional[str]]:
    try:
        moment = datetime.fromtimestamp(seconds, tz=_SHANGHAI_TZ)
    except (OverflowError, OSError, ValueError):
        return None, MINUTE_TS_OUT_OF_RANGE
    return _compose_minute(moment.hour, moment.minute)


def normalize_minute_timestamp(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """把分钟点时间戳归一化为 Bar 起点语义的 `HH:MM`（规范 §11.5）。

    返回 `(归一化时间, None)`；无法解析或超出 00:00–23:59 时返回 `(None, 原因码)`，
    由调用方（`DataAssembler` / 捕获适配器）标记 `field_status = missing` 并计入
    `dropped_point_count`，禁止替换为默认值。规则层不得调用本函数解析时间字符串。
    """
    if value is None or isinstance(value, bool):
        return None, MINUTE_TS_UNPARSABLE
    if isinstance(value, (int, float)):
        magnitude = abs(float(value))
        return _minute_from_epoch(float(value) / (1000.0 if magnitude >= 1e11 else 1.0))

    text = str(value).strip()
    if not text:
        return None, MINUTE_TS_UNPARSABLE

    head, _, tail = text.partition(":")
    if tail and len(head) <= 2 and head.isdigit():
        seconds = tail.split(":")
        if len(seconds) <= 2 and all(part.isdigit() for part in seconds) and len(seconds[0]) == 2:
            return _compose_minute(int(head), int(seconds[0]))

    if text.isdigit():
        if len(text) == 4:
            return _compose_minute(int(text[:2]), int(text[2:]))
        if len(text) == 6:
            return _compose_minute(int(text[:2]), int(text[2:4]))
        if len(text) in (10, 13):
            return _minute_from_epoch(float(text) / (1000.0 if len(text) == 13 else 1.0))
        return None, MINUTE_TS_UNPARSABLE

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, MINUTE_TS_UNPARSABLE
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_SHANGHAI_TZ)
    return _compose_minute(parsed.hour, parsed.minute)


def _quote_row_from_tencent(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """把 `tencent_fields` 权威解析结果映射为本层既有输出契约。

    SSOT 只负责"字段值是什么"；本层保留原有的缺省回退语义
    （`high`/`low` 缺失回退现价、`turnover`/`amount` 缺失回退 0）与 ST/停牌派生字段，
    使收敛不改变下游看到的取值形态。
    """
    price = parsed["price"]
    volume = parsed["volume_hands"]
    name = parsed.get("name", "")
    return {
        "symbol": parsed["code_raw"],
        "name": name,
        "price": price,
        "prev_close": parsed["prev_close"],
        "open": parsed["open"],
        "high": parsed["high"] if parsed["high"] is not None else price,
        "low": parsed["low"] if parsed["low"] is not None else price,
        "volume": volume,
        "amount": parsed["amount"] if parsed["amount"] is not None else 0.0,
        "turnover": parsed["turnover_pct"] if parsed["turnover_pct"] is not None else 0.0,
        "pe": parsed["pe"],
        "pb": parsed["pb"],
        "change_pct": parsed["change_pct"],
        "is_st": "ST" in name or "*ST" in name,
        "is_suspended": price <= 0 or volume <= 0,
    }


class DataLayer:
    """A股数据接入与管理层"""

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """统一标的代码格式为 6位数字，并返回市场前缀格式 (如 sh600519, sz000858, bj830000)"""
        raw = symbol.strip().lower()
        digits = "".join([c for c in raw if c.isdigit()])
        if len(digits) != 6:
            raise ValueError(f"无效的股票代码: {symbol}")

        if digits.startswith(("60", "68", "90")):
            return f"sh{digits}"
        elif digits.startswith(("00", "30", "20")):
            return f"sz{digits}"
        elif digits.startswith(("43", "83", "87", "92")):
            return f"bj{digits}"
        else:
            return f"sh{digits}" if raw.startswith("sh") else f"sz{digits}"

    @classmethod
    def get_realtime_quote(cls, symbol: str) -> Dict[str, Any]:
        """获取个股实时行情快照（腾讯 L1 解析口径统一收敛至 `tencent_fields` SSOT）"""
        full_code = cls.normalize_symbol(symbol)
        url = f"http://qt.gtimg.cn/q={full_code}"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = resp.read().decode("gbk", errors="ignore")

            if "=" not in data:
                return {}
            parsed = _parse_tencent_quote(data.split("=", 1)[1].strip().strip('";'))
            if parsed is None:
                return {}
            return _quote_row_from_tencent(parsed)
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    @classmethod
    def get_kline_history(
        cls, symbol: str, num_days: int = 500, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """获取前复权日K线历史数据
        返回格式: List of dicts, sorted by date asc:
        [{'date': '2026-01-02', 'open': 10.0, 'close': 10.5, 'high': 10.8, 'low': 9.9, 'volume': 120000, 'amount': 1250000.0}, ...]
        """
        full_code = cls.normalize_symbol(symbol)
        cache_file = CACHE_DIR / f"{full_code}_qfq_kline.json"

        # 检查缓存 (如果缓存创建时间在 4小时内，直接复用)
        if use_cache and cache_file.exists():
            try:
                mtime = cache_file.stat().st_mtime
                if time.time() - mtime < 14400:  # 4 hours
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if len(data) >= min(num_days, 50):
                            return data[-num_days:]
            except Exception:
                pass

        # 从腾讯接口获取前复权日K
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full_code},day,,,{num_days},qfq"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))

            stock_data = raw_json.get("data", {}).get(full_code, {})
            klines_raw = stock_data.get("qfqday", [])
            if not klines_raw:
                klines_raw = stock_data.get("day", [])

            result = []
            for item in klines_raw:
                if not isinstance(item, list) or len(item) < 6:
                    continue
                try:
                    d = str(item[0])
                    o = float(item[1])
                    c = float(item[2])
                    h = float(item[3])
                    l = float(item[4])
                    v = float(item[5])
                    amt = (
                        float(item[6]) * 10000
                        if len(item) > 6 and isinstance(item[6], (int, float, str)) and item[6]
                        else o * v * 100
                    )
                    result.append({
                        "date": d,
                        "open": o,
                        "close": c,
                        "high": h,
                        "low": l,
                        "volume": v,
                        "amount": amt,
                    })
                except (ValueError, TypeError):
                    continue

            if result and use_cache:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            return result[-num_days:] if result else []
        except Exception as e:
            if cache_file.exists():
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        return json.load(f)[-num_days:]
                except Exception:
                    pass
            print(f"Error fetching kline for {symbol}: {e}")
            return []

    @classmethod
    def get_batch_quotes(cls, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取实时行情（腾讯 L1 解析口径统一收敛至 `tencent_fields` SSOT）"""
        full_codes = [cls.normalize_symbol(s) for s in symbols]
        query_str = ",".join(full_codes)
        url = f"http://qt.gtimg.cn/q={query_str}"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        result = {}
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = resp.read().decode("gbk", errors="ignore")

            for line in data.strip().split(";"):
                line = line.strip()
                if "=" not in line:
                    continue
                parsed = _parse_tencent_quote(line.split("=", 1)[1].strip().strip('";'))
                if parsed is None:
                    continue
                row = _quote_row_from_tencent(parsed)
                result[row["symbol"]] = row
        except Exception as e:
            print(f"Error in get_batch_quotes: {e}")
        return result


def normalize_symbol(symbol: str) -> str:
    """统一标的代码格式为带市场前缀的小写格式 (sh600519, sz000858, bj830000)"""
    return DataLayer.normalize_symbol(symbol)


def clean_kline_df(df: Any) -> Any:
    """清洗与标准化K线DataFrame，确保包含标准列: date, open, high, low, close, volume, amount"""
    try:
        import pandas as pd
    except ImportError:
        return df

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    df = df.copy()
    col_map = {
        "日期": "date", "时间": "date", "datetime": "date", "Date": "date",
        "开盘": "open", "开盘价": "open", "Open": "open",
        "最高": "high", "最高价": "high", "High": "high",
        "最低": "low", "最低价": "low", "Low": "low",
        "收盘": "close", "收盘价": "close", "Close": "close",
        "成交量": "volume", "Volume": "volume", "vol": "volume",
        "成交额": "amount", "成交金额": "amount", "Amount": "amount", "amt": "amount",
    }
    df = df.rename(columns=col_map)
    for req in ["open", "high", "low", "close"]:
        if req in df.columns:
            df[req] = pd.to_numeric(df[req], errors="coerce")
    for req in ["volume", "amount"]:
        if req in df.columns:
            df[req] = pd.to_numeric(df[req], errors="coerce").fillna(0.0)
    if "date" in df.columns:
        df["date"] = df["date"].astype(str)
        df = df.sort_values("date").reset_index(drop=True)
    return df


__all__ = ["DataLayer", "normalize_symbol", "clean_kline_df"]

