# -*- coding: utf-8 -*-
"""
Paper Trading CLI subcommands for a_stock_agents.
Supports:
- balance / show-account: Query account cash, balance and assets
- accounts / list-accounts: List registered paper trading accounts
- create-account: Create a new paper account
- reset-account: Reset cash & positions for an account
- set-default: Set default trading account
- buy: Buy order (limit or market)
- sell: Sell order (limit or market)
- positions: Query stock positions
- orders: Query active or historical orders
- trades: Query trade transaction logs
- cancel: Cancel open orders
- add-cash / deduct-cash: Adjust available balance
- status / start / stop: Manage backend service
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_logger
from core.paper_trading.engine import OrderRequest, PaperTradingEngine
from core.paper_trading.paper_trading_runtime import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    get_default_db_path,
    get_default_log_path,
    get_default_pid_path,
)

logger = get_logger("core.commands.trade")


def _get_engine() -> PaperTradingEngine:
    db_path = get_default_db_path()
    return PaperTradingEngine(db_path=str(db_path))


def _resolve_account_id(engine: PaperTradingEngine, account_id: Optional[str] = None) -> Optional[str]:
    if account_id:
        return account_id
    default_id = engine.get_default_account_id()
    if default_id:
        return default_id
    accounts = engine.list_accounts()
    if len(accounts) == 1:
        return accounts[0]["account_id"]
    return None


def cmd_trade_balance(args, engine: PaperTradingEngine):
    """查询账户资金与余额"""
    target_id = _resolve_account_id(engine, getattr(args, "account_id", None))
    output_json = getattr(args, "json", False)

    if not target_id:
        accounts = engine.list_accounts()
        if not accounts:
            msg = {
                "status": "not_initialized",
                "message": "当前未初始化模拟账户。可用命令创建: astock trade create-account alpha --cash 1000000",
            }
            if output_json:
                print(json.dumps(msg, ensure_ascii=False, indent=2))
            else:
                print("ℹ️ 当前未初始化模拟账户。")
                print("   请先创建账户: ./bin/astock trade create-account alpha --cash 1000000")
            return
        msg = {
            "status": "multiple_accounts",
            "message": "检测到多个账户且未设定默认账户，请指定 account_id",
            "available_accounts": [a["account_id"] for a in accounts],
        }
        if output_json:
            print(json.dumps(msg, ensure_ascii=False, indent=2))
        else:
            print("⚠️ 检测到多个账户，请指定账户代码:")
            for a in accounts:
                print(f"  - {a['account_id']} (可用资金: ¥{a['available_cash']:,.2f})")
        return

    try:
        acc = engine.get_account(target_id)
        positions = engine.get_positions(target_id)
        total_market_value = sum(p.get("market_value", 0.0) for p in positions)
        total_asset = acc.get("cash", 0.0) + total_market_value

        res = {
            "account_id": acc["account_id"],
            "total_asset": round(total_asset, 2),
            "cash": round(acc["cash"], 2),
            "available_cash": round(acc["available_cash"], 2),
            "frozen_cash": round(acc["frozen_cash"], 2),
            "market_value": round(total_market_value, 2),
            "positions_count": len(positions),
            "created_at": acc.get("created_at", ""),
        }
        if output_json:
            print(json.dumps({"status": "success", "data": res}, ensure_ascii=False, indent=2))
        else:
            print(f"=== 模拟盘账户资金: {res['account_id']} ===")
            print(f"  总资产:     ¥{res['total_asset']:,.2f}")
            print(f"  总现金:     ¥{res['cash']:,.2f}")
            print(f"  可用资金:   ¥{res['available_cash']:,.2f}")
            print(f"  冻结资金:   ¥{res['frozen_cash']:,.2f}")
            print(f"  持仓市值:   ¥{res['market_value']:,.2f}")
            print(f"  持仓标的数: {res['positions_count']} 支")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 查询失败: {e}")


def cmd_trade_accounts(args, engine: PaperTradingEngine):
    """列出所有账户"""
    output_json = getattr(args, "json", False)
    accounts = engine.list_accounts()
    default_id = engine.get_default_account_id()
    if output_json:
        print(json.dumps({"status": "success", "default_account_id": default_id, "accounts": accounts}, ensure_ascii=False, indent=2))
    else:
        print(f"=== 模拟盘账户列表 (共 {len(accounts)} 个) ===")
        if not accounts:
            print("  (暂无账户，可用 create-account 创建)")
            return
        for a in accounts:
            tag = " [默认]" if a["account_id"] == default_id else ""
            print(f"  - {a['account_id']}{tag}: 可用资金 ¥{a['available_cash']:,.2f} / 总现金 ¥{a['cash']:,.2f}")


def cmd_trade_create(args, engine: PaperTradingEngine):
    """创建模拟盘账户"""
    output_json = getattr(args, "json", False)
    acc_id = args.account_id
    cash = getattr(args, "cash", 1000000.0)
    try:
        acc = engine.create_account(acc_id, cash)
        if not engine.get_default_account_id():
            engine.set_default_account(acc_id)
        if output_json:
            print(json.dumps({"status": "success", "account": acc}, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 成功创建模拟账户 '{acc_id}'，初始资金: ¥{cash:,.2f}")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 创建失败: {e}")


def cmd_trade_reset(args, engine: PaperTradingEngine):
    """重置模拟盘账户"""
    output_json = getattr(args, "json", False)
    acc_id = args.account_id
    cash = getattr(args, "cash", None)
    try:
        acc = engine.reset_account(acc_id, cash)
        if output_json:
            print(json.dumps({"status": "success", "account": acc}, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 账户 '{acc_id}' 已成功重置，初始资金: ¥{acc['cash']:,.2f}")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 重置失败: {e}")


def cmd_trade_set_default(args, engine: PaperTradingEngine):
    """设置默认账户"""
    output_json = getattr(args, "json", False)
    acc_id = args.account_id
    try:
        res = engine.set_default_account(acc_id)
        if output_json:
            print(json.dumps({"status": "success", "default_account_id": acc_id}, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 默认模拟盘账户已设为: '{acc_id}'")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 设置失败: {e}")


def cmd_trade_positions(args, engine: PaperTradingEngine):
    """查询持仓"""
    output_json = getattr(args, "json", False)
    target_id = _resolve_account_id(engine, getattr(args, "account_id", None))
    if not target_id:
        print("❌ 未指定账户且无默认账户")
        return
    try:
        positions = engine.get_positions(target_id)
        if output_json:
            print(json.dumps({"status": "success", "account_id": target_id, "positions": positions}, ensure_ascii=False, indent=2))
        else:
            print(f"=== 账户 '{target_id}' 持仓列表 (共 {len(positions)} 支) ===")
            if not positions:
                print("  (空仓)")
                return
            for p in positions:
                print(f"  - {p['symbol']}: 总股数 {p['qty']} | 可卖 {p['sellable_qty']} | 成本 ¥{p['cost_price']:.2f} | 现价 ¥{p.get('current_price', 0):.2f} | 浮盈 {p.get('pnl_ratio', 0)*100:+.2f}%")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 查询持仓失败: {e}")


def cmd_trade_orders(args, engine: PaperTradingEngine):
    """查询订单"""
    output_json = getattr(args, "json", False)
    target_id = _resolve_account_id(engine, getattr(args, "account_id", None))
    if not target_id:
        print("❌ 未指定账户且无默认账户")
        return
    status = getattr(args, "status", None)
    try:
        orders = engine.list_orders(target_id, status=status)
        if output_json:
            print(json.dumps({"status": "success", "account_id": target_id, "orders": orders}, ensure_ascii=False, indent=2))
        else:
            print(f"=== 账户 '{target_id}' 订单委托 (共 {len(orders)} 条) ===")
            if not orders:
                print("  (无委托记录)")
                return
            for o in orders:
                print(f"  - [{o['status']}] {o['side'].upper()} {o['symbol']} {o['qty']}股 @ ¥{o.get('limit_price') or '市价'} (单号: {o['order_id']})")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 查询订单失败: {e}")


def cmd_trade_trades(args, engine: PaperTradingEngine):
    """查询成交明细"""
    output_json = getattr(args, "json", False)
    target_id = _resolve_account_id(engine, getattr(args, "account_id", None))
    if not target_id:
        print("❌ 未指定账户且无默认账户")
        return
    try:
        trades = engine.list_trades(target_id)
        if output_json:
            print(json.dumps({"status": "success", "account_id": target_id, "trades": trades}, ensure_ascii=False, indent=2))
        else:
            print(f"=== 账户 '{target_id}' 成交明细 (共 {len(trades)} 笔) ===")
            if not trades:
                print("  (暂无成交)")
                return
            for t in trades:
                print(f"  - {t['trade_time']} | {t['side'].upper()} {t['symbol']} {t['qty']}股 @ ¥{t['price']:.2f} (费用: ¥{t.get('fee', 0):.2f})")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 查询成交明细失败: {e}")


def cmd_trade_order_action(args, engine: PaperTradingEngine, side: str):
    """下单买入或卖出 (自适应支持 'buy <account_id> <symbol> <qty>' 或 'buy <symbol> <qty>')"""
    output_json = getattr(args, "json", False)

    arg1 = getattr(args, "arg1", None)
    arg2 = getattr(args, "arg2", None)
    arg3 = getattr(args, "arg3", None)

    target_id = getattr(args, "account_id", None)
    symbol = None
    qty = 0

    if arg3 is not None:
        # 3个参数: <account_id> <symbol> <qty>
        target_id = arg1
        symbol = arg2
        try:
            qty = int(arg3)
        except ValueError:
            print(f"❌ 股数必须为整数: {arg3}")
            return
    else:
        # 2个参数: <symbol> <qty>
        symbol = arg1
        try:
            qty = int(arg2)
        except (ValueError, TypeError):
            # 可能是兼容原本 args.symbol / args.qty
            symbol = getattr(args, "symbol", arg1)
            qty = int(getattr(args, "qty", 0))

    target_id = _resolve_account_id(engine, target_id)
    if not target_id:
        print("❌ 未指定账户且无默认账户。请先创建账户或指定 account_id")
        return

    market = getattr(args, "market", False)
    price = getattr(args, "price", None)
    note = getattr(args, "note", "")

    if not market and price is None:
        print("❌ 限价单必须提供 --price，或者指定 --market 使用市价单")
        return

    req = OrderRequest(
        account_id=target_id,
        symbol=symbol,
        side=side,
        qty=qty,
        order_type="market" if market else "limit",
        limit_price=price,
        note=note,
    )
    try:
        order = engine.place_order(req)
        # 尝试即时撮合一次
        engine.process_orders()
        latest_order = engine.get_order(order["order_id"])
        if output_json:
            print(json.dumps({"status": "success", "order": latest_order}, ensure_ascii=False, indent=2))
        else:
            print(f"✅ {side.upper()} 委托已提交！")
            print(f"  账户:     {target_id}")
            print(f"  单号:     {latest_order['order_id']}")
            print(f"  标的:     {latest_order['symbol']}")
            print(f"  数量:     {latest_order['qty']} 股")
            print(f"  委托类型: {'市价' if market else f'限价 ¥{price:.2f}'}")
            print(f"  状态:     {latest_order['status']} ({latest_order.get('message', '')})")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 下单失败: {e}")


def cmd_trade_cancel(args, engine: PaperTradingEngine):
    """撤单"""
    output_json = getattr(args, "json", False)
    order_id = args.order_id
    try:
        res = engine.cancel_order(order_id)
        if output_json:
            print(json.dumps({"status": "success", "order": res}, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 撤单成功: {order_id} 状态已变更为: {res.get('status')}")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 撤单失败: {e}")


def cmd_trade_cash_adjust(args, engine: PaperTradingEngine, is_add: bool):
    """入金/出金 (自适应支持 'add-cash <account_id> <amount>' 或 'add-cash <amount>')"""
    output_json = getattr(args, "json", False)
    arg1 = getattr(args, "arg1", None)
    arg2 = getattr(args, "arg2", None)

    target_id = getattr(args, "account_id", None)
    amount = 0.0

    if arg2 is not None:
        target_id = arg1
        try:
            amount = float(arg2)
        except ValueError:
            print(f"❌ 金额必须为数值: {arg2}")
            return
    else:
        try:
            amount = float(arg1)
        except (ValueError, TypeError):
            amount = float(getattr(args, "amount", 0.0))

    target_id = _resolve_account_id(engine, target_id)
    if not target_id:
        print("❌ 未指定账户且无默认账户")
        return
    if amount <= 0:
        print("❌ 金额必须大于 0")
        return
    delta = amount if is_add else -amount
    note = getattr(args, "note", "入金" if is_add else "出金")
    try:
        res = engine.adjust_cash(target_id, delta, note=note)
        if output_json:
            print(json.dumps({"status": "success", "account": res}, ensure_ascii=False, indent=2))
        else:
            action_name = "入金" if is_add else "出金"
            print(f"✅ {action_name}成功: 账户 '{target_id}' 可用资金现为: ¥{res['available_cash']:,.2f}")
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        if output_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 操作失败: {e}")


def cmd_trade_service_ctl(args, action: str):
    """模拟盘后台服务控制"""
    output_json = getattr(args, "json", False)
    from core.paper_trading.paper_trading_ctl import (
        healthcheck,
        is_pid_alive,
        read_pid,
        start_service,
        stop_service,
    )

    host = DEFAULT_HOST
    port = DEFAULT_PORT
    pid_path = get_default_pid_path()
    log_path = get_default_log_path()
    db_path = get_default_db_path()

    if action == "status":
        pid = read_pid(pid_path)
        alive = is_pid_alive(pid)
        healthy = healthcheck(host, port)
        data = {
            "status": "running" if (alive and healthy) else "stopped",
            "pid": pid if alive else None,
            "healthy": healthy,
            "host": host,
            "port": port,
            "db_path": str(db_path),
        }
        if output_json:
            print(json.dumps({"status": "success", "data": data}, ensure_ascii=False, indent=2))
        else:
            print("=== 模拟盘服务状态 ===")
            print(f"  运行状态: {'🟢 正在运行' if (alive and healthy) else '⚪ 已停止'}")
            if alive:
                print(f"  进程 PID: {pid}")
            print(f"  服务地址: http://{host}:{port}")
            print(f"  数据存储: {db_path}")

    elif action == "start":
        try:
            pid = start_service(host, port, db_path, log_path, pid_path)
            if output_json:
                print(json.dumps({"status": "success", "pid": pid, "message": "Service started"}, ensure_ascii=False))
            else:
                print(f"✅ 模拟盘后台服务已启动 (PID: {pid})，监听 http://{host}:{port}")
        except Exception as e:
            if output_json:
                print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
            else:
                print(f"❌ 启动失败: {e}")

    elif action == "stop":
        try:
            stop_service(pid_path, host, port)
            if output_json:
                print(json.dumps({"status": "success", "message": "Service stopped"}, ensure_ascii=False))
            else:
                print("✅ 模拟盘后台服务已停止")
        except Exception as e:
            if output_json:
                print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
            else:
                print(f"❌ 停止失败: {e}")


def cmd_trade_dispatch(args, parser):
    """模拟盘子命令统一调度"""
    trade_cmd = getattr(args, "trade_cmd", None)
    if not trade_cmd:
        parser.print_help()
        return

    # 服务管理类子命令
    if trade_cmd in {"status", "start", "stop"}:
        cmd_trade_service_ctl(args, trade_cmd)
        return

    # 数据引擎类操作
    engine = _get_engine()
    if trade_cmd == "balance":
        cmd_trade_balance(args, engine)
    elif trade_cmd in {"accounts", "list-accounts"}:
        cmd_trade_accounts(args, engine)
    elif trade_cmd == "create-account":
        cmd_trade_create(args, engine)
    elif trade_cmd == "reset-account":
        cmd_trade_reset(args, engine)
    elif trade_cmd == "set-default":
        cmd_trade_set_default(args, engine)
    elif trade_cmd == "positions":
        cmd_trade_positions(args, engine)
    elif trade_cmd == "orders":
        cmd_trade_orders(args, engine)
    elif trade_cmd == "trades":
        cmd_trade_trades(args, engine)
    elif trade_cmd == "buy":
        cmd_trade_order_action(args, engine, side="buy")
    elif trade_cmd == "sell":
        cmd_trade_order_action(args, engine, side="sell")
    elif trade_cmd == "cancel":
        cmd_trade_cancel(args, engine)
    elif trade_cmd == "add-cash":
        cmd_trade_cash_adjust(args, engine, is_add=True)
    elif trade_cmd == "deduct-cash":
        cmd_trade_cash_adjust(args, engine, is_add=False)
    else:
        parser.print_help()
