# -*- coding: utf-8 -*-
"""Engine E: A股仿真撮合、多股回测与样本外检验引擎测试。

归属代码包：`core/paper_trading/` (multi_backtest_engine, engine, backtest_metrics, rolling_oos)
核心职责与断言：
1. 涨跌停封板限制与主板/创业板/科创板/北交所分板判定（10%/20%/30%）；
2. 仿真账户（AccountPortfolio）T+1 股份冻结与买卖交割生命周期；
3. 回测指标计算（calc_metrics）：夏普比率、最大回撤、胜率、盈亏比与除零安全保护；
4. 滚动样本外（Rolling OOS）检验与过拟合三重警报系统：
   - 警报 1：样本内夏普 > 3.5；
   - 警报 2：样本内胜率 > 75.0%；
   - 警报 3：IS-to-OOS 收益衰减 > 50.0%。
"""
from __future__ import annotations

import pytest

from core.paper_trading.multi_backtest_engine import (
    AccountPortfolio,
    MultiBacktestEngine,
)
from core.paper_trading.backtest_metrics import calc_metrics, _safe_div
from core.paper_trading.rolling_oos import RollingOOSValidator

pytestmark = pytest.mark.core


def test_board_specific_limit_prices():
    """验证分板涨跌停价格计算（主板 10%、创业板/科创板 20%、北交所 30%）。"""
    prev_close = 10.0

    # 1. 主板 600xxx / 000xxx: 10%
    up_sh, down_sh = MultiBacktestEngine._limit_prices("600519", prev_close)
    assert up_sh == 11.0 and down_sh == 9.0

    up_sz, down_sz = MultiBacktestEngine._limit_prices("000001", prev_close)
    assert up_sz == 11.0 and down_sz == 9.0

    # 2. 科创板 688xxx / 创业板 300xxx: 20%
    up_star, down_star = MultiBacktestEngine._limit_prices("688001", prev_close)
    assert up_star == 12.0 and down_star == 8.0

    up_chinext, down_chinext = MultiBacktestEngine._limit_prices("300750", prev_close)
    assert up_chinext == 12.0 and down_chinext == 8.0

    # 3. 北交所 83xxxx / 92xxxx: 30%
    up_bse, down_bse = MultiBacktestEngine._limit_prices("830001", prev_close)
    assert up_bse == 13.0 and down_bse == 7.0


def test_account_portfolio_t1_restriction():
    """验证账户仿真撮合中的 T+1 可用股份硬约束与日终解冻结算。"""
    portfolio = AccountPortfolio(initial_cash=100_000.0)
    assert portfolio.cash == 100_000.0

    # 当日买入 1000 股
    cost, shares = 10.0, 1000
    atr = 0.3
    ok_buy = portfolio.buy("600519", shares=shares, price=cost, date="2026-10-19", atr=atr)
    assert ok_buy is True
    assert portfolio.cash < 100_000.0

    pos = portfolio.positions.get("600519")
    assert pos is not None
    assert pos["shares"] == 1000
    # T 日当日买入可用股份为 0 (T+1 约束)
    assert pos["available_shares"] == 0

    # 当日尝试卖出必须被拒绝
    can_sell_t0 = portfolio.sell("600519", shares=1000, price=11.0, date="2026-10-19")
    assert can_sell_t0 is False

    # 模拟进入次日日终结算 (T+1 解冻)
    portfolio.end_of_day_settlement()
    assert pos["available_shares"] == 1000

    # 次日可正常卖出
    can_sell_t1 = portfolio.sell("600519", shares=1000, price=11.0, date="2026-10-20")
    assert can_sell_t1 is True
    assert "600519" not in portfolio.positions


def test_backtest_metrics_calculation_and_safe_div():
    """验证回测绩效指标计算与除零边界防护。"""
    assert _safe_div(10.0, 0.0) == 0.0
    assert _safe_div(10.0, 2.0) == 5.0

    equity_curve = [
        {"date": "2026-01-01", "equity": 100000.0},
        {"date": "2026-01-02", "equity": 102000.0},
        {"date": "2026-01-03", "equity": 101000.0},
        {"date": "2026-01-04", "equity": 105000.0},
        {"date": "2026-01-05", "equity": 108000.0},
    ]
    trades = [
        {"action": "buy", "price": 10.0, "qty": 1000, "date": "2026-01-01", "amount": 10000.0},
        {"action": "sell", "price": 10.8, "qty": 1000, "profit": 800.0, "date": "2026-01-05", "amount": 10800.0},
    ]
    metrics = calc_metrics(
        equity_curve=equity_curve,
        trades=trades,
        initial_cash=100000.0,
        final_equity=108000.0,
        days=5,
    )

    assert "total_return_pct" in metrics
    assert "max_drawdown_pct" in metrics
    assert "sharpe_ratio" in metrics
    assert "win_rate_pct" in metrics
    assert metrics["total_return_pct"] == 8.0
    assert metrics["max_drawdown_pct"] >= 0.0
    assert metrics["win_rate_pct"] == 100.0


def test_rolling_oos_validator_and_overfitting_alarms():
    """验证滚动样本外 (Rolling OOS) 划分、衰减计算与三重过拟合警报。"""
    # 1. 样本划分 (IS vs OOS)
    klines = [{"date": f"2026-01-{i:02d}", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1000} for i in range(1, 101)]
    is_sample, oos_sample = RollingOOSValidator.split_samples(klines, oos_ratio=0.3)
    assert len(is_sample) == 70
    assert len(oos_sample) == 30

    # 2. 衰减精算
    decay_normal = RollingOOSValidator.calculate_decay(10.0, 8.0)
    assert decay_normal == 20.0  # (10 - 8) / 10 = 20%

    decay_sharp = RollingOOSValidator.calculate_decay(10.0, 2.0)
    assert decay_sharp == 80.0  # (10 - 2) / 10 = 80% > 50%

    # 3. 三重过拟合警报触发测试
    # Case A: 正常稳健模型 (无警报)
    is_normal = {"sharpe_ratio": 1.8, "win_rate_pct": 62.0, "annual_return": 25.0}
    oos_normal = {"sharpe_ratio": 1.5, "win_rate_pct": 58.0, "annual_return": 20.0}
    eval_normal = RollingOOSValidator.evaluate_overfitting(is_normal, oos_normal)
    assert eval_normal["overfitting_suspected"] is False
    assert len(eval_normal["warnings"]) == 0

    # Case B: 触发警报 1 (Sharpe > 3.5)
    is_extreme_sharpe = {"sharpe_ratio": 4.2, "win_rate_pct": 65.0, "annual_return": 30.0}
    eval_sharpe = RollingOOSValidator.evaluate_overfitting(is_extreme_sharpe, oos_normal)
    assert eval_sharpe["overfitting_suspected"] is True
    assert eval_sharpe["triple_alerts"]["sharpe_gt_3_5"] is True
    assert any("夏普比率异常" in w for w in eval_sharpe["warnings"])

    # Case C: 触发警报 2 (WinRate > 75%)
    is_extreme_win = {"sharpe_ratio": 2.5, "win_rate_pct": 88.0, "annual_return": 30.0}
    eval_win = RollingOOSValidator.evaluate_overfitting(is_extreme_win, oos_normal)
    assert eval_win["overfitting_suspected"] is True
    assert eval_win["triple_alerts"]["win_rate_gt_75"] is True
    assert any("胜率异常" in w for w in eval_win["warnings"])

    # Case D: 触发警报 3 (收益衰减 > 50%)
    oos_collapsed = {"sharpe_ratio": 0.5, "win_rate_pct": 45.0, "annual_return": 5.0}
    eval_decay = RollingOOSValidator.evaluate_overfitting(is_normal, oos_collapsed)
    assert eval_decay["overfitting_suspected"] is True
    assert eval_decay["triple_alerts"]["decay_gt_50"] is True
    assert any("收益衰减严重" in w for w in eval_decay["warnings"])
