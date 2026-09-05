# -*- coding: utf-8 -*-
"""
A股市场交易日历与交易时段门控 (Schedule Gate)

统一处理:
1. 交易日判定 (排除周末)
2. 交易时段判定 (连续竞价: 09:30-11:30, 13:00-15:00; 集合竞价: 09:15-09:25)
3. 细分交易时段状态获取
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Optional


def is_trading_day(dt: Optional[datetime] = None) -> bool:
    """判断是否为法定交易日 (周一至周五，周末排除)。"""
    check_dt = dt or datetime.now()
    return check_dt.weekday() < 5


def is_market_hours(
    dt: Optional[datetime] = None,
    include_auction: bool = False,
    now: Optional[datetime] = None,
) -> bool:
    """判断当前时间是否处于 A 股市场盘中交易时段。

    Args:
        dt: 检查时间，默认为当前本地时间。
        include_auction: 是否包含 09:15-09:25 早盘集合竞价时段。默认为 False。
        now: dt 的别名参数，兼容不同调用习惯。

    Returns:
        bool: 处于交易时间返回 True，否则返回 False。
    """
    check_dt = dt or now or datetime.now()
    if not is_trading_day(check_dt):
        return False


    t = check_dt.time()
    
    # 早盘时段
    morning_start = time(9, 15) if include_auction else time(9, 30)
    if morning_start <= t <= time(11, 30):
        return True

    # 午盘时段
    if time(13, 0) <= t <= time(15, 0):
        return True

    return False


def get_market_phase(dt: Optional[datetime] = None) -> str:
    """获取当前市场所处的具体运行阶段。

    Returns:
        str: 阶段标识 (WEEKEND, PRE_MARKET, CALL_AUCTION, CONTINUOUS_MORNING, 
             LUNCH_BREAK, CONTINUOUS_AFTERNOON, CLOSING_AUCTION, POST_MARKET)
    """
    check_dt = dt or datetime.now()
    if not is_trading_day(check_dt):
        return "WEEKEND"

    t = check_dt.time()
    if t < time(9, 15):
        return "PRE_MARKET"
    elif time(9, 15) <= t < time(9, 25):
        return "CALL_AUCTION"
    elif time(9, 25) <= t < time(9, 30):
        return "PRE_OPEN_BUFFER"
    elif time(9, 30) <= t <= time(11, 30):
        return "CONTINUOUS_MORNING"
    elif time(11, 30) < t < time(13, 0):
        return "LUNCH_BREAK"
    elif time(13, 0) <= t < time(14, 57):
        return "CONTINUOUS_AFTERNOON"
    elif time(14, 57) <= t <= time(15, 0):
        return "CLOSING_AUCTION"
    else:
        return "POST_MARKET"


__all__ = ["is_trading_day", "is_market_hours", "get_market_phase"]
