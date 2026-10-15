# -*- coding: utf-8 -*-
"""
ta_entry_monitor.py - TradingAgents 入场/止损 cron 监控脚本生成器

提供 render_monitor_script 函数，基于模板生成单只股票的监控脚本。
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATE_PATH = TEMPLATE_DIR / "ta_entry_monitor.py.template"


def render_monitor_script(ticker: str,
                          entry_price: float,
                          stop_price: float,
                          account: str = "alpha",
                          shares: int = 0,
                          mode: str = "stop") -> str:
    """基于监控模板渲染生成 Python 监控脚本。

    Args:
        ticker: 6位 A股代码
        entry_price: 入场基准价
        stop_price: 止损价
        account: 账户名
        shares: 持仓股数
        mode: 模式 'stop', 'entry' 或 'all'

    Returns:
        生成的监控脚本代码字符串
    """
    if not TEMPLATE_PATH.exists():
        # Fallback to skills template if not found in core
        fallback = Path(__file__).resolve().parent.parent.parent / "skills" / "ta-multi-agent-analysis" / "templates" / "ta_entry_monitor.py"
        if fallback.exists():
            template = fallback.read_text(encoding="utf-8")
        else:
            raise FileNotFoundError(f"Monitor template not found at {TEMPLATE_PATH} or {fallback}")
    else:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

    rendered = template.replace("{{TICKER}}", ticker) \
                       .replace("{{ENTRY_PRICE}}", str(entry_price)) \
                       .replace("{{STOP_PRICE}}", str(stop_price)) \
                       .replace("{{ACCOUNT}}", account)

    # 替换运行模式
    rendered = rendered.replace(
        'MODE = os.environ.get("MONITOR_MODE", "stop")',
        f'MODE = os.environ.get("MONITOR_MODE", "{mode}")'
    )
    return rendered
