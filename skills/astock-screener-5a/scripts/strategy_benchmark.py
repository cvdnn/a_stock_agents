#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5a-stock-rotation — 策略基准与样本外(OOS)矩阵回测套件 (Strategy Benchmark Suite)
基于基准矩阵范式 (Benchmark Matrix Pattern) 设计，替代一次性硬编码对比脚本。

用法:
  python strategy_benchmark.py                   # 运行标准5配置样本内外回测
  python strategy_benchmark.py --quick           # 快速验证模式 (前2配置)
  python strategy_benchmark.py --split 0.7       # 自定义样本内/样本外切分比例
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

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

from core.models.multi_dim_model import RotationBacktest
from core.data.data_bridge import DataBridge
from core.config import OUTPUT_BACKTEST_DIR

# 标准回测基准股票池 (代表主板与双创各赛道代表股)
DEFAULT_BT_STOCKS = [
    "600519", "000858", "600036", "300750", "002594", "600887",
    "601899", "002371", "002463", "600584", "603259", "601012"
]

DEFAULT_CONFIGS = [
    ("MA10", 1, "配置A+MA10 (旋转模型基准)"),
    ("MA15", 1, "配置A+MA15 (旋转模型最优)"),
    ("MA20", 1, "配置A+MA20 (宽离场线)"),
    ("MA15", 2, "配置A+MA15+2仓分散 (稳健组合)"),
    ("MA15", 3, "配置A+MA15+3仓分散 (高容量组合)"),
]


class StrategyBenchmark:
    """策略基准与样本外回测执行器"""

    def __init__(
        self,
        stocks: List[str] = None,
        split_ratio: float = 0.6,
        configs: List[tuple] = None,
    ):
        self.stocks = stocks or DEFAULT_BT_STOCKS
        self.split_ratio = split_ratio
        self.configs = configs or DEFAULT_CONFIGS
        self.bridge = DataBridge()

    def run(self) -> Dict[str, Any]:
        print("=" * 100)
        print("  5a-stock-rotation — 策略基准矩阵与样本外(OOS)验证")
        print(f"  回测标的池: {len(self.stocks)} 只 | 样本切分: {self.split_ratio*100:.0f}% 样本内 / {(1-self.split_ratio)*100:.0f}% 样本外")
        print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 100)

        # 1. 尝试从本地种子获取上证指数，否则降级
        sh_path = SCRIPT_DIR / "sh000001_klines.json"
        if not sh_path.exists():
            print(f"  ❌ 缺失基准K线数据: {sh_path}")
            return {}

        with open(sh_path, "r", encoding="utf-8") as f:
            sh_raw = json.load(f)
        sh_kl = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in sh_raw]
        print(f"  基准数据: sh000001 ({len(sh_kl)} 根K线缓存已载入)")

        # 2. 拉取回测个股K线
        stock_kl = {}
        for code in self.stocks:
            try:
                kl = self.bridge.tencent_kline(code, 521)
                if kl and len(kl) >= 200:
                    stock_kl[code] = kl
                else:
                    print(f"  ⚠️ {code}: 数据不足 ({len(kl) if kl else 0} 根)")
            except Exception as e:
                print(f"  ❌ {code}: 获取失败 {e}")

        if len(stock_kl) < 3:
            print("  ❌ 候选股有效数据不足，回测终止")
            return {}

        n_total = min(len(sh_kl), min(len(kl) for kl in stock_kl.values()))
        n_split = int(n_total * self.split_ratio)
        stock_kl_in = {c: kl[:n_split] for c, kl in stock_kl.items()}
        stock_kl_out = {c: kl[n_split:] for c, kl in stock_kl.items() if len(kl) > n_split + 20}
        sh_kl_in = sh_kl[:n_split]
        sh_kl_out = sh_kl[n_split:]

        print(f"  切分点: 总计 {n_total} 日 | 样本内前 {n_split} 日 | 样本外后 {n_total - n_split} 日")

        def _exec_backtest(exit_line, n_pos, label, skl, shl):
            t0 = time.time()
            bt = RotationBacktest(exit_line=exit_line, num_positions=n_pos, initial_cash=1000000)
            res = bt.run(skl, shl)
            dt = time.time() - t0
            print(
                f"    {label:<32} => 收益: {res['total_return_pct']:>6.1f}% | "
                f"回撤: {res['max_drawdown_pct']:>5.1f}% | 胜率: {res['win_rate']:>5.1f}% | "
                f"夏普: {res['sharpe_ratio']:>4.2f} ({dt:.1f}s)"
            )
            return res

        # 3. 运行样本内回测
        print(f"\n[1. 样本内回测阶段 (前 {n_split} 交易日)]:")
        bt_results = []
        for exit_line, n_pos, label in self.configs:
            r = _exec_backtest(exit_line, n_pos, label, stock_kl_in, sh_kl_in)
            bt_results.append({"label": label, "result": r})

        # 4. 运行样本外盲测阶段
        print(f"\n[2. 样本外盲测阶段 (后 {n_total - n_split} 交易日)]:")
        oos_results = []
        if stock_kl_out and len(sh_kl_out) > 20:
            for exit_line, n_pos, label in self.configs:
                r = _exec_backtest(exit_line, n_pos, label, stock_kl_out, sh_kl_out)
                oos_results.append({"label": label, "result": r})

        # 5. 衰减率核算
        decay_rates = []
        if oos_results:
            print("\n[3. 稳健性衰减率核算 (样本外收益 / 样本内收益)]:")
            print(f"  {'策略配置':<35} {'样本内收益':>10} {'样本外收益':>10} {'衰减保留率':>10}")
            print("  " + "-" * 72)
            for i in range(len(self.configs)):
                in_r = bt_results[i]["result"]["total_return_pct"]
                out_r = oos_results[i]["result"]["total_return_pct"] if i < len(oos_results) else 0
                decay = round(out_r / in_r * 100, 1) if in_r else 0
                decay_rates.append({
                    "label": self.configs[i][2],
                    "in_return": in_r,
                    "out_return": out_r,
                    "decay_rate": decay,
                })
                print(f"  {self.configs[i][2]:<35} {in_r:>9.1f}% {out_r:>9.1f}% {decay:>9.1f}%")

        # 6. 持久化至统一产物输出目录
        def _to_summary(item):
            r = item["result"]
            return {
                "label": item["label"],
                "total_return": r["total_return_pct"],
                "annual_return": r["annual_return_pct"],
                "max_drawdown": r["max_drawdown_pct"],
                "win_rate": r["win_rate"],
                "profit_factor": r["profit_factor"],
                "sharpe": r["sharpe_ratio"],
                "n_trades": r["n_trades"],
                "direction_excess": r["direction_excess_pp"],
            }

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        OUTPUT_BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
        out_file = OUTPUT_BACKTEST_DIR / f"benchmark_matrix_{timestamp}.json"

        payload = {
            "metadata": {
                "version": "5.0.0",
                "run_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "n_total_days": n_total,
                "n_in_sample": n_split,
                "n_out_sample": n_total - n_split,
            },
            "in_sample": [_to_summary(x) for x in bt_results],
            "out_sample": [_to_summary(x) for x in oos_results] if oos_results else [],
            "decay_rates": decay_rates,
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n  [基准回测产物已落盘] {out_file}")

        return payload


def main():
    parser = argparse.ArgumentParser(description="策略基准与样本外回测矩阵")
    parser.add_argument("--split", type=float, default=0.6, help="样本内切分比例 (默认 0.6)")
    parser.add_argument("--quick", action="store_true", help="快速测试模式 (仅跑前2种配置)")
    args = parser.parse_args()

    configs = DEFAULT_CONFIGS[:2] if args.quick else DEFAULT_CONFIGS
    bench = StrategyBenchmark(split_ratio=args.split, configs=configs)
    bench.run()


if __name__ == "__main__":
    main()
