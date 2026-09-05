# -*- coding: utf-8 -*-
"""
监控状态持久化与单日信号去重管理器 (State Store & Deduplicator)

统一处理:
1. JSON 状态文件的安全读取与格式化保存
2. 单日 (或自定义时窗) 信号触发去重，避免重复轰炸与重复预警
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union


def load_state(
    path: Union[str, Path],
    default: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """安全读取监控状态 JSON 文件，若不存在或损坏则返回默认字典。"""
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    if default is not None:
        return dict(default)
    return {"triggered": {}}


def save_state(path: Union[str, Path], state: Dict[str, Any]) -> None:
    """原子/安全写入监控状态 JSON 文件，自动递归创建父级目录。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


class StateDeduplicator:
    """单日监控信号触发去重控制器"""

    def __init__(self, state_path: Union[str, Path], auto_save: bool = True):
        self.state_path = Path(state_path)
        self.auto_save = auto_save
        self.state = load_state(self.state_path)
        if "triggered" not in self.state or not isinstance(self.state["triggered"], dict):
            self.state["triggered"] = {}

    def is_triggered(self, key: str, date: Optional[str] = None) -> bool:
        """检查指定 key (如 股票代码、触发事件名) 在指定日期是否已触发。"""
        d = date or datetime.now().strftime("%Y-%m-%d")
        record = self.state["triggered"].get(key)
        if isinstance(record, dict):
            return record.get("date") == d
        elif isinstance(record, str):
            return record == d
        return False

    def should_fire(
        self,
        key: str,
        action: str = "",
        date: Optional[str] = None,
        today: Optional[str] = None,
    ) -> bool:
        """判断指定 key 和 action 在当日是否应当触发 (即未触发过)。"""
        full_key = f"{key}_{action}" if action else key
        target_date = today or date
        return not self.is_triggered(full_key, date=target_date)

    def record(
        self,
        key: str,
        date: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录指定 key 的触发状态。"""
        d = date or datetime.now().strftime("%Y-%m-%d")
        val: Dict[str, Any] = {"date": d, "time": datetime.now().strftime("%H:%M:%S")}
        if extra:
            val.update(extra)
        self.state["triggered"][key] = val
        if self.auto_save:
            self.save()

    def record_fire(
        self,
        key: str,
        action: str = "",
        date: Optional[str] = None,
        today: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录指定 key 和 action 在当日已被触发。"""
        full_key = f"{key}_{action}" if action else key
        target_date = today or date
        self.record(full_key, date=target_date, extra=extra)

    def clear(self) -> None:
        """清空所有记录。"""
        self.state["triggered"] = {}
        if self.auto_save:
            self.save()

    def save(self) -> None:
        """保存状态至文件。"""
        save_state(self.state_path, self.state)



__all__ = ["load_state", "save_state", "StateDeduplicator"]
