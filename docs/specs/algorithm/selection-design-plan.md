# 选股设计实施计划

> 规范编号：`SPEC-ALGO-002`
> 权威定义 (SSOT)：[`selection-design-guide.md`](../../guidelines/algorithm/selection-design-guide.md)
> **实施状态**：规划中 (RFC)

## 一、规范核心定位摘要

- 本看板承载「五阶段时序量化交易系统」（盘后初筛 → 大盘熔断 → 竞价动量 → 分时拐点狙击 → 刚性止损）的落地任务分解、分期路线与验收口径。
- 阶段规则、量化数学定义、参数默认值、时点契约与策略配置 Schema 的权威定义一律以 [`selection-design-guide.md`](../../guidelines/algorithm/selection-design-guide.md) 为准，本看板不复述。
- 系统建设总纲见 [`selection-system-specification.md`](../../guidelines/algorithm/selection-system-specification.md)，算法治理门禁见 [`algorithm-governance.md`](../../guidelines/algorithm/algorithm-governance.md)。

## 二、实施任务矩阵

| 任务 | 关联代码路径 | 状态 |
|:---|:---|:---:|
| 阶段0 盘后静态初筛器（日线/问财条件、候选池落盘） | `scripts/core/strategy/post_screener.py`、`output/pools/` | 规划中 |
| 阶段1 大盘 MA20 环境熔断检测器 | `scripts/core/strategy/market_filter.py` | 规划中 |
| 阶段2 集合竞价动量过滤器 | `scripts/core/strategy/auction_picker.py` | 规划中 |
| 阶段3 早盘分时微观拐点检测器（重点） | `scripts/core/strategy/inflection_detector.py` | 规划中 |
| 阶段4 阶梯止损与保本价风控监控器 | `scripts/core/strategy/risk_guard.py` | 规划中 |
| 策略全局参数配置文件 | `config/strategy_morning_surge.yaml` | 规划中 |

## 三、分期落地路线

1. **第一期（核心闭环打通）**：
   * 编写 `post_screener.py` 实现收盘后问财接口对接/本地日线过滤，输出候选池 CSV/JSON 到 `output/pools/`。
   * 编写 `market_filter.py` 接入上证指数 MA20 熔断判定。
   * 分时拐点采用**1分钟 K 线指标**（成交量衰减率 + 分时均线 VWAP 支撑 + 阳线反包）。
2. **第二期（微观拐点精准度优化）**：
   * 接入 3 秒级快照或 Level-2 逐笔委买委卖数据，量化“卖盘枯竭”（卖压撤销率、主动砸盘停滞）与“买盘增加”（大单扫盘成交笔数比）。
3. **第三期（全自动实盘/模拟盘执行）**：
   * 将 09:35~09:40 确认的股票代码直接推送到内部模拟盘或实盘接口（结合 `astock-action-execution` 模块），自动绑定三级止损状态机跟踪。

## 四、验收与验证证据

| 断言 | 验证方式 | 结果 |
|:---|:---|:---:|
| 阶段0 盘后初筛按规则矩阵与参数默认值输出候选池并落盘 `output/pools/` | 盘后执行选股器，核对候选池规模（20~50 只）与落盘文件 | 待验证 |
| 阶段1 大盘跌破门禁均线时打印 `[MARKET_FILTER_BREAK]` 告警且当日不开仓 | 构造空头环境回放，检查日志与开仓记录 | 待验证 |
| 阶段2 集合竞价过滤后精选池收敛至 3~8 只 | 竞价数据回放，核对精选池数量 | 待验证 |
| 阶段3 仅在规定出票窗口内输出买入信号，且 Top-K 不超过 2 只 | 分时数据回放，核对信号时间戳与数量 | 待验证 |
| 阶段4 三级止损阶梯与最低保本卖出价按 SSOT 精算口径执行（向上进位至分位） | 风控监控器接入后逐笔核对止损与保本价 | 待验证 |

## 五、变更日志

| 日期 | 变更摘要 |
|:---|:---|
| 2026-09-20 | 由 docs/guidelines/other/ 中文文档拆分迁入 |