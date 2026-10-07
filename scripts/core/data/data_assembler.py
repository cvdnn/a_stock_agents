# -*- coding: utf-8 -*-
"""DataAssembler（选股规范 §11.3）——最小可用装配层。

一期范围（评估报告 `assessment_smart-stock-selection_20261007.md` 处置建议 2 / P0-1 + P0-2）：

- `finalized_local` **单模式**：从本地 SQLite 定盘日线批量装配 `post_close` 输入；
  `intraday_capture` 仅实现"归档切片 → `minute_points`"这一条适配器通路，不含实时补数；
- `date <= as_of` 硬截断 + 一致性只读事务（`PRAGMA query_only`），禁止读到 `as_of` 之后的数据；
- 每次运行生成**不可变快照清单**（§11.7）并落盘本次实际使用的标准化输入切片与内容哈希；
- 缺失字段一律以 `field_status` 标注并**不写入记录**，禁止用 0 / 默认值填充（§11.6）；
- 消费侧水位门禁：`check_post_close_ready` 未达标即返回 `WAITING_DATA`，不产出候选（§11.4）。

装配层不含任何规则语义，也不得临时补数（§11.3）；规则层只消费本层输出的稳定输入。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import date as _date
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:  # Windows 缺少 tzdata 时回退；中国无夏令时，UTC+8 与 Asia/Shanghai 等价
    from zoneinfo import ZoneInfo

    _SHANGHAI_TZ: Any = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    _SHANGHAI_TZ = timezone(timedelta(hours=8))

try:
    from core.config import get_logger
except ImportError:  # pragma: no cover - 兼容 scripts/core 直接入 sys.path 的场景
    import logging

    get_logger = logging.getLogger

try:
    from scripts.core.workspace import OUTPUT_DIR
except ImportError:  # pragma: no cover
    from core.workspace import OUTPUT_DIR

from core.data.data_layer import normalize_minute_timestamp
from core.data.dataset_sync import POST_CLOSE_WATERMARK_KEYS, check_post_close_ready
from core.data.intraday_archiver import INTRADAY_CACHE_ROOT
from core.data.sync_engine import DB_PATH, TradeCalendar

logger = get_logger("core.data.data_assembler")

# ------------------------------------------------------------------ 常量与词汇表
ACCESS_FINALIZED_LOCAL = "finalized_local"
ACCESS_INTRADAY_CAPTURE = "intraday_capture"

STATUS_OK = "OK"
STATUS_WAITING_DATA = "WAITING_DATA"
STATUS_SOURCE_ERROR = "SOURCE_ERROR"

GATE_PASS = "PASS"
GATE_OBSERVATION = "OBSERVATION"
GATE_WAITING_DATA = STATUS_WAITING_DATA

#: §11.6 字段状态值域（不得用 0 统一代替缺失值）
FIELD_PRESENT = "present"
FIELD_NOT_READY = "not_ready"
FIELD_MISSING = "missing"
FIELD_STALE = "stale"
FIELD_UNSUPPORTED = "unsupported"
FIELD_SOURCE_ERROR = "source_error"

#: 单条 SQL 的 IN 变量上限保护（批量读取同类数据，避免逐股重复查询）
_READ_CHUNK = 400

DEFAULT_DAILY_LOOKBACK = 70
#: 流通市值快照允许的最大业务时间滞后（自然日）；超出仅标 stale，不伪造新鲜度
DEFAULT_VALUATION_MAX_AGE_DAYS = 7
#: 收盘批次完成时刻（§11.4：到达时间本身不表示数据已定盘，此处仅作历史 as_of 的业务时间）
_POST_CLOSE_BATCH_TIME = dt_time(15, 35)

ALGORITHM_VERSION = "data_assembler@v1"

#: 覆盖率硬门禁默认阈值（D-12：正式信号默认 100%，不达标整场降级）。
COVERAGE_THRESHOLD_DEFAULT = 1.0
#: 候选池覆盖率的必需字段（主口径 R-03：有值标的数 ÷ 候选池标的数）。
COVERAGE_REQUIRED_FIELDS = ("daily_kline",)

#: 判定 `ts` 是否显式携带日期（用于剔除"明确属于另一交易日"的归档行）
_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def content_hash(value: Any) -> str:
    """内容哈希：对规范化 JSON 取 sha256，前缀显式声明算法。"""
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def layer_denominator(
    scope: str,
    input_universe: Sequence[str],
    upstream_codes: Optional[Sequence[str]] = None,
) -> List[str]:
    """分层覆盖率分母（A-05）：

    - `universe_gate` 层分母 = **该层输入 Universe**（P3 目标股票池）；
    - `candidate_filter` 层分母 = **上层输出池**（无上游输出时退化为本层输入 Universe）。
    """
    if str(scope) == "universe_gate":
        return sorted({str(item) for item in input_universe if str(item)})
    if upstream_codes is not None:
        return sorted({str(item) for item in upstream_codes if str(item)})
    return sorted({str(item) for item in input_universe if str(item)})


def build_universe_watermark(
    records: Sequence[Mapping[str, Any]],
    universe: Sequence[str],
    *,
    required_fields: Sequence[str] = COVERAGE_REQUIRED_FIELDS,
    scope: str = "candidate_pool",
    coverage_threshold: float = COVERAGE_THRESHOLD_DEFAULT,
    mv_field: Optional[str] = "circulating_market_cap",
) -> Dict[str, Any]:
    """按 R-03/A-05 计算分层 `UniverseWatermark` 与覆盖率门禁结论。

    - 主口径 = 有值标的数 / **候选池标的数**（硬门禁，默认 100%）；
    - 同时记录流通市值加权覆盖率作**参考观测**，不参与门禁判定（R-03）；
    - 缺失标的逐字段留痕，不得用 0 或默认值填充（§11.6）。
    """
    denominator = sorted({str(item) for item in universe if str(item)})
    by_code = {str(rec.get("code") or ""): rec for rec in records}
    missing_by_field: Dict[str, List[str]] = {str(field): [] for field in required_fields}
    healthy = 0
    for code in denominator:
        record = by_code.get(code)
        status = dict(record.get("field_status") or {}) if record else {}
        ok = record is not None
        for field in required_fields:
            if status.get(field) != FIELD_PRESENT:
                missing_by_field[str(field)].append(code)
                ok = False
        if ok:
            healthy += 1
    expected = len(denominator)
    coverage = round(healthy / expected, 6) if expected else 0.0

    mv_weighted: Optional[float] = None
    if mv_field:
        total_mv = 0.0
        covered_mv = 0.0
        for code in denominator:
            record = by_code.get(code) or {}
            value = record.get(mv_field)
            if value is None:
                continue
            total_mv += float(value)
            if (record.get("field_status") or {}).get(mv_field) == FIELD_PRESENT:
                covered_mv += float(value)
        mv_weighted = round(covered_mv / total_mv, 6) if total_mv else None

    missing_codes = sorted({code for codes in missing_by_field.values() for code in codes})
    passed = bool(expected) and coverage >= float(coverage_threshold)
    return {
        "scope": str(scope),
        "expected": expected,
        "healthy": healthy,
        "coverage": coverage,
        "coverage_threshold": float(coverage_threshold),
        "passed": passed,
        "missing_codes": missing_codes,
        "missing_by_field": {key: sorted(value) for key, value in missing_by_field.items()},
        "coverage_mv_weighted": mv_weighted,
        "mv_weighted_role": "reference_only",
        "rule": "R-03/A-05：主口径=有值标的数÷候选池标的数（硬门禁）；mv 加权仅参考观测",
    }


def _chunks(items: Sequence[str], size: int = _READ_CHUNK) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _shanghai_now() -> datetime:
    return datetime.now(_SHANGHAI_TZ)


def _as_of_timestamp(as_of_date: str, now: datetime) -> str:
    """业务时间：目标日即今天用当前时钟，历史日按收盘批次口径记 15:35。"""
    if as_of_date == now.astimezone(_SHANGHAI_TZ).date().isoformat():
        moment = now
    else:
        moment = datetime.combine(_date.fromisoformat(as_of_date), _POST_CLOSE_BATCH_TIME, tzinfo=_SHANGHAI_TZ)
    return moment.isoformat(timespec="seconds")


class DataAssembler:
    """选股装配层：把物理表/归档切片转换为规则可消费的稳定输入。"""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        snapshot_root: Optional[Path] = None,
        intraday_root: Optional[Path] = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        # §13.10 落盘规范：默认落在 output/cache/selection-models/ 三桶范围内
        self.snapshot_root = (
            Path(snapshot_root) if snapshot_root
            else OUTPUT_DIR / "cache" / "selection-models" / "snapshots"
        )
        self.intraday_root = Path(intraday_root) if intraday_root else INTRADAY_CACHE_ROOT

    # ---------------------------------------------------------------- 通用
    def resolve_universe(
        self,
        codes: Optional[Iterable[str]] = None,
        all_market: bool = False,
    ) -> List[str]:
        """目标 Universe：显式代码 > 全市场（本地 daily_kline 实际标的）> 已登记标的 (P0–P2)。"""
        from core.data.data_bridge import DataBridge

        if codes:
            return sorted({DataBridge.normalize_symbol(str(c), with_prefix=True) for c in codes if str(c).strip()})
        if all_market:
            with closing(self._read_conn()) as conn:
                rows = conn.execute("SELECT DISTINCT symbol FROM daily_kline ORDER BY symbol").fetchall()
            return [str(row["symbol"]) for row in rows]
        from core.data.dataset_sync import _resolve_registered

        return _resolve_registered()

    def _read_conn(self) -> sqlite3.Connection:
        """一致性只读事务连接：`query_only` 阻断写入，事务内多次查询共享同一读快照。"""
        if not self.db_path.is_file():
            raise sqlite3.OperationalError(f"本地数据库不存在: {self.db_path}")
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None  # 由调用方显式 BEGIN / COMMIT，避免隐式事务破坏只读快照
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    # ---------------------------------------------------------------- §11.4 收盘阶段
    def assemble_daily(
        self,
        codes: Sequence[str],
        as_of: Optional[str] = None,
        lookback: int = DEFAULT_DAILY_LOOKBACK,
        allow_degraded: bool = False,
        algorithm_version: str = ALGORITHM_VERSION,
    ) -> Dict[str, Any]:
        """`finalized_local` 批量装配 post_close 输入（含水位门禁与快照清单落盘）。"""
        gate = self.evaluate_data_gate(as_of=as_of, allow_degraded=allow_degraded)
        if gate["state"] == GATE_WAITING_DATA:
            return {"status": STATUS_WAITING_DATA, "gate": gate, "records": [], "manifest": None}

        as_of_date = gate["trade_date"]
        now = _shanghai_now()
        read_at = now.isoformat(timespec="seconds")
        universe = sorted({str(c) for c in codes if str(c)})
        if not universe:
            return {"status": STATUS_WAITING_DATA, "gate": gate, "records": [], "manifest": None,
                    "reason_code": "UNIVERSE_EMPTY"}

        try:
            with closing(self._read_conn()) as conn:
                conn.execute("BEGIN")
                window_start = self._window_floor(conn, as_of_date, lookback)
                klines = self._read_klines(conn, universe, as_of_date, window_start, lookback)
                names = self._read_names(conn, universe)
                valuation = self._read_valuation(conn, universe, as_of_date)
                flow = self._read_capital_flow(conn, universe, as_of_date)
                sync_meta = self._read_sync_meta(conn, universe)
                conn.execute("COMMIT")
        except sqlite3.Error as exc:
            logger.warning("DataAssembler 只读装配失败: %s", exc)
            return {"status": STATUS_SOURCE_ERROR, "gate": gate, "records": [], "manifest": None,
                    "reason_code": "LOCAL_STORE_UNREADABLE", "error": str(exc)}

        records: List[Dict[str, Any]] = []
        missing_symbols: List[str] = []
        for symbol in universe:
            bars = klines.get(symbol) or []
            field_status: Dict[str, str] = {}
            business_time: Dict[str, str] = {}
            record: Dict[str, Any] = {"code": symbol}
            if bars:
                record["closes"] = [float(b["close"]) for b in bars]
                record["volumes"] = [float(b["volume"]) for b in bars]
                record["dates"] = [str(b["date"]) for b in bars]
                if len(record["closes"]) >= 2 and record["closes"][-2]:
                    record["change_pct"] = round(
                        (record["closes"][-1] / record["closes"][-2] - 1.0) * 100, 4
                    )
                    field_status["change_pct"] = FIELD_PRESENT
                else:
                    field_status["change_pct"] = FIELD_NOT_READY
                last_bar_date = str(bars[-1]["date"])
                field_status["daily_kline"] = (
                    FIELD_PRESENT if last_bar_date == as_of_date else FIELD_STALE
                )
                business_time["daily_kline"] = last_bar_date
            else:
                field_status["daily_kline"] = FIELD_MISSING
                missing_symbols.append(symbol)

            name = names.get(symbol)
            if name:
                record["name"] = name
                field_status["security_master"] = FIELD_PRESENT
            else:
                field_status["security_master"] = FIELD_MISSING

            cap_row = valuation.get(symbol)
            if cap_row and cap_row.get("float_market_cap") is not None:
                record["circulating_market_cap"] = float(cap_row["float_market_cap"])
                business_time["circulating_market_cap"] = str(cap_row["date"])
                # W-02/W-10：流通市值是 post_close 硬门槛字段，快照过期即标 stale 供披露与门禁复核
                field_status["circulating_market_cap"] = (
                    FIELD_STALE
                    if self._exceeds_age(str(cap_row["date"]), as_of_date, DEFAULT_VALUATION_MAX_AGE_DAYS)
                    else FIELD_PRESENT
                )
            else:
                # 无值即缺失；不得用 0 参与比较（§11.6 与 W-10 同口径）
                field_status["circulating_market_cap"] = FIELD_MISSING

            flow_row = flow.get(symbol)
            if flow_row is None:
                field_status["main_net_inflow"] = FIELD_MISSING
            elif str(flow_row.get("flow_source")) != "eastmoney_exact":
                # 裁定 W-07：代理档不得参与正式规则，标记 unsupported 而非把代理值传给规则
                field_status["main_net_inflow"] = FIELD_UNSUPPORTED
            else:
                record["main_net_inflow"] = flow_row.get("main_net_inflow")
                field_status["main_net_inflow"] = (
                    FIELD_PRESENT if record["main_net_inflow"] is not None else FIELD_MISSING
                )

            record["field_status"] = field_status
            if business_time:
                record["field_business_time"] = business_time
            records.append(record)

        # §5.5/§11.4 口径披露：水位分母是同步批次声明的 Universe，与本次装配 Universe
        # 不一致时必须显式记录缺口，绝不把"批次达标"当成"目标 Universe 达标"。
        coverage_gap = [
            key for key, wm in (gate.get("datasets") or {}).items()
            if wm and int(wm.get("universe_total") or 0) < len(universe)
        ]
        if coverage_gap:
            gate["universe_coverage_gap"] = coverage_gap

        manifest = self._build_local_manifest(
            universe=universe,
            records=records,
            as_of_date=as_of_date,
            as_of=_as_of_timestamp(as_of_date, now),
            read_at=read_at,
            lookback=lookback,
            window_start=window_start,
            gate=gate,
            sync_meta=sync_meta,
            missing_symbols=missing_symbols,
            algorithm_version=algorithm_version,
        )
        manifest["snapshot_path"] = str(self._snapshot_dir(manifest))
        self.stamp_records(records, manifest)
        self.persist_snapshot(manifest, records)
        return {
            "status": STATUS_OK,
            "gate": gate,
            "coverage_gate": manifest["coverage_gate"],
            "records": records,
            "manifest": manifest,
        }

    def _snapshot_dir(self, manifest: Dict[str, Any]) -> Path:
        return self.snapshot_root / str(manifest["data_snapshot_id"])

    @staticmethod
    def stamp_records(records: Sequence[Dict[str, Any]], manifest: Dict[str, Any]) -> None:
        """§11.4/§11.5：记录级 `data_meta` 携带快照标识、口径、水位与清单哈希（就地写入）。

        清单哈希先于 stamp 计算，故 `data_meta` 不反过来影响 `snapshot_manifest_hash`。
        """
        hashes = {str(item["code"]): item["input_hash"] for item in manifest.get("input_slices", [])}
        for rec in records:
            code = str(rec.get("code") or "")
            meta = rec.setdefault("data_meta", {})
            payload = {
                "data_snapshot_id": manifest["data_snapshot_id"],
                "access_mode": manifest["access_mode"],
                "as_of": manifest["as_of"],
                "read_at": manifest.get("read_at"),
                "captured_at": manifest.get("captured_at"),
                "capture_id": manifest.get("capture_id"),
                "provider_route": manifest.get("provider_route"),
                "physical_tables": manifest.get("physical_tables"),
                "adjustment": manifest.get("adjustment"),
                "units": manifest.get("units"),
                "integrity_status": manifest.get("integrity_status"),
                "universe_watermark": manifest.get("universe_watermark"),
                "calendar_version": manifest.get("calendar_version"),
                "indicator_engine_version": manifest.get("indicator_engine_version"),
                "normalization_schema_version": manifest.get("normalization_schema_version"),
                "snapshot_manifest_hash": manifest["snapshot_manifest_hash"],
                "snapshot_path": manifest.get("snapshot_path"),
            }
            # 记录级既有值优先：分钟捕获的 captured_at 是该标的真实捕获时刻，不得被清单值覆盖
            for key, value in payload.items():
                meta.setdefault(key, value)
            if code in hashes:
                meta.setdefault("input_hash", hashes[code])

    @staticmethod
    def _exceeds_age(business_date: str, as_of_date: str, max_age_days: int) -> bool:
        try:
            return (_date.fromisoformat(as_of_date) - _date.fromisoformat(business_date)).days > max_age_days
        except ValueError:
            return True

    @staticmethod
    def _window_floor(conn: sqlite3.Connection, as_of_date: str, lookback: int) -> Optional[str]:
        """参考交易日序列下界：本地库中 <= as_of 的最后 `lookback` 个交易日的首位。"""
        row = conn.execute(
            "SELECT date FROM daily_kline WHERE date <= ? GROUP BY date ORDER BY date DESC LIMIT ?",
            (as_of_date, max(int(lookback), 1)),
        ).fetchall()
        return str(row[-1]["date"]) if row else None

    @staticmethod
    def _read_klines(
        conn: sqlite3.Connection,
        universe: Sequence[str],
        as_of_date: str,
        window_start: Optional[str],
        lookback: int,
    ) -> Dict[str, List[sqlite3.Row]]:
        """批量读取定盘日线（`date <= as_of` 截断 + `is_settled = 1`），按标的保序分组。"""
        out: Dict[str, List[sqlite3.Row]] = {}
        if window_start is None:
            return out
        for chunk in _chunks(list(universe)):
            marks = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT symbol, date, open, high, low, close, volume, amount FROM daily_kline"
                f" WHERE date BETWEEN ? AND ? AND COALESCE(is_settled, 1) = 1 AND symbol IN ({marks})"
                f" ORDER BY symbol, date",
                [window_start, as_of_date, *chunk],
            ).fetchall()
            for row in rows:
                out.setdefault(str(row["symbol"]), []).append(row)
        return {symbol: bars[-max(int(lookback), 1):] for symbol, bars in out.items()}

    @staticmethod
    def _read_names(conn: sqlite3.Connection, universe: Sequence[str]) -> Dict[str, str]:
        names: Dict[str, str] = {}
        for chunk in _chunks(list(universe)):
            marks = ",".join("?" * len(chunk))
            try:
                rows = conn.execute(
                    f"SELECT symbol, name FROM stock_basic WHERE symbol IN ({marks})", list(chunk)
                ).fetchall()
            except sqlite3.Error:
                return names
            for row in rows:
                names[str(row["symbol"])] = str(row["name"])
        return names

    @staticmethod
    def _read_valuation(
        conn: sqlite3.Connection, universe: Sequence[str], as_of_date: str
    ) -> Dict[str, Dict[str, Any]]:
        """每标的 `date <= as_of` 的最新一条流通市值快照（D7，入库单位元）。"""
        out: Dict[str, Dict[str, Any]] = {}
        for chunk in _chunks(list(universe)):
            marks = ",".join("?" * len(chunk))
            try:
                rows = conn.execute(
                    f"SELECT cs.symbol, cs.date, cs.float_market_cap, cs.total_market_cap, cs.source"
                    f" FROM capital_snapshot cs JOIN ("
                    f"   SELECT symbol, MAX(date) AS d FROM capital_snapshot WHERE date <= ? GROUP BY symbol"
                    f" ) latest ON latest.symbol = cs.symbol AND latest.d = cs.date"
                    f" WHERE cs.symbol IN ({marks})",
                    [as_of_date, *chunk],
                ).fetchall()
            except sqlite3.Error:
                return out
            for row in rows:
                out[str(row["symbol"])] = dict(row)
        return out

    @staticmethod
    def _read_capital_flow(
        conn: sqlite3.Connection, universe: Sequence[str], as_of_date: str
    ) -> Dict[str, Dict[str, Any]]:
        """资金流仅取归属交易日当批（跨日拼接会伪造新鲜度，故不做回退）。"""
        out: Dict[str, Dict[str, Any]] = {}
        for chunk in _chunks(list(universe)):
            marks = ",".join("?" * len(chunk))
            try:
                rows = conn.execute(
                    f"SELECT symbol, date, main_net_inflow, flow_source FROM capital_flow_daily"
                    f" WHERE date = ? AND symbol IN ({marks})",
                    [as_of_date, *chunk],
                ).fetchall()
            except sqlite3.Error:
                return out
            for row in rows:
                out[str(row["symbol"])] = dict(row)
        return out

    @staticmethod
    def _read_sync_meta(conn: sqlite3.Connection, universe: Sequence[str]) -> Dict[str, Any]:
        """§11.7：清单须记录 sync_meta 的同步日期、范围、行数、完整性与更新时间。"""
        summary: Dict[str, Any] = {
            "symbols_with_meta": 0,
            "integrity_status_counts": {},
            "last_sync_date_min": None,
            "last_sync_date_max": None,
            "updated_at_max": None,
            "rows": 0,
        }
        for chunk in _chunks(list(universe)):
            marks = ",".join("?" * len(chunk))
            try:
                rows = conn.execute(
                    f"SELECT symbol, last_sync_date, row_count, min_date, max_date, integrity_status,"
                    f" updated_at FROM sync_meta WHERE symbol IN ({marks})",
                    list(chunk),
                ).fetchall()
            except sqlite3.Error:
                break
            for row in rows:
                summary["symbols_with_meta"] += 1
                summary["rows"] += int(row["row_count"] or 0)
                key = str(row["integrity_status"] or "unknown")
                summary["integrity_status_counts"][key] = summary["integrity_status_counts"].get(key, 0) + 1
                for col, field_name in (
                    ("last_sync_date", "last_sync_date_min"), ("last_sync_date", "last_sync_date_max"),
                    ("updated_at", "updated_at_max"),
                ):
                    value = row[col]
                    if value is None:
                        continue
                    current = summary[field_name]
                    if current is None or (field_name.endswith("_max") and value > current) or (
                        field_name.endswith("_min") and value < current
                    ):
                        summary[field_name] = str(value)
        return summary

    def _build_local_manifest(
        self,
        *,
        universe: Sequence[str],
        records: Sequence[Dict[str, Any]],
        as_of_date: str,
        as_of: str,
        read_at: str,
        lookback: int,
        window_start: Optional[str],
        gate: Dict[str, Any],
        sync_meta: Dict[str, Any],
        missing_symbols: Sequence[str],
        algorithm_version: str,
    ) -> Dict[str, Any]:
        slices = [
            {
                "code": rec["code"],
                "field_status": rec["field_status"],
                "field_business_time": rec.get("field_business_time", {}),
                "input_hash": content_hash(
                    {
                        "closes": rec.get("closes"),
                        "volumes": rec.get("volumes"),
                        "dates": rec.get("dates"),
                        "change_pct": rec.get("change_pct"),
                        "circulating_market_cap": rec.get("circulating_market_cap"),
                        "main_net_inflow": rec.get("main_net_inflow"),
                        "name": rec.get("name"),
                    }
                ),
            }
            for rec in records
        ]
        calendar_meta = TradeCalendar.local_calendar_version(self.db_path)
        # R-03/A-05：候选池覆盖率硬门禁（主口径=有值标的数÷候选池标的数；mv 加权仅参考观测）
        candidate_watermark = build_universe_watermark(
            records,
            universe,
            required_fields=COVERAGE_REQUIRED_FIELDS,
            scope="candidate_filter:post_close",
            coverage_threshold=COVERAGE_THRESHOLD_DEFAULT,
        )
        core = {
            "access_mode": ACCESS_FINALIZED_LOCAL,
            "as_of": as_of,
            "as_of_date": as_of_date,
            "query_params": {
                "lookback": lookback,
                "window_start": window_start,
                "window_end": as_of_date,
                "settled_only": True,
                "universe_size": len(universe),
            },
            "physical_tables": ["daily_kline", "sync_meta", "stock_basic", "capital_snapshot", "capital_flow_daily"],
            "adjustment": "qfq",
            "units": {"volume": "手(源侧原值)", "amount": "元", "circulating_market_cap": "元(W-09)"},
            "store_identity": {
                "db_file": str(self.db_path),
                "db_size_bytes": self.db_path.stat().st_size if self.db_path.is_file() else None,
                "db_mtime": (
                    datetime.fromtimestamp(self.db_path.stat().st_mtime, tz=_SHANGHAI_TZ).isoformat(timespec="seconds")
                    if self.db_path.is_file()
                    else None
                ),
            },
            "sync_meta": sync_meta,
            "integrity_status": gate["integrity_status"],
            "universe_watermark": gate["datasets"],
            "candidate_pool_watermark": candidate_watermark,
            "coverage_gate": {
                "passed": candidate_watermark["passed"],
                "coverage": candidate_watermark["coverage"],
                "threshold": candidate_watermark["coverage_threshold"],
                "scope": candidate_watermark["scope"],
                "degraded": not candidate_watermark["passed"],
                "rule": candidate_watermark["rule"],
            },
            "universe_coverage": {
                "requested": len(universe),
                "assembled": len(records),
                "missing_daily_kline": list(missing_symbols),
                "watermark_coverage_gap": list(gate.get("universe_coverage_gap", [])),
            },
            "calendar_version": calendar_meta["calendar_version"],
            "calendar_available": calendar_meta["calendar_available"],
            "indicator_engine_version": algorithm_version,
            "normalization_schema_version": 1,
            "read_at": read_at,
            "input_slices": slices,
        }
        # 内容寻址：清单哈希只覆盖"数据内容 + 查询口径"，排除读时刻与文件 mtime 等
        # 随运行漂移的字段，使同一份定盘数据重复装配得到同一 `data_snapshot_id`。
        volatile = ("read_at", "as_of", "store_identity")
        digest = content_hash({k: v for k, v in core.items() if k not in volatile})
        return {
            "data_snapshot_id": f"dss_{as_of_date.replace('-', '')}_local_{digest.split(':')[1][:12]}",
            "snapshot_manifest_hash": digest,
            "generated_at": read_at,
            **core,
        }

    def persist_snapshot(self, manifest: Dict[str, Any], records: Sequence[Dict[str, Any]]) -> Path:
        """§11.7：运行目录须保存本次实际使用的标准化输入切片，而不只保存数据库主键。"""
        target = self._snapshot_dir(manifest)
        target.mkdir(parents=True, exist_ok=True)
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with open(target / "records.jsonl", "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return target

    # ---------------------------------------------------------------- §11.4 水位门禁
    def evaluate_data_gate(
        self,
        as_of: Optional[str] = None,
        allow_degraded: bool = False,
        required_keys: Sequence[str] = POST_CLOSE_WATERMARK_KEYS,
    ) -> Dict[str, Any]:
        """把同步侧 §5.5 水位接到选股消费侧：未达标一律 `WAITING_DATA`，不产出候选。"""
        readiness = check_post_close_ready(
            trade_date=self._resolve_trade_date(as_of), db_path=self.db_path, required_keys=required_keys
        )
        degraded = bool(readiness["missing"] or readiness["not_finalized"])
        if degraded and not allow_degraded:
            state = GATE_WAITING_DATA
        elif degraded:
            state = GATE_OBSERVATION
        else:
            state = GATE_PASS
        return {
            "state": state,
            "trade_date": readiness["trade_date"],
            "required_keys": readiness["required_keys"],
            "missing": readiness["missing"],
            "not_finalized": readiness["not_finalized"],
            "datasets": readiness["datasets"],
            # 落库口径与现场审计口径分开表述：水位达标 != 现场 healthy 已稽核
            "integrity_status": "watermark_finalized" if state == GATE_PASS else "watermark_degraded",
            "rule": "selection-system-specification.md §11.4 / selection-system-plan.md 发布门禁",
        }

    @staticmethod
    def _resolve_trade_date(as_of: Optional[str]) -> Optional[str]:
        return str(as_of)[:10] if as_of else None

    # ---------------------------------------------------------------- §11.5 早盘捕获适配器
    def assemble_intraday(
        self,
        codes: Sequence[str],
        trade_date: Optional[str] = None,
        now: Optional[datetime] = None,
        gate: Optional[Dict[str, Any]] = None,
        algorithm_version: str = ALGORITHM_VERSION,
    ) -> Dict[str, Any]:
        """归档切片 → `minute_points` / `order_book` 适配器（时间戳归一化在本层完成）。

        - `minute_1m.jsonl` 的 `ts="YYYY-MM-DD HH:MM"` 经 `normalize_minute_timestamp` 归一为 Bar 起点 `HH:MM`；
        - 未收满 60 秒的进行中 Bar 标 `field_status = not_ready`，由规则层计入 `dropped_point_count`；
        - 主动买卖量仅在该分钟确有 `tick.jsonl` 分笔时给出（direction 为源侧推断 B/S，非真 L2）；
          无分笔覆盖的分钟**不填 0**，规则层按 §11.5 走价格方向代理口径。
        """
        universe = sorted({str(c) for c in codes if str(c)})
        day = str(trade_date or _shanghai_now().astimezone(_SHANGHAI_TZ).date())
        clock = now or _shanghai_now().replace(tzinfo=None)
        day_dir = self.intraday_root / day
        if not universe:
            return {"status": STATUS_WAITING_DATA, "records": [], "manifest": None, "reason_code": "UNIVERSE_EMPTY"}
        if not day_dir.is_dir():
            return {"status": STATUS_WAITING_DATA, "records": [], "manifest": None,
                    "reason_code": "INTRADAY_ARCHIVE_ABSENT", "archive_dir": str(day_dir)}

        bars, unparsed_bar_lines, malformed = self._read_minute_slices(day_dir, universe)
        ticks, tick_malformed = self._read_tick_slices(day_dir, universe)
        snapshots, snapshot_malformed = self._read_snapshot_slices(day_dir, universe)

        flow_by_minute: Dict[Tuple[str, str], Dict[str, float]] = {}
        for symbol, minute, volume, direction in ticks:
            bucket = flow_by_minute.setdefault((symbol, minute), {"buy_volume": 0.0, "sell_volume": 0.0, "neutral_volume": 0.0})
            if direction == "B":
                bucket["buy_volume"] += volume
            elif direction == "S":
                bucket["sell_volume"] += volume
            else:
                bucket["neutral_volume"] += volume

        latest_snapshot: Dict[str, Dict[str, Any]] = {}
        for rec in snapshots:
            symbol = str(rec.get("symbol") or "")
            if symbol:
                latest_snapshot[symbol] = rec

        records: List[Dict[str, Any]] = []
        for symbol in universe:
            points: List[Dict[str, Any]] = []
            dropped: List[Dict[str, Any]] = []
            for row in bars.get(symbol, []):
                minute, reason = normalize_minute_timestamp(row.get("ts"))
                if minute is None:
                    dropped.append({"raw_time": row.get("ts"), "field_status": FIELD_MISSING, "reason_code": reason})
                    continue
                if not row.get("close"):
                    dropped.append({"raw_time": row.get("ts"), "field_status": FIELD_MISSING,
                                    "reason_code": "MINUTE_BAR_PRICE_UNAVAILABLE"})
                    continue
                point: Dict[str, Any] = {
                    "time": minute,
                    "price": float(row["close"]),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "volume": float(row.get("volume") or 0.0),
                }
                if self._bar_not_finalized(day, minute, clock):
                    point["field_status"] = FIELD_NOT_READY
                    point["reason_code"] = "MINUTE_BAR_NOT_FINALIZED"
                flow = flow_by_minute.get((symbol, minute))
                if flow is not None and point.get("field_status") != FIELD_NOT_READY:
                    point["buy_volume"] = flow["buy_volume"]
                    point["sell_volume"] = flow["sell_volume"]
                points.append(point)
            points.sort(key=lambda item: item["time"])
            if points:
                points_field_status = FIELD_PRESENT
            elif dropped and all(item["field_status"] == FIELD_NOT_READY for item in dropped):
                points_field_status = FIELD_NOT_READY
            else:
                points_field_status = FIELD_MISSING

            record: Dict[str, Any] = {
                "code": symbol,
                "minute_points": points,
                "field_status": {"minute_points": points_field_status},
                "data_meta": {
                    "access_mode": ACCESS_INTRADAY_CAPTURE,
                    "archive_dir": str(day_dir),
                    "business_date": day,
                    "minute_point_count": len(points),
                    "minute_points_dropped": len(dropped),
                    "dropped_points": dropped,
                    "tick_coverage_pct": round(
                        len({m for (s, m) in flow_by_minute if s == symbol}) / len(points) * 100, 2
                    ) if points else 0.0,
                    "active_flow_source": "tick_direction_proxy(B/S/M 源侧推断·非真L2)" if any(
                        (s == symbol) for (s, _m) in flow_by_minute
                    ) else "unavailable",
                },
            }
            snap = latest_snapshot.get(symbol)
            if snap:
                if snap.get("prev_close"):
                    record["previous_close"] = float(snap["prev_close"])
                if snap.get("open"):
                    record["open"] = float(snap["open"])
                if snap.get("price") is not None:
                    record["current_price"] = snap.get("price")
                if snap.get("order_book"):
                    record["order_book"] = snap["order_book"]
                record["data_meta"]["captured_at"] = snap.get("captured_at")
                record["data_meta"]["watermarks"] = {
                    "order_book": snap.get("captured_at"),
                    "minute_bar": points[-1]["time"] if points else None,
                }
                record["field_status"]["opening_snapshot"] = FIELD_PRESENT
            else:
                record["field_status"]["opening_snapshot"] = FIELD_MISSING
            book = record.get("order_book")
            # T-09 口径：order_book 缺失或卖盘为 0 时权威解析器返回 None，本层原样透传不填充
            record["field_status"]["order_book"] = FIELD_PRESENT if book else FIELD_MISSING
            if not book:
                record.pop("order_book", None)
            record["data_meta"]["input_hash"] = content_hash(
                {"minute_points": points, "order_book": record.get("order_book"),
                 "open": record.get("open"), "previous_close": record.get("previous_close")}
            )
            records.append(record)

        manifest = {
            "data_snapshot_id": "dss_" + day.replace("-", "") + "_capture_"
            + content_hash({"day": day, "records": [r["data_meta"]["input_hash"] for r in records]})
            .split(":")[1][:12],
            "access_mode": ACCESS_INTRADAY_CAPTURE,
            "business_date": day,
            "archive_dir": str(day_dir),
            "capture_id": f"cap_{day.replace('-', '')}_{clock.strftime('%H%M%S')}",
            "provider_route": "IntradayArchiver:D3(minute_1m)/D9(snapshot)/D11(tick) 归档切片",
            "as_of": clock.replace(tzinfo=_SHANGHAI_TZ).isoformat(timespec="seconds"),
            "captured_at": clock.replace(tzinfo=_SHANGHAI_TZ).isoformat(timespec="seconds"),
            "physical_slices": ["minute_1m.jsonl", "snapshot.jsonl", "tick.jsonl"],
            "units": {
                "minute_bar.volume": "源侧 1m 成交量原值(未换算)",
                "tick.volume": "源侧分笔成交量原值(未换算)",
                "order_book.bid_volume/ask_volume": "手",
                "flow_ratio_note": "买卖比值仅在 tick 同口径内比较",
            },
            "normalization_schema_version": 1,
            "indicator_engine_version": algorithm_version,
            "universe": {"requested": len(universe), "assembled": len(records)},
            "malformed_line_count": {
                "minute_1m": malformed, "tick": tick_malformed, "snapshot": snapshot_malformed
            },
            "archive_unparsable_minute_line_count": unparsed_bar_lines,
            "dropped_point_count_total": sum(
                len(rec["data_meta"]["dropped_points"]) for rec in records
            ),
            "data_gate": gate,
        }
        manifest["snapshot_path"] = str(self._snapshot_dir(manifest))
        manifest["snapshot_manifest_hash"] = content_hash(manifest)
        self.stamp_records(records, manifest)
        self.persist_snapshot(manifest, records)
        return {"status": STATUS_OK, "records": records, "manifest": manifest}

    @staticmethod
    def _bar_not_finalized(day: str, minute: str, clock: datetime) -> bool:
        """Bar 起点 T 覆盖 T:00–T:59，收满 60 秒才定盘（§11.5）。"""
        try:
            start = datetime.combine(_date.fromisoformat(day), dt_time(int(minute[:2]), int(minute[3:])))
        except ValueError:
            return False
        return start + timedelta(minutes=1) > clock

    @staticmethod
    def _iter_jsonl(path: Path) -> Tuple[Iterable[Dict[str, Any]], int]:
        """逐行读 jsonl；坏行不静默丢弃，返回坏行计数交由清单披露。"""
        if not path.is_file():
            return [], 0
        good: List[Dict[str, Any]] = []
        bad = 0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                if isinstance(item, dict):
                    good.append(item)
                else:
                    bad += 1
        return good, bad

    def _read_minute_slices(
        self, day_dir: Path, universe: Sequence[str]
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], int, int]:
        """目标交易日分钟切片按 (标的, Bar 起点) 去重保序；无法归一化的原行单独保留待剔除。

        仅当 `ts` 明确带有**另一个交易日**的日期时才剔除（归档器一次拉取多日分钟线）；
        无法解析或不含日期的行必须留在切片里，由适配层按 §11.5 记 `field_status = missing`
        与原因码后计入 `dropped_points`，不得在此静默丢弃。
        """
        rows, malformed = self._iter_jsonl(day_dir / "minute_1m.jsonl")
        wanted = set(universe)
        by_minute: Dict[str, Dict[str, Dict[str, Any]]] = {}
        unparsed_rows: Dict[str, List[Dict[str, Any]]] = {}
        unparsed = 0
        for row in rows:
            symbol = str(row.get("symbol") or "")
            if symbol not in wanted:
                continue
            ts = str(row.get("ts") or "")
            if _DATE_PREFIX.match(ts) and not ts.startswith(day_dir.name):
                continue
            minute, _reason = normalize_minute_timestamp(ts)
            if minute is None:
                unparsed += 1
                unparsed_rows.setdefault(symbol, []).append(dict(row))
                continue
            by_minute.setdefault(symbol, {})[minute] = dict(row)
        out: Dict[str, List[Dict[str, Any]]] = {}
        for symbol in set(by_minute) | set(unparsed_rows):
            minutes = by_minute.get(symbol, {})
            out[symbol] = [minutes[key] for key in sorted(minutes)] + unparsed_rows.get(symbol, [])
        return out, unparsed, malformed

    def _read_tick_slices(self, day_dir: Path, universe: Sequence[str]) -> Tuple[List[Tuple[str, str, float, str]], int]:
        rows, malformed = self._iter_jsonl(day_dir / "tick.jsonl")
        wanted = set(universe)
        out: List[Tuple[str, str, float, str]] = []
        for row in rows:
            symbol = str(row.get("symbol") or "")
            if symbol not in wanted:
                continue
            minute, _reason = normalize_minute_timestamp(row.get("time"))
            if minute is None:
                malformed += 1
                continue
            try:
                volume = float(row.get("volume") or 0.0)
            except (TypeError, ValueError):
                malformed += 1
                continue
            out.append((symbol, minute, volume, str(row.get("direction") or "M")))
        return out, malformed

    @staticmethod
    def _read_snapshot_slices(day_dir: Path, universe: Sequence[str]) -> Tuple[List[Dict[str, Any]], int]:
        rows, malformed = DataAssembler._iter_jsonl(day_dir / "snapshot.jsonl")
        wanted = set(universe)
        return [r for r in rows if str(r.get("symbol") or "") in wanted], malformed


__all__ = [
    "ACCESS_FINALIZED_LOCAL",
    "ACCESS_INTRADAY_CAPTURE",
    "ALGORITHM_VERSION",
    "COVERAGE_REQUIRED_FIELDS",
    "COVERAGE_THRESHOLD_DEFAULT",
    "DataAssembler",
    "GATE_OBSERVATION",
    "GATE_PASS",
    "GATE_WAITING_DATA",
    "STATUS_OK",
    "STATUS_SOURCE_ERROR",
    "STATUS_WAITING_DATA",
    "build_universe_watermark",
    "content_hash",
    "layer_denominator",
]
