# -*- coding: utf-8 -*-
"""运行锁：跨平台文件锁，粒度 `model_id + trade_date`（B2 / O-02 / C-06）。

与 T-07 草稿编辑锁（粒度 `model_id + draft_revision`）**同族实现**（复用
`core.selection_models.file_lock.FileLock`），差异仅在粒度与持有时长：

- 粒度 = `model_id + trade_date`：允许多模型并行、同模型同交易日**串行**；
  守护进程与手工 CLI 天然互斥（多进程互斥，§10.5）；
- 持有时长 = **运行期持有**（C-06）：获取于层级执行前、释放在层级执行后，
  不做跨 Tick 常驻；
- 锁文件落 `temp/selection-models/locks/`，配套「超时释放 + 显式解锁 + 持有者可见」
  （S-03/O-02 配套要求），进程异常退出由操作系统释放底层 flock，不留永久死锁。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.selection_models.file_lock import (
    DEFAULT_TIMEOUT_SECONDS,
    FileLock,
)
from core.selection_models.paths import lock_dir


def run_lock_path(model_id: str, trade_date: str, *, root: Optional[Path] = None) -> Path:
    """运行锁文件路径：`<lock_root>/<model_id>.<trade_date>.run.lock`。"""
    from core.selection_models.paths import _safe_date, _safe_id  # 复用路径白名单

    name = f"{_safe_id(model_id, 'model_id')}.{_safe_date(trade_date, 'trade_date')}.run.lock"
    return Path(root or lock_dir()) / name


class RunLockManager:
    """运行期排他锁管理器（粒度 `model_id + trade_date`）。"""

    def __init__(
        self,
        *,
        root: Optional[Path] = None,
        timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.root = Path(root) if root else lock_dir()
        self.timeout_s = float(timeout_s)
        self._held: Dict[str, FileLock] = {}

    def path(self, model_id: str, trade_date: str) -> Path:
        return run_lock_path(model_id, trade_date, root=self.root)

    def acquire(
        self,
        model_id: str,
        trade_date: str,
        *,
        operator: Optional[str] = None,
        run_id: Optional[str] = None,
        stage_id: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> Optional[FileLock]:
        """尝试获取运行锁；已被占用时超时返回 `None`（不阻塞、不死锁）。"""
        key = f"{model_id}|{trade_date}"
        existing = self._held.get(key)
        if existing is not None and existing.held:
            return existing
        lock = FileLock(
            self.path(model_id, trade_date),
            timeout_s=self.timeout_s if timeout_s is None else timeout_s,
        )
        owner = {
            "model_id": model_id,
            "trade_date": trade_date,
            "operator": operator,
            "run_id": run_id,
            "stage_id": stage_id,
            "purpose": "model_run",
        }
        if not lock.acquire(owner):
            return None
        self._held[key] = lock
        return lock

    def status(self, model_id: str, trade_date: str) -> Optional[Dict[str, Any]]:
        """锁持有者可见性（O-02）：返回旁车持有者信息，未持有时返回 `None`。"""
        key = f"{model_id}|{trade_date}"
        held = self._held.get(key)
        if held is not None and held.held:
            return held.holder()
        return FileLock(self.path(model_id, trade_date)).holder()

    def release(self, model_id: str, trade_date: str) -> bool:
        """显式解锁：释放本进程持有的锁并清除旁车持有者记录。"""
        key = f"{model_id}|{trade_date}"
        held = self._held.pop(key, None)
        if held is not None:
            held.release()
            return True
        holder_path = Path(str(self.path(model_id, trade_date)) + ".holder.json")
        if not holder_path.exists():
            return False
        try:
            holder_path.unlink()
            return True
        except OSError:
            return False


__all__ = ["RunLockManager", "run_lock_path"]