#!/usr/bin/env python3
"""
持仓价格预警监控 (down-side 风控)
对每只持仓设置多层次预警线，触发时推送通知

配合 AI-Platform cron 使用：
  AI-Platform cron create --name "持仓风控预警" \
    --script ./.AI-Platform/skills/stocks/a-share-dashboard/scripts/position_stop_monitor.py \
    --schedule "every 5m" --no-agent --deliver all
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, time
from pathlib import Path

# ── 路径 ──
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
POSITIONS_PATH = SKILL_DIR / "data" / "positions.csv"
STATE_FILE = Path(os.path.expanduser("~/.AI-Platform/scripts/position_stop_monitor_state.json"))

# ── 持仓预警配置 ──
# 每只持仓: (code, name, 止损价, 预警线1(橙), 预警线2(黄))
# 预警线: 止损价上方一定距离，提前提醒
POSITIONS_ALERTS = [
    {"code": "002230", "name": "科大讯飞", "stop_loss": 42.00,
     "alerts": [
         (42.80, "⚠️ 科大讯飞 接近止损！距止损仅0.80元", "red"),
         (43.20, "⚡ 科大讯飞 黄色预警，跌幅加大，关注止损", "orange"),
         (43.80, "📊 科大讯飞 蓝色提醒，股价持续承压", "yellow"),
     ]},
    {"code": "600760", "name": "中航沈飞", "stop_loss": 40.00,
     "alerts": [
         (40.50, "⚠️ 中航沈飞 接近止损！距止损仅0.50元", "red"),
         (41.20, "⚡ 中航沈飞 橙色预警，跌幅加大", "orange"),
         (42.00, "📊 中航沈飞 MA20位置，关注能否收复", "yellow"),
     ]},
    {"code": "603893", "name": "瑞芯微", "stop_loss": 160.00,
     "alerts": [
         (163.00, "⚠️ 瑞芯微 接近止损！距止损仅3元", "red"),
         (168.00, "⚡ 瑞芯微 橙色预警，盈利回吐", "orange"),
         (173.00, "📊 瑞芯微 MA20位置，关注支撑", "yellow"),
     ]},
]


def is_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    if time(9, 30) <= t <= time(11, 30):
        return True
    if time(13, 0) <= t <= time(15, 0):
        return True
    return False


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"triggered": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def main():
    if not is_market_hours():
        return  # 非交易时间不检测

    state = load_state()
    triggered = state.setdefault("triggered", {})
    today = datetime.now().strftime("%Y-%m-%d")

    # 从文件读取当前持仓现价
    # 这里使用腾讯行情API
    import urllib.request

    for pos in POSITIONS_ALERTS:
        code = pos["code"]
        # 获取实时价（腾讯行情）
        try:
            url = f"https://qt.gtimg.cn/q=sh{code}0001"
            if code.startswith("00") or code.startswith("30"):
                url = f"https://qt.gtimg.cn/q=sz{code}"
            else:
                url = f"https://qt.gtimg.cn/q=sh{code}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("gbk")
            # 解析: v_sh600760="..."
            items = text.split("~")
            if len(items) >= 4:
                price = float(items[3])
                change_pct = float(items[32]) if len(items) > 32 else 0.0
            else:
                print(f"{code} 行情解析失败")
                continue
        except Exception as e:
            print(f"{code} 获取行情失败: {e}")
            continue

        # 检查止损
        if price <= pos["stop_loss"]:
            key = f"{code}_stopped_{today}"
            if key not in triggered:
                triggered[key] = True
                print(f"\n🚨 止损触发: {pos['name']}({code})")
                print(f"   现价: {price:.2f} | 止损: {pos['stop_loss']:.2f}")
                print(f"   操作: 立即清仓!")
            continue

        # 检查各层预警
        for alert_price, alert_msg, level in pos["alerts"]:
            if price <= alert_price:
                key = f"{code}_{alert_price}_{today}"
                if key not in triggered:
                    triggered[key] = True
                    print(f"\n{alert_msg}")
                    print(f"   现价: {price:.2f} (跌幅{change_pct:+.2f}%)")
                break  # 只触发最接近的一个

    save_state(state)


if __name__ == "__main__":
    main()
