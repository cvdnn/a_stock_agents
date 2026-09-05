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
            print(f"{'代码':<8} {'名称':<10} {'现价':>7} {'涨跌%':>7} {'PE':>6} {'换手%':>6} {'市值(亿)':>10} {'外盘比':>6}")
            print("-" * 75)
            for r in results:
                chg_color = "🔴" if r.get("change_pct", 0) > 0 else "🟢"
                print(
                    f"{r.get('code',''):<8} {r.get('name',''):<10} {r.get('price',0):>7.2f} "
                    f"{r.get('change_pct',0):>+6.2f}% {r.get('pe',0):>6.1f} {r.get('turnover_pct',0):>6.2f}% "
                    f"{r.get('market_cap',0):>10.1f} {r.get('o_ratio',0):>5.1f}% {chg_color}"
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
