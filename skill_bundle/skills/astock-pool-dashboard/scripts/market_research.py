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

import sys as _astock_sys
import os as _astock_os
import json as _astock_json
from pathlib import Path as _AstPath

def _astock_resolve_bundle():
    _file_path = _AstPath(__file__).resolve()
    # 1. 自定位：自身及父目录向上查找 bundle.json
    for _p in _file_path.parents:
        if (_p / "bundle.json").is_file():
            return _p
    # 2. 兄弟定位：查找兄弟目录 a-stock-agents/bundle.json（未解析/已解析上级均探测）
    for _base in (_AstPath(__file__), _file_path):
        for _p in _base.parents:
            for _candidate in (_p / "a-stock-agents", _p.parent / "a-stock-agents"):
                if (_candidate / "bundle.json").is_file():
                    return _candidate.resolve()
    # 3. 收据定位：读取系统固定安装收据 install.json
    _receipts = []
    _env_root = _astock_os.environ.get("A_STOCK_WORKSPACE_ROOT") or _astock_os.environ.get("A_STOCK_AGENTS_ROOT")
    if _env_root:
        _receipts.append(_AstPath(_env_root) / "install.json")
    if _astock_sys.platform == "win32":
        _local = _astock_os.environ.get("LOCALAPPDATA") or (_AstPath.home() / "AppData/Local")
        _receipts.append(_AstPath(_local) / "a_stock_agents" / "install.json")
    elif _astock_sys.platform == "darwin":
        _receipts.append(_AstPath.home() / "Library/Application Support" / "a_stock_agents" / "install.json")
    else:
        _xdg = _astock_os.environ.get("XDG_DATA_HOME") or (_AstPath.home() / ".local/share")
        _receipts.append(_AstPath(_xdg) / "a_stock_agents" / "install.json")
    for _rp in _receipts:
        if _rp.is_file():
            try:
                _data = _astock_json.loads(_rp.read_text(encoding="utf-8"))
                _target = _data.get("bundle_root") or _data.get("runtime_root") or _data.get("anchor_root")
                if _target:
                    _tp = _AstPath(_target).resolve()
                    if (_tp / "bundle.json").is_file():
                        return _tp
                    if (_tp / "a-stock-agents" / "bundle.json").is_file():
                        return (_tp / "a-stock-agents").resolve()
                    if _tp.name == "runtime" and (_tp.parent / "bundle.json").is_file():
                        return _tp.parent
            except Exception:
                pass
    raise RuntimeError("ANCHOR_SKILL_MISSING: Complete a_stock_agents bundle or a-stock-agents anchor skill required")

_astock_bundle = _astock_resolve_bundle()
_astock_runtime = _astock_bundle / "runtime"
if str(_astock_runtime) not in _astock_sys.path:
    _astock_sys.path.insert(0, str(_astock_runtime))

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from core.workspace import PROJECT_ROOT
A_DATA_DIR = _astock_bundle / "skills" / "astock-data-feed" / "scripts"
VENV_PY = sys.executable


def _run(cmd, timeout=45):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _fetch(script, *args):
    return _run([VENV_PY, str(A_DATA_DIR / "fetch_patched.py"), script] + list(args))


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
