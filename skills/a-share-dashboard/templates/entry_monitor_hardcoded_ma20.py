#!/usr/bin/env python3
"""
【模板】硬编码MA20入场监控脚本

使用方式:
  1. 复制此文件到 ~/.AI-Platform/scripts/entry_monitor_<CODE>.py
  2. 编辑 STOCK_CONFIG 填入目标股票的MA20值（每日收盘后从策略跑分获取）
  3. 部署 cron: AI-Platform cron create --name "监控名称" --script entry_monitor_<CODE>.py --schedule "every 5m" --no-agent --deliver all

原理:
  MA20日线一天只变化一次，不需要每次检测都重新获取。
  脚本仅用腾讯实时行情API（2秒返回）获取现价，与硬编码MA20对比。
  避免proxy-patch Eastmoney链路超时导致监控失效。

注意:
  - MA20值从 daily_decisions.py 或 fetch_history.py 获取（参见 a-share-dashboard 模块五）
  - 每日收盘后需更新 MA20 值（误差<0.5%可接受）
  - 腾讯API使用 http:// 协议，no-agent cron 模式下可直连
"""
import json
import os
import urllib.request
from datetime import datetime

# ======== 配置区域（编辑这里） ========
# code: (name, MA20, entry_condition, sector)
STOCK_CONFIG = {
    # "000000": ("示例股票", 50.00, "回踩MA20不破+缩量", "板块"),
}
# ======================================

STATE_PATH = os.path.expanduser("~/.AI-Platform/scripts/entry_monitor_state.json")


def is_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9*60+25 <= t <= 11*60+30) or (13*60 <= t <= 15*60)


def get_price(code: str) -> dict:
    """腾讯实时行情（2秒返回，支持实时价/涨跌幅/换手率）"""
    prefix = "sh" if code.startswith("60") else "sz"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=5)
        text = resp.read().decode('gbk')
        parts = text.split('~')
        if len(parts) >= 39:
            return {
                "price": float(parts[3]) if parts[3] else 0,
                "chg_pct": float(parts[32]) if parts[32] else 0,
                "turnover": float(parts[38]) if parts[38] else 0,
            }
    except:
        pass
    return {}


def check_entry(code: str, quote: dict) -> dict:
    """检测入场条件"""
    result = {"triggered": False, "reason": "", "confidence": "低"}
    if not quote:
        return result

    config = STOCK_CONFIG.get(code)
    if not config:
        return result

    name, ma20, entry_cond, sector = config
    price = quote.get("price", 0)
    chg = quote.get("chg_pct", 0)
    turnover = quote.get("turnover", 0)

    if price == 0 or ma20 == 0:
        return result

    dist = (price - ma20) / ma20 * 100
    triggers = []

    # 条件1: 价在MA20上方且距MA20 < 3%（回踩不破）
    if price > ma20 and dist < 3:
        triggers.append(f"回踩MA20({ma20:.2f})仅{dist:.1f}%")

    # 条件2: 缩量（换手率<3%）
    if turnover < 3:
        triggers.append(f"缩量(换手{turnover:.1f}%)")

    if len(triggers) >= 1:
        result["triggered"] = True
        result["reason"] = " + ".join(triggers)
        result["confidence"] = "高" if len(triggers) >= 2 else "中"
        result["price"] = price
        result["change"] = chg

    return result


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, ensure_ascii=False)


def main():
    if not is_market_hours():
        return

    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("date") != today:
        state = {"date": today, "triggered": {}}
    if "triggered" not in state:
        state["triggered"] = {}

    alerts = []

    for code, (name, ma20, entry_cond, sector) in STOCK_CONFIG.items():
        if state["triggered"].get(code):
            continue

        quote = get_price(code)
        if not quote:
            continue

        result = check_entry(code, quote)

        if result.get("triggered"):
            alerts.append(
                f"⚡ 入场信号: {code} {name}\n"
                f"  条件: {result['reason']}\n"
                f"  现价: {result['price']:.2f} ({result.get('change', 0):+.2f}%)\n"
                f"  可信度: {result['confidence']} | 建议: 评估开仓"
            )
            state["triggered"][code] = True

    save_state(state)

    if alerts:
        print("\n\n".join(alerts))


if __name__ == "__main__":
    main()
