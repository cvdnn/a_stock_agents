# -*- coding: utf-8 -*-
"""ISS 落盘目录规范（B6 / SSOT §13.10）。

工作区三桶纪律（AGENTS.md）在选股系统的映射：

```
output/config/selection-models/                  用户模型版本（不可变定义/计划/活动指针）
output/cache/selection-models/<signal_date>/     可恢复运行状态与采样缓存
output/cache/selection-models/<run_id>/inputs/    实际输入切片、快照清单与内容哈希
output/pools/selection-models/<signal_date>/     最终候选与信号
output/backtest/selection-models/                回测结果（二期）
output/reports/selection-models/                 个股评估与模型评价报告（二期）
output/cache/selection-models/tracking/          可恢复跟踪状态与观察缓存（二期）
log/selection-models/<date>/                     调度、数据、阶段与审计日志
temp/selection-models/                           原子写临时文件与锁文件，结束后清理
```

本模块是上述路径的**唯一派生点**：所有运行期读写必须经由此处，禁止在其它模块硬编码
绝对路径或自行拼接相对路径（AGENTS.md §工作区输出目录规范）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from core.workspace import LOG_DIR, OUTPUT_DIR, TEMP_DIR

CONFIG_ROOT: Path = OUTPUT_DIR / "config" / "selection-models"
CACHE_ROOT: Path = OUTPUT_DIR / "cache" / "selection-models"
POOLS_ROOT: Path = OUTPUT_DIR / "pools" / "selection-models"
BACKTEST_ROOT: Path = OUTPUT_DIR / "backtest" / "selection-models"
REPORTS_ROOT: Path = OUTPUT_DIR / "reports" / "selection-models"
LOG_ROOT: Path = LOG_DIR / "selection-models"
TEMP_ROOT: Path = TEMP_DIR / "selection-models"

#: 运行状态文件（当日可恢复状态：幂等键、已触发阶段、已发信号）
RUN_STATE_FILE = "run-state.json"
#: 运行元数据文件（含配置快照哈希、模型版本、触发来源）
RUN_META_FILE = "run.json"
#: 运行阶段明细文件（逐阶段输入/输出/淘汰证据）
RUN_STAGES_FILE = "stages.json"
#: 运行候选轨迹文件（逐股淘汰原因与最终入选证据）
RUN_CANDIDATES_FILE = "candidates.json"
#: 锁文件子目录（与 T-07 草稿锁同族，落 temp/，会话结束清理）
LOCK_SUBDIR = "locks"

#: 标识符白名单（§20.2：不接受任意路径，避免目录穿越）
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,96}$")
#: 交易日 / 信号日形态
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PathSpecError(ValueError):
    """路径标识符非法（目录穿越防护，§20.2）。"""

    code = "SELECTION_PATH_INVALID"


def _safe_id(value: str, field: str) -> str:
    candidate = str(value or "").strip()
    if not _ID_PATTERN.match(candidate):
        raise PathSpecError(f"非法 {field}（仅允许字母/数字/._-）：{value!r}")
    return candidate


def _safe_date(value: str, field: str) -> str:
    candidate = str(value or "").strip()[:10]
    if not _DATE_PATTERN.match(candidate):
        raise PathSpecError(f"非法 {field}（需 YYYY-MM-DD）：{value!r}")
    return candidate


def signal_date_dir(signal_date: str, *, root: Optional[Path] = None) -> Path:
    """`output/cache/selection-models/<signal_date>/`（可恢复运行状态与采样缓存）。"""
    return Path(root or CACHE_ROOT) / _safe_date(signal_date, "signal_date")


def run_dir(run_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/cache/selection-models/<run_id>/`（单次运行目录）。"""
    return Path(root or CACHE_ROOT) / _safe_id(run_id, "run_id")


def run_inputs_dir(run_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/cache/selection-models/<run_id>/inputs/`（实际输入切片与快照清单）。"""
    return run_dir(run_id, root=root) / "inputs"


def run_meta_path(run_id: str, *, root: Optional[Path] = None) -> Path:
    return run_dir(run_id, root=root) / RUN_META_FILE


def run_stages_path(run_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/cache/selection-models/<run_id>/stages.json`（逐阶段明细）。"""
    return run_dir(run_id, root=root) / RUN_STAGES_FILE


def run_candidates_path(run_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/cache/selection-models/<run_id>/candidates.json`（逐股候选轨迹）。"""
    return run_dir(run_id, root=root) / RUN_CANDIDATES_FILE


def state_path(model_id: str, signal_date: str, *, root: Optional[Path] = None) -> Path:
    """当日状态文件：`<signal_date>/<model_id>.state.json`。"""
    return signal_date_dir(signal_date, root=root) / f"{_safe_id(model_id, 'model_id')}.state.json"


def latch_path(model_id: str, version: int, signal_date: str, *, root: Optional[Path] = None) -> Path:
    """信号锁存文件：`<signal_date>/<model_id>.v<version>.latch.json`。"""
    return signal_date_dir(signal_date, root=root) / (
        f"{_safe_id(model_id, 'model_id')}.v{int(version)}.latch.json"
    )


def pools_dir(signal_date: str, *, root: Optional[Path] = None) -> Path:
    """`output/pools/selection-models/<signal_date>/`（最终候选与信号）。"""
    return Path(root or POOLS_ROOT) / _safe_date(signal_date, "signal_date")


def tracking_dir(*, root: Optional[Path] = None) -> Path:
    return Path(root or CACHE_ROOT) / "tracking"


#: 跟踪计划目录名（`output/cache/selection-models/tracking/<tracking_id>/`）。
TRACKING_PLAN_FILE = "plan.json"
TRACKING_OBSERVATIONS_FILE = "observations.json"


def tracking_plan_dir(tracking_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/cache/selection-models/tracking/<tracking_id>/`（跟踪计划与观察缓存）。"""
    return tracking_dir(root=root) / _safe_id(tracking_id, "tracking_id")


def tracking_plan_path(tracking_id: str, *, root: Optional[Path] = None) -> Path:
    return tracking_plan_dir(tracking_id, root=root) / TRACKING_PLAN_FILE


def tracking_observations_path(tracking_id: str, *, root: Optional[Path] = None) -> Path:
    return tracking_plan_dir(tracking_id, root=root) / TRACKING_OBSERVATIONS_FILE


def assessments_dir(run_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/reports/selection-models/assessments/<run_id>/`（逐候选结果研究评估）。"""
    return Path(root or REPORTS_ROOT) / "assessments" / _safe_id(run_id, "run_id")


def assessment_path(run_id: str, *, root: Optional[Path] = None) -> Path:
    return assessments_dir(run_id, root=root) / "assessments.json"


def evaluation_dir(model_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/reports/selection-models/evaluations/<model_id>/`（模型评价记录）。"""
    return Path(root or REPORTS_ROOT) / "evaluations" / _safe_id(model_id, "model_id")


def evaluation_path(model_id: str, evaluation_id: str, *, root: Optional[Path] = None) -> Path:
    return evaluation_dir(model_id, root=root) / f"{_safe_id(evaluation_id, 'evaluation_id')}.json"


def backtest_dir(run_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/backtest/selection-models/<run_id>/`（逐候选回测结果）。"""
    return Path(root or BACKTEST_ROOT) / _safe_id(run_id, "run_id")


def backtest_path(run_id: str, code: str, *, root: Optional[Path] = None) -> Path:
    return backtest_dir(run_id, root=root) / f"{_safe_id(code, 'code')}.json"


def suggestions_path(model_id: str, *, root: Optional[Path] = None) -> Path:
    """`output/reports/selection-models/suggestions/<model_id>.json`（只读优化建议）。"""
    return Path(root or REPORTS_ROOT) / "suggestions" / f"{_safe_id(model_id, 'model_id')}.json"


def log_dir(date: str, *, root: Optional[Path] = None) -> Path:
    """`log/selection-models/<date>/`（调度、数据、阶段与审计日志）。"""
    return Path(root or LOG_ROOT) / _safe_date(date, "date")


def lock_dir(*, root: Optional[Path] = None) -> Path:
    return Path(root or TEMP_ROOT) / LOCK_SUBDIR


__all__ = [
    "BACKTEST_ROOT",
    "CACHE_ROOT",
    "CONFIG_ROOT",
    "LOCK_SUBDIR",
    "LOG_ROOT",
    "POOLS_ROOT",
    "REPORTS_ROOT",
    "RUN_META_FILE",
    "RUN_CANDIDATES_FILE",
    "RUN_STAGES_FILE",
    "RUN_STATE_FILE",
    "TEMP_ROOT",
    "TRACKING_OBSERVATIONS_FILE",
    "TRACKING_PLAN_FILE",
    "PathSpecError",
    "assessment_path",
    "assessments_dir",
    "backtest_dir",
    "backtest_path",
    "evaluation_dir",
    "evaluation_path",
    "latch_path",
    "lock_dir",
    "log_dir",
    "pools_dir",
    "run_dir",
    "run_inputs_dir",
    "run_meta_path",
    "run_candidates_path",
    "run_stages_path",
    "signal_date_dir",
    "state_path",
    "suggestions_path",
    "tracking_dir",
    "tracking_observations_path",
    "tracking_plan_dir",
    "tracking_plan_path",
]