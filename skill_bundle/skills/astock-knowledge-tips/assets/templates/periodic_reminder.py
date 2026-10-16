# -*- coding: utf-8 -*-
"""周期性盘中提醒脚本模板 — no_agent cron 每30分钟调用, Windows Toast 弹窗播报。
用法: 在当前项目内复制到 temp/monitors/periodic_reminder_<codes>.py，
      改 CODES / LEVELS(来自当日早盘审查), 再 cronjob create:
        no_agent=true, script=<文件名>.py, schedule='*/30 9-11,13-15 * * 1-5'
验证: 先手动 python 跑一次看弹窗, 再 cronjob run + cronjob list 看 last_status。
零第三方依赖(curl/urllib + 标准库)。"""

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

import os
import re
import subprocess
import sys
import urllib.request

from core.data.tencent_fields import parse_tencent_quote

# ===== 配置区 (用户自定义持仓与关键位; 关键位来自早盘审查) =====
# 示例格式: 带 sh/sz 前缀的个股代码 + 大盘基准
CODES = [c.strip() for c in os.environ.get("REMINDER_CODES", "sh000001").split(",") if c.strip()]
LEVELS = {
    # 示例: "sh600000": {"name": "浦发银行", "stop": 9.50, "ma20": 10.05, "ma10": 9.90},
}
EXTRA = []  # 板块参照股 (可选)
STRATEGY = os.environ.get("REMINDER_STRATEGY", "策略: 防守持有不加仓 | 反抽减仓区减仓 | 破止损严格执行")

# 减仓区/加仓位等自定义触发: code -> [(lo, hi, 文案)]
ZONES = {
    # 示例: "sh600000": [(10.20, 10.50, "反抽减仓区(10.2-10.5)"), (10.80, None, "站上10.8可加仓")],
}


def fetch_via_urllib(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="replace")


def fetch_via_curl(url):
    r = subprocess.run(["curl", "-s", "--max-time", "10", url, "-H", "User-Agent: Mozilla/5.0"],
                       capture_output=True, timeout=20)
    return r.stdout.decode("gbk", errors="replace")


def get_quotes():
    url = "https://qt.gtimg.cn/q=" + ",".join(CODES + EXTRA)
    raw = None
    for fn in (fetch_via_urllib, fetch_via_curl):  # urllib 失败自动降级 curl
        try:
            raw = fn(url)
            if raw and "v_" in raw:
                break
        except Exception:
            raw = None
    if not raw:
        return None
    out = {}
    for m in re.finditer(r'v_(\w+)="([^"]*)"', raw):
        code = m.group(1)
        quote = parse_tencent_quote(m.group(0))
        if not quote:
            continue
        out[code] = {
            "name": quote["name"],
            "price": quote["price"],
            "chg": quote["change_pct"],
            "time": quote["time"],
        }
    return out


def check_levels(code, price):
    flags = []
    lv = LEVELS.get(code)
    if lv and lv.get("stop"):
        if price <= lv["stop"]:
            flags.append("⚠️ 跌破止损 → 执行止损")
        elif (price - lv["stop"]) / lv["stop"] * 100 < 1.0:
            flags.append("⚠️ 逼近止损(安全垫<1%)")
        elif lv.get("ma10") and price < lv["ma10"]:
            flags.append("破MA10,盯止损")
    for lo, hi, txt in ZONES.get(code, []):
        if lo is not None and price >= lo and (hi is None or price < hi):
            flags.append(txt)
    return flags


from pathlib import Path

# 尝试动态加载 core 模块
_cur = Path(__file__).resolve().parent
while _cur.parent != _cur:
    if (_cur / "pyproject.toml").exists() and (_cur / "core").exists():
        if str(_cur) not in sys.path:
            sys.path.insert(0, str(_cur))
        break
    _cur = _cur.parent

try:
    from core.monitor import send_windows_toast as _core_send_toast
except ImportError:
    _core_send_toast = None


def send_windows_toast(title, message):
    if _core_send_toast is not None:
        _core_send_toast(title, message)
        return
    ps_code = '''
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon((Get-Command powershell).Path)
$n.BalloonTipTitle = "%s"
$n.BalloonTipText = "%s"
$n.Visible = $true
$n.ShowBalloonTip(10000)
Start-Sleep -Seconds 12
$n.Visible = $false
$n.Dispose()
''' % (title, message)
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_code],
                       capture_output=True, timeout=20)
    except Exception:
        pass



def main():
    quotes = get_quotes()
    if not quotes:
        msg = "DATA_FETCH_FAILED 腾讯行情不可用"
        print(msg)
        send_windows_toast("盘中提醒", msg)
        sys.exit(1)

    lines = []
    for code in CODES:
        q = quotes.get(code)
        if not q or code not in LEVELS:
            continue
        lv = LEVELS[code]
        price = q["price"]
        ds = f"距止损{(price - lv['stop']) / lv['stop'] * 100:+.2f}%" if lv.get("stop") else ""
        dm = f"距MA20 {(price - lv['ma20']) / lv['ma20'] * 100:+.2f}%" if lv.get("ma20") else ""
        fl = " | " + " | ".join(check_levels(code, price)) if check_levels(code, price) else ""
        lines.append(f"{lv['name']} {price:.2f} ({q['chg']:+.2f}%) {ds} {dm}{fl}")
    for code in EXTRA:
        q = quotes.get(code)
        if q:
            lines.append(f"参照 {q['name']} {q['chg']:+.2f}%")
    idx = quotes.get("sh000001")
    if idx:
        lines.append(f"上证 {idx['price']:.2f} ({idx['chg']:+.2f}%)")

    out = "\n".join(lines)
    print(out)
    print(STRATEGY)
    send_windows_toast("🔔 盘中提醒 " + "/".join(LEVELS[c]["name"] for c in LEVELS),
                       out[:280] + "\n" + STRATEGY)


if __name__ == "__main__":
    main()
