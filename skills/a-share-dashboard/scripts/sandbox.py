#!/usr/bin/env python3
"""
持仓沙盘 — 精简版

直接读取持仓CSV+腾讯实时行情，输出持仓状态摘要。
每15分钟由cron调用(--no-agent模式)。
数据获取失败时静默退出，不推送无意义信息。
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core"))

from core.config import OUTPUT_POOLS_DIR
POSITIONS_PATH = OUTPUT_POOLS_DIR / "positions.csv"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_quote(code: str) -> dict:
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            items = resp.read().decode("gbk").split("~")
            if len(items) >= 40:
                return {
                    "price": float(items[3]),
                    "prev_close": float(items[4]),
                    "change_pct": float(items[32]),
                    "turnover": float(items[38]) if items[38] else 0,
                    "name": items[1],
                }
    except:
        pass
    return {}


def main():
    rows = read_csv(POSITIONS_PATH)
    if not rows:
        return  # 无持仓，静默退出

    results = []
    for r in rows:
        code = r.get("code", "")
        name = r.get("name", "")
        try:
            buy_price = float(r.get("buy_price", 0))
            qty = int(r.get("qty", 0))
            stop_loss = float(r.get("stop_loss", 0)) if r.get("stop_loss") else None
        except:
            continue

        quote = get_quote(code)
        if not quote:
            continue

        cur_price = quote["price"]
        pnl_pct = (cur_price - buy_price) / buy_price * 100
        stop_dist = (cur_price - stop_loss) / stop_loss * 100 if stop_loss else None

        results.append({
            "code": code, "name": name or quote.get("name", ""),
            "buy": buy_price, "cur": cur_price,
            "pnl_pct": round(pnl_pct, 1),
            "change_today": quote["change_pct"],
            "stop": stop_loss, "stop_dist": round(stop_dist, 1) if stop_dist else None,
            "strategy": r.get("strategy", ""),
            "reason": r.get("reason", ""),
        })

    if not results:
        return  # 全部获取失败，静默

    # 输出
    now = datetime.now().strftime("%H:%M")
    total_pnl = sum(r["pnl_pct"] for r in results)
    
    print(f"📊 持仓沙盘 · {now}")
    print(f"  {'─'*28}")
    
    for r in results:
        icon = "📈" if r["pnl_pct"] >= 0 else "📉"
        alert = " ⚠️" if r["stop_dist"] and r["stop_dist"] < 3 else ""
        print(f"  {icon} {r['code']} {r['name']}")
        print(f"     买入{r['buy']:.2f}→现{r['cur']:.2f} | {r['pnl_pct']:+.1f}%")
        if r["stop"]:
            print(f"     止损{r['stop']:.2f} | 距{r['stop_dist']:+.1f}%{alert}")
    
    print(f"  {'─'*28}")
    print(f"  下次更新: +15分钟")


if __name__ == "__main__":
    main()
