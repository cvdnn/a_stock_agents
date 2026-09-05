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
| **Windows (CMD/PowerShell)** | `.\bin\astock.cmd <subcommand> --json` | `.\bin\astock.cmd data quote 600519 --json` |
| **全平台通用 Python 回退** | `python core/cli.py <subcommand> --json` | `python core/cli.py data quote 600519 --json` |

---

## 🧭 17 项就地技能全景清单与意图路由 (Skills Manifest)

当用户提出具体投资与投研诉求时，请依据下表进行意图路由。如需查阅专业交易策略细节或进阶参数，可直接**就地读取** [`skills/<skill_id>/SKILL.md`](file:///Users/handy/workon/a_stock_agents/skills) 或 [`config/skills_manifest.json`](file:///Users/handy/workon/a_stock_agents/config/skills_manifest.json)。

| 技能 ID (`skills/`) | 适用场景与触发词 | 统一 CLI 调用入口 | 核心能力描述 |
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
