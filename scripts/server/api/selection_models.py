# -*- coding: utf-8 -*-
"""server.api.selection_models - 智能选股系统（ISS）后端 API（批次三 / SPEC-ALGO-ISS-001 §15）。

统一前缀 `/api/selection-models`。设计约束：

- **统一水印包裹**（P-08 / W-03）：所有响应用 `{status, data, error_code?, watermark}` 包裹；
  业务性不可用保持 HTTP 200 并给出稳定 `error_code`，前端据水印展示明确不可用提示；
- **正式运行与调试运行严格隔离**（发布门禁 10）：手工运行走 `runs`，只执行**已发布且已激活**
  的版本；`debug/*` 只读编译中间产物与规则评估轨迹，绝不落正式运行目录、绝不发信号；
- **不加码不伪造**：数据不足一律失败关闭（不产出代码），所有数字来自落盘运行记录；
- 权限（§20.1，10 项）复用 `server.auth.dependencies.require_selection` 的「menu + action 两段式」。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.data.data_assembler import GATE_WAITING_DATA, STATUS_OK, DataAssembler
from core.data.sync_engine import DB_PATH, TradeCalendar
from core.selection_models.catalog import (
    ModelCatalogError,
    ScheduleStore,
    create_model,
    draft_from_text,
    get_model,
    list_models,
)
from core.selection_models.definition_repository import (
    DefinitionRepository,
    DraftConflictError,
)
from core.selection_models.hash import short_hash
from core.selection_models.model_compiler import (
    CompiledSelectionPlan,
    ModelCompilerError,
    compile_definition,
)
from core.selection_models.model_type_registry import build_default_type_registry
from core.selection_models.model_evaluator import (
    DEFAULT_BENCHMARK,
    DEFAULT_MIN_OBSERVATION_DAYS,
    DEFAULT_MIN_SAMPLES,
    ModelEvaluator,
)
from core.selection_models.optimization_advisor import (
    OptimizationAdvisor,
    OptimizationAdvisorError,
    STATUS_ACCEPTED,
    STATUS_IGNORED,
)
from core.selection_models.orchestrator import SelectionModelOrchestrator
from core.selection_models.result_assessment import (
    ResultAssessmentError,
    ResultAssessmentService,
)
from core.selection_models.rule_registry import build_default_rule_registry
from core.selection_models.run_repository import RunRepository
from core.selection_models.scheduler import SelectionScheduler, parse_schedule
from core.selection_models.schemas import SelectionSchemaError
from core.selection_models.tracking_service import (
    DEFAULT_PERIODS,
    TrackingError,
    TrackingService,
)
from core.selection_models.version_repository import (
    VersionConflictError,
    VersionNotFoundError,
    VersionRepository,
)
from core.strategy.funnel_engine import FunnelEngine
from core.strategy.stock_funnel import build_stock_rule_registry
from server.auth.dependencies import AuthContext, require_selection
from server.db import record_auth_audit

router = APIRouter(prefix="/api/selection-models", tags=["Selection Models"])

SOURCE = "selection_models"


# ------------------------------------------------------------------ 统一水印包裹
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _watermark(
    *,
    availability: str = "ok",
    degraded_reason: Optional[str] = None,
    eligible_for_signal: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """数据准入水印（P-08）：来源 / 取数时点 / 可用性 / 降级原因 / 是否可发正式信号。"""
    payload: Dict[str, Any] = {
        "source": SOURCE,
        "as_of": _now(),
        "availability": availability,
        "degraded_reason": degraded_reason,
        "eligible_for_signal": bool(availability == "ok") if eligible_for_signal is None else bool(eligible_for_signal),
    }
    if extra:
        payload.update(extra)
    return payload


def _ok(data: Any, *, watermark: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"status": "ok", "data": data, "watermark": watermark or _watermark()}


def _fail(
    error_code: str,
    message: str,
    *,
    http_status: int = 200,
    watermark: Optional[Dict[str, Any]] = None,
    data: Any = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={
            "status": "error",
            "data": data,
            "error_code": error_code,
            "message": message,
            "watermark": watermark or _watermark(availability="unsupported", degraded_reason=error_code),
        },
    )


_ERROR_CODE_BY_EXC = {
    "MODEL_TYPE_UNKNOWN": "MODEL_TYPE_UNKNOWN",
    "MODEL_CONFIG_INVALID": "MODEL_CONFIG_INVALID",
    "MODEL_VERSION_NOT_FOUND": "MODEL_VERSION_NOT_FOUND",
    "MODEL_VERSION_CONFLICT": "MODEL_VERSION_CONFLICT",
    "MODEL_DRAFT_CONFLICT": "MODEL_DRAFT_CONFLICT",
    "MODEL_RULE_UNKNOWN": "MODEL_RULE_UNKNOWN",
}


def _guard(exc: Exception) -> JSONResponse:
    code = getattr(exc, "code", None) or "MODEL_CONFIG_INVALID"
    return _fail(str(code), str(exc))


def _audit(ctx: AuthContext, action: str, detail: str) -> None:
    try:
        record_auth_audit(ctx.user_id, ctx.username, f"selection_model.{action}", "success", "", detail)
    except Exception:  # pragma: no cover - 审计失败不阻断主流程
        pass


# ------------------------------------------------------------------ 请求体
class CreateModelRequest(BaseModel):
    model_type: str = Field(..., description="模型类型（首期仅 condition_tree / funnel 可创建）")
    name: str = Field(..., description="模型显示名")
    description: str = ""
    template: str = "blank"
    model_id: Optional[str] = None


class DraftFromTextRequest(BaseModel):
    text: str = Field(..., description="中文选股文案")


class SaveDraftRequest(BaseModel):
    definition: Dict[str, Any]
    base_version: Optional[int] = None
    draft_revision: int = 0


class ValidateRequest(BaseModel):
    definition: Optional[Dict[str, Any]] = None


class PublishRequest(BaseModel):
    base_version: Optional[int] = None
    draft_revision: Optional[int] = None


class CopyToDraftRequest(BaseModel):
    draft_revision: Optional[int] = None


class DebugRuleRequest(BaseModel):
    rule: Dict[str, Any]
    records: List[Dict[str, Any]] = Field(default_factory=list)


class DebugNodeRequest(BaseModel):
    stage_id: Optional[str] = None
    stage: Optional[Dict[str, Any]] = None
    records: List[Dict[str, Any]] = Field(default_factory=list)


class RunRequest(BaseModel):
    records: Optional[List[Dict[str, Any]]] = None
    codes: Optional[str] = None
    all_market: bool = False
    as_of: Optional[str] = None
    lookback: int = 70
    request_id: Optional[str] = None


class ScheduleUpdateRequest(BaseModel):
    paused: Optional[bool] = None
    stages: Optional[Dict[str, str]] = None


class AssessmentRequest(BaseModel):
    """结果研究评估入参：候选行情切片由调用方提供，缺数据即失败关闭（不伪造）。"""

    records: List[Dict[str, Any]] = Field(default_factory=list, description="逐候选行情切片（含 code/dates/closes）")
    benchmarks: Optional[Dict[str, Any]] = None
    account_equity: Optional[float] = None
    risk_per_trade_pct: float = 1.0
    initial_cash: float = 1_000_000.0
    as_of: Optional[str] = None
    horizons: Optional[List[int]] = None
    history_observations: Optional[List[Dict[str, Any]]] = None


class TrackingPlanRequest(BaseModel):
    run_id: str
    codes: Optional[List[str]] = None
    mode: str = "t_plus_n"
    periods: Optional[List[int]] = None
    benchmark: Optional[str] = None
    frequency: Optional[str] = None
    base_prices: Optional[Dict[str, float]] = None


class EvaluationRequest(BaseModel):
    version: Optional[int] = None
    period: Optional[int] = None
    min_samples: Optional[int] = None
    min_observation_days: Optional[int] = None
    benchmark: Optional[str] = None


class TuningRequest(BaseModel):
    version: Optional[int] = None
    period: Optional[int] = None


class SuggestionStatusRequest(BaseModel):
    status: str = Field(..., description="仅支持 accepted / ignored（pending → accepted | ignored）")


# ------------------------------------------------------------------ 内部装配
def _version_repo() -> VersionRepository:
    return VersionRepository()


def _run_repo() -> RunRepository:
    return RunRepository()


def _active_plan(model_id: str) -> tuple[int, CompiledSelectionPlan]:
    """加载已激活版本并复算编译计划；`plan_hash` 不一致即拒绝（发布门禁 9）。"""
    repo = _version_repo()
    active = repo.active_version(model_id)
    if active is None:
        raise ModelCatalogError("MODEL_VERSION_NOT_FOUND", f"模型 {model_id} 尚未激活任何版本")
    definition = repo.definition_of(model_id, active)
    stored = repo.plan_of(model_id, active)
    plan = compile_definition(definition)
    if str(plan.plan_hash) != str(stored.get("plan_hash")):
        raise ModelCatalogError(
            "MODEL_VERSION_CONFLICT",
            "已发布计划与当前编译器复算结果不一致（compiler_version 已变更）：请重新发布新版本",
        )
    return int(active), plan


def _calendar_meta() -> Dict[str, Any]:
    try:
        return TradeCalendar.local_calendar_version(DB_PATH)
    except Exception:  # pragma: no cover - 本地库缺失
        return {"calendar_version": None, "calendar_available": False}


def _assemble_records(payload: RunRequest) -> Dict[str, Any]:
    """装配正式运行输入；数据不足/本地库不可读返回非 OK，不产出任何代码（发布门禁 5）。"""
    if payload.records:
        return {"status": STATUS_OK, "records": [dict(item) for item in payload.records], "gate": None}
    assembler = DataAssembler()
    try:
        codes = assembler.resolve_universe(
            codes=[c.strip() for c in str(payload.codes or "").split(",") if c.strip()],
            all_market=bool(payload.all_market),
        )
        gate = assembler.evaluate_data_gate(as_of=payload.as_of)
        if gate.get("state") == GATE_WAITING_DATA:
            return {"status": "WAITING_DATA", "records": [], "gate": gate}
        built = assembler.assemble_daily(
            codes, as_of=payload.as_of, lookback=int(payload.lookback or 70), algorithm_version="iss",
        )
    except Exception as exc:  # 本地库缺失/不可读：如实降级，不猜测数据
        return {"status": "SOURCE_ERROR", "records": [], "gate": None, "detail": str(exc)}
    if built.get("status") != STATUS_OK:
        return {"status": str(built.get("status")), "records": [], "gate": built.get("gate") or gate}
    return {"status": STATUS_OK, "records": list(built["records"]), "gate": gate, "manifest": built.get("manifest")}


def _run_id_for(plan: CompiledSelectionPlan) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"selection_{stamp}_{short_hash(str(plan.plan_hash))}"


def _candidate_trace(stages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    trace: List[Dict[str, Any]] = []
    for stage in stages:
        result = stage.get("result") or {}
        for item in result.get("rejected_records") or []:
            candidate = item.get("candidate") or {}
            trace.append({
                "stage_id": stage.get("stage_id"),
                "code": candidate.get("code"),
                "verdict": item.get("candidate_verdict"),
                "failed_rules": [r.get("rule_id") for r in item.get("failed_rules") or []],
                "unknown_rules": [r.get("rule_id") for r in item.get("unknown_rules") or []],
            })
        for item in result.get("passed_records") or []:
            trace.append({
                "stage_id": stage.get("stage_id"),
                "code": item.get("code"),
                "verdict": "PASS",
                "failed_rules": [],
                "unknown_rules": [],
            })
    return trace


# ------------------------------------------------------------------ §15.1 元数据
@router.get("/types")
async def list_types(_: AuthContext = Depends(require_selection("view"))) -> Dict[str, Any]:
    """列出模型类型、能力与可发布性（P2 类型标 publishable=false，不提供编辑器）。"""
    registry = build_default_type_registry()
    return _ok({"types": registry.to_list(), "publishable": registry.publishable_names})


@router.get("/rule-types")
async def list_rule_types(_: AuthContext = Depends(require_selection("view"))) -> Dict[str, Any]:
    """获取规则类型、维度与参数 Schema（Web 表单据此动态生成，S-06）。"""
    registry = build_default_rule_registry()
    items = []
    for name in registry.names:
        meta = registry.get(name).to_dict()
        meta["form_annotations"] = registry.form_annotations(name)
        meta["defaults"] = registry.defaults(name)
        items.append(meta)
    categories = sorted({item["category"] for item in items if item["category"]})
    return _ok({"rule_types": items, "categories": categories})


# 注意：以下两个「单段静态路径」必须注册在 `GET /{model_id}` 之前，否则会被其吞掉。
@router.get("/results")
async def list_results_endpoint(
    model_id: Optional[str] = Query(default=None),
    signal_date: Optional[str] = Query(default=None),
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    items = _run_repo().query_signals(model_id=model_id, signal_date=signal_date)
    return _ok({"results": items, "total": len(items)})


@router.get("/data-health")
async def data_health_endpoint(_: AuthContext = Depends(require_selection("view"))) -> Any:
    """本地数据网关水位与同步健康度；无本地库即如实降级，不伪造覆盖率。"""
    calendar = _calendar_meta()
    try:
        assembler = DataAssembler()
        gate = assembler.evaluate_data_gate()
        ready = gate.get("state") != GATE_WAITING_DATA
        return _ok({"data_gate": gate, "calendar": calendar},
                   watermark=_watermark(availability="ok" if ready else "degraded",
                                        degraded_reason=None if ready else "DATA_WATERMARK_NOT_FINALIZED",
                                        eligible_for_signal=ready))
    except Exception as exc:
        return _ok({"data_gate": None, "calendar": calendar, "detail": str(exc)},
                   watermark=_watermark(availability="unsupported", degraded_reason="LOCAL_DATA_UNAVAILABLE",
                                        eligible_for_signal=False))


# ------------------------------------------------------------------ §15.1 模型与草稿
@router.get("")
async def list_models_endpoint(
    model_type: Optional[str] = Query(default=None),
    _: AuthContext = Depends(require_selection("view")),
) -> Dict[str, Any]:
    items = list_models(model_type=model_type)
    return _ok({"models": items, "total": len(items)})


@router.post("")
async def create_model_endpoint(
    payload: CreateModelRequest,
    ctx: AuthContext = Depends(require_selection("create")),
) -> Any:
    try:
        created = create_model(
            model_type=payload.model_type,
            name=payload.name,
            description=payload.description,
            template=payload.template,
            model_id=payload.model_id,
            operator=ctx.username,
        )
    except ModelCatalogError as exc:
        return _guard(exc)
    _audit(ctx, "create", f"创建模型 {created['model_id']}（{payload.model_type}）")
    return _ok(created)


@router.post("/drafts/from-text")
async def draft_from_text_endpoint(
    payload: DraftFromTextRequest,
    ctx: AuthContext = Depends(require_selection("create")),
) -> Any:
    try:
        parsed = draft_from_text(payload.text)
    except ModelCatalogError as exc:
        return _guard(exc)
    _audit(ctx, "draft_from_text", "文案解析草稿（未激活）")
    return _ok(parsed)


@router.get("/{model_id}")
async def get_model_endpoint(
    model_id: str,
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    try:
        detail = get_model(model_id)
    except (ModelCatalogError, ValueError) as exc:
        return _guard(exc if isinstance(exc, ModelCatalogError) else ModelCatalogError("MODEL_VERSION_NOT_FOUND", str(exc)))
    return _ok(detail)


@router.patch("/{model_id}/draft")
async def save_draft_endpoint(
    model_id: str,
    payload: SaveDraftRequest,
    ctx: AuthContext = Depends(require_selection("edit")),
) -> Any:
    repo = DefinitionRepository()
    try:
        saved = repo.save_draft(
            model_id,
            payload.definition,
            base_version=payload.base_version,
            draft_revision=int(payload.draft_revision),
            operator=ctx.username,
        )
    except DraftConflictError as exc:
        return _fail("MODEL_DRAFT_CONFLICT", str(exc))
    except (SelectionSchemaError, ValueError) as exc:
        code = getattr(exc, "code", "MODEL_CONFIG_INVALID")
        return _fail(str(code), str(exc))
    _audit(ctx, "save_draft", f"保存草稿 {model_id} rev={saved['draft_revision']}")
    return _ok(saved)


@router.post("/{model_id}/validate")
async def validate_endpoint(
    model_id: str,
    payload: ValidateRequest = Body(default=ValidateRequest()),
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    """校验草稿或显式提交的定义：编译期失败关闭（发布门禁 8）。"""
    definition = payload.definition
    if definition is None:
        draft = DefinitionRepository().load_draft(model_id)
        if draft is None:
            return _fail("MODEL_VERSION_NOT_FOUND", f"模型 {model_id} 无草稿可校验")
        definition = draft["definition"]
    try:
        plan = compile_definition(definition)
    except (ModelCompilerError, SelectionSchemaError, ValueError) as exc:
        code = getattr(exc, "code", "MODEL_CONFIG_INVALID")
        return _fail(str(code), str(exc))
    return _ok({
        "valid": True,
        "plan_hash": plan.plan_hash,
        "compiler_version": plan.compiler_version,
        "stage_count": len(plan.stages),
        "stages": [{"id": s.id, "kind": s.kind, "scope": s.scope, "trigger": s.trigger} for s in plan.stages],
    })


# ------------------------------------------------------------------ §15.1 版本仓库
@router.get("/{model_id}/versions")
async def list_versions_endpoint(
    model_id: str,
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    try:
        repo = _version_repo()
        versions = repo.list_versions(model_id)
        runs = _run_repo()
        for item in versions:
            item["run_reference_count"] = len(
                runs.list_runs(model_id, version=int(item["version"]))
            )
        return _ok({"model_id": model_id, "active_version": repo.active_version(model_id), "versions": versions})
    except ValueError as exc:
        return _fail("MODEL_VERSION_NOT_FOUND", str(exc))


@router.get("/{model_id}/version-diff")
async def version_diff_endpoint(
    model_id: str,
    from_version: int = Query(..., alias="from"),
    to_version: int = Query(..., alias="to"),
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    repo = _version_repo()
    try:
        left = repo.get_version(model_id, from_version)
        right = repo.get_version(model_id, to_version)
        left_def = repo.definition_of(model_id, from_version)
        right_def = repo.definition_of(model_id, to_version)
    except VersionNotFoundError as exc:
        return _fail("MODEL_VERSION_NOT_FOUND", str(exc))
    keys = sorted(set(left_def) | set(right_def))
    changed = [k for k in keys if json.dumps(left_def.get(k), sort_keys=True, default=str) != json.dumps(right_def.get(k), sort_keys=True, default=str)]
    return _ok({
        "model_id": model_id,
        "from": {"version": from_version, "definition_hash": left["definition_hash"], "plan_hash": left["plan_hash"]},
        "to": {"version": to_version, "definition_hash": right["definition_hash"], "plan_hash": right["plan_hash"]},
        "changed_keys": changed,
        "identical": not changed,
    })


@router.get("/{model_id}/versions/{version}")
async def get_version_endpoint(
    model_id: str,
    version: int,
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    repo = _version_repo()
    try:
        record = repo.get_version(model_id, version)
        definition = repo.definition_of(model_id, version)
        plan = repo.plan_of(model_id, version)
    except VersionNotFoundError as exc:
        return _fail("MODEL_VERSION_NOT_FOUND", str(exc))
    return _ok({
        "record": record,
        "definition": definition,
        "plan_summary": {
            "plan_hash": plan.get("plan_hash"),
            "compiler_version": plan.get("compiler_version"),
            "stage_count": len(plan.get("stages") or []),
            "stages": [
                {"id": s.get("id"), "kind": s.get("kind"), "scope": s.get("scope"), "trigger": s.get("trigger")}
                for s in plan.get("stages") or []
            ],
        },
    })


@router.post("/{model_id}/versions")
async def publish_endpoint(
    model_id: str,
    payload: PublishRequest,
    ctx: AuthContext = Depends(require_selection("publish")),
) -> Any:
    """把校验通过的草稿发布为服务端分配的不可变新版本（发布号单调、内容不可变）。"""
    draft_repo = DefinitionRepository()
    draft = draft_repo.load_draft(model_id)
    if draft is None:
        return _fail("MODEL_VERSION_NOT_FOUND", f"模型 {model_id} 无草稿可发布")
    try:
        plan = compile_definition(draft["definition"])
    except (ModelCompilerError, SelectionSchemaError, ValueError) as exc:
        code = getattr(exc, "code", "MODEL_CONFIG_INVALID")
        return _fail(str(code), str(exc))
    try:
        record = _version_repo().publish(
            model_id,
            draft["definition"],
            plan,
            base_version=payload.base_version if payload.base_version is not None else draft["base_version"],
            draft_revision=payload.draft_revision if payload.draft_revision is not None else draft["draft_revision"],
            operator=ctx.username,
            draft_repository=draft_repo,
        )
    except DraftConflictError as exc:
        return _fail("MODEL_DRAFT_CONFLICT", str(exc))
    except VersionConflictError as exc:
        return _fail("MODEL_VERSION_CONFLICT", str(exc))
    _audit(ctx, "publish", f"发布 {model_id} v{record['version']}")
    return _ok(record)


@router.post("/{model_id}/versions/{version}/copy-to-draft")
async def copy_to_draft_endpoint(
    model_id: str,
    version: int,
    payload: CopyToDraftRequest,
    ctx: AuthContext = Depends(require_selection("edit")),
) -> Any:
    repo = _version_repo()
    draft_repo = DefinitionRepository()
    try:
        definition = repo.definition_of(model_id, version)
    except VersionNotFoundError as exc:
        return _fail("MODEL_VERSION_NOT_FOUND", str(exc))
    existing = draft_repo.load_draft(model_id)
    if existing is not None:
        if payload.draft_revision is not None and int(existing["draft_revision"]) != int(payload.draft_revision):
            return _fail("MODEL_DRAFT_CONFLICT", "草稿修订号已变化，拒绝覆盖")
        # 以指定版本为基线：先清除旧草稿再按新基线重建（保留「需校验修订号」语义）
        draft_repo.delete_draft(model_id)
    saved = draft_repo.create_draft(model_id, definition, base_version=int(version), operator=ctx.username)
    _audit(ctx, "copy_to_draft", f"{model_id} v{version} → 草稿")
    return _ok(saved)


@router.post("/{model_id}/versions/{version}/archive")
async def archive_endpoint(
    model_id: str,
    version: int,
    ctx: AuthContext = Depends(require_selection("publish")),
) -> Any:
    try:
        record = _version_repo().archive(model_id, version, operator=ctx.username)
    except VersionConflictError as exc:
        return _fail("MODEL_VERSION_CONFLICT", str(exc))
    except VersionNotFoundError as exc:
        return _fail("MODEL_VERSION_NOT_FOUND", str(exc))
    _audit(ctx, "archive", f"归档 {model_id} v{version}")
    return _ok(record)


@router.post("/{model_id}/activate/{version}")
async def activate_endpoint(
    model_id: str,
    version: int,
    ctx: AuthContext = Depends(require_selection("activate")),
) -> Any:
    try:
        result = _version_repo().activate(model_id, version, operator=ctx.username)
    except VersionConflictError as exc:
        return _fail("MODEL_VERSION_CONFLICT", str(exc))
    except VersionNotFoundError as exc:
        return _fail("MODEL_VERSION_NOT_FOUND", str(exc))
    _audit(ctx, "activate", f"激活 {model_id} v{version}")
    return _ok(result)


# ------------------------------------------------------------------ §15.2 调试（与正式运行隔离）
def _debug_watermark() -> Dict[str, Any]:
    return _watermark(eligible_for_signal=False, extra={"debug": True})


@router.post("/{model_id}/debug/rule")
async def debug_rule_endpoint(
    model_id: str,
    payload: DebugRuleRequest,
    _: AuthContext = Depends(require_selection("debug")),
) -> Any:
    """单规则调试：只评估给定记录，不落运行目录、不发信号（发布门禁 10）。"""
    engine = FunnelEngine(build_stock_rule_registry())
    stage = {"id": "__debug_rule__", "scope": "candidate_filter", "logic": "all",
             "rules": [dict(payload.rule)]}
    try:
        result = engine.run_stage(stage, payload.records, {})
    except ValueError as exc:
        return _fail("MODEL_RULE_UNKNOWN", str(exc), watermark=_debug_watermark())
    return _ok(result.to_dict(), watermark=_debug_watermark())


@router.post("/{model_id}/debug/node")
async def debug_node_endpoint(
    model_id: str,
    payload: DebugNodeRequest,
    _: AuthContext = Depends(require_selection("debug")),
) -> Any:
    """条件组/阶段调试：在给定记录上预演单层，不落运行目录、不发信号。"""
    engine = FunnelEngine(build_stock_rule_registry())
    if payload.stage is not None:
        stage = dict(payload.stage)
    elif payload.stage_id:
        try:
            _, plan = _active_plan(model_id)
        except ModelCatalogError:
            draft = DefinitionRepository().load_draft(model_id)
            if draft is None:
                return _fail("MODEL_VERSION_NOT_FOUND", f"模型 {model_id} 无可用定义", watermark=_debug_watermark())
            plan = compile_definition(draft["definition"])
        matched = [s for s in plan.stages if s.id == payload.stage_id]
        if not matched:
            return _fail("MODEL_CONFIG_INVALID", f"编译计划不存在阶段 {payload.stage_id}", watermark=_debug_watermark())
        stage = matched[0].to_engine_stage()
    else:
        return _fail("MODEL_CONFIG_INVALID", "需要 stage_id 或 stage 之一", watermark=_debug_watermark())
    try:
        result = engine.run_stage(stage, payload.records, {})
    except ValueError as exc:
        return _fail("MODEL_CONFIG_INVALID", str(exc), watermark=_debug_watermark())
    return _ok(result.to_dict(), watermark=_debug_watermark())


# ------------------------------------------------------------------ §15.2 正式运行
@router.post("/{model_id}/runs")
async def create_run_endpoint(
    model_id: str,
    payload: RunRequest,
    ctx: AuthContext = Depends(require_selection("run")),
) -> Any:
    """手工创建正式运行：只执行已激活版本；相同 request_id 重试返回原运行。"""
    repo = _run_repo()
    if payload.request_id:
        for existing in repo.list_runs(model_id):
            if str(existing.get("request_id") or "") == str(payload.request_id):
                return _ok({"run": existing, "deduplicated": True})

    try:
        active_version, plan = _active_plan(model_id)
    except ModelCatalogError as exc:
        return _guard(exc)

    assembled = _assemble_records(payload)
    calendar = _calendar_meta()
    if assembled.get("status") != STATUS_OK:
        gc = assembled.get("gate") or {}
        return _fail(
            "MODEL_DATA_MISSING",
            "本地数据水位未就绪，失败关闭：不产出任何候选代码（发布门禁 5）",
            watermark=_watermark(availability="degraded", degraded_reason="MODEL_DATA_MISSING",
                                 eligible_for_signal=False, extra={"data_gate": gc}),
            data={"gate": gc, "calendar": calendar},
        )

    run_id = _run_id_for(plan)
    trade_date = str((assembled.get("gate") or {}).get("trade_date") or payload.as_of or datetime.now().date().isoformat())[:10]
    context = {"calendar_version": calendar.get("calendar_version"),
               "calendar_available": calendar.get("calendar_available")}
    if assembled.get("manifest"):
        context["data_snapshots"] = [assembled["manifest"]]
    if assembled.get("gate"):
        context["data_gate"] = assembled["gate"]

    repo.save_run({
        "run_id": run_id, "model_id": model_id, "model_version": active_version,
        "model_type": str((plan.source_model or {}).get("model_type") or ""),
        "trigger_type": "manual", "triggered_by": ctx.username,
        "request_id": payload.request_id, "status": "RUNNING",
        "signal_trade_date": trade_date, "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "plan_hash": plan.plan_hash, "compiler_version": plan.compiler_version,
    })

    orchestrator = SelectionModelOrchestrator()
    try:
        outcome = orchestrator.run_all(
            plan, assembled["records"], context,
            run_id=run_id, trigger_type="manual", triggered_by=ctx.username,
        )
    except Exception as exc:  # pragma: no cover - 执行期异常
        repo.update_run(run_id, {"status": "FAILED", "error": str(exc)})
        return _fail("MODEL_CRITICAL_DEPENDENCY_FAILED", str(exc))

    stages = outcome.get("stages") or []
    repo.save_run_stages(run_id, stages)
    repo.save_run_candidates(run_id, _candidate_trace(stages))
    repo.update_run(run_id, {
        "status": outcome.get("status"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "final_stage": outcome.get("final_stage"),
        "selected_codes": outcome.get("selected_codes") or [],
        "selected_count": outcome.get("selected_count") or 0,
        "run_metadata": outcome.get("run_metadata") or {},
    })

    if outcome.get("status") == "COMPLETED" and outcome.get("selected_codes"):
        repo.save_signals(trade_date, model_id, {
            "model_id": model_id, "model_version": active_version, "signal_trade_date": trade_date,
            "run_id": run_id, "plan_hash": plan.plan_hash,
            "signal_codes": outcome["selected_codes"],
        })
    _audit(ctx, "run", f"手工运行 {model_id} v{active_version} → {outcome.get('status')}")
    return _ok({"run": repo.load_run(run_id), "run_id": run_id, "stages": stages,
                "selected_codes": outcome.get("selected_codes") or []})


@router.get("/{model_id}/runs")
async def list_runs_endpoint(
    model_id: str,
    version: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    trigger_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    repo = _run_repo()
    items = repo.list_runs(model_id, version=version, status=status, trigger_type=trigger_type, limit=limit, offset=offset)
    total = len(repo.list_runs(model_id, version=version, status=status, trigger_type=trigger_type))
    return _ok({"model_id": model_id, "runs": items, "total": total, "limit": limit, "offset": offset})


@router.get("/runs/{run_id}")
async def get_run_endpoint(run_id: str, _: AuthContext = Depends(require_selection("view"))) -> Any:
    run = _run_repo().load_run(run_id)
    if not run:
        return _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")
    return _ok({"run": run})


@router.get("/runs/{run_id}/nodes")
async def get_run_nodes_endpoint(run_id: str, _: AuthContext = Depends(require_selection("view"))) -> Any:
    run = _run_repo().load_run(run_id)
    if not run:
        return _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")
    return _ok({"run_id": run_id, "nodes": _run_repo().load_run_stages(run_id)})


@router.get("/runs/{run_id}/candidates")
async def get_run_candidates_endpoint(run_id: str, _: AuthContext = Depends(require_selection("view"))) -> Any:
    run = _run_repo().load_run(run_id)
    if not run:
        return _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")
    return _ok({"run_id": run_id, "candidates": _run_repo().load_run_candidates(run_id)})


@router.post("/runs/{run_id}/cancel")
async def cancel_run_endpoint(run_id: str, ctx: AuthContext = Depends(require_selection("run"))) -> Any:
    repo = _run_repo()
    run = repo.load_run(run_id)
    if not run:
        return _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")
    if str(run.get("status") or "") not in {"RUNNING", "QUEUED"}:
        return _fail("MODEL_RUN_REQUEST_CONFLICT", f"运行已处于终态 {run.get('status')}，无需取消")
    updated = repo.update_run(run_id, {"status": "CANCELLED", "cancelled_by": ctx.username})
    _audit(ctx, "cancel", f"取消运行 {run_id}")
    return _ok({"run": updated})


@router.get("/runs/{run_id}/events")
async def run_events_endpoint(
    run_id: str,
    follow: bool = Query(default=False),
    _: AuthContext = Depends(require_selection("view")),
):
    """SSE 运行事件流（W-01）：`run.started` / `stage.completed` / `run.finished` /
    `run.failed` / `heartbeat`，每事件挂载 `run_id` 与水印。"""
    import asyncio

    def _sse(event: str, data: Dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def _stream():
        repo = _run_repo()
        run = repo.load_run(run_id)
        if not run:
            yield _sse("run.failed", {"run_id": run_id, "error_code": "MODEL_RUN_NOT_FOUND",
                                      "watermark": _watermark(availability="unsupported", degraded_reason="MODEL_RUN_NOT_FOUND")})
            return
        yield _sse("run.started", {"run_id": run_id, "model_id": run.get("model_id"),
                                   "model_version": run.get("model_version"),
                                   "started_at": run.get("started_at"), "watermark": _watermark()})
        for stage in repo.load_run_stages(run_id):
            yield _sse("stage.completed", {"run_id": run_id, "stage_id": stage.get("stage_id"),
                                           "status": stage.get("status"), "input_count": stage.get("input_count"),
                                           "output_count": stage.get("output_count"), "watermark": _watermark()})
        final_status = str(run.get("status") or "")
        terminal = final_status in {"COMPLETED", "FAILED", "BLOCKED", "EMPTY", "WAITING_DATA", "CANCELLED"}
        if terminal:
            event = "run.failed" if final_status == "FAILED" else "run.finished"
            yield _sse(event, {"run_id": run_id, "status": final_status,
                               "selected_codes": run.get("selected_codes") or [], "watermark": _watermark()})
            yield _sse("heartbeat", {"run_id": run_id, "watermark": _watermark()})
            return
        for _ in range(60 if follow else 1):
            await asyncio.sleep(1)
            latest = repo.load_run(run_id) or {}
            status_now = str(latest.get("status") or "")
            if status_now in {"COMPLETED", "FAILED", "BLOCKED", "EMPTY", "WAITING_DATA", "CANCELLED"}:
                event = "run.failed" if status_now == "FAILED" else "run.finished"
                yield _sse(event, {"run_id": run_id, "status": status_now,
                                   "selected_codes": latest.get("selected_codes") or [], "watermark": _watermark()})
                return
            yield _sse("heartbeat", {"run_id": run_id, "status": status_now, "watermark": _watermark()})

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ §15.3 调度
@router.get("/{model_id}/schedule")
async def get_schedule_endpoint(model_id: str, _: AuthContext = Depends(require_selection("view"))) -> Any:
    store = ScheduleStore()
    override = store.load(model_id)
    windows: List[Dict[str, Any]] = []
    scheduler_next = None
    try:
        _, plan = _active_plan(model_id)
        scheduler = SelectionScheduler(plan)
        now = datetime.now().astimezone()
        windows = [w.__dict__ for w in scheduler.windows]
        scheduler_next = scheduler.next_run_at(now)
    except ModelCatalogError:
        windows = []
    return _ok({"model_id": model_id, "paused": override["paused"], "overrides": override["stages"],
                "windows": windows, "next_run_at": scheduler_next, "updated_at": override["updated_at"]})


@router.put("/{model_id}/schedule")
async def update_schedule_endpoint(
    model_id: str,
    payload: ScheduleUpdateRequest,
    ctx: AuthContext = Depends(require_selection("activate")),
) -> Any:
    for stage_id, window in (payload.stages or {}).items():
        try:
            parse_schedule(window, stage_id=stage_id)
        except ValueError as exc:
            return _fail("MODEL_CONFIG_INVALID", str(exc))
    store = ScheduleStore()
    saved = store.save(model_id, {"paused": payload.paused, "stages": payload.stages}, operator=ctx.username)
    _audit(ctx, "update_schedule", f"更新调度 {model_id}")
    return _ok(saved)


@router.post("/{model_id}/pause")
async def pause_endpoint(model_id: str, ctx: AuthContext = Depends(require_selection("activate"))) -> Any:
    saved = ScheduleStore().set_paused(model_id, True, operator=ctx.username)
    _audit(ctx, "pause", f"暂停自动运行 {model_id}")
    return _ok(saved)


@router.post("/{model_id}/resume")
async def resume_endpoint(model_id: str, ctx: AuthContext = Depends(require_selection("activate"))) -> Any:
    saved = ScheduleStore().set_paused(model_id, False, operator=ctx.username)
    _audit(ctx, "resume", f"恢复自动运行 {model_id}")
    return _ok(saved)


# ------------------------------------------------------------------ §15.3 结果与数据健康
# （`/results`、`/data-health` 两个单段静态路径已前置注册，避免被 `/{model_id}` 吞掉。）


# ------------------------------------------------------------------ §15.3 阶段 E：结果研究（E1）
def _records_by_code(records: Any) -> Dict[str, Dict[str, Any]]:
    mapped: Dict[str, Dict[str, Any]] = {}
    for item in records or []:
        code = str((item or {}).get("code") or "").strip()
        if code:
            mapped[code] = dict(item)
    return mapped


@router.post("/runs/{run_id}/assessments")
async def generate_assessments_endpoint(
    run_id: str,
    payload: AssessmentRequest,
    ctx: AuthContext = Depends(require_selection("evaluate")),
) -> Any:
    """为最终候选生成结果研究评估；缺候选行情切片即失败关闭（不伪造任何数值）。"""
    if not _run_repo().load_run(run_id):
        return _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")
    records = _records_by_code(payload.records)
    if not records:
        return _fail(
            "MODEL_DATA_MISSING",
            "缺少候选行情切片，失败关闭：不生成任何评估数值（发布门禁 5）",
            watermark=_watermark(availability="degraded", degraded_reason="MODEL_DATA_MISSING",
                                 eligible_for_signal=False),
        )
    try:
        assessment = ResultAssessmentService().generate(
            run_id,
            records_by_code=records,
            benchmarks=payload.benchmarks,
            account_equity=payload.account_equity,
            risk_per_trade_pct=payload.risk_per_trade_pct,
            initial_cash=payload.initial_cash,
            as_of=payload.as_of,
            horizons=payload.horizons,
            history_observations=payload.history_observations,
        )
    except ResultAssessmentError as exc:
        return _fail(exc.code, str(exc))
    _audit(ctx, "assess", f"生成结果研究评估 {run_id}")
    return _ok({"run_id": run_id, "assessment": assessment})


@router.get("/runs/{run_id}/assessments")
async def get_assessments_endpoint(run_id: str, _: AuthContext = Depends(require_selection("view"))) -> Any:
    """获取个股信息、入选证据、回测摘要与建仓持股策略（研究方案，非交易指令）。"""
    if not _run_repo().load_run(run_id):
        return _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")
    payload = ResultAssessmentService().load(run_id)
    if not payload:
        return _ok({"run_id": run_id, "assessments": [], "generated": False},
                   watermark=_watermark(availability="unsupported", degraded_reason="ASSESSMENT_NOT_GENERATED"))
    return _ok({"run_id": run_id, "assessment": payload})


# ------------------------------------------------------------------ §15.3 阶段 E：持续跟踪（E3）
@router.post("/tracking-plans")
async def create_tracking_plan_endpoint(
    payload: TrackingPlanRequest,
    ctx: AuthContext = Depends(require_selection("track")),
) -> Any:
    """创建实时/T+N 跟踪计划；基准价格必须来自真实信号价，不接受虚构。"""
    run = _run_repo().load_run(payload.run_id)
    if not run:
        return _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {payload.run_id}")
    codes = [str(c) for c in (payload.codes or run.get("selected_codes") or [])]
    if not codes:
        return _fail("MODEL_DATA_MISSING", "该运行没有最终候选，无法创建跟踪计划")
    base_prices = dict(payload.base_prices or {})
    missing = [code for code in codes if not base_prices.get(code)]
    if missing:
        return _fail("MODEL_DATA_MISSING", f"缺少基准价格，失败关闭：{missing}")
    try:
        plan = TrackingService().create_plan(
            run_id=str(run.get("run_id")),
            model_id=str(run.get("model_id") or ""),
            model_version=int(run.get("model_version") or 0),
            signal_date=str(run.get("signal_trade_date") or ""),
            codes=codes,
            base_prices=base_prices,
            mode=payload.mode,
            periods=payload.periods or DEFAULT_PERIODS,
            benchmark=payload.benchmark,
            frequency=payload.frequency,
        )
    except TrackingError as exc:
        return _fail(exc.code, str(exc))
    except ValueError as exc:
        return _fail(getattr(exc, "code", "MODEL_CONFIG_INVALID"), str(exc))
    _audit(ctx, "track_create", f"创建跟踪计划 {plan['tracking_id']}")
    return _ok({"plan": plan})


@router.get("/tracking-plans/{tracking_id}")
async def get_tracking_plan_endpoint(tracking_id: str, _: AuthContext = Depends(require_selection("view"))) -> Any:
    try:
        return _ok(TrackingService().summary(tracking_id))
    except TrackingError as exc:
        return _fail(exc.code, str(exc))
    except ValueError as exc:
        return _fail(getattr(exc, "code", "TRACKING_PLAN_NOT_FOUND"), str(exc))


@router.get("/tracking-plans/{tracking_id}/observations")
async def get_tracking_observations_endpoint(
    tracking_id: str,
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    """查询不可变跟踪序列（只追加，不覆盖历史观察）。"""
    service = TrackingService()
    try:
        service.get_plan(tracking_id)
    except TrackingError as exc:
        return _fail(exc.code, str(exc))
    except ValueError as exc:
        return _fail(getattr(exc, "code", "TRACKING_PLAN_NOT_FOUND"), str(exc))
    observations = service.load_observations(tracking_id)
    return _ok({"tracking_id": tracking_id, "observations": observations, "total": len(observations)})


# ------------------------------------------------------------------ §15.3 阶段 E：模型评价与调优（E4/E5）
def _resolve_version(model_id: str, requested: Optional[int]) -> Optional[int]:
    if requested is not None:
        return int(requested)
    return _version_repo().active_version(model_id)


@router.post("/{model_id}/evaluations")
async def create_evaluation_endpoint(
    model_id: str,
    payload: EvaluationRequest,
    ctx: AuthContext = Depends(require_selection("evaluate")),
) -> Any:
    """按模型版本与观察窗口生成综合评价；样本不足返回 `EVALUATION_SAMPLE_INSUFFICIENT`。"""
    try:
        version = _resolve_version(model_id, payload.version)
    except ValueError as exc:  # 非法 model_id（防目录穿越）
        return _fail("MODEL_CONFIG_INVALID", str(exc))
    if version is None:
        return _fail("MODEL_VERSION_NOT_FOUND", f"模型 {model_id} 尚未激活任何版本")
    evaluation = ModelEvaluator().evaluate(
        model_id,
        int(version),
        period=payload.period,
        min_samples=payload.min_samples if payload.min_samples is not None else DEFAULT_MIN_SAMPLES,
        min_observation_days=(
            payload.min_observation_days if payload.min_observation_days is not None else DEFAULT_MIN_OBSERVATION_DAYS
        ),
        benchmark=payload.benchmark or DEFAULT_BENCHMARK,
    )
    _audit(ctx, "evaluate", f"生成模型评价 {model_id} v{version} → {evaluation.get('status')}")
    wm = _watermark() if evaluation.get("status") == "OK" else _watermark(
        availability="degraded", degraded_reason="EVALUATION_SAMPLE_INSUFFICIENT", eligible_for_signal=False
    )
    return _ok({"evaluation": evaluation}, watermark=wm)


@router.get("/{model_id}/evaluations/{evaluation_id}")
async def get_evaluation_endpoint(
    model_id: str,
    evaluation_id: str,
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    payload = ModelEvaluator().load(model_id, evaluation_id)
    if not payload:
        return _fail("MODEL_DATA_MISSING", f"评价记录不存在: {evaluation_id}")
    return _ok({"evaluation": payload})


@router.post("/{model_id}/tuning-suggestions")
async def create_tuning_suggestions_endpoint(
    model_id: str,
    payload: TuningRequest,
    ctx: AuthContext = Depends(require_selection("evaluate")),
) -> Any:
    """基于历史运行及其跟踪结果生成只读优化建议；样本不足只登记"继续观察"。"""
    try:
        version = _resolve_version(model_id, payload.version)
    except ValueError as exc:
        return _fail("MODEL_CONFIG_INVALID", str(exc))
    if version is None:
        return _fail("MODEL_VERSION_NOT_FOUND", f"模型 {model_id} 尚未激活任何版本")
    result = OptimizationAdvisor().suggest(model_id, int(version), period=payload.period)
    _audit(ctx, "tune_suggest", f"生成优化建议 {model_id} v{version}")
    return _ok(result)


@router.get("/{model_id}/tuning-suggestions")
async def list_tuning_suggestions_endpoint(
    model_id: str,
    _: AuthContext = Depends(require_selection("view")),
) -> Any:
    """列出建议；来源版本与当前活动版本不一致时重新判定为 `STALE`。"""
    active = _version_repo().active_version(model_id)
    return _ok(OptimizationAdvisor().list_suggestions(model_id, active_version=active))


@router.post("/{model_id}/tuning-suggestions/{suggestion_id}/status")
async def mark_suggestion_status_endpoint(
    model_id: str,
    suggestion_id: str,
    payload: SuggestionStatusRequest,
    ctx: AuthContext = Depends(require_selection("evaluate")),
) -> Any:
    """标记建议处理状态（仅 accepted / ignored）；不回写模型、不自动改版。"""
    if payload.status not in {STATUS_ACCEPTED, STATUS_IGNORED}:
        return _fail("MODEL_CONFIG_INVALID", "仅支持 accepted / ignored 两种处理状态")
    try:
        record = OptimizationAdvisor().mark_status(
            model_id, suggestion_id, payload.status, operator=ctx.username
        )
    except OptimizationAdvisorError as exc:
        return _fail(exc.code, str(exc))
    _audit(ctx, "tune_status", f"标记建议 {suggestion_id} → {payload.status}")
    return _ok({"suggestion": record})


__all__ = ["router"]