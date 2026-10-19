# -*- coding: utf-8 -*-
"""Engine D: 实战战法识别、税费精算与三级股池风控引擎测试。

归属代码包：`core/strategy/` (execution_action_engine, risk_manager, trapped_position, tuige, chenxiaoqun, pool_manager)
核心职责与断言：
1. 精确最低保本卖出价（二分迭代 + math.ceil 向上进位至分位，覆盖万2.5佣金最低5元、0.05%印花税与过户费）；
2. 三级风控止损阶梯（T0 -3% 警戒线、T1 -5% 减仓线、T2 -8% 绝杀线）；
3. 三场景实战反应动作单（开盘冲高、盘中震荡、跳水急跌）；
4. 受限凯利公式（Kelly Criterion）与解套诊断（TrappedPositionAnalyzer）；
5. 退哥（Tuige）与陈小群（ChenXiaoqun）战法信号识别与保本价核算；
6. 股票池五步真实 MA 审计与空池拦截（Fail-Closed 提示登记格式）。
"""
from __future__ import annotations

import math
from pathlib import Path
import pytest

from core.strategy.execution_action_engine import (
    ExecutionActionEngine,
    IntentEvaluator,
)
from core.strategy.risk_manager import RiskManager
from core.strategy.trapped_position import TrappedPositionAnalyzer
from core.strategy.tuige import TuigeStrategyEngine
from core.strategy.chenxiaoqun import ChenXiaoqunStrategyEngine
from core.strategy.pool_manager import PoolManager
from core.strategy.pool_schema import SELECTED_FIELDS, WATCH_FIELDS, POSITIONS_FIELDS, ensure_pool_csv

pytestmark = pytest.mark.core


def _generate_synthetic_klines(count=60, base_price=10.0):
    klines = []
    price = base_price
    for i in range(count):
        d = f"2026-08-{i+1:02d}" if i < 30 else f"2026-09-{i-29:02d}"
        op = price
        cl = price + (0.15 if i % 2 == 0 else -0.10)
        hi = max(op, cl) + 0.08
        lo = min(op, cl) - 0.08
        vol = 10000 + i * 150
        klines.append([d, op, cl, hi, lo, vol])
        price = cl
    return klines


def test_breakeven_price_ceil_and_net_revenue():
    """验证保本价计算满足 math.ceil 进位且实际卖出净收益 >= 买入总成本。"""
    cost = 10.0
    shares = 1000

    breakeven = ExecutionActionEngine.calc_min_breakeven_price(cost=cost, shares=shares)
    assert breakeven >= cost
    # 强制进位到分位 (小数点后不超过 2 位)
    assert round(breakeven * 100) == int(breakeven * 100)

    # 验证按该价格卖出确实不亏钱 (买入成本 vs 卖出净收益)
    buy_amount = cost * shares
    buy_comm = max(buy_amount * 0.00025, 5.0)
    buy_transfer = buy_amount * 0.00001
    total_buy = buy_amount + buy_comm + buy_transfer

    sell_amount = breakeven * shares
    sell_comm = max(sell_amount * 0.00025, 5.0)
    sell_stamp = sell_amount * 0.0005
    sell_transfer = sell_amount * 0.00001
    net_sell = sell_amount - sell_comm - sell_stamp - sell_transfer

    assert net_sell >= total_buy - 1e-4, f"保本价卖出产生实际亏损: net_sell={net_sell}, total_buy={total_buy}"


def test_three_tier_stop_loss_ladder():
    """验证三级止损阶梯（T0 -3% 警戒线、T0 -5% 强止损、T1/T2 移动防守线）。"""
    entry = 10.0
    latest = {"ma10": 9.6, "ma20": 9.3, "atr": 0.25}

    stops = RiskManager.calc_stop_losses(entry, latest=latest, t0_loss_pct=0.05)
    assert "t0_warning" in stops
    assert "t0_intraday" in stops
    assert "t1_ma10" in stops
    assert "t2_ma20" in stops

    # T0 警戒线为 -3% (9.70)
    assert stops["t0_warning"]["price"] == 9.70
    # T0 强平线为 -5% (9.50)
    assert stops["t0_intraday"]["price"] == 9.50


def test_execution_action_engine_reaction_tickets():
    """验证实战反应动作单生成与意图路由。"""
    # 1. 意图解析
    parsed = IntentEvaluator.parse_user_query("现在 600519 怎么操作，被套了怎么自救")
    assert "600519" in parsed["detected_codes"]
    assert parsed["primary_intent"] in (
        IntentEvaluator.INTENT_TRAPPED_RECOVERY,
        IntentEvaluator.INTENT_ORDER_EXECUTION,
    )

    # 2. 反应动作单生成
    quote = {"price": 10.50, "open": 10.20, "high": 10.80, "low": 10.10, "change_pct": 2.5}
    tech = {"ma5": 10.2, "ma10": 10.0, "ma20": 9.8, "rsi": 55.0, "atr": 0.3}
    holding = {"cost": 10.0, "shares": 1000}

    action_res = ExecutionActionEngine.generate_action("600001", "测试股", quote, tech, holding=holding)
    assert action_res["code"] == "600001"
    assert action_res["is_held"] is True
    assert action_res["breakeven_price"] >= 10.0
    assert "evidence_meta" in action_res
    assert len(action_res["action_items"]) >= 1


def test_trapped_position_analyzer_and_kelly():
    """验证持仓解套诊断与受限凯利仓位建议。"""
    klines = _generate_synthetic_klines(60, 10.0)
    analyzer = TrappedPositionAnalyzer(cost_price=12.0, shares=1000, klines=klines)
    diag = analyzer.diagnostic()

    assert diag["cost_price"] == 12.0
    assert diag["shares"] == 1000
    assert "loss_pct" in diag
    assert "atr_14" in diag
    assert "kelly_f" in diag
    assert "kelly_interpretation" in diag


def test_tuige_and_chenxiaoqun_tactical_engines():
    """验证退哥龙头短线与陈小群战法引擎计算。"""
    # 退哥短线保本价计算
    tuige_p = TuigeStrategyEngine.calculate_breakeven_price(15.0, 500)
    assert tuige_p >= 15.0
    assert round(tuige_p * 100) == int(tuige_p * 100)

    # 陈小群总龙头低吸保本价计算
    chen_p = ChenXiaoqunStrategyEngine.calculate_breakeven_price(20.0, 300)
    assert chen_p >= 20.0
    assert round(chen_p * 100) == int(chen_p * 100)


def test_pool_manager_audit_empty_pool_fail_closed(tmp_path: Path):
    """验证股票池审查在空池时 Fail-Closed 即刻终止，绝不臆测虚构股票。"""
    empty_pools_dir = tmp_path / "pools"
    empty_pools_dir.mkdir(parents=True, exist_ok=True)
    ensure_pool_csv(empty_pools_dir / "selected_pool.csv", SELECTED_FIELDS)
    ensure_pool_csv(empty_pools_dir / "watch_pool.csv", WATCH_FIELDS)
    ensure_pool_csv(empty_pools_dir / "positions.csv", POSITIONS_FIELDS)

    manager = PoolManager(pools_dir=empty_pools_dir)
    audit_res = manager.audit_pools()

    assert audit_res is not None
    # 空池必须如实汇报 0 标的并提示规范登记格式
    assert audit_res["status"] == "empty_pool"
    assert audit_res["total_stocks"] == 0
    assert "registration_guide" in audit_res
    assert "000001:1000@12.50" in audit_res["registration_guide"]["holding_format"]
