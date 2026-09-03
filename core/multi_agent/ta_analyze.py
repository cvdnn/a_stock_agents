#!/usr/bin/env python3
"""
ta_analyze.py — AI-Platform × TradingAgents 多Agent投研分析桥梁

整合 3 阶段管道：
  Phase 1: AI-Platform 数据层获取 + 量化评分预筛
  Phase 2: TradingAgents-astock 7分析师多Agent辩论
  Phase 3: AI-Platform 模拟盘执行 + cron监控部署

Usage:
  # 完整分析（Phase 1+2+3）
  python3 ta_analyze.py 600519 --date 2026-07-09 --paper-trade --deploy-monitor

  # 仅多Agent分析
  python3 ta_analyze.py 600760 --date 2026-07-09 --phase 2 --json

  # 仅量化评分预筛
  python3 ta_analyze.py 600498 --phase 1 --pre-score

  # 批量分析
  python3 ta_analyze.py --batch stocks.txt --date 2026-07-09 --phase 2 --json > batch.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 路径常量 ──────────────────────────────────────────────────────────────────

try:
    from core.config import PROJECT_ROOT, SKILLS_DIR, OUTPUT_DIR, OUTPUT_POOLS_DIR
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    SKILLS_DIR = PROJECT_ROOT / "skills"
    OUTPUT_DIR = PROJECT_ROOT / "output"
    OUTPUT_POOLS_DIR = OUTPUT_DIR / "pools"

# TradingAgents 项目路径（自动检测）
_TA_PATHS = [
    PROJECT_ROOT / "TradingAgents",
    PROJECT_ROOT.parent / "TradingAgents",
    Path.home() / "TradingAgents",
    Path.home() / "TradingAgents-astock",
    Path.home() / ".TradingAgents",
]
TA_DIR = next((p for p in _TA_PATHS if p.exists()), None)

# AI-Platform 技能路径（优先系统全局路径，回退本地 skills/）
AI_PLATFORM_SKILLS = Path.home() / ".AI-Platform" / "skills" / "stocks"
if not AI_PLATFORM_SKILLS.exists():
    AI_PLATFORM_SKILLS = SKILLS_DIR

# VENV Python
VENV_PY = Path(sys.executable)

# ═══════════════════════════════════════════════════════════════════════════════
# 数据降级策略（替换 TradingAgents 原生数据源）
# ═══════════════════════════════════════════════════════════════════════════════

def _call_ai_platform(skill: str, script: str, *args: str, timeout: int = 30) -> Optional[Dict]:
    """调用 AI-Platform skill 脚本并解析 JSON 输出。"""
    script_path = AI_PLATFORM_SKILLS / skill / "scripts" / script
    if not script_path.exists():
        return None
    cmd = [str(VENV_PY), str(script_path), "--json", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def _call_akshare_direct(code: str, script: str, *args: str) -> Optional[Dict]:
    """通过 akshare 直连获取数据（利用 TA 项目 venv）。"""
    cmd = [str(VENV_PY), "-c", f"""
import json, sys
sys.path.insert(0, r'{TA_DIR}')
from tradingagents.dataflows.akshare.stock import get_stock_data
try:
    df = get_stock_data('{code}')
    print(df.tail(10).to_json(orient='records', force_ascii=False))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return json.loads(result.stdout)
    except Exception:
        return None


def _tencent_quote(code: str) -> Optional[Dict]:
    """腾讯行情 API 直连（终局备选，最稳定）。"""
    prefix = "sh" if code.startswith(("6", "9")) else "sz" if code.startswith(("0", "3")) else "bj"
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    cmd = [str(VENV_PY), "-c", f"""
import urllib.request, json
try:
    req = urllib.request.Request('{url}', headers={{"User-Agent": "Mozilla/5.0"}})
    resp = urllib.request.urlopen(req, timeout=10)
    text = resp.read().decode('gbk')
    parts = text.split('~')
    print(json.dumps({{
        "name": parts[1], "price": parts[3], "change": parts[32],
        "high": parts[5], "low": parts[6], "volume": parts[7],
        "turnover": parts[8], "pe": parts[9], "pb": parts[10],
        "market_cap": parts[12],
    }}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        if "error" not in data:
            return data
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: 量化评分预筛
# ═══════════════════════════════════════════════════════════════════════════════

def _is_blocked(code: str) -> bool:
    """检查股票是否在不可交易板块（科创板/创业板/北交所）。"""
    return code.startswith(("688", "689", "30", "8", "4"))


def phase1_prescreen(ticker: str, date: str) -> Dict[str, Any]:
    """Phase 1: 数据获取 + 量化评分 + 策略预筛。"""
    result = {
        "ticker": ticker,
        "date": date,
        "blocked": _is_blocked(ticker),
        "realtime": None,
        "technical": None,
        "trading_combo_score": None,
        "tencent_fallback": False,
        "errors": [],
    }

    # 1. 实时行情（腾讯 API 直连，最稳定，2秒返回）
    result["realtime"] = _tencent_quote(ticker)

    # 2. 技术指标（AI-Platform a-share-data fetch_technical.py，15s超时）
    tech = _call_ai_platform("a-share-data", "fetch_technical.py",
                        ticker, "--freq", "1d", "--count", "120",
                        "--indicators", "MA,MACD,KDJ,RSI,BOLL",
                        timeout=15)
    result["technical"] = tech

    # 3. 板块排行（15s超时）
    boards = _call_ai_platform("a-share-data", "fetch_realtime.py",
                          "--boards-summary", "--boards-limit", "30",
                          timeout=15)

    # 4a. 使用腾讯直连做硬件评分（如果 AI-Platform 脚本超时）
    if not tech and result["realtime"]:
        result["tencent_fallback"] = True
        # 用腾讯行情数据做简化评分
        rt = result["realtime"]
        try:
            score = {
                "ma": 10,  # 无法获取均线，给中性分
                "macd": 10,
                "volume": 8,
                "sector": 10,
                "total": 38,
                "rating": "C",
                "note": "腾讯直连模式（技术指标未获取到）",
            }
            # 尝试用 PE 高低做简单估值参考
            pe_str = rt.get("pe", "0")
            pe_val = float(pe_str) if pe_str.replace(".", "").isdigit() else 0
            if 10 < pe_val < 40:
                score["ma"] = 15
                score["total"] = 43
                score["rating"] = "C"
            if pe_val > 0:
                score["note"] += f" | PE={pe_val:.0f}"
            result["trading_combo_score"] = score
        except (ValueError, TypeError):
            pass

    # 4b. trading-combo 评分（正常模式）
    if tech and boards:
        score = _calc_trading_combo_score(ticker, tech, boards)
        result["trading_combo_score"] = score
    elif tech and not boards:
        # 有技术数据但无板块数据，给部分分
        score = _calc_trading_combo_score(ticker, tech, {})
        score["note"] = "板块排行未获取到，板块分按默认计算"
        result["trading_combo_score"] = score

    # 5. 筹码分布（5s超时）
    cyq = _call_akshare_direct(ticker, "stock_cyq_em")
    if cyq and isinstance(cyq, list) and len(cyq) > 0:
        result["cyq"] = cyq[-1]
        # 计算简易评分
        if "90集中度" in str(cyq[-1]):
            result["cyq_rating"] = "筹码集中" if float(cyq[-1].get("90集中度", 1)) < 0.13 else "筹码发散"

    return result


def _calc_trading_combo_score(ticker: str, tech: Dict, boards: Dict) -> Dict:
    """计算 trading-combo 100 分制评分（简化版，详版见该技能 SKILL.md 第二章）。"""
    score = {"ma": 0, "macd": 0, "volume": 0, "sector": 0, "total": 0, "rating": "D"}

    try:
        # 从 tech 中提取最新数据行
        if isinstance(tech, dict) and "data" in tech:
            records = tech["data"]
        elif isinstance(tech, list) and len(tech) > 0:
            records = tech
        else:
            return score

        latest = records[-1] if isinstance(records, list) else records

        # 均线评分 (25)
        ma5 = float(latest.get("MA5", 0) if isinstance(latest, dict) else getattr(latest, "MA5", 0))
        ma10 = float(latest.get("MA10", 0) if isinstance(latest, dict) else getattr(latest, "MA10", 0))
        ma20 = float(latest.get("MA20", 0) if isinstance(latest, dict) else getattr(latest, "MA20", 0))
        close = float(latest.get("close", latest.get("收盘", 0)) if isinstance(latest, dict) else getattr(latest, "close", 0))

        if ma5 > ma10 > ma20 and close > ma20:
            score["ma"] = 25
        elif close > ma20:
            score["ma"] = 15

        # MACD 评分 (40)
        dif = float(latest.get("DIF", 0))
        dea = float(latest.get("DEA", 0))
        bar = float(latest.get("MACD", 0))

        if dif > 0 and dif > dea and bar > 0:
            score["macd"] = 40
        elif dif > 0:
            score["macd"] = 20
        elif dif > dea:
            score["macd"] = 10

        # 量价评分 (15)
        pct_ma20 = abs((close - ma20) / ma20 * 100) if ma20 else 999
        if close > ma20 and pct_ma20 < 3:
            score["volume"] = 15
        elif close > ma20:
            score["volume"] = 10
        elif pct_ma20 < 5:
            score["volume"] = 8

        # 板块共振 (20) — 从 boards 数据中查找
        if isinstance(boards, dict):
            board_data = boards.get("data", [])
            if isinstance(board_data, list) and len(board_data) > 3:
                score["sector"] = 20  # 默认给分，精确匹配需知道股票所属板块

        score["total"] = score["ma"] + score["macd"] + score["volume"] + score["sector"]
        if score["total"] >= 80:
            score["rating"] = "A"
        elif score["total"] >= 65:
            score["rating"] = "B"
        elif score["total"] >= 50:
            score["rating"] = "C"

    except (TypeError, ValueError, IndexError, ZeroDivisionError) as e:
        score["error"] = str(e)

    return score


# ═══════════════════════════════════════════════════════════════════════════════
# 融合评分 & 股池同步（新增：整合优化 P0+P1）
# ═══════════════════════════════════════════════════════════════════════════════

POOL_MANAGER = AI_PLATFORM_SKILLS / "a-share-dashboard" / "scripts" / "pool_manager.py"


def _consensus_rating(quant_score: Optional[Dict], ta_decision: Optional[Dict]) -> Dict:
    """
    计算量化评分 x LLM 决策的融合评级（P1: 融合评分矩阵）。
    
    矩阵映射:
      量化A + TA BUY  → 强烈买入 ⭐⭐⭐⭐
      量化A + TA HOLD → 持有观望 ⭐⭐⭐
      量化B + TA BUY  → 谨慎买入 ⭐⭐⭐
      ... 
      任一方 SELL     → 一致离场
    """
    q_rating = (quant_score or {}).get("rating", "D")
    ta_action = ""
    if isinstance(ta_decision, dict):
        ta_action = (ta_decision.get("action") or "").upper()
    elif isinstance(ta_decision, str):
        ta_action = ta_decision.upper()

    # 任一方触发离场
    if ta_action in ("SELL", "EXIT"):
        return {"level": "一致离场", "stars": 0, "position": "清仓", "action": "SELL"}

    matrix = {
        ("A", "BUY"):  {"level": "强烈买入", "stars": 4, "position": "30-40%", "action": "BUY"},
        ("A", "HOLD"): {"level": "持有观望", "stars": 3, "position": "维持现有", "action": "HOLD"},
        ("B", "BUY"):  {"level": "谨慎买入", "stars": 3, "position": "15-25%", "action": "BUY"},
        ("B", "HOLD"): {"level": "继续观察", "stars": 2, "position": "不加仓", "action": "HOLD"},
        ("C", "BUY"):  {"level": "评分分歧", "stars": 1, "position": "轻仓5-10%", "action": "BUY"},
        ("C", "HOLD"): {"level": "量化偏弱", "stars": 1, "position": "仅观察", "action": "HOLD"},
        ("D", "BUY"):  {"level": "严重分歧", "stars": 1, "position": "放弃或极轻仓", "action": "HOLD"},
        ("D", "HOLD"): {"level": "量化弱势", "stars": 0, "position": "不建议参与", "action": "HOLD"},
    }
    key = (q_rating, ta_action)
    if key not in matrix:
        key = (q_rating, "HOLD")
    return matrix[key]


def _sync_to_pool(ticker: str, name: str, consensus: Dict,
                  quant_score: Optional[Dict], ta_decision: Optional[Dict],
                  pool: str = "selected", sync: bool = True) -> Dict:
    """
    将分析结果同步到股池（P0: TA->股池自动写回）。
    
    决策 BUY  → pool_manager.py add
    决策 SELL → pool_manager.py remove
    """
    from datetime import date as dt_date
    result = {"synced": False, "action": None, "message": ""}

    if not sync:
        result["message"] = "同步已关闭（--no-sync-pool）"
        return result
    if not POOL_MANAGER.exists():
        result["message"] = f"pool_manager.py 未找到: {POOL_MANAGER}"
        return result

    action = consensus.get("action", "HOLD")
    price = ""
    stop_loss = ""
    if isinstance(ta_decision, dict):
        price = str(ta_decision.get("price") or ta_decision.get("entry_price") or "")
        stop_loss = str(ta_decision.get("stop_loss") or ta_decision.get("stop_price") or "")

    try:
        if action == "BUY":
            # 写入自选股池
            cmd = [
                str(VENV_PY), str(POOL_MANAGER),
                "add", "--pool", pool,
                "--code", ticker, "--name", name,
                "--reason", f"TA分析推荐: {consensus['level']} ⭐{'⭐'*consensus['stars']}",
                "--rating", (quant_score or {}).get("rating", "B"),
                "--risk-level", "中",
                "--entry-trigger", f"融合评级{consensus['level']}",
            ]
            if price:
                cmd += ["--stop-loss", stop_loss] if stop_loss else []
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            result["synced"] = (r.returncode == 0)
            result["action"] = "add"
            result["message"] = r.stdout.strip() or r.stderr.strip()

        elif action == "SELL":
            # 从自选股池移除
            cmd = [str(VENV_PY), str(POOL_MANAGER),
                   "remove", "--pool", pool, "--code", ticker]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            result["synced"] = (r.returncode == 0)
            result["action"] = "remove"
            result["message"] = r.stdout.strip() or r.stderr.strip()

        else:  # HOLD
            result["message"] = "HOLD 决策无需同步"
    except subprocess.TimeoutExpired:
        result["message"] = "股池同步超时"
    except Exception as e:
        result["message"] = f"股池同步失败: {e}"

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: TradingAgents 多Agent管道
# ═══════════════════════════════════════════════════════════════════════════════

def phase2_multiagent_analysis(ticker: str, date: str,
                                provider: str = "minimax",
                                deep_model: str = "MiniMax-M2.7",
                                quick_model: str = "MiniMax-M2.7-highspeed",
                                prescore: Optional[Dict] = None) -> Dict[str, Any]:
    """Phase 2: 调用 TradingAgents-astock 7分析师辩论管道。"""
    if not TA_DIR or not TA_DIR.exists():
        return {
            "error": True,
            "message": f"TradingAgents 项目目录未找到（已搜索: {[str(p) for p in _TA_PATHS]}）",
        }

    ta_tradingagents = TA_DIR / "tradingagents"
    if not ta_tradingagents.exists():
        return {
            "error": True,
            "message": f"tradingagents 模块不存在于: {ta_tradingagents}。"
                       f"请从 {_TA_PATHS[0]} 完整安装。"
                       f"运行: cd {TA_DIR.parent if TA_DIR else '?'} && pip install -e .",
        }

    # 检查是否有完整管道（agents/graph/llm_clients）
    has_full_pipeline = all(
        (ta_tradingagents / d).exists()
        for d in ["agents", "graph", "llm_clients"]
    )
    if not has_full_pipeline:
        return {
            "error": True,
            "message": f"TradingAgents 仅安装了部分模块（{TA_DIR}/tradingagents）。"
                       f"缺失 agents/graph/llm_clients 目录。"
                       f"请先安装完整 TradingAgents: pip install -e {TA_DIR or 'TradingAgents'}",
        }

    # 构建 Python 代码以在子进程中运行
    score_context = json.dumps(prescore, ensure_ascii=False) if prescore else "{}"

    py_code = f"""
import json, sys, os
sys.path.insert(0, r'{TA_DIR}')

# 加载 .env
from pathlib import Path
env_path = Path(r'{TA_DIR}') / '.env'
if not env_path.exists():
    env_path = Path(r'{TA_DIR}').parent / '.env'
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.strip().split('=', 1)
            os.environ[k.strip()] = v.strip()

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = dict(DEFAULT_CONFIG)
config.update({{
    "llm_provider": "{provider}",
    "deep_think_llm": "{deep_model}",
    "quick_think_llm": "{quick_model}",
    "output_language": "Chinese",
    "data_vendors": {{"*": "a_stock"}},
}})

ta = TradingAgentsGraph(debug=False, config=config)
final_state, decision = ta.propagate("{ticker}", "{date}")

# 构建输出
output = {{
    "ticker": "{ticker}",
    "date": "{date}",
    "error": False,
    "analyst_reports": {{
        "market": final_state.get("market_report", ""),
        "sentiment": final_state.get("sentiment_report", ""),
        "news": final_state.get("news_report", ""),
        "fundamentals": final_state.get("fundamentals_report", ""),
        "policy": final_state.get("policy_report", ""),
        "hot_money": final_state.get("hot_money_report", ""),
        "lockup": final_state.get("lockup_report", ""),
    }},
    "quality_gate": final_state.get("data_quality_summary", ""),
    "investment_plan": final_state.get("investment_plan", ""),
    "trade_plan": final_state.get("trader_investment_plan", ""),
    "final_decision": decision,
    "score_context": {score_context},
}}

print("__TA_RESULT__")
print(json.dumps(output, ensure_ascii=False))
print("__TA_END__")
"""
    cmd = [str(VENV_PY), "-c", py_code]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        # 从 stdout 提取结果
        stdout = result.stdout
        start = stdout.find("__TA_RESULT__")
        end = stdout.find("__TA_END__")
        if start >= 0 and end > start:
            json_str = stdout[start + len("__TA_RESULT__"):end].strip()
            return json.loads(json_str)
        else:
            return {
                "error": True,
                "message": "无法解析 TradingAgents 输出",
                "raw_stdout": stdout[-2000:],
                "raw_stderr": result.stderr[-2000:],
            }
    except subprocess.TimeoutExpired:
        return {"error": True, "message": "TradingAgents 分析超时（300s）"}
    except json.JSONDecodeError as e:
        return {"error": True, "message": f"JSON 解析失败: {e}"}
    except Exception as e:
        return {"error": True, "message": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3: 模拟盘执行 + 监控部署
# ═══════════════════════════════════════════════════════════════════════════════

_PAPER_CLI = AI_PLATFORM_SKILLS / "a-share-paper-trading" / "scripts" / "paper_trade_cli.py"


def phase3_execute(decision: Dict, ticker: str, paper_account: str = "alpha",
                   paper_base_url: str = "http://127.0.0.1:18765") -> Dict[str, Any]:
    """Phase 3: 根据决策执行模拟盘交易。"""
    action = (decision.get("action") or decision.get("final_decision") or "").upper()
    result = {
        "ticker": ticker,
        "action": action,
        "executed": False,
        "order_result": None,
        "position_result": None,
        "errors": [],
    }

    if action not in ("BUY", "SELL"):
        result["message"] = f"决策不是可执行动作: {action}"
        return result

    # 解析数量和价格
    shares = decision.get("shares", 0) or decision.get("quantity", 0)
    price = decision.get("price") or decision.get("limit_price")
    direction = "buy" if action == "BUY" else "sell"

    if shares <= 0:
        result["message"] = "无效数量"
        return result

    # 通过 paper_trade_cli.py 下单
    if _PAPER_CLI.exists():
        try:
            cmd = [
                str(VENV_PY), str(_PAPER_CLI),
                "--base-url", paper_base_url,
                direction, paper_account, ticker, str(shares),
            ]
            if price:
                cmd += ["--price", str(price)]
            else:
                cmd += ["--market"]

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            result["order_result"] = {
                "stdout": r.stdout[:1000],
                "stderr": r.stderr[:500],
                "exit_code": r.returncode,
            }
            if r.returncode == 0:
                result["executed"] = True

            # 获取持仓确认
            pos_cmd = [
                str(VENV_PY), str(_PAPER_CLI),
                "--base-url", paper_base_url,
                "positions", paper_account,
            ]
            pos_r = subprocess.run(pos_cmd, capture_output=True, text=True, timeout=15)
            if pos_r.returncode == 0:
                result["position_result"] = pos_r.stdout[:1000]

        except subprocess.TimeoutExpired:
            result["errors"].append("下单超时")
        except Exception as e:
            result["errors"].append(str(e))
    else:
        result["errors"].append(f"paper_trade_cli.py 未找到: {_PAPER_CLI}")

    return result


def phase3_deploy_monitor(ticker: str, entry_price: float, stop_price: float,
                          shares: int = 0, account: str = "alpha",
                          deploy_dashboard_monitor: bool = True) -> Dict[str, Any]:
    """Phase 3: 部署 cron 监控（止损 + 入场条件）。
    
    使用统一的 ta_entry_monitor.py 模板，同时支持：
    - stop 模式：止损检测（默认）
    - entry 模式：MA20回踩入场检测（如果 deploy_dashboard_monitor=True）
    """
    result = {"ticker": ticker, "monitors": [], "errors": []}

    # 使用统一模板
    candidates = [
        Path(__file__).resolve().parent / "templates" / "ta_entry_monitor.py.template",
        PROJECT_ROOT / "skills" / "ta-multi-agent-analysis" / "templates" / "ta_entry_monitor.py",
        SKILL_DIR / "templates" / "ta_entry_monitor.py",
    ]
    template_path = next((p for p in candidates if p.exists()), None)
    if not template_path:
        result["errors"].append("监控模板不存在")
        return result

    template = template_path.read_text(encoding="utf-8")

    # 1. 止损监控（stop 模式）
    stop_script = template.replace("{{TICKER}}", ticker) \
        .replace("{{ENTRY_PRICE}}", str(entry_price)) \
        .replace("{{STOP_PRICE}}", str(stop_price)) \
        .replace("{{ACCOUNT}}", account)
    # 默认 mode=stop
    stop_script = stop_script.replace(
        '# MODE = os.environ.get("MONITOR_MODE", "stop")',
        'MODE = "stop"')

    monitor_dir = OUTPUT_DIR / "monitors"
    monitor_dir.mkdir(parents=True, exist_ok=True)

    stop_path = monitor_dir / f"ta_monitor_{ticker}.py"
    stop_path.write_text(stop_script)
    result["stop_script_path"] = str(stop_path)

    # 部署止损 cron
    try:
        cron_cmd = [
            str(VENV_PY), "-m", "AI-Platform", "cron", "create",
            "--name", f"TA止损-{ticker}",
            "--script", str(stop_path),
            "--schedule", "every 5m",
            "--no-agent", "--deliver", "all",
        ]
        r = subprocess.run(cron_cmd, capture_output=True, text=True, timeout=15)
        result["stop_cron"] = {
            "stdout": r.stdout[:300],
            "exit_code": r.returncode,
        }
        if r.returncode == 0:
            result["deployed"] = True
    except subprocess.TimeoutExpired:
        result["errors"].append("止损cron部署超时")
    except Exception as e:
        result["errors"].append(str(e))

    # 2. 入场条件监控（entry 模式，可选）
    if deploy_dashboard_monitor and entry_price > 0:
        entry_script = template.replace("{{TICKER}}", ticker) \
            .replace("{{ENTRY_PRICE}}", str(entry_price)) \
            .replace("{{STOP_PRICE}}", "0") \
            .replace("{{ACCOUNT}}", account)
        entry_script = entry_script.replace(
            '# MODE = os.environ.get("MONITOR_MODE", "stop")',
            'MODE = "entry"')

        entry_path = monitor_dir / f"ta_entry_{ticker}.py"
        entry_path.write_text(entry_script)
        result["entry_script_path"] = str(entry_path)

        try:
            cron_cmd = [
                str(VENV_PY), "-m", "AI-Platform", "cron", "create",
                "--name", f"TA入场-{ticker}",
                "--script", str(entry_path),
                "--schedule", "every 5m",
                "--no-agent", "--deliver", "all",
            ]
            r = subprocess.run(cron_cmd, capture_output=True, text=True, timeout=15)
            result["entry_cron"] = {
                "stdout": r.stdout[:300],
                "exit_code": r.returncode,
            }
        except (subprocess.TimeoutExpired, Exception) as e:
            result["errors"].append(f"入场cron部署: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 报告格式化
# ═══════════════════════════════════════════════════════════════════════════════

def format_report(phase1: Dict, phase2: Optional[Dict],
                  phase3_exec: Optional[Dict], phase3_monitor: Optional[Dict],
                  brief: bool = False) -> str:
    """格式化输出报告。"""
    ticker = phase1["ticker"]
    date = phase1["date"]
    realtime = phase1.get("realtime", {})
    score = phase1.get("trading_combo_score", {})

    lines = []
    lines.append(f"═══════════════════════════════════════════════════")
    lines.append(f"  {realtime.get('name', ticker)}({ticker}) — 多Agent投研报告")
    lines.append(f"  日期：{date}{'（实时）' if realtime and 'price' in realtime else ''}")
    lines.append(f"═══════════════════════════════════════════════════")
    lines.append("")

    # 融合评级（新增：P1 优化）
    if not brief:
        decision = (phase2 or {}).get("final_decision", {})
        consensus = _consensus_rating(score, decision)
        stars_str = "⭐" * consensus["stars"]
        lines.append(f"  融合评级: {consensus['level']} {stars_str}")
        lines.append(f"  仓位建议: {consensus['position']}")
        if score and score.get("total", 0) > 0:
            lines.append(f"  量化评分: {score['total']}/100 ({score['rating']}级)  |  TA决策: {consensus.get('action', '?')}")
            lines.append(f"  双重验证: {'✅ 一致' if consensus['stars'] >= 3 else '⚠️ 分歧, 取保守'}")
        lines.append("")

    # ── Phase 1 ──
    lines.append("─── Phase 1: 数据预筛 ───")
    lines.append("")
    if phase1["blocked"]:
        lines.append("⚠️ 该标的在不可交易板块（科创板/创业板/北交所），仅限分析")
        lines.append("")
    if realtime and "price" in realtime:
        lines.append(f"  现价: {realtime['price']} | 涨跌幅: {realtime.get('change', 'N/A')}")
        lines.append(f"  换手: {realtime.get('volume', 'N/A')} | PE: {realtime.get('pe', 'N/A')}")
        lines.append("")
    if score and score.get("total", 0) > 0:
        lines.append(f"  量化评分（trading-combo 100分制）")
        lines.append(f"    均线: {score['ma']}/25 | MACD: {score['macd']}/40 | "
                      f"量价: {score['volume']}/15 | 板块: {score['sector']}/20")
        lines.append(f"    总分: {score['total']}/100 → 评级: {score['rating']} ⭐")
        lines.append("")
    if phase1.get("cyq_rating"):
        lines.append(f"  筹码分布: {phase1['cyq_rating']}")
        lines.append("")

    if brief:
        # 精简版：仅结论
        if phase2 and not phase2.get("error"):
            decision = phase2.get("final_decision", {})
            if isinstance(decision, str):
                lines.append(f"  TA决策: {decision}")
            elif isinstance(decision, dict):
                lines.append(f"  TA决策: {decision.get('action', 'N/A')} | "
                              f"仓位: {decision.get('position_size', 'N/A')}")
        else:
            lines.append("  TA分析: 未运行或出错")
        lines.append("")
        return "\n".join(lines)

    # ── Phase 2 ──
    lines.append("─── Phase 2: 多Agent深度分析 ───")
    lines.append("")
    if phase2 and not phase2.get("error"):
        reports = phase2.get("analyst_reports", {})
        analyst_labels = {
            "market": "🏪 市场分析师", "sentiment": "💬 舆情分析师",
            "news": "📰 新闻分析师", "fundamentals": "📊 基本面分析师",
            "policy": "🏛️ 政策分析师", "hot_money": "🔥 游资追踪师",
            "lockup": "🔓 解禁监控师",
        }
        for key, label in analyst_labels.items():
            report = reports.get(key, "")
            if report and len(report) > 50:
                # 截取精华部分
                summary = report[:300].strip().replace("\n", " ")
                lines.append(f"  {label}")
                lines.append(f"    {summary}{'...' if len(report) > 300 else ''}")
                lines.append("")

        # Quality Gate
        qg = phase2.get("quality_gate", "")
        if qg:
            lines.append(f"  质量门控: {qg[:200].strip()}...")
            lines.append("")

        # Research Manager
        plan = phase2.get("investment_plan", "")
        if plan:
            lines.append(f"  Research Manager 综合研判:")
            lines.append(f"    {plan[:500].strip().replace(chr(10), ' ')}{'...' if len(plan) > 500 else ''}")
            lines.append("")

        # Trader
        trade = phase2.get("trade_plan", "")
        if trade:
            lines.append(f"  Trader 交易方案:")
            lines.append(f"    {trade[:400].strip().replace(chr(10), ' ')}{'...' if len(trade) > 400 else ''}")
            lines.append("")

        # Final Decision
        decision = phase2.get("final_decision", {})
        lines.append("  Portfolio Manager 最终决策:")
        if isinstance(decision, str):
            lines.append(f"    {decision}")
        elif isinstance(decision, dict):
            for k, v in decision.items():
                lines.append(f"    {k}: {v}")
        lines.append("")

        # 量化评分参考对比
        if phase2.get("score_context") and phase2["score_context"] != "{}":
            lines.append("  量化评分参考（AI-Platform trading-combo）: 与TA分析交叉验证")
            lines.append("")
    else:
        err = phase2.get("message", "未知错误") if phase2 else "未运行"
        lines.append(f"  [TA分析未完成] {err}")
        lines.append("")

    # ── Phase 3 ──
    lines.append("─── Phase 3: 执行 & 监控 ───")
    lines.append("")
    if phase3_exec:
        if phase3_exec["executed"]:
            lines.append(f"  模拟盘执行: ✅ 已成交")
            lines.append(f"    动作: {phase3_exec['action']}")
            if phase3_exec.get("order_result"):
                lines.append(f"    结果: {phase3_exec['order_result']['stdout'][:200]}")
        else:
            lines.append(f"  模拟盘执行: ⏭️ {phase3_exec.get('message', '未执行')}")
        lines.append("")

    if phase3_monitor:
        if phase3_monitor.get("deployed"):
            lines.append(f"  监控部署: ✅ 已部署（5分钟/次）")
            lines.append(f"    脚本: {phase3_monitor.get('script_path', '')}")
        elif phase3_monitor.get("errors"):
            lines.append(f"  监控部署: ⚠️ {phase3_monitor['errors'][0]}")
        lines.append("")

    lines.append("─── 可信度标签 ───")
    lines.append(f"  数据源: 腾讯行情 + AI-Platform a-share-data（4层降级）")
    lines.append(f"  分析引擎: TradingAgents-astock 7分析师辩论管道")
    lines.append(f"  时效: {date} | 置信度: {'高' if phase2 and not phase2.get('error') else '中'}")

    # 股池同步状态（新增）
    pool_sync = phase1.get("_pool_sync") or {}
    if pool_sync.get("synced"):
        lines.append(f"  股池同步: ✅ {pool_sync.get('message', '已同步')}")
    elif pool_sync.get("message"):
        lines.append(f"  股池同步: ⚠️ {pool_sync.get('message', '')}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="多Agent投研分析 — AI-Platform × TradingAgents 整合桥梁",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("ticker", nargs="?", help="6位A股代码或股票名称")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="分析日期")
    parser.add_argument("--phase", type=int, default=0, choices=[0, 1, 2, 3],
                        help="仅运行特定阶段（0=全部）")
    parser.add_argument("--batch", help="批量分析：每行一只代码的文件路径")
    parser.add_argument("--pre-score", action="store_true", help="Phase 1: 开启量化评分预筛")
    parser.add_argument("--paper-trade", action="store_true", help="Phase 3: 开启模拟盘下单")
    parser.add_argument("--deploy-monitor", action="store_true", help="Phase 3: 部署cron监控")
    parser.add_argument("--sync-pool", action="store_true", default=True,
                        help="将分析结果自动同步到股池（默认开启）")
    parser.add_argument("--no-sync-pool", action="store_true",
                        help="关闭股池自动同步")
    parser.add_argument("--decision", help="Phase 3: JSON格式预置决策（跳过Phase 2）")
    parser.add_argument("--provider", default="minimax", help="LLM 供应商")
    parser.add_argument("--deep-model", default="MiniMax-M2.7", help="深度思考模型")
    parser.add_argument("--quick-model", default="MiniMax-M2.7-highspeed", help="快速模型")
    parser.add_argument("--paper-account", default="alpha", help="模拟盘账户")
    parser.add_argument("--paper-base-url", default="http://127.0.0.1:18765", help="模拟盘服务地址")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--brief", action="store_true", help="精简输出")
    parser.add_argument("--no-report", action="store_true", help="仅返回决策摘要")
    return parser


def analyze_single(ticker: str, args) -> Dict[str, Any]:
    """对单只标的运行完整分析管道。"""
    # Phase 1: 量化预筛
    phase1 = phase1_prescreen(ticker, args.date)

    phase2 = None
    phase3_exec = None
    phase3_monitor = None

    # Phase 2: 多Agent分析（如果未明确跳过 Phase 2）
    run_phase2 = (args.phase == 0 or args.phase == 2)
    if run_phase2:
        if args.decision:
            # 使用预置决策，跳过 TA 分析
            try:
                decision = json.loads(args.decision)
                phase2 = {
                    "error": False,
                    "final_decision": decision,
                    "analyst_reports": {},
                    "quality_gate": "",
                    "investment_plan": "",
                    "trade_plan": "",
                    "score_context": json.dumps(phase1.get("trading_combo_score", {})),
                }
            except json.JSONDecodeError as e:
                phase2 = {"error": True, "message": f"决策JSON解析失败: {e}"}
        else:
            # 注入 prescore 到 TA 上下文
            prescore = phase1.get("trading_combo_score") if args.pre_score else None
            if TA_DIR and TA_DIR.exists():
                phase2 = phase2_multiagent_analysis(
                    ticker, args.date,
                    provider=args.provider,
                    deep_model=args.deep_model,
                    quick_model=args.quick_model,
                    prescore=prescore,
                )
            else:
                phase2 = {
                    "error": True,
                    "message": "TradingAgents 项目未安装。请先运行 setup.sh",
                }

    # Phase 3: 执行 + 监控
    run_phase3 = (args.phase == 0 or args.phase == 3) and (args.paper_trade or args.deploy_monitor)
    if run_phase3:
        # 取决策
        decision = None
        if args.decision:
            try:
                decision = json.loads(args.decision)
            except json.JSONDecodeError:
                pass
        elif phase2 and not phase2.get("error"):
            decision = phase2.get("final_decision", {})
            if isinstance(decision, str):
                decision = {"action": decision}
        else:
            decision = None

        decision_dict = decision if isinstance(decision, dict) else {}

        if args.paper_trade and decision_dict:
            phase3_exec = phase3_execute(
                decision_dict, ticker,
                paper_account=args.paper_account,
                paper_base_url=args.paper_base_url,
            )

        if args.deploy_monitor and decision_dict:
            entry_price = decision_dict.get("price") or decision_dict.get("entry_price", 0)
            stop_price = decision_dict.get("stop_loss") or decision_dict.get("stop_price", 0)
            shares = decision_dict.get("shares", 0)
            if entry_price and stop_price:
                phase3_monitor = phase3_deploy_monitor(
                    ticker, float(entry_price), float(stop_price),
                    shares=int(shares), account=args.paper_account,
                )

    return {
        "phase1": phase1,
        "phase2": phase2,
        "phase3_exec": phase3_exec,
        "phase3_monitor": phase3_monitor,
        "consensus": None,
        "pool_sync": None,
    }


def _compute_and_sync(phase1, phase2, args):
    """计算融合评级并同步到股池（analyze_single 的收尾步骤）。"""
    result = {"consensus": None, "pool_sync": None}

    score = phase1.get("trading_combo_score")
    decision = (phase2 or {}).get("final_decision", {}) if phase2 else None
    realtime = phase1.get("realtime", {})
    ticker = phase1["ticker"]
    name = realtime.get("name", ticker)

    # 计算融合评级
    consensus = _consensus_rating(score, decision)
    result["consensus"] = consensus

    # 同步到股池
    sync_pool = args.sync_pool and not args.no_sync_pool
    pool_sync = _sync_to_pool(
        ticker, name, consensus, score, decision,
        pool="selected", sync=sync_pool,
    )
    result["pool_sync"] = pool_sync

    return result


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.ticker and not args.batch:
        parser.print_help()
        sys.exit(1)

    # 批量模式
    if args.batch:
        with open(args.batch) as f:
            tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        results = []
        for t in tickers:
            print(f"分析 {t}...", file=sys.stderr)
            result = analyze_single(t, args)
            # 融合评级 + 同步
            sync_r = _compute_and_sync(result["phase1"], result["phase2"], args)
            result["consensus"] = sync_r["consensus"]
            result["pool_sync"] = sync_r["pool_sync"]
            result["phase1"]["_pool_sync"] = sync_r["pool_sync"]
            results.append(result)
            print(f"  {t} 完成", file=sys.stderr)

        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for i, t in enumerate(tickers):
                r = results[i]
                print(format_report(r["phase1"], r["phase2"], r["phase3_exec"], r["phase3_monitor"], brief=args.brief))
                print()
        return

    # 单票模式
    result = analyze_single(args.ticker, args)

    # 融合评级 + 股池同步（P0/P1 优化）
    sync_result = _compute_and_sync(result["phase1"], result["phase2"], args)
    result["consensus"] = sync_result["consensus"]
    result["pool_sync"] = sync_result["pool_sync"]
    # 传递 pool_sync 到 format_report（通过 phase1）
    result["phase1"]["_pool_sync"] = sync_result["pool_sync"]

    if args.json:
        # JSON 输出
        output = result
        if args.no_report:
            # 仅保留决策摘要
            output = {
                "ticker": args.ticker,
                "date": args.date,
                "phase1_summary": {
                    "blocked": result["phase1"]["blocked"],
                    "score": result["phase1"].get("trading_combo_score"),
                    "realtime": result["phase1"].get("realtime"),
                },
                "phase2_decision": result["phase2"].get("final_decision") if result["phase2"] else None,
                "phase3_exec": result["phase3_exec"],
                "phase3_monitor": result["phase3_monitor"],
            }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # 文本报告
        report = format_report(
            result["phase1"], result["phase2"],
            result["phase3_exec"], result["phase3_monitor"],
            brief=args.brief or args.no_report,
        )
        print(report)


if __name__ == "__main__":
    main()
