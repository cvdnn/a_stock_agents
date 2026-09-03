#!/usr/bin/env python3
"""
ta_orchestrator.py — 股池事件触发 TA 分析调度器（P4 优化：事件驱动）

整合优化点：
  - 每日收盘后对自选股池批量跑 TA 分析
  - 关注股升级时自动触发 TA 分析
  - 统一调度 cron 监控更新

用法:
  # 每日定时分析自选股池
  python3 ta_orchestrator.py --mode daily-batch --pool selected

  # 单只重新分析（关注股升级或手动触发）
  python3 ta_orchestrator.py --mode reanalyze --ticker 600760

  # 检查股池状态并同步
  python3 ta_orchestrator.py --mode check-pool

  # 部署到 cron
  AI-Platform cron create --name "TA每日收盘分析" \
    --script /path/to/ta_orchestrator.py \
    --schedule "0 16 * * 1-5" \
    --deliver all
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 路径与环境自适应 ──────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core"))

from core.config import OUTPUT_POOLS_DIR

TA_ANALYZE = SCRIPT_DIR / "ta_analyze.py"
POOLS_BASE = OUTPUT_POOLS_DIR

_VENV_CANDIDATES = [
    Path(sys.executable),
    Path("python3"),
]
VENV_PY = next((p for p in _VENV_CANDIDATES if p.exists()), Path(sys.executable))


def _read_pool(name: str) -> List[Dict]:
    """读取股池 CSV。"""
    path = POOLS_BASE / f"{name}_pool.csv"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))



def _run_ta_batch(tickers: List[str], args) -> List[Dict]:
    """批量运行 TA 分析。"""
    results = []
    for t in tickers:
        print(f"  TA分析 {t}...", file=sys.stderr)
        cmd = [
            str(VENV_PY), str(TA_ANALYZE),
            t, "--phase", "2", "--brief", "--json", "--no-sync-pool",
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            out = json.loads(r.stdout)
            results.append({"ticker": t, "success": True, "result": out})
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            results.append({"ticker": t, "success": False, "error": str(e)})
        print(f"    {t} 完成", file=sys.stderr)
    return results


def _get_stale_tickers(pool_rows: List[Dict], max_age_days: int = 7) -> List[str]:
    """获取需要更新的标的（超过 N 天未分析）。"""
    stale = []
    today = datetime.now().strftime("%Y-%m-%d")
    for r in pool_rows:
        code = r["code"]
        analysis_date = r.get("ta_analysis_date", "")
        if not analysis_date or analysis_date < today:
            stale.append(code)
    return stale


# ═══════════════════════════════════════════════════════════════════════════════
# Modes
# ═══════════════════════════════════════════════════════════════════════════════


def mode_daily_batch(args):
    """每日收盘后批量分析自选股池。"""
    pool = args.pool or "selected"
    
    # 前置检查：确保必要依赖可用
    if not TA_ANALYZE.exists():
        print(f"❌ ta_analyze.py 未找到: {TA_ANALYZE}")
        return {"action": "daily_batch", "error": "ta_analyze.py not found"}

    # 检查 .env
    env_candidates = [
        PROJECT_ROOT / ".env",
        Path.home() / ".AI-Platform" / ".env",
        Path.home() / "TradingAgents" / ".env",
        Path.home() / "TradingAgents-astock" / ".env",
    ]
    env_found = any(p.exists() for p in env_candidates)
    if not env_found:
        print("⚠️ 未检测到 LLM API Key (.env)。Phase 2 分析将失败。")
        print("   继续运行 Phase 1 静态评分...")

    rows = _read_pool(pool)
    if not rows:
        print(f"股池 '{pool}' 为空，跳过批量分析")
        return {"action": "daily_batch", "pool": pool, "analyzed": 0}

    tickers = _get_stale_tickers(rows, max_age_days=args.max_age)
    if not tickers:
        print(f"股池 '{pool}' 所有标的已分析，无需更新")
        return {"action": "daily_batch", "pool": pool, "analyzed": 0}

    print(f"📊 每日批量分析: {pool}股池 ({len(tickers)} 只需更新)")
    results = _run_ta_batch(tickers, args)

    # 输出摘要
    success = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    print(f"\n✅ 成功: {len(success)} | ❌ 失败: {len(failed)}")
    if failed:
        for f in failed:
            print(f"  - {f['ticker']}: {f.get('error', '?')}")

    return {"action": "daily_batch", "pool": pool, "success": len(success), "failed": len(failed)}


def mode_reanalyze(args):
    """单只重新分析（关注股升级或手动触发）。"""
    ticker = args.ticker
    if not ticker:
        print("❌ 需要 --ticker 参数")
        return {"action": "reanalyze", "error": "no ticker"}

    print(f"🔄 重新分析 {ticker}...")
    results = _run_ta_batch([ticker], args)
    r = results[0]

    if r["success"]:
        print(f"\n✅ {ticker} 分析完成")
    else:
        print(f"\n❌ {ticker} 分析失败: {r.get('error', '?')}")

    return {"action": "reanalyze", "ticker": ticker, "success": r["success"]}


def mode_check_pool(args):
    """检查股池状态并生成分析建议。"""
    selected = _read_pool("selected")
    watch = _read_pool("watch")
    today = datetime.now().strftime("%Y-%m-%d")

    stale_selected = _get_stale_tickers(selected, max_age_days=args.max_age)
    stale_watch = _get_stale_tickers(watch, max_age_days=args.max_age)

    print("═══ 股池状态检查 ═══")
    print(f"")
    print(f"  自选股池: {len(selected)} 只")
    print(f"    需更新TA分析: {len(stale_selected)} 只")
    if stale_selected:
        for c in stale_selected:
            row = next((r for r in selected if r["code"] == c), {})
            print(f"      {c} {row.get('name','')}")
    print(f"")
    print(f"  关注股池: {len(watch)} 只")
    print(f"    需更新TA分析: {len(stale_watch)} 只")
    if stale_watch:
        for c in stale_watch[:5]:
            row = next((r for r in watch if r["code"] == c), {})
            print(f"      {c} {row.get('name','')}")

    print(f"\n  建议:")
    if stale_selected:
        print(f"    ta_orchestrator.py --mode daily-batch --pool selected")
    if stale_watch:
        print(f"    ta_orchestrator.py --mode daily-batch --pool watch")

    return {
        "selected_total": len(selected),
        "selected_stale": len(stale_selected),
        "watch_total": len(watch),
        "watch_stale": len(stale_watch),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="ta_orchestrator — 事件驱动 TA 分析调度器（P4 优化）",
    )
    parser.add_argument("--mode", required=True, choices=["daily-batch", "reanalyze", "check-pool"],
                        help="运行模式")
    parser.add_argument("--pool", choices=["selected", "watch"], default="selected",
                        help="目标股池")
    parser.add_argument("--ticker", help="单只标的（reanalyze 模式）")
    parser.add_argument("--max-age", type=int, default=7,
                        help="超过 N 天未分析视为过时（默认 7 天）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    modes = {
        "daily-batch": mode_daily_batch,
        "reanalyze": mode_reanalyze,
        "check-pool": mode_check_pool,
    }
    result = modes[args.mode](args)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
