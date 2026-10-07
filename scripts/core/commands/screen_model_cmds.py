# -*- coding: utf-8 -*-
"""ISS「智能选股系统」阶段 E 结果研究类 CLI（assess / track / evaluate / tune）。

与后端 `server/api/selection_models.py` 的阶段 E 端点语义完全一致，统一包裹
`{status, data, error_code?}`，并严格遵守失败关闭（fail-closed）铁律：

- **不加码不伪造**：数据不足一律失败关闭，绝不产出任何伪造的候选、价格或指标；
- `assess`：为已落盘运行生成逐候选结果研究评估；缺运行 → `MODEL_RUN_NOT_FOUND`，
  缺候选行情切片 → `MODEL_DATA_MISSING`（且不生成任何评估数值）；
- `track`：实时 / T+N 跟踪计划创建、查询与到期 Tick；Tick 水位未就绪只报 `WAITING_DATA`，
  绝不写伪观察值（发布门禁 14）；
- `evaluate`：按模型版本汇总历史样本；样本不足 → `degraded` +
  `EVALUATION_SAMPLE_INSUFFICIENT`，不出强结论（发布门禁 16）；
- `tune`：只读优化建议，绝不自动改版（发布门禁 19）。

失败关闭与 `funnel` 一致：先交付 JSON 包裹，再以非零退出码结束（不可用即不可交付）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from core.selection_models.model_evaluator import ModelEvaluator
from core.selection_models.optimization_advisor import OptimizationAdvisor
from core.selection_models.result_assessment import (
    ResultAssessmentError,
    ResultAssessmentService,
)
from core.selection_models.run_repository import RunRepository
from core.selection_models.tracker_scheduler import TrackerScheduler
from core.selection_models.tracking_service import (
    DEFAULT_PERIODS,
    TrackingError,
    TrackingService,
)
from core.selection_models.version_repository import VersionRepository

#: 失败关闭退出码（数据不足/运行缺失等不可交付状态）。
FAIL_CLOSED_EXIT_CODE = 3
#: 用法错误退出码（缺少子命令等）。
USAGE_EXIT_CODE = 2


# ------------------------------------------------------------------ 基础设施
def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _ok(data: Any) -> Dict[str, Any]:
    """成功包裹：`{status: ok, data}`。"""
    return {"status": "ok", "data": data}


def _fail(
    error_code: str,
    message: str,
    *,
    data: Any = None,
    status: str = "error",
    exit_code: int = FAIL_CLOSED_EXIT_CODE,
) -> None:
    """失败关闭：交付包裹后以非零退出码结束，绝不返回任何伪造数值。"""
    _emit({"status": status, "data": data, "error_code": error_code, "message": message})
    raise SystemExit(exit_code)


def _read_json(value: str) -> Any:
    """读取 JSON 文件路径；`-` 表示从 stdin 读取。"""
    if value == "-":
        return json.load(sys.stdin)
    return json.loads(Path(value).read_text(encoding="utf-8"))


def _load_json_arg(value: str) -> Any:
    """解析「内联 JSON 字符串或文件路径」两种形态（用于 `--base-prices-json`）。"""
    text = str(value).strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    return json.loads(Path(text).read_text(encoding="utf-8"))


def _split_codes(value: Optional[str]) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _split_ints(value: Optional[str]) -> Optional[List[int]]:
    """把 `1,3,5` 形态解析为正整数列表；未提供返回 `None`（交由服务层取默认值）。"""
    if value is None:
        return None
    return [int(part) for part in str(value).split(",") if str(part).strip()]


def _records_by_code(records: Any) -> Dict[str, Dict[str, Any]]:
    """把候选行情切片列表按 `code` 归并；缺 code 的片段一律丢弃，不猜测归属。"""
    mapped: Dict[str, Dict[str, Any]] = {}
    for item in records or []:
        code = str((item or {}).get("code") or "").strip()
        if code:
            mapped[code] = dict(item)
    return mapped


def _resolve_version(model_id: str, requested: Optional[int]) -> Optional[int]:
    """未显式指定版本时回落到已激活版本；无激活版本返回 `None`（失败关闭）。"""
    if requested is not None:
        return int(requested)
    return VersionRepository().active_version(model_id)


# ------------------------------------------------------------------ assess（E1）
def _cmd_assess(args) -> None:
    """为已落盘运行生成逐候选结果研究评估；缺运行或缺行情切片即失败关闭。"""
    run_id = str(getattr(args, "run", "") or "")
    if not run_id:
        _fail("MODEL_RUN_NOT_FOUND", "需要 --run 指定运行 ID", exit_code=USAGE_EXIT_CODE)
    if not RunRepository().load_run(run_id):
        _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")

    records_path = getattr(args, "records", None)
    records: Any = []
    if records_path:
        try:
            records = _read_json(records_path)
        except (OSError, ValueError) as exc:
            _fail("MODEL_DATA_MISSING", f"候选行情切片不可读: {exc}")
    records_by_code = _records_by_code(records)
    if not records_by_code:
        _fail(
            "MODEL_DATA_MISSING",
            "缺少候选行情切片，失败关闭：不生成任何评估数值（发布门禁 5）",
        )

    try:
        assessment = ResultAssessmentService().generate(
            run_id,
            records_by_code=records_by_code,
            account_equity=getattr(args, "account_equity", None),
            risk_per_trade_pct=(
                args.risk_per_trade_pct if getattr(args, "risk_per_trade_pct", None) is not None else 1.0
            ),
            initial_cash=(
                args.initial_cash if getattr(args, "initial_cash", None) is not None else 1_000_000.0
            ),
            as_of=getattr(args, "as_of", None),
            horizons=_split_ints(getattr(args, "horizons", None)),
        )
    except ResultAssessmentError as exc:
        _fail(exc.code, str(exc))
    _emit(_ok({"run_id": run_id, "assessment": assessment}))


# ------------------------------------------------------------------ track（E3）
def _cmd_track_create(args) -> None:
    """创建实时 / T+N 跟踪计划；基准价格必须来自真实信号价，缺一即失败关闭。"""
    run_id = str(getattr(args, "run", "") or "")
    if not run_id:
        _fail("MODEL_RUN_NOT_FOUND", "需要 --run 指定运行 ID", exit_code=USAGE_EXIT_CODE)
    run = RunRepository().load_run(run_id)
    if not run:
        _fail("MODEL_RUN_NOT_FOUND", f"运行不存在: {run_id}")

    codes = _split_codes(getattr(args, "codes", None)) or [str(c) for c in (run.get("selected_codes") or [])]
    if not codes:
        _fail("MODEL_DATA_MISSING", "该运行没有最终候选，无法创建跟踪计划")

    base_prices: Dict[str, float] = {}
    if getattr(args, "base_prices_json", None):
        try:
            loaded = _load_json_arg(args.base_prices_json)
        except (OSError, ValueError) as exc:
            _fail("MODEL_CONFIG_INVALID", f"基准价格 JSON 不可解析: {exc}")
        if not isinstance(loaded, Mapping):
            _fail("MODEL_CONFIG_INVALID", "基准价格 JSON 必须为 {code: price} 对象")
        base_prices = {str(k): float(v) for k, v in loaded.items()}

    missing = [code for code in codes if not base_prices.get(code)]
    if missing:
        _fail("MODEL_DATA_MISSING", f"缺少基准价格，失败关闭：{missing}")

    try:
        plan = TrackingService().create_plan(
            run_id=str(run.get("run_id")),
            model_id=str(run.get("model_id") or ""),
            model_version=int(run.get("model_version") or 0),
            signal_date=str(run.get("signal_trade_date") or ""),
            codes=codes,
            base_prices=base_prices,
            mode=str(getattr(args, "mode", None) or "t_plus_n"),
            periods=_split_ints(getattr(args, "periods", None)) or list(DEFAULT_PERIODS),
            benchmark=getattr(args, "benchmark", None),
        )
    except TrackingError as exc:
        _fail(exc.code, str(exc))
    except ValueError as exc:
        _fail(getattr(exc, "code", "MODEL_CONFIG_INVALID"), str(exc))
    _emit(_ok({"plan": plan}))


def _cmd_track_status(args) -> None:
    """查询跟踪计划与不可变观察序列。"""
    tracking_id = str(getattr(args, "tracking_id", "") or "")
    if not tracking_id:
        _fail("TRACKING_PLAN_NOT_FOUND", "需要 --tracking-id 指定跟踪计划", exit_code=USAGE_EXIT_CODE)
    try:
        summary = TrackingService().summary(tracking_id)
    except TrackingError as exc:
        _fail(exc.code, str(exc))
    except ValueError as exc:
        _fail(getattr(exc, "code", "TRACKING_PLAN_NOT_FOUND"), str(exc))
    _emit(_ok(summary))


def _cmd_track_tick(args) -> None:
    """执行一次 Tracker Tick：水位未就绪报 `WAITING_DATA`，绝不写伪观察值（门禁 14）。"""
    result = TrackerScheduler().tick()
    if int(result.get("waiting_data") or 0) > 0:
        _emit({
            "status": "WAITING_DATA",
            "data": result,
            "error_code": "TRACKING_WAITING_DATA",
            "message": "跟踪观察水位未就绪，未写入任何观察值（失败关闭，允许后续 Tick 重试）。",
        })
        return
    _emit(_ok(result))


def _cmd_track(args) -> None:
    sub = getattr(args, "screen_model_track_cmd", None)
    if sub == "create":
        _cmd_track_create(args)
    elif sub == "status":
        _cmd_track_status(args)
    elif sub == "tick":
        _cmd_track_tick(args)
    else:
        _fail("MODEL_CONFIG_INVALID", "track 需要子命令: create / status / tick", exit_code=USAGE_EXIT_CODE)


# ------------------------------------------------------------------ evaluate（E4）
def _cmd_evaluate(args) -> None:
    """按模型版本生成综合评价；样本不足返回 `degraded`，绝不臆造指标。"""
    model_id = str(getattr(args, "model", "") or "")
    if not model_id:
        _fail("MODEL_CONFIG_INVALID", "需要 --model 指定模型 ID", exit_code=USAGE_EXIT_CODE)
    try:
        version = _resolve_version(model_id, getattr(args, "version", None))
    except ValueError as exc:  # 非法 model_id（防目录穿越）
        _fail("MODEL_CONFIG_INVALID", str(exc))
    if version is None:
        _fail("MODEL_VERSION_NOT_FOUND", f"模型 {model_id} 尚未激活任何版本")

    kwargs: Dict[str, Any] = {"period": getattr(args, "period", None)}
    if getattr(args, "min_samples", None) is not None:
        kwargs["min_samples"] = int(args.min_samples)
    if getattr(args, "min_observation_days", None) is not None:
        kwargs["min_observation_days"] = int(args.min_observation_days)
    if getattr(args, "benchmark", None):
        kwargs["benchmark"] = args.benchmark
    evaluation = ModelEvaluator().evaluate(model_id, int(version), **kwargs)

    if str(evaluation.get("status")) == "OK":
        _emit(_ok({"evaluation": evaluation}))
        return
    _emit({
        "status": "degraded",
        "data": {"evaluation": evaluation},
        "error_code": str(evaluation.get("status") or "EVALUATION_SAMPLE_INSUFFICIENT"),
    })


# ------------------------------------------------------------------ tune（E5）
def _cmd_tune(args) -> None:
    """生成只读优化建议；不自动创建草稿、不修改参数、不发布、不激活（门禁 19）。"""
    model_id = str(getattr(args, "model", "") or "")
    if not model_id:
        _fail("MODEL_CONFIG_INVALID", "需要 --model 指定模型 ID", exit_code=USAGE_EXIT_CODE)
    try:
        version = _resolve_version(model_id, getattr(args, "version", None))
    except ValueError as exc:
        _fail("MODEL_CONFIG_INVALID", str(exc))
    if version is None:
        _fail("MODEL_VERSION_NOT_FOUND", f"模型 {model_id} 尚未激活任何版本")

    try:
        result = OptimizationAdvisor().suggest(model_id, int(version), period=getattr(args, "period", None))
    except ValueError as exc:
        _fail(getattr(exc, "code", "MODEL_CONFIG_INVALID"), str(exc))
    _emit(_ok(result))


# ------------------------------------------------------------------ 分发
def cmd_screen_model(args) -> None:
    """`screen-model` 子命令分发入口（assess / track / evaluate / tune）。"""
    action = getattr(args, "screen_model_cmd", None)
    if action == "assess":
        _cmd_assess(args)
    elif action == "track":
        _cmd_track(args)
    elif action == "evaluate":
        _cmd_evaluate(args)
    elif action == "tune":
        _cmd_tune(args)
    else:
        _fail(
            "MODEL_CONFIG_INVALID",
            "screen-model 需要子命令: assess / track / evaluate / tune",
            exit_code=USAGE_EXIT_CODE,
        )


__all__ = ["cmd_screen_model"]