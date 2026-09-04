#!/usr/bin/env python3
"""
分档限价单监控模板 (Tiered Limit-Order Monitor Template)
=================================================
用途: 对单只股票在交易时段内轮询，按策略模型给出的分档价位触发提醒。
设计范式: 参数策略对象注入 (Parameter Strategy Injection)

核心特性:
  1. no_agent cron + 空stdout=静默  → 仅触发时 print 提醒(投递), 未触发 print 一行日志
  2. 状态文件去重 (每信号每日只推一次)
  3. 交易时段门 (09:25~11:30 / 13:00~15:00, 周末跳过)
  4. 价位使用策略模型给出的区间: 回踩低吸区 / 突破价 / 止损 / 止盈目标

部署方式:
  AI-Platform cron create --name "${CODE}限价单监控" \
    --script monitor_${CODE}_limit.py \
    --schedule "every 5m" --no-agent --deliver all
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, time as dt_time
from pathlib import Path

# ── 单标的监控参数配置 (请根据实际标的修改或通过环境变量注入) ──
CODE = os.environ.get("MONITOR_STOCK_CODE", "000001")
NAME = os.environ.get("MONITOR_STOCK_NAME", "目标股票")
MARKET = "sh" if CODE.startswith(("60", "68")) else "sz"

# 分档价位 (来自入场审查或策略模型输出)
A_ZONE = (10.00, 10.20)   # A档 回踩低吸区 (低, 高)
B_ZONE = (9.80, 9.95)     # B档 极限低吸区
BREAK_HIGH = 10.50        # C档 突破追入价
STOP_LOSS = 9.70          # 止损离场价
TARGET = 11.20            # 第一目标止盈价

SCRIPT_DIR = Path.home() / ".AI-Platform" / "scripts"
STATE_FILE = SCRIPT_DIR / f"monitor_{CODE}_limit_state.json"


def is_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    if dt_time(9, 25) <= t <= dt_time(11, 30):
        return True
    if dt_time(13, 0) <= t <= dt_time(15, 0):
        return True
    return False


def get_quote(code: str, market: str) -> dict:
    qcode = f"{market}{code}"
    url = f"https://qt.gtimg.cn/q={qcode}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=10)
    parts = resp.read().decode("gbk").split("~")
    if len(parts) < 35:
        return {}
    return {
        "price": float(parts[3]) if parts[3] else 0,
        "prev_close": float(parts[4]) if parts[4] else 0,
        "high": float(parts[33]) if parts[33] else 0,
        "low": float(parts[34]) if parts[34] else 0,
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"triggered": {}}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def main():
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    now_fmt = now.strftime("%H:%M")

    if not is_market_hours():
        return  # 空输出 → cron no_agent 静默

    q = get_quote(CODE, MARKET)
    if not q or q["price"] == 0:
        print(f"[{CODE}监控] 行情获取失败, 本轮跳过", file=sys.stderr)
        return

    price = q["price"]
    chg_pct = (price - q["prev_close"]) / q["prev_close"] * 100 if q["prev_close"] else 0

    state = load_state()
    triggered = state.setdefault("triggered", {})
    # 清理非今日记录 (去重只针对当日)
    for k in [k for k in triggered if not k.endswith(today)]:
        triggered.pop(k, None)

    fired = []

    # 🔴 止损 / 暂停入场
    if price < STOP_LOSS:
        key = f"stop_{today}"
        if key not in triggered:
            triggered[key] = True
            fired.append(
                f"🔴 {CODE} 跌破止损位 {STOP_LOSS}!\n"
                f"现价 {price:.2f} ({chg_pct:+.2f}%)\n"
                f"操作: 止损离场 / 暂停入场, 等待企稳"
            )
    # 🟡 回踩低吸区 (含A/B档)
    elif A_ZONE[0] <= price <= A_ZONE[1]:
        key = f"a_zone_{today}"
        if key not in triggered:
            triggered[key] = True
            fired.append(
                f"🟡 {CODE} 进入回踩低吸区 {A_ZONE[0]:.2f}~{A_ZONE[1]:.2f}\n"
                f"现价 {price:.2f} ({chg_pct:+.2f}%)\n"
                f"操作: 回踩企稳可挂A档低吸; 深度回踩{B_ZONE[0]:.2f}~{B_ZONE[1]:.2f}更佳(B档)"
            )
    # 🟢 突破追入
    elif price >= BREAK_HIGH:
        key = f"break_{today}"
        if key not in triggered:
            triggered[key] = True
            fired.append(
                f"🟢 {CODE} 放量突破 {BREAK_HIGH}!\n"
                f"现价 {price:.2f} ({chg_pct:+.2f}%)\n"
                f"操作: 突破确认可追入, 第一目标 {TARGET}"
            )

    # 🎯 第一目标
    if price >= TARGET:
        key = f"target_{today}"
        if key not in triggered:
            triggered[key] = True
            fired.append(
                f"🎯 {CODE} 触及第一目标 {TARGET}\n"
                f"现价 {price:.2f}\n"
                f"操作: 分批止盈, 若放量突破看更高压力"
            )

    save_state(state)

    if fired:
        header = f"📌 {CODE} 限价单提醒 | {today} {now_fmt}"
        print("\n\n".join([header] + fired))
    else:
        print(f"[{CODE}] {now_fmt} 现价{price:.2f} 未触发, 静默")


if __name__ == "__main__":
    main()
