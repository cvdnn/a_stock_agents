#!/usr/bin/env python3
"""5a-stock-rotation v4 — 完整五维评分接入回测后的 OOS 重跑基线
运行: python rerun_oos_v4.py
产出: v4_backtest_results.json (样本内+样本外+衰减率), 与 SKILL.md v4 表对照
"""
import sys, os, json, datetime, time
sys.path.insert(0, r"C:\Users\user\AppData\Local\AI-Platform\skills\stocks\5a-stock-rotation\scripts")
sys.path.insert(0, r"C:\Users\user\AppData\Local\AI-Platform\skills\stocks\a-stocks\scripts")

from multi_dim_model_v3 import RotationBacktest
from data_bridge import DataBridge

BT_STOCKS = ["600519", "000858", "600036", "300750", "002594", "600887",
             "601899", "002371", "002463", "600584", "603259", "601012"]
CONFIGS = [
    ("MA10", 1, "配置A+MA10(旋转模型基准)"),
    ("MA15", 1, "配置A+MA15(旋转模型最优)"),
    ("MA20", 1, "配置A+MA20(宽离场)"),
    ("MA15", 2, "配置A+MA15+2仓分散(组合化建议#3)"),
    ("MA15", 3, "配置A+MA15+3仓分散"),
]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    bridge = DataBridge()
    # 拉取 12 股K线
    stock_kl = {}
    for code in BT_STOCKS:
        try:
            kl = bridge.tencent_kline(code, 521)
            if kl and len(kl) >= 250:
                stock_kl[code] = kl
                print(f"  OK {code}: {len(kl)}K", flush=True)
            else:
                print(f"  SKIP {code}: 数据不足 {len(kl) if kl else 0}", flush=True)
        except Exception as e:
            print(f"  ERR {code}: {e}", flush=True)
    if len(stock_kl) < 6:
        print("FAIL: 候选股数据不足", flush=True); return

    # 上证K线 (读缓存)
    sh_path = os.path.join(SCRIPT_DIR, "sh000001_klines.json")
    with open(sh_path, "r", encoding="utf-8") as f:
        sh_raw = json.load(f)
    sh_kl = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in sh_raw]
    print(f"  sh000001: {len(sh_kl)}K (cached)", flush=True)

    n_total = min(len(sh_kl), min(len(kl) for kl in stock_kl.values()))
    n_split = int(n_total * 0.6)
    stock_kl_in = {c: kl[:n_split] for c, kl in stock_kl.items()}
    stock_kl_out = {c: kl[n_split:] for c, kl in stock_kl.items() if len(kl) > n_split + 20}
    sh_kl_in = sh_kl[:n_split]
    sh_kl_out = sh_kl[n_split:]
    print(f"  split: total={n_total} in={n_split} out={n_total-n_split}", flush=True)

    def _run(label, skl, shl):
        t0 = time.time()
        exit_line, n_pos, _ = label
        bt = RotationBacktest(exit_line=exit_line, num_positions=n_pos, initial_cash=1000000)
        r = bt.run(skl, shl)
        dt = time.time() - t0
        print(f"    {label[2]} => {r['total_return_pct']:+.1f}% dd={r['max_drawdown_pct']}% win={r['win_rate']}% n={r['n_trades']} sharpe={r['sharpe_ratio']} ({dt:.0f}s)", flush=True)
        return r

    # 样本内 (5 配置)
    bt_results = []
    print(f"\n[样本内] 前{n_split}日 (60%):", flush=True)
    for cfg in CONFIGS:
        r = _run(cfg, stock_kl_in, sh_kl_in)
        bt_results.append({"label": cfg, "result": r})

    # 样本外 (5 配置)
    oos_results = []
    print(f"\n[样本外] 后{n_total - n_split}日 (40% blind):", flush=True)
    if stock_kl_out and len(sh_kl_out) > 20:
        for cfg in CONFIGS:
            r = _run(cfg, stock_kl_out, sh_kl_out)
            oos_results.append({"label": cfg, "result": r})

    def _to_dict(r):
        return {"label": r["label"][2], "total_return": r["result"]["total_return_pct"],
                "annual_return": r["result"]["annual_return_pct"], "max_drawdown": r["result"]["max_drawdown_pct"],
                "win_rate": r["result"]["win_rate"], "profit_factor": r["result"]["profit_factor"],
                "median_pnl": r["result"]["median_pnl_pct"], "avg_hold": r["result"]["avg_hold_days"],
                "n_trades": r["result"]["n_trades"], "utilization": r["result"]["utilization_pct"],
                "direction_excess": r["result"]["direction_excess_pp"], "sharpe": r["result"]["sharpe_ratio"]}

    out = {
        "version": "v4", "run_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scoring": "完整五维 FiveDimScorer (口径与截面一致) + 逐日上证市场状态 _hist_market",
        "n_total_days": n_total, "n_in_sample": n_split, "n_out_sample": n_total - n_split,
        "in_sample": [_to_dict(r) for r in bt_results],
    }
    if oos_results:
        out["out_sample"] = [_to_dict(r) for r in oos_results]
        out["decay_rates"] = []
        for i in range(len(CONFIGS)):
            in_r = bt_results[i]["result"]["total_return_pct"]
            out_r = oos_results[i]["result"]["total_return_pct"] if i < len(oos_results) else 0
            out["decay_rates"].append({"label": CONFIGS[i][2], "in_return": in_r,
                                       "out_return": out_r, "decay_rate": round(out_r / in_r * 100, 1) if in_r else 0})
    with open(os.path.join(SCRIPT_DIR, "v4_backtest_results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[DONE] 已写 v4_backtest_results.json", flush=True)

if __name__ == "__main__":
    main()