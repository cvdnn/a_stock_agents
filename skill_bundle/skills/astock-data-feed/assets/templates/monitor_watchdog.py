#!/usr/bin/env python3
"""
股价监控模板 — 用于 no_agent cron 定时任务
在当前项目内复制到 temp/monitors/ 并修改以下配置：
  CODE, NAME, TRIGGERS, COST_PRICE, HOLDINGS

触发价从高到低排列（向上/向下混合排列），
通过 key 前缀 '__up__' 标记向上触发、'__down__' 标记向下触发。
到达后发送 Windows Toast + AI-Platform 消息推送。

实战验证：2026-07-20 中航沈飞(600760) 5档双向触发监控已部署运行。
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


import json
import os
import subprocess
from datetime import datetime, time

# ══════════════════ 用户配置区 ══════════════════
CODE = "000000"          # 6位股票代码
NAME = "股票名称"
TRIGGERS = [            # (触发价, 操作建议, 唯一key)  从高到低排列！
    # 向上触发（反弹/成本位）用 __up__ 前缀标记 key
    (0.0, "反弹至某阻力位，建议减仓", "__up__ma60"),
    (0.0, "反弹至成本位，可平本出局", "__up__cost"),
    # 向下触发（止损/支撑）用 __down__ 前缀标记 key（默认行为）
    (0.0, "跌破支撑，建议减仓", "__down__ma20"),
    (0.0, "逼近强支撑，关注企稳", "__down__boll_lower"),
    (0.0, "跌停/前低！建议清仓", "__down__stop_loss"),
]
COST_PRICE = 0.0         # 0 表示不计算浮亏
HOLDINGS = 0
# ═══════════════════════════════════════════════

import sys
from pathlib import Path

from core.workspace import PROJECT_ROOT
from core.data.tencent_fields import parse_tencent_quote
STATE_FILE = str(PROJECT_ROOT / "temp" / "monitor-state" / f"stock_monitor_{CODE}_state.json")

# 尝试动态加载 core 模块
_cur = Path(__file__).resolve().parent
while _cur.parent != _cur:
    if (_cur / "pyproject.toml").exists() and (_cur / "core").exists():
        if str(_cur) not in sys.path:
            sys.path.insert(0, str(_cur))
        break
    _cur = _cur.parent

try:
    from core.monitor import (
        is_market_hours as _core_is_market_hours,
        send_windows_toast as _core_send_toast,
        load_state as _core_load_state,
        save_state as _core_save_state,
    )
except ImportError:
    _core_is_market_hours = None
    _core_send_toast = None
    _core_load_state = None
    _core_save_state = None


def is_market_hours() -> bool:
    """A股交易时间：9:30-11:30 / 13:00-15:00，排除周末"""
    if _core_is_market_hours is not None:
        return _core_is_market_hours()
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    if time(9, 30) <= t <= time(11, 30):
        return True
    if time(13, 0) <= t <= time(15, 0):
        return True
    return False


def send_windows_toast(title: str, message: str) -> None:
    if _core_send_toast is not None:
        _core_send_toast(title, message)
        return
    ps_code = f'''
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon((Get-Command powershell).Path)
$n.BalloonTipTitle = "{title}"
$n.BalloonTipText = "{message}"
$n.Visible = $true
$n.ShowBalloonTip(10000)
Start-Sleep -Seconds 12
$n.Visible = $false
$n.Dispose()
'''
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_code],
                       capture_output=True, timeout=15)
    except Exception:
        pass


def get_price() -> float | None:
    """腾讯API直连 — 比 fetch_realtime.py 快10x(105ms), 零依赖, 避免pandas/akshare/cffi断链"""
    import urllib.request
    try:
        prefix = "sh" if CODE.startswith(("6", "9")) else "sz"
        url = f"https://qt.gtimg.cn/q={prefix}{CODE}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode("gbk")
        for line in text.strip().split("\n"):
            quote = parse_tencent_quote(line)
            if quote and quote.get("price") is not None:
                return float(quote["price"])
    except Exception:
        pass
    return None


def load_state() -> dict:
    if _core_load_state is not None:
        return _core_load_state(STATE_FILE, default={"fired": []})
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"fired": []}


def save_state(state: dict) -> None:
    if _core_save_state is not None:
        _core_save_state(STATE_FILE, state)
        return
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)



def main():
    if not is_market_hours():
        return  # 非交易时间 → 静默

    state = load_state()
    price = get_price()
    if price is None:
        return  # 获取失败 → 静默

    messages = []
    for target_price, action, key in TRIGGERS:
        if key in state["fired"]:
            continue

        # 双向触发判断：__up__ 前缀=股价>=触发价，否则=股价<=触发价
        is_up = key.startswith("__up__")
        triggered = price >= target_price if is_up else price <= target_price

        if triggered:
            loss_info = ""
            if COST_PRICE > 0 and HOLDINGS > 0:
                loss_pct = (price - COST_PRICE) / COST_PRICE * 100
                loss_info = (
                    f"\n当前浮亏: {loss_pct:.1f}%\n"
                    f"持仓: {HOLDINGS}股，成本 {COST_PRICE}元"
                )
            direction_mark = "↑" if is_up else "↓"
            msg = (
                f"{direction_mark} {NAME} 触发提醒\n"
                f"触发价 {target_price} 已到达！当前 {price:.2f}元\n"
                f"{action}"
                f"{loss_info}"
            )
            messages.append(msg)
            state["fired"].append(key)
            send_windows_toast(
                f"{NAME} 触发提醒",
                f"触发价 {target_price}元！当前 {price:.2f}元\n{action}"
            )

    if messages:
        save_state(state)
        print("\n---\n".join(messages))
    # 无触发 → 不输出任何内容（静默）


if __name__ == "__main__":
    main()
