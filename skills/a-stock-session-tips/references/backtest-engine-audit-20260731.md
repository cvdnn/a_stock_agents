# paper_trading 回测引擎深度审查

> Session 2026-07-31: 逐行审查 engine.py run_backtest() + 成本模型 + 策略接口 + 数据层 + 验证脚本

## 一、run_backtest() 逐行审查 (engine.py L489-572)

### 数据获取 (L490-491)
- `bars = market_data.get_history(symbol, start, end, count)`
- 数据源链: 腾讯K线 → 新浪K线 → 东财akshare (3层降级)
- 问题: 依赖外部网络, 回测不可离线运行, 无本地缓存

### 指标计算 (L500-506)
- MA快慢线 + RSI 在回测主循环内用 pandas rolling 计算
- 问题: 策略指标内嵌于回测主循环, 非策略模块化

### 信号回路 (L507-528) — 核心问题区
- `buy_and_hold`: 仅首日买入
- `sma_cross`: 快线穿越慢线 → buy/sell
  - **look-ahead偏差**: 用当前bar收盘 vs 前bar收盘判定穿越, 但当日收盘价成交
  - A股T+1下实际应是当日信号 → 次日开盘价成交
  - 当前方式使回测收益系统性偏高
- `rsi_revert`: RSI<阈值且qty==0买入 / RSI>阈值且qty>0卖出
  - 只允许满仓/空仓切换, 不支持加减仓
- `else: raise` — 3种策略硬编码, 无策略接入接口

### 撮合执行 (L529-550)
- 涨跌停过滤: 基于前日收盘推算, 涨停买不进/跌停卖不出 (正确)
- 买入: `lot_qty = int(cash/price//100)*100` (全仓)
- 卖出: qty全部 (全仓)
- 成本: calc_commission + calc_tax
- 问题: 无滑点建模(成交价=收盘价), 全仓进出无仓位管理

### 资金曲线 (L551-572)
- `equity_curve.append(每日净值)` 但 L571 `equity_curve[-60:]` 截断
- 仅输出: total_return / max_drawdown / win_count / loss_count
- 缺失: 年化/夏普/卡尔玛/索提诺/换手率/盈亏比/超额收益/最大连续亏损

## 二、成本模型审查

| 项目 | engine.py | stock-report-html模板 | 实际行业 | 位置 |
|------|-----------|---------------------|---------|------|
| 佣金率 | 万3 (0.03%) | 万1.2 (0.012%) | 万2.5可配 | `calc_commission()` L72-74 |
| 最低佣金 | 5元 | 5元 | 5元 | 同上 |
| 印花税 | 万10 (0.1%) | 万5 (0.05%) | 万5(2023.8.28起) | `calc_tax()` L77-78 |
| 过户费 | 万0.1(沪市) | 万0.1(沪深) | 万0.1 | `calc_transfer_fee()` L66-69 |
| 滑点 | 无 | 无 | ~0.1% | 缺失 |

跨技能不一致: engine.py佣金万3 vs report模板万1.2, 修改时应统一为可配置参数。

## 三、策略接口审查

当前架构: 策略逻辑硬编码在 `run_backtest()` 的 if-else 中 (L510-528)

- CLI入口 `choices=["buy_and_hold", "sma_cross", "rsi_revert"]` 硬编码
- HTTP路由 `POST /backtest` 透传 strategy 字符串, 无注册机制
- 无法接入: combo_scorer / trend_pullback / MACD二次金叉 / 布林回归 / 动量排名

修改方向: 新建 `backtest_strategies.py`, 抽象 BacktestStrategy 基类:
```python
class BacktestStrategy:
    def on_bar(self, i, bar, bars, position, cash) -> Signal: ...
    def params(self) -> dict: ...
```

## 四、数据层审查 (market_data.py)

| 特性 | paper_trading | a-stocks data_bridge |
|------|--------------|---------------------|
| 数据源 | 腾讯→新浪→东财 | 腾讯→新浪→proxy |
| 前复权 | 不一致(腾讯qfq/新浪不复权) | 统一前复权(qfq) |
| 批量拉取 | 无 | batch_quote |
| 离线缓存 | 无 | 无 |
| 依赖 | akshare+requests | 仅urllib |
| Python兼容 | ≥3.10(list[str]语法) | ≥3.9 |

前复权不一致问题: 降级到新浪时数据不连续(除权缺口), 影响回测准确性。

## 五、回测输出覆盖度

| 指标 | 业界标准 | 当前输出 | 状态 |
|------|---------|---------|------|
| 总收益率 | 核心 | ✅ | 完整 |
| 年化收益率 | 核心 | ❌ | 无250交易日换算 |
| 最大回撤 | 核心 | ✅ | 但无回撤持续天数 |
| 夏普比率 | 核心 | ❌ | 无波动率计算 |
| 卡尔玛比率 | 常用 | ❌ | |
| 索提诺比率 | 常用 | ❌ | |
| 胜率 | 核心 | ⚠️ | win/loss有但无百分比 |
| 盈亏比 | 核心 | ❌ | 无平均盈利/亏损 |
| 换手率 | 常用 | ❌ | |
| 最大连续亏损 | 常用 | ❌ | |
| 超额收益 | 核心 | ❌ | 无buy_hold对比 |
| 资金曲线 | 核心 | ⚠️ | 截断60条 |
| 收益分布偏度/峰度 | 高级 | ❌ | |

覆盖: 2/15完整(13%), 3/15部分(20%), 10/15缺失(67%)

## 六、架构级问题

1. **回测耦合HTTP服务**: CLI→REST→engine, 需先启动paper_trading_service才能回测
2. **信号look-ahead偏差**: 当日收盘信号+当日收盘成交 → 回测收益系统性偏高
3. **全仓进出**: 无仓位管理, 无法模拟分批建仓/减仓/止损
4. **单股回测**: 不支持多股组合, 无法回测动量排名选股
5. **Python兼容**: market_data.py L82 `list[str]` 需Python 3.10+

## 七、验证脚本评估

| 脚本 | 测试内容 | 回测覆盖 | 可离线 |
|------|---------|---------|--------|
| rule_regression_check.py | 价格精度/市场时段/陈旧行情/过户费 | 0% | ✅ |
| real_stock_rule_validation.py | 22只股票涨跌停规则 | 0% | ❌ 需网络 |
| backtest_batch_validation.py | 20只股票sma_cross回测不崩溃 | 仅结构验证 | ❌ 需网络 |

缺失: 回测指标正确性单元测试(已知输入→预期输出)

## 八、修改方案 (Phase 1-6)

| Phase | 内容 | 优先级 | 工作量 | 修改文件 |
|-------|------|--------|--------|---------|
| 1 | 策略接口抽象 | P0 | ~80行 | 新建 backtest_strategies.py |
| 2 | 回测指标补全 | P0 | ~150行 | 新建 backtest_metrics.py |
| 3 | 成本模型校正 | P1 | ~30行 | 修改 engine.py L72-78 |
| 4 | 信号T+1修正 | P1 | ~20行 | 修改 engine.py L510-549 |
| 5 | equity_curve去截断 | P2 | ~5行 | 修改 engine.py L571 |
| 6 | 离线模式 | P2 | ~40行 | 新建 backtest_offline.py |

### Phase 1: 策略接口抽象
```python
# backtest_strategies.py
class BacktestStrategy:
    def on_bar(self, i, bar, bars, position, cash) -> Signal: ...
    def params(self) -> dict: ...

class SmaCrossStrategy(BacktestStrategy): ...
class RsiRevertStrategy(BacktestStrategy): ...
class BuyHoldStrategy(BacktestStrategy): ...
class BollReversionStrategy(BacktestStrategy): ...  # 新策略
class ComboScorerStrategy(BacktestStrategy): ...   # 接a-stocks
```
修改 engine.py run_backtest() 接收 strategy 对象而非字符串。

### Phase 2: 回测指标补全
```python
# backtest_metrics.py
def calc_metrics(equity_curve, trades, initial_cash, days):
    annual_return = (final/initial)^(250/days) - 1
    daily_returns = diff(equity_curve)/prev
    sharpe = mean(excess) / std(excess) * sqrt(250)
    calmar = annual_return / max_drawdown
    sortino = mean(excess) / std(downside) * sqrt(250)
    turnover = sum(trade_amounts)/initial/years
    profit_factor = avg_win / avg_loss
    max_consecutive_loss = ...
    avg_holding_days = ...
```

### Phase 3: 成本模型校正
- `calc_tax`: `amount * 0.001` → `amount * 0.0005`
- `calc_commission`: `amount * 0.0003` → 可配置, 默认 `0.00025`
- 新增滑点: 买入 `price * 1.001` / 卖出 `price * 0.999`

### Phase 4: 信号T+1修正
- 信号在 bar[i] 产生 → 成交在 bar[i+1] 的 open 价
- 而非当前: 信号在 bar[i] 成交在 bar[i] 的 close 价

### Phase 5: equity_curve去截断
- L571: `equity_curve[-60:]` → `equity_curve` (完整)
- 可选: `--save-csv` 参数输出CSV

### Phase 6: 离线模式
- 新建 backtest_offline.py
- 接受本地K线CSV文件
- 可与 a-stocks 的 data_bridge.tencent_kline 对接

## 九、方案总评

- 可行性: ★★★★☆ (基于正确骨架扩展, 风险可控)
- 工作量: ★★★☆☆ (~450行新增+80行修改, 2-3个session)
- 风险: ★★☆☆☆ (Phase4 T+1修正可能使已有策略收益显著下降)
- 紧迫性: ★★★★★ (无回测=无验证, 所有新策略开发都受阻塞)

实施顺序: Phase1 → Phase2 → Phase3+4合并 → Phase5 → Phase6