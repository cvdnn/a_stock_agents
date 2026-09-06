# -*- coding: utf-8 -*-
"""
core.governance.auditor - Skill invocation auditor and runtime metrics collector.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_logger
from core.governance.models import SkillAuditRecord, SkillAuditStats

logger = get_logger("core.governance.auditor")


class SkillAuditor:
    """Auditor responsible for tracking skill executions, latencies, and security metrics."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path
        self._in_memory_logs: List[Dict[str, Any]] = []

    def record_call(
        self,
        skill_id: str,
        action: str,
        status: str,
        latency_ms: int,
        error_message: Optional[str] = None,
        tokens: int = 0,
    ) -> None:
        """Record an execution log entry into SQLite and fallback memory."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            from server.db import record_skill_audit
            record_skill_audit(
                skill_id=skill_id,
                action=action,
                status=status,
                latency_ms=latency_ms,
                error_message=error_message,
                tokens=tokens,
                db_path=self.db_path,
            )
        except Exception as exc:
            logger.warning(f"Could not persist skill audit to SQLite: {exc}. Using in-memory fallback.")
            self._in_memory_logs.append({
                "skill_id": skill_id,
                "action": action,
                "status": status,
                "latency_ms": latency_ms,
                "error_message": error_message,
                "tokens": tokens,
                "created_at": now_iso,
            })

    def get_stats(self) -> SkillAuditStats:
        """Retrieve aggregated metrics from SQLite or in-memory fallback."""
        try:
            from server.db import get_skill_audit_stats
            data = get_skill_audit_stats(db_path=self.db_path)
            return SkillAuditStats(**data)
        except Exception as exc:
            logger.warning(f"Could not read audit stats from SQLite: {exc}. Computing from memory.")
            total = len(self._in_memory_logs)
            success = sum(1 for x in self._in_memory_logs if x["status"] == "success")
            error = total - success
            avg_lat = sum(x["latency_ms"] for x in self._in_memory_logs) / total if total > 0 else 0.0
            lats = sorted(x["latency_ms"] for x in self._in_memory_logs)
            p95 = lats[int(total * 0.95)] if total > 0 else 0
            by_skill: Dict[str, Dict[str, Any]] = {}
            for item in self._in_memory_logs:
                sid = item["skill_id"]
                if sid not in by_skill:
                    by_skill[sid] = {"total_calls": 0, "success_count": 0, "error_count": 0, "avg_latency_ms": 0.0, "last_called_at": ""}
                by_skill[sid]["total_calls"] += 1
                if item["status"] == "success":
                    by_skill[sid]["success_count"] += 1
                else:
                    by_skill[sid]["error_count"] += 1
                by_skill[sid]["last_called_at"] = item["created_at"]

            return SkillAuditStats(
                total_calls=total,
                today_calls=total,
                success_count=success,
                error_count=error,
                error_rate=round(error / total, 4) if total > 0 else 0.0,
                avg_latency_ms=round(avg_lat, 1),
                p95_latency_ms=p95,
                by_skill=by_skill,
            )


# Default module-level auditor
default_auditor = SkillAuditor()
