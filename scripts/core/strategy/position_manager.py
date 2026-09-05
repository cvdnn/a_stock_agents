#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持仓管理器 — 开仓/平仓/持仓查询/盈亏计算/快照
完整交易生命周期:
  关注股池(watch) → 自选股池(selected) → 持仓(positions) → 平仓(历史)

采用业务逻辑层 (API) 与终端展示层 (CLI) 分离架构。
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
from typing import Any, Dict, List, Optional, Tuple

# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
from core.config import PROJECT_ROOT

from core.config import (
    DEFAULT_MA_BUFFER_PCT,
    DEFAULT_STOP_LOSS_PCT,
    OUTPUT_POOLS_DIR,
    get_logger,
    infer_market_prefix,
    normalize_symbol,
)
from core.strategy.pool_schema import (
    HISTORY_FIELDS,
    POSITIONS_FIELDS,
    _is_blocked,
    ensure_pool_csv as _ensure_file,
    is_blocked,
    read_pool_csv as _read_csv,
    write_pool_csv as _write_csv,
)

logger = get_logger("core.strategy.position_manager")

POOLS_BASE = OUTPUT_POOLS_DIR
POSITIONS_PATH = os.path.join(str(POOLS_BASE), "positions.csv")
HISTORY_PATH = os.path.join(str(POOLS_BASE), "positions_history.csv")
SELECTED_PATH = os.path.join(str(POOLS_BASE), "selected_pool.csv")
A_DATA_DIR = str(PROJECT_ROOT / "core" / "data")
VENV_PY = sys.executable


def _get_quote(code: str) -> Dict[str, Any]:
    """获取实时行情信息，具备多级降级保护。"""
    try:
        from core.data.data_bridge import DataBridge
        q = DataBridge().get_realtime_quote(code)
        if q and "price" in q:
            return {
                "最新价": q.get("price"),
                "名称": q.get("name", code),
                "涨跌幅(%)": q.get("change_pct", 0),
                "代码": q.get("code", code),
            }
    except Exception as exc:
        logger.debug(f"[position_manager] L1 DataBridge.get_realtime_quote({code}) failed: {exc}")
    try:
        script_path = os.path.join(A_DATA_DIR, "fetch_patched.py")
        if os.path.exists(VENV_PY) and os.path.exists(script_path):
            r = subprocess.run(
                [VENV_PY, script_path,
                 "fetch_realtime.py", "--quote", code, "--json"],
                capture_output=True, text=True, timeout=20,
            )
            if r.returncode == 0 and r.stdout:
                return json.loads(r.stdout)
    except Exception as exc:
        logger.warning(f"[position_manager] L2 subprocess quote failed for {code}: {exc}")
    return {}


# ═══════════════════════════════════════════════════
#  核心业务逻辑层 (Business Services)
# ═══════════════════════════════════════════════════

def get_open_positions(enrich_quote: bool = True) -> List[Dict[str, Any]]:
    """获取当前持仓列表，可附加实时行情与浮动盈亏。"""
    rows = _read_csv(POSITIONS_PATH)
    if not enrich_quote:
        return rows

    enriched = []
    for r in rows:
        item = dict(r)
        code = r["code"]
        buy_price = float(r.get("buy_price", 0) or 0)
        qty = int(r.get("qty", 0) or 0)
        cost = buy_price * qty
        quote = _get_quote(code)
        cur_price = float(quote.get("最新价", buy_price) or buy_price)
        cur_val = cur_price * qty
        pnl = cur_val - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0.0

        item["cur_price"] = cur_price
        item["cost"] = cost
        item["market_value"] = cur_val
        item["pnl"] = pnl
        item["pnl_pct"] = pnl_pct
        item["quote_name"] = quote.get("名称", r.get("name", code))
        enriched.append(item)
    return enriched


def get_history_positions() -> List[Dict[str, Any]]:
    """获取历史平仓记录。"""
    return _read_csv(HISTORY_PATH)


def open_position(
    code: str,
    price: float,
    qty: int,
    name: str = "",
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    date: str = "",
    sector: str = "",
    reason: str = "",
    strategy: str = "",
    entry_trigger: str = "",
    expected_days: Optional[int] = None,
    risk_level: str = "",
    ma_status: str = "",
    market_context: str = "",
    backtest_result: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """开仓买入标的，支持参数校验、自动去重与自选股池联动。"""
    _ensure_file(POSITIONS_PATH, POSITIONS_FIELDS)
    rows = _read_csv(POSITIONS_PATH)

    if _is_blocked(code):
        return {"success": False, "error": f"{code} 为不可交易板块股票（创业板/科创板/北交所）"}
    if any(r["code"] == code for r in rows):
        return {"success": False, "error": f"{code} 已在持仓中，不能重复开仓"}

    quote = _get_quote(code)
    actual_name = name or quote.get("名称", code)

    new_record = {
        "code": code,
        "name": actual_name,
        "buy_date": date or datetime.now().strftime("%Y-%m-%d"),
        "buy_price": str(price),
        "qty": str(qty),
        "stop_loss": str(stop_loss) if stop_loss else "",
        "take_profit": str(take_profit) if take_profit else "",
        "sector": sector,
        "reason": reason,
        "status": "持有",
        "strategy": strategy,
        "entry_trigger": entry_trigger,
        "expected_days": str(expected_days) if expected_days else "",
        "risk_level": risk_level,
        "ma_status": ma_status,
        "market_context": market_context,
        "backtest_result": backtest_result,
        "notes": notes,
    }
    rows.append(new_record)
    _write_csv(POSITIONS_PATH, rows, POSITIONS_FIELDS)

    # 自动从自选股池移除
    removed_from_selected = False
    if os.path.exists(SELECTED_PATH):
        sel = _read_csv(SELECTED_PATH)
        new_sel = [r for r in sel if r["code"] != code]
        if len(new_sel) < len(sel):
            _write_csv(SELECTED_PATH, new_sel, ["code","name","added_date","reason","sector","rating","entry_price","position"])
            removed_from_selected = True

    return {
        "success": True,
        "record": new_record,
        "cost": price * qty,
        "removed_from_selected": removed_from_selected,
    }


def close_position(
    code: str,
    price: Optional[float] = None,
    reason: str = "",
    hold_days: Optional[int] = None,
) -> Dict[str, Any]:
    """平仓卖出标的，移入历史表并更新持仓表。"""
    rows = _read_csv(POSITIONS_PATH)
    target = None
    for r in rows:
        if r["code"] == code:
            target = r
            break
    if not target:
        return {"success": False, "error": f"持仓中未找到 {code}"}

    qty = int(target["qty"])
    buy_price = float(target["buy_price"])
    sell_price = price or float(_get_quote(code).get("最新价", buy_price))
    pnl = (sell_price - buy_price) * qty
    pnl_pct = (sell_price - buy_price) / buy_price * 100 if buy_price > 0 else 0.0

    _ensure_file(HISTORY_PATH, HISTORY_FIELDS)
    hist = _read_csv(HISTORY_PATH)
    hist_record = {
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
        "reason": reason or "平仓",
        "strategy": target.get("strategy", ""),
        "entry_trigger": target.get("entry_trigger", ""),
        "hold_days": str(hold_days or ""),
        "risk_level": target.get("risk_level", ""),
        "notes": target.get("notes", ""),
    }
    hist.append(hist_record)
    _write_csv(HISTORY_PATH, hist, HISTORY_FIELDS)

    rows = [r for r in rows if r["code"] != code]
    _write_csv(POSITIONS_PATH, rows, POSITIONS_FIELDS)

    return {
        "success": True,
        "code": code,
        "name": target["name"],
        "buy_price": buy_price,
        "sell_price": sell_price,
        "qty": qty,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


def update_position(
    code: str,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """更新持仓的风控止损/止盈/理由等字段。"""
    rows = _read_csv(POSITIONS_PATH)
    for r in rows:
        if r["code"] == code:
            if stop_loss is not None:
                r["stop_loss"] = str(stop_loss)
            if take_profit is not None:
                r["take_profit"] = str(take_profit)
            if reason is not None:
                r["reason"] = reason
            _write_csv(POSITIONS_PATH, rows, POSITIONS_FIELDS)
            return {"success": True, "code": code, "updated": r}
    return {"success": False, "error": f"未找到持仓标的 {code}"}


def calculate_pnl_summary() -> Dict[str, Any]:
    """计算当前总持仓盈亏、浮亏与已实现盈亏汇总。"""
    rows = _read_csv(POSITIONS_PATH)
    hist = _read_csv(HISTORY_PATH)

    total_cost = 0.0
    total_value = 0.0
    for r in rows:
        buy_price = float(r.get("buy_price", 0) or 0)
        qty = int(r.get("qty", 0) or 0)
        cost = buy_price * qty
        total_cost += cost
        quote = _get_quote(r["code"])
        cur_price = float(quote.get("最新价", buy_price) or buy_price)
        total_value += cur_price * qty

    floating_pnl = total_value - total_cost
    realized_pnl = sum(float(r.get("pnl", 0) or 0) for r in hist)
    total_pnl = floating_pnl + realized_pnl
    return {
        "total_cost": total_cost,
        "total_value": total_value,
        "floating_pnl": floating_pnl,
        "realized_pnl": realized_pnl,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / total_cost * 100) if total_cost > 0 else 0.0,
        "position_count": len(rows),
        "history_count": len(hist),
    }


def check_stop_triggers() -> List[Dict[str, Any]]:
    """检测当前持仓是否触发预设的止损/止盈位。"""
    rows = _read_csv(POSITIONS_PATH)
    triggers = []
    for r in rows:
        code = r["code"]
        quote = _get_quote(code)
        cur_price = quote.get("最新价")
        if not cur_price:
            continue

        sl = r.get("stop_loss")
        tp = r.get("take_profit")
        name = r.get("name", code)

        if sl and float(sl) > 0:
            sl_val = float(sl)
            if cur_price <= sl_val:
                triggers.append({
                    "type": "stop_loss",
                    "code": code,
                    "name": name,
                    "cur_price": cur_price,
                    "threshold": sl_val,
                    "diff_pct": (cur_price - sl_val) / sl_val * 100,
                    "message": f"⚠ 止损触发: {code}({name}) 现价{cur_price} ≤ 止损{sl}",
                })

        if tp and float(tp) > 0:
            tp_val = float(tp)
            if cur_price >= tp_val:
                triggers.append({
                    "type": "take_profit",
                    "code": code,
                    "name": name,
                    "cur_price": cur_price,
                    "threshold": tp_val,
                    "diff_pct": (cur_price - tp_val) / tp_val * 100,
                    "message": f"✓ 止盈触发: {code}({name}) 现价{cur_price} ≥ 止盈{tp}",
                })
    return triggers


# ═══════════════════════════════════════════════════
#  命令行展示层 (CLI Formatting & Dispatch)
# ═══════════════════════════════════════════════════

def cmd_list(args):
    """列出当前持仓或历史"""
    if getattr(args, "history", False):
        rows = get_history_positions()
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        if not rows:
            print("暂无平仓历史")
            return
        print(f"\n📜 平仓历史 ({len(rows)} 笔)")
        print(f"{'代码':>8} {'名称':<8} {'买入日':<10} {'卖出日':<10} {'买入价':>8} {'卖出价':>8} {'盈亏':>10} {'盈亏%':>8} {'理由':<12}")
        print("-" * 90)
        total_pnl = 0.0
        for r in rows:
            pnl = float(r.get("pnl", 0) or 0)
            total_pnl += pnl
            icon = "▲" if pnl >= 0 else "▼"
            print(f"{r.get('code','?'):>8} {r.get('name','?'):<8} {r.get('buy_date','?'):<10} "
                  f"{r.get('sell_date','?'):<10} {r.get('buy_price','?'):>8} {r.get('sell_price','?'):>8} "
                  f"{icon} {pnl:>+8.0f} {r.get('pnl_pct','?'):>7}% {r.get('reason','?'):<12}")
        print(f"\n  累计盈亏: {total_pnl:+.0f}")
        return

    # 当前持仓
    rows = get_open_positions(enrich_quote=True)
    if getattr(args, "json", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("当前无持仓")
        return

    total_cost = 0.0
    total_value = 0.0
    print(f"\n📊 当前持仓 ({len(rows)} 只)")
    print(f"{'代码':>8} {'名称':<8} {'策略':<12} {'买入价':>8} {'数量':>8} {'成本':>10} {'现价':>8} {'盈亏':>10} {'盈亏%':>8} {'风险':>4}")
    print("-" * 100)

    for r in rows:
        code = r["code"]
        name = r.get("name", code)
        buy_price = float(r["buy_price"])
        qty = int(r["qty"])
        cost = r["cost"]
        cur_price = r["cur_price"]
        pnl = r["pnl"]
        pnl_pct = r["pnl_pct"]
        total_cost += cost
        total_value += r["market_value"]

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
    res = open_position(
        code=args.code,
        price=args.price,
        qty=args.qty,
        name=getattr(args, "name", "") or "",
        stop_loss=getattr(args, "stop_loss", None),
        take_profit=getattr(args, "take_profit", None),
        date=getattr(args, "date", "") or "",
        sector=getattr(args, "sector", "") or "",
        reason=getattr(args, "reason", "") or "",
        strategy=getattr(args, "strategy", "") or "",
        entry_trigger=getattr(args, "entry_trigger", "") or "",
        expected_days=getattr(args, "expected_days", None),
        risk_level=getattr(args, "risk_level", "") or "",
        ma_status=getattr(args, "ma_status", "") or "",
        market_context=getattr(args, "market_context", "") or "",
        backtest_result=getattr(args, "backtest_result", "") or "",
        notes=getattr(args, "notes", "") or "",
    )
    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if not res["success"]:
        print(f"✗ 开仓失败: {res['error']}", file=sys.stderr)
        return

    rec = res["record"]
    print(f"✓ 开仓成功: {rec['code']}({rec['name']})")
    print(f"  买入价: {rec['buy_price']} x {rec['qty']} = {res['cost']:.0f}")
    if rec.get("stop_loss"):
        sl = float(rec["stop_loss"])
        p = float(rec["buy_price"])
        print(f"  止损: {sl} (跌幅{(sl-p)/p*100:.1f}%)")
    if rec.get("take_profit"):
        tp = float(rec["take_profit"])
        p = float(rec["buy_price"])
        print(f"  止盈: {tp} (涨幅{(tp-p)/p*100:.1f}%)")
    if res.get("removed_from_selected"):
        print(f"  (已从自选股池移除)")


def cmd_close(args):
    """平仓：卖出股票"""
    res = close_position(
        code=args.code,
        price=getattr(args, "price", None),
        reason=getattr(args, "reason", "") or "",
        hold_days=getattr(args, "hold_days", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if not res["success"]:
        print(f"⚠ {res['error']}")
        return

    icon = "▲" if res["pnl"] >= 0 else "▼"
    print(f"✓ 平仓成功: {res['code']}({res['name']})")
    print(f"  买入: {res['buy_price']:.2f} x {res['qty']} → 卖出: {res['sell_price']:.2f} x {res['qty']}")
    print(f"  盈亏: {icon} {res['pnl']:+.0f} ({res['pnl_pct']:+.2f}%)")


def cmd_update(args):
    """更新持仓参数（止损/止盈等）"""
    res = update_position(
        code=args.code,
        stop_loss=getattr(args, "stop_loss", None),
        take_profit=getattr(args, "take_profit", None),
        reason=getattr(args, "reason", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if res["success"]:
        print(f"✓ {args.code} 已更新")
    else:
        print(f"⚠ {res['error']}")


def cmd_pnl(args):
    """盈亏总览"""
    summary = calculate_pnl_summary()
    if getattr(args, "json", False):
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(f"\n{'='*50}")
    print(f"  盈亏总览")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    print(f"  当前持仓成本: {summary['total_cost']:>10.0f}")
    print(f"  当前持仓市值: {summary['total_value']:>10.0f}")
    print(f"  浮动盈亏:     {summary['floating_pnl']:>+10.0f}")
    print(f"  已实现盈亏:   {summary['realized_pnl']:>+10.0f}")
    print(f"  {'─'*40}")
    print(f"  总盈亏:       {summary['total_pnl']:>+10.0f}")
    if summary["total_cost"] > 0:
        print(f"  总收益率:     {summary['total_pnl_pct']:>+9.2f}%")
    print(f"{'='*50}")


def cmd_snapshot(args):
    """持仓快照（含实时价和止损/止盈触发检查）"""
    cmd_list(args)
    triggers = check_stop_triggers()
    if getattr(args, "json", False):
        return

    print(f"\n── 止损/止盈触发检查 ──")
    if triggers:
        for t in triggers:
            print(f"  {t['message']}")
    else:
        print("  无触发")


def main():
    parser = argparse.ArgumentParser(description="持仓管理器")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="查看持仓")
    p_list.add_argument("--history", action="store_true", help="查看平仓历史")
    p_list.add_argument("--json", action="store_true", help="以 JSON 格式输出")

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
    p_open.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    # close
    p_close = sub.add_parser("close", help="平仓")
    p_close.add_argument("--code", required=True)
    p_close.add_argument("--price", type=float)
    p_close.add_argument("--reason")
    p_close.add_argument("--hold-days", type=int, help="实际持有天数")
    p_close.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    # update
    p_upd = sub.add_parser("update", help="更新持仓参数")
    p_upd.add_argument("--code", required=True)
    p_upd.add_argument("--stop-loss", type=float)
    p_upd.add_argument("--take-profit", type=float)
    p_upd.add_argument("--reason")
    p_upd.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    # pnl
    p_pnl = sub.add_parser("pnl", help="盈亏总览")
    p_pnl.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="持仓快照（含实时价和触发检查）")
    p_snap.add_argument("--json", action="store_true", help="以 JSON 格式输出")

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