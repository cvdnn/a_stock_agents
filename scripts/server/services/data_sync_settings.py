# -*- coding: utf-8 -*-
"""server.services.data_sync_settings - 行情数据同步设置的白名单校验与持久化服务。

契约（SPEC-UI-003 §六 / SSOT §6.2）：
1. 全部设置字段经服务端白名单 + 范围校验后落盘 `local/settings/data_sync.json`；
   路径必须经 workspace.LOCAL_DIR 解析，严禁硬编码绝对路径；
2. 外部行情源优先级与本地 SQLite 数据层是两个相互独立的配置域：
   外部域可编辑排序与启停；本地层为只读派生观测，不参与外部源排序；
3. 无效输入逐项拒绝并回传字段级错误，不静默夹紧、不部分保存；
4. 落盘使用临时文件 + 原子替换，文件权限 0o600（目录 0o700 由 workspace 保障）；
5. 读取到损坏文件时回退默认值，并在响应中如实标注 `persisted_status`，不伪造成功。
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import get_logger
from core.workspace import LOCAL_DIR, PROJECT_ROOT

logger = get_logger("server.data_sync_settings")

ENV_OVERRIDE = "A_STOCK_DATA_SYNC_SETTINGS_FILE"

EXTERNAL_PROVIDERS = ("tencent", "sina", "eastmoney")
_PROVIDER_LABELS = {"tencent": "腾讯", "sina": "新浪", "eastmoney": "东方财富"}
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# ---------------------------------------------------------------------------
# 默认设置（服务端唯一真源；GET 时与持久化文件深合并后返回有效值）
# ---------------------------------------------------------------------------
DEFAULTS: Dict[str, Any] = {
    "base": {
        "mode": "incremental",          # 默认同步模式
        "concurrency": 4,               # 1..16（服务内定盘巡检与批量同步并发）
        "retries": 1,                   # 0..5
        "timeout_seconds": 300,         # 30..1800
    },
    "daemon": {
        "enabled": True,                # 定时守护总开关
        "interval_seconds": 60,         # 15..3600 轮询间隔
        "p0_time": "15:35",             # P0 持仓池定盘时间
        "p1_time": "15:40",             # P1 自选/关注 + P2 指数定盘时间
    },
    "p3": {
        "enabled": True,                # P3 全市场自动增量开关
        "time": "16:00",                # 交易日自动执行时间
        "concurrency": 8,               # 1..16
        "batch_size": 600,              # 50..5000
        "retries": 1,                   # 0..5
    },
    "external_sources": {
        "order": list(EXTERNAL_PROVIDERS),      # 首选顺序（排列）
        "enabled": {p: True for p in EXTERNAL_PROVIDERS},  # 至少保留一个启用
    },
    "integrity": {
        "auto_audit": False,            # 自动完整性审计
        "auto_repair": False,           # 异常缺漏自动回补（合规停牌永不回补，由引擎保证）
    },
    "cooperation": {
        "tdx_target_pool": "watchlist",  # 通达信导入默认目标股池
    },
    # 新工作台的目标配置。已接入的执行参数仍由 base/daemon/p3 等域驱动；
    # 其他目标范围只持久化，不声称当前执行层已支持。
    "workspace": {
        "common": {
            "frequency": "trading_day", "time": "16:30", "mode": "incremental",
            "prioritize_pools": True, "markets": ["sh", "sz", "bj"],
            "datasets": ["basic", "daily", "minute", "factor", "index", "finance", "valuation", "industry"],
            "minute_periods": [1, 5, 15, 30, 60], "minute_days": 30,
        },
        "history": {"start_mode": "listing", "start_date": "", "end_mode": "last_complete", "end_date": "", "skip_complete": True},
        "quality": {
            "audit_when": "after_update", "check_items": ["missing_date", "duplicate", "required"],
            "repair_scope": "abnormal_only", "repair_skip": True,
            "auto_retry": True, "retry_max": 3, "retry_interval_seconds": 60,
        },
        "performance": {
            "primary": "tencent", "backup": "sina", "auto_failover": True,
            "request_interval_ms": 500, "auto_throttle": True,
        },
        "import_rules": {"data_type": "daily", "mode": "missing", "validate_before": True},
    },
}


def settings_file_path() -> Path:
    """设置文件路径：默认 LOCAL_DIR/settings/data_sync.json，测试可用环境变量重定向。"""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser().resolve()
    return LOCAL_DIR / "settings" / "data_sync.json"


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _check_range(errors: List[Dict[str, str]], field: str, value: Any, lo: int, hi: int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append({"field": field, "reason": "必须为整数"})
        return
    if not float(lo) <= float(value) <= float(hi):
        errors.append({"field": field, "reason": f"超出允许范围 {lo}–{hi}"})


def _check_time(errors: List[Dict[str, str]], field: str, value: Any) -> None:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        errors.append({"field": field, "reason": "时间格式必须为 HH:MM（24 小时制）"})


def _check_bool(errors: List[Dict[str, str]], field: str, value: Any) -> None:
    if not isinstance(value, bool):
        errors.append({"field": field, "reason": "必须为布尔值 true/false"})


def _check_choice(errors: List[Dict[str, str]], field: str, value: Any, choices: Tuple[Any, ...]) -> None:
    if value not in choices:
        errors.append({"field": field, "reason": f"必须属于 {list(choices)}"})


def _check_list(errors: List[Dict[str, str]], field: str, value: Any, choices: Tuple[Any, ...]) -> None:
    if not isinstance(value, list) or not value or len(value) != len(set(str(item) for item in value)) or any(item not in choices for item in value):
        errors.append({"field": field, "reason": f"须为非空、无重复的 {list(choices)} 子集"})


def _check_optional_date(errors: List[Dict[str, str]], field: str, value: Any) -> None:
    if not isinstance(value, str):
        errors.append({"field": field, "reason": "日期须为 YYYY-MM-DD 或空值"})
        return
    if value:
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("bad date format")
        except ValueError:
            errors.append({"field": field, "reason": "日期须为 YYYY-MM-DD 或空值"})


def validate_patch(patch: Dict[str, Any]) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """按白名单逐项校验补丁；返回 (字段级错误列表, 合并后的候选设置)。

    白名单外的键一律拒绝；任何一项非法都不做静默修正。
    """
    errors: List[Dict[str, Any]] = []
    if not isinstance(patch, dict):
        return [{"field": "", "reason": "请求体必须为 JSON 对象"}], DEFAULTS

    # 顶层与嵌套白名单
    if not set(patch) <= set(DEFAULTS):
        for key in sorted(set(patch) - set(DEFAULTS)):
            errors.append({"field": key, "reason": "未知配置域，不在白名单内"})

    base = patch.get("base")
    if isinstance(base, dict):
        if not set(base) <= set(DEFAULTS["base"]):
            for key in sorted(set(base) - set(DEFAULTS["base"])):
                errors.append({"field": f"base.{key}", "reason": "未知字段，不在白名单内"})
        if "mode" in base and base["mode"] not in ("incremental", "snapshot"):
            errors.append({"field": "base.mode", "reason": "默认模式仅支持 incremental / snapshot"})
        if "concurrency" in base:
            _check_range(errors, "base.concurrency", base["concurrency"], 1, 16)
        if "retries" in base:
            _check_range(errors, "base.retries", base["retries"], 0, 5)
        if "timeout_seconds" in base:
            _check_range(errors, "base.timeout_seconds", base["timeout_seconds"], 30, 1800)

    daemon = patch.get("daemon")
    if isinstance(daemon, dict):
        if not set(daemon) <= set(DEFAULTS["daemon"]):
            for key in sorted(set(daemon) - set(DEFAULTS["daemon"])):
                errors.append({"field": f"daemon.{key}", "reason": "未知字段，不在白名单内"})
        if "enabled" in daemon:
            _check_bool(errors, "daemon.enabled", daemon["enabled"])
        if "interval_seconds" in daemon:
            _check_range(errors, "daemon.interval_seconds", daemon["interval_seconds"], 15, 3600)
        for time_key in ("p0_time", "p1_time"):
            if time_key in daemon:
                _check_time(errors, f"daemon.{time_key}", daemon[time_key])
        p0 = daemon.get("p0_time")
        p1 = daemon.get("p1_time")
        if _TIME_RE.match(str(p0 or "")) and _TIME_RE.match(str(p1 or "")) and str(p0) > str(p1):
            errors.append({"field": "daemon.p0_time", "reason": "P0 定盘时间不得晚于 P1"})

    p3 = patch.get("p3")
    if isinstance(p3, dict):
        if not set(p3) <= set(DEFAULTS["p3"]):
            for key in sorted(set(p3) - set(DEFAULTS["p3"])):
                errors.append({"field": f"p3.{key}", "reason": "未知字段，不在白名单内"})
        if "enabled" in p3:
            _check_bool(errors, "p3.enabled", p3["enabled"])
        if "time" in p3:
            _check_time(errors, "p3.time", p3["time"])
        if "concurrency" in p3:
            _check_range(errors, "p3.concurrency", p3["concurrency"], 1, 16)
        if "batch_size" in p3:
            _check_range(errors, "p3.batch_size", p3["batch_size"], 50, 5000)
        if "retries" in p3:
            _check_range(errors, "p3.retries", p3["retries"], 0, 5)

    ext = patch.get("external_sources")
    if isinstance(ext, dict):
        if not set(ext) <= set(DEFAULTS["external_sources"]):
            for key in sorted(set(ext) - set(DEFAULTS["external_sources"])):
                errors.append({"field": f"external_sources.{key}", "reason": "未知字段，不在白名单内"})
        if "order" in ext:
            order = ext["order"]
            if not isinstance(order, list) or sorted(str(x) for x in order) != sorted(EXTERNAL_PROVIDERS):
                errors.append({
                    "field": "external_sources.order",
                    "reason": f"必须为 {list(EXTERNAL_PROVIDERS)} 三个供应商的完整排列",
                })
        if "enabled" in ext:
            flags = ext["enabled"]
            if not isinstance(flags, dict) or not set(flags) == set(EXTERNAL_PROVIDERS):
                errors.append({
                    "field": "external_sources.enabled",
                    "reason": "必须同时给出 tencent/sina/eastmoney 三个供应商的布尔启停",
                })
            else:
                for provider, flag in flags.items():
                    _check_bool(errors, f"external_sources.enabled.{provider}", flag)

    integrity = patch.get("integrity")
    if isinstance(integrity, dict):
        if not set(integrity) <= set(DEFAULTS["integrity"]):
            for key in sorted(set(integrity) - set(DEFAULTS["integrity"])):
                errors.append({"field": f"integrity.{key}", "reason": "未知字段，不在白名单内"})
        for bool_key in ("auto_audit", "auto_repair"):
            if bool_key in integrity:
                _check_bool(errors, f"integrity.{bool_key}", integrity[bool_key])

    coop = patch.get("cooperation")
    if isinstance(coop, dict):
        if not set(coop) <= set(DEFAULTS["cooperation"]):
            for key in sorted(set(coop) - set(DEFAULTS["cooperation"])):
                errors.append({"field": f"cooperation.{key}", "reason": "未知字段，不在白名单内"})
        if "tdx_target_pool" in coop and coop["tdx_target_pool"] not in ("watchlist", "focus", "holdings"):
            errors.append({"field": "cooperation.tdx_target_pool", "reason": "目标股池仅支持 watchlist / focus / holdings"})

    workspace = patch.get("workspace")
    if "workspace" in patch and not isinstance(workspace, dict):
        errors.append({"field": "workspace", "reason": "必须为配置对象"})
    elif isinstance(workspace, dict):
        for section, fields in workspace.items():
            if section not in DEFAULTS["workspace"]:
                errors.append({"field": f"workspace.{section}", "reason": "未知设置分组"})
                continue
            if not isinstance(fields, dict):
                errors.append({"field": f"workspace.{section}", "reason": "必须为配置对象"})
                continue
            allowed = DEFAULTS["workspace"][section]
            for key, value in fields.items():
                field = f"workspace.{section}.{key}"
                if key not in allowed:
                    errors.append({"field": field, "reason": "未知字段，不在白名单内"})
                    continue
                if key in ("time",):
                    _check_time(errors, field, value)
                elif key in ("start_date", "end_date"):
                    _check_optional_date(errors, field, value)
                elif key in ("prioritize_pools", "skip_complete", "repair_skip", "auto_retry", "auto_failover", "auto_throttle", "validate_before"):
                    _check_bool(errors, field, value)
                elif key == "markets":
                    _check_list(errors, field, value, ("sh", "sz", "bj"))
                elif key == "datasets":
                    _check_list(errors, field, value, ("basic", "daily", "minute", "factor", "index", "finance", "valuation", "industry"))
                elif key == "minute_periods":
                    _check_list(errors, field, value, (1, 5, 15, 30, 60))
                elif key == "check_items":
                    _check_list(errors, field, value, ("missing_date", "duplicate", "required"))
                elif key in ("minute_days", "retry_max", "retry_interval_seconds", "request_interval_ms"):
                    limits = {"minute_days": (5, 60), "retry_max": (0, 5), "retry_interval_seconds": (30, 300), "request_interval_ms": (0, 1000)}
                    if isinstance(value, bool) or not isinstance(value, int) or not limits[key][0] <= value <= limits[key][1]:
                        errors.append({"field": field, "reason": f"必须为 {limits[key][0]}–{limits[key][1]} 的整数"})
                else:
                    enums = {
                        "frequency": ("trading_day",), "mode": (("missing", "overwrite") if section == "import_rules" else ("incremental", "history")),
                        "start_mode": ("listing", "custom"), "end_mode": ("last_complete", "custom"),
                        "audit_when": ("after_update", "manual"), "repair_scope": ("abnormal_only", "all_missing"),
                        "primary": EXTERNAL_PROVIDERS, "backup": EXTERNAL_PROVIDERS,
                        "data_type": ("daily", "minute", "factor"),
                    }
                    _check_choice(errors, field, value, enums.get(key, (allowed[key],)))
        history = workspace.get("history")
        if isinstance(history, dict):
            if history.get("start_mode") == "custom" and not history.get("start_date"):
                errors.append({"field": "workspace.history.start_date", "reason": "自定义起始范围必须填写日期"})
            if history.get("end_mode") == "custom" and not history.get("end_date"):
                errors.append({"field": "workspace.history.end_date", "reason": "自定义结束范围必须填写日期"})
            if history.get("start_date") and history.get("end_date") and str(history["start_date"]) > str(history["end_date"]):
                errors.append({"field": "workspace.history.end_date", "reason": "结束日期不得早于起始日期"})
        performance = workspace.get("performance")
        if isinstance(performance, dict) and performance.get("primary") and performance.get("primary") == performance.get("backup"):
            errors.append({"field": "workspace.performance.backup", "reason": "备用数据源应不同于首选数据源"})

    # 合并后再验"至少保留一个可用外部数据源"（对候选有效值判定，而非仅补丁）
    candidate = effective_settings() if errors else _deep_merge(effective_settings(), patch)
    if isinstance(ext, dict) or "external_sources" in patch:
        enabled_map = (candidate.get("external_sources") or {}).get("enabled") or {}
        if ext and isinstance(ext.get("enabled"), dict) and not any(
            enabled_map.get(p) is True for p in EXTERNAL_PROVIDERS
        ):
            errors.append({"field": "external_sources.enabled", "reason": "至少保留一个可用外部数据源"})

    return errors, candidate


# ---------------------------------------------------------------------------
# 持久化与有效值
# ---------------------------------------------------------------------------
_WRITE_LOCK = threading.Lock()


def read_persisted() -> Tuple[Optional[Dict[str, Any]], str]:
    """读取持久化文件。返回 (数据或 None, 状态):
    ok=正常；missing=尚未保存过；corrupt=文件损坏（调用方应回退默认值并如实标注）。"""
    path = settings_file_path()
    if not path.is_file():
        return None, "missing"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return None, "corrupt"
        # 仅采纳白名单内结构，损坏/注入字段直接丢弃但保留文件可诊断
        return {k: v for k, v in data.items() if k in DEFAULTS}, "ok"
    except (OSError, ValueError):
        return None, "corrupt"


def effective_settings() -> Dict[str, Any]:
    """服务端默认值与持久化值深合并后的有效设置。"""
    persisted, _status = read_persisted()
    if persisted:
        merged = _deep_merge(DEFAULTS, persisted)
        # 补丁只经 save 通道进入，已校验；读取防御性过滤未知键
        return {k: v for k, v in merged.items() if k in DEFAULTS}
    return copy.deepcopy(DEFAULTS)


def local_layer_snapshot() -> Dict[str, Any]:
    """本地 SQLite 数据层只读观测（独立于外部源排序，SSOT §6.1 本地数据层）。"""
    from core.data.sync_engine import DB_PATH

    exists = Path(DB_PATH).is_file()
    wal_mode = None
    daily_coverage = {"symbols": None, "as_of": None, "rows": None}
    if exists:
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5.0)
            try:
                row = conn.execute("PRAGMA journal_mode;").fetchone()
                wal_mode = str(row[0]) if row else None
                row = conn.execute("SELECT COUNT(DISTINCT symbol), MAX(date), COUNT(*) FROM daily_kline").fetchone()
                if row:
                    daily_coverage = {"symbols": row[0], "as_of": row[1], "rows": row[2]}
            finally:
                conn.close()
        except Exception:
            wal_mode = None
    try:
        rel = str(Path(DB_PATH).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        rel = str(DB_PATH)
    return {
        "db_relative_path": rel,
        "db_exists": exists,
        "daily_coverage": daily_coverage,
        "journal_mode": wal_mode,
        "read_only_fields": ["db_relative_path", "journal_mode"],
        "note": "本地层为存储与离线读取观测，不参与外部行情源优先级排序",
    }


def save_settings(patch: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """校验并原子落盘全量补丁；无效输入不写文件。返回 (错误, 有效设置)。"""
    errors, candidate = validate_patch(patch)
    if errors:
        return errors, effective_settings()
    path = settings_file_path()
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(candidate, handle, ensure_ascii=False, indent=2)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path.parent, 0o700)
            os.chmod(path, 0o600)
        except OSError:
            pass
    # 回读校验：以文件真实内容为准返回有效设置，不做乐观声明
    reloaded, status = read_persisted()
    if status != "ok" or reloaded is None:
        return [{"field": "", "reason": "设置已写入但回读失败，文件可能被外部破坏"}], effective_settings()
    return [], effective_settings()


def reset_to_defaults() -> Dict[str, Any]:
    """恢复默认设置（全局影响操作，路由层负责二次确认语义）。"""
    return save_settings(copy.deepcopy(DEFAULTS))


# ---------------------------------------------------------------------------
# 设置项生效范围如实披露（杜绝"可保存但不生效"的静默死配置误导用户）
#
# wired        —— 已接入执行层，保存后真实影响后续行为；
# persist_only —— 仅做白名单校验与持久化，当前无执行层消费者，保存不产生实际效果。
# 新增设置项必须在此登记归类；把 persist_only 项接线后应移入 wired。
# ---------------------------------------------------------------------------
EXECUTION_WIRING: Dict[str, List[str]] = {
    "wired": [
        "base.concurrency",             # → SERVER_SYNC_RUNTIME.workers / sync_batch(max_workers)
        "base.timeout_seconds",         # → tasks.create_task 未显式指定时的默认超时
        "daemon.enabled",               # → 服务内巡检协程门控（不控独立 CLI 守护进程）
        "daemon.interval_seconds",      # → 服务内巡检轮询间隔
        "daemon.p0_time",               # → 服务内巡检与 CLI 守护的 P0 定盘时刻
        "daemon.p1_time",               # → 服务内巡检与 CLI 守护的 P1 定盘时刻
        "p3.enabled",                   # → P3 交易日自动增量门控
        "p3.time",                      # → P3 自动执行时刻
        "p3.concurrency",               # → P3 分批并发
        "p3.batch_size",                # → P3 分批大小
        "external_sources.order",       # → data_bridge 取数降级链顺序
        "external_sources.enabled.*",   # → data_bridge 取数降级链逐源启停
        "cooperation.tdx_target_pool",  # → 通达信导入未指定时的默认目标股池
    ],
    "persist_only": [
        "base.mode",                    # 同步模式由各任务入参决定，不读全局默认
        "base.retries",                 # 取数链尚无按设置计数的重试实现
        "p3.retries",
        "integrity.auto_audit",         # 审计/修复仅由显式任务参数触发，无自动挂钩
        "integrity.auto_repair",
        "workspace.common.*",           # 新工作台目标范围，执行层尚未支持
        "workspace.history.*",
        "workspace.quality.*",
        "workspace.performance.*",      # 与 external_sources 功能重叠；选源一律以 external_sources 为准
        "workspace.import_rules.*",     # 导入参数取自请求体，不回读本设置
    ],
}


def apply_to_runtime(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把有效设置回灌到服务内自动巡检运行时（每轮调度前调用，保证设置真实生效）。"""
    from core.data.sync_daemon import SERVER_SYNC_RUNTIME

    eff = settings or effective_settings()
    SERVER_SYNC_RUNTIME["enabled"] = bool(eff["daemon"]["enabled"])
    SERVER_SYNC_RUNTIME["interval"] = max(15, min(int(eff["daemon"]["interval_seconds"]), 3600))
    SERVER_SYNC_RUNTIME["workers"] = max(1, min(int(eff["base"]["concurrency"]), 16))
    return SERVER_SYNC_RUNTIME


def settings_summary_for_ui() -> Dict[str, Any]:
    """UI 摘要视图：有效设置 + 本地层只读观测 + 持久化状态，字段与前端展示契约对齐。"""
    eff = effective_settings()
    _persisted, status = read_persisted()
    return {
        "settings": eff,
        "local_layer": local_layer_snapshot(),
        "persisted_status": status,  # ok | missing | corrupt —— 如实反映，不伪装
        "defaults": copy.deepcopy(DEFAULTS),
        "provider_labels": dict(_PROVIDER_LABELS),
        "execution_wiring": copy.deepcopy(EXECUTION_WIRING),
    }
