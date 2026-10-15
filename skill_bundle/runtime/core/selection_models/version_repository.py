# -*- coding: utf-8 -*-
"""已发布版本仓库：不可变版本、活动指针、回滚与归档（A6 / SSOT §7.6、§13.2）。

版本控制硬约束（§7.6）：

1. 发布号由服务端分配、模型内**单调递增**且不可复用；
2. 已发布版本**不可原地覆盖**，内容与哈希永久不变；
3. 草稿 `base_version` / `draft_revision` 冲突时**拒绝**，禁止静默覆盖；
4. **激活只移动活动版本指针**，不复制、不修改历史版本；激活旧版本即回滚；
5. 活动版本不可归档；已发布版本**禁止物理删除**。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

import yaml

from core.selection_models.definition_repository import (
    ACTIVE_FILE,
    DEFAULT_BASE_DIR,
    VERSIONS_FILE,
    DefinitionRepository,
    DraftConflictError,
    atomic_write_text,
    model_dir,
    validate_model_id,
)
from core.selection_models.hash import definition_hash as compute_definition_hash

STATUS_PUBLISHED = "PUBLISHED"
STATUS_ACTIVE = "ACTIVE"
STATUS_RETIRED = "RETIRED"
STATUS_ARCHIVED = "ARCHIVED"
VALID_STATUSES = (STATUS_PUBLISHED, STATUS_ACTIVE, STATUS_RETIRED, STATUS_ARCHIVED)


class VersionConflictError(ValueError):
    code = "MODEL_VERSION_CONFLICT"


class VersionNotFoundError(ValueError):
    code = "MODEL_VERSION_NOT_FOUND"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class VersionRecord:
    model_id: str
    version: int
    base_version: Optional[int]
    status: str
    definition_hash: str
    compiler_version: str
    plan_hash: str
    published_at: str
    published_by: Optional[str] = None
    activated_at: Optional[str] = None
    activated_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "base_version": self.base_version,
            "status": self.status,
            "definition_hash": self.definition_hash,
            "compiler_version": self.compiler_version,
            "plan_hash": self.plan_hash,
            "published_at": self.published_at,
            "published_by": self.published_by,
            "activated_at": self.activated_at,
            "activated_by": self.activated_by,
        }


@dataclass
class _Index:
    model_id: str
    active_version: Optional[int] = None
    pointer_revision: int = 0
    versions: List[Dict[str, Any]] = field(default_factory=list)


class VersionRepository:
    """已发布版本的存储与生命周期（发布 / 激活 / 回滚 / 归档）。"""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(base_dir or DEFAULT_BASE_DIR)

    # ------------------------------------------------------------ 路径
    def dir_for(self, model_id: str) -> Path:
        return model_dir(model_id, self.base_dir)

    def definition_path(self, model_id: str, version: int) -> Path:
        return self.dir_for(model_id) / f"definition-v{int(version)}.yaml"

    def plan_path(self, model_id: str, version: int) -> Path:
        return self.dir_for(model_id) / f"plan-v{int(version)}.json"

    def index_path(self, model_id: str) -> Path:
        return self.dir_for(model_id) / VERSIONS_FILE

    def active_path(self, model_id: str) -> Path:
        return self.dir_for(model_id) / ACTIVE_FILE

    # ------------------------------------------------------------ 索引
    def _load_index(self, model_id: str) -> _Index:
        path = self.index_path(model_id)
        if not path.exists():
            return _Index(model_id=validate_model_id(model_id))
        data = json.loads(path.read_text(encoding="utf-8"))
        return _Index(
            model_id=validate_model_id(model_id),
            active_version=data.get("active_version"),
            pointer_revision=int(data.get("pointer_revision", 0)),
            versions=list(data.get("versions") or []),
        )

    def _save_index(self, model_id: str, index: _Index) -> None:
        atomic_write_text(
            self.index_path(model_id),
            json.dumps(
                {
                    "model_id": index.model_id,
                    "active_version": index.active_version,
                    "pointer_revision": index.pointer_revision,
                    "versions": index.versions,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    def list_versions(self, model_id: str) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._load_index(model_id).versions]

    def active_version(self, model_id: str) -> Optional[int]:
        return self._load_index(model_id).active_version

    def get_version(self, model_id: str, version: int) -> Dict[str, Any]:
        for record in self._load_index(model_id).versions:
            if int(record["version"]) == int(version):
                return dict(record)
        raise VersionNotFoundError(f"模型 {model_id} 不存在版本 v{version}")

    def definition_of(self, model_id: str, version: int) -> Dict[str, Any]:
        self.get_version(model_id, version)  # 存在性校验
        path = self.definition_path(model_id, version)
        if not path.exists():
            raise VersionNotFoundError(f"版本定义文件缺失: {path}")
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def plan_of(self, model_id: str, version: int) -> Dict[str, Any]:
        self.get_version(model_id, version)
        path = self.plan_path(model_id, version)
        if not path.exists():
            raise VersionNotFoundError(f"版本计划文件缺失: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------ 发布
    def publish(
        self,
        model_id: str,
        definition: Mapping[str, Any],
        plan: Union[Any, Mapping[str, Any]],
        *,
        base_version: Optional[int] = None,
        draft_revision: Optional[int] = None,
        operator: Optional[str] = None,
        draft_repository: Optional[DefinitionRepository] = None,
    ) -> Dict[str, Any]:
        """发布草稿为服务端分配的新版本号；内容不可变、版本号单调递增。"""
        model_id = validate_model_id(model_id)
        if draft_repository is not None:
            draft = draft_repository.load_draft(model_id)
            if draft is not None and (
                draft["base_version"] != base_version or int(draft["draft_revision"]) != int(draft_revision or 0)
            ):
                raise DraftConflictError(
                    "发布被拒绝：草稿 base_version/draft_revision 已变化（§7.6 第3条）"
                )
        plan_payload = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
        plan_hash_value = str(plan_payload.get("plan_hash") or "")
        compiler_version = str(plan_payload.get("compiler_version") or "")
        if not plan_hash_value or not compiler_version:
            raise VersionConflictError("发布需要携带已编译计划的 plan_hash 与 compiler_version")

        index = self._load_index(model_id)
        next_version = max((int(item["version"]) for item in index.versions), default=0) + 1
        definition_file = self.definition_path(model_id, next_version)
        if definition_file.exists():
            raise VersionConflictError(f"版本文件已存在，禁止覆盖: {definition_file}")

        definition_payload = dict(definition)
        record = VersionRecord(
            model_id=model_id,
            version=next_version,
            base_version=base_version,
            status=STATUS_PUBLISHED,
            definition_hash=compute_definition_hash(definition_payload),
            compiler_version=compiler_version,
            plan_hash=plan_hash_value,
            published_at=_now(),
            published_by=operator,
        )
        atomic_write_text(
            definition_file,
            yaml.safe_dump(definition_payload, allow_unicode=True, sort_keys=False),
        )
        atomic_write_text(
            self.plan_path(model_id, next_version),
            json.dumps(plan_payload, ensure_ascii=False, indent=2),
        )
        index.versions.append(record.to_dict())
        self._save_index(model_id, index)
        return record.to_dict()

    # ------------------------------------------------------------ 激活 / 回滚
    def activate(self, model_id: str, version: int, *, operator: Optional[str] = None) -> Dict[str, Any]:
        """激活指定版本；激活旧版本即回滚，只移动指针，不改写历史版本。"""
        model_id = validate_model_id(model_id)
        index = self._load_index(model_id)
        target = self._find(index, version)
        if target["status"] == STATUS_ARCHIVED:
            raise VersionConflictError(f"版本 v{version} 已归档，不能激活")
        previous = index.active_version
        for record in index.versions:
            if record["status"] == STATUS_ACTIVE:
                record["status"] = STATUS_RETIRED
        target["status"] = STATUS_ACTIVE
        target["activated_at"] = _now()
        target["activated_by"] = operator
        index.active_version = int(version)
        index.pointer_revision += 1
        self._save_index(model_id, index)
        atomic_write_text(
            self.active_path(model_id),
            json.dumps(
                {
                    "model_id": model_id,
                    "version": int(version),
                    "previous_version": previous,
                    "pointer_revision": index.pointer_revision,
                    "operator": operator,
                    "updated_at": _now(),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        return {
            "model_id": model_id,
            "version": int(version),
            "previous_version": previous,
            "pointer_revision": index.pointer_revision,
            "operator": operator,
        }

    def rollback(self, model_id: str, version: int, *, operator: Optional[str] = None) -> Dict[str, Any]:
        """回滚 = 重新激活旧版本；语义与 `activate` 完全一致。"""
        return self.activate(model_id, version, operator=operator)

    def archive(self, model_id: str, version: int, *, operator: Optional[str] = None) -> Dict[str, Any]:
        """归档非活动版本；保留全部内容与引用关系，**不物理删除**。"""
        model_id = validate_model_id(model_id)
        index = self._load_index(model_id)
        target = self._find(index, version)
        if target["status"] == STATUS_ACTIVE:
            raise VersionConflictError(f"活动版本 v{version} 不能归档（§7.6 第10条）")
        target["status"] = STATUS_ARCHIVED
        target["archived_by"] = operator
        target["archived_at"] = _now()
        self._save_index(model_id, index)
        return dict(target)

    def active_pointer(self, model_id: str) -> Dict[str, Any]:
        path = self.active_path(model_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _find(index: _Index, version: int) -> Dict[str, Any]:
        for record in index.versions:
            if int(record["version"]) == int(version):
                return record
        raise VersionNotFoundError(f"模型 {index.model_id} 不存在版本 v{version}")


__all__ = [
    "STATUS_ACTIVE",
    "STATUS_ARCHIVED",
    "STATUS_PUBLISHED",
    "STATUS_RETIRED",
    "VALID_STATUSES",
    "VersionConflictError",
    "VersionNotFoundError",
    "VersionRecord",
    "VersionRepository",
]