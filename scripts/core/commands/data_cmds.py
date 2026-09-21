# -*- coding: utf-8 -*-
"""
Data & Technicals CLI subcommands.
"""
from __future__ import annotations

import json
from typing import List

from core.config import get_logger

logger = get_logger("core.commands.data")


def cmd_data_quote(args):
    """实时行情 (单股或多股)"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    raw_code = getattr(args, "code", None)
    raw_codes = getattr(args, "codes", None)

    codes: List[str] = []
    if raw_code:
        codes = [raw_code]
    elif raw_codes:
        if isinstance(raw_codes, list):
            codes = raw_codes
        else:
            codes = [c.strip() for c in str(raw_codes).split(",") if c.strip()]

    if not codes:
        msg = {"error": "未提供股票代码"}
        print(json.dumps(msg, ensure_ascii=False) if getattr(args, "json", False) else "错误: 未提供股票代码")
        return

    if len(codes) == 1:
        c = codes[0]
        q = bridge.get_realtime_quote(c)
        if not q:
            err = {"error": f"无法获取 {c} 实时行情"}
            print(json.dumps(err, ensure_ascii=False) if getattr(args, "json", False) else f"错误: 无法获取 {c} 实时行情")
            return
        if getattr(args, "json", False) or getattr(args, "output", "") == "json":
            print(json.dumps(q, ensure_ascii=False, indent=2))
        else:
            print(f"{q.get('name', c)}({q.get('code', c)})")
            print(f"  现价: {q.get('price')}  涨跌: {q.get('change_pct', 0):+.2f}%")
            print(f"  PE: {q.get('pe', 'N/A')}  换手: {q.get('turnover_pct', 'N/A')}%")
            print(f"  日内: {q.get('low', 'N/A')} ~ {q.get('high', 'N/A')}")
    else:
        results = bridge.fetch_batch_snapshot(codes)
        if getattr(args, "json", False) or getattr(args, "output", "") == "json":
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(f"{'代码':<8} {'名称':<10} {'现价':>7} {'涨跌%':>7} {'PE':>6} {'换手%':>6} {'流通市值(亿)':>12} {'外盘比':>6}")
            print("-" * 75)
            for r in results:
                chg_color = "🔴" if r.get("change_pct", 0) > 0 else "🟢"
                print(
                    f"{r.get('code',''):<8} {r.get('name',''):<10} {r.get('price',0):>7.2f} "
                    f"{r.get('change_pct',0):>+6.2f}% {(r.get('pe') if r.get('pe') is not None else 0):>6.1f} {r.get('turnover_pct',0):>6.2f}% "
                    f"{r.get('circulating_market_cap',0):>12.1f} {r.get('o_ratio',0):>5.1f}% {chg_color}"
                )


def cmd_data_technical(args):
    """技术指标分析与缺口检测"""
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all, gap_analysis, second_golden_cross

    bridge = DataBridge()
    count = getattr(args, "count", 120)
    klines = bridge.tencent_kline(args.code, count=count)
    if not klines or len(klines) < 20:
        err = {"error": f"标的 {args.code} K线数据不足 ({len(klines) if klines else 0}根)"}
        print(json.dumps(err, ensure_ascii=False) if getattr(args, "json", False) else err["error"])
        return

    tech = calc_all(klines)
    gaps = gap_analysis(klines)
    golden = second_golden_cross(klines)
    res = {"code": args.code, "technical": tech, "gaps": gaps, "second_golden_cross": golden}

    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        l = tech.get("latest", {})
        print(f"=== [{args.code}] 经典技术指标 (K线 {len(klines)} 根) ===")
        print(f"收盘价: {l.get('close')}")
        print(f"MA5/10/20/60: {l.get('ma5', 'N/A')}/{l.get('ma10', 'N/A')}/{l.get('ma20', 'N/A')}/{l.get('ma60', 'N/A')}")
        print(f"MACD: DIF={l.get('dif', 'N/A')} | DEA={l.get('dea', 'N/A')} | Bar={l.get('macd_bar', 'N/A')}")
        print(f"KDJ: K={l.get('kdj_k', 'N/A')} | D={l.get('kdj_d', 'N/A')} | J={l.get('kdj_j', 'N/A')}")
        print(f"RSI: {l.get('rsi', 'N/A')} | ATR: {l.get('atr', 'N/A')}")
        print(f"BOLL通道: {l.get('boll_lower', 'N/A')} ~ {l.get('boll_mid', 'N/A')} ~ {l.get('boll_upper', 'N/A')}")
        if gaps.get("gaps"):
            print(f"跳空缺口: 近10日共 {gaps.get('count')} 次, 连续同向 {gaps.get('consecutive_same')} 次")
        print(f"二次金叉检测: {golden.get('verdict')} | 理由: {golden.get('reason', '无')}")


def cmd_batch(args):
    """批量行情快照"""
    args.codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    cmd_data_quote(args)


def cmd_events(args):
    """个股重要事件与公告"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    name = getattr(args, "name", "")
    result = bridge.get_stock_events(args.code, name)
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 个股事件 ===")
        if result:
            print(result.get("text", str(result))[:2000])
        else:
            print("  暂无事件数据（需配置 proxy-patch 或数据源插件）")


def cmd_cyq(args):
    """筹码分布 (CYQ)"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    result = bridge.get_cyq(args.code)
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print(f"=== [{args.code}] 筹码分布 ===")
        if result:
            print(f"  获利比例: {result.get('profit_ratio', 'N/A')}")
            print(f"  平均成本: {result.get('avg_cost', 'N/A')}")
            print(f"  90%集中度: {result.get('concentration_90', 'N/A')}")
            print(f"  70%集中度: {result.get('concentration_70', 'N/A')}")
            conc = result.get("concentration_90", 0)
            if conc and conc < 0.10:
                print("  判断: 高度集中，主力控盘 ⭐")
            elif conc and conc < 0.13:
                print("  判断: 筹码相对集中")
            elif conc and conc < 0.15:
                print("  判断: 中性")
            else:
                print("  判断: 筹码相对发散")
        else:
            print("  暂无筹码数据（需数据源支持）")


def cmd_balance(args):
    """代理服务与数据源余额检查"""
    from core.data.data_bridge import DataBridge

    bridge = DataBridge()
    result = bridge.check_proxy_balance()
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result or {}, ensure_ascii=False, indent=2))
    else:
        print("代理积分与服务状态:")
        print(f"  {result or '状态正常 / 零积分直连运行中'}")


def cmd_market(args):
    """五维大盘健康度评估"""
    from core.models.market_assessor import MarketAssessor

    assessor = MarketAssessor()
    result = assessor.assess_all()
    if getattr(args, "json", False) or getattr(args, "output", "") == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"╔══════════════════════════════════════════════════╗")
        print(f"║  五维大盘健康度综合评估                          ║")
        print(f"╚══════════════════════════════════════════════════╝")
        print(f"  总分: {result['total_score']}/{result['max_score']}")
        print(f"  市场模式: {result['mode']} | 建议仓位上限: {result['max_position']}")
        for dim, info in result.get("dimensions", {}).items():
            bar = "█" * info["score"] + "░" * (info["max"] - info["score"])
            print(f"  {dim:<12} [{bar}] {info['score']}/{info['max']}")
            print(f"             {info.get('reason', '')}")
        print("\n  主要指数:")
        for k, v in result.get("index_data", {}).items():
            chg = v.get("change_pct", 0)
            arrow = "↑" if chg > 0 else "↓"
            print(f"  {v.get('name', k):<8} {v.get('price', 'N/A')} {arrow} {chg:+.2f}%")


def cmd_data_sync(args):
    """行情与K线数据同步命令"""
    if getattr(args, 'daemon', False):
        cmd_data_daemon(args)
        return

    from core.data.sync_engine import DataSyncEngine

    engine = DataSyncEngine()

    raw_code = getattr(args, 'code', None)
    raw_codes = getattr(args, 'codes', None)
    codes = []
    if raw_code:
        codes.append(raw_code)
    elif raw_codes:
        if isinstance(raw_codes, list):
            codes = raw_codes
        else:
            codes = [c.strip() for c in str(raw_codes).split(',') if c.strip()]

    pool = getattr(args, 'pool', None)
    include_indices = getattr(args, 'indices', False)
    all_pool = getattr(args, 'all', False)

    symbols = engine.resolve_symbols(
        codes=codes, pool=pool, include_indices=include_indices, all_pool=all_pool
    )

    is_json = getattr(args, 'json', False) or getattr(args, 'output', '') == 'json'

    # 1. 完整性校验模式 (--check)
    if getattr(args, 'check', False):
        res = engine.audit_integrity(symbols, start_date=getattr(args, 'start', None), end_date=getattr(args, 'end', None))
        if is_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"=== 行情数据完整性校验报告 (共 {len(symbols)} 只标的) ===")
            print(f"{'代码':<10} {'状态':<8} {'在库条数':<8} {'时间范围':<23} {'缺漏数':<8} {'停牌数':<8} {'坏点数':<8}")
            print('-' * 82)
            for r in res:
                st_icon = '🟢' if r['status'] == 'healthy' else ('⚪' if r['status'] == 'empty' else '🔴')
                date_range = f"{r.get('min_date', '')} ~ {r.get('max_date', '')}" if r.get('min_date') else '无'
                print(f"{r['symbol']:<10} {st_icon} {r['status']:<6} {r['row_count']:<8} {date_range:<23} {r.get('missing_count', 0):<8} {r.get('suspended_count', 0):<8} {r.get('bad_count', 0):<8}")
                if r.get('suspended_days'):
                    print(f"   ├─ 合规停牌切片: {', '.join(r['suspended_days'])}")
                if r.get('missing_days'):
                    print(f"   └─ 缺漏日期切片: {', '.join(r['missing_days'])}")
        return

    # 2. 缺漏回补修复模式 (--repair)
    if getattr(args, 'repair', False):
        res = engine.repair_gaps(symbols)
        if is_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"=== 缺漏数据修复回补报告 (共 {len(symbols)} 只标的) ===")
            for r in res:
                icon = '✅' if r['repaired'] else 'ℹ️'
                print(f"{icon} [{r['symbol']}] {r['message']}")
        return

    # 3. 当日快照模式 (--today)
    if getattr(args, 'today', False):
        res = engine.sync_today_snapshot(symbols)
        if is_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"=== 当日行情快照同步 ===")
            st = res.get("status", "")
            if st == "skipped":
                print(f"ℹ️ {res.get('message', '非交易日跳过')}")
            else:
                settled_str = "已定盘" if res.get("is_settled") else f"未定盘 ({res.get('phase_label', '盘中')})"
                print(f"日期: {res.get('date')} | 更新条数: {res.get('updated_count')}/{res.get('total_requested')} | 状态: {settled_str}")
        return

    # 4. 常规增量/全量/实时同步
    mode = getattr(args, 'mode', 'incremental') or 'incremental'
    days = getattr(args, 'days', None)
    start_date = getattr(args, 'start', None)
    end_date = getattr(args, 'end', None)
    count = getattr(args, 'count', 250)
    if days and days > 0:
        count = days

    workers = getattr(args, 'workers', 4) or 4
    res = engine.sync_batch(
        symbols, mode=mode, count=count, start_date=start_date, end_date=end_date, max_workers=workers
    )

    if is_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        phase_label = res.get('phase_label', '实时时段')
        settled_desc = "已定盘" if res.get('is_settled') else f"未定盘 ({phase_label})"
        print(f"=== A-Stock 数据同步完成 ({mode} · {settled_desc}) ===")
        print(f"耗时: {res['elapsed_seconds']}s | 并发: {res.get('workers', workers)} | 成功: {res['success_count']}/{res['total_requested']} | 失败: {res['failed_count']} | 快照时间: {res.get('snapshot_time', '')}")
        print(f"{'代码':<10} {'状态':<10} {'时段标记':<16} {'定盘状态':<10} {'本次拉取':<8} {'在库总数':<8} {'最新日期':<12}")
        print('-' * 80)
        has_unsettled = False
        for d in res['details']:
            st = d.get('status', '')
            icon = '✅' if st in ['success', 'up_to_date'] else '❌'
            is_set = d.get('is_settled', True)
            set_str = '🟢 已定盘' if is_set else '⏳ 未定盘'
            phase_disp = d.get('phase_label') or d.get('sync_phase') or '-'
            if not is_set:
                has_unsettled = True
            print(f"{d['symbol']:<10} {icon} {st:<8} {phase_disp:<16} {set_str:<10} {d.get('synced_count', 0):<8} {d.get('total_count', 0):<8} {d.get('last_date', ''):<12}")
            if st in ['failed', 'error'] and d.get('error'):
                print(f"   └─ 失败原因: {d.get('error')}")

        if has_unsettled:
            print('-' * 80)
            print("💡 提示: 本次同步包含未定盘实时切片（如盘中/午间行情），供盘中/午后策略评估使用；盘后 15:35 定盘后可重新增量同步以固化最终收盘数据。")



def cmd_data_daemon(args):
    """本地行情定时同步守护进程命令"""
    from core.data.sync_daemon import DataSyncDaemon

    pool = getattr(args, "pool", None)
    pools = [pool] if pool and pool != "all" else None
    interval = getattr(args, "interval", 60) or 60
    workers = getattr(args, "workers", 4) or 4

    daemon = DataSyncDaemon(pools=pools, check_interval=interval, max_workers=workers)
    is_json = getattr(args, "json", False) or getattr(args, "output", "") == "json"

    if getattr(args, "once", False):
        res = daemon.run_once()
        if is_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            st = res.get("status")
            icon = "✅" if st in ["executed", "up_to_date"] else ("ℹ️" if st == "skipped" else "⏳")
            print(f"{icon} [定时守护单次检测] 状态: {st} | 消息: {res.get('message', '执行完毕')}")
            if res.get("executed_pools"):
                print(f"   └─ 已同步标的池: {', '.join(res['executed_pools'])}")
    else:
        if not is_json:
            print(f"🚀 正在启动 A-Stock 数据同步守护进程 (轮询间隔: {interval}s, 并发: {workers})...")
            print("💡 按 Ctrl+C 可安全优雅停机。日志沉淀在: log/sync_daemon.log")
        daemon.run_forever()
