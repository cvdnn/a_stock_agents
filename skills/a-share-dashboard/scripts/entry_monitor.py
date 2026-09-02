#!/usr/bin/env python3
"""
入场监控策略 — 实时检测关注股是否满足入场条件，触发后提示

配合 AI-Platform cron 使用，每5分钟检测一次。

检测逻辑（基于 trading-combo 策略规则）：
  1. 读取关注股池(watch_pool.csv)，获取每只的入场条件(entry_condition)
  2. 获取实时行情和技术指标
  3. 判断是否满足条件
  4. 触发后输出通知，建议移入自选股池或直接开仓

用法:
  AI-Platform cron create \\
    --name "入场监控" \\
    --script entry_monitor.py \\
    --schedule "every 5m" \\
    --no-agent \\
    --deliver all
"""
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, time

# ── 路径 ──
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCH_PATH = os.path.join(SKILL_DIR, "data", "watch_pool.csv")
A_SCRIPT = "./.AI-Platform/skills/stocks/a-share-data/scripts/fetch_patched.py"
VENV_PY = "python3"


def is_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (time(9, 30) <= t <= time(11, 30)) or (time(13, 0) <= t <= time(15, 0))


def run(cmd: list[str], timeout=20) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def get_price(code: str) -> dict:
    out = run([VENV_PY, A_SCRIPT, "fetch_realtime.py", "--quote", code, "--json"])
    if out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            pass
    return {}


def get_ma(code: str) -> dict:
    """获取MA10和MA20"""
    out = run([VENV_PY, A_SCRIPT, "fetch_technical.py", code, "--freq", "1d", "--count", "30",
               "--indicators", "MA", "--json"], timeout=25)
    if out:
        try:
            data = json.loads(out)
            if data:
                latest = data[-1]
                return {"ma10": latest.get("MA10"), "ma20": latest.get("MA20")}
        except (json.JSONDecodeError, IndexError):
            pass
    return {}


def check_entry(code: str, name: str, entry_condition: str, quote: dict, ma: dict) -> dict:
    """判断是否满足入场条件"""
    result = {"triggered": False, "reason": "", "confidence": "低"}
    price = quote.get("最新价", 0)
    change = quote.get("涨跌幅(%)", 0)

    if not price or not ma:
        return result

    ma10 = ma.get("ma10")
    ma20 = ma.get("ma20")

    # ---- 条件检测 ----
    triggers = []

    # 条件1: 回踩MA20不破
    if ma20 and "MA20" in entry_condition:
        near_ma20 = abs(price - ma20) / ma20 * 100 < 2  # 距MA20 2%以内
        above_ma20 = price > ma20
        if near_ma20 and above_ma20:
            triggers.append(f"回踩MA20({ma20:.2f})不破")

    # 条件2: 回踩MA10不破
    if ma10 and "MA10" in entry_condition:
        near_ma10 = abs(price - ma10) / ma10 * 100 < 1.5
        above_ma10 = price > ma10
        if near_ma10 and above_ma10:
            triggers.append(f"回踩MA10({ma10:.2f})不破")

    # 条件3: 缩量（通过换手率判断，<3%为缩量）
    turnover = quote.get("换手率", 100)
    if "缩量" in entry_condition and turnover < 3:
        triggers.append(f"缩量(换手{turnover}%)")

    # 条件4: 回调至某价位附近
    if "回调" in entry_condition and change < 0:
        triggers.append(f"回调中({change:+.2f}%)")

    # ---- 结果判定 ----
    if len(triggers) >= 1:
        result["triggered"] = True
        result["reason"] = " + ".join(triggers)
        result["confidence"] = "高" if len(triggers) >= 2 else "中"
        result["price"] = price
        result["change"] = change

    return result


def load_watch_pool():
    rows = []
    if not os.path.exists(WATCH_PATH):
        return rows
    with open(WATCH_PATH, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # 只检测A/B级且入场条件不空的
            if r.get("rating") in ("A", "B") and r.get("entry_condition"):
                rows.append(r)
    return rows


def load_state():
    path = os.path.expanduser("~/.AI-Platform/scripts/entry_monitor_state.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_state(state):
    path = os.path.expanduser("~/.AI-Platform/scripts/entry_monitor_state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)


def main():
    if not is_market_hours():
        return

    watch_list = load_watch_pool()
    if not watch_list:
        return

    state = load_state()
    alerts = []

    for w in watch_list:
        code = w["code"]
        name = w["name"]
        entry_cond = w.get("entry_condition", "")

        # 已触发过则跳过
        if state.get(f"triggered_{code}"):
            continue

        quote = get_price(code)
        if "error" in quote or not quote.get("最新价"):
            continue

        ma = get_ma(code)
        if not ma:
            continue

        result = check_entry(code, name, entry_cond, quote, ma)

        if result["triggered"]:
            price = result.get("price", 0)
            change = result.get("change", 0)
            alerts.append(
                f"⚡ 入场信号触发: {code}({name})\n"
                f"   条件匹配: {result['reason']}\n"
                f"   当前价: {price} ({change:+.2f}%)\n"
                f"   可信度: {result['confidence']}\n"
                f"   建议: pool_manager upgrade --code {code} --reason \"入场条件触发\"\n"
                f"         或 position_manager open --code {code} --price {price} --qty [股数]"
            )
            state[f"triggered_{code}"] = True

    save_state(state)

    if alerts:
        print("\n\n".join(alerts))


if __name__ == "__main__":
    main()