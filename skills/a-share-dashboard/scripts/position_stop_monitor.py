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

import csv
import json
import os
import sys
from datetime import datetime, time
from pathlib import Path

# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core"))

from core.config import OUTPUT_POOLS_DIR, OUTPUT_CACHE_DIR
POSITIONS_PATH = OUTPUT_POOLS_DIR / "positions.csv"
STATE_FILE = OUTPUT_CACHE_DIR / "position_stop_monitor_state.json"


def load_positions_alerts() -> list[dict]:
    """从当前 OUTPUT_POOLS_DIR/positions.csv 动态读取持仓并生成风控预警线"""
    alerts = []
    if POSITIONS_PATH.exists():
        try:
            with open(POSITIONS_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = row.get("code", "").strip()
                    name = row.get("name", "").strip() or code
                    stop_loss_str = row.get("stop_loss", "").strip()
                    if not code:
                        continue
                    try:
                        stop_loss = float(stop_loss_str) if stop_loss_str else 0.0
                    except ValueError:
                        stop_loss = 0.0
                    
                    if stop_loss > 0:
                        a1 = round(stop_loss * 1.01, 2)
                        a2 = round(stop_loss * 1.02, 2)
                        a3 = round(stop_loss * 1.03, 2)
                        alerts.append({
                            "code": code,
                            "name": name,
                            "stop_loss": stop_loss,
                            "alerts": [
                                (a1, f"⚠️ {name} 接近止损！距止损仅 {a1 - stop_loss:.2f}元", "red"),
                                (a2, f"⚡ {name} 橙色预警，跌幅加大，关注止损线", "orange"),
                                (a3, f"📊 {name} 关注支撑位置，警惕回调风险", "yellow"),
                            ]
                        })
        except Exception:
            pass
    return alerts


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
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"triggered": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    force = "--show" in sys.argv or "--force" in sys.argv or "-f" in sys.argv
    if not force and not is_market_hours():
        return  # 非交易时间不检测

    positions = load_positions_alerts()
    if not positions:
        if force:
            print("持仓池 (positions.csv) 中暂无已配置止损价的标的。")
        return

    if force:
        print(f"📊 持仓风控监控 (共 {len(positions)} 只):")
        for pos in positions:
            print(f"  - [{pos['code']}] {pos['name']} 止损价: {pos['stop_loss']:.2f}")

    state = load_state()
    triggered = state.setdefault("triggered", {})
    today = datetime.now().strftime("%Y-%m-%d")

    from core.data.data_bridge import DataBridge
    bridge = DataBridge()

    for pos in positions:
        code = pos["code"]
        q = bridge.get_realtime_quote(code)
        if not q or "price" not in q or q.get("price", 0) <= 0:
            if force:
                print(f"{code} 获取实时行情失败")
            continue

        price = float(q["price"])
        change_pct = float(q.get("change_pct", 0.0))

        # 检查止损
        if price <= pos["stop_loss"]:
            key = f"{code}_stopped_{today}"
            if key not in triggered:
                triggered[key] = True
                print(f"\n🚨 止损触发: {pos['name']}({code})")
                print(f"   现价: {price:.2f} | 止损: {pos['stop_loss']:.2f}")
                print(f"   操作: 达到纪律止损位，建议执行纪律减仓/清仓!")
            continue

        # 检查各层预警
        for alert_price, alert_msg, level in pos["alerts"]:
            if price <= alert_price:
                key = f"{code}_{alert_price}_{today}"
                if key not in triggered:
                    triggered[key] = True
                    print(f"\n{alert_msg}")
                    print(f"   现价: {price:.2f} (涨跌: {change_pct:+.2f}%) | 止损参考: {pos['stop_loss']:.2f}")
                break  # 只触发最接近的一个

    save_state(state)


if __name__ == "__main__":
    main()
