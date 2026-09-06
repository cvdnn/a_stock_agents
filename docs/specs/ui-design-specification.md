# A-Stock Agents Web UI 界面设计与交互规范 (UI/UX Specification)

- **文档版本**：v1.0
- **创建日期**：2026-09-06
- **适用范围**：A-Stock Agents 独立 Web 投研前端、Desktop 客户端（Tauri/Electron）及跨端界面系统
- **状态**：正式规范 (Production Baseline)

---

## 1. 设计哲学与视觉基调 (Design Philosophy & Aesthetics)

本系统面向专业 A 股量化投资者与机构级投研人员，遵循 **浅色金融商务风格（Clean Light Financial Aesthetic）**：
1. **视觉减负与数据优先**：界面不使用多余的装饰性花哨渐变，以清晰规整的网格卡片、等宽数字、高对比度核心指标呈现金融投研数据。
2. **涨跌色彩铁律**：严格遵守中国 A 股交易市场标准（**红涨绿跌**）：
   - 上涨 / 盈余 / 做多色：`#F5222D`（浅底背景：`#FFF1F0`，边框：`#FFA39E`）
   - 下跌 / 亏损 / 规避色：`#52C41A`（浅底背景：`#F6FFED`，边框：`#B7EB8F`）
   - 品牌主色：`#1677FF`（深蓝，代表理性、量化与科技）
   - 全局背景：`#F8FAFD`（亚光冷白，护眼防疲劳）；卡片底色：`#FFFFFF`；细分割线：`#DFE6EF`
3. **高精数字排版**：涉及行情价格、涨跌幅、成交量、资金流、保本价等所有金融数值，必须强制启用 CSS `font-variant-numeric: tabular-nums`，确保垂直方向精准对齐。

---

## 2. 工作区整体架构：三栏式 40% / 60% 弹性布局规范

工作区采用 CSS Grid 弹性响应式三栏架构，视口高度严密锁定在 `calc(100vh - 50px)`，杜绝整页滚动：

```
+---------------------------------------------------------------------------------------------------------------+
| Top Header (50px): AI量化投资助手 | 全局检索 (股票/代码/指标) | 📑研报  🔔预警 | 👤量化实盘账户 (机构级认证)            |
+-------------------+-----------------------------------+-------------------------------------------------------+
| 左侧菜单栏 (240px)| 中间：AI投研助手 (占 40%)          | 右侧：详细内容展示区 (占 60%，折叠时占 100%)            |
| (三段式结构)      | (独立垂直上下滑动)                | (多标签页保留体系，独立垂直上下滑动)                  |
|                   |                                   |                                                       |
| [1. 功能导航]     | [极简标题栏]                      | [顶部多标签栏 (Tabs Bar)]                              |
| · 🤖 投研助手     | 🤖 投研助手 ● 在线       [◀ 收起] | [▶ 展开] [📊投研盘面] [📈市场行情] [⭐自选] [💰收益]   |
| · 📊 市场行情     |                                   |          [🛡️实战动作单·宁德时代 ✕]                     |
| · ⭐ 自选个股     | [对话流区域 (Chat Messages)]      | [右侧上下文操作条]                                     |
| · 📈 收益分析     | · 用户提问气泡                    | 📌 当前展示: 整体投研盘面 | [💬针对提问] [✏️修改参数]   |
|                   | · AI 一问一答标准卡片             | [内容视口 (Scrollable Pane)]                           |
| [2. 会话记录]     |   - 头像 + 标题 + 摘要            | · Pane 1: 投研综合盘面 (大盘/指数/板块/自选)           |
| · 倒序前10条      |   - 研报正文与实战三原则动作单    | · Pane 2: 市场行情全景 (四大指数/情绪表/日K/北向)      |
| · 触底自动加载    |   - [⛶ 放大投射到右侧]            | · Pane 3: 自选个股研判 (多周期K线/主力控盘/资金流)     |
| · [+ 新建对话]    |                                   | · Pane 4: 收益分析全景 (净值走势图/月度胜负/持仓明细)  |
|                   | [底部固定输入区]                  | · Pane 5: 动态投射视窗 (保本价ceil进位试算器/战法大图) |
| [3. 系统设置]     | · [⚡ 引用右侧提问] [📁] [📊]     |   * 触发时从左至右动画弹出 (popupSlideFromLeft)        |
| · ⚙️ 系统设置     | · 输入框 + [发送 ✈️] (Enter即发)  |                                                       |
+-------------------+-----------------------------------+-------------------------------------------------------+
```

### 2.1 网格栅格定义
```css
.app-container {
  display: grid;
  grid-template-columns: 240px 4fr 6fr; /* 左侧 240px，中栏 40%，右栏 60% */
  height: calc(100vh - 50px);
  overflow: hidden;
  background: var(--bg-body);
  transition: grid-template-columns 0.3s cubic-bezier(0.2, 0, 0, 1);
}

/* 当中间 AIChatUI 折叠时 */
.app-container.chat-collapsed {
  grid-template-columns: 240px 42px 1fr; /* 中栏缩为 42px 侧边条，右栏占满 */
}
```

### 2.2 折叠与展开交互规范
- **收起动作**：点击中间投研助手标题右侧的 `[◀ 收起]` 按钮，中间列平滑收拢为宽度 `42px` 的竖向悬停条，右侧内容区自然扩充至 **100%** 全宽；
- **展开动作**：点击侧边竖向悬停条任意位置，或点击右侧标签栏最左侧出现的 `[▶ 展开投研助手]` 按钮，工作区平滑还原至 `40% : 60%`；
- **自适应重绘**：折叠/展开动画完成后，系统自动调度 `window.dispatchEvent(new Event('resize'))`，驱动右侧所有 Canvas 图表（K线、分时、净值曲线、月度盈亏）重算像素分辨率，严禁出现拉伸或模糊。

---

## 3. 菜单栏三段式纵向划分规范 (Sidebar 3 Sections)

菜单栏固定宽度 `240px`，纵向由上至下划分为三大高内聚区域：

### 3.1 功能区 (Top Functional Section)
包含 4 项全局核心投研功能入口：
1. **投研助手 (🤖)**：右侧激活综合投研盘面，聚焦与智能体的大模型交互；
2. **市场行情 (📊)**：右侧展示四大指数、78分贪婪情绪温度计、日K线蜡烛图及北向资金；
3. **自选个股 (⭐)**：右侧展示自选股池、个股深度研判（K线量能、资金流向饼图、主力控盘仪表盘）；
4. **收益分析 (📈)**：右侧展示量化实盘收益分析看板（资产净值走势 Canvas、月度盈亏柱状图、夏普比率、胜率、回撤与持仓明细）。

### 3.2 会话记录区 (Middle Sessions Section)
- **新建入口**：标题栏右侧常驻 `[＋ 新建]` 按钮，一键清空当前会话并开启新轮次投研，新会话自动置顶；
- **时间倒序排序**：会话按创建/活跃时间倒序排列（如“刚刚”、“今天 11:20”、“昨天 16:15”）；
- **分页与触底无限滚动规范**：
  - 初始挂载时仅加载并渲染最近 **10 条** 会话，保障首屏秒开；
  - 监听会话列表滚动事件：当检测到 `scrollTop + clientHeight >= scrollHeight - 15` 时，自动触发下一分页异步拉取；
  - 列表底部展示轻量级 Loading 动效（`.spinner-dot` 脉冲呼吸动画），加载完成后平滑追加 10 条历史会话，并展示当前已收录总数。

### 3.3 系统设置区 (Bottom Settings Section)
- 底部常驻显示当前量化实盘账户简介与在线状态；
- 点击 `⚙️ 系统设置` 唤出金融级全局配置弹窗（Modal）：
  - **大模型网关**：DeepSeek V3 (量化推理推荐) / Gemini 2.5 Flash / 本地 Ollama (Qwen2.5-7B) 切换与 API Key 管理；
  - **行情降级策略**：腾讯财经 API $\to$ 东方财富 $\to$ 新浪财经 $\to$ Baostock 四级容灾状态；
  - **实战三原则参数**：印花税率（0.05%）、佣金费率（万2.5最低5元起）、T0/T1/T2 止损线数值调整；
  - **Skill 治理监控**：17 项技能健康度与运行审计。

---

## 4. 独立双向垂直滚动规范 (Independent Dual-Scroll Specification)

为了杜绝金融交易中“看图时聊天输入框滚出屏幕”或“翻阅对话时图表跑偏”的恶性体验，系统实施严格的**局部独立垂直滚动机制**：

| 列区域 | 滚动容器选择器 | CSS 规则 | 滚动行为边界 |
| :--- | :--- | :--- | :--- |
| **左侧菜单栏** | `.sidebar-sessions-list` | `flex: 1; overflow-y: auto;` | 仅会话记录列表内部滚动，功能区与系统设置区始终固定 |
| **中间投研助手** | `.chat-messages` | `flex: 1; overflow-y: auto;` | 仅对话消息流独立上下滑动，顶部标题与底部输入条始终固定 |
| **右侧内容展示区** | `.right-content-scroll` | `flex: 1; overflow-y: auto;` | 仅详细内容视口内部滚动，顶部多标签栏与上下文操作条始终固定 |

---

## 5. AIChatUI 极简设计与双向交互规范 (AIChat & Bidirectional Linkage)

### 5.1 极简标题栏规范
- **杜绝空间浪费**：移除传统对话应用大面积的欢迎 Banner、Slogan 标语及冗余胶囊，将上部区域高度压缩至 `44px`；
- **标准标题排版**：
  ```html
  <div class="chat-header-simple">
    <div class="chat-simple-left">
      <div class="ai-avatar-pill-sm">AI</div>
      <h3 class="chat-simple-title">投研助手</h3>
      <span class="chat-status-dot">● 在线</span>
    </div>
    <button class="btn-collapse-chat" onclick="toggleChatCollapse()" title="收起投研助手">
      <span class="collapse-icon">◀</span>
      <span class="collapse-text">收起</span>
    </button>
  </div>
  ```

### 5.2 【重要交互 1】：针对右侧信息提问与修改
1. **针对提问 (Ask About Right Content)**：
   - 右侧上下文操作条提供 `[💬 针对此内容提问 AIChat]`；
   - 右侧数据表格（自选股、持仓股、板块排行）每行配备 `💬 提问` 按钮；
   - 点击后，JS 引擎自动提取右侧激活标的、现价、涨跌幅与主力控盘数据，自动格式化为标准量化 Prompt 注入中间 `#chatInput` 并高亮聚焦；
   - 输入框上方常驻关联状态条：`[🔗 当前关联右侧: ...] [⚡ 引用数据提问] [解除]`。
2. **针对修改 (Modify Right Parameters)**：
   - 右侧工具栏配备 `[✏️ 修改右侧参数]` 弹窗，支持实时调整买入成本、持仓股数与止损阶梯；
   - 在 AIChat 对话中若 AI 提出参数调优建议，回复卡片内强制生成 `[⚡ 应用修改到右侧]` 按钮，用户点击即可无缝将新参数回写至右侧视图并重绘图表。

### 5.3 【重要交互 2】：卡片放大投射与从左到右弹出动画 (Projection & Pop-in Animation)
1. **多标签页保护机制 (Preserve Existing Content)**：
   - 右侧顶部设立常驻 **Tabs 标签栏**（`投研盘面`、`市场行情`、`自选个股`、`收益分析`）；
   - 在 AIChat 内点击任意卡片（实战三原则动作单、行情研报、5A选股模型）的 `[⛶ 放大投射到右侧工作台]` 时：
     - **绝对不覆盖、不清除已有标签**；
     - 动态在右侧标签栏追加新标签（如 `[🛡️ 实战动作单·宁德时代 ✕]`）；
     - 平滑激活该标签，展示高精度放大版交互工作台（含保本价动态滑块进位试算器）；
     - 点击标签右侧 `✕` 即可关闭，安全平滑回退至原前序内容。
2. **从左到右弹出硬件加速动画 (`popupSlideFromLeft`)**：
   - 点击投射时，右侧展示区必须应用如下动效，呈现内容从中间智能体大脑“跃迁弹出至右侧”的沉浸式空间感：
   ```css
   @keyframes popupSlideFromLeft {
     0% {
       opacity: 0;
       transform: translateX(-40px) scale(0.97);
     }
     60% {
       opacity: 1;
       transform: translateX(4px) scale(1.002);
     }
     100% {
       opacity: 1;
       transform: translateX(0) scale(1);
     }
   }

   .popup-slide-from-left {
     animation: popupSlideFromLeft 0.38s cubic-bezier(0.16, 1, 0.3, 1) forwards;
   }
   ```

---

## 6. 实战三原则保本价精算与风控指令单规范 (AGENTS.md 契约落地)

在 AIChat 卡片及放大投射视窗中呈现实战动作单时，必须严格执行项目全局规范：
1. **税费全计入**：印花税（0.05%）、券商佣金（万2.5且最低5元起收）、过户费（双向0.002%）；
2. **强制向上进位至分 (`math.ceil`)**：
   $$\text{最低保本卖出价} = \frac{\lceil (\text{总买入金额} + \text{全部买卖摩擦税费}) \times 100 \rceil}{100 \times \text{股数}}$$
   严禁任何形式的四舍五入，杜绝哪怕 1 分钱的摩擦亏损。
3. **三级风控止损阶梯卡片**：
   - **T0 警戒线 (-3%)**：准备对冲或平保
   - **T1 减仓线 (-5%)**：强制减仓 50% 锁定本金
   - **T2 绝杀线 (-8%)**：无条件市价坚决止损出局
4. **三场景即时动作单**：明确开盘冲高 (+3%)、盘中窄幅震荡 (<1.5%)、盘中跳水急跌 (-3%以下) 时的清晰操作指令。

---

## 7. 收益分析全景看板规范 (Returns Analysis Specification)

作为本次重构新增的第四大核心视图，收益分析看板包含以下四大板块：
1. **6 大量化核心 KPI 矩阵**：
   - 累计总收益率（对比基准超额）、年化收益率、交易胜率（胜负笔数）、夏普比率（Sharpe）、最大回撤（MaxDD）、盈亏比（P/L Ratio）；
2. **双 Canvas 图表引擎**：
   - **资产净值走势图** (`FinancialCharts.drawEquityCurve`)：策略净值实线（带渐变填充）vs 沪深300虚线对比；
   - **月度盈亏柱状分布图** (`FinancialCharts.drawMonthlyPnLChart`)：红涨绿跌柱状图，顶部标注精确百分比；
3. **策略收益贡献分布与因子暴露**：5A多因子旋转策略 (45%)、主板趋势回踩策略 (30%)、MACD水下金叉战法 (18%)、退哥短线连板策略 (7%) 进度条；
4. **实盘持仓盈亏与保本进位风控核算明细表**：全览代码、持仓量、成本、现价、浮盈浮亏、分位进位保本价、风控阶梯状态及行级 `💬 提问` 操作。

---

## 8. 代码文件与资产对应表

| 规范章节 | 对应前端实现文件 | 对应样式与逻辑模块 |
| :--- | :--- | :--- |
| **三栏式40/60布局与折叠** | `web/index.html`<br>`web/css/style.css` | `.app-container`, `.app-container.chat-collapsed`, `toggleChatCollapse` |
| **极简投研助手标题栏** | `web/index.html`<br>`web/css/style.css` | `.chat-header-simple`, `.chat-simple-title`, `.btn-collapse-chat` |
| **三段式菜单栏与无限滚动** | `web/index.html`<br>`web/js/app.js` | `.sidebar-sessions-list`, `renderSessionList`, `setupSessionInfiniteScroll` |
| **多标签页保留与左向右弹出** | `web/index.html`<br>`web/css/style.css`<br>`web/js/app.js` | `#rightTabsBar`, `projectToRight`, `popupSlideFromLeft` |
| **针对右侧提问与参数修改** | `web/index.html`<br>`web/js/app.js` | `askAboutRightContent`, `askStockPrompt`, `applyRightParamForm` |
| **保本价进位与滑块试算器** | `web/index.html`<br>`web/js/app.js` | `updateProjectedCalculator`, `#resBreakeven`, `math.ceil` |
| **收益分析与 Canvas 图表** | `web/index.html`<br>`web/js/charts.js` | `drawEquityCurve`, `drawMonthlyPnLChart`, `.returns-overview-grid` |
