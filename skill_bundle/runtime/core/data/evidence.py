# -*- coding: utf-8 -*-
"""
统一循证溯源信封构造模块 (Evidence Envelope SSOT)
遵循 SPEC-SKILL-002 与机构股票投研规范准则二（全链路可循证性与 C2 门禁）。
为所有技能输出强制注入统一溯源元数据 (evidence_meta)。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

# 权威费率单点事实（印花税 0.05% + 佣金万 2.5 最低 5 元 + 向上进位至分位）
FEE_RULE_SSOT_DEFAULT = "stamp_0.0005_comm_0.00025_min5_ceil"


@dataclass(frozen=True)
class EvidenceEnvelope:
    """标准循证溯源信封数据结构"""
    as_of_trading_day: str
    quote_source: str
    kline_bars_count: int
    watermark_ready: bool
    fee_rule_ssot: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def resolve_current_trading_day(fallback_date: Optional[str] = None) -> str:
    """获取当前或最近一个有效交易日 (YYYY-MM-DD)"""
    if fallback_date:
        return str(fallback_date).strip()[:10]
    try:
        from core.data.sync_engine import TradeCalendar
        td = TradeCalendar.last_trading_day()
        if td:
            return td
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")


def build_evidence_meta(
    as_of_trading_day: Optional[str] = None,
    quote_source: str = "L1:tencent_realtime",
    kline_bars_count: int = 0,
    watermark_ready: bool = True,
    fee_rule_ssot: str = FEE_RULE_SSOT_DEFAULT,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    构造统一规范的 evidence_meta 循证溯源信封。

    Args:
        as_of_trading_day: 数据对应交易日 (YYYY-MM-DD)，缺省时自动通过交易日历解析最近交易日
        quote_source: 行情源标识 (如 L1:tencent_realtime, L1:tencent_kline, L2:eastmoney 等)
        kline_bars_count: 分析所采用的 K 线根数
        watermark_ready: 本地数据水位是否已就绪
        fee_rule_ssot: 费率与保本价计算规范单点事实标识
        **kwargs: 扩展循证字段

    Returns:
        遵循 C2 规范的 evidence_meta 字典
    """
    day = resolve_current_trading_day(as_of_trading_day)
    meta = {
        "as_of_trading_day": str(day),
        "quote_source": str(quote_source),
        "kline_bars_count": int(kline_bars_count),
        "watermark_ready": bool(watermark_ready),
        "fee_rule_ssot": str(fee_rule_ssot),
    }
    if kwargs:
        meta.update(kwargs)
    return meta


__all__ = [
    "FEE_RULE_SSOT_DEFAULT",
    "EvidenceEnvelope",
    "resolve_current_trading_day",
    "build_evidence_meta",
]
