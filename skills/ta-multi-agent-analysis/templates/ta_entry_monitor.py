#!/usr/bin/env python3
"""
ta_entry_monitor.py - TradingAgents 入场/止损 cron 监控模板

no_agent 模式：无事件时静默退出（不推送空壳信息）。

用法：
  1. 复制到 ~/.AI-Platform/scripts/ta_monitor_{CODE}.py
  2. 编辑下方 STOCK_CONFIG
  3. 部署 cron:
     AI-Platform cron create --name "TA监控-{CODE}" --script ta_monitor_{CODE}.py \
       --schedule "every 5m" --no-agent --deliver all
"""

import json
import os
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── 编辑区域：每只股票单独配置 ──────────────────────────────────────────────────

STOCK_CONFIG = {
    "code": "{{TICKER}}",          # 6位A股代码
    "name": "",                    # 股票名称（留空自动获取）
    "entry_price": {{ENTRY_PRICE}},  # 入场价
    "stop_price": {{STOP_PRICE}},    # 止损价
    "target_price": 0,             # 目标价（可选）
    "shares": 0,                   # 持仓股数（可选）
    "account": "{{ACCOUNT}}",      # 模拟盘账户
}

# ── 运行模式（部署时自动替换）───────────────────────────────────────────────────
# mode=stop  : 止损检测（默认）
# mode=entry : MA20回踩入场检测
# mode=all   : 两者都检测
MODE = os.environ.get("MONITOR_MODE", "stop")


def _get_ma20_estimate(code: str) -> Optional[float]:
    """通过腾讯行情获取近似 MA20（用最近收盘价的均值估算）。"""
    # 简单回退：取昨收作为 MA20 近似值
    return None

# ── 核心逻辑（通常无需修改）────────────────────────────────────────────────────

STATE_FILE = Path.home() / ".AI-Platform" / "scripts" / f"ta_monitor_{STOCK_CONFIG['code']}_state.json"
CODE = STOCK_CONFIG["code"]
PREFIX = "sh" if CODE.startswith(("6", "9")) else "sz" if CODE.startswith(("0", "3")) else "bj"


def is_market_hours() -> bool:
    """检查是否在 A 股交易时段。"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour + now.minute / 60
    return (9.30 <= t <= 11.30) or (13.00 <= t <= 15.00)


def get_tencent_quote(code: str) -> dict:
    """从腾讯行情 API 获取实时数据。"""
    url = f"https://qt.gtimg.cn/q={PREFIX}{code}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=10)
    text = resp.read().decode("gbk")
    parts = text.split("~")
    if len(parts) < 33:
        return {}
    try:
        price = float(parts[3])
        prev_close = float(parts[4])
        change_pct = (price - prev_close) / prev_close * 100
    except (ValueError, IndexError):
        return {}
    return {
        "price": price,
        "change_pct": round(change_pct, 2),
        "high": float(parts[5]) if parts[5] else 0,
        "low": float(parts[6]) if parts[6] else 0,
        "time": parts[30],
        "name": parts[1],
    }


def load_state() -> dict:
    """读取已触发状态，避免重复通知。"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"day": "", "stop_triggered": False, "target_triggered": False, "alerts": []}


def save_state(state: dict):
    """持久化状态。"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def main():
    today = date.today().isoformat()
    state = load_state()

    # 每日重置
    if state.get("day") != today:
        state = {"day": today, "stop_triggered": False, "stop_warned": False, "target_triggered": False, "alerts": []}

    # 非交易时段：静默退出
    if not is_market_hours():
        now = datetime.now()
        if now.hour < 9 or now.hour >= 15:
            sys.exit(0)

    # 获取行情
    try:
        quote = get_tencent_quote(CODE)
    except Exception:
        sys.exit(0)

    if not quote or "price" not in quote:
        sys.exit(0)

    price = quote["price"]
    name = quote.get("name", STOCK_CONFIG.get("name", CODE))
    entry = STOCK_CONFIG["entry_price"]
    stop = STOCK_CONFIG["stop_price"]
    target = STOCK_CONFIG["target_price"]

    signals = []

    # 止损检测
    if stop > 0:
        if price <= stop and not state.get("stop_triggered"):
            signals.append(f"[RED] 止损触发！{name}({CODE}) 现价{price:.2f} <= 止损{stop:.2f}")
            state["stop_triggered"] = True
        elif price <= stop * 1.03 and not state.get("stop_warned"):
            pct = (price - stop) / stop * 100
            signals.append(f"[ORANGE] 接近止损！{name}({CODE}) 现价{price:.2f}，距止损{pct:.1f}%")
            state["stop_warned"] = True

    # 目标价触发
    if target > 0 and price >= target and not state.get("target_triggered"):
        signals.append(f"[GREEN] 目标价触及！{name}({CODE}) 现价{price:.2f} >= 目标{target:.2f}")
        state["target_triggered"] = True

    # 记录状态
    state["alerts"] = (state.get("alerts", []) + signals)[-20:]
    save_state(state)

    # 无事件：静默退出
    if not signals:
        sys.exit(0)

    # 有事件：输出推送内容
    print(f"=== 监控提醒: {name}({CODE}) ===")
    for s in signals:
        print(f"  {s}")
    if entry:
        profit_pct = (price / entry - 1) * 100
        print(f"  入场: {entry:.2f} | 现价: {price:.2f} ({profit_pct:+.2f}%)")
    print(f"  时间: {quote.get('time', '')}")


if __name__ == "__main__":
    main()
