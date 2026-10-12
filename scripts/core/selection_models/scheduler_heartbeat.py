# -*- coding: utf-8 -*-
"""Per-model daemon Tick heartbeat. A recent file is evidence, not a process guarantee."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from core.selection_models.definition_repository import atomic_write_text, validate_model_id
from core.selection_models import run_repository


class SchedulerHeartbeatStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else run_repository.CACHE_ROOT

    def path(self, model_id: str) -> Path:
        return self.root / "daemon-heartbeats" / f"{validate_model_id(model_id)}.json"

    def load(self, model_id: str) -> dict[str, Any]:
        path = self.path(model_id)
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}

    def record_tick(self, result: Mapping[str, Any]) -> dict[str, Any]:
        model_id = validate_model_id(str(result["model_id"]))
        previous = self.load(model_id)
        executed = result.get("executed") or []
        actual = [item for item in executed if item.get("status") not in {"IDEMPOTENT_SKIP", "LOCK_CONTENDED"}]
        failed = next((item for item in actual if item.get("status") in {"FAILED", "WAITING_DATA"}), None)
        heartbeat = result.get("heartbeat") or {}
        payload = {
            "model_id": model_id,
            "model_version": result.get("model_version"),
            "tick_at": heartbeat.get("tick_at"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "tick_status": result.get("status"),
            "last_execution_at": heartbeat.get("tick_at") if actual else (
                previous.get("last_execution_at") if previous.get("model_version") == result.get("model_version") else None),
            "last_error": (failed.get("reason_code") or failed.get("error") or failed.get("status")) if failed else None,
            "next_run_at": result.get("next_run_at"),
        }
        atomic_write_text(self.path(model_id), json.dumps(payload, ensure_ascii=False, indent=2))
        return payload
