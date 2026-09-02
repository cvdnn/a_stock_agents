# 数据字段目录（Data Field Catalog）

本文件汇总 TradingAgents 系统中所有 CSV 数据文件的完整字段定义，避免跨文件 grep 查找字段名。

## 一、关注股池 (data/watch_pool.csv)

**定位**：潜力扫描，暂不买入。
**管理脚本**：`scripts/pool_manager.py`
**字段数**：11

| # | 字段 | 类型 | 必填 | 说明 | 示例 |
|---|------|------|:----:|------|------|
| 1 | `code` | str | ✓ | 股票代码（纯数字，如 603993） | 603993 |
| 2 | `name` | str | ✓ | 股票名称 | 洛阳钼业 |
| 3 | `added_date` | date | ✓ | 添加到关注池的日期 | 2026-06-22 |
| 4 | `rating` | str | 推荐 | 评级：A(最优先)/B(可关注)/C(观察)/D(回避) | A |
| 5 | `reason` | str | 推荐 | 关注理由 / 选股逻辑 | 铜钴龙头-算力金属直接受益 |
| 6 | `sector` | str | 推荐 | 所属板块（行业名称） | 有色金属 |
| 7 | `pe` | float | 推荐 | 动态市盈率 | 14.9 |
| 8 | `change_pct` | str | 推荐 | 当日涨跌幅 | +8.03% |
| 9 | `fund_flow` | str | 推荐 | 主力资金动向 | 主力+3.17亿 |
| 10 | `entry_condition` | str | ✓ | 入场触发条件（明确写明触发规则） | 回踩MA20不破+缩量60~80% |
| 11 | `market_context` | str | 推荐 | 市场背景（板块表现/大盘环境/资金/估值） | 铜板块+3.13%板块启动 |

**填写准则**：所有字段尽量填满，缺少评级/入场条件/市场背景的股票，后续复盘时无参考价值。

---

## 二、自选股池 (data/selected_pool.csv)

**定位**：准备投资，可分析评估。
**管理脚本**：`scripts/pool_manager.py`
**字段数**：15

| # | 字段 | 类型 | 必填 | 说明 | 示例 |
|---|------|------|:----:|------|------|
| 1 | `code` | str | ✓ | 股票代码 | 600760 |
| 2 | `name` | str | ✓ | 股票名称 | 中航沈飞 |
| 3 | `added_date` | date | ✓ | 添加到自选股池日期 | 2026-06-22 |
| 4 | `rating` | str | ✓ | 评级：A(可重仓)/B(可轻仓)/C(观察)/D(回避) | A |
| 5 | `reason` | str | ✓ | 选股理由 | 军工龙头+筹码集中 |
| 6 | `sector` | str | ✓ | 所属行业 | 航空装备 |
| 7 | `pe` | float | ✓ | 动态市盈率 | 53.3 |
| 8 | `change_pct` | str | ✓ | 当日涨跌幅 | -1.29% |
| 9 | `ma_status` | str | ✓ | 均线状态：多头/震荡/空头 | 多头 |
| 10 | `entry_trigger` | str | ✓ | 入场触发条件（精确可执行） | 回踩MA20不破+放量 |
| 11 | `stop_loss` | float | ✓ | 止损价 | 40.00 |
| 12 | `take_profit` | float | ✓ | 止盈价/目标价 | 46.00 |
| 13 | `risk_level` | str | ✓ | 风险等级：低/中/高 | 中 |
| 14 | `market_context` | str | ✓ | 市场背景（板块表现/资金/大盘） | 航空装备板块+0.18% |
| 15 | `notes` | str | 选填 | 备注 | 缩量回踩可入场 |

---

## 三、当前持仓 (data/positions.csv)

**定位**：已买入持有，实时监控。
**管理脚本**：`scripts/position_manager.py`
**字段数**：18

| # | 字段 | 类型 | 必填 | 说明 | 示例 |
|---|------|------|:----:|------|------|
| 1 | `code` | str | ✓ | 股票代码 | 600760 |
| 2 | `name` | str | ✓ | 股票名称 | 中航沈飞 |
| 3 | `buy_date` | date | ✓ | 买入日期 | 2026-06-22 |
| 4 | `buy_price` | float | ✓ | 买入价 | 47.62 |
| 5 | `qty` | int | ✓ | 持有数量（股） | 1200 |
| 6 | `stop_loss` | float | ✓ | 止损价 | 42.00 |
| 7 | `take_profit` | float | ✓ | 止盈价/目标价 | 52.00 |
| 8 | `sector` | str | ✓ | 所属行业 | 航空装备 |
| 9 | `reason` | str | ✓ | 买入理由 | 军工龙头+筹码集中+回踩确认 |
| 10 | `status` | str | ✓ | 状态：持有/已卖 | 持有 |
| 11 | `strategy` | str | ✓ | 使用策略：趋势共振/缩量回踩/MACD二次金叉/其他 | 趋势共振 |
| 12 | `entry_trigger` | str | ✓ | 入场触发条件 | 回踩MA20不破+放量 |
| 13 | `expected_days` | int | 推荐 | 预期持有天数 | 5 |
| 14 | `risk_level` | str | ✓ | 风险等级：低/中/高 | 中 |
| 15 | `ma_status` | str | ✓ | 入场时均线状态 | 多头 |
| 16 | `market_context` | str | 推荐 | 当时市场背景 | 铜板块+3.13% |
| 17 | `backtest_result` | str | 推荐 | 回测预期结果 | 回测预期+8~15% |
| 18 | `notes` | str | 选填 | 备注 | 分批止盈 |

---

## 四、平仓历史 (data/positions_history.csv)

**定位**：已卖出的交易记录。
**管理脚本**：`scripts/position_manager.py`
**字段数**：16

| # | 字段 | 类型 | 必填 | 说明 | 示例 |
|---|------|------|:----:|------|------|
| 1 | `code` | str | ✓ | 股票代码 | 603993 |
| 2 | `name` | str | ✓ | 股票名称 | 洛阳钼业 |
| 3 | `buy_date` | date | ✓ | 买入日期 | 2026-06-22 |
| 4 | `sell_date` | date | ✓ | 卖出日期 | 2026-06-28 |
| 5 | `buy_price` | float | ✓ | 买入价 | 21.65 |
| 6 | `sell_price` | float | ✓ | 卖出价 | 23.50 |
| 7 | `qty` | int | ✓ | 数量 | 1000 |
| 8 | `pnl` | float | ✓ | 盈亏金额 | 1850 |
| 9 | `pnl_pct` | float | ✓ | 盈亏百分比 | 8.55 |
| 10 | `sector` | str | ✓ | 所属行业 | 有色金属 |
| 11 | `reason` | str | ✓ | 平仓原因 | 止盈 |
| 12 | `strategy` | str | ✓ | 使用策略 | 趋势共振 |
| 13 | `entry_trigger` | str | ✓ | 入场触发条件 | 回踩MA20不破 |
| 14 | `hold_days` | int | ✓ | 持有天数 | 6 |
| 15 | `risk_level` | str | ✓ | 风险等级 | 中 |
| 16 | `notes` | str | 选填 | 备注 | 达到目标价 |

---

## 五、完整交易生命周期

```
关注股池(watch_pool.csv, 11字段)
    │ pool_manager.py upgrade
    ▼
自选股池(selected_pool.csv, 15字段)
    │ position_manager.py open（自动从自选池移除）
    ▼
持仓(positions.csv, 18字段)
    │ position_manager.py close（自动平仓联动）
    ▼
平仓历史(positions_history.csv, 16字段)
```

---

## 六、账号过滤

`_is_blocked(code)` — 屏蔽 688/689/30/8/4 前缀的股票。

---

## 七、CSV 操作提醒

- 编码：UTF-8，可直接 Excel/WPS 编辑
- 保持列标题顺序不变
- 新增字段需同步更新 Python 脚本
- 用 CLI 工具而非手动编辑来增删行
