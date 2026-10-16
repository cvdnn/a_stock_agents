#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地K线「技术评分 + MA20趋势回测」一体工具 —— 规避 backtest_engine 的 urllib SSL 超时，
以及 execute_code 沙箱无外网的问题。数据先用 terminal curl 落盘 (快且稳) 再交给本脚本计算。

用法:
  1) 落盘K线 (terminal, 非 execute_code; execute_code 沙箱无外网 Errno 101):
     mkdir -p /tmp/astk/kl
     for pair in "603259:sh" "601899:sh" "002532:sz"; do
       code="${pair%%:*}"; pfx="${pair##*:}"
       timeout 15 curl -s "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=${pfx}${code},day,,,120,qfq" \
         -H "User-Agent: Mozilla/5.0" -o "/tmp/astk/kl/${code}.json"
     done
  2) 评分 + 回测:
     python3 local_ma20_backtest.py 603259 601899 002532 002371 002463
  (ASTK_KL_DIR 环境变量可改K线目录, 默认 /tmp/astk/kl)

输出: 每只一行 —— 收盘/距MA20/距MA10/MACD/KDJ_J/RSI/组合评分 + 买持/趋势策略/年化/最大回撤/交易/胜率/盈亏比。
回测: close>MA20 持有多头、close<MA20 空仓的纯趋势过滤器。结论仅作策略有效性参考, 非买卖指令。
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

import json, sys, os

KLDIR = os.environ.get("ASTK_KL_DIR", "/tmp/astk/kl")


def load(code):
    path = os.path.join(KLDIR, f"{code}.json")
    if not os.path.exists(path):
        sys.stderr.write(f"[!] 缺K线文件: {path}\n")
        return None
    d = json.load(open(path))
    k = list(d["data"].values())[0]
    return k.get("qfqday") or k.get("day")  # [[date,open,close,high,low,vol],...]


from core.indicators.technical_indicators import calc_all, ma
from core.models.combo_scorer import ComboScorer
from core.paper_trading.backtest_metrics import compute_metrics


def tech(kl):
    """复用 core.indicators.technical_indicators 权威计算。"""
    closes = [float(x[2]) for x in kl]
    last = closes[-1]
    res = calc_all(kl)
    latest = res.get("latest") or {}
    ma10 = latest.get("ma10", 0.0)
    ma20 = latest.get("ma20", 0.0)
    bar = latest.get("macd_bar", 0.0)
    rsi_list = res.get("rsi", [])
    rsi = round(rsi_list[-1], 1) if rsi_list else 50.0
    d20 = (last - ma20) / ma20 * 100 if ma20 else 0.0
    d10 = (last - ma10) / ma10 * 100 if ma10 else 0.0
    return dict(
        last=last,
        ma5=latest.get("ma5", 0.0),
        ma10=ma10,
        ma20=ma20,
        ma60=latest.get("ma60", 0.0),
        dif=latest.get("dif", 0.0),
        dea=latest.get("dea", 0.0),
        bar=bar,
        rsi=rsi,
        d20=d20,
        d10=d10,
        latest=latest,
    )


def combo_score(t, kl=None):
    """复用 core.models.combo_scorer 权威100分制评分。"""
    scorer = ComboScorer()
    latest = t.get("latest") or t
    if kl:
        scores = scorer.score_full(kl, latest=latest)
        total = scores.get("total", 0)
        rating = scores.get("rating", "D")
    else:
        ma_s, _ = scorer.score_ma_structure(latest)
        macd_s, _ = scorer.score_macd(latest)
        total = ma_s + macd_s
        rating = "A" if total >= 40 else ("B" if total >= 30 else ("C" if total >= 20 else "D"))
    return total, rating


def backtest(kl):
    """复用 core.indicators 均线与 core.paper_trading.backtest_metrics 权威回测指标。"""
    closes = [float(x[2]) for x in kl]
    dates = [str(x[0]) for x in kl]
    m20 = ma(closes, 20)
    bh = (closes[-1] / closes[0] - 1.0) * 100.0 if closes[0] else 0.0

    pos = 0
    entry = 0.0
    equity = 1.0
    trades = []
    equity_curve = [{"date": dates[0], "equity": 1.0}]

    for i in range(20, len(closes)):
        sig = m20[i] is not None and m20[i] > 0 and closes[i] > m20[i]
        if sig and pos == 0:
            pos = 1
            entry = closes[i]
            trades.append({"action": "buy", "price": closes[i], "qty": 100, "date": dates[i]})
        elif not sig and pos == 1:
            profit = (closes[i] / entry - 1.0) * entry * 100
            trades.append({"action": "sell", "price": closes[i], "qty": 100, "profit": profit, "date": dates[i]})
            equity *= (closes[i] / entry)
            pos = 0
        elif pos == 1:
            equity *= (closes[i] / closes[i - 1])
        cur_eq = equity * (closes[i] / entry) if pos and entry else equity
        equity_curve.append({"date": dates[i], "equity": cur_eq})

    if pos and entry:
        profit = (closes[-1] / entry - 1.0) * entry * 100
        trades.append({"action": "sell", "price": closes[-1], "qty": 100, "profit": profit, "date": dates[-1]})
        final_eq = equity * (closes[-1] / entry)
    else:
        final_eq = equity

    metrics = compute_metrics(
        equity_curve=equity_curve,
        trades=trades,
        initial_cash=1.0,
        final_equity=final_eq,
        days=len(closes),
        buy_hold_return_pct=bh,
    )

    pf = metrics.get("profit_factor", 0.0)
    pf_str = round(pf, 2) if pf != 999.0 and pf != float("inf") else "inf"
    return dict(
        bh=round(bh, 1),
        strat=round(metrics.get("total_return_pct", 0.0), 1),
        ann=round(metrics.get("annual_return_pct", 0.0), 1),
        maxdd=round(metrics.get("max_drawdown_pct", 0.0), 1),
        trades=metrics.get("total_trades", 0),
        wr=round(metrics.get("win_rate_pct", 0.0)),
        pf=pf_str,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    print(f"{'代码':<7}{'收盘':>8}{'距MA20':>8}{'距MA10':>8}{'MACD':>8}{'RSI':>6}  {'评分':>5}  {'买持':>7}{'趋势':>8}{'年化':>7}{'回撤':>8}{'交易':>5}{'胜率':>5}{'盈亏比':>7}")
    for code in sys.argv[1:]:
        kl = load(code)
        if not kl:
            continue
        t = tech(kl)
        total, rating = combo_score(t, kl=kl)
        b = backtest(kl)
        print(f"{code:<7}{t['last']:>8.2f}{t['d20']:>+7.1f}%{t['d10']:>+7.1f}%{t['bar']:>+8.2f}{t['rsi']:>6.1f}  {total}/{rating}  "
              f"{b['bh']:>6.1f}%{b['strat']:>7.1f}%{b['ann']:>6.1f}%{b['maxdd']:>7.1f}%{b['trades']:>5}{b['wr']:>4.0f}%{b['pf']:>7}")
