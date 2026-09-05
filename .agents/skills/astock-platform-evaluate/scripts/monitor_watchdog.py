"""
aStocks Cron 监控模板 — 全天持仓监控

部署方式:
  AI-Platform cron create --name "全天持仓监控" --script monitor_watchdog.py \
    --schedule "every 5m" --no-agent --workdir ~/.AI-Platform/scripts --deliver all

修改此文件后重新部署:
  1. 编辑 ~/.AI-Platform/scripts/monitor_watchdog.py
  2. AI-Platform cron update <job_id> --script monitor_watchdog.py

⚠️ Python 3.9 兼容: 不要使用 dict[str, Any] | None 等联合类型语法。
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ═══════════════════════════════════════════════
#  持仓配置区 — 纯粹从 positions.csv 自动加载，杜绝代码中写死个人持仓
# ═══════════════════════════════════════════════

def load_holdings():
    """从本地持仓 CSV 动态加载持仓配置，若无则返回空列表"""
    try:
        from core.config import OUTPUT_POOLS_DIR
        pos_file = OUTPUT_POOLS_DIR / "positions.csv"
        if pos_file.exists():
            import csv
            loaded = []
            with open(pos_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    c = r.get("code", "").strip()
                    if not c:
                        continue
                    cost = float(r.get("buy_price") or 0)
                    qty = int(float(r.get("qty") or 100))
                    stop = float(r.get("stop_loss") or (cost * 0.95 if cost > 0 else 0))
                    tp = float(r.get("take_profit") or (cost * 1.05 if cost > 0 else 0))
                    is_trapped = (cost > stop and stop > 0)
                    loaded.append({
                        "code": c,
                        "name": r.get("name", c),
                        "cost": cost,
                        "shares": qty,
                        "mode": "trapped_rebound" if is_trapped else "trend_profit_lock",
                        "stop_loss_t0": round(cost * 0.95, 2),
                        "rebound_reduce_t1": round(cost * 0.98, 2),
                        "rebound_reduce_t2": round(cost * 1.02, 2),
                        "hard_stop": stop,
                        "tp1_target": tp,
                        "tp2_target": round(tp * 1.05, 2),
                        "trailing_stop": round(cost * 1.03, 2),
                        "breakeven_price": round(cost * 1.003, 2),
                    })
            if loaded:
                return loaded
    except Exception:
        pass
    return []


HOLDINGS = load_holdings()
AVAILABLE_CASH = 100000.0  # 可用资金

# 警示语库
RETAIL_WARNINGS = [
    "严格执行 A-Share Quant Engine 纪律：盈利超+5%必须上移保本线，绝不让盈利变亏损！",
    "深套标的每一次脉冲反抽都是减仓契机，严禁在左侧盲目加仓摊平成本！",
    "不要因为涨了就去追，不要因为跌了就恐慌割肉 — 一切以量化关键位为准！",
    "顺周期多头品种依托均线持股，未触及移动止盈防守线前保持定力！",
    "可用资金是战略流动性，不是用来给弱势股'抄底'的！",
    "记住你是你投资组合的风控官，执行力是量化策略唯一的生命线！",
]

# ═══════════════════════════════════════════════
#  核心逻辑
# ═══════════════════════════════════════════════
# Find project root dynamically
_cur = Path(__file__).resolve().parent
while _cur.parent != _cur:
    if (_cur / "pyproject.toml").exists() and (_cur / "core").exists():
        _ROOT = _cur
        break
    _cur = _cur.parent
else:
    _ROOT = Path(__file__).resolve().parents[3]

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(_ROOT / "core"))

from core.monitor import (
    is_market_hours as _core_is_market_hours,
    load_state as _core_load_state,
    save_state as _core_save_state,
)

STATE_FILE = Path.home() / ".AI-Platform/scripts/stock_monitor_state.json"


def is_market_hours():
    """判断是否A股交易时间"""
    if os.environ.get("FORCE_RUN_MONITOR") == "1":
        return True
    return _core_is_market_hours()


def tencent_batch_quote(codes):
    """批量获取腾讯行情"""
    codes_param = ",".join(codes)
    url = f"https://qt.gtimg.cn/q={codes_param}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode("gbk")
    except Exception:
        return {}

    results = {}
    for line in text.strip().split("\n"):
        if "~" not in line:
            continue
        parts = line.split("~")
        code = parts[2].strip() if len(parts) > 2 and parts[2].strip().isdigit() else parts[0].split("=")[0].split("_")[-1].replace("sh", "").replace("sz", "")
        try:
            price = float(parts[3])
        except (ValueError, IndexError):
            continue
        results[code] = {
            "name": parts[1],
            "price": price,
            "change_pct": float(parts[32]) if parts[32] else 0.0,
            "high": float(parts[33]) if parts[33] else price,
            "low": float(parts[34]) if parts[34] else price,
            "volume_hands": float(parts[6]) if parts[6] else 0,
        }
    return results


def load_state():
    return _core_load_state(
        STATE_FILE,
        default={"last_warning_date": "", "breakeven_activated": {}, "tp1_triggered": {}},
    )


def save_state(state):
    _core_save_state(STATE_FILE, state)



def main():
    if not HOLDINGS:
        print("ℹ️ 本地未配置持仓标的 (positions.csv 为空或不存在)，监控处于就绪状态。")
        print("   提示: 请使用 'core/cli.py position add' 录入持仓后启动监控。")
        return

    if not is_market_hours():
        print("⏸ 当前为非交易时间，监控处于待机状态 (可用 FORCE_RUN_MONITOR=1 调试)")
        return

    # 批量获取行情 (规范化前缀)
    try:
        from core.config import normalize_symbol
        codes = [normalize_symbol(h['code'], with_prefix=True) for h in HOLDINGS]
    except Exception:
        codes = [f"sh{h['code']}" if h['code'].startswith("6") else f"sz{h['code']}" for h in HOLDINGS]

    quotes = tencent_batch_quote(codes)

    if not quotes:
        print("⚠️ 行情获取失败")
        return

    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    alerts = []
    total_value = 0.0
    total_cost = 0.0

    for h in HOLDINGS:
        code = h["code"]
        q = quotes.get(code)
        if not q:
            continue

        price = q["price"]
        cost = h["cost"]
        shares = h["shares"]
        value = price * shares
        cost_total = cost * shares
        total_value += value
        total_cost += cost_total
        pnl = value - cost_total
        pnl_pct = (pnl / cost_total * 100.0) if cost_total > 0 else 0.0

        # ── 1. 恒瑞医药 (被套反弹减仓模式) ──────────────────────────
        if h.get("mode") == "trapped_rebound":
            # T0 强止损预警
            if price <= h["stop_loss_t0"]:
                alerts.append(f"🔴 【T0强止损触发】{h['name']}({code}) 现价¥{price:.2f} ≤ 止损位¥{h['stop_loss_t0']:.2f}，立即减仓1000股防极端风险！")
            elif price <= h["hard_stop"]:
                alerts.append(f"🔴 【硬止损警戒】{h['name']}({code}) 现价¥{price:.2f} 击穿Quant Engine硬止损¥{h['hard_stop']:.2f}！")
            
            # 超卖脉冲反弹到达减仓线
            if price >= h["rebound_reduce_t1"]:
                alerts.append(f"⚡ 【超卖反弹减仓点触发】{h['name']}({code}) 现价¥{price:.2f} 已达 MA5/第一阻力位 ¥{h['rebound_reduce_t1']:.2f}，果断执行阶梯减半仓(卖出1000股)！")
            elif price >= h["rebound_reduce_t1"] * 0.985:
                alerts.append(f"🔵 【逼近减仓区间】{h['name']}({code}) 现价¥{price:.2f} 距第一减仓点(¥{h['rebound_reduce_t1']:.2f})仅差 {h['rebound_reduce_t1']-price:.2f}元，准备挂单！")

        # ── 2. 紫金矿业 (趋势主升与锁利模式) ──────────────────────────
        elif h.get("mode") == "trend_profit_lock":
            # 移动止盈防守线触发
            if price <= h["trailing_stop"]:
                alerts.append(f"🟠 【移动止盈触发】{h['name']}({code}) 现价¥{price:.2f} 跌破防守线¥{h['trailing_stop']:.2f}，即刻市价卖出1000股锁定浮盈！")
            elif price <= h["trailing_stop"] * 1.015:
                alerts.append(f"🟡 【移动止盈预警】{h['name']}({code}) 现价¥{price:.2f} 逼近止盈线¥{h['trailing_stop']:.2f} (缓冲区仅 {price-h['trailing_stop']:.2f}元)")

            # 保本跳变机制
            if pnl_pct >= 5.0 and code not in state.get("breakeven_activated", {}):
                state.setdefault("breakeven_activated", {})[code] = today
                alerts.append(f"🛡️ 【保本跳变已激活】{h['name']}({code}) 浮盈已达 +{pnl_pct:.2f}%，量化引擎已强制锁定保本线 ¥{h['breakeven_price']:.2f}！")

            # 阶梯止盈第一档 (+5%)
            if price >= h["tp1_target"] and code not in state.get("tp1_triggered", {}):
                state.setdefault("tp1_triggered", {})[code] = today
                alerts.append(f"🎯 【阶梯止盈目标达成】{h['name']}({code}) 现价¥{price:.2f} 突破+5%目标价¥{h['tp1_target']:.2f}，按纪律减仓 1/3 锁定超额收益！")

        # 单日异动提醒
        if q["change_pct"] <= -3.0:
            alerts.append(f"📉 【单日异常下挫】{h['name']}({code}) 今日跌幅达 {q['change_pct']:.2f}%，成交量 {q['volume_hands']:,.0f}手")

    # 组合盈亏统计
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100.0) if total_cost > 0 else 0.0

    # 每日首次散户心理提醒
    if today != state.get("last_warning_date", ""):
        import random
        alerts.insert(0, f"🔔 【Quant Engine 每日纪律】{random.choice(RETAIL_WARNINGS)}")
        alerts.append(f"💰 当前可用资金: ¥{AVAILABLE_CASH:,.0f} (严控总权益暴露)")
        state["last_warning_date"] = today
        save_state(state)

    # 输出汇总
    print(f"\n=======================================================")
    print(f"  aStocks Watchdog — 实时风控与监控看板 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print(f"=======================================================")
    if alerts:
        print("\n".join(alerts))
    else:
        print("✅ 持仓风控指标正常，未触发警戒条件。")
    print(f"\n📊 组合全景: 总市值 ¥{total_value:,.2f} | 总盈亏 ¥{total_pnl:+,.2f} ({total_pnl_pct:+.2f}%) | 可用资金 ¥{AVAILABLE_CASH:,.2f}\n")


if __name__ == "__main__":
    main()
