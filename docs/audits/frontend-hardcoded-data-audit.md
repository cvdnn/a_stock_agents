# 前端硬编码数据审查报告

- 审查日期：2026-09-09
- 审查范围：`web/`（`index.html`、`js/app.js`、`js/api.js`、`js/charts.js`、`js/ui_engine.js`、`js/components/astock.js`）以及后端 `scripts/server/api/market_data.py`
- 审查目标：前端页面不得硬编码业务数据（股票列表、指数行情、情绪、持仓、收益分析、分析结论等），数据必须从后台接口获取；测试阶段数据允许使用 MOCK。
- 审查结论：**存在大面积硬编码 + 数据接入链路失效**，已完成主要修复（详见实施计划）。

> [!WARNING]
> **本文结论已部分过期（2026-10-07 更正，原文按审计时点保留不改）**
>
> 本报告写于 2026-09-09，当时允许「测试阶段使用 MOCK」，故 §2.2 的 `generateKlines`「保留为组件兜底工具」、§2.3 的 `astock.js` 组件缺省值「保留」、§四 的「后端 `market_data.py` MOCK 数据 / `api.js` 本地 MOCK 兜底」、§六 的剩余硬编码建议，均已被项目后续确立的**零虚假数据铁律**推翻。2026-10-07 复核与整改实况：
>
> 1. **伪造载体归因更正**：治理测试 `test_production_authenticity` 的失败源在 `web/js/app.js`（`MarketFallbackData` / `WatchlistFallbackData` / `ReturnsFallbackData` / `generateKlines` / `defaultSpark` / `defaultNews`），**不在** `astock.js`；§2.3 的表述失真。
> 2. **上述 6 个伪造载体已全部删除**（非保留），并新增 `renderReturnsUnavailable` / `renderWatchHeroUnavailable` / `markMarketIndicesUnavailable` / `markMarketKlineUnavailable` 四组诚实空态；`initDashboardCharts` + `loadDashboardData`（227 行、目标 DOM id 已全不存在却仍白发 5 个后端请求）一并清除。
> 3. **§四 数据链路已改**：`/api/market/sentiment`、`/api/market/ranks`、`/api/portfolio/analysis` 不再返回 MOCK，改 `_unavailable()` fail-closed（503 `CAPABILITY_NOT_IMPLEMENTED`）。
> 4. **§2.1 `index.html`「已清理」不实**：静态层仍残留指数点位、自选 Hero（宁德时代/300750）、事件时间轴、收益结论、北向比率等 17 处写死值，已于 2026-10-07 清除为骨架屏或 `datasync-detail-placeholder` 占位。
> 5. **第 7 个伪造载体漏检（2026-10-07 追加更正）**：上述「6 个伪造载体已全部删除」并不成立——`web/js/app.js` 的策略选股工作台另有一个整屏假数据载体（6 个模型案例 + 5 层漏斗通过数 + 10 行候选股及价格涨跌幅 + 一条固定价格走势数组），`web/index.html` 的 `#pane-selection` 静态层同样预置了模型名、「● 运行中」徽章、总条数与 255 页假分页、个股现价/涨跌幅/综合评分/更新时间及四段投研结论，且新建/停止/日志/导出/加自选/页签/周期切换按钮一律只弹 toast（违反 [SSOT §17.2](../guidelines/algorithm/selection-system-specification.md)「不得提供可点击的假编辑器」）。根因是治理黑名单为**字面量列表**，恰好不含上述任何串。现该工作台已按后端无 `selection_models` 接口的事实改为 fail-closed 如实空态，无数据源的动作按钮一律 `disabled` 并说明原因。另：同一套假数据的原型页 `web/backup/成长优选模型工作台片段.html` 经 `/ui/backup/*` 仍可被浏览器直接打开（`web/` 由 StaticFiles 整目录挂载），已加显式「非生产设计原型」横幅与标题声明，`workbench_dashboard_backup.html` 同步补标。
>
> 防复现回归：`test_workbench_panes_have_no_fabricated_fallback_data`、`test_index_html_has_no_static_fabricated_market_values`、`test_unconnected_market_endpoints_fail_closed_in_source`、`test_selection_workbench_is_fail_closed_not_fabricated`（含五条结构性断言：静态层可见文本不得含任何数字、不得残留凭空运行态、按钮必须 `disabled` 或接入真实函数、无走势数据源不得自带 canvas、`web/` 下任何备份/原型 html 必须声明「非生产设计原型」——`web/` 被 StaticFiles 整目录挂载，备份页同样会被当成真实结果）；`tests/frontend/test_market_adaptive_layout.js` 中原「强制要求 `MarketFallbackData` 存在」的断言语义已反转。现状以 [`SPEC-UI-003`](../specs/ui/market-data-sync-control-console-plan.md) 变更日志为准。

---

## 一、总体结论

前端数据链路存在三层问题，导致页面实际显示的全部是写死在 HTML/JS 里的假数据：

| 层 | 文件 | 问题 |
|---|---|---|
| 视图层 | `web/index.html` | 上百处业务数据直接硬编码在标签内（指数点位、涨跌幅、自选股、涨跌榜、北向、持仓、收益 KPI、监控流、AI 结论等） |
| 逻辑层 | `web/js/app.js` | 6 个数据加载器全部失效：调用不存在的 API 方法、期望错误的响应结构、引用当前 HTML 中不存在的 DOM id、图表方法名错误 |
| 数据层 | `web/js/api.js` | **本身正确**：已按后端契约实现并带 MOCK 兜底，但从未被正确调用 |

后端 `scripts/server/api/market_data.py` 已提供规范契约并返回 MOCK 数据（满足"测试阶段可用 MOCK"），`tests/test_market_data_api.py` 8 项用例全部通过。

---

## 二、硬编码数据清单（按区块）

### 2.1 `web/index.html`（已清理）

| 区块 | 元素/ID | 原硬编码内容 |
|---|---|---|
| 总资产概览 | `ovTotalAssets`/`ovPositionMarketVal`/`ovCash`/`ovTodayPnl`/`ovAccumReturn`/`ovAnnualReturn`/`ovPositionRatioLbl`/`ovCashRatioLbl` | ¥454.24万、¥328.56万、¥125.68万、+¥3.86万、+36.78%、+18.24% 等 |
| 风控状态 | `ovRiskStatus`/`ovCushionDesc` | "账户风控正常"、安全垫文案 |
| 持仓分布 | `ovHoldingsList` | 宁德时代/中芯国际/海光信息 3 条 |
| 大盘指数（工作台） | `dashIndexSh/Sz/Cy/KcVal/Change/Meta` | 3426.56、10892.14、2289.76、1012.35 等 |
| 情绪仪表 | `dashSentimentScoreText`/`dashSentimentMetaDesc`/`dashAiCommentary`/`dashSectorHotList` | 78分、1.28万亿、3348/1105/86、AI 研判文案 |
| 自选指数 | `dashCustomIdx1/2Title/Change/Val` | 自选等权组合指数 +2.18%、半导体科技指数 +3.62% |
| 工作台自选表 | `dashWatchlistTableBody` | 中芯国际/海光信息/宁德时代 3 行 |
| 投资指标 | `dashSharpeVal`/`dashWinRateVal`/`dashMaxDdVal`/`dashPlRatioVal`/`dashAttributionExcess`/`dashAttributionRow` | 1.84、68.5%、-8.24%、2.41、+25.4%、归因 3 条 |
| 盯盘监控 | `dashMonitorLiveBadge`/`dashMonitorStreamList`/`dashStrategiesContainer` | 延迟28ms、3 条事件、4 个策略开关 |
| 市场指数 | `mktSh/Sz/Cy/KcPrice/Change/Open/High/PreClose/Turnover` | 3426.56、+24.38、3410.21 等 |
| 市场情绪 | `mktLimitUpCount`/`mktLimitDownCount`/`mktTotalTurnover`/`mktUpCount`/`mktFlatCount`/`mktDownCount` | 86、6、1.20万亿、3426、892、892 |
| K线均线 | `mktKlineMa5/10/20` | 3410.32、3398.76、3376.21 |
| 板块涨幅榜 | `mktSectorGrid` | 半导体/光伏/消费电子等 10 个板块 |
| 今日要闻 | `mktNewsList` | 5 条新闻 |
| 热门概念 | `mktHotConcepts` | 9 个概念标签 |
| 涨跌/北向榜 | `mktGainersBody`/`mktLosersBody`/`mktNorthboundBody` | 各 5 行 |
| 自选股列表 | `watchStockList`/`watchStockCount` | 12 只自选股 |
| 个股详情 | `watchHeroName/Code/Tags/Price/Delta/Open/High/Low/PreClose/Vol/Amount` | 宁德时代 300750 328.56 等 |
| 个股元数据 | `watchMetaIndustry/Concepts/FloatCap/TotalCap/Pe/Pb/52High/52Low` | 电池、7,654.32亿、18.76 等 |
| 事件时间线 | `watchEventsTimeline` | 4 条事件 |
| 资金流向 | `watchFundMain/Super/Large/Mid/SmallInflow` | 12.36亿、7.23亿 等 |
| 北向资金 | `watchNorthSH`/`watchNorthSZ` | 3.12亿、2.11亿 |
| 主力追踪 | `watchMainHoldings/Ratio/Concentration` | 12.76亿、8.46%、71.26% |
| AI 分析结论 | `watchAiConclusion`/`watchAiTags` | 一段结论 + 3 个标签 |
| 收益 KPI | `retAccumReturnVal`/`retBenchmarkExcessVal`/`retAnnualReturnVal`/`retWinRateVal`/`retWinLossCount`/`retSharpeVal`/`retMaxDrawdownVal`/`retPlRatioVal` | +34.28%、+25.63%、+42.15%、68.5%、54胜/25负、1.84、-8.24%、2.35 |
| 策略收益贡献 | `retStrategyContribGrid` | 4 个策略条 |
| 持仓明细 | `retPositionsTableBody` | 4 行持仓 |

> 保留未动：保本价试算器与三场景动作单（属客户端确定性税费精算 + 静态指令模板，非后端数据）；技能治理面板（已接 `/api/skills`）。

### 2.2 `web/js/app.js`

| 位置 | 硬编码内容 | 处理状态 |
|---|---|---|
| `HistoricalSessions`（20 条） | 会话记录 | 保留为离线兜底，已被 `listSessions` 覆盖 |
| `PromptTemplates`（4 段） | 评估/收益/行情分析报告模板（分析结果） | 保留为 MOCK，待接 `/api/chat/completions/stream` |
| `AtOperatorRegistry` | @ 操作符股票/技能/算法列表 | 技能/算法为静态配置；股票分组现价待接行情 |
| `renderTabCharts` | 硬编码图表数据（donut/sparkline/K线/净值曲线） | 已改为触发加载器 |
| `generateKlines` | 随机 K 线生成器 | 保留为组件兜底工具 |
| 6 个数据加载器 | 调用不存在方法 + 错误响应结构 + 错误 DOM id | 已重写 |

### 2.3 `web/js/components/astock.js`

组件 `renderCompact/renderExpanded` 内 hardcoded 指数/K线作为 `props` 缺省值（UI 组件库兜底），保留；实际数据应由调用方传 `props`。

---

## 三、根因分析：API 契约错配

`app.js` 加载器期望的契约与后端/`api.js` 实际契约严重错配，导致加载器在 `try/catch` 中静默失败：

| 维度 | 加载器原期望（错误） | 后端/`api.js` 实际（正确） |
|---|---|---|
| 方法名 | `getIndices/getSentiment/getKline/getRanks/getStockDetail` | `getMarketIndices/getMarketSentiment/getMarketKline/getMarketRanks` + `getWatchlist().active_stock_detail` |
| 响应包装 | `{ data: {...} }` | 直接返回对象（`indices`/`score`/`klines`…） |
| 字段风格 | snake_case（`total_assets`/`change_pct` 等混合） | camelCase（`total_assets`/`change_pct` 等，与后端一致） |
| DOM id | `dashTotalAssets`/`dashShPrice` 等（旧版 HTML） | `ovTotalAssets`/`dashIndexShVal` 等（当前 HTML） |
| 图表方法 | `drawSentimentGauge`/`drawTrendLine`（不存在） | `drawGauge`/`drawMultiLine` |

---

## 四、修复后的数据链路

```
后端 /api/*（market_data.py，MOCK 数据）
        │  fetch（前端同源）
        ▼
AStockAPI（api.js，先请求后端；后端离线时返回本地 MOCK，兜底形状与后端一致）
        │
        ▼
加载器 load*Data（app.js，映射到正确 DOM id，绘制图表）
        │
        ▼
index.html（空容器/占位，由 JS 渲染）
```

---

## 五、验证结论

- `node --check`：`app.js`/`api.js`/`charts.js`/`ui_engine.js`/`astock.js` 全部通过
- `pytest tests/test_market_data_api.py`：**8 passed**
- `getElementById` 引用与 `index.html` id 交叉校验：重写后的加载器引用全部命中（唯一缺失 `linkedContextText` 为既有旧引用，非本次引入）
- 旧的坏方法名（`getIndices/getSentiment/…`、`drawSentimentGauge/drawTrendLine`）已无残留
- `FinancialCharts` 所有被调用方法（`drawSparkline/drawCandlestickChart/drawGauge/drawDonutChart/drawMultiLine/drawEquityCurve/drawMonthlyPnLChart`）均存在，`drawGauge` 支持 `colorType: 'sentiment' | 'control'`

---

## 六、剩余硬编码项（后续处理，详见实施计划）

| 项 | 文件 | 建议 |
|---|---|---|
| AI 分析结果模板 | `app.js` `PromptTemplates` | 改为调用 `/api/chat/completions/stream`，MOCK 仅兜底 |
| 会话记录 | `app.js` `HistoricalSessions` | 保留为离线兜底，已接 `listSessions` |
| @ 操作符股票列表 | `app.js` `AtOperatorRegistry.stock/watchlist` | 现价/涨跌接入 `getWatchlist`，拼音/图标保留静态 |
| 技能清单 | `app.js` `BuiltinSkillsManifest` | 已作为 `/api/skills` 兜底，符合预期 |
