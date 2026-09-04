#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5a-stock-rotation — A股多维共振旋转选股引擎 (通用扫描执行器)
基于模板方法模式 (Template Method) 与声明式配置驱动架构设计。

用法:
  python screen.py                          # 运行默认主板池 (mainboard_24)
  python screen.py --pool h2_mainlines      # 运行2026下半年主线候选池
  python screen.py --pool h2_expand         # 运行低位主线补涨候选池
  python screen.py --stocks 600519,601899   # 临时指定股票列表
  python screen.py --list-pools             # 查看所有支持的预设股票池
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml

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

from core.models.multi_dim_model import StockSelectionModel
from core.config import OUTPUT_REPORTS_DIR


from core.strategy.pool_schema import is_blocked as _is_blocked


def load_stock_pools() -> Dict[str, Any]:
    """从统一声明式配置文件加载股票池定义"""
    cfg_paths = [
        PROJECT_ROOT / "config" / "stock_pools.yaml",
        SCRIPT_DIR.parent / "config" / "pools.yaml",
    ]
    for p in cfg_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"  [Warning] 读取股票池配置失败 {p}: {e}")
    return {}


class ScreenerPipeline:
    """选股扫描通用控制流水线 (模板方法模式)"""

    def __init__(
        self,
        pool_name: str = "mainboard_24",
        custom_stocks: Optional[List[str]] = None,
        max_price: float = 350.0,
        max_pe: float = 100.0,
        suffix: Optional[str] = None,
        export_dir: Optional[Path] = None,
    ):
        self.pool_name = pool_name
        self.custom_stocks = custom_stocks
        self.suffix = suffix
        self.export_dir = export_dir or OUTPUT_REPORTS_DIR
        self.model = StockSelectionModel(max_price=max_price, max_pe=max_pe)
        self.candidates = self._resolve_candidates()

    def _resolve_candidates(self) -> List[str]:
        if self.custom_stocks:
            return [c.strip() for c in self.custom_stocks if c.strip()]
        pools_cfg = load_stock_pools()
        pools_dict = pools_cfg.get("pools", {})
        if self.pool_name in pools_dict:
            raw_stocks = pools_dict[self.pool_name].get("stocks", [])
            return [s for s in raw_stocks if not _is_blocked(s)]
        print(f"  ⚠️ 未找到名为 '{self.pool_name}' 的股票池，回退至 mainboard_24")
        if "mainboard_24" in pools_dict:
            return pools_dict["mainboard_24"].get("stocks", [])
        return ["600519", "000858", "600036", "601318", "601899", "600276"]

    def run(self) -> Dict[str, Any]:
        print("=" * 110)
        print("  5a-stock-rotation — 五维共振旋转选股引擎 v5.0 (通用扫描流水线)")
        print(f"  标的池: {self.pool_name} ({len(self.candidates)} 只有效标的)")
        print(f"  运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 110)

        # 1. 评估大盘门控 (Market Gate)
        self.model.gate.assess()
        gate_status = "OPEN ✅" if self.model.gate.gate_open else "CLOSED ❌"
        print(f"\n  大盘门控: {gate_status} (上证{'>' if self.model.gate.gate_open else '<'}MA20)")
        print(f"  市场状态: {self.model.gate.state} (健康度={self.model.gate.health_score}/100)")
        print(
            f"  仓位上限: {self.model.gate.config['仓位上限']*100:.0f}% | "
            f"单标的: {self.model.gate.config['单标的']*100:.0f}% | "
            f"共振要求: {self.model.gate.config['共振']}维 | "
            f"技术门槛: {self.model.gate.config['技术门槛']}分"
        )

        # 2. 遍历候选股并执行打分
        results = []
        errors = []
        for code in self.candidates:
            try:
                r = self.model.evaluate(code)
                if "error" in r:
                    errors.append((code, r["error"]))
                    print(f"  ❌ {code}: {r['error']}")
                else:
                    results.append(r)
            except Exception as e:
                errors.append((code, str(e)))
                print(f"  ❌ {code}: {e}")

        # 3. 排序
        results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

        # 4. 打印报告表
        print(f"\n  {'排名':<4} {'代码':<8} {'CS':>6} {'评级':<4} {'基本面':<7} {'共振':<5} {'操作':<14} {'仓位':<6} {'现价':>9} {'止损%':>6} {'盈亏比':>5} {'卖出信号'}")
        print("  " + "-" * 110)
        for i, r in enumerate(results):
            sells = len(r.get("sell_signals", []))
            filter_tag = "PASS ✅" if r.get("passed_filter") else "BLOCK ❌"
            pos_str = str(r.get("position", "-"))
            print(
                f"  {i+1:<4} {r['code']:<8} {r['composite_score']:>6.1f} {r['rating']:<4} "
                f"{filter_tag:<7} {r['resonance_count']}/5  {r['action']:<14} {pos_str:<6} "
                f"{r.get('entry_price', 0):>9.2f} {r.get('stop_loss_pct', 0):>6.2f} "
                f"{r.get('risk_reward', 0):>5.2f} {sells}"
            )

        print(f"\n  成功评估 {len(results)} 只, 失败 {len(errors)} 只")
        if errors:
            print(f"  失败清单: {errors}")

        # 5. 产物接收器持久化 (Artifact Sink Routing)
        today = datetime.datetime.now().strftime("%Y%m%d")
        target_dir = self.export_dir / today
        target_dir.mkdir(parents=True, exist_ok=True)
        time_tag = datetime.datetime.now().strftime("%H%M%S")
        tag = self.suffix or f"{self.pool_name}_{time_tag}"
        out_path = target_dir / f"screen_{tag}.json"

        output_payload = {
            "metadata": {
                "engine_version": getattr(self.model, "__version__", "5.0.0"),
                "run_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pool_name": self.pool_name,
                "total_candidates": len(self.candidates),
                "success_count": len(results),
                "error_count": len(errors),
            },
            "market_gate": {
                "gate_open": self.model.gate.gate_open,
                "market_state": self.model.gate.state,
                "health_score": self.model.gate.health_score,
                "config": self.model.gate.config,
            },
            "results": results,
            "errors": errors,
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)
        print(f"\n  [产物已安全归档] {out_path}")

        return output_payload


def main():
    parser = argparse.ArgumentParser(description="5a-stock-rotation 通用选股扫描执行器")
    parser.add_argument("--pool", "-p", default="mainboard_24", help="指定预设股票池名称 (默认: mainboard_24)")
    parser.add_argument("--stocks", "-s", help="临时指定逗号分隔的A股代码列表 (覆盖预设池)")
    parser.add_argument("--suffix", help="输出文件后缀标识 (默认自动时间戳)")
    parser.add_argument("--list-pools", action="store_true", help="列出配置文件中已定义的所有股票池")
    args = parser.parse_args()

    if args.list_pools:
        cfg = load_stock_pools()
        pools = cfg.get("pools", {})
        print("\n已配置的股票池:")
        for k, v in pools.items():
            print(f"  - {k:<15} : {v.get('name')} ({len(v.get('stocks', []))}只) - {v.get('description')}")
        return

    custom_stocks = args.stocks.split(",") if args.stocks else None
    pipeline = ScreenerPipeline(
        pool_name=args.pool,
        custom_stocks=custom_stocks,
        suffix=args.suffix,
    )
    pipeline.run()


if __name__ == "__main__":
    main()
