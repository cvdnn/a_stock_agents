# -*- coding: utf-8 -*-
"""
tencent_fields.py — 腾讯 qt.gtimg.cn L1 快照解析的单点真实源 (SSOT)

背景：历史上项目内散落 6 处彼此独立的腾讯快照解析实现
(`data_bridge` / `fetch_realtime` / `paper_trading.market_data` / `multi_agent.ta_analyze`
/ `data_layer.get_realtime_quote` / `data_layer.get_batch_quotes`)。
其中 `ta_analyze` 使用了一整套错位的下标，导致降级模式下把"买一价"当作 PE 输出；
`data_layer` 两处下标正确但把 PE/PB 缺失折算为 0，与 §7.7.7「缺失 ≠ 亏损」冲突。
本模块将下标常量与解析逻辑收敛为单一权威实现，6 处调用点一律 import 复用。
`data_layer` 两处的输出键名（`symbol`/`volume`/`turnover`）由其自身适配层转换，
字段下标与 PE/PB 口径均取自本模块，不再独立解析。

口径约定（对应 §7.7.7）：
- "缺失"（字段为空串或 PE/PB 占位 "0"）→ None；
- 负值（如亏损股 PE<0）原样保留，由规则层显式判定"亏损"，数据层不做归并；
- 五档盘口（T-09）：统一输出 `order_book` 结构；档位缺失不入列表，整体缺失或卖盘为 0
  （委比无定义）→ None，消费方按 Kleene 判 UNKNOWN。
"""

from __future__ import annotations

from typing import Dict, List, Optional

try:
    from core.config import infer_market_prefix as _infer_market_prefix
except ImportError:  # pragma: no cover - 兼容 scripts/core 直接入 sys.path 的场景
    try:
        from config import infer_market_prefix as _infer_market_prefix
    except ImportError:
        _infer_market_prefix = None


def _infer_market(code_raw: str) -> str:
    """推断市场前缀：优先复用 core.config 的 SSOT，不可用时按代码段回退。"""
    if _infer_market_prefix is not None:
        return _infer_market_prefix(code_raw)
    if code_raw.startswith(("8", "4", "92")):
        return "bj"
    if code_raw.startswith(("6", "5", "9")):
        return "sh"
    return "sz"


# ── 腾讯 L1 快照字段下标（权威映射，严禁在其他文件重复定义） ──────────────────
IDX_SYMBOL = 0          # 赋值左值，含市场前缀，如 v_sh600519
IDX_NAME = 1            # 名称
IDX_CODE = 2            # 纯数字代码，如 600519
IDX_PRICE = 3           # 现价
IDX_PREV_CLOSE = 4      # 昨收
IDX_OPEN = 5            # 今开
IDX_VOLUME_HANDS = 6    # 成交量(手)
IDX_OUTER = 7           # 外盘
IDX_INNER = 8           # 内盘
# 五档盘口（T-09 / P-01 / W-05）：买一价/量(手)起于 9，逐档 +2；卖一价/量起于 19
IDX_BID1 = 9            # 买一价
IDX_BID2 = 11
IDX_BID3 = 13
IDX_BID4 = 15
IDX_BID5 = 17
IDX_ASK1 = 19           # 卖一价
IDX_ASK2 = 21
IDX_ASK3 = 23
IDX_ASK4 = 25
IDX_ASK5 = 27
IDX_TIME = 30           # 快照时间
IDX_CHANGE_PCT = 32     # 涨跌幅(%)
IDX_HIGH = 33           # 最高
IDX_LOW = 34            # 最低
IDX_AMOUNT_WAN = 37     # 成交额(万元)
IDX_TURNOVER_PCT = 38   # 换手率(%)
IDX_PE = 39             # 市盈率(TTM)
IDX_AMPLITUDE = 43      # 振幅(%)
IDX_CIRC_MKTCAP = 44    # 流通市值(亿元)
IDX_TOTAL_MKTCAP = 45   # 总市值(亿元)
IDX_PB = 46             # 市净率
IDX_LIMIT_UP = 47       # 涨停价
IDX_LIMIT_DOWN = 48     # 跌停价
IDX_VOL_RATIO = 49      # 量比

MIN_PARTS = IDX_TOTAL_MKTCAP + 1  # 构成一条有效快照所需的最小字段数


def _num(parts: List[str], idx: int) -> Optional[float]:
    """按下标取浮点值；越界或空串视为"缺失" → None。"""
    if idx >= len(parts):
        return None
    raw = parts[idx].strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _num_no_zero(parts: List[str], idx: int) -> Optional[float]:
    """取浮点值，并把占位 "0" 一并视为"缺失" → None（仅用于 PE/PB 这类无 0 语义字段）。"""
    val = _num(parts, idx)
    return None if val == 0 else val


def parse_order_book(parts: List[str]) -> Optional[Dict]:
    """解析五档买卖盘口为统一 order_book 结构（T-09 / P-01 / W-05 单点实现）。

    输出: {"bids": [{price, volume}×N], "asks": [...],
           "bid_volume": 五档买盘总量(手), "ask_volume": 五档卖盘总量(手)}

    契约（规范 §5.1 D11 / 算法侧 T-09）：
    - 逐档取值，价格或量缺失/为 0 的档位不入列表（收盘后快照常见整块缺失）；
    - 完全无有效档位，或 **卖盘总量为 0**（一字涨停无卖盘、委比无定义）→ 整体返回 None，
      消费方须按 Kleene 三值逻辑判 UNKNOWN 并携带 not_eligible_for_signal，禁止以 0 参与比较。
    """
    bids: List[Dict] = []
    asks: List[Dict] = []
    for price_idx in (IDX_BID1, IDX_BID2, IDX_BID3, IDX_BID4, IDX_BID5):
        price = _num(parts, price_idx)
        volume = _num(parts, price_idx + 1)
        if price is not None and price > 0 and volume is not None and volume > 0:
            bids.append({"price": price, "volume": volume})
    for price_idx in (IDX_ASK1, IDX_ASK2, IDX_ASK3, IDX_ASK4, IDX_ASK5):
        price = _num(parts, price_idx)
        volume = _num(parts, price_idx + 1)
        if price is not None and price > 0 and volume is not None and volume > 0:
            asks.append({"price": price, "volume": volume})
    if not bids and not asks:
        return None
    bid_volume = sum(level["volume"] for level in bids)
    ask_volume = sum(level["volume"] for level in asks)
    if ask_volume <= 0:
        # 卖盘为 0：按契约整体判缺失（委买卖比无定义）
        return None
    return {"bids": bids, "asks": asks, "bid_volume": bid_volume, "ask_volume": ask_volume}


def split_tencent_line(line: str) -> Optional[List[str]]:
    """拆分腾讯快照行为字段列表；结构不可用（非快照行/字段数不足）返回 None。"""
    if not line or "~" not in line:
        return None
    parts = line.split("~")
    if len(parts) < MIN_PARTS:
        return None
    return parts


def parse_tencent_quote(line: str) -> Optional[Dict]:
    """解析腾讯 L1 快照单行为结构化 dict（全项目唯一权威实现）。

    返回 None 表示该行不可用：非快照行、字段数不足、现价缺失/非正、或昨收缺失。
    """
    parts = split_tencent_line(line)
    if parts is None:
        return None

    price = _num(parts, IDX_PRICE)
    prev_close = _num(parts, IDX_PREV_CLOSE)
    if price is None or price <= 0 or prev_close is None:
        return None

    code_raw = parts[IDX_CODE].strip()
    if not code_raw:
        return None

    market = ""
    symbol_field = parts[IDX_SYMBOL]
    for prefix in ("sh", "sz", "bj"):
        if f"_{prefix}" in symbol_field:
            market = prefix
            break
    market = market or _infer_market(code_raw)

    change = round(price - prev_close, 2)
    change_pct = round(change / prev_close * 100, 2) if prev_close else 0.0
    amount_wan = _num(parts, IDX_AMOUNT_WAN)

    return {
        "code_raw": code_raw,
        "market": market,
        "code": f"{market}{code_raw}",
        "name": parts[IDX_NAME] if IDX_NAME < len(parts) else "",
        "time": parts[IDX_TIME] if IDX_TIME < len(parts) else "",
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "open": _num(parts, IDX_OPEN),
        "high": _num(parts, IDX_HIGH),
        "low": _num(parts, IDX_LOW),
        "volume_hands": int(_num(parts, IDX_VOLUME_HANDS) or 0),
        "outer": _num(parts, IDX_OUTER) or 0.0,
        "inner": _num(parts, IDX_INNER) or 0.0,
        "amount_wan": amount_wan,
        "amount": amount_wan * 10000 if amount_wan is not None else None,
        # §7.7.7: "缺失"(空/占位 0) → None；负值(亏损) 原样保留
        "pe": _num_no_zero(parts, IDX_PE),
        "pb": _num_no_zero(parts, IDX_PB),
        "turnover_pct": _num(parts, IDX_TURNOVER_PCT),
        "amplitude": _num(parts, IDX_AMPLITUDE),
        "vol_ratio": _num(parts, IDX_VOL_RATIO),
        "circulating_market_cap": _num(parts, IDX_CIRC_MKTCAP),
        "total_market_cap": _num(parts, IDX_TOTAL_MKTCAP),
        "limit_up": _num(parts, IDX_LIMIT_UP),
        "limit_down": _num(parts, IDX_LIMIT_DOWN),
        # T-09: 五档盘口统一结构；缺失或卖盘为 0 → None（消费方判 UNKNOWN）
        "order_book": parse_order_book(parts),
    }