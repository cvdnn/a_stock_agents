#!/usr/bin/env python3
"""
市场研判工具 — 基于 a-share-data 的数据评估市场主线方向

功能:
  1. 板块排行分析 → 当前资金流向主线
  2. 成交额TOP分析 → 大资金偏好
  3. 涨跌停统计 → 市场情绪
  4. 输出综合研判

用法:
  market_research.py                   # 全量市场研判
  market_research.py --boards-only     # 仅板块分析
  market_research.py --flow-only       # 仅资金分析
"""
import argparse
import json
import os
import subprocess
from datetime import datetime

A_DATA_DIR = "./.AI-Platform/skills/stocks/a-share-data/scripts"
VENV_PY = "python3"


def _run(cmd, timeout=45):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _fetch(script, *args):
    return _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_patched.py"), script] + list(args))


def research_full():
    """全量市场研判"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print("=" * 56)
    print(f"  市场趋势研判报告")
    print(f"  日期: {now}")
    print(f"  提示: Agent 需结合外部搜索补充政策和产业信息")
    print("=" * 56)

    # 1. 板块排行
    print("\n── 一、板块排行（当前资金流向）──")
    out = _fetch("fetch_realtime.py", "--boards-summary", "--boards-limit", "15", "--json")
    if out:
        try:
            d = json.loads(out)
            print(f"  {'板块名称':<16} {'涨跌幅':>8} {'上涨家数':>8}")
            print(f"  {'-'*16} {'-'*8} {'-'*8}")
            for b in d.get("data", [])[:10]:
                label = b.get("groupLabel", "?")
                pct = b.get("changePct", 0)
                up = b.get("upCount", 0)
                total = b.get("count", 1)
                print(f"  {label:<16} {pct:>7.2f}% {up:>3d}/{total:<3d}")
        except (json.JSONDecodeError, KeyError):
            print("  [解析失败]")
    else:
        print("  [数据获取失败]")
        print(f"  替代命令: {VENV_PY} a-share-data/scripts/fetch_realtime.py --boards-summary --boards-limit 15")

    # 2. 成交额TOP
    print("\n── 二、成交额TOP10（大资金去向）──")
    out = _fetch("fetch_realtime.py", "--all-quote", "--sort", "amount_desc", "--top", "10", "--json")
    if out:
        try:
            d = json.loads(out)
            for s in d.get("data", [])[:10]:
                name = s.get("name", "?")
                price = s.get("price", "?")
                chg = s.get("change_pct", 0)
                amt = s.get("amount", 0) / 1e8
                print(f"  {name:<10} {price:>8} ({chg:>+6.2f}%) 成交{amt:>6.1f}亿")
        except (json.JSONDecodeError, KeyError):
            print("  [解析失败]")
    else:
        print("  [数据获取失败]")

    # 3. 市场情绪
    print("\n── 三、市场情绪 ──")
    out = _fetch("fetch_realtime.py", "--all-quote", "--json")
    if out:
        try:
            d = json.loads(out)
            stocks = d.get("data", [])
            up = sum(1 for s in stocks if s.get("change_pct", 0) > 0)
            dn = sum(1 for s in stocks if s.get("change_pct", 0) < 0)
            total_amt = sum(s.get("amount", 0) for s in stocks) / 1e8
            print(f"  上涨:{up} 下跌:{dn} 成交额:{total_amt:.0f}亿")
            print(f"  涨跌比:{up/dn:.2f}" if dn > 0 else "  涨跌比:INF")
        except (json.JSONDecodeError, KeyError):
            print("  [解析失败]")
    else:
        print("  [数据获取失败]")

    # 4. 综合研判框架
    print("\n── 四、综合研判（Agent需补充）──")
    print("  1. 政策方向：需搜索'国常会/政治局/部委 最新政策定调'")
    print("  2. 产业主线：需搜索'机构下半年策略 AI/半导体/新能源'")
    print("  3. 国际环境：需搜索'美联储/中美关系/地缘'")
    print("  4. 选股依据：综合以上 → 输出 3~5 个主线方向")
    print("\n  执行建议: Agent 调用 web_search 补全第4部分")

    print("\n" + "=" * 56)
    print(f"  报告完成，使用 investment_report.py 生成个股报告")
    print("=" * 56)


def research_boards_only():
    """仅板块分析"""
    print(f"\n板块排行 ({datetime.now().strftime('%H:%M')})")
    print("-" * 50)
    out = _fetch("fetch_realtime.py", "--boards-summary", "--boards-limit", "10", "--json")
    if out:
        try:
            d = json.loads(out)
            for b in d.get("data", [])[:10]:
                print(f"  {b.get('groupLabel','?'):<14} {b.get('changePct',0):>+6.2f}%  ({b.get('upCount',0)}涨/{b.get('count',0)}只)")
        except json.JSONDecodeError:
            print("  [解析失败]")
    else:
        print("  [获取失败]")


def main():
    parser = argparse.ArgumentParser(description="市场研判工具")
    parser.add_argument("--boards-only", action="store_true", help="仅板块排行")
    parser.add_argument("--flow-only", action="store_true", help="仅资金分析")
    args = parser.parse_args()

    if args.boards_only:
        research_boards_only()
    elif args.flow_only:
        print("仅资金分析模式待实现")
    else:
        research_full()


if __name__ == "__main__":
    main()