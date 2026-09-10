# Skill 能力真实性验收台账

> 日期：2026-09-10  
> 范围：P0 / R2a 止血，不代表 P1 统一执行器或 P6 工作台投射完成。

判定口径：`connected` 表示处理器调用现有 core 后端且失败时显式报错；`reference` 仅返回知识材料，不声称执行了分析；`unavailable` 表示尚未接通，正式路径返回 `CAPABILITY_NOT_IMPLEMENTED`。`unavailable` 不是能力完成。

| Skill ID | 当前类型 | 生产事实源 | P0 验收 | 后续缺口 |
|---|---|---|---|---|
| `astock-data-feed` | connected | `DataBridge`、`calc_all` | 无行情/K线时 error | P1 统一 ExecutionResult |
| `astock-platform-evaluate` | connected | `DataBridge`、`ComboScorer` | 缺数据/总分时 error | P6 页面投射 |
| `astock-screener-5a` | connected | `DynamicUniverseEngine`、`StockScreener` | 异常不伪造候选 | P1 超时与证据包 |
| `astock-pool-dashboard` | connected | `PoolManager` | 后端异常时 error | 统一股池 schema |
| `astock-trade-paper` | conditional | `AccountManager`（若可用） | 缺失适配器时 unavailable，不模拟成交 | 接入统一模拟盘账户接口 |
| `astock-strategy-mainboard` | connected | `DailyDecisionEngine` | 后端异常时 error | 完整参数/证据验收 |
| `astock-quant-engine` | unavailable | none | `CAPABILITY_NOT_IMPLEMENTED` | 接入量化 pipeline |
| `astock-agent-debate` | conditional | `TechnicalAnalysisOrchestrator`（若可用） | 异常时 unavailable，无固定多空比 | P4 多智能体证据隔离 |
| `astock-strategy-tuige` | reference | 本地规则文本 | 标记 `type=reference`，不称已校验 | 接入场景检查器 |
| `astock-strategy-macd` | connected | `DataBridge`、`calc_all` | K线不足时 error | 形态证据 schema |
| `astock-action-execution` | connected | `ExecutionActionEngine`、`RiskManager` | 无实时行情时 error，无 10 元回退 | 费率配置确认门禁 |
| `astock-pool-audit` | unavailable | none | `CAPABILITY_NOT_IMPLEMENTED` | 接入审计/修复流水线 |
| `astock-report-archive` | unavailable | none | `CAPABILITY_NOT_IMPLEMENTED` | 接入归档服务与产物证据 |
| `astock-report-html` | unavailable | none | `CAPABILITY_NOT_IMPLEMENTED` | 接入 HTML 报告生成器 |
| `astock-knowledge-tips` | reference | 本地知识文本 | 标记 `type=reference` | 引用来源版本化 |
| `astock-model-validation` | unavailable | none | `CAPABILITY_NOT_IMPLEMENTED`，无固定 IC | 接入滚动样本外验证 |
| `astock-meta-routing` | reference | 本地路由规则 | 标记 `type=reference` | P1 路由策略执行化 |

## REST 投射边界

- `market.indices`、`market.sentiment`、`market.kline`、`market.ranks`、`portfolio.analysis` 尚无已验收后端，返回结构化 HTTP 503。
- `portfolio.overview` 只读取本地持仓 CSV，不进行行情补值；空文件返回 `status=empty`。
- `watchlist` 只投射 `config/stock_pools.yaml` 中的声明，不生成价格、资金流或 AI 结论。
- `monitor.stream` 在没有运行时监控服务时返回 `status=not_running` 和空事件。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capability_truthfulness.py tests/test_market_data_api.py tests/test_server_suite.py -q -p no:cacheprovider
```
