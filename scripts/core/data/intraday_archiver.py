# -*- coding: utf-8 -*-
"""盘中前向采集归档器 (Intraday Archiver) — SPEC-DATA §5.1 D3/D9/D11/D12 运行捕获切片。

服务对象：选股漏斗示例 close_to_open_turning_point 的盘中阶段
- D9  盘中实时快照流 → snapshot.jsonl  （market_gate 终判 / opening_gap 的 gap_pct）
- D3  1 分钟 K 前向归档 → minute_1m.jsonl（turning_point 的 minute_points 主输入，**不可回补**）
- D11 分笔成交明细 → tick.jsonl（ERS A/B 组主动买卖量；direction B/S/M 为源侧推断，非真 L2）
- D12 集合竞价观测 → auction.jsonl（09:15–09:25 窗口内的快照切片；仅归档不参与信号）

落盘位置（裁定 W-08）：local/cache/intraday/<交易日>/，POSIX 700/600，Git 与打包发布排除。
数据切片 jsonl 只追加不可改（append-only，按交易日分片）；manifest.json 为批次索引可覆写。
由切片派生的候选清单与信号归档仍落 output/（工作区三桶纪律）。

铁律（规范 §5.1 / §5.3 条件 4）：
- 采集失败显式记录到 manifest["errors"]，不静默丢弃；
- 盘口五档已按 T-09 收敛至权威解析器 tencent_fields（order_book 缺失或卖盘为 0
  时为 None），消费方须按 Kleene 判 UNKNOWN，禁止以 0 参与比较；
- 停止后须调用 seal() 封存切片并计算 §5.5 水位（写 dataset_audit，不翻正控制台接入状态）。
"""
from __future__ import annotations

import json
import os
import time as _time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from core.config import get_logger
    from core.workspace import PROJECT_ROOT
except ImportError:  # 独立脚本直接执行回退
    import logging

    get_logger = logging.getLogger
    PROJECT_ROOT = Path(__file__).resolve().parents[3]

logger = get_logger("core.data.intraday_archiver")

#: 落盘根目录（W-08：local/ 公共时序底座，700 权限物理隔离）
INTRADAY_CACHE_ROOT = PROJECT_ROOT / "local" / "cache" / "intraday"

#: 竞价窗口（D12）与连续交易窗口
AUCTION_START = dt_time(9, 15)
AUCTION_END = dt_time(9, 25)
MARKET_OPEN = dt_time(9, 30)
MARKET_CLOSE = dt_time(15, 0)


def _default_snapshot_fetcher():
    """D9：腾讯 L1 批量快照（DataBridge 统一封装）。"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    return lambda codes: (bridge.fetch_batch_snapshot(codes) or [])


def _default_minute_fetcher() -> Callable[[str], List[Dict[str, Any]]]:
    """D3 前向通道：腾讯 mkline m1（返回按 ts 升序的 bar 列表）。"""
    from core.data.fetch_realtime import get_price

    def fetch(code: str) -> List[Dict[str, Any]]:
        df = get_price(code, "1m", 320)
        if df is None or df.empty:
            return []
        bars = []
        for ts, row in df.iterrows():
            bars.append({
                "ts": ts.strftime("%Y-%m-%d %H:%M"),
                "open": float(row["open"]), "close": float(row["close"]),
                "high": float(row["high"]), "low": float(row["low"]),
                "volume": float(row["volume"]),
            })
        return bars

    return fetch


def _default_tick_fetcher() -> Callable[[str], List[Dict[str, Any]]]:
    """D11：腾讯分笔成交明细（最新页，direction 为源侧推断 B/S/M）。"""
    import requests

    url = "https://stock.gtimg.cn/data/index.php"

    def fetch(code: str) -> List[Dict[str, Any]]:
        try:
            session = requests.Session()
            session.trust_env = False
            resp = session.get(url, params={"appn": "detail", "action": "data", "c": code, "p": 0}, timeout=10)
            resp.raise_for_status()
            text = resp.text.strip()
        except Exception as exc:
            raise RuntimeError(f"tick 拉取失败: {exc.__class__.__name__}") from exc
        if "=[" not in text:
            return []
        bracket = text.split("=[", 1)[1].rstrip("];")
        parts = bracket.split(",", 1)
        records_raw = parts[1].strip('"').split("|") if len(parts) > 1 else []
        out = []
        for rec in records_raw:
            fields = rec.split("/")
            if len(fields) < 7:
                continue
            try:
                out.append({
                    "seq": int(fields[0]) if fields[0].isdigit() else 0,
                    "time": fields[1],
                    "price": float(fields[2]),
                    "volume": int(fields[4]),
                    "amount": float(fields[5]),
                    "direction": fields[6],  # B/S/M（源侧推断，非真 L2）
                })
            except (ValueError, IndexError):
                continue
        return out

    return fetch


class IntradayArchiver:
    """盘中前向采集归档器：一个实例绑定一个交易日与一份候选池。"""

    def __init__(
        self,
        symbols: Iterable[str],
        out_root: Optional[Path] = None,
        snapshot_interval: float = 1.0,
        minute_interval: float = 60.0,
        tick_interval: float = 3.0,
        db_path: Optional[Path] = None,
        snapshot_fetcher: Optional[Callable[[List[str]], List[Dict[str, Any]]]] = None,
        minute_fetcher: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
        tick_fetcher: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
    ):
        self.symbols: List[str] = list(dict.fromkeys(symbols))
        self.snapshot_interval = max(1.0, snapshot_interval)
        self.minute_interval = max(10.0, minute_interval)
        self.tick_interval = max(1.0, tick_interval)
        self.db_path = db_path
        self.trade_date = datetime.now().strftime("%Y-%m-%d")
        self.root = Path(out_root) if out_root else (INTRADAY_CACHE_ROOT / self.trade_date)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

        self.snapshot_fetcher = snapshot_fetcher or _default_snapshot_fetcher()
        self.minute_fetcher = minute_fetcher or _default_minute_fetcher()
        self.tick_fetcher = tick_fetcher or _default_tick_fetcher()

        self._last_minute_ts: Dict[str, str] = {}
        self._last_tick_seq: Dict[str, int] = {}
        self._next_minute_at = 0.0
        self._next_tick_at = 0.0
        self.manifest: Dict[str, Any] = {
            "trade_date": self.trade_date,
            "symbols": self.symbols,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_cycle_at": None,
            "sealed": False,
            "counts": {"snapshot": 0, "minute": 0, "tick": 0, "auction": 0},
            "covered_symbols": [],
            "errors": [],
        }

    # ---------------------------------------------------------------- 基础设施
    def _append(self, name: str, records: Iterable[Dict[str, Any]]) -> int:
        """追加写入 jsonl 切片（append-only）；单条失败显式记 manifest.errors。"""
        path = self.root / name
        payload = list(records)
        if not payload:
            return 0
        try:
            with open(path, "a", encoding="utf-8") as fh:
                for rec in payload:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            self.manifest["errors"].append(f"{name}:write:{exc.__class__.__name__}")
            return 0
        return len(payload)

    def _write_manifest(self) -> None:
        path = self.root / "manifest.json"
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            self.manifest["errors"].append(f"manifest:write:{exc.__class__.__name__}")

    def _now(self) -> datetime:
        return datetime.now()

    def _in_auction(self, t: dt_time) -> bool:
        return AUCTION_START <= t <= AUCTION_END

    # ---------------------------------------------------------------- 采集通道
    def capture_snapshot(self) -> int:
        """D9 快照采集（含 D12 竞价窗口切片与 order_book=None 口径）。"""
        try:
            quotes = self.snapshot_fetcher(self.symbols) or []
        except Exception as exc:
            self.manifest["errors"].append(f"snapshot:{exc.__class__.__name__}")
            return 0
        now = self._now()
        captured_at = now.strftime("%Y-%m-%d %H:%M:%S")
        records = []
        auction_records = []
        for q in quotes:
            code = str(q.get("code") or "")
            if not code:
                continue
            rec = {
                "captured_at": captured_at,
                "symbol": code,
                "name": q.get("name"),
                "price": q.get("price"),
                "prev_close": q.get("prev_close"),
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "change_pct": q.get("change_pct"),
                "volume_hands": q.get("volume_hands"),
                "amount": q.get("amount"),
                "outer": q.get("outer"),
                "inner": q.get("inner"),
                # T-09 已落地：五档透传（缺失或卖盘为 0 时为 None，消费方判 UNKNOWN）
                "order_book": q.get("order_book"),
            }
            records.append(rec)
            if self._in_auction(now.time()):
                auction_records.append({**rec, "phase": "auction"})
        written = self._append("snapshot.jsonl", records)
        if auction_records:
            self.manifest["counts"]["auction"] += self._append("auction.jsonl", auction_records)
        seen = {str(q.get("code") or "") for q in quotes if q.get("code")}
        covered = set(self.manifest["covered_symbols"]) | (seen & set(self.symbols))
        self.manifest["covered_symbols"] = sorted(covered)
        self.manifest["counts"]["snapshot"] += written
        return written

    def capture_minute(self) -> int:
        """D3 前向采集：仅追加新增 bar（ts 严格大于上次水位）。"""
        written = 0
        for symbol in self.symbols:
            try:
                bars = self.minute_fetcher(symbol) or []
            except Exception as exc:
                self.manifest["errors"].append(f"minute:{symbol}:{exc.__class__.__name__}")
                continue
            last = self._last_minute_ts.get(symbol)
            fresh = [b for b in bars if last is None or b["ts"] > last]
            if fresh:
                self._last_minute_ts[symbol] = fresh[-1]["ts"]
            written += self._append("minute_1m.jsonl", ({**b, "symbol": symbol} for b in fresh))
        self.manifest["counts"]["minute"] += written
        return written

    def capture_tick(self) -> int:
        """D11 前向采集：仅追加 seq 递增的新分笔。"""
        written = 0
        for symbol in self.symbols:
            try:
                records = self.tick_fetcher(symbol) or []
            except Exception as exc:
                self.manifest["errors"].append(f"tick:{symbol}:{exc.__class__.__name__}")
                continue
            last = self._last_tick_seq.get(symbol, 0)
            fresh = [r for r in records if r.get("seq", 0) > last]
            if fresh:
                self._last_tick_seq[symbol] = fresh[-1]["seq"]
            written += self._append("tick.jsonl", ({**r, "symbol": symbol} for r in fresh))
        self.manifest["counts"]["tick"] += written
        return written

    # ---------------------------------------------------------------- 调度
    def run_cycle(self) -> Dict[str, Any]:
        """单轮采集：快照必采；分钟/分笔按各自周期到期触发。"""
        now = self._now()
        counts = {"snapshot": self.capture_snapshot()}
        if now.time() >= MARKET_OPEN:
            if _time.time() >= self._next_minute_at:
                counts["minute"] = self.capture_minute()
                self._next_minute_at = _time.time() + self.minute_interval
            if _time.time() >= self._next_tick_at:
                counts["tick"] = self.capture_tick()
                self._next_tick_at = _time.time() + self.tick_interval
        self.manifest["last_cycle_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self._write_manifest()
        return counts

    def run(self, max_cycles: Optional[int] = None, until: Optional[dt_time] = None) -> Dict[str, Any]:
        """循环采集：到达 until / 收盘 15:00 / max_cycles 耗尽后自动封存退出。"""
        cycles = 0
        try:
            while True:
                now = self._now()
                stop_at = until or MARKET_CLOSE
                if now.time() >= stop_at:
                    break
                if max_cycles is not None and cycles >= max_cycles:
                    break
                self.run_cycle()
                cycles += 1
                _time.sleep(self.snapshot_interval)
        except KeyboardInterrupt:
            logger.info("intraday archiver 收到中断信号，封存退出")
        finally:
            self.seal()
        return self.manifest

    # ---------------------------------------------------------------- 封存与水位
    def seal(self) -> Dict[str, Any]:
        """盘后封存：计算 §5.5 水位并写入 dataset_audit（不翻正控制台接入状态）。"""
        now = self._now()
        self.manifest["sealed"] = True
        self.manifest["sealed_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        total = len(self.symbols)
        covered = len(self.manifest["covered_symbols"])
        self.manifest["watermark"] = {
            "universe_total": total,
            "covered": covered,
            "coverage_pct": round(covered / total * 100, 2) if total else 0.0,
            "availability": "finalized" if total and covered == total else "degraded",
        }
        self._write_manifest()
        # 写入 dataset_audit 供 §5.5 消费（dataset 键未入控制台登记册探测，保持占位，W-05/W-08）
        try:
            from core.data.dataset_sync import write_universe_watermark
            from core.data.sync_engine import MarketDataStore

            store = MarketDataStore(self.db_path) if self.db_path else MarketDataStore()
            write_universe_watermark(
                store, "intraday_snapshot", covered, total,
                availability=self.manifest["watermark"]["availability"],
                blocking_fields=["snapshot"] if covered < total else [],
                trade_date=self.trade_date,
                note="运行捕获切片水位（D9；D11 tick/D12 auction 见 manifest counts）",
            )
        except Exception as exc:  # 水印失败不阻断封存，但必须留痕
            self.manifest["errors"].append(f"watermark:{exc.__class__.__name__}")
            self._write_manifest()
        return self.manifest


def load_day_slices(trade_date: Optional[str] = None, root: Optional[Path] = None) -> Dict[str, Any]:
    """读取某交易日的封存清单与切片行数（复盘/回测装配入口）。"""
    base = Path(root) if root else INTRADAY_CACHE_ROOT
    day = trade_date or datetime.now().strftime("%Y-%m-%d")
    day_dir = base / day
    if not day_dir.is_dir():
        return {"trade_date": day, "exists": False}
    manifest_path = day_dir / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
    out = {"trade_date": day, "exists": True, "manifest": manifest, "files": {}}
    for name in ("snapshot.jsonl", "minute_1m.jsonl", "tick.jsonl", "auction.jsonl"):
        path = day_dir / name
        if not path.is_file():
            continue
        lines = 0
        with open(path, "r", encoding="utf-8") as fh:
            for _ in fh:
                lines += 1
        out["files"][name] = {"lines": lines, "bytes": path.stat().st_size}
    return out
