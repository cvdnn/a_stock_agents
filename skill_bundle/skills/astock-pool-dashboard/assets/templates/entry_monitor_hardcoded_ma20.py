#!/usr/bin/env python3
"""
【模板】硬编码MA20入场监控脚本

使用方式:
  1. 在当前项目内复制到 temp/monitors/entry_monitor_<CODE>.py
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
import urllib.request
from datetime import datetime

# ======== 配置区域（编辑这里） ========
# code: (name, MA20, entry_condition, sector)
STOCK_CONFIG = {
    # "000000": ("示例股票", 50.00, "回踩MA20不破+缩量", "板块"),
}
# ======================================

import sys
from pathlib import Path

from core.workspace import PROJECT_ROOT
STATE_PATH = str(PROJECT_ROOT / "temp" / "monitor-state" / "entry_monitor_state.json")

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
        load_state as _core_load_state,
        save_state as _core_save_state,
    )
except ImportError:
    _core_is_market_hours = None
    _core_load_state = None
    _core_save_state = None

from core.data.tencent_fields import parse_tencent_quote


def is_market_hours() -> bool:
    if _core_is_market_hours is not None:
        return _core_is_market_hours(include_auction=True)
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
        quote = parse_tencent_quote(text)
        if quote:
            return {
                "price": float(quote["price"]) if quote.get("price") is not None else 0,
                "chg_pct": float(quote["change_pct"]) if quote.get("change_pct") is not None else 0,
                "turnover": float(quote["turnover_pct"]) if quote.get("turnover_pct") is not None else 0,
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
    if _core_load_state is not None:
        return _core_load_state(STATE_PATH, default={})
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    if _core_save_state is not None:
        _core_save_state(STATE_PATH, state)
        return
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
