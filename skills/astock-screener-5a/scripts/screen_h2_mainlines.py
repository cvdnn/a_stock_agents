#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5a-stock-rotation — 2026下半年主线候选池截面评估
主线依据(机构共识): AI算力硬件/光通信 / 有色资源涨价 / 创新药CXO /
电力设备与能源 / 机器人高端制造 / 券商(牛市旗手+盈利复苏)
用法: python screen_h2_mainlines.py [输出后缀]
"""
import sys, os, json, datetime

SUFFIX = sys.argv[1] if len(sys.argv) > 1 else "20260903_h2"

# 项目根目录 (保证 core.* 可导入) + 本脚本目录
PROJECT_ROOT = r"C:\Users\cvdnn\coding\a_stock_agents"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPT_DIR)

from multi_dim_model_v3 import StockSelectionV3

# 候选池: 覆盖下半年机构共识主线, 全部为沪深主板可交易标的
candidates = [
    # ── AI算力硬件 (核心进攻主线) ──
    "601138",  # 工业富联 AI服务器/算力
    "000977",  # 浪潮信息 AI服务器
    "002463",  # 沪电股份 PCB龙头
    "002475",  # 立讯精密 AI硬件连接器
    "600584",  # 长电科技 先进封装
    "002371",  # 北方华创 半导体设备
    "603986",  # 兆易创新 存储芯片
    # ── 光通信/光纤光缆 (海外供应链基础设施) ──
    "002281",  # 光迅科技 光模块
    "600487",  # 亨通光电 光纤光缆+海缆
    "600522",  # 中天科技 光纤光缆
    # ── 有色资源 (涨价周期+降息受益) ──
    "601899",  # 紫金矿业 铜金
    "603993",  # 洛阳钼业 铜钴
    "600111",  # 北方稀土 稀土
    "600547",  # 山东黄金 黄金
    "000878",  # 云南铜业 铜
    # ── 创新药/CXO (盈利复苏接力) ──
    "603259",  # 药明康德 CXO
    "600276",  # 恒瑞医药 创新药
    # ── 电力设备/能源 (AI能耗瓶颈+防御) ──
    "600406",  # 国电南瑞 电网设备
    "600089",  # 特变电工 电网/特高压
    "601088",  # 中国神华 能源红利(白名单)
    # ── 机器人/高端制造 ──
    "601689",  # 拓普集团 机器人零部件
    "002050",  # 三花智控 热管理/执行器
    # ── 券商 (牛市旗手+盈利复苏) ──
    "600030",  # 中信证券
]

print("=" * 110)
print("  5a-stock-rotation — 五维共振旋转选股引擎 v5.0 (2026下半年主线截面评估)")
print(f"  运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 110)

model = StockSelectionV3()
model.gate.assess()

print(f"\n  大盘门控: {'OPEN' if model.gate.gate_open else 'CLOSED'} (上证{'>' if model.gate.gate_open else '<'}MA20)")
print(f"  市场状态: {model.gate.state} (健康度={model.gate.health_score}/100)")
print(f"  仓位上限: {model.gate.config['仓位上限']*100:.0f}% | 单标的: {model.gate.config['单标的']*100:.0f}% | 共振要求: {model.gate.config['共振']}维")
print(f"  候选池: {len(candidates)} 只 (沪深主板, 覆盖6大主线)")

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
    "version": "v5.0-h2-mainlines",
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
