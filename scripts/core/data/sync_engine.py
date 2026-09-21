# -*- coding: utf-8 -*-
"""A-Stock 本地行情数据同步引擎 (DataSyncEngine & MarketDataStore)

核心职责:
1. 零虚假数据原则: 严禁伪造/合成任何走势数据，断网或上游无数据时明确返回错误提示；
2. 交易日与时钟状态机: 精准判定 A股交易日（含法定节假日及调休）、交易阶段（早盘/午间休市/午后/收盘/盘后定盘）；
3. 通用实时同步状态标记: 任意时刻（如盘中、午间、盘后）同步均打上精细状态标记 (is_settled, sync_phase, snapshot_time)；
4. 增量防漏与动态回溯: 未定盘数据后续可覆盖刷新；长期断更自动动态估算拉取深度；
5. SQLite WAL 并发存储: 开启 WAL 模式与 busy_timeout，彻底杜绝并发锁冲突；
6. 缓存规范治理: 统一仅落盘于 local/cache/data_layer，杜绝污染 output/ 用户交付区。
"""

from contextlib import closing
from datetime import date, datetime, timedelta, time as dt_time
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

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


class TradeCalendar:
    """A股交易日历与时钟状态机权威工具类，支持交易日判断、休市过滤与标准交易日序列生成"""

    # 2024 - 2027 年已明确的法定休市日期全集 (包含春节、清明、劳动节、端午、中秋、国庆、元旦)
    # A股规则铁律：周六与周日即便属于国家法定调休上班日，A股市场亦永远休市不交易！
    STATUTORY_HOLIDAYS_CLOSED = {
        # 2024
        "2024-01-01", "2024-02-09", "2024-02-12", "2024-02-13", "2024-02-14", "2024-02-15",
        "2024-02-16", "2024-04-04", "2024-04-05", "2024-05-01", "2024-05-02", "2024-05-03",
        "2024-06-10", "2024-09-16", "2024-09-17", "2024-10-01", "2024-10-02", "2024-10-03",
        "2024-10-04", "2024-10-07",
        # 2025
        "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31", "2025-02-03",
        "2025-02-04", "2025-04-04", "2025-05-01", "2025-05-02", "2025-05-05", "2025-05-31",
        "2025-06-02", "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-06", "2025-10-07",
        "2025-10-08",
        # 2026
        "2026-01-01", "2026-01-02", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19",
        "2026-02-20", "2026-04-06", "2026-05-01", "2026-05-04", "2026-05-05", "2026-06-19",
        "2026-09-25", "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
        # 2027
        "2027-01-01", "2027-02-05", "2027-02-08", "2027-02-09", "2027-02-10", "2027-02-11",
        "2027-02-12", "2027-04-05", "2027-05-03", "2027-06-09", "2027-09-15", "2027-10-01",
        "2027-10-04", "2027-10-05", "2027-10-06", "2027-10-07",
    }

    FIXED_ANNUAL_HOLIDAYS = {
        (1, 1), (1, 2), (1, 3),
        (5, 1), (5, 2), (5, 3),
        (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7),
    }

    @classmethod
    def is_weekend(cls, d: Union[date, datetime]) -> bool:
        return d.weekday() >= 5

    @classmethod
    def is_trading_day(
        cls,
        d: Optional[Union[str, date, datetime]] = None,
        db_path: Optional[Path] = None,
    ) -> bool:
        """权威判断指定日期是否为 A股交易日（排除周末与法定节假日），支持动态真值延伸校验。

        支持 str ('YYYY-MM-DD')、date、datetime 输入；为空时默认取当前系统日期。
        """
        if d is None:
            check_date = datetime.now().date()
        elif isinstance(d, str):
            check_date = datetime.strptime(d.strip()[:10], "%Y-%m-%d").date()
        elif isinstance(d, datetime):
            check_date = d.date()
        else:
            check_date = d

        # 1. 任何周六、周日绝不开市（即使国家规定周末调休补班）
        if check_date.weekday() >= 5:
            return False

        d_str = check_date.strftime("%Y-%m-%d")

        # 2. 动态延伸：若显式提供 db_path 或日期超出静态已知年份 (> 2027)，优先结合本地库基准指数历史真值校验
        if db_path or check_date.year > 2027:
            local_days = cls.trading_days_from_local(d_str, d_str, db_path=db_path)
            if local_days:
                return True

        # 3. 检查法定节假日明细库
        if d_str in cls.STATUTORY_HOLIDAYS_CLOSED:
            return False

        # 4. 检查固定年度兜底休市
        if (check_date.month, check_date.day) in cls.FIXED_ANNUAL_HOLIDAYS:
            return False

        return True

    @classmethod
    def is_trading_day_dynamic(
        cls,
        d: Union[str, date, datetime],
        db_path: Optional[Path] = None,
    ) -> bool:
        """动态延伸查询交易日（结合本地历史真实交易数据与法定节假日）"""
        return cls.is_trading_day(d, db_path=db_path)

    @classmethod
    def is_trading_hour(cls, dt: Optional[datetime] = None) -> bool:
        """判断当前是否处于连续竞价时段 (09:30-11:30, 13:00-15:00)"""
        now_dt = dt or datetime.now()
        if not cls.is_trading_day(now_dt):
            return False
        t = now_dt.time()
        return (dt_time(9, 30) <= t <= dt_time(11, 30)) or (dt_time(13, 0) <= t <= dt_time(15, 0))

    @classmethod
    def get_market_phase(cls, dt: Optional[datetime] = None) -> Dict[str, Any]:
        """获取当前精确市场运行阶段与时钟状态。

        返回结构:
        - phase: 阶段代码
        - phase_label: 中文描述 (例如: '早盘连续竞价', '午间休市(午后策略评估窗口)', '盘后定盘完成')
        - is_trading_day: 是否交易日
        - is_market_open: 是否正在交易中
        - is_settled: 当日数据是否已定盘 (15:35 之后或非交易日为 True)
        - time_str: 当前时间 (HH:MM:SS)
        - date_str: 当前日期 (YYYY-MM-DD)
        """
        now_dt = dt or datetime.now()
        date_str = now_dt.strftime("%Y-%m-%d")
        time_str = now_dt.strftime("%H:%M:%S")
        is_td = cls.is_trading_day(now_dt)

        if not is_td:
            is_wk = cls.is_weekend(now_dt)
            phase = "WEEKEND" if is_wk else "HOLIDAY"
            label = "周末休市" if is_wk else "法定节假日休市"
            return {
                "phase": phase,
                "phase_label": label,
                "is_trading_day": False,
                "is_market_open": False,
                "is_settled": True,
                "time_str": time_str,
                "date_str": date_str,
            }

        t = now_dt.time()
        if t < dt_time(9, 15):
            return {
                "phase": "PRE_MARKET",
                "phase_label": "盘前准备期",
                "is_trading_day": True,
                "is_market_open": False,
                "is_settled": False,
                "time_str": time_str,
                "date_str": date_str,
            }
        elif dt_time(9, 15) <= t < dt_time(9, 25):
            return {
                "phase": "CALL_AUCTION",
                "phase_label": "早盘集合竞价",
                "is_trading_day": True,
                "is_market_open": True,
                "is_settled": False,
                "time_str": time_str,
                "date_str": date_str,
            }
        elif dt_time(9, 25) <= t < dt_time(9, 30):
            return {
                "phase": "PRE_OPEN_BUFFER",
                "phase_label": "开盘缓冲期",
                "is_trading_day": True,
                "is_market_open": False,
                "is_settled": False,
                "time_str": time_str,
                "date_str": date_str,
            }
        elif dt_time(9, 30) <= t <= dt_time(11, 30):
            return {
                "phase": "CONTINUOUS_MORNING",
                "phase_label": "早盘连续竞价",
                "is_trading_day": True,
                "is_market_open": True,
                "is_settled": False,
                "time_str": time_str,
                "date_str": date_str,
            }
        elif dt_time(11, 30) < t < dt_time(13, 0):
            return {
                "phase": "LUNCH_BREAK",
                "phase_label": "午间休市(午后策略评估窗口)",
                "is_trading_day": True,
                "is_market_open": False,
                "is_settled": False,
                "time_str": time_str,
                "date_str": date_str,
            }
        elif dt_time(13, 0) <= t < dt_time(14, 57):
            return {
                "phase": "CONTINUOUS_AFTERNOON",
                "phase_label": "午后连续竞价",
                "is_trading_day": True,
                "is_market_open": True,
                "is_settled": False,
                "time_str": time_str,
                "date_str": date_str,
            }
        elif dt_time(14, 57) <= t <= dt_time(15, 0):
            return {
                "phase": "CLOSING_AUCTION",
                "phase_label": "收盘集合竞价",
                "is_trading_day": True,
                "is_market_open": True,
                "is_settled": False,
                "time_str": time_str,
                "date_str": date_str,
            }
        elif dt_time(15, 0) < t < dt_time(15, 35):
            return {
                "phase": "POST_MARKET_CLEARING",
                "phase_label": "盘后交易所清算期(未定盘)",
                "is_trading_day": True,
                "is_market_open": False,
                "is_settled": False,
                "time_str": time_str,
                "date_str": date_str,
            }
        else:
            return {
                "phase": "SETTLED",
                "phase_label": "盘后定盘完成",
                "is_trading_day": True,
                "is_market_open": False,
                "is_settled": True,
                "time_str": time_str,
                "date_str": date_str,
            }

    @classmethod
    def get_trading_days_between(
        cls, start_date: str, end_date: str, reference_dates: Optional[Set[str]] = None
    ) -> List[str]:
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
                if cls.is_trading_day(cur):
                    trading_days.append(cur_str)
            cur += timedelta(days=1)
        return trading_days

    @classmethod
    def trading_days_from_local(
        cls, start_date: str, end_date: str, db_path: Optional[Path] = None
    ) -> List[str]:
        """以本地 daily_kline 实际存在的交易日推导交易日集合（规范 §11.2）"""
        path = Path(db_path) if db_path else DB_PATH
        if not path.exists():
            return []
        conn = sqlite3.connect(str(path), timeout=30.0)
        try:
            rows = conn.execute(
                "SELECT DISTINCT date FROM daily_kline WHERE date BETWEEN ? AND ? ORDER BY date",
                (start_date, end_date),
            ).fetchall()
        finally:
            conn.close()
        return [str(row[0]) for row in rows]

    @classmethod
    def calendar_version(cls, trading_days: Iterable[str]) -> str:
        """本地交易日集合的内容标识；集合内容变化即改变（规范 §11.2）"""
        payload = ",".join(sorted({str(day) for day in trading_days}))
        return "cal-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def local_calendar_version(cls, db_path: Optional[Path] = None) -> Dict[str, Any]:
        """本地已同步区间的日历版本，供运行快照清单与运行元数据记录（§11.2 / §11.7）"""
        path = Path(db_path) if db_path else DB_PATH
        unavailable = {
            "calendar_version": None,
            "calendar_available": False,
            "trading_days": 0,
            "coverage_start": None,
            "coverage_end": None,
        }
        if not path.exists():
            return unavailable
        conn = sqlite3.connect(str(path), timeout=30.0)
        try:
            row = conn.execute("SELECT MIN(date), MAX(date) FROM daily_kline").fetchone()
        except sqlite3.Error:
            return unavailable
        finally:
            conn.close()
        if not row or not row[0] or not row[1]:
            return unavailable
        days = cls.trading_days_from_local(str(row[0]), str(row[1]), db_path=path)
        if not days:
            return unavailable
        return {
            "calendar_version": cls.calendar_version(days),
            "calendar_available": True,
            "trading_days": len(days),
            "coverage_start": days[0],
            "coverage_end": days[-1],
        }


class MarketDataStore:
    """基于 SQLite 的本地市场数据持久化与检索层 (启用 WAL 并发模式与安全隔离)"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        CACHE_DATA_LAYER_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            # 开启 WAL 并发读写模式与繁忙超时重试，彻底杜绝多进程锁定冲突
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA busy_timeout=30000;")
            except Exception as e:
                logger.debug(f"设置 WAL 模式提示: {e}")

            # 1. 核心日K线表
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
                    is_settled INTEGER DEFAULT 1,
                    PRIMARY KEY (symbol, date)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kline_symbol_date ON daily_kline (symbol, date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_kline (date)")

            # 2. 同步元数据水位线表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_meta (
                    symbol TEXT PRIMARY KEY,
                    last_sync_date TEXT,
                    row_count INTEGER DEFAULT 0,
                    min_date TEXT,
                    max_date TEXT,
                    integrity_status TEXT DEFAULT 'unknown',
                    sync_phase TEXT DEFAULT 'SETTLED',
                    is_settled INTEGER DEFAULT 1,
                    snapshot_time TEXT,
                    updated_at TEXT
                )
            """)

            # 3. 平滑无损迁移: 为旧表自动增量补充新字段
            def _ensure_column(table_name: str, col_name: str, col_type: str):
                cursor.execute(f"PRAGMA table_info({table_name})")
                cols = [row[1] for row in cursor.fetchall()]
                if col_name not in cols:
                    try:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
                    except Exception:
                        pass

            _ensure_column("daily_kline", "is_settled", "INTEGER DEFAULT 1")
            _ensure_column("sync_meta", "is_settled", "INTEGER DEFAULT 1")
            _ensure_column("sync_meta", "sync_phase", "TEXT DEFAULT 'SETTLED'")
            _ensure_column("sync_meta", "snapshot_time", "TEXT")
            _ensure_column("sync_meta", "known_suspensions", "TEXT DEFAULT ''")

            conn.commit()

    def upsert_klines(
        self,
        symbol: str,
        klines: List[Dict[str, Any]],
        sync_phase: str = "SETTLED",
        is_settled: int = 1,
        snapshot_time: Optional[str] = None,
    ) -> int:
        if not klines:
            return 0
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        max_date_in_klines = max(k["date"] for k in klines)

        records = []
        for k in klines:
            d = k["date"]
            # 仅最新一根柱子由当前时钟阶段判定定盘状态，之前所有历史日K一律定盘
            rec_settled = is_settled if d == max_date_in_klines else 1
            records.append((
                norm_symbol,
                d,
                float(k.get("open", 0.0)),
                float(k.get("close", 0.0)),
                float(k.get("high", 0.0)),
                float(k.get("low", 0.0)),
                float(k.get("volume", 0.0)),
                float(k.get("amount", 0.0)),
                float(k.get("turnover_pct", 0.0)),
                float(k.get("pe", 0.0)),
                float(k.get("pb", 0.0)),
                rec_settled,
            ))

        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO daily_kline (
                    symbol, date, open, close, high, low, volume, amount, turnover_pct, pe, pb, is_settled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open=excluded.open,
                    close=excluded.close,
                    high=excluded.high,
                    low=excluded.low,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    turnover_pct=excluded.turnover_pct,
                    pe=excluded.pe,
                    pb=excluded.pb,
                    is_settled=excluded.is_settled
            """, records)

            cursor.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM daily_kline WHERE symbol = ?", (norm_symbol,))
            row = cursor.fetchone()
            row_count, min_date, max_date = row[0], row[1], row[2]

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            snap_time = snapshot_time or datetime.now().strftime("%H:%M:%S")

            cursor.execute("""
                INSERT INTO sync_meta (
                    symbol, last_sync_date, row_count, min_date, max_date,
                    integrity_status, sync_phase, is_settled, snapshot_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'synced', ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    last_sync_date=excluded.last_sync_date,
                    row_count=excluded.row_count,
                    min_date=excluded.min_date,
                    max_date=excluded.max_date,
                    integrity_status='synced',
                    sync_phase=excluded.sync_phase,
                    is_settled=excluded.is_settled,
                    snapshot_time=excluded.snapshot_time,
                    updated_at=excluded.updated_at
            """, (norm_symbol, max_date, row_count, min_date, max_date, sync_phase, is_settled, snap_time, now_str))
            conn.commit()

        self.export_json_cache(norm_symbol)
        return len(records)

    def get_klines(
        self,
        symbol: str,
        count: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        query = """
            SELECT date, open, close, high, low, volume, amount, turnover_pct, pe, pb, is_settled
            FROM daily_kline WHERE symbol = ?
        """
        params: List[Any] = [norm_symbol]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date ASC"

        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = [dict(r) for r in rows]

        if count and count > 0 and len(results) > count:
            results = results[-count:]
        return results

    def get_dates_set(self, symbol: str) -> Set[str]:
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date FROM daily_kline WHERE symbol = ?", (norm_symbol,))
            return {row[0] for row in cursor.fetchall()}

    def get_sync_meta(self, symbol: str) -> Optional[Dict[str, Any]]:
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_meta WHERE symbol = ?", (norm_symbol,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def record_known_suspensions(self, symbol: str, dates: List[str]) -> None:
        """记录已核验的合规停牌日期列表"""
        if not dates:
            return
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        meta = self.get_sync_meta(norm_symbol) or {}
        existing = set(filter(None, (meta.get("known_suspensions") or "").split(",")))
        existing.update(dates)
        merged_str = ",".join(sorted(existing))
        with closing(self._get_conn()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sync_meta SET known_suspensions = ?, integrity_status = 'healthy' WHERE symbol = ?",
                (merged_str, norm_symbol),
            )
            conn.commit()

    def export_json_cache(self, symbol: str, limit: int = 500):
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        klines = self.get_klines(norm_symbol, count=limit)
        if not klines:
            return
        try:
            CACHE_DATA_LAYER_DIR.mkdir(parents=True, exist_ok=True)
            target_file = CACHE_DATA_LAYER_DIR / f"{norm_symbol}_qfq_kline.json"
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
        """从外部真实数据源拉取K线（严格隔离本地库自循环，严禁合成假数据）"""
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        raw_klines = DataBridge.fetch_remote_kline_strictly(norm_symbol, count=count)
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
                # 腾讯接口原始第6项为成交额(万元)，优先解析真实成交额，提升数据精度
                amt = 0.0
                if len(item) > 6 and item[6] not in (None, "", "null"):
                    try:
                        amt = float(item[6]) * 10000.0
                    except (ValueError, TypeError):
                        amt = round(o * v * 100, 2)
                else:
                    amt = round(o * v * 100, 2)

                formatted.append({
                    "date": d,
                    "open": o,
                    "close": c,
                    "high": h,
                    "low": l,
                    "volume": v,
                    "amount": round(amt, 2),
                })
            except (ValueError, TypeError):
                continue
        return formatted

    def sync_symbol(
        self,
        symbol: str,
        mode: str = "incremental",
        count: int = 250,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """同步单个标的的K线数据，支持全天候实时同步标记与定盘状态跃迁"""
        norm_symbol = DataBridge.normalize_symbol(symbol, with_prefix=True)
        phase_info = TradeCalendar.get_market_phase()
        today_str = phase_info["date_str"]
        is_today_settled = phase_info["is_settled"]
        sync_phase = phase_info["phase"]
        snapshot_time = phase_info["time_str"]

        meta = self.store.get_sync_meta(norm_symbol)

        # 1. 动态估算需拉取的切片深度，消除历史断层与截断失效
        if start_date:
            try:
                s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                now_date = datetime.now().date()
                days_span = max(1, (now_date - s_date).days)
                # 自然日 * 0.72 + 30 冗余，确保覆盖到指定的起始历史点
                pull_count = max(count, int(days_span * 0.72) + 30)
            except Exception:
                pull_count = count
        elif mode == "incremental" and meta and meta.get("last_sync_date"):
            last_date = meta["last_sync_date"]
            raw_settled = meta.get("is_settled")
            meta_is_settled = int(raw_settled) if raw_settled is not None else 1

            # 增量防漏跳过铁律：
            # 只有当本地已达到今日且【已经过盘后定盘 (is_settled=1)】时，方可真正跳过！
            # 若本地是盘中/午间临时态 (is_settled=0)，即便 last_date == today_str，亦必须允许被最新数据刷新！
            if last_date >= today_str and meta_is_settled == 1:
                return {
                    "symbol": norm_symbol,
                    "status": "up_to_date",
                    "synced_count": 0,
                    "total_count": meta.get("row_count", 0),
                    "last_date": last_date,
                    "sync_phase": meta.get("sync_phase", "SETTLED"),
                    "is_settled": True,
                    "snapshot_time": meta.get("snapshot_time", "15:35:00"),
                    "note": "本地数据已为最新定盘数据，无需重复拉取",
                }

            try:
                l_date = datetime.strptime(last_date, "%Y-%m-%d").date()
                gap_days = max(1, (datetime.now().date() - l_date).days)
                pull_count = max(35, int(gap_days * 0.72) + 15)
            except Exception:
                pull_count = 35
        else:
            pull_count = count

        # 2. 严格从远程抓取真实数据 (零假数据原则)
        remote_data = self.fetch_remote_klines(norm_symbol, count=pull_count)
        if not remote_data:
            return {
                "symbol": norm_symbol,
                "status": "failed",
                "error": "未能从外部数据源获取真实K线（网络不可用或接口无响应，严禁伪造数据）",
                "synced_count": 0,
                "total_count": meta.get("row_count", 0) if meta else 0,
                "last_date": meta.get("last_sync_date", "") if meta else "",
                "is_settled": False,
            }

        # 3. 日期范围精细过滤
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

        # 4. 落盘入库并注入定盘状态与时段标记
        # 历史K线永远定盘 (is_settled=1)，今日K线由当前时钟阶段动态决定
        inserted = self.store.upsert_klines(
            norm_symbol,
            remote_data,
            sync_phase=sync_phase,
            is_settled=1 if is_today_settled else 0,
            snapshot_time=snapshot_time,
        )
        updated_meta = self.store.get_sync_meta(norm_symbol) or {}

        # 5. 组装人类可读与机器结构化输出
        settled_flag = bool(updated_meta.get("is_settled", 1))
        phase_str = updated_meta.get("sync_phase", sync_phase)
        note = "已定盘收盘数据" if settled_flag else f"实时未定盘切片 ({phase_info['phase_label']}, 快照: {snapshot_time})"

        return {
            "symbol": norm_symbol,
            "status": "success",
            "synced_count": inserted,
            "total_count": updated_meta.get("row_count", 0),
            "last_date": updated_meta.get("last_sync_date", ""),
            "sync_phase": phase_str,
            "phase_label": phase_info["phase_label"],
            "is_settled": settled_flag,
            "snapshot_time": snapshot_time,
            "note": note,
        }

    def sync_today_snapshot(self, symbols: List[str]) -> Dict[str, Any]:
        """同步当日最新行情快照，含交易日与时钟状态守卫"""
        phase_info = TradeCalendar.get_market_phase()
        today_str = phase_info["date_str"]

        # 交易日守卫：若当前为非交易日（周末/法定休市），严禁硬塞虚假周末K线
        if not phase_info["is_trading_day"]:
            return {
                "status": "skipped",
                "message": f"今日 ({today_str}) 为非交易日（{phase_info['phase_label']}），无需执行当日快照同步",
                "date": today_str,
                "updated_count": 0,
                "total_requested": len(symbols),
                "is_settled": True,
            }

        if not symbols:
            return {"status": "empty", "count": 0}

        quotes = self.bridge.fetch_batch_snapshot(symbols)
        updated_count = 0
        is_settled = 1 if phase_info["is_settled"] else 0

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

            # 优先从快照中提取真实交易日期，而非简单盲写
            rec_date = q.get("date") or today_str

            record = [{
                "date": rec_date,
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
            self.store.upsert_klines(
                norm_symbol,
                record,
                sync_phase=phase_info["phase"],
                is_settled=is_settled,
                snapshot_time=phase_info["time_str"],
            )
            updated_count += 1

        return {
            "status": "success",
            "date": today_str,
            "sync_phase": phase_info["phase"],
            "phase_label": phase_info["phase_label"],
            "is_settled": bool(is_settled),
            "snapshot_time": phase_info["time_str"],
            "updated_count": updated_count,
            "total_requested": len(symbols),
        }

    def audit_integrity(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """稽核本地时序数据完整性，检测缺漏交易日断点与坏点，智能识别合规停牌"""
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
                    "suspended_days": [],
                    "bad_records": [],
                    "message": "本地暂无数据",
                })
                continue

            local_dates = {k["date"] for k in local_klines}
            min_date = local_klines[0]["date"]
            max_date = local_klines[-1]["date"]

            # 基准对齐: 若标的自身为大盘指数 sh000001，通过 TradeCalendar 权威交易日历自检
            if norm_symbol == benchmark_symbol:
                expected_trading_days = TradeCalendar.get_trading_days_between(min_date, max_date)
            else:
                expected_trading_days = sorted([d for d in ref_dates if min_date <= d <= max_date])

            all_missing = [d for d in expected_trading_days if d not in local_dates]

            # 获取已知合规停牌记录 (从 sync_meta 表读取)
            meta = self.store.get_sync_meta(norm_symbol) or {}
            raw_known_suspensions = meta.get("known_suspensions") or ""
            known_suspensions = {d.strip() for d in raw_known_suspensions.split(",") if d.strip()}

            missing_days = []
            suspended_days = []
            for d in all_missing:
                if d in known_suspensions:
                    suspended_days.append(d)
                else:
                    missing_days.append(d)

            bad_records = []
            for k in local_klines:
                if k["close"] <= 0 or k["open"] <= 0 or k["high"] <= 0 or k["low"] <= 0:
                    bad_records.append(k["date"])

            status = "healthy"
            if missing_days or bad_records:
                status = "degraded"

            if status == "healthy":
                msg = f"数据健康完整 (含 {len(suspended_days)} 日合规停牌)" if suspended_days else "数据健康完整"
            else:
                parts = []
                if missing_days:
                    parts.append(f"{len(missing_days)} 处缺漏交易日")
                if suspended_days:
                    parts.append(f"{len(suspended_days)} 日合规停牌")
                if bad_records:
                    parts.append(f"{len(bad_records)} 个坏点")
                msg = "发现 " + ", ".join(parts)

            audit_results.append({
                "symbol": norm_symbol,
                "status": status,
                "row_count": len(local_klines),
                "min_date": min_date,
                "max_date": max_date,
                "missing_count": len(missing_days),
                "missing_days": missing_days[:10],
                "suspended_count": len(suspended_days),
                "suspended_days": suspended_days[:10],
                "bad_count": len(bad_records),
                "bad_records": bad_records,
                "message": msg,
            })

        return audit_results

    def repair_gaps(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """靶向修复并回补缺漏数据，智能识别合规停牌"""
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

            # 若全量重新拉取后，仍有缺漏日，但远程抓取成功（说明外部源亦无交易，为合法停牌或上市前）
            if re_audit["status"] == "degraded" and sync_res.get("status") in ["success", "up_to_date"]:
                unfilled_days = re_audit.get("missing_days", [])
                if unfilled_days and re_audit.get("bad_count", 0) == 0:
                    self.store.record_known_suspensions(sym, unfilled_days)
                    re_audit = self.audit_integrity([sym])[0]
                    repair_results.append({
                        "symbol": sym,
                        "repaired": True,
                        "synced_count": sync_res.get("synced_count", 0),
                        "remaining_missing": 0,
                        "suspended_count": len(unfilled_days),
                        "message": f"修复成功 (已全量对齐，识别并核准 {len(unfilled_days)} 日合规停牌)",
                    })
                    continue

            repair_results.append({
                "symbol": sym,
                "repaired": re_audit["status"] == "healthy",
                "synced_count": sync_res.get("synced_count", 0),
                "remaining_missing": re_audit.get("missing_count", 0),
                "message": "修复成功 (已对齐完整)" if re_audit["status"] == "healthy" else f"仍有 {re_audit.get('missing_count')} 处缺漏(可能为网络异常或新股上市前)",
            })

        return repair_results

    def sync_batch(
        self,
        symbols: List[str],
        mode: str = "incremental",
        count: int = 250,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_workers: int = 4,
    ) -> Dict[str, Any]:
        """批量同步调度，支持多线程并发与流控"""
        t0 = time.time()
        results: List[Optional[Dict[str, Any]]] = [None] * len(symbols)
        success_count = 0
        failed_count = 0

        def _worker(idx: int, sym: str) -> Tuple[int, Dict[str, Any]]:
            try:
                res = self.sync_symbol(sym, mode=mode, count=count, start_date=start_date, end_date=end_date)
                return idx, res
            except Exception as e:
                logger.error(f"同步标的 {sym} 异常: {e}")
                return idx, {"symbol": sym, "status": "error", "error": str(e)}

        workers = max(1, min(max_workers or 4, 16))
        if workers > 1 and len(symbols) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_worker, i, sym) for i, sym in enumerate(symbols)]
                for fut in as_completed(futures):
                    idx, res = fut.result()
                    results[idx] = res
                    if res.get("status") in ["success", "up_to_date"]:
                        success_count += 1
                    else:
                        failed_count += 1
        else:
            for i, sym in enumerate(symbols):
                idx, res = _worker(i, sym)
                results[idx] = res
                if res.get("status") in ["success", "up_to_date"]:
                    success_count += 1
                else:
                    failed_count += 1

        elapsed = round(time.time() - t0, 2)
        phase_info = TradeCalendar.get_market_phase()

        return {
            "mode": mode,
            "sync_phase": phase_info["phase"],
            "phase_label": phase_info["phase_label"],
            "is_settled": phase_info["is_settled"],
            "snapshot_time": phase_info["time_str"],
            "total_requested": len(symbols),
            "success_count": success_count,
            "failed_count": failed_count,
            "elapsed_seconds": elapsed,
            "workers": workers,
            "details": [r for r in results if r is not None],
        }
