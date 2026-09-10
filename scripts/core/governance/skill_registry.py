# -*- coding: utf-8 -*-
"""
core.governance.skill_registry - Central Skill Registry and Governance Subsystem.
Loads 17 A-Stock skills from config/skills_manifest.json, generates OpenAI function schemas,
manages dynamic enable/disable state, enforces security gates and timeout fuses.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from core.config import PROJECT_ROOT, get_logger
from core.governance.auditor import default_auditor
from core.governance.models import SkillMeta, SkillRiskLevel, SkillTestResponse

logger = get_logger("core.governance.skill_registry")

MANIFEST_PATH = PROJECT_ROOT / "config" / "skills_manifest.json"


# ── Canonical Parameter Schemas for all 17 Skills ────────────────────────────

SKILL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "astock-data-feed": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "6位A股代码，如 600519、000001、300750"},
            "action": {"type": "string", "enum": ["quote", "tech", "history"], "description": "数据类型：quote (实时行情), tech (技术指标), history (历史K线)"},
            "count": {"type": "integer", "description": "K线根数，默认 60"},
        },
        "required": ["code"],
    },
    "astock-platform-evaluate": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "6位A股代码进行多因子综合打分与诊断"},
        },
        "required": ["code"],
    },
    "astock-screener-5a": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "返回优质标的数量上限，默认 10"},
            "dynamic_mode": {"type": "string", "enum": ["hot_sectors", "high_momentum"], "description": "选股模式：热点板块或高动量"},
        },
    },
    "astock-pool-dashboard": {
        "type": "object",
        "properties": {
            "pool_type": {"type": "string", "enum": ["focus", "custom", "holding"], "description": "股票池类型：关注池、自选池或持仓池"},
            "action": {"type": "string", "enum": ["list", "summary"], "description": "操作：查看列表或摘要"},
        },
    },
    "astock-trade-paper": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["balance", "positions", "buy", "sell", "orders", "cancel"], "description": "交易动作"},
            "code": {"type": "string", "description": "6位股票代码 (下单/撤单时需要)"},
            "shares": {"type": "integer", "description": "交易股数 (买入/卖出，100的整数倍)"},
            "price": {"type": "number", "description": "委托价格 (限价单)"},
            "order_id": {"type": "string", "description": "委托单号 (撤单时需要)"},
        },
        "required": ["action"],
    },
    "astock-strategy-mainboard": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["candidates", "signals", "check"], "description": "主板策略动作"},
            "code": {"type": "string", "description": "股票代码 (单股检查时需要)"},
        },
    },
    "astock-quant-engine": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["pipeline", "kelly", "atr", "factors"], "description": "量化工程计算流水线指令"},
            "code": {"type": "string", "description": "目标股票代码"},
        },
    },
    "astock-agent-debate": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "进行7大分析师多空对抗研判的A股代码"},
            "rounds": {"type": "integer", "description": "辩论轮数，默认 2 轮"},
        },
        "required": ["code"],
    },
    "astock-strategy-tuige": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "6位股票代码"},
            "scenario": {"type": "string", "enum": ["limit_up_pullback", "continuation", "wash_end"], "description": "短线交易场景"},
        },
        "required": ["code"],
    },
    "astock-strategy-macd": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "检查MACD底背离与零轴下二次金叉的A股代码"},
        },
        "required": ["code"],
    },
    "astock-action-execution": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "6位A股代码"},
            "cost": {"type": "number", "description": "持仓买入成本价"},
            "shares": {"type": "integer", "description": "持仓股数，默认 100"},
        },
        "required": ["code"],
    },
    "astock-pool-audit": {
        "type": "object",
        "properties": {
            "fix": {"type": "boolean", "description": "是否自动清洗失效标的与重算均线，默认 false"},
        },
    },
    "astock-report-archive": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "生成或归档报告的标的代码"},
            "report_type": {"type": "string", "enum": ["evaluation", "combo", "multi_stock"], "description": "报告类型"},
        },
    },
    "astock-report-html": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "生成高颜值单文件HTML报告的代码"},
        },
        "required": ["code"],
    },
    "astock-knowledge-tips": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "技巧主题：auction (早盘集合竞价), fallback (API防封降级), traps (避坑指南)"},
        },
    },
    "astock-model-validation": {
        "type": "object",
        "properties": {
            "model_name": {"type": "string", "description": "时序基础模型名称，如 Kronos, TimesFM"},
            "code": {"type": "string", "description": "验证测试股票代码"},
        },
    },
    "astock-meta-routing": {
        "type": "object",
        "properties": {
            "task_description": {"type": "string", "description": "任务意图描述"},
        },
        "required": ["task_description"],
    },
}


class SkillRegistry:
    """Central registry and governor managing metadata, schemas, dynamic state, and safety fuses."""

    _instance: Optional[SkillRegistry] = None

    def __init__(self, manifest_path: Optional[Path] = None) -> None:
        self.manifest_path = manifest_path or MANIFEST_PATH
        self._skills: Dict[str, SkillMeta] = {}
        self._execution_handlers: Dict[str, Callable[..., Any]] = {}
        self.load_manifest()
        self._load_overrides()

    @classmethod
    def get_instance(cls) -> SkillRegistry:
        if cls._instance is None:
            cls._instance = SkillRegistry()
        return cls._instance

    def load_manifest(self) -> None:
        """Parse config/skills_manifest.json and initialize SkillMeta instances."""
        if not self.manifest_path.exists():
            logger.warning(f"Manifest not found at {self.manifest_path}. Creating fallback catalog.")
            return

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error(f"Failed to read manifest {self.manifest_path}: {exc}", exc_info=True)
            return

        skills_list = data.get("skills", [])
        for item in skills_list:
            sid = item.get("id")
            if not sid:
                continue

            # Determine risk level and default confirmation
            risk = SkillRiskLevel.READONLY
            require_confirm = False
            timeout = 30

            if sid == "astock-trade-paper":
                risk = SkillRiskLevel.SIMULATION
                require_confirm = True
            elif sid in ("astock-screener-5a", "astock-quant-engine", "astock-model-validation"):
                timeout = 60
            elif sid == "astock-agent-debate":
                timeout = 120

            schema = SKILL_SCHEMAS.get(sid, {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "A股代码"}},
            })

            meta = SkillMeta(
                id=sid,
                name=item.get("name", sid),
                title=item.get("title", sid),
                category=item.get("category", "general"),
                description=item.get("description", ""),
                risk_level=risk,
                enabled=True,
                triggers=item.get("triggers", []),
                parameters_schema=schema,
                timeout_seconds=timeout,
                require_confirmation=require_confirm,
                entry_point=item.get("entry_point"),
                cli_command=item.get("cli_command"),
                skill_doc=item.get("skill_doc"),
                recommended_model=item.get("recommended_model", "inherit"),
            )
            self._skills[sid] = meta

        logger.info(f"Loaded {len(self._skills)} skills into SkillRegistry from {self.manifest_path.name}")

    def _load_overrides(self) -> None:
        """Load persistent status overrides from SQLite."""
        try:
            from server.db import get_skill_overrides
            overrides = get_skill_overrides()
            for sid, ov in overrides.items():
                if sid in self._skills:
                    if ov.get("enabled") is not None:
                        self._skills[sid].enabled = ov["enabled"]
                    if ov.get("timeout_seconds") is not None:
                        self._skills[sid].timeout_seconds = ov["timeout_seconds"]
                    if ov.get("require_confirmation") is not None:
                        self._skills[sid].require_confirmation = ov["require_confirmation"]
        except Exception as exc:
            logger.debug(f"Could not load skill overrides: {exc}")

    def list_skills(
        self,
        category: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[SkillMeta]:
        """List registered skills filtered by category or enabled status."""
        res = list(self._skills.values())
        if category:
            res = [s for s in res if s.category.lower() == category.lower()]
        if enabled_only:
            res = [s for s in res if s.enabled]
        return res

    def get_skill(self, skill_id: str) -> Optional[SkillMeta]:
        """Fetch metadata for a given skill id (supports hyphen or underscore format)."""
        sid = skill_id.replace("_", "-")
        if sid in self._skills:
            return self._skills[sid]
        # Also try reverse if keyed with underscores
        return self._skills.get(skill_id)

    def update_skill(
        self,
        skill_id: str,
        enabled: Optional[bool] = None,
        timeout_seconds: Optional[int] = None,
        require_confirmation: Optional[bool] = None,
    ) -> Optional[SkillMeta]:
        """Dynamically update a skill's settings and persist them."""
        skill = self.get_skill(skill_id)
        if not skill:
            return None

        if enabled is not None:
            skill.enabled = enabled
        if timeout_seconds is not None:
            skill.timeout_seconds = timeout_seconds
        if require_confirmation is not None:
            skill.require_confirmation = require_confirmation

        # Persist override
        try:
            from server.db import save_skill_override
            save_skill_override(
                skill_id=skill.id,
                enabled=skill.enabled,
                timeout_seconds=skill.timeout_seconds,
                require_confirmation=skill.require_confirmation,
            )
        except Exception as exc:
            logger.warning(f"Failed to persist skill override for {skill.id}: {exc}")

        return skill

    def to_openai_tools(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """
        Convert registered skills to standard OpenAI Function Calling Tool Schemas.
        Uses underscore-separated function names (OpenAI specification compliance).
        """
        tools = []
        for s in self._skills.values():
            if enabled_only and not s.enabled:
                continue

            fn_name = s.id.replace("-", "_")
            tools.append({
                "type": "function",
                "function": {
                    "name": fn_name,
                    "description": s.description,
                    "parameters": s.parameters_schema,
                },
            })
        return tools

    def validate_parameters(self, skill_id: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate execution parameters against the skill's JSON Schema."""
        skill = self.get_skill(skill_id)
        if not skill:
            return False, f"Unknown skill: {skill_id}"

        required = skill.parameters_schema.get("required", [])
        for req in required:
            if req not in params:
                return False, f"缺少必须的参数: '{req}'"
            if params[req] is None or params[req] == "":
                return False, f"参数 '{req}' 不能为空"

        # Type checks
        props = skill.parameters_schema.get("properties", {})
        for k, v in params.items():
            if k in props:
                expected_type = props[k].get("type")
                if expected_type == "integer" and not isinstance(v, int):
                    try:
                        params[k] = int(v)
                    except (ValueError, TypeError):
                        return False, f"参数 '{k}' 必须是整数"
                elif expected_type == "number" and not isinstance(v, (int, float)):
                    try:
                        params[k] = float(v)
                    except (ValueError, TypeError):
                        return False, f"参数 '{k}' 必须是数值"
                elif expected_type == "boolean" and not isinstance(v, bool):
                    if str(v).lower() in ("true", "1"):
                        params[k] = True
                    elif str(v).lower() in ("false", "0"):
                        params[k] = False
                    else:
                        return False, f"参数 '{k}' 必须是布尔值"

        return True, None

    def register_handler(self, skill_id: str, handler: Callable[..., Any]) -> None:
        """Register execution callback for a skill."""
        normalized = skill_id.replace("-", "_")
        self._execution_handlers[normalized] = handler
        self._execution_handlers[skill_id] = handler

    async def execute_skill(
        self,
        skill_id: str,
        params: Dict[str, Any],
        confirmed: bool = False,
    ) -> SkillTestResponse:
        """
        Execute skill with:
        1. Enabled check
        2. Security gate (Human-in-the-loop confirmation for SIMULATION/DESTRUCTIVE)
        3. Parameter Schema validation
        4. Timeout fuse protection
        5. Audit logging
        """
        start_t = time.time()
        skill = self.get_skill(skill_id)
        if not skill:
            return SkillTestResponse(
                skill_id=skill_id,
                status="error",
                error=f"未找到对应技能: {skill_id}",
                latency_ms=0,
            )

        if not skill.enabled:
            return SkillTestResponse(
                skill_id=skill.id,
                status="error",
                error=f"技能 {skill.title} ({skill.id}) 当前处于停用状态，请先在治理控制台启用。",
                latency_ms=0,
            )

        # Security gate
        if skill.require_confirmation and not confirmed:
            msg = f"【安全门禁拦截】技能 {skill.title} 涉及 {skill.risk_level.value} 等级操作，需要用户在前端界面二次确认后方可执行。"
            default_auditor.record_call(
                skill_id=skill.id,
                action="execute",
                status="rejected",
                latency_ms=0,
                error_message="Confirmation required",
            )
            return SkillTestResponse(
                skill_id=skill.id,
                status="confirmation_required",
                message=msg,
                latency_ms=0,
            )

        # Parameter validation
        valid, err_msg = self.validate_parameters(skill.id, params)
        if not valid:
            default_auditor.record_call(
                skill_id=skill.id,
                action="execute",
                status="error",
                latency_ms=0,
                error_message=err_msg,
            )
            return SkillTestResponse(
                skill_id=skill.id,
                status="error",
                error=err_msg,
                latency_ms=0,
            )

        # Locate handler
        handler = self._execution_handlers.get(skill.id) or self._execution_handlers.get(skill.id.replace("-", "_"))
        is_fallback = False
        if not handler:
            from server.agent.tools import execute_tool as default_tool_executor
            handler = default_tool_executor
            is_fallback = True

        try:
            # Execute with timeout fuse
            if asyncio.iscoroutinefunction(handler):
                coro = handler(skill.id, params) if is_fallback else handler(**params)
                result = await asyncio.wait_for(coro, timeout=skill.timeout_seconds)
            else:
                loop = asyncio.get_running_loop()
                fn_call = (lambda: handler(skill.id, params)) if is_fallback else (lambda: handler(**params))
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, fn_call),
                    timeout=skill.timeout_seconds,
                )


            latency = int((time.time() - start_t) * 1000)
            result_status = result.get("status") if isinstance(result, dict) else None
            allowed_statuses = {"success", "error", "unavailable", "timeout", "confirmation_required"}
            status = result_status if result_status in allowed_statuses else (
                "error" if isinstance(result, dict) and result.get("error") else "success"
            )
            err = result.get("error") if isinstance(result, dict) else None

            default_auditor.record_call(
                skill_id=skill.id,
                action="execute",
                status=status,
                latency_ms=latency,
                error_message=str(err) if err else None,
            )

            return SkillTestResponse(
                skill_id=skill.id,
                status=status,
                result=result if isinstance(result, dict) else {"output": result},
                error=err,
                latency_ms=latency,
            )

        except asyncio.TimeoutError:
            latency = int((time.time() - start_t) * 1000)
            err_msg = f"技能执行超时熔断: 运行耗时超过设定的 {skill.timeout_seconds} 秒上限。"
            default_auditor.record_call(
                skill_id=skill.id,
                action="execute",
                status="timeout",
                latency_ms=latency,
                error_message=err_msg,
            )
            return SkillTestResponse(
                skill_id=skill.id,
                status="timeout",
                error=err_msg,
                latency_ms=latency,
            )
        except Exception as exc:
            latency = int((time.time() - start_t) * 1000)
            err_msg = f"技能执行发生未捕获异常: {str(exc)}"
            logger.error(f"Skill execution failed for {skill.id}: {exc}", exc_info=True)
            default_auditor.record_call(
                skill_id=skill.id,
                action="execute",
                status="error",
                latency_ms=latency,
                error_message=err_msg,
            )
            return SkillTestResponse(
                skill_id=skill.id,
                status="error",
                error=err_msg,
                latency_ms=latency,
            )


def get_skill_registry() -> SkillRegistry:
    """Helper returning the singleton SkillRegistry instance."""
    return SkillRegistry.get_instance()
