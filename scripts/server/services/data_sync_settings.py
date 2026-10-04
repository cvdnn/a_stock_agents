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

    # 合并后再验"至少保留一个可用外部数据源"（对候选有效值判定，而非仅补丁）
    candidate = _deep_merge(DEFAULTS, {}) if errors else _deep_merge(DEFAULTS, patch)
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
    if exists:
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5.0)
            try:
                row = conn.execute("PRAGMA journal_mode;").fetchone()
                wal_mode = str(row[0]) if row else None
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
    }
