# -*- coding: utf-8 -*-
"""用户模型目录与调度定义存储（批次三 / SSOT §7.1、§16、§15.3）。

本模块承载面向用户的自建模型能力：

- **模型目录**：列出/读取用户模型（名称、类型、活动版本、最新版本、更新时间）；
- **创建草稿**：从"空白"或"示例模板"创建 `condition_tree` / `funnel` 草稿（§16 创建向导）；
- **文案草稿解析**（§15.1 `drafts/from-text`）：把中文选股文案**确定性**映射为规则草稿，
  无法识别的片段如实登记为 `ambiguities`，不猜测、不虚构口径；
- **调度定义存储**（§15.3）：应用内调度覆盖（暂停/恢复 + 阶段时间窗覆盖）落
  `output/config/selection-models/<model_id>/schedule.json`。

本模块只做结构装配与持久化，不读取行情、不产出选股结论。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from core.selection_models import schemas
from core.selection_models.definition_repository import (
    DEFAULT_BASE_DIR,
    DefinitionRepository,
    atomic_write_text,
    model_dir,
    validate_model_id,
)
from core.selection_models.model_type_registry import (
    ModelTypeError,
    build_default_type_registry,
)
from core.selection_models.version_repository import VersionRepository

#: 调度定义文件名（应用内覆盖，不参与 definition_hash）。
SCHEDULE_FILE = "schedule.json"

#: 允许创建的模型类型：仅 P0 可发布类型（P2 只显示"规划中"，不得提供可点击编辑器，§16）。
CREATABLE_TEMPLATES = ("blank", "funnel_close_breakout", "condition_pullback")


class ModelCatalogError(ValueError):
    """模型目录相关错误；`code` 为稳定错误码，供 API 透出。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ------------------------------------------------------------------ 目录
def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    import yaml

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _model_summary(model_id: str, base_dir: Path) -> Dict[str, Any]:
    directory = model_dir(model_id, base_dir)
    versions = VersionRepository(base_dir).list_versions(model_id)
    active_version = VersionRepository(base_dir).active_version(model_id)
    draft = DefinitionRepository(base_dir).load_draft(model_id)

    definition: Dict[str, Any] = {}
    source = "empty"
    if active_version is not None:
        definition = _read_yaml(directory / f"definition-v{int(active_version)}.yaml")
        source = "active"
    elif versions:
        latest = max(int(item["version"]) for item in versions)
        definition = _read_yaml(directory / f"definition-v{latest}.yaml")
        source = "published"
    elif draft is not None:
        definition = draft.get("definition") or {}
        source = "draft"

    model = definition.get("model") or {}
    latest_version = max((int(item["version"]) for item in versions), default=0)
    status = "draft" if source == "draft" else ("active" if source == "active" else source)
    return {
        "model_id": model_id,
        "name": str(model.get("name") or model_id),
        "model_type": str(model.get("model_type") or ""),
        "description": model.get("description"),
        "enabled": bool(model.get("enabled", True)),
        "status": status,
        "source": source,
        "active_version": active_version,
        "latest_version": latest_version,
        "version_count": len(versions),
        "has_draft": draft is not None,
        "draft_revision": (draft or {}).get("draft_revision"),
        "updated_at": (draft or {}).get("updated_at")
        or (versions[-1].get("published_at") if versions else None),
    }


def list_models(
    *,
    base_dir: Optional[Path] = None,
    model_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """列出全部用户模型；可按模型类型过滤，按更新时间倒序。"""
    root = Path(base_dir or DEFAULT_BASE_DIR)
    if not root.is_dir():
        return []
    summaries: List[Dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        try:
            model_id = validate_model_id(child.name)
        except ValueError:
            continue
        summary = _model_summary(model_id, root)
        if model_type and summary["model_type"] != model_type:
            continue
        summaries.append(summary)
    summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return summaries


def get_model(model_id: str, *, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """读取单个模型：元信息 + 活动版本摘要 + 草稿可见性。"""
    root = Path(base_dir or DEFAULT_BASE_DIR)
    model_id = validate_model_id(model_id)
    directory = model_dir(model_id, root)
    if not directory.is_dir():
        raise ModelCatalogError("MODEL_VERSION_NOT_FOUND", f"模型不存在: {model_id}")
    summary = _model_summary(model_id, root)
    draft = DefinitionRepository(root).load_draft(model_id)
    summary["draft"] = (
        {
            "definition": draft["definition"],
            "base_version": draft["base_version"],
            "draft_revision": draft["draft_revision"],
            "updated_at": draft["updated_at"],
            "updated_by": draft["updated_by"],
        }
        if draft
        else None
    )
    return summary


# ------------------------------------------------------------------ 创建草稿
def _new_model_id(root: Path) -> str:
    base = "sm_" + datetime.now().strftime("%Y%m%d%H%M%S")
    candidate = base
    counter = 1
    while model_dir(candidate, root).exists():
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _funnel_template_stages(template: str) -> List[Dict[str, Any]]:
    """示例模板的阶段骨架（参数均为可配置默认值，不含任何写死的运行结论）。"""
    if template == "funnel_close_breakout":
        return [
            {
                "id": "post_close",
                "name": "收盘突破候选",
                "enabled": True,
                "order": 10,
                "scope": "candidate_filter",
                "kind": "filter",
                "logic": "all",
                "schedule": "15:35-23:59",
                "input_binding": schemas.ROOT_INPUT_BINDING,
                "missing_data_policy": "reject",
                "rules": [
                    {"id": "r_new_high", "type": "rolling_high", "lookback": 20, "strict": True},
                ],
            },
            {
                "id": "market_gate",
                "name": "大盘门控",
                "enabled": True,
                "order": 20,
                "scope": "universe_gate",
                "kind": "gate",
                "logic": "all",
                "schedule": "09:30-09:31",
                "input_binding": "post_close.candidates",
                "missing_data_policy": "wait",
                "rules": [
                    {"id": "r_market_ma20", "type": "market_above_sma", "period": 20, "strict": True},
                ],
            },
            {
                "id": "opening_gap",
                "name": "高开过滤",
                "enabled": True,
                "order": 30,
                "scope": "candidate_filter",
                "kind": "filter",
                "logic": "all",
                "schedule": "09:30-09:35",
                "input_binding": "market_gate.candidates",
                "missing_data_policy": "wait",
                "rules": [
                    {"id": "r_gap", "type": "field_compare", "field": "gap_pct", "op": "gte", "value": 1.0},
                    {"id": "r_gap_max", "type": "field_compare", "field": "gap_pct", "op": "lte", "value": 2.0},
                ],
            },
            {
                "id": "turning_point",
                "name": "早盘拐点确认",
                "enabled": True,
                "order": 40,
                "scope": "candidate_filter",
                "kind": "filter",
                "logic": "all",
                "schedule": "09:36-09:40",
                "input_binding": "opening_gap.candidates",
                "missing_data_policy": "wait",
                "rules": [
                    {"id": "r_turn", "type": "intraday_turning_point"},
                ],
            },
        ]
    # blank：单阶段空白漏斗，用户自行编排
    return [
        {
            "id": "stage_1",
            "name": "第一层",
            "enabled": True,
            "order": 10,
            "scope": "candidate_filter",
            "kind": "filter",
            "logic": "all",
            "schedule": None,
            "input_binding": schemas.ROOT_INPUT_BINDING,
            "missing_data_policy": "reject",
            "rules": [
                {"id": "r_1", "type": "rolling_high", "lookback": 20, "strict": True},
            ],
        }
    ]


def blank_funnel_definition(
    model_id: str,
    name: str,
    description: Optional[str],
    *,
    template: str = "blank",
) -> Dict[str, Any]:
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "model": {
            "id": model_id,
            "name": name,
            "model_type": "funnel",
            "version": 1,
            "enabled": True,
            "timezone": schemas.DEFAULT_TIMEZONE,
            "exchange_calendar": schemas.DEFAULT_EXCHANGE_CALENDAR,
            "description": description,
        },
        "data_requirements": [],
        "stages": _funnel_template_stages(template),
    }


def blank_condition_definition(
    model_id: str,
    name: str,
    description: Optional[str],
    *,
    template: str = "blank",
) -> Dict[str, Any]:
    if template == "condition_pullback":
        group_rules = [
            {"id": "r_above_ma", "type": "above_sma", "period": 60, "strict": True},
            {"id": "r_volume", "type": "volume_sustained_expansion"},
        ]
    else:
        group_rules = [
            {"id": "r_above_ma", "type": "above_sma", "period": 60, "strict": True},
        ]
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "model": {
            "id": model_id,
            "name": name,
            "model_type": "condition_tree",
            "version": 1,
            "enabled": True,
            "timezone": schemas.DEFAULT_TIMEZONE,
            "exchange_calendar": schemas.DEFAULT_EXCHANGE_CALENDAR,
            "description": description,
        },
        "data_requirements": [],
        "groups": [
            {"id": "g_tech", "name": "技术面", "logic": "all", "rules": group_rules},
        ],
        "expression": {"ref": "g_tech"},
    }


def create_model(
    *,
    model_type: str,
    name: str,
    description: str = "",
    template: str = "blank",
    model_id: Optional[str] = None,
    base_dir: Optional[Path] = None,
    operator: Optional[str] = None,
) -> Dict[str, Any]:
    """从空白/模板创建一个未激活草稿；返回草稿元信息（不发布、不激活）。"""
    registry = build_default_type_registry()
    try:
        capability = registry.require_publishable(model_type)
    except ModelTypeError as exc:
        raise ModelCatalogError("MODEL_TYPE_UNKNOWN", str(exc)) from exc
    if not str(name or "").strip():
        raise ModelCatalogError("MODEL_CONFIG_INVALID", "模型名称不能为空")
    if template not in CREATABLE_TEMPLATES:
        raise ModelCatalogError("MODEL_CONFIG_INVALID", f"未知模板: {template}")

    root = Path(base_dir or DEFAULT_BASE_DIR)
    if model_id:
        model_id = validate_model_id(model_id)
        if model_dir(model_id, root).exists():
            raise ModelCatalogError("MODEL_VERSION_CONFLICT", f"模型 ID 已存在: {model_id}")
    else:
        model_id = _new_model_id(root)

    if capability.type_id == "funnel":
        definition = blank_funnel_definition(model_id, str(name).strip(), description or None, template=template)
    else:
        definition = blank_condition_definition(model_id, str(name).strip(), description or None, template=template)

    normalized, warnings = schemas.migrate_to_v2(definition)
    draft = DefinitionRepository(root).create_draft(model_id, normalized, base_version=None, operator=operator)
    return {
        "model_id": draft["model_id"],
        "model_type": model_type,
        "name": str(name).strip(),
        "description": description,
        "template": template,
        "base_version": draft["base_version"],
        "draft_revision": draft["draft_revision"],
        "definition": draft["definition"],
        "warnings": list(warnings),
    }


# ------------------------------------------------------------------ 文案草稿解析
#: 文案片段 → 规则的最小确定性映射表（不猜测未命中的语义）。
_NEW_HIGH_RE = re.compile(r"(\d{1,3})\s*(?:个)?\s*(?:交易)?日\s*新?高")
_ABOVE_MA_RE = re.compile(r"高于\s*(\d{1,3})\s*(?:日|天)?\s*均线")
_GAP_RE = re.compile(r"高开\s*(\d+(?:\.\d+)?)\s*%\s*(?:到|至|~|-|—)\s*(\d+(?:\.\d+)?)\s*%")
_EXCLUDE_ST_RE = re.compile(r"排除\s*ST")
_EXCLUDE_BSE_RE = re.compile(r"排除\s*(?:北交所|北证|8|4)")
_VOLUME_RE = re.compile(r"量能放大|放量|量能持续放大")


def draft_from_text(text: str) -> Dict[str, Any]:
    """把选股文案确定性解析为漏斗草稿骨架；未识别片段如实登记为歧义项。

    解析原则（不伪造口径）：
    - 只映射**能明确对应已注册规则**的片段；其余整段进入 `ambiguities`，由用户手工补充；
    - 不生成任何行情数值或选股结论，只装配规则结构与参数。
    """
    raw = str(text or "").strip()
    if not raw:
        raise ModelCatalogError("MODEL_CONFIG_INVALID", "选股文案不能为空")

    matched: List[Dict[str, Any]] = []
    ambiguities: List[str] = []

    def _consume(pattern: re.Pattern, builder) -> bool:
        found = False
        for match in pattern.finditer(raw):
            matched.append(builder(match))
            found = True
        return found

    rules: List[Dict[str, Any]] = []

    _consume(_NEW_HIGH_RE, lambda m: {"rule": {"id": f"r_new_high_{m.group(1)}", "type": "rolling_high", "lookback": int(m.group(1)), "strict": True}, "text": m.group(0)})
    _consume(_ABOVE_MA_RE, lambda m: {"rule": {"id": f"r_above_ma_{m.group(1)}", "type": "above_sma", "period": int(m.group(1)), "strict": True}, "text": m.group(0)})
    _consume(_VOLUME_RE, lambda m: {"rule": {"id": "r_volume", "type": "volume_sustained_expansion"}, "text": m.group(0)})
    _consume(_GAP_RE, lambda m: {"rule": {"id": "r_gap_min", "type": "field_compare", "field": "gap_pct", "op": "gte", "value": float(m.group(1))}, "text": m.group(0)})
    _consume(_GAP_RE, lambda m: {"rule": {"id": "r_gap_max", "type": "field_compare", "field": "gap_pct", "op": "lte", "value": float(m.group(2))}, "text": m.group(0)})
    _consume(_EXCLUDE_ST_RE, lambda m: {"rule": {"id": "r_exclude_st", "type": "text_exclude", "tokens": ["ST"]}, "text": m.group(0)})
    _consume(_EXCLUDE_BSE_RE, lambda m: {"rule": {"id": "r_exclude_bse", "type": "symbol_prefix_exclude", "prefixes": ["4", "8", "92"]}, "text": m.group(0)})

    for item in matched:
        rule = item["rule"]
        if rule["id"] not in [existing["id"] for existing in rules]:
            rules.append(rule)

    # 逐句登记未识别片段（同一句若命中任一模式则不列为歧义）
    for sentence in re.split(r"[，,。;；\n]+", raw):
        fragment = sentence.strip()
        if not fragment:
            continue
        if any(item["text"] and item["text"] in fragment for item in matched):
            continue
        ambiguities.append(fragment)

    if not rules:
        raise ModelCatalogError(
            "MODEL_CONFIG_INVALID",
            "文案未命中任何可映射规则，无法自动生成草稿；请手工选择规则或改写文案",
        )

    definition = blank_funnel_definition("__draft__", "文案草稿", None, template="blank")
    definition["stages"][0]["rules"] = rules
    definition["stages"][0]["name"] = "文案解析层"
    definition["model"]["name"] = (raw[:24] or "文案草稿")
    normalized, warnings = schemas.migrate_to_v2(definition)
    normalized["model"]["id"] = "__draft_pending__"

    return {
        "definition": normalized,
        "matched_rules": rules,
        "ambiguities": ambiguities,
        "warnings": list(warnings),
        "activated": False,
    }


# ------------------------------------------------------------------ 调度定义存储
class ScheduleStore:
    """应用内调度覆盖持久化（暂停/恢复 + 阶段时间窗覆盖），落 `schedule.json`。"""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(base_dir or DEFAULT_BASE_DIR)

    def path(self, model_id: str) -> Path:
        return model_dir(model_id, self.base_dir) / SCHEDULE_FILE

    def load(self, model_id: str) -> Dict[str, Any]:
        payload = _read_json(self.path(model_id))
        return {
            "model_id": validate_model_id(model_id),
            "paused": bool(payload.get("paused", False)),
            "stages": dict(payload.get("stages") or {}),
            "updated_at": payload.get("updated_at"),
            "updated_by": payload.get("updated_by"),
        }

    def save(self, model_id: str, payload: Mapping[str, Any], *, operator: Optional[str] = None) -> Dict[str, Any]:
        model_id = validate_model_id(model_id)
        current = self.load(model_id)
        stages = dict(current["stages"])
        if "stages" in payload and isinstance(payload["stages"], Mapping):
            stages.update({str(k): v for k, v in payload["stages"].items()})
        body = {
            "model_id": model_id,
            "paused": current["paused"] if payload.get("paused") is None else bool(payload.get("paused")),
            "stages": stages,
            "updated_at": _now(),
            "updated_by": operator,
        }
        atomic_write_text(self.path(model_id), json.dumps(body, ensure_ascii=False, indent=2))
        return body

    def set_paused(self, model_id: str, paused: bool, *, operator: Optional[str] = None) -> Dict[str, Any]:
        return self.save(model_id, {"paused": bool(paused)}, operator=operator)


__all__ = [
    "CREATABLE_TEMPLATES",
    "SCHEDULE_FILE",
    "ModelCatalogError",
    "ScheduleStore",
    "blank_condition_definition",
    "blank_funnel_definition",
    "create_model",
    "draft_from_text",
    "get_model",
    "list_models",
]