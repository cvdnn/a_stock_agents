# -*- coding: utf-8 -*-
"""Signal Latch：`converge_at_window_end` 窗口收敛锁存（B3 / §9.2、§10.5、§22.1）。

锁存语义（强制）：

- 幂等键 = `signal-latch:<model_id>:<model_version>:<signal_trade_date>:<code>`（§10.5）；
- **窗口内**命中只记 `pending`（待定候选），不占用终态、不派发信号；
- **窗口结束**（如 09:40）一次性收敛，pending → `latched`，成为**唯一终态**；
- 收敛后同一键再次命中**不得丢弃该次结果**，而是向既有锁存记录追加 `latched_by_run_id`，
  保持终态为 `latched`、审计链不断裂；
- 窗口内重复命中同一 run_id 去重；不同 run 追加不覆盖。

状态落 `output/cache/selection-models/<signal_date>/<model_id>.v<version>.latch.json`（§13.10）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.selection_models.definition_repository import atomic_write_text, validate_model_id
from core.selection_models.paths import CACHE_ROOT, latch_path

STATUS_PENDING = "pending"
STATUS_LATCHED = "latched"


def minute_of(value: str) -> int:
    """`HH:MM` → 自 00:00 起的分钟数（用于窗口端点闭区间比较）。"""
    text = str(value)[:5]
    return int(text[:2]) * 60 + int(text[3:])


class SignalLatch:
    """按 `(model_id, model_version, signal_trade_date)` 组织的信号锁存。"""

    def __init__(self, *, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else CACHE_ROOT

    # ------------------------------------------------------------ 存储
    def latch_file(self, model_id: str, model_version: int, signal_trade_date: str) -> Path:
        return latch_path(model_id, int(model_version), signal_trade_date, root=self.root)

    def _load(self, model_id: str, model_version: int, signal_trade_date: str) -> Dict[str, Any]:
        path = self.latch_file(model_id, model_version, signal_trade_date)
        if not path.is_file():
            return {
                "model_id": model_id,
                "model_version": int(model_version),
                "signal_trade_date": signal_trade_date,
                "window_end": None,
                "entries": {},
            }
        import json

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("model_id", model_id)
        data.setdefault("model_version", int(model_version))
        data.setdefault("signal_trade_date", signal_trade_date)
        data.setdefault("window_end", None)
        data.setdefault("entries", {})
        return data

    def _save(self, model_id: str, model_version: int, signal_trade_date: str, data: Dict[str, Any]) -> Path:
        import json

        path = self.latch_file(model_id, model_version, signal_trade_date)
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
        return path

    # ------------------------------------------------------------ 窗口内
    def register_pending(
        self,
        model_id: str,
        model_version: int,
        signal_trade_date: str,
        *,
        run_id: str,
        codes: Iterable[str],
        window_end: Optional[str] = None,
        hit_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """窗口内命中：写入/追加 `pending` 记录；已锁存则追加 `latched_by_run_id`（不改终态）。"""
        model_id = validate_model_id(model_id)
        data = self._load(model_id, model_version, signal_trade_date)
        if window_end:
            data["window_end"] = str(window_end)
        entries: Dict[str, Any] = data["entries"]
        touched: List[str] = []
        for raw_code in codes:
            code = str(raw_code)
            if not code:
                continue
            entry = entries.get(code)
            if entry is None:
                entries[code] = {
                    "code": code,
                    "status": STATUS_PENDING,
                    "first_hit_at": hit_at,
                    "window_end": data.get("window_end"),
                    "latched_at": None,
                    "latched_by_run_id": [str(run_id)],
                }
            else:
                runs = entry.setdefault("latched_by_run_id", [])
                if str(run_id) not in runs:
                    runs.append(str(run_id))
            touched.append(code)
        self._save(model_id, model_version, signal_trade_date, data)
        return self.summary(model_id, model_version, signal_trade_date)

    def converge(
        self,
        model_id: str,
        model_version: int,
        signal_trade_date: str,
        *,
        now: Optional[str] = None,
        window_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """窗口结束收敛：`now >= window_end` 时把全部 pending 升为唯一终态 `latched`。"""
        model_id = validate_model_id(model_id)
        data = self._load(model_id, model_version, signal_trade_date)
        end = window_end or data.get("window_end")
        if end is not None and now is not None and minute_of(now) < minute_of(end):
            result = self.summary(model_id, model_version, signal_trade_date)
            result["converged"] = False
            result["reason"] = "WINDOW_NOT_CLOSED"
            return result
        for entry in data["entries"].values():
            if entry.get("status") == STATUS_PENDING:
                entry["status"] = STATUS_LATCHED
                entry["latched_at"] = now
        self._save(model_id, model_version, signal_trade_date, data)
        result = self.summary(model_id, model_version, signal_trade_date)
        result["converged"] = True
        return result

    # ------------------------------------------------------------ 查询
    def latched_codes(self, model_id: str, model_version: int, signal_trade_date: str) -> List[str]:
        data = self._load(validate_model_id(model_id), model_version, signal_trade_date)
        return sorted(
            code for code, entry in data["entries"].items() if entry.get("status") == STATUS_LATCHED
        )

    def status(self, model_id: str, model_version: int, signal_trade_date: str, code: str) -> Optional[str]:
        data = self._load(validate_model_id(model_id), model_version, signal_trade_date)
        entry = data["entries"].get(str(code))
        return entry.get("status") if entry else None

    def latched_by(self, model_id: str, model_version: int, signal_trade_date: str, code: str) -> List[str]:
        data = self._load(validate_model_id(model_id), model_version, signal_trade_date)
        entry = data["entries"].get(str(code)) or {}
        return list(entry.get("latched_by_run_id") or [])

    def summary(self, model_id: str, model_version: int, signal_trade_date: str) -> Dict[str, Any]:
        data = self._load(validate_model_id(model_id), model_version, signal_trade_date)
        pending = sorted(c for c, e in data["entries"].items() if e.get("status") == STATUS_PENDING)
        latched = sorted(c for c, e in data["entries"].items() if e.get("status") == STATUS_LATCHED)
        return {
            "model_id": data["model_id"],
            "model_version": data["model_version"],
            "signal_trade_date": data["signal_trade_date"],
            "window_end": data.get("window_end"),
            "pending_codes": pending,
            "latched_codes": latched,
        }


__all__ = ["STATUS_LATCHED", "STATUS_PENDING", "SignalLatch", "minute_of"]