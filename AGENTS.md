# A-Stock Agents — 智能体工作区规则与就地执行规范 (AGENTS.md)

欢迎进入 **A-Stock Agents** 工作区。本项目是一套高内聚、自包含、生产就绪的 A股全流程量化投研与实战反应决策系统。

> [!IMPORTANT]
> **零全局污染原则 (Zero Global Pollution)**：
> 本项目的全部 17 项技能及底层量化引擎**完全就地运行在当前工作区内**。
> **严禁**将本项目的技能或配置复制到系统全局目录（如 `~/.gemini/config/skills`、`~/.hermes/skills` 或系统级路径）。无论在 Antigravity、Hermes、Codex 还是 Claude Code 中，直接在本项目工作区内就地按需调用即可。

---

## 🛠️ 跨平台执行底座契约 (Execution Contract)

在处理用户的量化、行情、选股、风控或回测需求时，**严禁自行编写临时的网络爬虫脚本**。必须直接调用本项目内置的统一 CLI 命令，并始终追加 `--json` 参数以获取结构化数据。

### 跨平台命令调用对照表

| 操作系统 | 推荐命令格式 | 示例 (查询茅台行情) |
| :--- | :--- | :--- |
| **Linux / macOS** | `./bin/astock <subcommand> --json` | `./bin/astock data quote 600519 --json` |
| **Windows (PowerShell 优先 / CMD)** | `.\bin\astock.ps1 <subcommand> --json`<br>(CMD: `.\bin\astock.cmd <subcommand> --json`) | `.\bin\astock.ps1 data quote 600519 --json` |
| **全平台通用 Python 回退** | `python scripts/core/cli.py <subcommand> --json` | `python scripts/core/cli.py data quote 600519 --json` |

---

## 🧭 17 项就地技能全景清单与意图路由 (Skills Manifest)

当用户提出具体投资与投研诉求时，请依据下表进行意图路由。如需查阅专业交易策略细节或进阶参数，可直接**就地读取** [`.agents/skills/<skill_id>/SKILL.md`](file:///Users/handy/workon/a_stock_agents/.agents/skills) 或 [`config/skills_manifest.json`](file:///Users/handy/workon/a_stock_agents/config/skills_manifest.json)。

| 技能 ID (`.agents/skills/`) | 适用场景与触发词 | 统一 CLI 调用入口 | 核心能力描述 |
| :--- | :--- | :--- | :--- |
| **`astock-data-feed`** | 行情、现价、K线、筹码分布、技术指标、板块资金 | `astock data quote <代码> --json`<br>`astock data tech <代码> --json` | 4级降级实时行情与日K线，全套经典技术指标与筹码模型 |
| **`astock-platform-evaluate`** | 全流程分析、股票诊断、综合打分、大盘健康度 | `astock evaluate <代码> --json` | 100分制量化打分、解套决策树与大盘健康度综合研判 |
| **`astock-screener-5a`** | 选股、5A选股、主线轮动、多维评分、牛股挖掘 | `astock screen 5a --json` | 量价/基本面/估值/主线旋转 5 维共振多因子选股模型 |
| **`astock-quant-engine`** | 截面因子、换手沉淀、MAD去极值、滚动IC | `astock quant pipeline --json` | 工业级量化工程计算流水线与因子合成引擎 |
| **`astock-action-execution`** | 保本价、止损位、开盘冲高/急跌应对动作单 | `astock action plan --code <代码> --cost <成本> --shares <股数> --json` | 计入全部税费并向上进位至分位（`ceil`）的保本价精算与三级风控 |
| **`astock-strategy-macd`** | 水下二次金叉、MACD底背离、双底形态 | `astock pattern macd <代码> --json` | 波谷极值对比与波段间距过滤的纯粹 MACD 经典形态识别 |
| **`astock-strategy-tuige`** | 退哥短线、涨停回调、连板接力、龙头首阴 | `astock shortline check --code <代码> --json` | 纪律严明的 A 股短线与接力交易规则库 |
| **`astock-strategy-mainboard`** | 主板波段、趋势回踩、防守反击、流动性池 | `astock strategy swing --code <代码> --json` | 聚焦主板大市值流动性品种的多波段防御策略 |
| **`astock-pool-dashboard`** | 股票池、自选股、关注池、持仓池查看 | `astock pool list --json` | 个人三级股票池生命周期管理与盘中监控 |
| **`astock-pool-audit`** | 审查股票池、清洗失效标的、支撑阻力重算 | `astock pool audit --json` | 自动清洗过期失效标的，更新关键位与止损参考 |
| **`astock-trade-paper`** | 模拟盘、模拟买入/卖出、账户资金、持仓查询 | `astock trade balance --json`<br>`astock trade buy/sell --json` | 考虑市场冲击滑点与 T+1 硬约束的真实撮合模拟盘 |
| **`astock-agent-debate`** | 多空辩论、7大分析师辩论、深度研报 | `astock debate <代码> --json` | 基本面/量价/消息/政策/游资/筹码/风控 7 角色对抗研判 |
| **`astock-report-html`** | HTML报告、可视化报表生成 | `astock report html --code <代码> --json` | 白色亚光背景、红涨绿跌、自包含单文件交互式报告 |
| **`astock-report-archive`** | 报告归档、多股联合报告 | `astock report generate --json` | 报告结构化持久化规范与多股聚合分析文档 |
| **`astock-meta-routing`** | 任务路由、大模型选型策略 | `astock tips --json` | 纯分析 vs 代码执行的任务分流规范与模型推荐 |
| **`astock-knowledge-tips`** | 避坑指南、集合竞价、防被封技巧 | `astock tips --json` | 历史实战踩坑经验、数据源降级策略与风控心法 |
| **`astock-model-validation`** | 外部AI时序模型检验、样本外回测 | `astock validate-model --json` | 外部时序模型（TimesFM/Kronos）的滚动样本外回测标准 |

---

## 🛡️ 实战交易三原则（智能体输出铁律）

在给用户输出任何个股分析结论与实战建议时，**必须强制包含以下三项要素**：
1. **精确最低保本卖出价**：严格按印花税（0.05%）、佣金（万2.5且最低5元起收）、过户费核算，并强制向上进位至分位（`math.ceil`），拒绝任何四舍五入。
2. **三级风控止损阶梯**：
   - T0 警戒线：$-3\%$（准备减仓或对冲）
   - T1 减仓线：$-5\%$（减仓 $50\%$ 保本防守）
   - T2 绝杀线：$-8\%$（无条件止损出局）
3. **三场景即时动作单**：明确开盘冲高、盘中窄幅震荡、盘中跳水急跌三种场景下的明确触发条件与应对操作。

---

## 📋 股池与持仓分析空数据处理规范 (Empty Pool Handling)

当用户要求分析【持仓/关注/自选】等股池时：
1. **调用股池数据**：通过 `./bin/astock pool list --json`、`./bin/astock trade positions --json` 或对应智能体工具获取真实数据。
2. **空数据即刻终止分析**：若调用股票数据为空（持仓池/自选池/关注池中无记录），**不用继续分析，严禁臆测、虚构股票或擅自推荐替代股票**。
3. **直接提示用户登记**：直接向用户提示还未登记相关股池，并提示用户登记示例与格式：
   - **持仓股登记**：`股票:股数@成本价`（例如持仓股：`000222:1000@25.1234`。格式：`股票:股数@成本价`）；
   - **关注/自选股登记**：直接输入股票代码或名称（例如：`000001`、`600519`）。

---

## 🧩 通用执行用户意图任务规则 (General Execution Rules for User Intent Tasks)

在理解、拆解与执行用户的各类复杂投资意图时（例如：大盘多指数行情分析、全市场主线筛选、多只自选股并行体检、持仓池逐一穿透诊断等），智能体认知规划系统与前端展示引擎**必须无条件遵循以下通用任务执行与编排规则**：

### 1. 任务分级模型 (Hierarchical Task Model)
所有用户意图执行链路统一采用四级树形层级，严禁平铺打散：
- **L0 根意图目标 (Root Intent)**：用户的原始请求目标（例如：“分析今日大盘走势及主力动向”）；
- **L1 意图阶段与批量父任务 (Batch Parent Task Container)**：当完成某一意图阶段需要并发或连续调用 $\ge 2$ 次同类型能力时，**必须创建批量父任务容器**，严禁以一级任务散落平铺；
- **L2 挂接原子子任务 (Hooked Subtasks)**：具体的每一次原子工具调用（如获取 `sh000001`、`399001`）**必须作为子任务直接挂接在对应的批量父任务下**，缩进展示；
- **L3 执行明细与结果抽屉 (Details & Data Drawer)**：各子任务的参数细节与最终返回数据在父容器底部的抽屉中聚合呈现。

### 2. 批量父任务命名与契约规范 (Batch Task Naming Contract)
批量父任务节点命名**无需包含外层【】方括号**，直接使用紧凑规范的标准模板：
$$\text{能力调用 <skill\_id> 任务（批量 <N> 次调用）}$$
- **命名示例**：
  - 调用 12 次数据接口：`能力调用astock_data_feed任务（批量12次调用）`；
  - 批量诊断 3 只持仓股：`能力调用astock_platform_evaluate任务（批量3次调用）`；
  - 批量精算 4 只个股保本价：`能力调用astock_action_execution任务（批量4次调用）`。
- **反例禁忌**：严禁带外层方括号（错误：`【能力调用astock_data_feed任务（批量12次调用）】`；正确：`能力调用astock_data_feed任务（批量12次调用）`）。

### 3. 子任务挂接与去冗余展示规范 (Subtask Attachment & Anti-Redundancy)
- **拒绝同类平铺**：同一意图下的多次同类型调用不得以独立的一级卡片连续刷屏；
- **结构化挂接显示**：每个原子调用在父任务分支导轨下显示为子节点：
  `• 子任务 <序号>: <能力名称> · <动作或摘要>`（例如：`• 子任务 1: astock_data_feed · 现价 3888.11 (-1.18%)`）；
- **层级折叠保护**：批量父任务提供统一的折叠/展开（`∨` / `>`）控件，让用户既能宏观把握执行进度，又能随时展开下钻微观调用细节。

### 4. 状态收敛与生命周期管理 (Lifecycle & State Convergence)
- **动态状态聚合**：父任务的状态由其挂接的子任务集合动态决定：
  - 所有子任务处于等待/运行中 $\to$ 父任务为 `运行中 (⏳)`；
  - 全部子任务成功 $\to$ 父任务为 `执行完成 (🔧)`；
  - 部分子任务异常/失败 $\to$ 父任务标记为 `局部降级或异常 (⚠️/❌)`，并高亮具体失败子任务；
- **数据集中交付**：子任务的执行结果在父任务完成后进行集中归并，一次性交付给下游分析师模型推演，避免零碎输出阻断思考链路。

