# 前端数据接入后端 · 修改实施计划

- 制定日期：2026-09-09
- 关联文档：`docs/audits/frontend-hardcoded-data-audit.md`
- 总体目标：前端所有业务数据（股票列表、行情、情绪、持仓、收益分析、分析结论）均从后台接口获取；测试阶段数据使用 MOCK（后端 MOCK + 前端 `api.js` 兜底），杜绝 HTML/JS 硬编码。
- **执行状态：✅ 已全部完成（2026-09-09），P0–P3 与里程碑 M0–M3 全部达成。**

---

## 一、目标与原则

1. **单一数据源**：后端 `/api/*` 为唯一数据源；`api.js` 是唯一客户端入口，前端不允许绕过它直接写死数据。
2. **MOCK 兜底**：后端已返回 MOCK；`api.js` 在后端离线时返回本地同构 MOCK，保证静态页面可预览。
3. **契约一致**：`api.js` 响应结构与后端 `market_data.py` Pydantic Schema 严格对齐（camelCase、无 `{data}` 包装）。
4. **可验证**：每个阶段都有明确验收标准与测试。

---

## 二、已完成工作（本轮）

| # | 任务 | 文件 | 状态 |
|---|---|---|---|
| 1 | 重写 4 个数据加载器（`loadDashboardData/loadMarketData/loadWatchlistData/loadReturnsData`），改为消费 `AStockAPI` 正确方法 + 正确字段 + 正确 DOM id | `web/js/app.js` | ✅ |
| 2 | `renderTabCharts` 改为触发加载器（删除硬编码图表数据）；补充 `toggleStrategy` 桩 + `resize` 防抖 | `web/js/app.js` | ✅ |
| 3 | 清空 `index.html` 全部硬编码业务数据（占位 `--` / 空容器），补 `watchStockCount/watchHeroTags/watchAiTags/watchNorthSH/watchNorthSZ` 挂载点 | `web/index.html` | ✅ |
| 4 | 验证：JS 语法、后端 8 用例、DOM id 交叉、图表方法存在性 | — | ✅ |
| 5 | 修复 SSE `content_delta` 字段解析 + `streamAIResponse` 回调契约，分析结论接入后端流式输出 | `web/js/api.js`、`web/js/app.js` | ✅ |
| 6 | 新增 `syncAtOperatorQuotes`，@ 操作符股票现价/涨跌接 `getWatchlist` | `web/js/app.js` | ✅ |
| 7 | 清理失效 DOM 引用、更新架构文档、拆分原子提交 | — | ✅ |

---

## 三、执行情况记录（P0–P3）

### 阶段 P0 —— 数据接入完成度核验（✅ 已完成）

- [x] 启动后端 `python scripts/server/run.py --port 6300`，headless Edge（`--dump-dom`）渲染首页并核验 DOM。
- [x] 工作台：总资产 ¥454.24万、四大指数 3,426.56/10,892.14/2,289.76/1,012.35、情绪「78分 · 市场情绪亢温」、自选 14 卡、投资指标、监控流 4 策略开关。
- [x] 市场行情：指数/K线/板块/要闻/概念/涨跌榜/北向均填充后端数据。
- [x] 自选个股：`watchStockList` 渲染 14 张卡片，`active_stock_detail.name = 宁德时代`。
- [x] 收益分析：`retPositionsTableBody` 渲染完整持仓行（宁德时代 300750.SZ 1,000股 ¥315.00→¥328.56 +4.3%、保本 ¥315.68、🟢正常持仓、5A多因子…），KPI 累计 +36.78%/胜率 68.5%/夏普 1.84。
- [x] MOCK 兜底：`api.js` 本地同构兜底形状与后端对齐（后端离线可刷新渲染）。

> 说明：DSH 沙箱默认阻止 Chromium 系浏览器的 Mojo 命名管道，headless Edge 需一次性 `danger-full-access` 提升后方可渲染；此为宿主沙箱限制，非本项目代码问题。

**验收结论：通过。** 页面所有业务数据由后端渲染，无硬编码残留。

### 阶段 P1 —— 分析结果（AI 文本）接入后端（✅ 已完成）

- [x] 修复 `api.js` `content_delta` 字段解析：后端 `ContentDeltaEvent` 序列化为 `{"text":…}`，原 `delta||content` 恒为空，现改为 `delta || content || text`。
- [x] 修复 `streamAIResponse` 回调名与 `api.js` 契约对齐：`onSessionCreated`→`onStart`、`onToolCall`→`onToolStart` + 新增 `onToolComplete`。
- [x] 全部分析结论调用点补传真实用户提问 `{ userText }`（`executeQuickAction` 3 处 + `executeOperatorTask` 5 处），后端可命中标的代码与意图触发词。
- [x] 确认后端 `scripts/server/api/chat.py` → `AgentReActRunner` → `MockLLMProvider` 离线流式返回（`conversation_start`/`thought`/`tool_call_*`/`content_delta`/`done`）。

**验收：通过。** `POST /api/chat/completions/stream` 实测返回 `event: content_delta` 且 data 为 `{"text":"…量化投研与操盘决议…"}`；离线回退 `PromptTemplates` 打字机。

### 阶段 P2 —— @ 操作符股票列表接行情（✅ 已完成）

- [x] 新增 `syncAtOperatorQuotes(stocks)`：按 `code` 合并 `getWatchlist` 结果刷新 `AtOperatorRegistry.stock`/`.watchlist` 的 `currentPrice`/`changePct`。
- [x] 拼音、图标、描述、股池、持仓比例、`costPrice`、`pe` 保留静态配置。
- [x] 技能/算法分组维持静态。

**验收：通过。** 后端 watchlist 覆盖注册中心 7/8 个代码；未覆盖的 `300308`（中际旭创）优雅降级为静态值。

### 阶段 P3 —— 收尾与文档（✅ 已完成）

- [x] 移除两处失效的 `linkedContextText` DOM 引用（`switchRightTab` / `unlinkRightContent`）。
- [x] 更新 `docs/guidelines/web-aichat-architecture.md`：校准 SSE 事件帧契约 + 新增「前端数据契约与 MOCK 兜底规范」章节。
- [x] `git` 原子提交（4 个）。

---

## 四、测试计划与执行结果

| 层 | 用例 | 命令/方式 | 结果 |
|---|---|---|---|
| 后端 | 市场/组合/自选/监控接口契约 | `pytest tests/test_market_data_api.py` | ✅ 8 passed |
| 后端 | SSE 流式协议 | TestClient 实测 `/api/chat/completions/stream` | ✅ `content_delta` 含 `text` |
| 后端 | watchlist 代码覆盖 | TestClient 实测 `/api/watchlist` | ✅ 14 只股票含 `code/price/change_pct` |
| 前端 | JS 语法 | `node --check web/js/*.js web/js/components/*.js` | ✅ 全通过 |
| 前端 | DOM id 一致性 | 脚本比对 `getElementById` 与 `index.html` id | ✅ 全命中 |
| 前端 | 渲染目检 | headless Edge `--dump-dom` | ✅ 数据完整渲染 |
| 前端 | MOCK 兜底 | `api.js` 同构兜底形状对齐 | ✅ 契约一致 |

---

## 五、风险与回滚

| 风险 | 影响 | 缓解 | 结果 |
|---|---|---|---|
| 重写加载器引入 DOM 映射错误 | 页面显示 `--` 或空白 | P0 目检 + DOM id 交叉校验 | 未发生，DOM 全命中 |
| 后端未启动时页面短暂占位 | 首屏为 `--` | `api.js` 本地 MOCK 兜底 | 兜底契约已对齐 |
| `streamChatCompletions` 协议不匹配（P1） | 分析结果为空 | 先读契约再改，保留 `PromptTemplates` 兜底 | 已修复（字段 + 回调名） |
| 前端 MOCK 与后端 MOCK 形状漂移 | 前后端不一致 | 兜底形状与后端 Schema 对齐 | 已对齐，测试回归基线 |

---

## 六、里程碑

1. **M0（✅ 完成）**：行情/组合/自选/收益/监控数据从 API 接入，HTML 硬编码清空。
2. **M1（✅ 完成）**：分析结果（AI 文本）接入后端流式输出。
3. **M2（✅ 完成）**：@ 操作符股票列表接行情。
4. **M3（✅ 完成）**：文档与提交收尾。

---

## 七、执行记录（提交与验证证据）

### 提交记录

| commit | 说明 |
|---|---|
| `2df909e` | docs(audits): 新增前端硬编码数据审查报告与数据接入实施计划 |
| `9f4c006` | feat(web): 修复 SSE content_delta 字段与回调契约，AI 分析结论接入后端流式输出，@ 操作符股票行情同步 getWatchlist |
| `bb6f5f4` | refactor(web): 清空 index.html 硬编码业务数据，改为 API 渲染占位与空容器 |
| `88f1f71` | docs(guidelines): 校准 SSE 事件帧契约并补充前端数据契约与 MOCK 兜底规范 |

### 关键验证证据

- 后端接口：`/api/market/indices`（4 指数）、`/api/watchlist`（14 股，`active_stock_detail.name=宁德时代`）。
- SSE：`content_delta` 帧 data 为 `{"text":"\n\n### 📊 量化投研与操盘决议\n\n…"}`（`MockLLMProvider` 离线流式生成）。
- 前端渲染（headless Edge DOM）：总资产 `¥454.24万`、四大指数、情绪 `78分 · 市场情绪亢温`、自选 14 卡、持仓表完整行、收益 KPI、监控流 4 策略开关。
