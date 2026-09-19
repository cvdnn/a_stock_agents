# -*- coding: utf-8 -*-
"""
A-Stock Data Sync Engine (本地行情与K线数据同步引擎)

功能:
1. 默认同步当日行情数据与收盘日K线，固化至本地存储供指标离线分析
2. 支持时间段同步 (--start YYYY-MM-DD --end YYYY-MM-DD / --days N)
3. 支持增量同步 (Incremental) 与全量同步 (Full)
4. 数据完整性校验 (--check): 自动对照交易日历探测时间序列断点、空洞与坏点
5. 缺漏数据靶向回补 (--repair): 定向抓取缺失日期并安全合并
6. 零外部污染存储: 本地嵌入式 SQLite (output/market_data/astock_data.db) + JSON高速缓存桥接
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from core.config import PROJECT_ROOT, get_logger
    from core.data.data_bridge import DataBridge
    from core.strategy.pool_manager import PoolManager
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    import logging
    get_logger = logging.getLogger
    from scripts.core.data.data_bridge import DataBridge
    from scripts.core.strategy.pool_manager import PoolManager

logger = get_logger("core.data.sync_engine")

# 存储路径约束规范: 统一归集至 local/ 保护目录下，阻断权限泄漏
LOCAL_DIR = PROJECT_ROOT / "local"
MARKET_DATA_DIR = LOCAL_DIR / "market_data"
DB_PATH = MARKET_DATA_DIR / "astock_data.db"
CACHE_DATA_LAYER_DIR = LOCAL_DIR / "cache" / "data_layer"
LEGACY_OUTPUT_CACHE_DIR = PROJECT_ROOT / "output" / "cache" / "data_layer"


class TradeCalendar:
    """A股交易日历工具类，支持交易日判断、休市过滤与标准交易日序列生成"""

    FIXED_HOLIDAYS = {
        (1, 1), (1, 2), (1, 3),
        (5, 1), (5, 2), (5, 3),
        (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7),
    }

    @classmethod
    def is_weekend(cls, d: date) -> bool:
        return d.weekday() >= 5

    @classmethod
    def get_trading_days_between(cls, start_date: str, end_date: str, reference_dates: Optional[Set[str]] = None) -> List[str]:
        s = datetime.strptime(start_date, "%Y-%m-%d").date()
        e = datetime.strptime(end_date, "%Y-%m-%d").date()
        if s > e:
            s, e = e, s

        trading_days = []
        cur = s
        while cur <= e:
            cur_str = cur.strftime("%Y-%m-%d")
            if reference_dates and len(reference_dates) > 0:
                if cur_str in reference_dates:
                    trading_days.append(cur_str)
            else:
                if not cls.is_weekend(cur) and (cur.month, cur.day) not in cls.FIXED_HOLIDAYS:
                    trading_days.append(cur_str)
            cur += timedelta(days=1)
        return trading_days


class MarketDataStore:
    """基于 SQLite 的本地市场数据持久化与检索层 (零外部环境依赖)"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        CACHE_DATA_LAYER_DIR.mkdir(parents=True, exist_ok=True)
        LEGACY_OUTPUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # 兼容性平滑迁移: 若原 output/market_data/astock_data.db 存在且当前不存在，自动迁移至 local
        legacy_db = PROJECT_ROOT / "output" / "market_data" / "astock_data.db"
        if self.db_path == DB_PATH and legacy_db.exists() and not self.db_path.exists():
            try:
                import shutil
                shutil.copy2(legacy_db, self.db_path)
            except Exception:
                pass
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_kline (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    close REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    volume REAL NOT NULL,
                    amount REAL DEFAULT 0.0,
                    turnover_pct REAL DEFAULT 0.0,
                    pe REAL DEFAULT 0.0,
                    pb REAL DEFAULT 0.0,
                    PRIMARY KEY (symbol, date)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kline_symbol_date ON daily_kline (symbol, date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_kline (date)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_meta (
                    symbol TEXT PRIMARY KEY,
                    last_sync_date TEXT,
                    row_count INTEGER DEFAULT 0,
                    min_date TEXT,
                    max_date TEXT,
                    integrity_status TEXT DEFAULT 'unknown',
                    updated_at TEXT
                )
            """)
            conn.commit()

    def upsert_klines(self, symbol: str, klines: List[Dict[str, Any]]) -> int:
        if not klines:
            return 0
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        records = []
        for k in klines:
            records.append((
                norm_symbol,
                k["date"],
                float(k.get("open", 0.0)),
                float(k.get("close", 0.0)),
                float(k.get("high", 0.0)),
                float(k.get("low", 0.0)),
                float(k.get("volume", 0.0)),
                float(k.get("amount", 0.0)),
                float(k.get("turnover_pct", 0.0)),
                float(k.get("pe", 0.0)),
                float(k.get("pb", 0.0)),
            ))

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO daily_kline (
                    symbol, date, open, close, high, low, volume, amount, turnover_pct, pe, pb
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open=excluded.open,
                    close=excluded.close,
                    high=excluded.high,
                    low=excluded.low,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    turnover_pct=excluded.turnover_pct,
                    pe=excluded.pe,
                    pb=excluded.pb
            """, records)

            cursor.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM daily_kline WHERE symbol = ?", (norm_symbol,))
            row = cursor.fetchone()
            row_count, min_date, max_date = row[0], row[1], row[2]

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO sync_meta (
                    symbol, last_sync_date, row_count, min_date, max_date, integrity_status, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'synced', ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    last_sync_date=excluded.last_sync_date,
                    row_count=excluded.row_count,
                    min_date=excluded.min_date,
                    max_date=excluded.max_date,
                    integrity_status='synced',
                    updated_at=excluded.updated_at
            """, (norm_symbol, max_date, row_count, min_date, max_date, now_str))
            conn.commit()

        self.export_json_cache(norm_symbol)
        return len(records)

    def get_klines(self, symbol: str, count: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        query = "SELECT date, open, close, high, low, volume, amount, turnover_pct, pe, pb FROM daily_kline WHERE symbol = ?"
        params: List[Any] = [norm_symbol]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date ASC"

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = [dict(r) for r in rows]

        if count and count > 0 and len(results) > count:
            results = results[-count:]
        return results

    def get_dates_set(self, symbol: str) -> Set[str]:
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date FROM daily_kline WHERE symbol = ?", (norm_symbol,))
            return {row[0] for row in cursor.fetchall()}

    def get_sync_meta(self, symbol: str) -> Optional[Dict[str, Any]]:
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_meta WHERE symbol = ?", (norm_symbol,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def export_json_cache(self, symbol: str, limit: int = 500):
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        klines = self.get_klines(norm_symbol, count=limit)
        if not klines:
            return
        for d in [CACHE_DATA_LAYER_DIR, LEGACY_OUTPUT_CACHE_DIR]:
            try:
                d.mkdir(parents=True, exist_ok=True)
                target_file = d / f"{norm_symbol}_qfq_kline.json"
                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(klines, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"导出JSON缓存失败 {norm_symbol}: {e}")


class DataSyncEngine:
    """A股行情与K线数据同步核心调度器"""

    DEFAULT_INDICES = ["sh000001", "sz399001", "sz399006", "sh000688", "sh000300"]

    def __init__(self, store: Optional[MarketDataStore] = None):
        self.store = store or MarketDataStore()
        self.bridge = DataBridge()

    def resolve_symbols(
        self,
        codes: Optional[List[str]] = None,
        pool: Optional[str] = None,
        include_indices: bool = False,
        all_pool: bool = False,
    ) -> List[str]:
        symbols: Set[str] = set()

        if codes:
            for c in codes:
                if c.strip():
                    symbols.add(DataBridge.normalize_symbol(c.strip(), with_prefix=True))

        if pool:
            pm = PoolManager()
            pool_data = pm.get_pool(pool)
            for item in pool_data:
                c = item.get("code") or item.get("symbol")
                if c:
                    symbols.add(DataBridge.normalize_symbol(c, with_prefix=True))

        if all_pool:
            pm = PoolManager()
            for p_name in ["holdings", "watchlist", "focus"]:
                for item in pm.get_pool(p_name):
                    c = item.get("code") or item.get("symbol")
                    if c:
                        symbols.add(DataBridge.normalize_symbol(c, with_prefix=True))

        if include_indices:
            for idx in self.DEFAULT_INDICES:
                symbols.add(idx)

        if not symbols:
            pm = PoolManager()
            for item in pm.get_pool("holdings"):
                c = item.get("code") or item.get("symbol")
                if c:
                    symbols.add(DataBridge.normalize_symbol(c, with_prefix=True))
            for idx in self.DEFAULT_INDICES:
                symbols.add(idx)

        return sorted(list(symbols))

    def fetch_remote_klines(self, symbol: str, count: int = 250) -> List[Dict[str, Any]]:
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        raw_klines = self.bridge.get_kline_robust(norm_symbol, count=count)
        if not raw_klines:
            return []

        formatted = []
        for item in raw_klines:
            if len(item) < 6:
                continue
            try:
                d = str(item[0])
                o = float(item[1])
                c = float(item[2])
                h = float(item[3])
                l = float(item[4])
                v = float(item[5])
                formatted.append({
                    "date": d,
                    "open": o,
                    "close": c,
                    "high": h,
                    "low": l,
                    "volume": v,
                    "amount": round(o * v * 100, 2),
                })
            except (ValueError, TypeError):
                continue
        return formatted

    def sync_symbol(self, symbol: str, mode: str = "incremental", count: int = 250, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        meta = self.store.get_sync_meta(norm_symbol)

        if mode == "incremental" and meta and meta.get("last_sync_date") and not start_date:
            last_date = meta["last_sync_date"]
            today_str = datetime.now().strftime("%Y-%m-%d")
            if last_date >= today_str:
                return {
                    "symbol": norm_symbol,
                    "status": "up_to_date",
                    "synced_count": 0,
                    "total_count": meta.get("row_count", 0),
                    "last_date": last_date,
                }
            pull_count = 35
        else:
            pull_count = count

        remote_data = self.fetch_remote_klines(norm_symbol, count=pull_count)
        if not remote_data:
            return {
                "symbol": norm_symbol,
                "status": "failed",
                "error": "未能从上游获取K线数据",
                "synced_count": 0,
            }

        if start_date or end_date:
            filtered = []
            for r in remote_data:
                d = r["date"]
                if start_date and d < start_date:
                    continue
                if end_date and d > end_date:
                    continue
                filtered.append(r)
            remote_data = filtered

        inserted = self.store.upsert_klines(norm_symbol, remote_data)
        updated_meta = self.store.get_sync_meta(norm_symbol) or {}

        return {
            "symbol": norm_symbol,
            "status": "success",
            "synced_count": inserted,
            "total_count": updated_meta.get("row_count", 0),
            "last_date": updated_meta.get("last_sync_date", ""),
        }

    def sync_today_snapshot(self, symbols: List[str]) -> Dict[str, Any]:
        if not symbols:
            return {"status": "empty", "count": 0}

        quotes = self.bridge.fetch_batch_snapshot(symbols)
        today_str = datetime.now().strftime("%Y-%m-%d")
        updated_count = 0

        for q in quotes:
            c = q.get("code")
            if not c:
                continue
            norm_symbol = DataBridge.normalize_symbol(c, with_prefix=True)
            price = float(q.get("price") or 0.0)
            if price <= 0:
                continue

            open_p = float(q.get("open") or price)
            high_p = float(q.get("high") or price)
            low_p = float(q.get("low") or price)
            vol = float(q.get("volume") or 0.0)
            amt = float(q.get("amount") or 0.0)
            pe = float(q.get("pe") or 0.0)
            pb = float(q.get("pb") or 0.0)
            turnover = float(q.get("turnover_pct") or 0.0)

            record = [{
                "date": today_str,
                "open": open_p,
                "close": price,
                "high": high_p,
                "low": low_p,
                "volume": vol,
                "amount": amt,
                "turnover_pct": turnover,
                "pe": pe,
                "pb": pb,
            }]
            self.store.upsert_klines(norm_symbol, record)
            updated_count += 1

        return {
            "status": "success",
            "date": today_str,
            "updated_count": updated_count,
            "total_requested": len(symbols),
        }

    def audit_integrity(self, symbols: List[str], start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        benchmark_symbol = "sh000001"
        ref_dates = self.store.get_dates_set(benchmark_symbol)
        if not ref_dates or len(ref_dates) < 20:
            self.sync_symbol(benchmark_symbol, mode="full", count=250)
            ref_dates = self.store.get_dates_set(benchmark_symbol)

        audit_results = []
        for sym in symbols:
            norm_symbol = DataBridge.normalize_symbol(sym, with_prefix=True)
            local_klines = self.store.get_klines(norm_symbol, start_date=start_date, end_date=end_date)

            if not local_klines:
                audit_results.append({
                    "symbol": norm_symbol,
                    "status": "empty",
                    "row_count": 0,
                    "missing_days": [],
                    "bad_records": [],
                    "message": "本地暂无数据",
                })
                continue

            local_dates = {k["date"] for k in local_klines}
            min_date = local_klines[0]["date"]
            max_date = local_klines[-1]["date"]

            expected_trading_days = sorted([d for d in ref_dates if min_date <= d <= max_date])
            missing_days = [d for d in expected_trading_days if d not in local_dates]

            bad_records = []
            for k in local_klines:
                if k["close"] <= 0 or k["open"] <= 0 or k["high"] <= 0 or k["low"] <= 0:
                    bad_records.append(k["date"])

            status = "healthy"
            if missing_days or bad_records:
                status = "degraded"

            audit_results.append({
                "symbol": norm_symbol,
                "status": status,
                "row_count": len(local_klines),
                "min_date": min_date,
                "max_date": max_date,
                "missing_count": len(missing_days),
                "missing_days": missing_days[:10],
                "bad_count": len(bad_records),
                "bad_records": bad_records,
                "message": "数据健康完整" if status == "healthy" else f"发现 {len(missing_days)} 处缺漏交易日, {len(bad_records)} 个坏点",
            })

        return audit_results

    def repair_gaps(self, symbols: List[str]) -> List[Dict[str, Any]]:
        audit_reports = self.audit_integrity(symbols)
        repair_results = []

        for rep in audit_reports:
            sym = rep["symbol"]
            if rep["status"] == "healthy":
                repair_results.append({
                    "symbol": sym,
                    "repaired": False,
                    "message": "无需修复 (数据已完整)",
                })
                continue

            sync_res = self.sync_symbol(sym, mode="full", count=250)
            re_audit = self.audit_integrity([sym])[0]
            repair_results.append({
                "symbol": sym,
                "repaired": re_audit["status"] == "healthy",
                "synced_count": sync_res.get("synced_count", 0),
                "remaining_missing": re_audit.get("missing_count", 0),
                "message": "修复成功 (已对齐完整)" if re_audit["status"] == "healthy" else f"仍有 {re_audit.get('missing_count')} 处缺漏(可能为停牌或新股上市前)",
            })

        return repair_results

    def sync_batch(
        self,
        symbols: List[str],
        mode: str = "incremental",
        count: int = 250,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        t0 = time.time()
        results = []
        success_count = 0
        failed_count = 0

        for sym in symbols:
            try:
                res = self.sync_symbol(sym, mode=mode, count=count, start_date=start_date, end_date=end_date)
                results.append(res)
                if res.get("status") in ["success", "up_to_date"]:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"同步标的 {sym} 异常: {e}")
                results.append({"symbol": sym, "status": "error", "error": str(e)})
                failed_count += 1

        elapsed = round(time.time() - t0, 2)
        return {
            "mode": mode,
            "total_requested": len(symbols),
            "success_count": success_count,
            "failed_count": failed_count,
            "elapsed_seconds": elapsed,
            "details": results,
        }
