#!/usr/bin/env python3
"""
持仓沙盘 — 精简版

直接读取持仓CSV+腾讯实时行情，输出持仓状态摘要。
每15分钟由cron调用(--no-agent模式)。
数据获取失败时静默退出，不推送无意义信息。
"""
from __future__ import annotations

import sys as _astock_sys
import os as _astock_os
import json as _astock_json
from pathlib import Path as _AstPath

def _astock_resolve_bundle():
    _file_path = _AstPath(__file__).resolve()
    # 1. 自定位：自身及父目录向上查找 bundle.json
    for _p in _file_path.parents:
        if (_p / "bundle.json").is_file():
            return _p
    # 2. 兄弟定位：查找兄弟目录 a-stock-agents/bundle.json（未解析/已解析上级均探测）
    for _base in (_AstPath(__file__), _file_path):
        for _p in _base.parents:
            for _candidate in (_p / "a-stock-agents", _p.parent / "a-stock-agents"):
                if (_candidate / "bundle.json").is_file():
                    return _candidate.resolve()
    # 3. 收据定位：读取系统固定安装收据 install.json
    _receipts = []
    _env_root = _astock_os.environ.get("A_STOCK_WORKSPACE_ROOT") or _astock_os.environ.get("A_STOCK_AGENTS_ROOT")
    if _env_root:
        _receipts.append(_AstPath(_env_root) / "install.json")
    if _astock_sys.platform == "win32":
        _local = _astock_os.environ.get("LOCALAPPDATA") or (_AstPath.home() / "AppData/Local")
        _receipts.append(_AstPath(_local) / "a_stock_agents" / "install.json")
    elif _astock_sys.platform == "darwin":
        _receipts.append(_AstPath.home() / "Library/Application Support" / "a_stock_agents" / "install.json")
    else:
        _xdg = _astock_os.environ.get("XDG_DATA_HOME") or (_AstPath.home() / ".local/share")
        _receipts.append(_AstPath(_xdg) / "a_stock_agents" / "install.json")
    for _rp in _receipts:
        if _rp.is_file():
            try:
                _data = _astock_json.loads(_rp.read_text(encoding="utf-8"))
                _target = _data.get("bundle_root") or _data.get("runtime_root") or _data.get("anchor_root")
                if _target:
                    _tp = _AstPath(_target).resolve()
                    if (_tp / "bundle.json").is_file():
                        return _tp
                    if (_tp / "a-stock-agents" / "bundle.json").is_file():
                        return (_tp / "a-stock-agents").resolve()
                    if _tp.name == "runtime" and (_tp.parent / "bundle.json").is_file():
                        return _tp.parent
            except Exception:
                pass
    raise RuntimeError("ANCHOR_SKILL_MISSING: Complete a_stock_agents bundle or a-stock-agents anchor skill required")

_astock_bundle = _astock_resolve_bundle()
_astock_runtime = _astock_bundle / "runtime"
if str(_astock_runtime) not in _astock_sys.path:
    _astock_sys.path.insert(0, str(_astock_runtime))


import csv
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
def _find_project_root() -> Path:
    for p in [SCRIPT_DIR] + list(SCRIPT_DIR.parents):
        if (p / "pyproject.toml").exists() or (p / "AGENTS.md").exists():
            return p
    return SCRIPT_DIR.parents[3] if len(SCRIPT_DIR.parents) > 3 else SCRIPT_DIR.parents[2]

from core.workspace import PROJECT_ROOT
for _p in [PROJECT_ROOT, PROJECT_ROOT / "skill_bundle" / "runtime", PROJECT_ROOT / "skill_bundle" / "runtime" / "core", PROJECT_ROOT / "core"]:
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.config import OUTPUT_POOLS_DIR
from core.data.tencent_fields import parse_tencent_quote
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
            text = resp.read().decode("gbk")
            quote = parse_tencent_quote(text)
            if quote:
                return {
                    "price": quote["price"],
                    "prev_close": quote["prev_close"],
                    "change_pct": quote["change_pct"],
                    "turnover": quote["turnover_pct"] or 0,
                    "name": quote["name"],
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
