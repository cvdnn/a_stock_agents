#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地K线「技术评分 + MA20趋势回测」一体工具 —— 规避 backtest_engine 的 urllib SSL 超时，
以及 execute_code 沙箱无外网的问题。数据先用 terminal curl 落盘 (快且稳) 再交给本脚本计算。

用法:
  1) 落盘K线 (terminal, 非 execute_code; execute_code 沙箱无外网 Errno 101):
     mkdir -p /tmp/astk/kl
     for pair in "603259:sh" "601899:sh" "002532:sz"; do
       code="${pair%%:*}"; pfx="${pair##*:}"
       timeout 15 curl -s "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=${pfx}${code},day,,,120,qfq" \
         -H "User-Agent: Mozilla/5.0" -o "/tmp/astk/kl/${code}.json"
     done
  2) 评分 + 回测:
     python3 local_ma20_backtest.py 603259 601899 002532 002371 002463
  (ASTK_KL_DIR 环境变量可改K线目录, 默认 /tmp/astk/kl)

输出: 每只一行 —— 收盘/距MA20/距MA10/MACD/KDJ_J/RSI/组合评分 + 买持/趋势策略/年化/最大回撤/交易/胜率/盈亏比。
回测: close>MA20 持有多头、close<MA20 空仓的纯趋势过滤器。结论仅作策略有效性参考, 非买卖指令。
"""
import json, sys, os

KLDIR = os.environ.get("ASTK_KL_DIR", "/tmp/astk/kl")


def load(code):
    path = os.path.join(KLDIR, f"{code}.json")
    if not os.path.exists(path):
        sys.stderr.write(f"[!] 缺K线文件: {path}\n")
        return None
    d = json.load(open(path))
    k = list(d["data"].values())[0]
    return k.get("qfqday") or k.get("day")  # [[date,open,close,high,low,vol],...]


def ma(vals, n):
    return [None if i < n - 1 else sum(vals[i - n + 1:i + 1]) / n for i in range(len(vals))]


def ema(vals, n):
    k = 2 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def tech(kl):
    closes = [float(x[2]) for x in kl]
    last = closes[-1]
    m5, m10, m20, m60 = ma(closes, 5), ma(closes, 10), ma(closes, 20), ma(closes, 60)
    e12, e26 = ema(closes, 12), ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    bar = 2 * (dif[-1] - dea[-1])
    # RSI14
    g = sum(max(closes[i] - closes[i - 1], 0) for i in range(-14, 0))
    l = sum(max(closes[i - 1] - closes[i], 0) for i in range(-14, 0))
    rsi = 100 if l == 0 else round(100 - 100 / (1 + g / l), 1)
    return dict(last=last, ma5=m5[-1], ma10=m10[-1], ma20=m20[-1], ma60=m60[-1],
                dif=dif[-1], dea=dea[-1], bar=bar, rsi=rsi,
                d20=(last - m20[-1]) / m20[-1] * 100, d10=(last - m10[-1]) / m10[-1] * 100)


def combo_score(t):
    """简化100分制: 均线25 + MACD40 + 量价距MA20 15"""
    ms = 25 if (t["ma5"] > t["ma10"] and t["last"] > t["ma20"]) else (
        15 if t["last"] > t["ma20"] else (10 if t["last"] > t["ma60"] and t["last"] > t["ma10"] else 5))
    if t["dif"] > 0 and t["dif"] > t["dea"] and t["bar"] > 0:
        mac = 40
    elif t["dif"] > 0:
        mac = 20
    elif t["dif"] > t["dea"] and t["bar"] > 0:
        mac = 10
    else:
        mac = 0
    vs = 15 if (t["last"] > t["ma20"] and abs(t["d20"]) < 3) else (
        10 if t["last"] > t["ma20"] else (8 if abs(t["d20"]) < 5 else 5))
    total = ms + mac + vs
    return total, 'A' if total >= 80 else ('B' if total >= 65 else ('C' if total >= 50 else 'D'))


def backtest(closes):
    m20 = ma(closes, 20)
    bh = (closes[-1] / closes[0] - 1) * 100
    ann = ((closes[-1] / closes[0]) ** (252 / len(closes)) - 1) * 100
    pos = 0; equity = 1.0; peak = 1.0; maxdd = 0; trades = []; entry = 0
    for i in range(20, len(closes)):
        sig = closes[i] > m20[i]
        if sig and pos == 0:
            pos, entry = 1, closes[i]
        elif not sig and pos == 1:
            r = closes[i] / entry - 1; trades.append(r); equity *= (1 + r); pos = 0
        elif pos == 1:
            equity *= (closes[i] / closes[i - 1])
        cur_eq = equity * (closes[i] / entry) if pos else equity
        peak = max(peak, cur_eq); maxdd = max(maxdd, (peak - cur_eq) / peak * 100)
    if pos:
        trades.append(closes[-1] / entry - 1)
        strat = (equity * (closes[-1] / entry) - 1) * 100
    else:
        strat = (equity - 1) * 100
    wins = [x for x in trades if x > 0]; loss = [x for x in trades if x <= 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    pf = (sum(wins) / abs(sum(loss))) if loss and sum(loss) != 0 else float('inf')
    return dict(bh=round(bh, 1), strat=round(strat, 1), ann=round(ann, 1), maxdd=round(maxdd, 1),
                trades=len(trades), wr=round(wr), pf=round(pf, 2) if pf != float('inf') else 'inf')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    print(f"{'代码':<7}{'收盘':>8}{'距MA20':>8}{'距MA10':>8}{'MACD':>8}{'RSI':>6}  {'评分':>5}  {'买持':>7}{'趋势':>8}{'年化':>7}{'回撤':>8}{'交易':>5}{'胜率':>5}{'盈亏比':>7}")
    for code in sys.argv[1:]:
        kl = load(code)
        if not kl:
            continue
        closes = [float(x[2]) for x in kl]
        t = tech(kl)
        total, rating = combo_score(t)
        b = backtest(closes)
        print(f"{code:<7}{t['last']:>8.2f}{t['d20']:>+7.1f}%{t['d10']:>+7.1f}%{t['bar']:>+8.2f}{t['rsi']:>6.1f}  {total}/{rating}  "
              f"{b['bh']:>6.1f}%{b['strat']:>7.1f}%{b['ann']:>6.1f}%{b['maxdd']:>7.1f}%{b['trades']:>5}{b['wr']:>4.0f}%{b['pf']:>7}")
