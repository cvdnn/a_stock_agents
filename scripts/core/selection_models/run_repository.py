# -*- coding: utf-8 -*-
"""运行仓库：当日可恢复状态、运行元数据、候选/信号落盘与淘汰（B4/B6 / O-04 / §13.10）。

职责：

1. **当日状态持久化与按交易日重建**（O-04 / 发布门禁 6）：
   幂等键集合（已执行层级）、已触发阶段、已锁存信号随运行元数据落
   `output/cache/selection-models/<signal_date>/`；进程重启后按**当前交易日**重建，
   跨日快照一律标记过期、**不恢复**（避免把昨天的执行状态误当今天）；
2. **运行元数据落盘**（T-03）：每次运行写 `<run_id>/run.json`，多模型多次运行互不覆盖；
3. **候选与信号落盘**：`output/pools/selection-models/<signal_date>/`；
4. **淘汰**（D-18）：普通运行切片保留 90 天；**信号关联切片**额外保留（先删无信号关联，
   再删最旧）。

本模块只做持久化，不解释规则、不产出选股结论；写入一律原子替换，禁止半写状态被读到。
"""
from __future__ import annotations

import json
from datetime import date as _date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.selection_models.definition_repository import atomic_write_text, validate_model_id
from core.selection_models.paths import (
    CACHE_ROOT,
    POOLS_ROOT,
    RUN_CANDIDATES_FILE,
    RUN_META_FILE,
    RUN_STAGES_FILE,
    RUN_STATE_FILE,
    pools_dir,
    run_candidates_path,
    run_dir,
    run_meta_path,
    run_stages_path,
    signal_date_dir,
    state_path,
)

#: 普通运行切片的默认保留天数（D-18）。
DEFAULT_RETENTION_DAYS = 90


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _fresh_state(model_id: str, trade_date: str) -> Dict[str, Any]:
    return {
        "model_id": model_id,
        "trade_date": trade_date,
        "executed_keys": [],
        "stages": {},
        "signal_codes": [],
        "updated_at": None,
    }


class RunRepository:
    """按交易日组织的运行状态与运行元数据仓库。"""

    def __init__(
        self,
        *,
        cache_root: Optional[Path] = None,
        pools_root: Optional[Path] = None,
    ) -> None:
        self.cache_root = Path(cache_root) if cache_root else CACHE_ROOT
        self.pools_root = Path(pools_root) if pools_root else POOLS_ROOT

    # ------------------------------------------------------------ 当日状态
    def state_file(self, model_id: str, trade_date: str) -> Path:
        return state_path(model_id, trade_date, root=self.cache_root)

    def load_state(self, model_id: str, trade_date: str) -> Dict[str, Any]:
        """读取指定交易日的可恢复状态；跨日快照标记过期且**不恢复**（O-04）。"""
        model_id = validate_model_id(model_id)
        path = self.state_file(model_id, trade_date)
        if not path.is_file():
            state = _fresh_state(model_id, trade_date)
            # 跨日快照标记过期、不恢复（O-04 / 发布门禁 6）
            stale_from = self._latest_state_trade_date(model_id)
            if stale_from is not None:
                state["expired_snapshot_from"] = stale_from
            return state
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _fresh_state(model_id, trade_date)
        if str(stored.get("trade_date")) != str(trade_date):
            # 跨交易日：旧状态标记过期，不恢复到当前交易日
            state = _fresh_state(model_id, trade_date)
            state["expired_snapshot_from"] = stored.get("trade_date")
            return state
        state = _fresh_state(model_id, trade_date)
        state["executed_keys"] = [str(item) for item in stored.get("executed_keys") or []]
        state["stages"] = dict(stored.get("stages") or {})
        state["signal_codes"] = [str(item) for item in stored.get("signal_codes") or []]
        state["updated_at"] = stored.get("updated_at")
        return state

    def _latest_state_trade_date(self, model_id: str) -> Optional[str]:
        """扫描该模型已落盘状态文件，返回其它交易日的最近交易日（用于跨日过期标记）。"""
        root = Path(self.cache_root)
        if not root.is_dir():
            return None
        latest: Optional[str] = None
        for path in root.glob(f"*/{validate_model_id(model_id)}.state.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            day = payload.get("trade_date")
            if day and (latest is None or str(day) > latest):
                latest = str(day)
        return latest

    def save_state(self, model_id: str, trade_date: str, state: Dict[str, Any]) -> Path:
        model_id = validate_model_id(model_id)
        payload = _fresh_state(model_id, trade_date)
        payload["executed_keys"] = list(dict.fromkeys(str(item) for item in state.get("executed_keys") or []))
        payload["stages"] = dict(state.get("stages") or {})
        payload["signal_codes"] = list(dict.fromkeys(str(item) for item in state.get("signal_codes") or []))
        payload["updated_at"] = _now()
        target = self.state_file(model_id, trade_date)
        atomic_write_text(target, json.dumps(payload, ensure_ascii=False, indent=2))
        return target

    def is_marked(self, model_id: str, trade_date: str, key: str) -> bool:
        return str(key) in self.load_state(model_id, trade_date)["executed_keys"]

    def mark_once(self, model_id: str, trade_date: str, key: str) -> bool:
        """分层幂等键落盘：首次写入返回 True，重复写入返回 False（同分钟重复 Tick 去重）。

        写入为「读-改-写」；调用方须在运行锁保护下执行，保证多进程互斥（§10.5）。
        """
        state = self.load_state(model_id, trade_date)
        key = str(key)
        if key in state["executed_keys"]:
            return False
        state["executed_keys"].append(key)
        self.save_state(model_id, trade_date, state)
        return True

    def record_stage(self, model_id: str, trade_date: str, stage_id: str, payload: Dict[str, Any]) -> None:
        state = self.load_state(model_id, trade_date)
        state["stages"][str(stage_id)] = dict(payload)
        for code in payload.get("signal_codes") or []:
            if str(code) not in state["signal_codes"]:
                state["signal_codes"].append(str(code))
        self.save_state(model_id, trade_date, state)

    # ------------------------------------------------------------ 运行元数据
    def save_run(self, payload: Dict[str, Any]) -> Path:
        """写入单次运行元数据 `<run_id>/run.json`；多模型多次运行互不覆盖（门禁 18）。"""
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("save_run 需要 run_id")
        target = run_meta_path(run_id, root=self.cache_root)
        body = {"created_at": payload.get("created_at") or _now(), **dict(payload)}
        atomic_write_text(target, json.dumps(body, ensure_ascii=False, indent=2))
        return target

    def load_run(self, run_id: str) -> Dict[str, Any]:
        path = run_meta_path(run_id, root=self.cache_root)
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def update_run(self, run_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """就地更新运行元数据（写前读-改-写）；用于取消标记与终态回填。"""
        current = self.load_run(run_id)
        if not current:
            return {}
        current.update({key: value for key, value in dict(patch).items() if value is not None})
        self.save_run(current)
        return current

    def list_runs(
        self,
        model_id: str,
        *,
        version: Optional[int] = None,
        status: Optional[str] = None,
        trigger_type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """列出某模型运行实例，按 `started_at` 倒序；可按版本/状态/触发方式过滤并分页。"""
        model_id = validate_model_id(model_id)
        runs: List[Dict[str, Any]] = []
        root = Path(self.cache_root)
        if not root.is_dir():
            return runs
        for meta in root.glob(f"*/{RUN_META_FILE}"):
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if str(payload.get("model_id")) != model_id:
                continue
            if version is not None and int(payload.get("model_version") or 0) != int(version):
                continue
            if status and str(payload.get("status") or "") != str(status):
                continue
            if trigger_type and str(payload.get("trigger_type") or "") != str(trigger_type):
                continue
            runs.append(payload)
        runs.sort(key=lambda item: str(item.get("started_at") or item.get("created_at") or ""), reverse=True)
        start = max(int(offset), 0)
        end = start + int(limit) if limit is not None else None
        return runs[start:end] if end is not None else runs[start:]

    # ------------------------------------------------------------ 阶段与候选轨迹
    def save_run_stages(self, run_id: str, stages: Iterable[Dict[str, Any]]) -> Path:
        """逐阶段明细落 `<run_id>/stages.json`；与运行元数据同目录、互不覆盖。"""
        target = run_stages_path(run_id, root=self.cache_root)
        atomic_write_text(
            target,
            json.dumps({"run_id": str(run_id), "stages": [dict(item) for item in stages]},
                       ensure_ascii=False, indent=2),
        )
        return target

    def load_run_stages(self, run_id: str) -> List[Dict[str, Any]]:
        path = run_stages_path(run_id, root=self.cache_root)
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return list(payload.get("stages") or [])

    def save_run_candidates(self, run_id: str, candidates: Iterable[Dict[str, Any]]) -> Path:
        """候选轨迹落 `<run_id>/candidates.json`（逐股淘汰原因与入选证据）。"""
        target = run_candidates_path(run_id, root=self.cache_root)
        atomic_write_text(
            target,
            json.dumps({"run_id": str(run_id), "candidates": [dict(item) for item in candidates]},
                       ensure_ascii=False, indent=2),
        )
        return target

    def load_run_candidates(self, run_id: str) -> List[Dict[str, Any]]:
        path = run_candidates_path(run_id, root=self.cache_root)
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return list(payload.get("candidates") or [])

    # ------------------------------------------------------------ 正式信号
    def save_signals(self, signal_date: str, model_id: str, payload: Dict[str, Any]) -> Path:
        """最终正式信号落 `output/pools/selection-models/<date>/<model>.signals.json`。"""
        model_id = validate_model_id(model_id)
        target = pools_dir(signal_date, root=self.pools_root) / f"{model_id}.signals.json"
        atomic_write_text(target, json.dumps(dict(payload), ensure_ascii=False, indent=2))
        return target

    def load_signals(self, signal_date: str, model_id: str) -> Dict[str, Any]:
        path = pools_dir(signal_date, root=self.pools_root) / f"{validate_model_id(model_id)}.signals.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def query_signals(
        self,
        *,
        model_id: Optional[str] = None,
        signal_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询正式信号（按模型/交易日过滤），来自落盘候选与信号文件，不合成任何数值。"""
        root = Path(self.pools_root)
        if not root.is_dir():
            return []
        results: List[Dict[str, Any]] = []
        dates = [str(signal_date)] if signal_date else self.signal_dates()
        for day in dates:
            day_dir = pools_dir(day, root=self.pools_root)
            if not day_dir.is_dir():
                continue
            for path in sorted(day_dir.glob("*.json")):
                name = path.stem
                if model_id and not name.startswith(f"{model_id}."):
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                payload = dict(payload)
                payload.setdefault("signal_trade_date", day)
                payload["source_file"] = path.name
                results.append(payload)
        return results

    # ------------------------------------------------------------ 候选与信号
    def save_candidates(self, signal_date: str, model_id: str, payload: Dict[str, Any]) -> Path:
        model_id = validate_model_id(model_id)
        target = pools_dir(signal_date, root=self.pools_root) / f"{model_id}.candidates.json"
        atomic_write_text(target, json.dumps(dict(payload), ensure_ascii=False, indent=2))
        return target

    def load_candidates(self, signal_date: str, model_id: str) -> Dict[str, Any]:
        path = pools_dir(signal_date, root=self.pools_root) / f"{validate_model_id(model_id)}.candidates.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def signal_dates(self) -> List[str]:
        """已存在候选/信号文件的交易日集合（信号关联切片，淘汰时受保护）。"""
        root = Path(self.pools_root)
        if not root.is_dir():
            return []
        dates = {path.parent.name for path in root.glob("*/*.candidates.json")}
        dates |= {path.parent.name for path in root.glob("*/*.signals.json")}
        return sorted(dates)

    # ------------------------------------------------------------ 淘汰（D-18）
    def prune(
        self,
        *,
        cutoff_days: int = DEFAULT_RETENTION_DAYS,
        today: Optional[str] = None,
        protected_dates: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """淘汰超过保留期的**无信号关联**切片；信号关联切片受保护。

        保护集合 = 显式 `protected_dates` ∪ 已有候选/信号文件的交易日（先删无信号关联，
        再删最旧）。返回被删除的目录清单，不触碰 `output/` 之外任何路径。
        """
        anchor = _date.fromisoformat(str(today)[:10]) if today else datetime.now().date()
        cutoff = anchor - timedelta(days=max(int(cutoff_days), 0))
        protected = set(str(item) for item in (protected_dates or ())) | set(self.signal_dates())
        removed: List[str] = []
        root = Path(self.cache_root)
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                name = child.name
                try:
                    child_date = _date.fromisoformat(name)
                except ValueError:
                    # 非日期命名的 <run_id> 目录：按 mtime 判定，不误删当日运行
                    mtime = _date.fromtimestamp(child.stat().st_mtime)
                    if mtime < cutoff:
                        _remove_tree(child)
                        removed.append(str(child))
                    continue
                if name in protected or child_date >= cutoff:
                    continue
                _remove_tree(child)
                removed.append(str(child))
        return {"cutoff": cutoff.isoformat(), "protected": sorted(protected), "removed": removed}


def _remove_tree(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_dir():
            child.rmdir()
        else:
            child.unlink(missing_ok=True)
    path.rmdir()


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "RUN_CANDIDATES_FILE",
    "RUN_META_FILE",
    "RUN_STAGES_FILE",
    "RUN_STATE_FILE",
    "RunRepository",
    "signal_date_dir",
    "run_dir",
]