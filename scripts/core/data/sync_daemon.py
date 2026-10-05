# -*- coding: utf-8 -*-
"""A-Stock 本地行情自动化定时同步守护进程 (DataSyncDaemon)

核心职责:
1. 时钟驱动与定盘监听: 依据 TradeCalendar 时钟状态机，精确在交易所定盘归档期 (>= 15:35) 触发增量同步；
2. 分级标的池调度:
   - 15:35 优先触发 P0 核心持仓池 (holdings) 定盘同步；
   - 15:40 触发 P1 重点自选与关注池 (watchlist / focus) 及核心大盘指数同步；
3. 当日幂等防重: 记录当日成功同步状态，同一交易日定盘数据不重复拉取；
4. 规范日志沉淀: 严格遵守工作区规范，日志统一写入 log/sync_daemon.log；
5. 优雅退出支持: 响应 SIGINT / SIGTERM 信号安全停机。
"""

from datetime import datetime, time as dt_time
import json
import logging
import os
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from core.config import PROJECT_ROOT, LOG_DIR, get_logger
    from core.data.sync_engine import DataSyncEngine, TradeCalendar
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    LOG_DIR = PROJECT_ROOT / "log"
    import logging
    get_logger = logging.getLogger
    from scripts.core.data.sync_engine import DataSyncEngine, TradeCalendar

logger = get_logger("core.data.sync_daemon")


# ---------------------------------------------------------------------------
# 服务内自动巡检的共享运行时状态（唯一事实来源）
#
# 消费者是 server 进程内的 `_market_post_settle_cron` 协程（scripts/server/app.py），
# /api/market_data/daemon/* 端点只做读写，不另存副本，避免"开关显示与真实调度脱节"。
#
# 重要边界：独立 CLI 守护进程 DataSyncDaemon 运行在**另一个进程**，
# 无法共享本进程内存状态，因此不受这里的 enabled/workers 影响。
# ---------------------------------------------------------------------------
SERVER_SYNC_RUNTIME: Dict[str, Any] = {
    "enabled": True,
    "interval": 60,
    "workers": 4,
    "last_check": None,
    "last_run": None,
    "last_status": None,
    "last_message": None,
    "skipped_reason": None,
    # 巡检事件不依赖 logging 级别（core.config 默认 WARNING 会丢弃 info 行），
    # 由 record_sync_runtime_event 直接维护，保证 UI 读到的执行历史真实可回溯。
    "history": [],
}

HISTORY_LIMIT = 50


# ---------------------------------------------------------------------------
# P3 优先级仲裁器（SPEC-UI-003 §4.3：同一时刻最多一个 P3；P3 不得抢占 P0/P1）
#
# 与服务内调度协程、任务队列共享同一份进程内事实：
# - p3_task 非空时禁止新的 P3 提交（单任务互斥）；
# - core_active（P0/P1/P2 定盘同步进行中）时禁止 P3 启动（不抢占高优先级）；
# - 反向不阻塞：P0/P1 到点照常触发，不被 P3 拖住。
# ---------------------------------------------------------------------------
_SYNC_ARBITER_LOCK = threading.Lock()

SYNC_ARBITER: Dict[str, Any] = {
    "p3_task": None,        # 当前活动 P3 拥有者（task_id 或 "cron:<date>"）
    "core_active": False,   # P0/P1/P2 定盘同步是否进行中
}


def try_acquire_p3(owner: str) -> Tuple[bool, str]:
    """尝试占用 P3 槽位。冲突时返回 (False, 原因)，绝不静默排队。"""
    with _SYNC_ARBITER_LOCK:
        if SYNC_ARBITER["p3_task"]:
            return False, f"已有活动 P3 任务（{SYNC_ARBITER['p3_task']}），同一时刻仅允许一个 P3"
        if SYNC_ARBITER["core_active"]:
            return False, "P0/P1/P2 定盘同步进行中，P3 不得抢占高优先级任务"
        SYNC_ARBITER["p3_task"] = owner
        return True, ""


def release_p3(owner: str) -> None:
    """释放 P3 槽位；仅持有者可释放，防止误清他人锁。"""
    with _SYNC_ARBITER_LOCK:
        if SYNC_ARBITER["p3_task"] == owner:
            SYNC_ARBITER["p3_task"] = None


def set_core_sync_active(active: bool) -> None:
    with _SYNC_ARBITER_LOCK:
        SYNC_ARBITER["core_active"] = bool(active)


def p3_conflict_reason() -> Optional[str]:
    """存在冲突活动任务时返回拒绝原因，否则 None（用于创建前预检 409）。"""
    with _SYNC_ARBITER_LOCK:
        if SYNC_ARBITER["p3_task"]:
            return f"已有活动 P3 任务（{SYNC_ARBITER['p3_task']}），请等待结束或先取消"
        if SYNC_ARBITER["core_active"]:
            return "P0/P1/P2 定盘同步进行中，P3 不得抢占"
        return None


def parse_hhmm(value: str) -> Optional[dt_time]:
    """HH:MM → datetime.time；非法返回 None。"""
    try:
        hour_str, minute_str = str(value).strip().split(":")
        return dt_time(int(hour_str), int(minute_str))
    except (ValueError, AttributeError):
        return None


def is_auto_tier_due(now, tier: str, eff_settings: Dict[str, Any], executed_dates: Dict[str, str]) -> bool:
    """纯判定：某层级定时自动同步当前是否到期且今日尚未执行（交易日判断由调用方负责）。

    - P0/P1 受定时守护总开关 daemon.enabled 门控；P3 额外受 p3.enabled 门控；
    - 到点判定为 now >= 设定时间；当日同层级只允许成功执行一次。
    """
    daemon = eff_settings.get("daemon") or {}
    if not daemon.get("enabled", True):
        return False
    if tier == "P3" and not (eff_settings.get("p3") or {}).get("enabled", True):
        return False
    time_key = {"P0": "p0_time", "P1": "p1_time", "P3": "time"}[tier]
    raw_time = daemon.get(time_key, "") if tier in ("P0", "P1") else (eff_settings.get("p3") or {}).get("time", "")
    due_at = parse_hhmm(str(raw_time))
    if due_at is None:
        return False
    today = now.strftime("%Y-%m-%d")
    if executed_dates.get(tier) == today:
        return False
    return now.time() >= due_at


def record_sync_runtime_event(message: str, status: Optional[str] = None) -> Dict[str, Any]:
    """追加一条巡检事件到进程内历史；status 非空时同步更新 last_status/last_message。"""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    level = (status or "info").upper()
    entry = f"[{stamp}] {level} :: {message}"
    history = SERVER_SYNC_RUNTIME.setdefault("history", [])
    if not history or history[-1] != entry:
        history.append(entry)
        del history[:-HISTORY_LIMIT]
    SERVER_SYNC_RUNTIME["last_message"] = message
    if status:
        SERVER_SYNC_RUNTIME["last_status"] = status
    return sync_runtime_snapshot()


def sync_runtime_snapshot() -> Dict[str, Any]:
    """返回当前服务内巡检状态的可变副本。"""
    return dict(SERVER_SYNC_RUNTIME)


def apply_sync_runtime_control(
    action: str = "status",
    interval: Optional[int] = None,
    workers: Optional[int] = None,
) -> Dict[str, Any]:
    """按 action 变更服务内巡检调度参数；非法值夹紧到安全区间。"""
    if interval is not None:
        SERVER_SYNC_RUNTIME["interval"] = max(15, min(int(interval), 3600))
    if workers is not None:
        SERVER_SYNC_RUNTIME["workers"] = max(1, min(int(workers), 16))

    act = (action or "status").strip().lower()
    if act in ("start", "restart"):
        SERVER_SYNC_RUNTIME["enabled"] = True
        # 恢复启用时必须清除暂停原因，否则日志会同时出现"已启用"与"已被暂停"
        SERVER_SYNC_RUNTIME["skipped_reason"] = None
        if act == "restart":
            SERVER_SYNC_RUNTIME["last_status"] = None
        record_sync_runtime_event(
            "服务内自动巡检已启用（API 控制）" if act == "start" else "服务内自动巡检已重启（API 控制）",
            "info",
        )
    elif act == "stop":
        SERVER_SYNC_RUNTIME["enabled"] = False
        SERVER_SYNC_RUNTIME["skipped_reason"] = "服务内自动巡检已被暂停"
        record_sync_runtime_event(
            "服务内自动巡检已暂停（API 控制）：15:35 定盘同步不再自动执行", "info",
        )
    return sync_runtime_snapshot()


class DataSyncDaemon:
    """本地行情数据自动化定时同步守护器"""

    DEFAULT_POOLS = ["holdings", "watchlist", "focus"]

    def __init__(
        self,
        pools: Optional[List[str]] = None,
        check_interval: int = 60,
        max_workers: int = 4,
        log_file: Optional[Path] = None,
    ):
        self.pools = pools or list(self.DEFAULT_POOLS)
        self.check_interval = max(5, check_interval)
        self.max_workers = max(1, min(max_workers, 16))
        self.engine = DataSyncEngine()
        self._stop_requested = False
        self._synced_dates: Dict[str, str] = {}

        # 确保日志文件落于 log/
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_file = log_file or (LOG_DIR / "sync_daemon.log")
        self._setup_file_logger()

    def _setup_file_logger(self):
        self.file_logger = logging.getLogger("sync_daemon.file")
        self.file_logger.setLevel(logging.INFO)
        if not self.file_logger.handlers:
            handler = logging.FileHandler(str(self.log_file), encoding="utf-8")
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            handler.setFormatter(formatter)
            self.file_logger.addHandler(handler)

    def log(self, message: str, level: str = "info"):
        lvl = level.lower()
        if lvl == "error":
            logger.error(message)
            self.file_logger.error(message)
        elif lvl == "warning":
            logger.warning(message)
            self.file_logger.warning(message)
        else:
            logger.info(message)
            self.file_logger.info(message)

    def run_once(self) -> Dict[str, Any]:
        """单次时钟检查并执行到期的同步任务"""
        phase_info = TradeCalendar.get_market_phase()
        today = phase_info["date_str"]
        now_time_str = phase_info["time_str"]
        is_trading_day = phase_info["is_trading_day"]
        phase_label = phase_info["phase_label"]

        # 1. 非交易日（周末/法定节假日）处理
        if not is_trading_day:
            msg = f"今日 ({today}) 为非交易日 ({phase_label})，休市中跳过定盘同步"
            self.log(msg)
            return {
                "status": "skipped",
                "reason": "non_trading_day",
                "date": today,
                "phase": phase_info["phase"],
                "message": msg,
            }

        now_dt = datetime.now()
        t = now_dt.time()

        # 2. 判断是否已到定盘同步窗口 (15:35 之后)
        t_p0 = dt_time(15, 35)
        t_p1 = dt_time(15, 40)

        if t < t_p0:
            msg = f"当前时段 ({now_time_str} · {phase_label}) 尚未到达盘后定盘同步窗口 (15:35 开启)"
            return {
                "status": "waiting",
                "reason": "before_settlement_window",
                "date": today,
                "time": now_time_str,
                "phase": phase_info["phase"],
                "message": msg,
            }

        # 3. 达到定盘窗口，按优先级调度
        executed_pools = []
        batch_results = {}

        # 3.1 P0 核心持仓同步 (>= 15:35)
        if "holdings" in self.pools:
            if self._synced_dates.get("holdings") != today:
                self.log(f"--> 触发 P0 核心持仓池定盘同步 (Holdings)... [时钟: {now_time_str}]")
                symbols = self.engine.resolve_symbols(pool="holdings")
                if symbols:
                    res = self.engine.sync_batch(
                        symbols, mode="incremental", count=250, max_workers=self.max_workers
                    )
                    batch_results["holdings"] = res
                    self.log(f"    P0 持仓同步完成: 成功 {res['success_count']}/{res['total_requested']}")
                self._synced_dates["holdings"] = today
                executed_pools.append("holdings")
            else:
                self.log(f"    P0 持仓池今日 ({today}) 已完成定盘同步，跳过重复拉取")

        # 3.2 P1 重点自选与关注池同步 (>= 15:40)
        if t >= t_p1:
            for p in ["watchlist", "focus"]:
                if p in self.pools:
                    if self._synced_dates.get(p) != today:
                        include_idx = (p == "watchlist")
                        self.log(f"--> 触发 P1 {p} 池定盘同步 (含指数: {include_idx})... [时钟: {now_time_str}]")
                        symbols = self.engine.resolve_symbols(pool=p, include_indices=include_idx)
                        if symbols:
                            res = self.engine.sync_batch(
                                symbols, mode="incremental", count=120, max_workers=self.max_workers
                            )
                            batch_results[p] = res
                            self.log(f"    P1 {p} 同步完成: 成功 {res['success_count']}/{res['total_requested']}")
                        self._synced_dates[p] = today
                        executed_pools.append(p)
                    else:
                        self.log(f"    P1 {p} 池今日 ({today}) 已完成定盘同步，跳过重复拉取")

        # 3.3 数据集登记册同步 (SPEC-DATA §5.1 固定窗口，每日一次)
        from core.data import dataset_sync
        dataset_results = dataset_sync.run_due_datasets(now_dt, self._synced_dates, db_path=self.engine.store.db_path)
        for res in dataset_results:
            self.log(f"    数据集同步 {res['key']}: {res['status']} · rows={res['rows']} · source={res['source']}")

        if executed_pools or dataset_results:
            return {
                "status": "executed",
                "date": today,
                "time": now_time_str,
                "executed_pools": executed_pools,
                "datasets": [res["key"] for res in dataset_results],
                "details": batch_results,
            }
        else:
            return {
                "status": "up_to_date",
                "date": today,
                "time": now_time_str,
                "message": f"今日 ({today}) 所有关注股池定盘同步已全部就绪，无需额外拉取",
            }

    def run_forever(self):
        """常驻后台循环轮询"""
        self.log(f"=== A-Stock 数据同步守护进程启动 (间隔: {self.check_interval}s, 标的池: {self.pools}, 并发: {self.max_workers}) ===")

        def _handle_signal(signum, frame):
            self.log(f"接收到终止信号 ({signum})，正在优雅停止守护进程...")
            self._stop_requested = True

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        try:
            while not self._stop_requested:
                try:
                    res = self.run_once()
                    st = res.get("status")
                    if st == "executed":
                        self.log(f"[守护进程] 本轮定盘同步完成: {res.get('executed_pools')}")
                except Exception as e:
                    self.log(f"[守护进程异常] 轮询执行出错: {e}", level="error")

                # 细分沉睡，支持毫秒级快速响应停机信号
                for _ in range(self.check_interval):
                    if self._stop_requested:
                        break
                    time.sleep(1)
        finally:
            self.log("=== A-Stock 数据同步守护进程已安全退出 ===")

    def stop(self):
        self._stop_requested = True
