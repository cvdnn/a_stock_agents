# -*- coding: utf-8 -*-
"""
Subcommand handlers for core.cli.
Modularized for high maintainability, observability, and clean separation of concerns.
"""
from core.commands.data_cmds import (
    cmd_balance,
    cmd_batch,
    cmd_cyq,
    cmd_data_quote,
    cmd_data_technical,
    cmd_events,
    cmd_market,
)
from core.commands.model_cmds import (
    cmd_analyze,
    cmd_deploy_monitor,
    cmd_evaluate,
    cmd_multi_factor,
    cmd_score,
    cmd_screen,
    cmd_trapped,
)
from core.commands.strategy_cmds import (
    cmd_action_plan,
    cmd_downside,
    cmd_golden_cross,
    cmd_grid,
    cmd_intent,
    cmd_mean_reversion,
    cmd_portfolio_risk,
    cmd_risk,
    cmd_vol_breakout,
)
from core.commands.backtest_cmds import (
    cmd_backtest,
    cmd_multi_backtest,
)
from core.commands.portfolio_cmds import (
    cmd_config_market,
    cmd_config_paths,
    cmd_pool_dispatch,
    cmd_pos_dispatch,
    cmd_report,
    cmd_skill_list,
)

__all__ = [
    "cmd_data_quote",
    "cmd_data_technical",
    "cmd_batch",
    "cmd_events",
    "cmd_cyq",
    "cmd_balance",
    "cmd_market",
    "cmd_score",
    "cmd_analyze",
    "cmd_multi_factor",
    "cmd_trapped",
    "cmd_risk",
    "cmd_golden_cross",
    "cmd_portfolio_risk",
    "cmd_action_plan",
    "cmd_intent",
    "cmd_downside",
    "cmd_screen",
    "cmd_evaluate",
    "cmd_backtest",
    "cmd_multi_backtest",
    "cmd_mean_reversion",
    "cmd_grid",
    "cmd_vol_breakout",
    "cmd_deploy_monitor",
    "cmd_config_paths",
    "cmd_config_market",
    "cmd_skill_list",
    "cmd_report",
    "cmd_pool_dispatch",
    "cmd_pos_dispatch",
]
