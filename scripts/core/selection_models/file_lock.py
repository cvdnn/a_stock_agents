# -*- coding: utf-8 -*-
"""跨平台悲观文件锁（T-07 / S-03 / O-02 同族实现）。

- `fcntl`（POSIX）/ `msvcrt`（Windows）封装，非阻塞尝试 + 超时等待；
- 锁对象的持有者信息写入旁车 JSON，供"锁持有者可见"（S-03 配套要求）；
- 进程异常退出时由操作系统释放底层锁，**不会**留下永久死锁；另提供显式解锁。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

try:  # pragma: no cover - 平台分支
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

try:  # pragma: no cover - 平台分支
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None  # type: ignore[assignment]

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_POLL_SECONDS = 0.05


class FileLockError(RuntimeError):
    """文件锁相关错误。"""


class FileLock:
    """基于文件描述符的排他锁；`acquire()` 超时返回 False 而非阻塞。"""

    def __init__(
        self,
        path: Path,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
        poll_s: float = DEFAULT_POLL_SECONDS,
    ) -> None:
        self.path = Path(path)
        self.holder_path = Path(str(self.path) + ".holder.json")
        self.timeout_s = float(timeout_s)
        self.poll_s = float(poll_s)
        self._fd: Optional[int] = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self, owner: Optional[Mapping[str, Any]] = None) -> bool:
        if self.held:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + self.timeout_s
        while True:
            if self._try_lock(fd):
                self._fd = fd
                self._write_holder(owner)
                return True
            if time.monotonic() >= deadline:
                os.close(fd)
                return False
            time.sleep(self.poll_s)

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            self._unlock(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None
            try:
                self.holder_path.unlink()
            except FileNotFoundError:
                pass

    def holder(self) -> Optional[Dict[str, Any]]:
        if not self.holder_path.exists():
            return None
        try:
            return json.loads(self.holder_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def __enter__(self) -> "FileLock":
        if not self.acquire():
            raise FileLockError(f"获取文件锁超时: {self.path}")
        return self

    def __exit__(self, *_: Any) -> None:
        self.release()

    # ------------------------------------------------------------ 平台分支
    def _try_lock(self, fd: int) -> bool:
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt is not None:  # pragma: no cover - Windows
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - 极少数平台
                raise FileLockError("当前平台不支持文件锁（缺少 fcntl/msvcrt）")
            return True
        except OSError:
            return False

    def _unlock(self, fd: int) -> None:
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

    def _write_holder(self, owner: Optional[Mapping[str, Any]]) -> None:
        payload = {
            "path": str(self.path),
            "pid": os.getpid(),
            "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **dict(owner or {}),
        }
        tmp = Path(str(self.holder_path) + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.holder_path)


__all__ = ["DEFAULT_POLL_SECONDS", "DEFAULT_TIMEOUT_SECONDS", "FileLock", "FileLockError"]