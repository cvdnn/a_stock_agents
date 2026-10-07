# -*- coding: utf-8 -*-
"""阶段 E 行情视图与统计基元（SSOT §12 / §13.7-13.9）。

结果研究（评估/回测/跟踪/评价/调优）必须在**同一套口径**上读取本地日线：
价格口径固定为**收盘价主口径**（D-14），多口径仅作旁证。本模块是这些基元的
唯一实现点，供 E1～E5 复用：

- 记录 → `Bar` 序列的确定性归一（缺字段即缺失，不猜测、不回退另一口径）；
- A股涨跌停价、MFE/MAE、最大回撤、年化波动率、ATR、均线；
- **未来数据检测**（发布门禁 15）：任一 `bar.date > as_of` 即判为未来函数；
- **交易日历 T+N**（发布门禁 14 / §12.4：N 必须按交易日而非自然日计算）；
- 费用配置与**最低保本卖出价**（复用 `ExecutionActionEngine`，向上进位至分位）。

本模块只做纯计算：不读数据库、不发起网络请求、不写盘，也不产出任何选股结论。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as _date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from core.config import get_market_config
from core.data.sync_engine import DB_PATH, TradeCalendar
from core.strategy.execution_action_engine import ExecutionActionEngine

DEFAULT_ATR_PERIOD = 14
#: 价格主口径（D-14）：模型评价与标记分析统一使用收盘价。
PRICE_CALIBER = "close"

_FEE_DEFAULTS = {
    "commission_rate": 0.00025,
    "min_commission": 5.0,
    "tax_rate_sell": 0.0005,
    "transfer_fee_rate": 0.00001,
    "breakeven_ceil_cent": True,
    "default_benchmark": "sh000001",
}


class MarketViewError(ValueError):
    """行情视图不可用（缺字段/长度不一致/非法值）；失败关闭，绝不猜测。"""

    def __init__(self, message: str, code: str = "MODEL_DATA_UNSUPPORTED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Bar:
    """单根日线（收盘价主口径；OHLC 缺失时为 `None`，不得以收盘价冒充）。"""

    date: str
    close: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "close": self.close,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "volume": self.volume,
        }


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _aligned(seq: Any, length: int) -> Optional[List[Optional[float]]]:
    """把可选的并列数组对齐到 `length`；长度不符即视为缺失（返回 None）。"""
    if not isinstance(seq, Sequence) or isinstance(seq, (str, bytes)):
        return None
    if len(seq) != length:
        return None
    return [_finite(item) for item in seq]


def normalize_bars(source: Union[Mapping[str, Any], Sequence[Any]]) -> List[Bar]:
    """把装配记录或逐条 `{date, close, ...}` 序列归一为按日期升序的 `Bar` 列表。

    归一契约（不伪造）：
    - 必须有等长的 `dates` 与 `closes`；任一缺失/长度不符即 `MarketViewError`；
    - `opens/highs/lows/volumes` 为可选并列数组，缺失即逐根置 `None`；
    - 收盘价必须为正的有限数，否则该记录不可用于研究（失败关闭）。
    """
    if isinstance(source, Mapping):
        dates = source.get("dates")
        closes = source.get("closes")
        if not isinstance(dates, Sequence) or not isinstance(closes, Sequence):
            raise MarketViewError("记录缺少 dates/closes，无法构建行情视图")
        if len(dates) != len(closes) or not closes:
            raise MarketViewError("dates 与 closes 长度不一致或为空")
        length = len(closes)
        opens = _aligned(source.get("opens"), length)
        highs = _aligned(source.get("highs"), length)
        lows = _aligned(source.get("lows"), length)
        volumes = _aligned(source.get("volumes"), length)
        raw = [
            {
                "date": str(dates[i])[:10],
                "close": _finite(closes[i]),
                "open": opens[i] if opens else None,
                "high": highs[i] if highs else None,
                "low": lows[i] if lows else None,
                "volume": volumes[i] if volumes else None,
            }
            for i in range(length)
        ]
    elif isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        raw = []
        for item in source:
            if not isinstance(item, Mapping):
                raise MarketViewError("逐条行情必须是映射结构")
            raw.append(
                {
                    "date": str(item.get("date") or "")[:10],
                    "close": _finite(item.get("close")),
                    "open": _finite(item.get("open")),
                    "high": _finite(item.get("high")),
                    "low": _finite(item.get("low")),
                    "volume": _finite(item.get("volume")),
                }
            )
    else:
        raise MarketViewError("不支持的行情来源类型")

    by_date: Dict[str, Bar] = {}
    for entry in raw:
        day = entry["date"]
        close = entry["close"]
        if not day or close is None or close <= 0:
            raise MarketViewError(f"非法行情：date={day!r} close={entry['close']!r}")
        by_date[day] = Bar(
            date=day,
            close=close,
            open=entry["open"],
            high=entry["high"],
            low=entry["low"],
            volume=entry["volume"],
        )
    if not by_date:
        raise MarketViewError("行情视图为空")
    return [by_date[key] for key in sorted(by_date)]


def limit_prices(code: str, prev_close: float) -> Tuple[float, float]:
    """返回 (涨停价, 跌停价)；按板块涨跌幅限制（主板 10% / 创业板科创 20% / 北交所 30%）。"""
    if not prev_close or prev_close <= 0:
        return (float("inf"), 0.0)
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    core = digits[-6:] if len(digits) >= 6 else digits
    if core.startswith(("688", "689", "30")):
        pct = 0.20
    elif core.startswith(("8", "4", "92")):
        pct = 0.30
    else:
        pct = 0.10
    return (round(prev_close * (1 + pct), 2), round(prev_close * (1 - pct), 2))


def board_of(code: str) -> str:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    core = digits[-6:] if len(digits) >= 6 else digits
    if core.startswith(("688", "689")):
        return "star"
    if core.startswith("30"):
        return "chinext"
    if core.startswith(("8", "4", "92")):
        return "bse"
    return "main"


def max_position_weight(code: str) -> float:
    """单票仓位上限（D-20）：主板 15%，20cm 及以上 8%。"""
    return 0.08 if board_of(code) in {"chinext", "star", "bse"} else 0.15


def simple_returns(closes: Sequence[float]) -> List[float]:
    returns: List[float] = []
    for prev, cur in zip(closes, closes[1:]):
        returns.append((cur - prev) / prev if prev else 0.0)
    return returns


def max_drawdown_pct(values: Sequence[float]) -> float:
    """区间最大回撤（正数百分比）。"""
    peak: Optional[float] = None
    worst = 0.0
    for value in values:
        if value <= 0:
            continue
        peak = value if peak is None or value > peak else peak
        if peak:
            worst = max(worst, (peak - value) / peak * 100.0)
    return round(worst, 4)


def annualized_volatility_pct(closes: Sequence[float], periods_per_year: int = 250) -> float:
    returns = simple_returns(closes)
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return round(math.sqrt(variance) * math.sqrt(periods_per_year) * 100.0, 4)


def mfe_mae_pct(bars: Sequence[Bar], base_price: Optional[float] = None) -> Dict[str, Any]:
    """相对基准价的最大有利/不利波动（MFE/MAE）。

    有 OHLC 时用最高/最低价；缺失时退化为收盘价并显式标注口径，绝不冒充。
    """
    if not bars:
        raise MarketViewError("MFE/MAE 需要非空行情序列")
    base = base_price if base_price and base_price > 0 else bars[0].close
    has_hl = all(bar.high is not None and bar.low is not None for bar in bars)
    highs = [float(bar.high) for bar in bars] if has_hl else [bar.close for bar in bars]
    lows = [float(bar.low) for bar in bars] if has_hl else [bar.close for bar in bars]
    mfe = (max(highs) - base) / base * 100.0
    mae = (min(lows) - base) / base * 100.0
    return {
        "base_price": round(base, 4),
        "mfe_pct": round(mfe, 4),
        "mae_pct": round(mae, 4),
        "caliber": "high_low" if has_hl else "close_only",
    }


def atr_value(bars: Sequence[Bar], period: int = DEFAULT_ATR_PERIOD) -> Optional[float]:
    """ATR（真实波幅均值）；无 OHLC 或样本不足时返回 None（不猜测）。"""
    if len(bars) < period + 1:
        return None
    if not all(bar.high is not None and bar.low is not None for bar in bars):
        return None
    trs: List[float] = []
    for prev, cur in zip(bars, bars[1:]):
        high, low = float(cur.high), float(cur.low)
        trs.append(max(high - low, abs(high - prev.close), abs(low - prev.close)))
    window = trs[-period:]
    return round(sum(window) / len(window), 4)


def moving_average(closes: Sequence[float], period: int) -> Optional[float]:
    if period <= 0 or len(closes) < period:
        return None
    window = closes[-period:]
    return round(sum(window) / len(window), 4)


def detect_future_data(bars: Sequence[Bar], as_of: str) -> List[str]:
    """未来数据检测（发布门禁 15）：返回日期晚于 `as_of` 的 bar 日期清单。"""
    cutoff = str(as_of or "")[:10]
    return [bar.date for bar in bars if bar.date > cutoff]


def nth_trading_date(
    signal_date: str,
    n: int,
    *,
    db_path: Optional[Any] = None,
    max_lookahead_days: int = 60,
) -> Optional[str]:
    """信号日 T 之后的第 N 个交易日（T+N，按证券交易日历，§12.4）。

    `n<=0` 返回信号日自身；超出 `max_lookahead_days` 未命中则返回 `None`（如实不猜测）。
    """
    if n <= 0:
        return str(signal_date)[:10]
    try:
        cursor = datetime.strptime(str(signal_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    path = db_path or DB_PATH
    remaining = int(n)
    for _ in range(max(1, int(max_lookahead_days))):
        cursor = cursor + timedelta(days=1)
        if TradeCalendar.is_trading_day(cursor, db_path=path):
            remaining -= 1
            if remaining == 0:
                return cursor.strftime("%Y-%m-%d")
    return None


def market_config() -> Dict[str, Any]:
    """摩擦成本配置（佣金/印花税/过户费/滑点阈值），缺失键以规范默认值补齐。"""
    config = dict(_FEE_DEFAULTS)
    try:
        config.update({k: v for k, v in (get_market_config() or {}).items() if v is not None})
    except Exception:  # pragma: no cover - 配置不可读时用规范默认，不阻断研究
        pass
    return config


def breakeven_price(entry_price: float, shares: int, cfg: Optional[Mapping[str, Any]] = None) -> Optional[float]:
    """含全部税费的最低保本卖出价（向上进位至分位）；缺股数/成交价即返回 None。"""
    if not entry_price or entry_price <= 0 or not shares or int(shares) <= 0:
        return None
    return float(
        ExecutionActionEngine.calc_min_breakeven_price(
            cost=float(entry_price), shares=int(shares), market_cfg=dict(cfg or market_config())
        )
    )


def stop_loss_levels(source: str = "AGENTS.md 实战交易三原则（T0 -3% / T1 -5% / T2 -8%）") -> Dict[str, Any]:
    """三级风控止损阶梯及其口径来源（D-23：新增模块必须显式声明引用口径）。"""
    return {"T0_warn_pct": -3.0, "T1_trim_pct": -5.0, "T2_stop_pct": -8.0, "stop_source": source}


__all__ = [
    "DEFAULT_ATR_PERIOD",
    "PRICE_CALIBER",
    "Bar",
    "MarketViewError",
    "annualized_volatility_pct",
    "atr_value",
    "board_of",
    "breakeven_price",
    "detect_future_data",
    "limit_prices",
    "market_config",
    "max_drawdown_pct",
    "max_position_weight",
    "mfe_mae_pct",
    "moving_average",
    "normalize_bars",
    "nth_trading_date",
    "simple_returns",
    "stop_loss_levels",
]