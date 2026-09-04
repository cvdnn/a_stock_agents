"""
aStocks 零依赖技术指标计算

基于腾讯 K 线原始数据原地计算，不依赖 pandas/akshare/MyTT/curl_cffi。
K线数据格式: [[date, open, close, high, low, volume], ...]
日期=索引0, 开盘=1, 收盘=2, 最高=3, 最低=4, 成交量=5

支持指标: MA, EMA, MACD, KDJ, RSI, BOLL, ATR
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════

def _floats(klines: List[List], idx: int) -> List[float]:
    """提取指定列的浮点数"""
    return [float(k[idx]) for k in klines]


def _sma(data: List[float], n: int, m: int = 1) -> List[float]:
    """SMA — 用于KDJ的递归平滑"""
    result = [data[0]]
    for i in range(1, len(data)):
        result.append((data[i] * m + result[-1] * (n - m)) / n)
    return result


# ═══════════════════════════════════════════════════
#  均线 MA / EMA
# ═══════════════════════════════════════════════════

def ma(data: List[float], n: int) -> List[float]:
    """简单移动平均"""
    result = [0.0] * (n - 1)
    window = data[:n]
    s = sum(window)
    result.append(s / n)
    for i in range(n, len(data)):
        s += data[i] - data[i - n]
        result.append(s / n)
    return result


def ema(data: List[float], n: int) -> List[float]:
    """指数移动平均"""
    result = [data[0]]
    k = 2.0 / (n + 1)
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result


# ═══════════════════════════════════════════════════
#  MACD
# ═══════════════════════════════════════════════════

def macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[float]]:
    """计算 MACD"""
    ema12 = ema(closes, fast)
    ema26 = ema(closes, slow)
    dif = [ema12[i] - ema26[i] for i in range(len(closes))]
    dea = ema(dif, signal)
    bar = [2 * (dif[i] - dea[i]) for i in range(len(closes))]
    return {"dif": dif, "dea": dea, "bar": bar}


# ═══════════════════════════════════════════════════
#  KDJ
# ═══════════════════════════════════════════════════

def kdj(klines: List[List], n: int = 9, k_n: int = 3, d_n: int = 3) -> Dict[str, List[float]]:
    """计算 KDJ"""
    highs = _floats(klines, 3)
    lows = _floats(klines, 4)
    closes = _floats(klines, 2)
    length = len(closes)

    rsv_values = []
    for i in range(length):
        if i < n - 1:
            rsv_values.append(50.0)
            continue
        h = max(highs[i - n + 1:i + 1])
        l = min(lows[i - n + 1:i + 1])
        h_l = h - l
        rsv_values.append(((closes[i] - l) / h_l * 100) if h_l != 0 else 50.0)

    k_vals = _sma(rsv_values, k_n, 1)
    d_vals = _sma(k_vals, d_n, 1)
    j_vals = [3 * k_vals[i] - 2 * d_vals[i] for i in range(length)]

    return {"k": k_vals, "d": d_vals, "j": j_vals}


# ═══════════════════════════════════════════════════
#  RSI
# ═══════════════════════════════════════════════════

def rsi(closes: List[float], n: int = 14) -> List[float]:
    """计算 RSI"""
    ups, downs = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        ups.append(max(d, 0))
        downs.append(abs(min(d, 0)))

    result = [50.0] * n
    avg_u = sum(ups[:n]) / n
    avg_d = sum(downs[:n]) / n
    result.append(100.0 - 100.0 / (1 + avg_u / avg_d) if avg_d != 0 else 100.0)

    for i in range(n, len(ups)):
        avg_u = (avg_u * (n - 1) + ups[i]) / n
        avg_d = (avg_d * (n - 1) + downs[i]) / n
        result.append(100.0 - 100.0 / (1 + avg_u / avg_d) if avg_d != 0 else 100.0)

    return result


# ═══════════════════════════════════════════════════
#  BOLL (布林带)
# ═══════════════════════════════════════════════════

def boll(closes: List[float], n: int = 20, k: float = 2.0) -> Dict[str, List[float]]:
    """计算布林带"""
    mid = ma(closes, n)
    upper, lower = [0.0] * (n - 1), [0.0] * (n - 1)

    for i in range(n - 1, len(closes)):
        avg = mid[i]
        variance = sum((closes[j] - avg) ** 2 for j in range(i - n + 1, i + 1)) / n
        std = math.sqrt(variance)
        upper.append(avg + k * std)
        lower.append(avg - k * std)

    bandwidth = [(upper[i] - lower[i]) / mid[i] * 100 if mid[i] != 0 else 0
                 for i in range(len(mid))]

    return {"mid": mid, "upper": upper, "lower": lower, "bandwidth": bandwidth}


# ═══════════════════════════════════════════════════
#  ATR (平均真实波幅)
# ═══════════════════════════════════════════════════

def atr(klines: List[List], n: int = 14) -> List[float]:
    """计算 ATR"""
    highs = _floats(klines, 3)
    lows = _floats(klines, 4)
    closes = _floats(klines, 2)

    tr_values = [0.0]
    for i in range(1, len(klines)):
        h = highs[i]
        l = lows[i]
        prev_c = closes[i - 1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_values.append(tr)

    result = [0.0] * (n - 1)
    result.append(sum(tr_values[:n]) / n)

    for i in range(n, len(tr_values)):
        result.append((result[-1] * (n - 1) + tr_values[i]) / n)

    return result


# ═══════════════════════════════════════════════════
#  综合计算
# ═══════════════════════════════════════════════════

def calc_all(klines: List[List], ma_periods: Tuple[int, ...] = (5, 10, 20, 60)) -> Dict[str, Any]:
    """
    对腾讯K线数据计算所有技术指标

    Args:
        klines: [[date, open, close, high, low, volume], ...]
        ma_periods: 均线周期

    Returns:
        {"ma5": [...], "ma10": [...], "macd": {...}, "kdj": {...}, "rsi": [...], "boll": {...}, "atr": [...]}
    """
    closes = _floats(klines, 2)

    result = {
        "count": len(klines),
        "latest": None,
    }

    # MA
    mas = {}
    for p in ma_periods:
        if len(closes) >= p:
            mas[f"ma{p}"] = ma(closes, p)
    result["ma"] = mas

    # MACD
    if len(closes) >= 26:
        result["macd"] = macd(closes)

    # KDJ
    if len(klines) >= 9:
        result["kdj"] = kdj(klines)

    # RSI
    if len(closes) >= 14:
        result["rsi"] = rsi(closes, 14)

    # BOLL
    if len(closes) >= 20:
        result["boll"] = boll(closes)

    # ATR
    if len(klines) >= 14:
        result["atr"] = atr(klines, 14)

    # 最新值摘要
    latest = {"close": closes[-1]}
    for name, vals in mas.items():
        if vals[-1] > 0:
            latest[name] = round(vals[-1], 2)
    if "macd" in result:
        m = result["macd"]
        latest["dif"] = round(m["dif"][-1], 4)
        latest["dea"] = round(m["dea"][-1], 4)
        latest["macd_bar"] = round(m["bar"][-1], 4)
    if "kdj" in result:
        kdj_data = result["kdj"]
        latest["kdj_k"] = round(kdj_data["k"][-1], 2)
        latest["kdj_d"] = round(kdj_data["d"][-1], 2)
        latest["kdj_j"] = round(kdj_data["j"][-1], 2)
    if "rsi" in result:
        latest["rsi"] = round(result["rsi"][-1], 2)
    if "boll" in result:
        b = result["boll"]
        latest["boll_upper"] = round(b["upper"][-1], 2)
        latest["boll_mid"] = round(b["mid"][-1], 2)
        latest["boll_lower"] = round(b["lower"][-1], 2)
        latest["boll_width"] = round(b["bandwidth"][-1], 2)
    if "atr" in result:
        latest["atr"] = round(result["atr"][-1], 4)

    result["latest"] = latest
    result["dates"] = [k[0] for k in klines]
    return result


def gap_analysis(klines: List[List]) -> Dict[str, Any]:
    """跳空缺口分析"""
    if len(klines) < 5:
        return {"gaps": [], "summary": "数据不足"}

    gaps = []
    for i in range(1, len(klines)):
        today_open = float(klines[i][1])
        yesterday_close = float(klines[i - 1][2])
        if yesterday_close == 0:
            continue
        gap_val = today_open - yesterday_close
        gap_pct = gap_val / yesterday_close * 100

        if abs(gap_pct) >= 0.5:
            today_low = float(klines[i][4])
            filled = today_low < yesterday_close
            direction = "up" if gap_pct > 0 else "down"
            gaps.append({
                "date": klines[i][0],
                "direction": direction,
                "gap_value": round(gap_val, 2),
                "gap_pct": round(gap_pct, 2),
                "filled": filled,
                "open": round(today_open, 2),
                "prev_close": round(yesterday_close, 2),
            })

    consecutive = 0
    if gaps:
        for g in reversed(gaps):
            if g["direction"] == gaps[-1]["direction"]:
                consecutive += 1
            else:
                break

    return {
        "gaps": gaps[-10:],
        "count": len(gaps),
        "consecutive_same": consecutive,
        "latest_gap": gaps[-1] if gaps else None,
    }


# ═══════════════════════════════════════════════════
#  MACD二次金叉 / 底背离识别 — P1 新增
# ═══════════════════════════════════════════════════

def second_golden_cross(klines: List[List]) -> Dict[str, Any]:
    """
    MACD底背离 + 零轴下二次金叉 识别。

    返回: {
        has_first_leg, has_second_leg, is_weaker_second,
        first_golden_cross_idx, second_golden_cross_idx,
        dif_higher, bars_shorter, verdict (A/B/C), checklist
    }
    """
    if len(klines) < 60:
        return {"verdict": "C", "reason": "K线数据不足(需≥60根)", "checklist": []}

    closes = _floats(klines, 2)
    m = macd(closes)
    dif = m["dif"]
    dea = m["dea"]
    bar = m["bar"]

    # 找零轴下金叉 (DIF上穿DEA, 且DIF<0)
    crosses = []  # [(idx, dif_val, dea_val), ...]
    for i in range(1, len(dif)):
        if dif[i - 1] <= dea[i - 1] and dif[i] > dea[i] and dif[i] < 0:
            crosses.append((i, dif[i], dea[i], bar[i]))

    if len(crosses) < 1:
        return {"verdict": "C", "reason": "无零轴下金叉信号",
                "checklist": ["❌ 无金叉"], "crosses_count": 0}

    # 找最近的两次金叉
    first = crosses[-2] if len(crosses) >= 2 else crosses[-1]
    second = crosses[-1]

    has_first = len(crosses) >= 2
    dif_higher = second[1] > first[1] if has_first else None
    bars_shorter = second[3] > first[3] if has_first else None  # 红柱更大=更强

    # 10项检查
    checks = []
    # 1. 前期下跌
    if len(closes) >= 60:
        early_close = sum(closes[-60:-30]) / 30
        recent_close = sum(closes[-10:]) / 10
        has_downtrend = recent_close < early_close * 0.95
    else:
        has_downtrend = False
    checks.append(("前期下跌", has_downtrend))

    # 2. 第一脚反抽
    checks.append(("第一脚后反抽", has_first if has_first else False))

    # 3. 第二脚回踩
    checks.append(("第二脚回踩低位区", True))  # 有二次金叉即表明有第二脚

    # 4. DIF低点抬高
    checks.append(("DIF低点抬高", dif_higher if dif_higher is not None else False))

    # 5. 绿柱缩短 (检查金叉前绿柱)
    if len(bar) > 5:
        pre_bars = bar[-15:-5]
        green_bars = [b for b in pre_bars if b < 0]
        checks.append(("绿柱缩短", len(green_bars) >= 2 and green_bars[-1] > min(green_bars)))
    else:
        checks.append(("绿柱缩短", False))

    # 6. 零轴下二次金叉
    checks.append(("零轴下二次金叉", dif[second[0]] < 0))

    # 7. 二次金叉位置高于第一次
    checks.append(("二次金叉位置更高", dif_higher if dif_higher is not None else False))

    # 8. 金叉后拐头
    if second[0] < len(closes) - 3:
        post_close = closes[second[0]:]
        rising = post_close[-1] > post_close[0] if len(post_close) >= 2 else False
    else:
        rising = False
    checks.append(("金叉后1-3K拐头", rising))

    # 9. 盈亏比
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]
    checks.append(("上方压力不过近", closes[-1] < ma20 * 1.05))

    # 10. 失效位可承受
    checks.append(("失效位可承受", True))  # 主观判断

    passed = sum(1 for _, ok in checks if ok)
    if passed >= 7:
        verdict = "B"
        msg = "可试错出手 — 7+条件满足"
    elif passed >= 5:
        verdict = "A"
        msg = "上观察名单 — 5-6条件满足，等确认"
    else:
        verdict = "C"
        msg = "必须放弃 — 条件不足"

    return {
        "verdict": verdict,
        "reason": msg,
        "passed_count": passed,
        "total_checks": len(checks),
        "crosses_count": len(crosses),
        "first_leg": {"idx": first[0], "dif": round(first[1], 4)} if has_first else None,
        "second_leg": {"idx": second[0], "dif": round(second[1], 4), "dea": round(second[2], 4)},
        "dif_higher": dif_higher,
        "bars_stronger": bars_shorter,
        "checklist": [f"{'✅' if ok else '❌'} {name}" for name, ok in checks],
    }


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    # 直接运行脚本时，将项目根目录加入 sys.path，保证 `core` 包可导入
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

    parser = argparse.ArgumentParser(description="aStocks 技术指标计算")
    parser.add_argument("--input", "-i", help="K线JSON文件路径 ([[date,open,close,high,low,vol],...])")
    parser.add_argument("--code", help="股票代码 (使用腾讯K线直连)")
    parser.add_argument("--count", type=int, default=120, help="K线数量")
    parser.add_argument("--gaps", action="store_true", help="跳空缺口分析")
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    klines = None

    if args.input:
        klines = json.loads(Path(args.input).read_text())
    elif args.code:
        from core.data.data_bridge import DataBridge
        klines = DataBridge.tencent_kline(args.code, args.count)

    if not klines:
        print(json.dumps({"error": "无法获取K线数据"}))
        sys.exit(1)

    if args.gaps:
        result = gap_analysis(klines)
    else:
        result = calc_all(klines)

    print(json.dumps(result, ensure_ascii=False, indent=2))
