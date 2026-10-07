# -*- coding: utf-8 -*-
"""选股模型类型注册中心（`SelectionModelTypeRegistry`，A5 / SPEC-ALGO-ISS-MT-001 §2）。

- 首期登记 4 个类型：`condition_tree` / `funnel`（P0，可发布）与
  `scoring_rank` / `composite`（P2，仅登记不可发布）；
- 每个类型声明结构、编译器、可执行节点与输出契约；
- 未知类型一律拒绝（`MODEL_TYPE_UNKNOWN`），P2 类型的节点由编译器拒绝，
  **不得在界面或接口显示为可运行**（§2 首期可运行约束）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


class ModelTypeError(ValueError):
    """模型类型相关错误；`code` 为稳定错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelTypeCapability:
    type_id: str
    label: str
    structure: str
    status: str
    publishable: bool
    editable: bool
    output_contract: str
    supported_node_kinds: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type_id": self.type_id,
            "label": self.label,
            "structure": self.structure,
            "status": self.status,
            "publishable": self.publishable,
            "editable": self.editable,
            "output_contract": self.output_contract,
            "supported_node_kinds": list(self.supported_node_kinds),
        }


class SelectionModelTypeRegistry:
    """模型类型注册中心：类型发现、能力查询与可发布性判定。"""

    def __init__(self) -> None:
        self._capabilities: Dict[str, ModelTypeCapability] = {}

    def register(self, capability: ModelTypeCapability) -> ModelTypeCapability:
        if not capability.type_id:
            raise ModelTypeError("MODEL_TYPE_UNKNOWN", "模型类型 ID 不能为空")
        self._capabilities[capability.type_id] = capability
        return capability

    def get(self, type_id: str) -> ModelTypeCapability:
        try:
            return self._capabilities[type_id]
        except KeyError as exc:
            raise ModelTypeError("MODEL_TYPE_UNKNOWN", f"未知模型类型: {type_id}") from exc

    @property
    def names(self) -> List[str]:
        return sorted(self._capabilities)

    @property
    def publishable_names(self) -> List[str]:
        return sorted(
            type_id for type_id, cap in self._capabilities.items() if cap.publishable
        )

    def is_publishable(self, type_id: str) -> bool:
        return self.get(type_id).publishable

    def require_publishable(self, type_id: str) -> ModelTypeCapability:
        capability = self.get(type_id)
        if not capability.publishable:
            raise ModelTypeError(
                "MODEL_TYPE_UNKNOWN",
                f"模型类型 {type_id}（{capability.status}）首期不可发布："
                "对应节点执行器尚未实现（§2 首期可运行约束）",
            )
        return capability

    def to_list(self) -> List[Dict[str, Any]]:
        return [self._capabilities[type_id].to_dict() for type_id in self.names]


def build_default_type_registry() -> SelectionModelTypeRegistry:
    registry = SelectionModelTypeRegistry()
    registry.register(
        ModelTypeCapability(
            type_id="condition_tree",
            label="条件选股",
            structure="多维度规则组 + 布尔表达式树",
            status="P0",
            publishable=True,
            editable=True,
            output_contract="单层或多层 filter 层，层内安全表达式树",
            supported_node_kinds=("filter",),
        )
    )
    registry.register(
        ModelTypeCapability(
            type_id="funnel",
            label="漏斗选股",
            structure="多阶段逐层收缩 + 阶段触发器",
            status="P0",
            publishable=True,
            editable=True,
            output_contract="有序 filter/gate/output 层级与候选传递",
            supported_node_kinds=("filter", "gate", "output"),
        )
    )
    registry.register(
        ModelTypeCapability(
            type_id="scoring_rank",
            label="评分排序",
            structure="因子评分 + 权重 + Top-K",
            status="P2",
            publishable=False,
            editable=False,
            output_contract="过滤层 → 评分层 → 排序层 → 输出层",
            supported_node_kinds=("filter", "score", "rank", "output"),
        )
    )
    registry.register(
        ModelTypeCapability(
            type_id="composite",
            label="组合模型",
            structure="引用其他模型输出并做集合运算",
            status="P2",
            publishable=False,
            editable=False,
            output_contract="子模型输入 → 集合运算层 → 汇总层",
            supported_node_kinds=("merge", "branch", "output"),
        )
    )
    return registry


__all__ = [
    "ModelTypeCapability",
    "ModelTypeError",
    "SelectionModelTypeRegistry",
    "build_default_type_registry",
]