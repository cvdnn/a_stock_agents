# -*- coding: utf-8 -*-
"""用户模型草稿仓库：草稿持久化 + 悲观编辑锁（A6 / SSOT §7.6、S-03、T-07）。

路径规范（§7.6）：

```
output/config/selection-models/<model_id>/definition-v<N>.yaml   已发布不可变版本
output/config/selection-models/<model_id>/plan-v<N>.json         编译计划
output/config/selection-models/<model_id>/draft.yaml             可编辑草稿（不参与正式调度）
output/config/selection-models/<model_id>/active.json            当前启用版本指针
temp/selection-models/locks/<model_id>.draft.lock                草稿编辑悲观锁（T-07）
```

草稿并发采用**悲观锁**：进入编辑即独占，超时自动释放（进程异常退出由操作系统释放），
并提供显式解锁与"锁持有者可见"（S-03 配套要求）。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from core.selection_models.file_lock import (
    DEFAULT_TIMEOUT_SECONDS,
    FileLock,
    FileLockError,
)
from core.workspace import OUTPUT_DIR, TEMP_DIR

DEFAULT_BASE_DIR = OUTPUT_DIR / "config" / "selection-models"
DEFAULT_LOCK_DIR = TEMP_DIR / "selection-models" / "locks"

DRAFT_FILE = "draft.yaml"
DRAFT_META_FILE = "draft-meta.json"
ACTIVE_FILE = "active.json"
VERSIONS_FILE = "versions.json"

#: 模型 ID 白名单（§20.2）：不接受任意路径，避免目录穿越。
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


class DraftConflictError(ValueError):
    """草稿并发冲突（`base_version` / `draft_revision` 不匹配）；不得静默覆盖。"""

    code = "MODEL_DRAFT_CONFLICT"


def validate_model_id(model_id: str) -> str:
    candidate = str(model_id or "").strip()
    if not MODEL_ID_PATTERN.match(candidate):
        raise ValueError(f"非法 model_id（仅允许字母/数字/._-）：{model_id!r}")
    return candidate


def model_dir(model_id: str, base_dir: Optional[Path] = None) -> Path:
    return Path(base_dir or DEFAULT_BASE_DIR) / validate_model_id(model_id)


def atomic_write_text(path: Path, text: str) -> None:
    """先写同目录临时文件再 `os.replace`，避免半写状态被读到。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class DefinitionRepository:
    """草稿读写与悲观编辑锁；不涉及已发布版本的分配与指针切换。"""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        lock_dir: Optional[Path] = None,
        lock_timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_dir = Path(base_dir or DEFAULT_BASE_DIR)
        self.lock_dir = Path(lock_dir or DEFAULT_LOCK_DIR)
        self.lock_timeout_s = float(lock_timeout_s)
        self._held_locks: Dict[str, FileLock] = {}

    # ------------------------------------------------------------ 路径
    def dir_for(self, model_id: str) -> Path:
        return model_dir(model_id, self.base_dir)

    def draft_path(self, model_id: str) -> Path:
        return self.dir_for(model_id) / DRAFT_FILE

    def draft_meta_path(self, model_id: str) -> Path:
        return self.dir_for(model_id) / DRAFT_META_FILE

    def lock_path(self, model_id: str) -> Path:
        return self.lock_dir / f"{validate_model_id(model_id)}.draft.lock"

    # ------------------------------------------------------------ 草稿
    def load_draft(self, model_id: str) -> Optional[Dict[str, Any]]:
        draft_path = self.draft_path(model_id)
        meta_path = self.draft_meta_path(model_id)
        if not draft_path.exists() or not meta_path.exists():
            return None
        definition = yaml.safe_load(draft_path.read_text(encoding="utf-8")) or {}
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return {
            "model_id": validate_model_id(model_id),
            "definition": definition,
            "base_version": meta.get("base_version"),
            "draft_revision": int(meta.get("draft_revision", 0)),
            "updated_at": meta.get("updated_at"),
            "updated_by": meta.get("updated_by"),
        }

    def create_draft(
        self,
        model_id: str,
        definition: Mapping[str, Any],
        *,
        base_version: Optional[int] = None,
        operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.load_draft(model_id) is not None:
            raise DraftConflictError(f"模型 {model_id} 已存在草稿；请先加载后再保存")
        return self._write_draft(model_id, definition, base_version, 1, operator)

    def save_draft(
        self,
        model_id: str,
        definition: Mapping[str, Any],
        *,
        base_version: Optional[int],
        draft_revision: int,
        operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.load_draft(model_id)
        if existing is None:
            return self._write_draft(model_id, definition, base_version, 1, operator)
        if int(existing["draft_revision"]) != int(draft_revision):
            raise DraftConflictError(
                f"草稿修订号冲突：期望 {draft_revision}，当前 {existing['draft_revision']}；"
                "禁止最后写入者静默覆盖（§7.6 第3条）"
            )
        if existing["base_version"] != base_version:
            raise DraftConflictError(
                f"草稿基线版本冲突：期望 base_version={base_version}，当前 {existing['base_version']}"
            )
        return self._write_draft(
            model_id, definition, base_version, int(existing["draft_revision"]) + 1, operator
        )

    def delete_draft(self, model_id: str) -> bool:
        removed = False
        for path in (self.draft_path(model_id), self.draft_meta_path(model_id)):
            if path.exists():
                path.unlink()
                removed = True
        return removed

    def _write_draft(
        self,
        model_id: str,
        definition: Mapping[str, Any],
        base_version: Optional[int],
        revision: int,
        operator: Optional[str],
    ) -> Dict[str, Any]:
        target_dir = self.dir_for(model_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = _now()
        atomic_write_text(
            self.draft_path(model_id),
            yaml.safe_dump(dict(definition), allow_unicode=True, sort_keys=False),
        )
        atomic_write_text(
            self.draft_meta_path(model_id),
            json.dumps(
                {
                    "base_version": base_version,
                    "draft_revision": revision,
                    "updated_at": timestamp,
                    "updated_by": operator,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        return {
            "model_id": validate_model_id(model_id),
            "definition": dict(definition),
            "base_version": base_version,
            "draft_revision": revision,
            "updated_at": timestamp,
            "updated_by": operator,
        }

    # ------------------------------------------------------------ 悲观锁
    def acquire_lock(
        self,
        model_id: str,
        *,
        operator: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ) -> Optional[FileLock]:
        """获取草稿编辑独占锁；超时返回 None（不阻塞、不死锁）。"""
        lock = FileLock(
            self.lock_path(model_id),
            timeout_s=self.lock_timeout_s if timeout_s is None else timeout_s,
        )
        draft = self.load_draft(model_id) or {}
        owner = {
            "model_id": validate_model_id(model_id),
            "operator": operator,
            "draft_revision": draft.get("draft_revision"),
            "purpose": "draft_edit",
        }
        if not lock.acquire(owner):
            return None
        self._held_locks[validate_model_id(model_id)] = lock
        return lock

    def lock_status(self, model_id: str) -> Optional[Dict[str, Any]]:
        """返回锁持有者信息（锁可见性，S-03）；未持有时返回 None。"""
        held = self._held_locks.get(validate_model_id(model_id))
        if held is not None:
            return held.holder()
        return FileLock(self.lock_path(model_id)).holder()

    def release_lock(self, model_id: str) -> bool:
        """显式解锁：释放本进程持有的锁并清除旁车持有者记录（S-03）。"""
        key = validate_model_id(model_id)
        held = self._held_locks.pop(key, None)
        if held is not None:
            held.release()
            return True
        holder_path = Path(str(self.lock_path(model_id)) + ".holder.json")
        if not holder_path.exists():
            return False
        try:
            holder_path.unlink()
            return True
        except OSError:
            return False


__all__ = [
    "ACTIVE_FILE",
    "DEFAULT_BASE_DIR",
    "DEFAULT_LOCK_DIR",
    "DRAFT_FILE",
    "DRAFT_META_FILE",
    "VERSIONS_FILE",
    "DefinitionRepository",
    "DraftConflictError",
    "FileLockError",
    "atomic_write_text",
    "model_dir",
    "validate_model_id",
]