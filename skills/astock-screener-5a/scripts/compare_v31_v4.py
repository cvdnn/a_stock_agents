#!/usr/bin/env python3
"""v3.1(增强6因子) vs v4(完整五维) 短线选股对比 — 胜率与风险规避评估
对置位候选池跑两种评分, 接入风险因子(股价/PE/市值/换手/近期下跌/60日动量/相对高位/波动/长期亏损),
统计两种方法高分股的重合度、风险画像、短线后续收益(胜率)。
运行: python compare_v31_v4.py
"""
import sys, os, json, datetime
import statistics
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PROJECT_ROOT / "core" / "data") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core" / "data"))
if str(PROJECT_ROOT / "core" / "indicators") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core" / "indicators"))
if str(PROJECT_ROOT / "core" / "models") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core" / "models"))

from data_bridge import DataBridge
from technical_indicators import calc_all
from multi_dim_model_v3 import FiveDimScorer, _latest_at, _hist_market


# 候选池 (主板蓝筹+行业龙头, 同 screen)
CANDIDATES = ["600519","000858","600036","601318","600406","002230","002475","601899",
              "600887","601012","600584","002371","603259","002594","600030","600900",
              "000333","600276","601138","600941","600309","601668","600028","601088"]

# =============================================
# v3.1 增强6因子评分 (从旧 diff 重建, 口径与当时回测完全一致)
# =============================================
def score_v31(closes, volumes, opens, klines, day):
    """增强6因子: tech(MA对齐20+RSI15) + vol(量价25+量比) + struct(MA20回踩20) + fund(动量20)"""
    if day < 20:
        return 0.0
    s = closes[:day+1]
    v = volumes[:day+1] if len(volumes) >= day+1 else [0]*(day+1)
    c = s[-1]
    ma20 = sum(s[-20:])/20
    ma5 = sum(s[-5:])/5
    ma10 = sum(s[-10:])/10
    # RSI(14)
    if len(s) >= 15:
        gains = [max(0, s[i]-s[i-1]) for i in range(-14,0)]
        losses = [max(0, s[i-1]-s[i]) for i in range(-14,0)]
        ag = sum(gains)/14; al = sum(losses)/14
        rsi = 100-100/(1+ag/al) if al > 0 else 100
    else:
        rsi = 50
    # Tech: MA alignment(20) + RSI(15)
    if ma5 > ma10 > ma20 > sum(s[-60:])/60:
        tech_ma = 20
    elif ma5 > ma10 > ma20:
        tech_ma = 16
    elif c > ma20:
        tech_ma = 12
    else:
        tech_ma = 4
    tech_rsi = 15 if 40 <= rsi <= 68 else (10 if 30 <= rsi < 40 else 6)
    tech_s = tech_ma + tech_rsi
    # Volume(25): 量比 + 量价
    vol_5 = sum(v[-5:])/5 if len(v) >= 5 else 0
    vol_20 = sum(v[-20:])/20 if len(v) >= 20 else 1
    vol_ratio = vol_5/vol_20 if vol_20 > 0 else 1.0
    open_today = opens[day] if day < len(opens) else c
    if c > open_today and vol_5 > vol_20:
        vol_s = 25
    elif vol_ratio < 0.8 and c > ma20:
        vol_s = 22
    elif vol_5 > 1.2*vol_20:
        vol_s = 18
    elif vol_5 > vol_20:
        vol_s = 14
    else:
        vol_s = 8
    # Structure(20): MA20回踩
    dist = abs(c-ma20)/ma20*100 if ma20 > 0 else 100
    if c > ma20 and 0 < dist <= 5:
        struct_s = 20
    elif c > ma20 and dist <= 10:
        struct_s = 15
    elif c > ma20:
        struct_s = 10
    else:
        struct_s = 5
    # Fund(20): 动量
    mom20 = (s[-1]/s[-20]-1)*100 if len(s) >= 20 else 0
    mom60 = (s[-1]/s[-60]-1)*100 if len(s) >= 60 else 0
    if mom20 > 2 and mom60 > 5: fund_s = 20
    elif mom20 > 0 and mom60 > 0: fund_s = 15
    elif mom20 > -3 and mom60 > 0: fund_s = 10
    else: fund_s = 5
    return tech_s + vol_s + struct_s + fund_s  # max ~100

def main():
    bridge = DataBridge()
    five = FiveDimScorer()
    rows = []
    for code in CANDIDATES:
        try:
            kl = bridge.tencent_kline(code, 260)
            if not kl or len(kl) < 60:
                print(f"  SKIP {code}: 数据不足"); continue
            closes = [float(k[2]) for k in kl]
            opens = [float(k[1]) for k in kl]
            volumes = [float(k[5]) for k in kl if len(k) > 5]
            day = len(closes) - 1
            # 两种评分 (当日)
            v31 = score_v31(closes, volumes, opens, kl, day)
            tech_all = calc_all(kl)
            latest = _latest_at(tech_all, day)
            tech_day = {"macd": {"bar": tech_all["macd"]["bar"][:day+1]}}
            sh = closes  # 无上证, 市场静态用中性
            s4 = five.score(kl, tech_day, latest, None, "震荡", 50)
            v4 = s4["cs"]
            # 风险因子
            quotes = bridge.get_realtime_quote(code)
            price = float(closes[-1])
            ma20 = sum(closes[-20:])/20
            ma60 = sum(closes[-60:])/60
            hi250 = max(closes[-250:]) if len(closes) >= 250 else max(closes)
            lo250 = min(closes[-250:]) if len(closes) >= 250 else min(closes)
            mom5 = (closes[-1]/closes[-6]-1)*100 if len(closes) >= 6 else 0
            mom20 = (closes[-1]/closes[-20]-1)*100
            mom60 = (closes[-1]/closes[-60]-1)*100
            max_dd60 = min((closes[i]/max(closes[max(0,i-60):i+1])-1)*100 for i in range(max(1,len(closes)-60), len(closes))) if len(closes) > 60 else 0
            # 长期亏损/趋势: 60日动量为负且收在MA60下方的天数占比(近60日)
            below60 = sum(1 for i in range(max(0,len(closes)-60), len(closes)) if closes[i] < sum(closes[max(0,i-60):i+1])/(min(60,i+1)))
            below_ratio = below60 / 60
            pe = (quotes or {}).get('pe') if quotes else None
            mc = (quotes or {}).get('market_cap') if quotes else None
            turn = (quotes or {}).get('turnover_pct') if quotes else None
            pos = (price - lo250)/(hi250 - lo250)*100 if hi250 > lo250 else 50
            rows.append({
                "code": code, "v31": round(v31,1), "v4": round(v4,1),
                "price": round(price,2), "pe": pe, "mc": mc, "turn": turn,
                "mom5": round(mom5,1), "mom20": round(mom20,1), "mom60": round(mom60,1),
                "maxdd60": round(max_dd60,1), "below_ma60": round(below_ratio,2),
                "pos250": round(pos,0), "res4": s4["resonance"],
            })
        except Exception as e:
            print(f"  ERR {code}: {e}")
    # 汇总
    out = {"run_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "version": "compare", "n": len(rows), "rows": rows}
    with open(SCRIPT_DIR / "compare_v31_v4.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 打印表
    print(f"{'代码':<7}{'v31':>5}{'v4':>5}{'共振':>4}{'价':>8}{'PE':>6}{'mom5':>6}{'mom20':>6}{'mom60':>7}{'md60':>6}{'<MA60':>6}{'pos':>5}")
    for r in sorted(rows, key=lambda x: -x["v31"]):
        print(f"{r['code']:<7}{r['v31']:>5}{r['v4']:>5}{r['res4']:>4}{r['price']:>8.1f}{str(r['pe'] or '-'):>6}{r['mom5']:>6.1f}{r['mom20']:>6.1f}{r['mom60']:>7.1f}{r['maxdd60']:>6.1f}{r['below_ma60']:>6.2f}{r['pos250']:>5.0f}")
    print(f"\n共 {len(rows)} 只")
if __name__ == "__main__":
    main()