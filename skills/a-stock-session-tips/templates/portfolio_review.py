# -*- coding: utf-8 -*-
"""
持仓股池每日双时段审查 (09:40 / 13:10) — a-stocks 引擎 + 腾讯行情
功能: 读取 positions.csv → 实时行情(含量比/换手/内外盘) → 技术指标(MA/MACD/KDJ/RSI/BOLL)
      → 主力动作推断(量比+内外盘+换手) → 持仓策略评估(止损/MA20/超买超卖) → Toast + stdout
零 token 成本: no_agent cron 直接投递。

使用前必改:
  1. STOP_LEVELS 止损常量 — 来自当日早盘审查，行情变化后重跑审查更新
  2. POSITIONS_CSV / SCRIPTS_DIR 路径按环境调整 (Windows 桌面 / WSL 不同)
部署: cp 到 ~/AppData/Local/AI-Platform/scripts/ 后手动 python 验证 →
      AI-Platform cron create --script <name>.py --schedule "40 9 * * 1-5" --no-agent --deliver local
      AI-Platform cron create --script <name>.py --schedule "10 13 * * 1-5" --no-agent --deliver local
"""
import csv
import json
import os
import re
import subprocess
import sys
import urllib.request

# ── 路径 ──
SCRIPTS_DIR = os.path.expanduser("~/AppData/Local/AI-Platform/skills/stocks/a-stocks/scripts")
POSITIONS_CSV = os.path.expanduser("~/AppData/Local/AI-Platform/skills/stocks/a-share-dashboard/data/positions.csv")
sys.path.insert(0, SCRIPTS_DIR)
from technical_indicators import calc_all  # noqa: E402

# ── 持仓止损纪律 (当日早盘审查确定, 每只持仓一个) ──
STOP_LEVELS = {
    "600276": 53.00,
    "601899": 31.50,
}

def fetch_via_urllib(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="replace")

def fetch_via_curl(url):
    r = subprocess.run(["curl", "-s", "--max-time", "10", url, "-H", "User-Agent: Mozilla/5.0"],
                       capture_output=True, timeout=20)
    return r.stdout.decode("gbk", errors="replace")

def get_quotes(codes):
    """codes: [(code, market), ...] market='sh'/'sz'"""
    url = "https://qt.gtimg.cn/q=" + ",".join(f"{m}{c}" for c, m in codes)
    raw = None
    for fn in (fetch_via_urllib, fetch_via_curl):
        try:
            raw = fn(url)
            if raw and "v_" in raw:
                break
        except Exception:
            raw = None
    if not raw:
        return {}
    out = {}
    for m in re.finditer(r'v_(\w+)="([^"]*)"', raw):
        code = m.group(1)
        p = m.group(2).split("~")
        if len(p) < 50:
            continue
        try:
            price, prev = float(p[3]), float(p[4])
            chg = (price - prev) / prev * 100 if prev else 0.0
            out[code] = {
                "name": p[1], "price": price, "chg": chg, "time": p[30],
                "turnover": p[38],      # 换手率%
                "volume_ratio": p[49],  # 量比
                "outer": float(p[7]) if p[7] else 0,   # 外盘
                "inner": float(p[8]) if p[8] else 0,   # 内盘
                "high": p[33], "low": p[34],
            }
        except (ValueError, IndexError):
            continue
    return out

def get_kline_tech(code, market="sh", count=120):
    """腾讯K线 → 技术指标, curl 落盘规避 urllib SSL 挂起"""
    tmp = os.path.join(os.environ.get("LOCALAPPDATA", "/tmp"), "astk_kl_" + code + ".json")
    url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{code},day,,,{count},qfq"
    ok = False
    for _ in range(3):
        r = subprocess.run(["curl", "-s", "--max-time", "8", url, "-H", "User-Agent: Mozilla/5.0"],
                           capture_output=True, timeout=15)
        if r.returncode == 0 and r.stdout:
            try:
                d = json.loads(r.stdout.decode("utf-8", errors="replace"))
                k = list(d.get("data", {}).values())[0]
                klines = k.get("qfqday") or k.get("day")
                if klines:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(klines, f)
                    ok = True
                    break
            except Exception:
                pass
    if not ok and os.path.exists(tmp):
        try:
            klines = json.load(open(tmp, encoding="utf-8"))
            ok = True
        except Exception:
            klines = []
    if not ok:
        return None
    try:
        tech = calc_all(klines)
        return tech["latest"]
    except Exception:
        return None

def send_windows_toast(title, message):
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
''' % (title.replace('"', "'"), message.replace('"', "'")[:380])
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_code],
                       capture_output=True, timeout=25)
    except Exception:
        pass

def analyze_stock(code, name, cost, qty, quote, tech):
    """综合信息 + 技术指标 + 主力动作 + 策略评估"""
    lines = []
    price = quote["price"]
    pnl = (price - cost) * qty
    pnl_pct = (price - cost) / cost * 100
    stop = STOP_LEVELS.get(code)
    dist_stop = (price - stop) / stop * 100 if stop else None

    # 主力动作推断
    vr = float(quote["volume_ratio"]) if quote["volume_ratio"] else 0
    tr = float(quote["turnover"]) if quote["turnover"] else 0
    outer, inner = quote["outer"], quote["inner"]
    ob_ratio = outer / (outer + inner) * 100 if (outer + inner) > 0 else 50.0
    if vr > 1.5 and quote["chg"] > 0:
        flow = f"放量{vr:.1f}倍↑ 外盘占{ob_ratio:.0f}% → 主力活跃偏多"
    elif vr > 1.5 and quote["chg"] < 0:
        flow = f"放量{vr:.1f}倍↓ 外盘占{ob_ratio:.0f}% → 主力出货/杀跌"
    elif vr < 0.8:
        flow = f"缩量({vr:.1f}) 换手{tr:.2f}% → 观望为主"
    else:
        flow = f"量比{vr:.1f} 换手{tr:.2f}% 外盘占{ob_ratio:.0f}% → 多空拉锯"
    lines.append(f"{name}({code}) 现价{price:.2f}({quote['chg']:+.2f}%)")
    lines.append(f"  持仓: {qty}股 成本{cost:.4f} → 浮盈亏 {pnl:+,.0f} ({pnl_pct:+.2f}%)")

    # 技术面
    if tech:
        L = tech
        ma_bull = L["ma5"] > L["ma10"] > L["ma20"]
        macd_state = "金叉" if L["dif"] > L["dea"] else "死叉"
        macd_above = "零轴上" if L["dif"] > 0 else "零轴下"
        kdj_j = L["kdj_j"]
        dist_ma20 = (price - L["ma20"]) / L["ma20"] * 100
        lines.append(
            f"  技术: MA5/10/20={L['ma5']:.2f}/{L['ma10']:.2f}/{L['ma20']:.2f} "
            f"({'多头' if ma_bull else '空头/纠缠'}) MACD{macd_above}{macd_state}"
            f"(dif {L['dif']:.3f}) KDJ_J={kdj_j:.1f} RSI={L['rsi']:.1f}"
        )
        lines.append(f"  距MA20: {dist_ma20:+.2f}%  BOLL: {L['boll_lower']:.2f}~{L['boll_mid']:.2f}~{L['boll_upper']:.2f} ATR={L['atr']:.2f}")
        # 策略信号
        signals = []
        if stop and price <= stop:
            signals.append("🔴 跌破止损，纪律性清仓")
        elif stop and dist_stop < 1:
            signals.append("🟠 逼近止损(<1%)，准备离场")
        if kdj_j < 0:
            signals.append("🟡 KDJ_J<0 极端超卖，勿恐慌割肉")
        elif kdj_j > 95:
            signals.append("🟡 KDJ_J>95 极端超买，防回调")
        if macd_above == "零轴上" and macd_state == "金叉":
            signals.append("🟢 零轴上方金叉，趋势偏强")
        if price < L["ma20"] and dist_ma20 < -3:
            signals.append("🟠 破MA20且乖离>3%，弱势")
        if pnl_pct < -5:
            signals.append("🔴 浮亏>5%，执行减仓纪律")
        lines.append("  策略: " + ("; ".join(signals) if signals else "无预警信号，按既定纪律持有"))
    else:
        lines.append("  技术: K线获取失败(降级)")
    lines.append(f"  主力: {flow}")
    return lines

def main():
    # 读取持仓池
    positions = []
    if os.path.exists(POSITIONS_CSV):
        with open(POSITIONS_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    positions.append({
                        "code": r["code"], "name": r["name"],
                        "cost": float(r["buy_price"]), "qty": int(r["qty"]),
                    })
                except (ValueError, KeyError):
                    continue
    if not positions:
        print("持仓池为空，跳过审查")
        return

    # 批量实时行情
    codes = [(p["code"], "sh" if p["code"].startswith("6") else "sz") for p in positions]
    quotes = get_quotes(codes)
    if not quotes:
        print("DATA_FETCH_FAILED 腾讯行情不可用")
        return

    lines = []
    for p in positions:
        market = "sh" if p["code"].startswith("6") else "sz"
        q = quotes.get(market + p["code"])
        if not q:
            continue
        tech = get_kline_tech(p["code"], market)
        lines.extend(analyze_stock(p["code"], p["name"], p["cost"], p["qty"], q, tech))
        lines.append("")

    # 大盘
    idx = quotes.get("sh000001")
    if idx:
        lines.append(f"上证指数 {idx['price']:.2f} ({idx['chg']:+.2f}%)")

    session = "早盘" if int(__import__("datetime").datetime.now().strftime("%H")) < 12 else "午后"
    out = f"【持仓审查 · {session}】\n" + "\n".join(lines)
    print(out)
    send_windows_toast(f"📊 持仓审查 {session}", out)

if __name__ == "__main__":
    main()