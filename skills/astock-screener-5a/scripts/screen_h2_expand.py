#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5a-stock-rotation — 2026下半年主线扩展候选池 (第二轮: 低位主线+补涨方向)
第一轮结论: 门控关闭(上证<MA20), AI算力硬件主线普遍高位回撤被风险过滤拦截。
第二轮思路: 扫描尚未启动或刚企稳的主线标的 (资源/电力/传媒/军工/消费低位/金融)。
用法: python screen_h2_expand.py [输出后缀]
"""
import sys, os, json, datetime

SUFFIX = sys.argv[1] if len(sys.argv) > 1 else "20260903_h2_expand"

PROJECT_ROOT = r"C:\Users\cvdnn\coding\a_stock_agents"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPT_DIR)

from multi_dim_model_v3 import StockSelectionV3

candidates = [
    # ── 资源/有色 补涨 ──
    "601600",  # 中国铝业 铜铝
    "600362",  # 江西铜业 铜
    "600188",  # 兖矿能源 煤炭
    "600985",  # 淮北矿业 煤炭
    "601225",  # 陕西煤业 煤炭
    "600256",  # 广汇能源 油气
    # ── 石油石化/能源 ──
    "600028",  # 中国石化
    "601857",  # 中国石油
    # ── 电力/公用事业 (防御+AI能耗) ──
    "600900",  # 长江电力
    "600886",  # 国投电力
    "600023",  # 浙能电力
    "600025",  # 华能水电
    # ── 大金融 (低估值+牛市旗手预备) ──
    "601688",  # 华泰证券
    "600999",  # 招商证券
    "601628",  # 中国人寿
    "601601",  # 中国太保
    "601318",  # 中国平安
    "600036",  # 招商银行
    "601288",  # 农业银行
    "601398",  # 工商银行
    # ── 军工/航天 (低轨卫星+商业航天) ──
    "600760",  # 中航沈飞
    "000768",  # 中航西飞
    "600893",  # 航发动力
    # ── 消费/医药 低位修复 ──
    "600887",  # 伊利股份
    "000333",  # 美的集团
    "600085",  # 同仁堂 中药
    "000538",  # 云南白药
    "600196",  # 复星医药
    # ── 通信运营商 (红利+AI) ──
    "600941",  # 中国移动
    "601728",  # 中国电信
    "600050",  # 中国联通
    # ── 交运/基建 低位 ──
    "601668",  # 中国建筑
    "601800",  # 中国交建
    # ── 化工/材料 (涨价链) ──
    "600309",  # 万华化学
    "002601",  # 龙佰集团 钛白粉
    # ── 出海制造 ──
    "601717",  # 郑煤机
    "600031",  # 三一重工
    # ── 农业 (8月强势) ──
    "600598",  # 北大荒
]

print("=" * 110)
print("  5a-stock-rotation — 五维共振旋转选股引擎 v5.0 (第二轮扩展主线候选池)")
print(f"  运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 110)

model = StockSelectionV3()
model.gate.assess()

print(f"\n  大盘门控: {'OPEN' if model.gate.gate_open else 'CLOSED'} (上证{'>' if model.gate.gate_open else '<'}MA20)")
print(f"  市场状态: {model.gate.state} (健康度={model.gate.health_score}/100)")
print(f"  仓位上限: {model.gate.config['仓位上限']*100:.0f}% | 单标的: {model.gate.config['单标的']*100:.0f}% | 共振要求: {model.gate.config['共振']}维")
print(f"  候选池: {len(candidates)} 只")

results = []
errors = []
for code in candidates:
    try:
        r = model.evaluate(code)
        if "error" in r:
            errors.append((code, r["error"]))
            print(f"  X {code}: {r['error']}")
        else:
            results.append(r)
            print(f"  . {code}: CS={r['composite_score']:.1f} {r['rating']} {r['action']}")
    except Exception as e:
        errors.append((code, str(e)))
        print(f"  X {code}: {e}")

results.sort(key=lambda x: x["composite_score"], reverse=True)

print(f"\n  {'排名':<4} {'代码':<8} {'CS':>6} {'评级':<4} {'基本面':<9} {'共振':<5} {'操作':<14} {'仓位':<6} {'现价':>9} {'止损%':>7} {'盈亏比':>6} {'卖出信号'}")
print("  " + "-" * 112)
for i, r in enumerate(results):
    sells = len(r["sell_signals"])
    filter_tag = "PASS" if r.get("passed_filter") else "BLOCK"
    print(f"  {i+1:<4} {r['code']:<8} {r['composite_score']:>6.1f} {r['rating']:<4} {filter_tag:<9} {r['resonance_count']}/5  {r['action']:<14} {r['position']:<6} {r['entry_price']:>9.2f} {r['stop_loss_pct']:>7.2f} {r['risk_reward']:>6.2f} {sells}")

print(f"\n  成功评估 {len(results)} 只, 失败 {len(errors)} 只")
if errors:
    print(f"  失败清单: {errors}")

out = {
    "run_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "version": "v5.0-h2-expand",
    "market_state": model.gate.state,
    "market_score": model.gate.health_score,
    "gate_open": model.gate.gate_open,
    "results": results,
    "errors": errors,
}
out_path = os.path.join(SCRIPT_DIR, "v3_screen_" + SUFFIX + ".json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n  结果已保存: {out_path}")
