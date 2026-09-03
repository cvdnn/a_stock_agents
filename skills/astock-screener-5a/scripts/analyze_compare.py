#!/usr/bin/env python3
"""v3.1 vs v4 短线选股对比 — 统计分析
读取 compare_v31_v4.json, 做:
 1) 两组高分股(前8/v31>=60 与 v4>=60) 重合度
 2) 高分股风险画像均值 (PE/股价/mom60/maxdd60/below_ma60/pos250) vs 低分组
 3) 短线胜率: 拉未来5日收益, 看每种方法选中的top股胜率
"""
import sys, json, statistics
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core" / "data") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core" / "data"))
if str(PROJECT_ROOT / "core" / "models") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core" / "models"))
if str(PROJECT_ROOT / "core" / "indicators") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core" / "indicators"))

from data_bridge import DataBridge

DATA = SCRIPT_DIR / "compare_v31_v4.json"
if not DATA.exists():
    print(f"数据文件不存在: {DATA}")
    print("请先运行: python skills/astock-screener-5a/scripts/compare_v31_v4.py 生成对比数据")
    sys.exit(0)

rows = json.load(open(DATA, encoding="utf-8"))["rows"]



def agg(rs):
    if not rs: return {}
    def m(k, f=None):
        vals = [r[k] for r in rs if r.get(k) is not None]
        if not vals: return None
        return round(statistics.mean(vals),2) if f is None else round(f(vals),2)
    return {
        "n": len(rs), "PE均": m("pe"), "股价中位": m("price", statistics.median),
        "mom60": m("mom60"), "md60": m("maxdd60"), "<MA60占比": m("below_ma60"),
        "pos250": m("pos250"), "v4均": m("v4"), "v31均": m("v31"),
        "PE≥30数": sum(1 for r in rs if (r.get("pe") or 999) >= 30),
        "股价≥100数": sum(1 for r in rs if (r.get("price") or 0) >= 100),
        "mom60<0数": sum(1 for r in rs if (r.get("mom60") or 0) < 0),
        "md60<-25数": sum(1 for r in rs if (r.get("maxdd60") or 0) < -25),
    }

print("=== 分组定义 ===")
all_r = rows
top31 = [r for r in all_r if r["v31"] >= 60]
top4 = [r for r in all_r if r["v4"] >= 60]
bot31 = [r for r in all_r if r["v31"] < 60]
mid4 = [r for r in all_r if 45 <= r["v4"] < 60]

codes31 = {r["code"] for r in top31}
codes4 = {r["code"] for r in top4}
print(f"v31≥60: {len(top31)}只 {sorted(codes31)}")
print(f"v4≥60: {len(top4)}只 {sorted(codes4)}")
print(f"重合: {len(codes31 & codes4)}只  {sorted(codes31 & codes4)}")
print(f"仅v31: {sorted(codes31 - codes4)}")
print(f"仅v4: {sorted(codes4 - codes31)}")

print("\n=== 风险画像对比 ===")
for name, rs in [("全24只", all_r), ("v31≥60", top31), ("v4≥60", top4), ("v31<60", bot31), ("v4 45-60", mid4)]:
    a = agg(rs)
    print(f"\n[{name}] n={a['n']}")
    for k in ["PE均","股价中位","mom60","md60","<MA60占比","pos250","v4均","v31均","PE≥30数","股价≥100数","mom60<0数","md60<-25数"]:
        print(f"   {k}: {a.get(k)}")

print("\n=== 关键风险个股被谁过滤 ===")
risky = [r for r in all_r if (r.get("pe") or 0) >= 30 or (r.get("price") or 0) >= 500 or (r.get("maxdd60") or 0) < -30]
for r in sorted(risky, key=lambda x: -x["v31"]):
    print(f"  {r['code']:<7} v31={r['v31']:>5.1f} v4={r['v4']:>5.1f} 价={r['price']:>7.1f} PE={str(r['pe'] or '-'):>6} md60={r['maxdd60']:>5.1f}% {'⚠️高风险' if (r.get('pe') or 0)>=30 or (r.get('price') or 0)>=500 else '大幅调整'}")