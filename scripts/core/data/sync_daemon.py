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
import time
from typing import Any, Dict, List, Optional, Set

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

        if executed_pools:
            return {
                "status": "executed",
                "date": today,
                "time": now_time_str,
                "executed_pools": executed_pools,
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
