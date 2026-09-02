#!/usr/bin/env python3
"""
股票池管理器 — 自选股池 + 关注股池 CRUD

用法:
  pool_manager.py list [--pool selected|watch]
  pool_manager.py add --pool selected|watch --code CODE --name NAME --reason "理由" --sector "板块"
  pool_manager.py remove --pool selected|watch --code CODE
  pool_manager.py upgrade --code CODE [--reason "升级理由"]
  pool_manager.py check-watch
"""
import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core"))

from core.config import OUTPUT_POOLS_DIR
POOLS_BASE = str(OUTPUT_POOLS_DIR)

SELECTED_PATH = os.path.join(POOLS_BASE, "selected_pool.csv")
WATCH_PATH = os.path.join(POOLS_BASE, "watch_pool.csv")


# ── CSV 列定义 ──
SELECTED_FIELDS = ["code","name","added_date","rating","reason","sector","pe","change_pct",
                     "ma_status","entry_trigger","stop_loss","take_profit","risk_level","market_context","notes",
                     "ta_decision","ta_analysis_date","ta_report_path","consensus_rating"]
WATCH_FIELDS = ["code","name","added_date","rating","reason","sector","pe","change_pct","fund_flow","entry_condition","market_context",
                "ta_analysis_date"]


def _ensure_file(path, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(fields)


def _is_blocked(code: str) -> bool:
    """判断是否为不可交易的股票（科创板/创业板/北交所等）"""
    return code.startswith(("688", "689", "30", "8", "4"))


def _read_csv(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _migrate_csv(path, fields):
    """自动迁移旧版 CSV：补全新列（若缺失）。"""
    if not os.path.exists(path):
        _ensure_file(path, fields)
        return
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        rows = list(reader)
    if existing_fields == fields:
        return  # 已是最新 schema
    # 补充缺失的列
    missing = [f for f in fields if f not in existing_fields]
    if not missing:
        return
    for row in rows:
        for f in missing:
            row[f] = ""
    new_fields = existing_fields + missing
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  📋 CSV schema 升级: {path.name if hasattr(path, 'name') else os.path.basename(path)} → 新增 {missing}", file=sys.stderr)


def _write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def cmd_list(args):
    """列出自选股或关注股"""
    if args.pool in ["selected", None]:
        rows = _read_csv(SELECTED_PATH)
        print(f"\n📋 自选股池 ({len(rows)} 只)")
        print(f"{'评级':>4} {'代码':>8} {'名称':<8} {'PE':>6} {'涨幅':>7} {'均线':<8} {'风险':>4} {'止损':>8} {'触发条件':<20}")
        print("-" * 90)
        for r in rows:
            icon = {"A":"⭐","B":"▸","C":"○","D":"✗"}.get(r.get('rating','?'), "?")
            print(f"{icon}{r.get('rating','?'):<2} {r.get('code','?'):>8} {r.get('name','?'):<8} "
                  f"{r.get('pe','?'):>6} {r.get('change_pct','?'):>7} {r.get('ma_status','?'):<8} "
                  f"{r.get('risk_level','?'):>4} {r.get('stop_loss','?'):>8} {r.get('entry_trigger','?'):<20}")

    if args.pool in ["watch", None]:
        rows = _read_csv(WATCH_PATH)
        print(f"\n👀 关注股池 ({len(rows)} 只)")
        print(f"{'评级':>4} {'代码':>8} {'名称':<8} {'PE':>6} {'涨幅':>7} {'主力':>12} {'板块':<10} {'入场条件':<20}")
        print("-" * 90)
        for r in rows:
            rating = r.get('rating','?')
            # 评级颜色标记
            icon = {"A":"⭐","B":"▸","C":"○","D":"✗"}.get(rating, "?")
            print(f"{icon}{rating:<2} {r.get('code','?'):>8} {r.get('name','?'):<8} "
                  f"{r.get('pe','?'):>6} {r.get('change_pct','?'):>7} {r.get('fund_flow','?'):>12} "
                  f"{r.get('sector','?'):<10} {r.get('entry_condition','?'):<20}")


def cmd_add(args):
    """添加股票到指定池"""
    # 科创板/创业板/北交所检查
    if _is_blocked(args.code):
        print(f"✗ {args.code} 为不可交易板块股票（创业板/科创板/北交所），已拒绝添加")
        return
    if args.pool == "selected":
        _ensure_file(SELECTED_PATH, SELECTED_FIELDS)
        rows = _read_csv(SELECTED_PATH)
        # 检查是否已存在
        if any(r["code"] == args.code for r in rows):
            print(f"⚠ {args.code} 已在自选股池中")
            return
        rows.append({
            "code": args.code,
            "name": args.name,
            "added_date": datetime.now().strftime("%Y-%m-%d"),
            "rating": args.rating or "C",
            "reason": args.reason,
            "sector": args.sector,
            "pe": str(args.pe) if args.pe else "",
            "change_pct": args.change_pct or "",
            "ma_status": args.ma_status or "",
            "entry_trigger": args.entry_trigger or "",
            "stop_loss": str(args.stop_loss) if args.stop_loss else "",
            "take_profit": str(args.take_profit) if args.take_profit else "",
            "risk_level": args.risk_level or "",
            "market_context": args.market_context or "",
            "notes": args.notes or "",
        })
        _write_csv(SELECTED_PATH, rows, SELECTED_FIELDS)
        print(f"✓ {args.code}({args.name}) 已加入自选股池")

    elif args.pool == "watch":
        _ensure_file(WATCH_PATH, WATCH_FIELDS)
        rows = _read_csv(WATCH_PATH)
        if any(r["code"] == args.code for r in rows):
            print(f"⚠ {args.code} 已在关注股池中")
            return
        rows.append({
            "code": args.code,
            "name": args.name,
            "added_date": datetime.now().strftime("%Y-%m-%d"),
            "rating": args.rating or "C",
            "reason": args.reason,
            "sector": args.sector,
            "pe": str(args.pe) if args.pe else "",
            "change_pct": args.change_pct or "",
            "fund_flow": args.fund_flow or "",
            "entry_condition": args.entry_condition or "待评估",
            "market_context": args.market_context or "",
        })
        _write_csv(WATCH_PATH, rows, WATCH_FIELDS)
        print(f"✓ {args.code}({args.name}) 已加入关注股池")


def cmd_remove(args):
    if args.pool == "selected":
        rows = _read_csv(SELECTED_PATH)
        new_rows = [r for r in rows if r["code"] != args.code]
        if len(new_rows) == len(rows):
            print(f"⚠ 未在自选股池中找到 {args.code}")
            return
        _write_csv(SELECTED_PATH, new_rows, SELECTED_FIELDS)
        print(f"✓ {args.code} 已从自选股池移除")
    elif args.pool == "watch":
        rows = _read_csv(WATCH_PATH)
        new_rows = [r for r in rows if r["code"] != args.code]
        if len(new_rows) == len(rows):
            print(f"⚠ 未在关注股池中找到 {args.code}")
            return
        _write_csv(WATCH_PATH, new_rows, WATCH_FIELDS)
        print(f"✓ {args.code} 已从关注股池移除")


def cmd_upgrade(args):
    """关注股 → 自选股"""
    watch_rows = _read_csv(WATCH_PATH)
    target = None
    for r in watch_rows:
        if r["code"] == args.code:
            target = r
            break
    if not target:
        print(f"⚠ 未在关注股池中找到 {args.code}")
        return

    # 加入自选股池
    _ensure_file(SELECTED_PATH, SELECTED_FIELDS)
    sel_rows = _read_csv(SELECTED_PATH)
    if any(r["code"] == args.code for r in sel_rows):
        print(f"⚠ {args.code} 已在自选股池中，跳过")
    else:
        sel_rows.append({
            "code": target["code"],
            "name": target["name"],
            "added_date": datetime.now().strftime("%Y-%m-%d"),
            "reason": args.reason or target["reason"],
            "sector": target["sector"],
            "rating": "B",
            "entry_price": "",
            "position": "",
        })
        _write_csv(SELECTED_PATH, sel_rows, SELECTED_FIELDS)

    # 从关注股池移除
    watch_rows = [r for r in watch_rows if r["code"] != args.code]
    _write_csv(WATCH_PATH, watch_rows, WATCH_FIELDS)
    print(f"✓ {args.code}({target['name']}) 已从关注股 → 自选股")


def cmd_check_watch(args):
    """检查关注股是否满足升级条件"""
    watch_rows = _read_csv(WATCH_PATH)
    if not watch_rows:
        print("关注股池为空")
        return

    print("\n🔍 关注股升级条件检查")
    print("=" * 60)

    for r in watch_rows:
        code = r["code"]
        name = r["name"]
        print(f"\n{code} {name} — 等待: {r.get('wait_condition','?')}")
        print("  ⏳ 条件未验证（需调用 fetch_technical.py 逐只确认）")
        print("  建议执行: pool_manager.py check-watch 前先拉取技术指标")


def main():
    parser = argparse.ArgumentParser(description="股票池管理器")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="列出自选股/关注股")
    p_list.add_argument("--pool", choices=["selected", "watch"], default=None)

    # add
    p_add = sub.add_parser("add", help="添加股票到池")
    p_add.add_argument("--pool", required=True, choices=["selected", "watch"])
    p_add.add_argument("--code", required=True)
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--reason", default="")
    p_add.add_argument("--sector", default="")
    p_add.add_argument("--rating", choices=["A", "B", "C"])
    p_add.add_argument("--wait-condition")
    # 关注股扩展字段
    p_add.add_argument("--pe", type=float)
    p_add.add_argument("--change-pct")
    p_add.add_argument("--fund-flow")
    p_add.add_argument("--entry-condition")
    p_add.add_argument("--market-context")
    # 自选股扩展字段
    p_add.add_argument("--ma-status", choices=["多头","震荡","空头"])
    p_add.add_argument("--entry-trigger")
    p_add.add_argument("--stop-loss", type=float)
    p_add.add_argument("--take-profit", type=float)
    p_add.add_argument("--risk-level", choices=["低","中","高"])
    p_add.add_argument("--notes")

    # remove
    p_rm = sub.add_parser("remove", help="移除股票")
    p_rm.add_argument("--pool", required=True, choices=["selected", "watch"])
    p_rm.add_argument("--code", required=True)

    # upgrade
    p_up = sub.add_parser("upgrade", help="关注股→自选股")
    p_up.add_argument("--code", required=True)
    p_up.add_argument("--reason")

    # check-watch
    sub.add_parser("check-watch", help="检查关注股升级条件")

    args = parser.parse_args()

    # CSV schema 自动迁移（每次使用前检查）
    _migrate_csv(SELECTED_PATH, SELECTED_FIELDS)
    _migrate_csv(WATCH_PATH, WATCH_FIELDS)

    if args.command == "list":
        cmd_list(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "upgrade":
        cmd_upgrade(args)
    elif args.command == "check-watch":
        cmd_check_watch(args)


if __name__ == "__main__":
    main()