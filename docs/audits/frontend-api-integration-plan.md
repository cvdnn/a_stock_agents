# 前端数据接入后端 · 修改实施计划

- 制定日期：2026-09-09
- 关联文档：`docs/audits/frontend-hardcoded-data-audit.md`
- 总体目标：前端所有业务数据（股票列表、行情、情绪、持仓、收益分析、分析结论）均从后台接口获取；测试阶段数据使用 MOCK（后端 MOCK + 前端 `api.js` 兜底），杜绝 HTML/JS 硬编码。

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

---

## 三、剩余工作分阶段计划

### 阶段 P0 —— 数据接入完成度核验（1–2h）

- [ ] 启动后端 `.\bin\astock.cmd server`（或 `python scripts/server/run.py`），浏览器打开首页，逐 Tab 目检：
  - 工作台：总资产/指数/情绪/自选表/投资指标/监控流
  - 市场行情：指数/情绪/K线/板块/要闻/概念/涨跌榜/北向
  - 自选个股：列表/详情/事件/资金/主力/北向/AI 结论
  - 收益分析：KPI/净值曲线/月度盈亏/策略贡献/持仓表
- [ ] 断网/停后端验证 MOCK 兜底：刷新页面仍能渲染（`api.js` 本地 MOCK）。
- [ ] 记录目检问题到 issue 清单。

**验收**：4 个 Tab 在“有后端”与“无后端”两种情况下均能完整渲染，无 `console.error`。

### 阶段 P1 —— 分析结果（AI 文本）接入后端（2–4h）

- [ ] `PromptTemplates` 改造：`executeQuickAction` 不再直接 `streamAIResponse(tpl)`，改为调用 `AStockAPI.streamChatCompletions(...)` 流式输出；离线时回退到现有 `PromptTemplates` 作为 MOCK。
  - 文件：`web/js/app.js`（`executeQuickAction`、`streamAIResponse`）
- [ ] `askAboutRightContent` / `askStockPrompt` 生成的 prompt 确认走 `/api/chat/completions/stream`。
- [ ] 确认后端 `scripts/server/api/chat.py` 已支持对应会话与流式协议（必要时补 MOCK 响应）。

**验收**：点击快速入口/提问按钮，分析结果由后端（或 MOCK）生成并流式展示，而非前端写死模板。

### 阶段 P2 —— @ 操作符股票列表接行情（1–2h）

- [ ] `AtOperatorRegistry` 的 `stock`/`watchlist` 分组，现价/涨跌幅从 `AStockAPI.getWatchlist()` 刷新；拼音、图标、描述、`costPrice`（若有）保留为静态配置。
  - 文件：`web/js/app.js`（`AtOperatorController.init` / `AtOperatorRegistry`）
- [ ] 技能/算法分组维持静态（属配置，非行情数据）。

**验收**：@ 弹窗股票现价与行情一致；无股票时优雅降级为静态配置。

### 阶段 P3 —— 收尾与文档（0.5h）

- [ ] 清理既有 `linkedContextText` 等失效 DOM 引用。
- [ ] 补充 `docs/guidelines/web-aichat-architecture.md` 的数据契约章节（后端 Schema ↔ `api.js` ↔ 加载器映射）。
- [ ] `git` 提交：拆分“JS 数据接入”与“HTML 清理”两个原子提交。

---

## 四、测试计划

| 层 | 用例 | 命令/方式 |
|---|---|---|
| 后端 | 市场/组合/自选/监控接口契约 | `pytest tests/test_market_data_api.py`（8 用例，已通过） |
| 后端 | 端到端接口联调 | `pytest tests/test_live_server_e2e.py`（需先启动服务） |
| 前端 | JS 语法 | `node --check web/js/*.js web/js/components/*.js` |
| 前端 | DOM id 一致性 | 脚本比对 `getElementById('…')` 与 `index.html` 的 `id="…"` |
| 前端 | 渲染目检 | 浏览器手测（P0 清单） |
| 前端 | MOCK 兜底 | 停后端后刷新页面验证 |

---

## 五、风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 重写加载器引入 DOM 映射错误 | 页面显示 `--` 或空白 | P0 目检 + DOM id 交叉校验已通过；单文件 `git` 回滚 |
| 后端未启动时页面短暂占位 | 首屏为 `--` | `api.js` 本地 MOCK 兜底，刷新即渲染 |
| `streamChatCompletions` 协议不匹配（P1） | 分析结果为空 | 先读 `scripts/server/api/chat.py` 契约再改，保留 `PromptTemplates` 兜底 |
| 前端 MOCK 与后端 MOCK 形状漂移 | 前后端不一致 | `api.js` 兜底形状与后端 Schema 对齐；建议后续加契约测试 |

---

## 六、里程碑

1. **M0（已完成）**：行情/组合/自选/收益/监控数据从 API 接入，HTML 硬编码清空。
2. **M1**：分析结果（AI 文本）接入后端。
3. **M2**：@ 操作符股票列表接行情。
4. **M3**：文档与提交收尾。
