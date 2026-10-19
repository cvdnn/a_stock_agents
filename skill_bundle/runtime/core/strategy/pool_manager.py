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
from typing import Any, Dict, List, Optional, Union

# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent.parent
SCRIPTS_DIR = ROOT / "skill_bundle" / "runtime"
for p in [ROOT, SCRIPTS_DIR, SCRIPTS_DIR / "core", SCRIPT_DIR]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from core.config import PROJECT_ROOT, OUTPUT_POOLS_DIR
POOLS_BASE = OUTPUT_POOLS_DIR

SELECTED_PATH = os.path.join(str(POOLS_BASE), "selected_pool.csv")
WATCH_PATH = os.path.join(str(POOLS_BASE), "watch_pool.csv")


from core.strategy.pool_schema import (
    SELECTED_FIELDS,
    WATCH_FIELDS,
    is_blocked,
    _is_blocked,
    ensure_pool_csv as _ensure_file,
    read_pool_csv as _read_csv,
    write_pool_csv as _write_csv,
)


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


class PoolManager:
    """股票池管理器，统一管理自选股池 (selected)、关注股池 (watch) 与持仓池 (positions/holding)。"""

    def __init__(self, pools_dir: Optional[Union[str, Path]] = None) -> None:
        self.pools_dir = Path(pools_dir) if pools_dir else Path(POOLS_BASE)
        self.selected_path = self.pools_dir / "selected_pool.csv"
        self.watch_path = self.pools_dir / "watch_pool.csv"
        self.positions_path = self.pools_dir / "positions.csv"

    def get_pool(self, pool_type: str = "holding") -> List[Dict[str, Any]]:
        """获取指定类型的股票池标的列表。"""
        pt = str(pool_type or "holding").lower().strip()
        if pt in ("holding", "holdings", "positions", "持仓", "持仓池"):
            if self.positions_path.exists():
                return _read_csv(self.positions_path)
            try:
                from core.strategy.position_manager import get_open_positions
                return get_open_positions(enrich_quote=False)
            except Exception:
                return _read_csv(self.positions_path)
        elif pt in ("selected", "watchlist", "custom", "自选", "自选股", "自选池"):
            return _read_csv(self.selected_path)
        elif pt in ("watch", "focus", "关注", "关注股", "关注池"):
            return _read_csv(self.watch_path)
        else:
            target = self.pools_dir / f"{pt}_pool.csv"
            if target.exists():
                return _read_csv(target)
            return []

    def get_all_pools(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取全量股票池概览。"""
        return {
            "selected": self.get_pool("selected"),
            "watch": self.get_pool("watch"),
            "holding": self.get_pool("holding"),
        }

    def add_stock(self, pool_type: str, stock_data: Dict[str, Any]) -> bool:
        """添加股票到自选或关注池。"""
        pt = str(pool_type).lower().strip()
        if pt in ("selected", "custom"):
            path = self.selected_path
            fields = SELECTED_FIELDS
        elif pt in ("watch", "focus"):
            path = self.watch_path
            fields = WATCH_FIELDS
        else:
            return False
        _ensure_file(path, fields)
        rows = _read_csv(path)
        code = str(stock_data.get("code", "")).strip()
        if any(r.get("code") == code for r in rows):
            return False
        rows.append(stock_data)
        _write_csv(path, fields, rows)
        return True

    def remove_stock(self, pool_type: str, code: str) -> bool:
        """从自选或关注池中移除标的。"""
        pt = str(pool_type).lower().strip()
        path = self.selected_path if pt in ("selected", "custom") else self.watch_path
        if not path.exists():
            return False
        fields = SELECTED_FIELDS if pt in ("selected", "custom") else WATCH_FIELDS
        rows = _read_csv(path)
        code_str = str(code).strip()
        new_rows = [r for r in rows if str(r.get("code", "")).strip() != code_str]
        if len(new_rows) == len(rows):
            return False
        _write_csv(path, fields, new_rows)
        return True

    def audit_pools(
        self,
        fix: bool = False,
        pool_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        五步真实 MA 股池审查与失效标的清洗 (G3 修复 & C3/C6 标准)。
        1. 空股池即刻终止 (Fail-Closed)，拒绝虚构臆测并提示登记格式；
        2. 拉取最新行情/日K，重算真实 MA5/MA10/MA20/MA60 水位；
        3. 穿透检测止损跌破 (breached_stops)；
        4. 穿透检测均线严重失真 (>15%) 与失效标的 (stale_records)；
        5. 输出结构化审查报告与修复建议 (若 fix=True 执行安全自动清洗)。
        """
        try:
            from core.data.evidence import build_evidence_meta
        except ImportError:
            build_evidence_meta = None

        try:
            from core.data.data_bridge import DataBridge
            bridge = DataBridge()
        except Exception:
            bridge = None

        if pool_type:
            pools = {pool_type: self.get_pool(pool_type)}
        else:
            pools = self.get_all_pools()

        all_stocks = []
        for p_name, rows in pools.items():
            for r in rows:
                row_copy = dict(r)
                row_copy["_pool"] = p_name
                all_stocks.append(row_copy)

        # ── 第一步：空股池即刻终止判定 (Fail-Closed) ──
        if not all_stocks:
            evidence = (
                build_evidence_meta(quote_source="L0:local_pools", watermark_ready=True)
                if build_evidence_meta
                else {}
            )
            return {
                "status": "empty_pool",
                "fix": fix,
                "total_pools": len(pools),
                "total_stocks": 0,
                "pools": {k: len(v) for k, v in pools.items()},
                "pools_summary": {k: len(v) for k, v in pools.items()},
                "healthy_count": 0,
                "stale_records": [],
                "breached_stops": [],
                "ma_levels": {},
                "recommendations": ["未登记任何标的，请先登记股票池后再执行审查。"],
                "message": "⚠️ 当前检测到股池为空（持仓池/自选池/关注池无记录），未继续分析。请先按规范登记标的。",
                "registration_guide": {
                    "holding_format": "持仓股登记：股票:股数@成本价（例如持仓股：000001:1000@12.50）",
                    "watch_format": "关注/自选股登记：直接输入股票代码或名称（例如：000001、600519）",
                },
                "evidence_meta": evidence,
            }

        # ── 第二步 ~ 第四步：真实 MA 重算、止损与失效检测 ──
        stale_records = []
        breached_stops = []
        ma_levels = {}
        cleaned_count = 0
        healthy_count = 0

        for s in all_stocks:
            code = str(s.get("code", "")).strip()
            name = str(s.get("name", code)).strip()
            pool_name = s.get("_pool", "unknown")
            if not code:
                continue

            # 4.1 检查不可交易板块
            if is_blocked(code):
                stale_records.append({
                    "code": code,
                    "name": name,
                    "pool": pool_name,
                    "reason": "不可交易板块标的（创业板/科创板/北交所/退市）",
                })
                continue

            # 获取真实行情与日 K
            klines = []
            quote = {}
            if bridge:
                try:
                    quote = bridge.get_realtime_quote(code) or {}
                    klines = bridge.tencent_kline(code, count=60) or []
                except Exception:
                    pass

            curr_price = float(quote.get("price", 0.0) or (klines[-1][2] if klines else 0.0))

            if not klines or len(klines) < 5 or curr_price <= 0:
                stale_records.append({
                    "code": code,
                    "name": name,
                    "pool": pool_name,
                    "reason": "行情数据缺失或长期停牌",
                })
                continue

            closes = [float(k[2]) for k in klines]
            ma5 = round(sum(closes[-5:]) / 5.0, 2)
            ma10 = round(sum(closes[-10:]) / min(len(closes), 10), 2)
            ma20 = round(sum(closes[-20:]) / min(len(closes), 20), 2)
            ma60 = round(sum(closes[-60:]) / len(closes), 2)

            ma_levels[code] = {
                "name": name,
                "price": curr_price,
                "ma5": ma5,
                "ma10": ma10,
                "ma20": ma20,
                "ma60": ma60,
            }

            # 3. 检测止损跌破
            stop_val = None
            if s.get("stop_loss"):
                try:
                    stop_val = float(s["stop_loss"])
                except (ValueError, TypeError):
                    stop_val = None
            elif s.get("buy_price"):
                try:
                    bp = float(s["buy_price"])
                    stop_val = round(bp * 0.92, 2)  # -8% 绝杀线
                except (ValueError, TypeError):
                    stop_val = None

            if stop_val and stop_val > 0 and curr_price < stop_val:
                loss_pct = round((curr_price - stop_val) / stop_val * 100.0, 2)
                breached_stops.append({
                    "code": code,
                    "name": name,
                    "pool": pool_name,
                    "price": curr_price,
                    "stop_loss": stop_val,
                    "deviation_pct": loss_pct,
                    "action_advice": "现价已跌破关键止损线，触及实战风控绝杀位，建议无条件止损出局",
                })

            # 4. 检测均线偏离度 (>15%)
            bias_ma20 = (curr_price - ma20) / ma20 if ma20 > 0 else 0.0
            if abs(bias_ma20) > 0.15:
                stale_records.append({
                    "code": code,
                    "name": name,
                    "pool": pool_name,
                    "price": curr_price,
                    "ma20": ma20,
                    "bias_pct": round(bias_ma20 * 100.0, 2),
                    "reason": f"现价偏离MA20达 {bias_ma20*100:+.1f}% (>15%)，价格失真或高位加速透支",
                })
            else:
                if not (stop_val and stop_val > 0 and curr_price < stop_val):
                    healthy_count += 1

        # ── 第五步：若 fix=True 执行安全清洗 ──
        if fix:
            to_remove = set()
            for item in stale_records:
                to_remove.add((item["pool"], item["code"]))
            for item in breached_stops:
                to_remove.add((item["pool"], item["code"]))

            for p_name, code in to_remove:
                if p_name in ("selected", "watch"):
                    if self.remove_stock(p_name, code):
                        cleaned_count += 1

        recs = []
        if breached_stops:
            recs.append(f"发现 {len(breached_stops)} 只标的跌破止损位，请优先处理风控防守")
        if stale_records:
            recs.append(f"发现 {len(stale_records)} 只标的偏离均线>15%或数据失效，建议清洗更新")
        if not breached_stops and not stale_records:
            recs.append("全量股票池运行稳健，未检测到破位或严重均线偏离标的")

        evidence = (
            build_evidence_meta(quote_source="L1:tencent_kline", watermark_ready=True)
            if build_evidence_meta
            else {}
        )

        return {
            "status": "success",
            "fix": fix,
            "cleaned_count": cleaned_count,
            "total_pools": len(pools),
            "total_stocks": len(all_stocks),
            "healthy_count": healthy_count,
            "pools": {k: len(v) for k, v in pools.items()},
            "pools_summary": {k: len(v) for k, v in pools.items()},
            "breached_stops": breached_stops,
            "stale_records": stale_records,
            "ma_levels": ma_levels,
            "recommendations": recs,
            "evidence_meta": evidence,
        }

def cmd_list(args):
    """列出自选股或关注股"""
    if getattr(args, "json", False):
        import json
        pm = PoolManager()
        pool_arg = getattr(args, "pool", None)
        if pool_arg:
            stocks = pm.get_pool(pool_arg)
            res = {"status": "success", "pool": pool_arg, "count": len(stocks), "stocks": stocks}
        else:
            all_pools = pm.get_all_pools()
            total = sum(len(v) for v in all_pools.values())
            res = {"status": "success", "count": total, "pools": all_pools}
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
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
