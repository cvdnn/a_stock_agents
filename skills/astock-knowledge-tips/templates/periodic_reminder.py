# -*- coding: utf-8 -*-
"""周期性盘中提醒脚本模板 — no_agent cron 每30分钟调用, Windows Toast 弹窗播报。
用法: 复制到 ~/AppData/Local/AI-Platform/scripts/periodic_reminder_<codes>.py,
      改 CODES / LEVELS(来自当日早盘审查), 再 cronjob create:
        no_agent=true, script=<文件名>.py, schedule='*/30 9-11,13-15 * * 1-5'
验证: 先手动 python 跑一次看弹窗, 再 cronjob run + cronjob list 看 last_status。
零第三方依赖(curl/urllib + 标准库)。"""
import re
import subprocess
import sys
import urllib.request

# ===== 配置区(每只持仓股一条; 关键位来自当日早盘审查) =====
CODES = ["sh600276", "sh601899", "sh000001"]  # 股票(带sh/sz前缀) + 大盘
LEVELS = {
    "sh600276": {"name": "恒瑞医药", "stop": 53.00, "ma20": 54.05, "ma10": 53.80},
    "sh601899": {"name": "紫金矿业", "stop": 31.50, "ma20": 32.44, "ma10": 33.58},
}
EXTRA = ["sh600547", "sh603259"]  # 板块参照股(可选)
STRATEGY = "策略: 防守持有不加仓 | 反抽减仓区减仓 | 破止损执行"  # 策略行(写死)

# 减仓区/加仓位等自定义触发: code -> (lo, hi, 文案) 或 (price, 方向, 文案)
ZONES = {
    "sh601899": [(32.44, 33.00, "反抽减仓区(32.4-33.0)"), (33.60, None, "站上33.6可加仓")],
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
        p = m.group(2).split("~")
        if len(p) < 35:
            continue
        try:
            price, prev = float(p[3]), float(p[4])
            chg = (price - prev) / prev * 100 if prev else 0.0
        except (ValueError, IndexError):
            continue
        out[code] = {"name": p[1], "price": price, "chg": chg, "time": p[30]}
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
