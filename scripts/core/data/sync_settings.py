# -*- coding: utf-8 -*-
"""core.data.sync_settings - 数据同步持久化设置的 core 层只读访问器。

写入与校验的权威是 server 侧 `server.services.data_sync_settings`；而取数与调度执行层
（`data_bridge` 选源、`sync_daemon` 定盘时刻）运行在 core 层，**严禁反向 import server.services**，
因此在此提供轻量只读入口，供执行层消费已落盘的有效设置。

契约：
1. 路径与 ENV 覆盖必须与 server 侧完全一致：默认 `LOCAL_DIR/settings/data_sync.json`，
   可用 `A_STOCK_DATA_SYNC_SETTINGS_FILE` 重定向（测试与多实例隔离用）；
2. 文件缺失 / JSON 损坏 / 顶层非对象时返回 `({}, status)`，由调用方各自回落默认值
   并如实标注来源，绝不伪造配置、绝不静默沿用与用户设置不一致的硬编码值；
3. 本模块只读，不写盘、不加锁、不校验业务白名单（校验属 server 侧职责）。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.workspace import LOCAL_DIR
except ImportError:  # 以仓库根为入口运行时的回退
    from scripts.core.workspace import LOCAL_DIR

#: 与 server.services.data_sync_settings.ENV_OVERRIDE 保持同一字面量
ENV_OVERRIDE = "A_STOCK_DATA_SYNC_SETTINGS_FILE"

#: HH:MM 严格校验，与 server 侧 _TIME_RE 同口径
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

#: external_sources.order 的合法 provider 全集与默认顺序（与 server 侧 EXTERNAL_PROVIDERS 一致）
EXTERNAL_PROVIDERS = ("tencent", "sina", "eastmoney")
DEFAULT_PROVIDER_ORDER: Tuple[str, ...] = EXTERNAL_PROVIDERS

#: 内置默认定盘时刻（server 侧 DEFAULTS.daemon 的同源副本，仅在设置不可用时回落）
DEFAULT_P0_TIME = "15:35"
DEFAULT_P1_TIME = "15:40"


def settings_file_path() -> Path:
    """持久化设置文件路径；ENV 覆盖优先，便于测试重定向。"""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    return LOCAL_DIR / "settings" / "data_sync.json"


def read_settings() -> Tuple[Dict[str, Any], str]:
    """读取已落盘设置，返回 (payload, status)。

    status 取值：
    - `ok`        正常解析出 JSON 对象；
    - `missing`   文件不存在（尚未保存过设置）；
    - `corrupt`   文件存在但 JSON 不可解析；
    - `invalid`   JSON 可解析但顶层不是对象。
    非 `ok` 时 payload 恒为空 dict，调用方据此回落默认值。
    """
    path = settings_file_path()
    if not path.is_file():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, "corrupt"
    if not isinstance(payload, dict):
        return {}, "invalid"
    return payload, "ok"


def resolve_provider_order(providers: Optional[List[str]] = None) -> Tuple[List[str], str]:
    """解析外部行情源的实际取数顺序（使控制台配置真正驱动执行层）。

    规则：
    1. 显式入参 `providers` 优先（供调用方与测试注入），来源标注 `explicit`；
    2. 否则取设置 `external_sources.order`，并按 `external_sources.enabled` 过滤停用源；
    3. 过滤后为空（用户手工把三源全关）→ 回落默认顺序，来源标注 `default:all_disabled`，
       宁可如实按默认链取数，也不返回空链让上层误判"无可用源"；
    4. 设置缺失/损坏/字段非法 → 回落默认顺序，来源如实标注，绝不静默。

    返回 (顺序列表, 来源标注)。来源标注用于日志与接口披露，保证可追溯。
    """
    if providers:
        chain = [str(p) for p in providers if str(p) in EXTERNAL_PROVIDERS]
        if chain:
            return chain, "explicit"

    payload, status = read_settings()
    if status != "ok":
        return list(DEFAULT_PROVIDER_ORDER), f"default:settings_{status}"

    ext = payload.get("external_sources")
    if not isinstance(ext, dict):
        return list(DEFAULT_PROVIDER_ORDER), "default:no_external_sources"

    raw_order = ext.get("order")
    if not isinstance(raw_order, list) or not raw_order:
        return list(DEFAULT_PROVIDER_ORDER), "default:bad_order"
    # 只认合法 provider，去重保序；非法项忽略而非报错（执行层不因设置噪声中断取数）
    order: List[str] = []
    for item in raw_order:
        key = str(item)
        if key in EXTERNAL_PROVIDERS and key not in order:
            order.append(key)
    if not order:
        return list(DEFAULT_PROVIDER_ORDER), "default:bad_order"

    enabled = ext.get("enabled")
    if isinstance(enabled, dict):
        # `enabled.get(key) is not False`：键缺失视为启用（容忍排序/开关不完整），
        # 显式 False 才停用。停用项必须真正从链中剔除，否则配置形同虚设。
        active = [key for key in order if enabled.get(key) is not False]
        if not active:
            return list(DEFAULT_PROVIDER_ORDER), "default:all_disabled"
        return active, "settings"

    return order, "settings"


def resolve_settle_time(field: str, default: str) -> Tuple[str, str]:
    """解析 daemon 定盘时刻（`p0_time` / `p1_time`），返回 (HH:MM, 来源标注)。

    设置缺失或时间非法时回落内置默认并如实标注，绝不静默沿用硬编码时刻。
    """
    payload, status = read_settings()
    if status != "ok":
        return default, f"default:settings_{status}"
    daemon_cfg = payload.get("daemon")
    if not isinstance(daemon_cfg, dict):
        return default, "default:no_daemon_section"
    value = daemon_cfg.get(field)
    if not isinstance(value, str):
        return default, f"default:missing_{field}"
    text = value.strip()
    if not _TIME_RE.match(text):
        return default, f"default:invalid_{field}"
    return text, "settings"
