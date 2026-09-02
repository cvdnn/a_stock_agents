#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5a-stock-rotation — 扩展候选池截面评估 (五维共振旋转引擎)
对 ~24 只主板候选股跑 StockSelectionV3.evaluate, 输出完整评分+评级+风控参数
用法: python screen_20260813.py [输出后缀]
"""
import sys, os, json, datetime

SUFFIX = sys.argv[1] if len(sys.argv) > 1 else "20260813"

sys.path.insert(0, r"C:\Users\user\AppData\Local\AI-Platform\skills\stocks\5a-stock-rotation\scripts")
sys.path.insert(0, r"C:\Users\user\AppData\Local\AI-Platform\skills\stocks\a-stocks\scripts")

from multi_dim_model_v3 import StockSelectionV3

# 账户交易限制: 排除 688/689(科创) 30(创业) 8/4(北交所/老三板)
def _is_blocked(code: str) -> bool:
    return code.startswith(("688", "689", "30", "8", "4"))

# 候选池: 主板大盘蓝筹 + 各行业龙头 (沪深主板, 可交易)
candidates = [
    "600519",  # 贵州茅台 白酒
    "000858",  # 五粮液 白酒
    "600036",  # 招商银行 银行
    "601318",  # 中国平安 保险
    "600406",  # 国电南瑞 电网设备
    "002230",  # 科大讯飞 AI
    "002475",  # 立讯精密 消费电子
    "601899",  # 紫金矿业 有色
    "600887",  # 伊利股份 乳业
    "601012",  # 隆基绿能 光伏
    "600584",  # 长电科技 半导体封测
    "002371",  # 北方华创 半导体设备
    "603259",  # 药明康德 医药
    "002594",  # 比亚迪 新能源车
    "600030",  # 中信证券 券商
    "600900",  # 长江电力 电力
    "000333",  # 美的集团 家电
    "600276",  # 恒瑞医药 医药
    "601138",  # 工业富联 AI算力
    "600941",  # 中国移动 通信
    "600309",  # 万华化学 化工
    "601668",  # 中国建筑 基建
    "600028",  # 中国石化 石油
    "601088",  # 中国神华 煤炭
]

print("=" * 110)
print("  5a-stock-rotation — 五维共振旋转选股引擎 v5.0 (截面评估 + 五大风险过滤)")
print(f"  运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 110)

model = StockSelectionV3()
model.gate.assess()

print(f"\n  大盘门控: {'OPEN ✅' if model.gate.gate_open else 'CLOSED ❌'} (上证{'>' if model.gate.gate_open else '<'}MA20)")
print(f"  市场状态: {model.gate.state} (健康度={model.gate.health_score}/100)")
print(f"  仓位上限: {model.gate.config['仓位上限']*100:.0f}% | 单标的: {model.gate.config['单标的']*100:.0f}% | 共振要求: {model.gate.config['共振']}维 | 技术门槛: {model.gate.config['技术门槛']}分")
print(f"  候选池: {len(candidates)} 只 (已过滤 688/30/8 板块)")

results = []
errors = []
for code in candidates:
    try:
        r = model.evaluate(code)
        if "error" in r:
            errors.append((code, r["error"]))
            print(f"  ❌ {code}: {r['error']}")
        else:
            results.append(r)
    except Exception as e:
        errors.append((code, str(e)))
        print(f"  ❌ {code}: {e}")

results.sort(key=lambda x: x["composite_score"], reverse=True)

print(f"\n  {'排名':<4} {'代码':<8} {'CS':>6} {'评级':<4} {'基本面':<7} {'共振':<5} {'操作':<14} {'仓位':<6} {'现价':>9} {'止损%':>6} {'盈亏比':>5} {'卖出信号'}")
print("  " + "-" * 110)
for i, r in enumerate(results):
    sells = len(r["sell_signals"])
    filter_tag = "PASS ✅" if r.get("passed_filter") else "BLOCK ❌"
    print(f"  {i+1:<4} {r['code']:<8} {r['composite_score']:>6.1f} {r['rating']:<4} {filter_tag:<7} {r['resonance_count']}/5  {r['action']:<14} {r['position']:<6} {r['entry_price']:>9.2f} {r['stop_loss_pct']:>6.2f} {r['risk_reward']:>5.2f} {sells}")

print(f"\n  成功评估 {len(results)} 只, 失败 {len(errors)} 只")
if errors:
    print(f"  失败清单: {errors}")

# 输出完整 JSON 供后续分析
out = {
    "run_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "version": "v5.0",
    "market_state": model.gate.state,
    "market_score": model.gate.health_score,
    "gate_open": model.gate.gate_open,
    "results": results,
}
with open(os.path.join(os.path.dirname(__file__), "v3_screen_" + SUFFIX + ".json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n  结果已保存: v3_screen_{SUFFIX}.json")

