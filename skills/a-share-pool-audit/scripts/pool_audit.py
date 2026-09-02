#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三大股池审计 — 统一腾讯快照+MA重算+关键位比对标记. 用法: python pool_audit.py [--data DIR]"""
import argparse, csv, json, os, re, urllib.request

def load_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8"))) if os.path.exists(path) else []

def sym(c):  # 6xx->sh 其余->sz; 池内已排除 688/30/8/4
    return ("sh" if c.startswith("6") else "sz") + c

def quote_batch(codes):
    url = "https://qt.gtimg.cn/q=" + ",".join(sym(c) for c in codes)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read().decode("gbk", errors="replace")
    out = {}
    for m in re.finditer(r'v_(\w+)="([^"]*)"', raw):
        p = m.group(2).split("~")
        if len(p) < 46: continue
        try: price, prev, pe = float(p[3]), float(p[4]), p[39].strip()
        except (ValueError, IndexError): continue
        out[m.group(1)[2:]] = {"name": p[1], "price": price,
                               "chg": (price-prev)/prev*100 if prev else 0.0, "pe": pe}
    return out

def ma_of(code, n):
    s = sym(code)
    u = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,60,qfq" % s
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read().decode("utf-8"))
    kl = d["data"][s]; kl = kl.get("qfqday") or kl.get("day")
    closes = [float(x[2]) for x in kl]
    return round(sum(closes[-n:])/n, 2) if len(closes) >= n else None

def ma_status(p, m5, m10, m20):
    if None in (m5, m10, m20): return "?"
    if p >= m5 >= m10 and p >= m20: return "多头"
    if p <= m5 and p <= m10 and p <= m20: return "空头"
    return "震荡"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    a = ap.parse_args()
    watch, selected, positions = (load_csv(os.path.join(a.data, f)) for f in ("watch_pool.csv", "selected_pool.csv", "positions.csv"))
    codes = sorted({r["code"] for rows in (watch, selected, positions) for r in rows if r.get("code")})
    if not codes: print("无股票数据"); return
    print("拉取 %d 只行情..." % len(codes))
    q, ma = quote_batch(codes), {c: (ma_of(c, 5), ma_of(c, 10), ma_of(c, 20)) for c in codes}

    print("\n===== 关注股池 (%d) =====" % len(watch))
    for r in watch:
        c = r["code"]; d = q.get(c) or {}; p = d.get("price")
        if p is None: print("%s %s: 无行情" % (c, r.get("name", "?"))); continue
        m5, m10, m20 = ma.get(c, (None, None, None))
        line = "%s %s 现价%7.2f (%+.2f%%) PE=%s MA20=%s %s" % (c, r.get("name", "?"), p, d.get("chg", 0), d.get("pe", "?"), m20, ma_status(p, m5, m10, m20))
        mm = re.findall(r"[\d.]+", r.get("entry_condition") or "")
        if mm and abs((p - float(mm[0])) / float(mm[0]) * 100) > 5:
            line += "  ⚠️参考位偏离%+.1f%%(可能过期)" % ((p - float(mm[0])) / float(mm[0]) * 100)
        print(line)

    print("\n===== 自选股池 (%d) =====" % len(selected))
    for r in selected:
        c = r["code"]; d = q.get(c) or {}; p = d.get("price")
        if p is None: print("%s %s: 无行情" % (c, r.get("name", "?"))); continue
        m5, m10, m20 = ma.get(c, (None, None, None))
        line = "%s %s 现价%7.2f (%+.2f%%) PE=%s %s" % (c, r.get("name", "?"), p, d.get("chg", 0), d.get("pe", "?"), ma_status(p, m5, m10, m20))
        try: sl = float(r["stop_loss"]) if r.get("stop_loss") else None
        except ValueError: sl = None
        try: tp = float(r["take_profit"]) if r.get("take_profit") else None
        except ValueError: tp = None
        if sl is not None:
            line += "  🔴已破止损(%.2f)" % sl if p <= sl else ("  ⚠️止损高于现价(失效)" if sl > p else "  止损%.2f(距%+.1f%%)" % (sl, (p - sl) / sl * 100))
        if tp is not None:
            line += "  ✅已达止盈(%.2f)" % tp if p >= tp else "  止盈%.2f(距%+.1f%%)" % (tp, (tp - p) / p * 100)
        print(line)

    print("\n===== 持仓池 (%d) =====" % len(positions))
    tc = tv = 0.0
    for r in positions:
        c = r["code"]; d = q.get(c) or {}; p = d.get("price")
        if p is None: print("%s %s: 无行情" % (c, r.get("name", "?"))); continue
        try: cost, qty = float(r["buy_price"]), int(r["qty"])
        except (ValueError, KeyError): continue
        cv, v = cost * qty, p * qty; tc += cv; tv += v
        m5, m10, m20 = ma.get(c, (None, None, None))
        line = "%s %s 成本%7.2f 现价%7.2f 浮盈亏%+.0f (%+.1f%%) %s" % (c, r.get("name", "?"), cost, p, v - cv, (p - cost) / cost * 100, ma_status(p, m5, m10, m20))
        try: sl = float(r["stop_loss"]) if r.get("stop_loss") else None
        except ValueError: sl = None
        try: tp = float(r["take_profit"]) if r.get("take_profit") else None
        except ValueError: tp = None
        if sl is not None: line += "  🔴已破止损" if p <= sl else "  距止损%+.1f%%" % ((p - sl) / sl * 100)
        if tp is not None: line += "  ✅已达止盈" if p >= tp else "  距止盈%+.1f%%" % ((tp - p) / p * 100)
        print(line)
    if tc > 0: print("组合: 成本%.0f 市值%.0f 浮盈亏%+.0f (%+.2f%%)" % (tc, tv, tv - tc, (tv - tc) / tc * 100))

if __name__ == "__main__":
    main()
