#!/usr/bin/env python3
"""
A股预测数据采集 — 为DeepSeek-V4-Flash提供结构化输入数据

用法:
  predictor.py --code 600519              # 单只个股预测数据
  predictor.py --code 600519 --full       # 含历史K线和筹码
  predictor.py --pool selected            # 自选股批量
  predictor.py --pool watch               # 关注股批量
  predictor.py --positions                # 持仓批量
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime

try:
    from core.config import OUTPUT_POOLS_DIR
    POOLS_BASE = str(OUTPUT_POOLS_DIR)
except Exception:
    SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
    output_pools = os.path.join(PROJECT_ROOT, "output", "pools")
    POOLS_BASE = output_pools if os.path.exists(output_pools) else os.path.join(SKILL_DIR, "data")

A_DATA_DIR = "./.AI-Platform/skills/stocks/a-share-data/scripts"
VENV_PY = "python3"



def _run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except:
        return ""


def get_quote(code):
    out = _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_patched.py"),
                "fetch_realtime.py", "--quote", code, "--json"])
    if out:
        try:
            return json.loads(out)
        except:
            pass
    return {}


def get_technical(code):
    """获取技术指标 — 使用fetch_history脚本更快"""
    out = _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_patched.py"),
                "fetch_history.py", "--kline", code,
                "--start", "20260301", "--end", "20260622",
                "--freq", "d", "--json"], timeout=20)
    if out:
        try:
            data = json.loads(out)
            if data and len(data) > 10:
                closes = [d["close"] for d in data if d.get("close")]
                if len(closes) >= 10:
                    cur = closes[-1]
                    ma10 = sum(closes[-10:])/10
                    ma20 = sum(closes[-20:])/20 if len(closes)>=20 else None
                    ma60 = sum(closes[-60:])/60 if len(closes)>=60 else None
                    # 简化计算
                    pct1 = (cur/closes[-2]-1)*100 if len(closes)>=2 else 0
                    pct5 = (cur/closes[-6]-1)*100 if len(closes)>=6 else 0
                    pct20 = (cur/closes[-21]-1)*100 if len(closes)>=21 else 0
                    return {
                        "close": round(cur,2), "ma10": round(ma10,2),
                        "ma20": round(ma20,2) if ma20 else None,
                        "ma60": round(ma60,2) if ma60 else None,
                        "pct1": round(pct1,2), "pct5": round(pct5,2),
                        "pct20": round(pct20,2),
                        "bias_ma20": round((cur/ma20-1)*100,2) if ma20 else None,
                        "bias_ma60": round((cur/ma60-1)*100,2) if ma60 else None,
                        "data_points": len(closes),
                    }
        except:
            pass
    return {"error": "获取失败"}


def get_fund_flow(code):
    """获取资金流向"""
    out = _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_patched.py"),
                "fetch_realtime.py", "--fund-flow", code, "--days", "5", "--json"], timeout=25)
    if out:
        try:
            data = json.loads(out)
            if isinstance(data, list) and len(data) > 0:
                total_main = sum(d.get("主力净流入-净额", 0) for d in data)
                return {"main_5d": round(total_main / 10000, 0)}
        except:
            pass
    return {}


def get_sector(code):
    """获取行业"""
    out = _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_patched.py"),
                "fetch_sector_info.py", "--no-concepts", "--json", code], timeout=15)
    if out:
        try:
            return json.loads(out)
        except:
            pass
    return {}


def predict_single(code: str, name: str = "") -> dict:
    """采集单只股票预测所需数据"""
    print(f"  [获取 {code} 行情...]", file=sys.stderr, flush=True)
    quote = get_quote(code)
    print(f"  [获取 {code} 技术指标...]", file=sys.stderr, flush=True)
    tech = get_technical(code)
    print(f"  [获取 {code} 资金流向...]", file=sys.stderr, flush=True)
    fund = get_fund_flow(code)
    sector = get_sector(code)

    prediction_input = {
        "code": code,
        "name": name or quote.get("名称", code),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "market_state": quote.get("市场状态", "未知"),
        "current_price": quote.get("最新价"),
        "change_pct": quote.get("涨跌幅(%)"),
        "technical": tech,
        "fund_flow": fund,
        "sector_info": sector,
        "ma_trend": _calc_ma_trend(tech),
        "prediction_indicators": {
            "short_term_signal": _short_term_signal(tech, fund),
            "risk_level": _calc_risk(tech, fund),
            "support": _calc_support(tech, quote),
            "resistance": _calc_resistance(tech, quote),
        }
    }
    return prediction_input


def _calc_ma_trend(tech: dict) -> str:
    """判断均线趋势"""
    if not tech or "error" in tech:
        return "数据不足"
    m5, m10, m20, m60 = tech.get("ma5"), tech.get("ma10"), tech.get("ma20"), tech.get("ma60")
    if all(v is not None for v in [m5, m10, m20, m60]):
        if m5 > m10 > m20 > m60:
            return "多头排列"
        elif m5 < m10 < m20 < m60:
            return "空头排列"
        else:
            return "交叉/整理"
    return "数据不足"


def _short_term_signal(tech: dict, fund: dict) -> str:
    """短期综合信号"""
    if not tech or "error" in tech:
        return "等待"
    signals = []
    bias = tech.get("bias_ma20")
    if bias is not None and -2 < bias < 2:
        signals.append("回踩MA20")
    if tech.get("pct1", 0) > 0 and tech.get("vol_ratio", 1) > 1.2:
        signals.append("放量上涨")
    if tech.get("pct5", 0) < -3:
        signals.append("连续回调")
    if fund.get("main_5d", 0) > 1000:
        signals.append("主力流入")
    if fund.get("main_5d", 0) < -1000:
        signals.append("主力流出")
    return "+".join(signals) if signals else "无明显信号"


def _calc_risk(tech: dict, fund: dict) -> str:
    """风险评估"""
    if not tech:
        return "未知"
    risk = []
    bias = tech.get("bias_ma20")
    if bias is not None and bias < -3:
        risk.append("跌破MA20")
    if tech.get("pct5", 0) < -8:
        risk.append("近5日大跌")
    if fund.get("main_5d", 0) is not None and fund.get("main_5d", 0) < -5000:
        risk.append("主力大幅流出")
    if tech.get("vol_ratio", 1) is not None and tech.get("vol_ratio", 1) < 0.5:
        risk.append("极度缩量")
    return "+".join(risk) if risk else "正常"


def _calc_support(tech: dict, quote: dict) -> float:
    """计算支撑位"""
    if not tech:
        return 0
    ma20 = tech.get("ma20", 0)
    ma60 = tech.get("ma60", 0)
    low = quote.get("最低", 0)
    return min(ma20, ma60, low) if low > 0 else min(ma20, ma60)


def _calc_resistance(tech: dict, quote: dict) -> float:
    """计算压力位"""
    if not tech:
        return 0
    ma5 = tech.get("ma5", 0)
    ma10 = tech.get("ma10", 0)
    high = quote.get("最高", 0)
    candidates = [v for v in [ma5, ma10, high] if v and v > 0]
    return max(candidates) if candidates else 0


def cmd_single(args):
    data = predict_single(args.code, args.name)
    if args.full:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        d = data
        print(f"\n{'='*50}")
        print(f"  {d['name']}({d['code']})  预测数据采集完成")
        print(f"  时间: {d['timestamp']}")
        print(f"  现价: {d['current_price']} ({d['change_pct']:+.2f}%)")
        print(f"{'='*50}")
        t = d.get("technical", {})
        if "error" not in t:
            print(f"\n  【技术面】")
            print(f"  均线: MA5={t.get('ma5','?')} MA10={t.get('ma10','?')}")
            print(f"        MA20={t.get('ma20','?')} MA60={t.get('ma60','?')}")
            print(f"  趋势: {d.get('ma_trend','?')}")
            print(f"  量比: {t.get('vol_ratio','?')}  换手: {t.get('turnover','?')}%")
            print(f"  近1日: {t.get('pct1',0):+.2f}%  近5日: {t.get('pct5',0):+.2f}%")
            print(f"  乖离MA20: {t.get('bias_ma20',0):+.2f}%  乖离MA60: {t.get('bias_ma60',0):+.2f}%")
        f = d.get("fund_flow", {})
        if f:
            print(f"\n  【资金面】")
            print(f"  近5日主力: {f.get('main_5d',0):+.0f}万")
        pi = d.get("prediction_indicators", {})
        print(f"\n  【预测指标】")
        print(f"  短期信号: {pi.get('short_term_signal','?')}")
        print(f"  风险评估: {pi.get('risk_level','?')}")
        print(f"  支撑位: {pi.get('support','?')}  压力位: {pi.get('resistance','?')}")
        print(f"\n  → 将以上数据提供给 DeepSeek-V4-Flash 生成预测")


def cmd_pool(args):
    path = os.path.join(POOLS_BASE,
                        "selected_pool.csv" if args.pool == "selected" else "watch_pool.csv")
    if not os.path.exists(path):
        print(f"{args.pool}池为空")
        return
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        data = predict_single(r["code"], r.get("name", ""))
        t = data.get("technical", {})
        pi = data.get("prediction_indicators", {})
        icon = "✓" if pi.get("risk_level") == "正常" else "⚠"
        print(f"  {icon} {data['code']} {data['name']:<10} "
              f"现价{data['current_price']:<8} "
              f"乖离MA20:{t.get('bias_ma20',0):+6.2f}% "
              f"短期:{pi.get('short_term_signal','?'):<20} "
              f"风险:{pi.get('risk_level','?')}")


def cmd_positions(args):
    path = os.path.join(POOLS_BASE, "positions.csv")
    if not os.path.exists(path):
        print("持仓为空")
        return

    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    total_cost, total_val = 0, 0
    for r in rows:
        try:
            bp, qty = float(r["buy_price"]), int(r["qty"])
        except:
            continue
        cost = bp * qty
        total_cost += cost
        data = predict_single(r["code"], r.get("name", ""))
        cur = data.get("current_price", bp)
        val = cur * qty
        total_val += val
        pnl = val - cost
        pnl_pct = (cur - bp) / bp * 100
        pi = data.get("prediction_indicators", {})
        icon = "▲" if pnl >= 0 else "▼"
        print(f"  {icon} {data['code']} {data['name']:<10} "
              f"成本{bp:<8.2f} 现价{cur:<8.2f} "
              f"盈亏{pnl_pct:+7.2f}% "
              f"风险:{pi.get('risk_level','?'):<8} "
              f"信号:{pi.get('short_term_signal','?'):<16}")
    total_pnl = total_val - total_cost
    print(f"\n  持仓汇总: 成本{total_cost:,.0f} 市值{total_val:,.0f} "
          f"总盈亏{total_pnl:+,.0f} ({(total_pnl/total_cost*100):+.2f}%)")


def main():
    parser = argparse.ArgumentParser(description="A股预测数据采集")
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--name", help="股票名称")
    parser.add_argument("--full", action="store_true", help="完整数据输出")
    parser.add_argument("--pool", choices=["selected", "watch"], help="池批量预测")
    parser.add_argument("--positions", action="store_true", help="持仓批量预测")
    args = parser.parse_args()

    if args.pool:
        cmd_pool(args)
    elif args.positions:
        cmd_positions(args)
    elif args.code:
        cmd_single(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()