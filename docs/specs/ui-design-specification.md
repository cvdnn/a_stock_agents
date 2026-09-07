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

## 2. 工作区整体架构：双模动态视口与 AI 助手灵活定位规范 (Adaptive Dual-Mode Layout)

为了兼顾“深度会话投研”与“专业业务看盘分析”两种截然不同的核心使用场景，工作区彻底升级为 **意图驱动的双模动态视口架构（Intent-Driven Dual-Mode Viewport）**。视口高度严密锁定在 `calc(100vh - 50px)`，杜绝整页滚动。

### 2.1 模式一：【投研助手】模式 (Chat-Centric Dedicated Mode)
当用户在左侧菜单栏选择 **【投研助手】**（或新建/切换历史会话）时触发：
- **【AIChatUI】居于中间核心主交互位（占 40% 宽度）**，作为主视觉交互焦点，专注于多轮投研问答、量化推演与动作单生成；
- **铁律：AIChatUI 在该模式下始终展示**（不提供收起 AIChatUI 的操作，杜绝主对话区折叠消失）；
- **右侧定位为【工作台】（占 60% 宽度）**，承载整体综合盘面、快捷入口、自选异动、持仓统计及量化盯盘策略；
- **长条连通顶部栏规范（无中段分割与工作台标题）**：
  - 投研助手模式下，顶部栏彻底重构为**横贯中间与右侧的长条连通一体化布局（Unified Connected Top Bar）**；
  - 顶部栏消除中间垂直分割线，并删除原本突兀的 `[📊] 工作台` 独立标题；
  - 顶部栏左端常驻展示 `[AI] 投研助手 ● 在线`，右端常驻展示 `[收起 ▶]` 折叠按钮；
  - 垂直分割线仅在顶部栏下方的内容区域生效（准确区隔左侧对话流与右侧工作台盘面组件），使整个工作区视觉浑然一体、大气开阔；
- **工作台收起与展开交互闭环**：
  - **收起动作**：点击长条顶部栏右侧 `[收起 ▶]` 按钮，工作台平滑向右收起（`width: 0` / `display: none`），中间 AIChatUI 瞬间弹性扩展至 **100% 全宽**，开启沉浸式投研对话；
  - **唤回动作**：工作台收起后，长条顶部栏右侧动态高亮展示 `[📊 工作台 ◀]` 小按钮；点击该按钮即可平滑恢复为 40%/60% 双栏工作区，Canvas 图表自动完成重绘适配。

```
+---------------------------------------------------------------------------------------------------------------+
| Top Header (50px): AI量化投资助手 | 全局检索 (股票/代码/指标) | 📑研报  🔔预警 | 👤量化实盘账户 (机构级认证)            |
+-------------------+-------------------------------------------------------------------------------------------+
| 左侧菜单栏 (240px)| 中右长条连通一体化顶部栏 (50px): 消除中段分割与工作台标题                                         |
| [1. 功能导航]     | 🤖 投研助手 ● 在线                         [📊工作台◀ (折叠时)]                       [收起 ▶] |
| · 🤖 投研助手 (选)+-----------------------------------+-------------------------------------------------------+
| · 📊 市场行情     | 中间：AIChatUI 对话区 (40% / 100%) | 右侧：工作台内容区 (60% / 0%)                         |
| · ⭐ 自选个股     | [对话流区域 (Chat Messages)]      | [工作台内容视口 (Scrollable Dashboard)]               |
| · 📈 收益分析     | · 用户提问气泡                    | · 1. 整体盘面 (大盘/指数/板块/两市成交)               |
|                   | · AI 一问一答标准卡片             | · 2. 快捷入口 (大盘分析/行业轮动/5A选股)              |
| [2. 会话记录]     |   - 头像 + 标题 + 摘要            | · 3. 自选个股异动监控 (中芯国际/海光信息/宁德时代)    |
| · 倒序前10条      |   - 研报正文与实战三原则动作单    | · 4. 持股/投资统计 (持仓市值/总收益/年化收益)         |
| · 触底自动加载    |   - [⛶ 放大投射到右侧工作台]      | · 5. 量化/盯盘/消息提醒 (趋势突破策略开关)            |
| · [+ 新建对话]    | [底部固定输入区]                  |                                                       |
| [3. 系统设置]     | · [⚡ 引用右侧提问] [📁] [📊]     |                                                       |
| · ⚙️ 系统设置     | · 输入框 + [发送 ✈️] (Enter即发)  |                                                       |
+-------------------+-----------------------------------+-------------------------------------------------------+
```

### 2.2 模式二：【业务主工作区】模式 (Workspace-Centric Copilot Mode)
当用户在左侧菜单栏点击其他核心业务功能（如 **【市场行情】**、**【自选个股】**、**【收益分析】** 等）时自动触发：
1. **主工作区居中（占据中间主体视口）**：
   - 业务内容（市场行情全景看板、自选股深度研判、收益分析等）跃升为主导视重视窗；
   - 拥有独立的主工作区 Title 栏与多标签管理能力；
2. **【AIChatUI】定位为 AI 助手（伴随式 AI Copilot）并变动到右侧**：
   - 宽度固定或弹性占据右侧（如 `390px` 或 `35%` 比例）；
   - 标题切换为 `🤖 AI助手 ● 协同中`，顶部提供 `[▶ 收起]` 按钮；
   - 支持随主工作区内容上下文同步滚动提问、参数联动修改与答疑。

```
+---------------------------------------------------------------------------------------------------------------+
| Top Header (50px): AI量化投资助手 | 全局检索 (股票/代码/指标) | 📑研报  🔔预警 | 👤量化实盘账户 (机构级认证)            |
+-------------------+-------------------------------------------------------+-----------------------------------+
| 左侧菜单栏 (240px)| 中间：业务主工作区 (占 65%~70%，折叠右侧时占 100%)    | 右侧：AIChatUI 定位为 AI助手 (390px)|
|                   | [业务主工作区 Title 栏 / 多标签栏]                   | [AI助手标题栏]                    |
| [1. 功能导航]     | [📊投研盘面] [📈市场行情] (当前激活) [⭐自选] [💰收益]| 🤖 AI助手 ● 协同中       [▶ 收起] |
| · 🤖 投研助手     |                                                       |                                   |
| · 📊 市场行情 (选)| [主工作区上下文操作条与 Title]                        | [对话流区域 (Chat Messages)]      |
| · ⭐ 自选个股     | 📌 市场行情全景 (四大指数/情绪/日K) [💬提问] [🤖AI助手]| · 针对当前行情提出分析与推演      |
| · 📈 收益分析     |                                                       | · 关联当前选中标的实时建议        |
|                   | [大屏专业图表与数据流 (Scrollable Workspace)]         |                                   |
| [2. 会话记录]     | · 四大核心指数分时/日K走势全屏看板                    | [底部固定输入区]                  |
| · 倒序前10条      | · 情绪温度计 (78分贪婪) + 两市成交 1.28万亿           | · [⚡ 引用中间提问]               |
| · 触底自动加载    | · 行业/概念板块资金流入榜 + 涨跌停家数对比            | · 输入框 + [发送 ✈️]              |
| · [+ 新建对话]    | · 宁德时代 / 中芯国际深度盘口动态                     |                                   |
|                   |                                                       |                                   |
| [3. 系统设置]     |                                                       |                                   |
| · ⚙️ 系统设置     |                                                       |                                   |
+-------------------+-------------------------------------------------------+-----------------------------------+
```

### 2.3 右侧 AI 助手收起与中间区域 Title 右侧小按钮交互规范 (Collapsed Copilot Interaction)
在模式二（业务主工作区）下：
1. **收起动作**：用户点击右侧 AI 助手标题右上方的 `[▶ 收起]` 按钮：
   - 右侧 AI 助手平滑向右侧滑出收起（CSS 宽度收敛为 0，添加 `.copilot-collapsed` 类）；
   - 中间业务主工作区宽度瞬间弹性扩展至 **100% 全宽**，满足专业交易者大屏复盘看盘的沉浸诉求；
2. **中间区域 Title 右侧常驻展开小按钮**：
   - **位置与形态**：在中间主工作区 Title / 上下文操作栏右侧，动态显示一个精巧的高对比度微按钮：
     ```html
     <button class="btn-copilot-launcher" id="btnCopilotLauncher" onclick="toggleCopilot()" title="打开AI助手">
       <span class="copilot-btn-icon">🤖</span>
       <span class="copilot-btn-label">AI助手</span>
       <span class="copilot-btn-arrow">◀</span>
     </button>
     ```
   - **视觉规范**：高度 `28px`，圆角 `6px`，背景浅蓝高亮 `#E8F3FF`，文字主色 `#1677FF`，边框 `1px solid #ADC6FF`，带有轻微的呼吸点与悬停高亮效果；
   - **展开动作**：用户在看盘时随时点击该小按钮，右侧 AI 助手向左平滑展开，工作区平滑恢复为业务区 + AI 助手双列，同时自动派发图表 resize 事件重新适配 Canvas。

```
+---------------------------------------------------------------------------------------------------------------+
| 左侧菜单栏 (240px)| 中间：业务主工作区 (100% 全宽大屏看盘沉浸模式)                                                    |
|                   | [业务主工作区 Title 栏]                                                                        |
| · 🤖 投研助手     | 📌 市场行情全景 (四大指数/情绪表/日K/板块)                 [💬提问]  [ 🤖 AI助手 ◀ ] (小按钮)|
| · 📊 市场行情 (选)| +-------------------------------------------------------------------------------------------+ |
| · ⭐ 自选个股     | |                                                                                           | |
| · 📈 收益分析     | |  [100% 满屏金融图表、K线量价深度矩阵、净值曲线大图展示]                                  | |
|                   | |                                                                                           | |
+-------------------+-------------------------------------------------------------------------------------------+ |
```

### 2.4 网格栅格定义与 CSS Order 置换实现
```css
/* 基础容器 */
.app-container {
  display: grid;
  height: calc(100vh - 56px);
  max-height: calc(100vh - 56px);
  overflow: hidden;
  overscroll-behavior: none;
  background: var(--bg-body);
  transition: grid-template-columns 0.3s cubic-bezier(0.2, 0, 0, 1);
}

/* 1. 投研助手模式：AIChat 在中 (40%)，辅助展示在右 (60%) */
.app-container.layout-chat-center {
  grid-template-columns: 240px 4fr 6fr;
}
.app-container.layout-chat-center .app-middle-chat {
  order: 2;
}
.app-container.layout-chat-center .app-right-details {
  order: 3;
}

/* 2. 业务主工作区模式：业务区在中 (占满主视口)，AI助手在右 (390px) */
.app-container.layout-workspace-main {
  grid-template-columns: 240px 1fr 390px;
}
.app-container.layout-workspace-main .app-right-details {
  order: 2; /* 业务主工作区置于中间 */
}
.app-container.layout-workspace-main .app-middle-chat {
  order: 3; /* AIChatUI 定位为 AI助手置于右侧 */
  border-left: 1px solid var(--border-card);
  border-right: none;
}

/* 3. 业务主工作区模式下 AI助手收起：主工作区占满 100% */
.app-container.layout-workspace-main.copilot-collapsed {
  grid-template-columns: 240px 1fr 0px;
}
.app-container.layout-workspace-main.copilot-collapsed .app-middle-chat {
  display: none;
}
/* 收起时显示中间 Title 栏右侧小按钮 */
.app-container.layout-workspace-main.copilot-collapsed .btn-copilot-launcher {
  display: inline-flex;
}
```

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

### 5.1 极简标题栏规范与双模状态自适应
- **杜绝空间浪费**：移除传统对话应用大面积的欢迎 Banner、Slogan 标语及冗余胶囊，将上部区域高度压缩至 `44px`；
- **双模动态标题与收起交互**：
  1. **模式一（投研助手居中）**：
     - 标题展示为：`🤖 投研助手 ● 在线`；
     - 右侧按钮为：`[◀ 收起]`（点击调用 `toggleChatCollapse()`）；
  2. **模式二（定位为右侧伴随式 AI 助手）**：
     - 标题展示为：`🤖 AI助手 ● 协同中`；
     - 右侧按钮为：`[▶ 收起]`（点击调用 `toggleCopilot()`，平滑向右滑出折叠）；
  3. **收起后的中区 Title 联动呼出**：
     - 当 AI 助手在右侧收起时，中间主工作区 Title 栏右侧展示小按钮 `[🤖 AI助手]`；
     - 用户在中间主工作区点击任何 `💬 提问` 时，若 AI 助手处于收起状态，系统**自动唤醒展开右侧 AI 助手**并完成 Prompt 注入与聚焦。
- **标准标题排版模板**：
  ```html
  <div class="chat-header-simple">
    <div class="chat-simple-left">
      <div class="ai-avatar-pill-sm">AI</div>
      <h3 class="chat-simple-title" id="chatHeaderTitle">投研助手</h3>
      <span class="chat-status-dot" id="chatHeaderStatus">● 在线</span>
    </div>
    <button class="btn-collapse-chat" id="btnCollapseChat" onclick="handleChatCollapseBtn()" title="收起">
      <span class="collapse-icon" id="collapseIcon">◀</span>
      <span class="collapse-text" id="collapseText">收起</span>
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
| **双模动态视口与灵活定位** | `web/index.html`<br>`web/css/style.css`<br>`web/js/app.js` | `.layout-chat-center`, `.layout-workspace-main`, `handleMenuClick`, `switchLayoutMode` |
| **AI助手收起与Title小按钮** | `web/index.html`<br>`web/css/style.css`<br>`web/js/app.js` | `.copilot-collapsed`, `.btn-copilot-launcher`, `#btnCopilotLauncher`, `toggleCopilot` |
| **AIChatUI 极简标题与折叠** | `web/index.html`<br>`web/css/style.css`<br>`web/js/app.js` | `.chat-header-simple`, `#chatHeaderTitle`, `#btnCollapseChat`, `handleChatCollapseBtn` |
| **三段式菜单栏与无限滚动** | `web/index.html`<br>`web/js/app.js` | `.sidebar-sessions-list`, `renderSessionList`, `setupSessionInfiniteScroll` |
| **多标签页保留与左向右弹出** | `web/index.html`<br>`web/css/style.css`<br>`web/js/app.js` | `#rightTabsBar`, `projectToRight`, `popupSlideFromLeft` |
| **针对中右提问与参数修改** | `web/index.html`<br>`web/js/app.js` | `askAboutRightContent`, `askStockPrompt`, `applyRightParamForm` |
| **保本价进位与滑块试算器** | `web/index.html`<br>`web/js/app.js` | `updateProjectedCalculator`, `#resBreakeven`, `math.ceil` |
| **收益分析与 Canvas 图表** | `web/index.html`<br>`web/js/charts.js` | `drawEquityCurve`, `drawMonthlyPnLChart`, `.returns-overview-grid` |
