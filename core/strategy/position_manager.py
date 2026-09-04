#!/usr/bin/env python3
"""
持仓管理器 — 开仓/平仓/持仓查询/盈亏计算/快照

完整交易生命周期:
  关注股池(watch) → 自选股池(selected) → 持仓(positions) → 平仓(历史)

用法:
  position_manager.py list                    # 当前持仓列表
  position_manager.py list --history          # 历史平仓记录
  position_manager.py open --code CODE --price 42.5 --qty 1000 [--reason "理由"]
  position_manager.py close --code CODE --price 43.0 [--reason "止盈"]
  position_manager.py update --code CODE --stop-loss 40.0 --take-profit 46.0
  position_manager.py pnl                     # 盈亏总览
  position_manager.py snapshot                # 持仓快照（含实时价）
  position_manager.py check-stops             # 检查止损/止盈触发
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core"))

from core.config import OUTPUT_POOLS_DIR
POOLS_BASE = OUTPUT_POOLS_DIR

POSITIONS_PATH = os.path.join(str(POOLS_BASE), "positions.csv")
HISTORY_PATH = os.path.join(str(POOLS_BASE), "positions_history.csv")
SELECTED_PATH = os.path.join(str(POOLS_BASE), "selected_pool.csv")
A_DATA_DIR = str(PROJECT_ROOT / "core" / "data")
VENV_PY = sys.executable


from core.strategy.pool_schema import (
    POSITIONS_FIELDS,
    HISTORY_FIELDS,
    is_blocked,
    _is_blocked,
    ensure_pool_csv as _ensure_file,
    read_pool_csv as _read_csv,
    write_pool_csv as _write_csv,
)






def _get_quote(code):
    try:
        from core.data.data_bridge import DataBridge
        q = DataBridge().get_realtime_quote(code)
        if q and "price" in q:
            return {
                "最新价": q.get("price"),
                "名称": q.get("name", code),
                "涨跌幅(%)": q.get("change_pct", 0),
                "代码": q.get("code", code)
            }
    except Exception:
        pass
    try:
        r = subprocess.run(
            [VENV_PY, os.path.join(A_DATA_DIR, "fetch_patched.py"),
             "fetch_realtime.py", "--quote", code, "--json"],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0:
            return json.loads(r.stdout)
    except Exception:
        pass
    return {}



# ── 命令实现 ──

def cmd_list(args):
    """列出当前持仓或历史"""
    if getattr(args, "history", False):
        rows = _read_csv(HISTORY_PATH)
        if not rows:
            print("暂无平仓历史")
            return
        print(f"\n📜 平仓历史 ({len(rows)} 笔)")
        print(f"{'代码':>8} {'名称':<8} {'买入日':<10} {'卖出日':<10} {'买入价':>8} {'卖出价':>8} {'盈亏':>10} {'盈亏%':>8} {'理由':<12}")
        print("-" * 90)
        total_pnl = 0
        for r in rows:
            pnl = float(r.get("pnl", 0))
            total_pnl += pnl
            icon = "▲" if pnl >= 0 else "▼"
            print(f"{r.get('code','?'):>8} {r.get('name','?'):<8} {r.get('buy_date','?'):<10} "
                  f"{r.get('sell_date','?'):<10} {r.get('buy_price','?'):>8} {r.get('sell_price','?'):>8} "
                  f"{icon} {pnl:>+8.0f} {r.get('pnl_pct','?'):>7}% {r.get('reason','?'):<12}")
        print(f"\n  累计盈亏: {total_pnl:+.0f}")
        return

    # 当前持仓
    rows = _read_csv(POSITIONS_PATH)
    if not rows:
        print("当前无持仓")
        return

    total_cost = 0
    total_value = 0
    print(f"\n📊 当前持仓 ({len(rows)} 只)")
    print(f"{'代码':>8} {'名称':<8} {'策略':<12} {'买入价':>8} {'数量':>8} {'成本':>10} {'现价':>8} {'盈亏':>10} {'盈亏%':>8} {'风险':>4}")
    print("-" * 100)

    for r in rows:
        code = r["code"]
        name = r["name"]
        buy_price = float(r["buy_price"])
        qty = int(r["qty"])
        cost = buy_price * qty
        total_cost += cost

        quote = _get_quote(code)
        cur_price = quote.get("最新价", buy_price)
        value = cur_price * qty
        total_value += value
        pnl = value - cost
        pnl_pct = (cur_price - buy_price) / buy_price * 100
        icon = "▲" if pnl >= 0 else "▼"
        strategy = r.get("strategy", "")[:12]
        risk = r.get("risk_level", "")

        print(f"{code:>8} {name:<8} {strategy:<12} {buy_price:>8.2f} {qty:>8d} "
              f"{cost:>10.0f} {cur_price:>8.2f} {icon} {pnl:>+8.0f} {pnl_pct:>+7.2f}% {risk:>4}")

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_value - total_cost) / total_cost * 100 if total_cost > 0 else 0
    print("-" * 100)
    print(f"{'合计':>26} {'':>8} {total_cost:>10.0f} {'':>8} {total_value:>10.0f} {'':>8} {total_pnl:>+8.0f} {total_pnl_pct:>+7.2f}%")


def cmd_open(args):
    """开仓：买入股票"""
    _ensure_file(POSITIONS_PATH, POSITIONS_FIELDS)
    rows = _read_csv(POSITIONS_PATH)

    if _is_blocked(args.code):
        print(f"✗ {args.code} 为不可交易板块股票（创业板/科创板/北交所）", file=sys.stderr)
        return
    if any(r["code"] == args.code for r in rows):
        print(f"⚠ {args.code} 已在持仓中，不能重复开仓")
        return

    # 获取名称
    quote = _get_quote(args.code)
    name = args.name or quote.get("名称", args.code)

    rows.append({
        "code": args.code,
        "name": name,
        "buy_date": args.date or datetime.now().strftime("%Y-%m-%d"),
        "buy_price": str(args.price),
        "qty": str(args.qty),
        "stop_loss": str(args.stop_loss) if args.stop_loss else "",
        "take_profit": str(args.take_profit) if args.take_profit else "",
        "sector": args.sector or "",
        "reason": args.reason or "",
        "status": "持有",
        "strategy": args.strategy or "",
        "entry_trigger": args.entry_trigger or "",
        "expected_days": str(args.expected_days) if args.expected_days else "",
        "risk_level": args.risk_level or "",
        "ma_status": args.ma_status or "",
        "market_context": args.market_context or "",
        "backtest_result": args.backtest_result or "",
        "notes": args.notes or "",
    })
    _write_csv(POSITIONS_PATH, rows, POSITIONS_FIELDS)

    cost = args.price * args.qty
    print(f"✓ 开仓成功: {args.code}({name})")
    print(f"  买入价: {args.price} x {args.qty} = {cost:.0f}")
    if args.stop_loss:
        print(f"  止损: {args.stop_loss} (跌幅{(args.stop_loss-args.price)/args.price*100:.1f}%)")
    if args.take_profit:
        print(f"  止盈: {args.take_profit} (涨幅{(args.take_profit-args.price)/args.price*100:.1f}%)")

    # 自动从自选股池移除
    if os.path.exists(SELECTED_PATH):
        sel = _read_csv(SELECTED_PATH)
        new_sel = [r for r in sel if r["code"] != args.code]
        if len(new_sel) < len(sel):
            _write_csv(SELECTED_PATH, new_sel, ["code","name","added_date","reason","sector","rating","entry_price","position"])
            print(f"  (已从自选股池移除)")


def cmd_close(args):
    """平仓：卖出股票"""
    rows = _read_csv(POSITIONS_PATH)
    target = None
    for r in rows:
        if r["code"] == args.code:
            target = r
            break
    if not target:
        print(f"⚠ 持仓中未找到 {args.code}")
        return

    qty = int(target["qty"])
    buy_price = float(target["buy_price"])
    sell_price = args.price or float(_get_quote(args.code).get("最新价", buy_price))
    pnl = (sell_price - buy_price) * qty
    pnl_pct = (sell_price - buy_price) / buy_price * 100

    # 记录历史
    _ensure_file(HISTORY_PATH, HISTORY_FIELDS)
    hist = _read_csv(HISTORY_PATH)
    hist.append({
        "code": target["code"],
        "name": target["name"],
        "buy_date": target["buy_date"],
        "sell_date": datetime.now().strftime("%Y-%m-%d"),
        "buy_price": target["buy_price"],
        "sell_price": f"{sell_price:.2f}",
        "qty": target["qty"],
        "pnl": f"{pnl:.0f}",
        "pnl_pct": f"{pnl_pct:.2f}",
        "sector": target.get("sector", ""),
        "reason": args.reason or "平仓",
        "strategy": target.get("strategy", ""),
        "entry_trigger": target.get("entry_trigger", ""),
        "hold_days": str(args.hold_days or ""),
        "risk_level": target.get("risk_level", ""),
        "notes": target.get("notes", ""),
    })
    _write_csv(HISTORY_PATH, hist, HISTORY_FIELDS)

    # 从持仓移除
    rows = [r for r in rows if r["code"] != args.code]
    _write_csv(POSITIONS_PATH, rows, POSITIONS_FIELDS)

    icon = "▲" if pnl >= 0 else "▼"
    print(f"✓ 平仓成功: {args.code}({target['name']})")
    print(f"  买入: {buy_price:.2f} x {qty} → 卖出: {sell_price:.2f} x {qty}")
    print(f"  盈亏: {icon} {pnl:+.0f} ({pnl_pct:+.2f}%)")


def cmd_update(args):
    """更新持仓参数（止损/止盈等）"""
    rows = _read_csv(POSITIONS_PATH)
    for r in rows:
        if r["code"] == args.code:
            if args.stop_loss is not None:
                r["stop_loss"] = str(args.stop_loss)
            if args.take_profit is not None:
                r["take_profit"] = str(args.take_profit)
            if args.reason:
                r["reason"] = args.reason
            _write_csv(POSITIONS_PATH, rows, POSITIONS_FIELDS)
            print(f"✓ {args.code} 已更新")
            return
    print(f"⚠ 未找到 {args.code}")


def cmd_pnl(args):
    """盈亏总览"""
    rows = _read_csv(POSITIONS_PATH)
    hist = _read_csv(HISTORY_PATH)

    # 当前持仓浮动盈亏
    total_cost = 0
    total_value = 0
    for r in rows:
        buy_price = float(r["buy_price"])
        qty = int(r["qty"])
        cost = buy_price * qty
        total_cost += cost
        quote = _get_quote(r["code"])
        cur_price = quote.get("最新价", buy_price)
        total_value += cur_price * qty

    floating_pnl = total_value - total_cost

    # 历史已实现盈亏
    realized_pnl = sum(float(r.get("pnl", 0)) for r in hist)

    total_pnl = floating_pnl + realized_pnl

    print(f"\n{'='*50}")
    print(f"  盈亏总览")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    print(f"  当前持仓成本: {total_cost:>10.0f}")
    print(f"  当前持仓市值: {total_value:>10.0f}")
    print(f"  浮动盈亏:     {floating_pnl:>+10.0f}")
    print(f"  已实现盈亏:   {realized_pnl:>+10.0f}")
    print(f"  {'─'*40}")
    print(f"  总盈亏:       {total_pnl:>+10.0f}")
    if total_cost > 0:
        print(f"  总收益率:     {total_pnl/total_cost*100:>+9.2f}%")
    print(f"{'='*50}")


def cmd_snapshot(args):
    """持仓快照（含实时价和止损/止盈触发检查）"""
    cmd_list(args)  # 先显示持仓
    rows = _read_csv(POSITIONS_PATH)
    if not rows:
        return

    print(f"\n── 止损/止盈触发检查 ──")
    triggered = []
    for r in rows:
        code = r["code"]
        quote = _get_quote(code)
        cur_price = quote.get("最新价")
        if not cur_price:
            continue

        sl = r.get("stop_loss")
        tp = r.get("take_profit")
        name = r["name"]

        if sl and float(sl) > 0:
            sl_pct = (float(sl) - cur_price) / cur_price * 100
            if sl_pct >= 0:
                triggered.append(f"⚠ 止损触发: {code}({name}) 现价{cur_price} ≤ 止损{sl}")

        if tp and float(tp) > 0:
            tp_pct = (cur_price - float(tp)) / float(tp) * 100
            if tp_pct >= 0:
                triggered.append(f"✓ 止盈触发: {code}({name}) 现价{cur_price} ≥ 止盈{tp}")

    if triggered:
        for t in triggered:
            print(f"  {t}")
    else:
        print("  无触发")


def main():
    parser = argparse.ArgumentParser(description="持仓管理器")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="查看持仓")
    p_list.add_argument("--history", action="store_true", help="查看平仓历史")

    # open
    p_open = sub.add_parser("open", help="开仓")
    p_open.add_argument("--code", required=True)
    p_open.add_argument("--name")
    p_open.add_argument("--price", type=float, required=True)
    p_open.add_argument("--qty", type=int, required=True)
    p_open.add_argument("--stop-loss", type=float)
    p_open.add_argument("--take-profit", type=float)
    p_open.add_argument("--sector")
    p_open.add_argument("--reason")
    p_open.add_argument("--date")
    p_open.add_argument("--strategy", help="策略名称如:趋势共振/缩量回踩/MACD二次金叉")
    p_open.add_argument("--entry-trigger", help="入场触发条件")
    p_open.add_argument("--expected-days", type=int, help="预期持有天数")
    p_open.add_argument("--risk-level", choices=["低","中","高"])
    p_open.add_argument("--ma-status", choices=["多头","震荡","空头"])
    p_open.add_argument("--market-context")
    p_open.add_argument("--backtest-result")
    p_open.add_argument("--notes")

    # close
    p_close = sub.add_parser("close", help="平仓")
    p_close.add_argument("--code", required=True)
    p_close.add_argument("--price", type=float)
    p_close.add_argument("--reason")
    p_close.add_argument("--hold-days", type=int, help="实际持有天数")

    # update
    p_upd = sub.add_parser("update", help="更新持仓参数")
    p_upd.add_argument("--code", required=True)
    p_upd.add_argument("--stop-loss", type=float)
    p_upd.add_argument("--take-profit", type=float)
    p_upd.add_argument("--reason")

    # pnl
    sub.add_parser("pnl", help="盈亏总览")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="持仓快照（含实时价和触发检查）")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "open":
        cmd_open(args)
    elif args.command == "close":
        cmd_close(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "pnl":
        cmd_pnl(args)
    elif args.command == "snapshot":
        cmd_snapshot(args)


if __name__ == "__main__":
    main()