# A-Stock Agents 快速上手指南 (Quickstart Guide)

欢迎使用 **A-Stock Agents**。本项目是一套高内聚、自包含、生产就绪的 **A股全流程量化投研、多智能体协同研判与实战反应决策系统**。
支持全平台原生 CLI、现代浅色金融风格 Web 投研工作台，以及主流 AI Agent 平台（Google Antigravity、Hermes Agent、OpenAI Codex、Claude Code 等）的就地无缝接入。

---

## 一、环境要求与准备

- **操作系统**：Linux / Windows (PowerShell / CMD) / macOS
- **Python 环境**：Python 3.9 ~ 3.13（推荐 3.10 ~ 3.12）
- **核心依赖**：`requests`, `pandas`, `numpy`, `tabulate`, `pyyaml`, `scipy`, `fastapi`, `uvicorn`, `pydantic` 等（已完整定义在 `requirements.txt` 与 `pyproject.toml`）
- **包管理工具**：标准 `pip` 或极速包管理器 `uv`

---

## 二、一键安装部署

### 1. Linux / macOS
```bash
# 进入项目根目录
cd a_stock_agents

# 赋予执行权限并运行一键安装
chmod +x install.sh update.sh bin/astock
./install.sh
```

### 2. Windows (PowerShell)
```powershell
# 进入项目根目录
cd a_stock_agents

# 运行一键安装部署
.\install.ps1
```

> [!NOTE]
> **全自动环境就绪保障**：
> 安装脚本会自动创建独立的 Python 虚拟环境 `.venv`，安装项目所需全部核心依赖，并自适应就地配置 `.agents/skills` 技能目录，严格遵循**零全局污染原则 (Zero Global Pollution)**，绝不修改操作系统全局配置。

---

## 三、一键自检与验证 (Verify)

在正式使用前，建议运行全模块自动化就绪性测试，验证 11 项全链路能力（数据源降级、技术指标、多因子打分、保本价进位法则、模拟盘撮合及模块导入等）：

```bash
# 使用虚拟环境 Python 运行自检
python verify.py

# 或显式指定虚拟环境路径执行：
.\.venv\Scripts\python verify.py   # Windows
./.venv/bin/python verify.py         # Linux / macOS
```

当终端出现 `测试总结: 11/11 项测试通过！系统处于完全就绪状态 (ALL SYSTEMS GO)` 即表明系统已具备实战与投研条件。

---

## 四、双交互模式快速上手

项目支持 **Web 投研工作台** 与 **终端 CLI 工具链** 双交互模式，可依据使用习惯自由选择。

### 模式 A：现代 Web 投研工作台 (推荐)

系统内置现代浅色金融风格的 Web 投研工作台，具备三栏式 40/60 动态视口布局与流式 AI 投研助手：

#### 1. 启动 Web 后端网关服务
```bash
# Linux / macOS
./bin/astock server start

# Windows
.\bin\astock.cmd server start
```
服务默认监听在 `http://127.0.0.1:8000`。支持追加 `--port 8080` 或 `--reload`（热重载开发模式）。

#### 2. 在默认浏览器中调起投研界面
```bash
# Linux / macOS
./bin/astock ui
# 或
./bin/astock server preview

# Windows
.\bin\astock.cmd ui
# 或
.\bin\astock.cmd server preview
```

#### 3. 工作台核心功能
- **全景投研工作区**：内置分时/日K线走势图、五维健康度雷达图、资金流向监测、自选与持仓池实时监控。
- **AI 智能投研助手 (AIChat)**：支持从左向右平滑弹出与折叠收起，具备 SSE 打字机流式输出，原生挂载 ReAct 智能体循环与 17 项技能工具调用。
- **模拟盘操作面板**：支持账户切换、实时持仓盈亏分析、限价/市价委托下单与订单撤单。

---

### 模式 B：全功能 CLI 实战速查

跨平台统一执行底座：
- **Linux / macOS**: `./bin/astock <subcommand> [--json]`
- **Windows (CMD/PowerShell)**: `.\bin\astock.cmd <subcommand> [--json]`
- **全平台通用 Python 回退**: `python scripts/core/cli.py <subcommand> [--json]`

> [!TIP]
> 所有的 CLI 命令均原生支持追加 `--json` 参数，便于外部脚本、AI 智能体及第三方 API 解析。

#### 1. 实时行情与 4 级自动降级快照 (Quote)
```bash
# 查询贵州茅台实时行情
./bin/astock data quote 600519

# 批量查询股票行情 (输出结构化 JSON)
./bin/astock data quote 600519 000858 002594 --json
```

#### 2. 零编译经典技术指标计算 (Technical)
```bash
# 计算均线、MACD、KDJ、RSI、BOLL、ATR 及水下二次金叉信号
./bin/astock data tech 600519 --count 120 --json
```

#### 3. 5A 多维共振主线选股 (Screener)
```bash
# 结合市场动态主线、动量、质量与估值进行三层漏斗选股
./bin/astock screen --dynamic hot_sectors --limit 10 --json
```

#### 4. 多因子 100 分制综合诊断 (Evaluate)
```bash
# 对标的进行全维度量化打分与风险评估
./bin/astock evaluate 600519 --json
```

#### 5. 实战反应动作单与最低保本卖出价精算 (Action Plan)
> 严格计入卖出印花税（0.05%）、券商佣金（万2.5且最低5元起收）、过户费，并**强制向上精确进位至分位（`math.ceil`）**，杜绝隐性亏损。
```bash
# 核算买入成本 1450.00 元、200 股的保本价与场景动作
./bin/astock action plan --code 600519 --cost 1450.00 --shares 200 --json
```
**输出要素包含**：
- **精确最低保本卖出价**
- **三级风控止损阶梯**：T0 警戒线（-3%）、T1 减仓线（-5%）、T2 绝杀线（-8%）
- **三场景即时动作单**：开盘冲高、盘中窄幅震荡、跳水急跌触发条件与操作指令

#### 6. 被套持仓量化解套决策树 (Trapped)
```bash
# 持仓成本 1680.00 元，持仓 500 股，输出解套决策树（补仓/T+0/换股/止损）
./bin/astock trapped 600519 --cost 1680.00 --shares 500 --json
```

#### 7. 7 大 AI 分析师多空对抗辩论 (Debate)
```bash
# 调动基本面、量价、消息、政策、游资、筹码、首席风控官展开多轮对抗研判
./bin/astock debate 600519
```

#### 8. A 股真实撮合模拟盘与账户体系 (Paper Trading)
```bash
# 1. 查询账户资金余额与资产净值
./bin/astock trade balance

# 2. 模拟限价买入贵州茅台 100 股
./bin/astock trade buy 600519 100 --price 1400.00

# 3. 查看模拟盘当前持仓明细
./bin/astock trade positions

# 4. 模拟市价卖出股票
./bin/astock trade sell 600519 100 --market

# 5. 查看委托订单
./bin/astock trade orders
```

#### 9. 自包含交互式 HTML 诊断研报生成 (Report)
```bash
# 生成 1344px 居中、亚光白背景、红涨绿跌自包含单文件 HTML 分析报告
./bin/astock report 600519 --output output/reports/600519_report.html
```

#### 10. 个性化券商费率配置 (Config Market)
```bash
# 启动交互式向导配置自身券商费率 (支持万2.5、万1、免5设置)
./bin/astock config market --interactive

# 查看当前生效的印花税、佣金与过户费参数
./bin/astock config market
```

---

## 五、主流 AI Agent 平台集成指南

本项目设计严格遵循**零全局污染原则 (Zero Global Pollution)**，全部 17 项技能及底层量化引擎**就地运行在当前工作区内**，严禁将技能复制到系统全局目录。

### 1. Google Antigravity / Gemini CLI
- 将本项目根目录作为 Workspace 打开。
- Antigravity 自动识别工作区内 [`.agents/skills/`](file:///c:/Users/cvdnn/coding/a_stock_agents/.agents/skills) 的 17 项技能。
- 对话中直接输入自然语言，例如：“帮我分析茅台行情”、“5A选股”、“测算买入成本1500元的保本价”，智能体将自动路由至对应技能并调用 CLI 获取结构化数据。

### 2. Hermes Agent
- 直接在项目根目录下启动会话：
  ```bash
  hermes --skills-dir ./.agents/skills
  ```
- Hermes 自动按需读取系统提示词并执行量化子进程。

### 3. OpenAI Codex / Claude Code / Cursor / Cline
- 项目根目录已提供标准化 [`AGENTS.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/AGENTS.md) 与 [`CLAUDE.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/CLAUDE.md)。
- 智能体直接遵循规约，严禁自行编写网页爬虫脚本，统一直接调用 `./bin/astock <subcommand> --json` 获取输出。

---

## 六、用户专属数据隔离与安全运维

### 1. 专属数据隔离 (`output/`)
系统设计了严格的 `output/` 个人数据隔离目录，个人持仓、交易明细与回测日志不会随代码仓库提交：
```
output/
├── pools/             # 个人自选池、关注池、持仓池 CSV
├── positions/         # 个人持仓档案与实盘交易明细记录
├── reports/           # 个股深度研报、多股联合报告与复盘 HTML
├── cache/             # 本地行情运算、监控状态与临时缓存
└── backtest/          # 个人策略回测日志与绩效分析结果
```

### 2. 安全打包发布 (`bin/pack.py`)
执行打包时，工具**强制排除 `output/` 目录、实盘数据、`.venv` 与日志缓存**：
```bash
python bin/pack.py --tag v3
```

### 3. 安全热更新与防损回滚 (`bin/update.py`)
```bash
# Linux / macOS 安全升级
./update.sh -from-zip a_stock_agents_v3.zip

# Windows PowerShell 安全升级
.\update.ps1 -from-zip a_stock_agents_v3.zip

# 手动备份当前数据快照
python bin/update.py --backup-only

# 异常时一键回滚
python bin/update.py --rollback backup_20260902_174003
```

---

## 七、技术文档体系速查

如需查阅更多底层架构与设计方案，请参阅以下专项文档：

- **全景架构导图**：[`index.md`](index.md)
- **Web UI 界面设计与交互规范**：[`specs/ui-design-specification.md`](specs/ui-design-specification.md)
- **Web AIChat 与 Skill 治理架构**：[`specs/web-aichat-and-skill-governance.md`](specs/web-aichat-and-skill-governance.md)
- **最低保本卖出价精算数学公式**：[`trading/breakeven-rules.md`](trading/breakeven-rules.md)
- **实战交易反应动作操作手册**：[`trading/execution-manual.md`](trading/execution-manual.md)
- **算法资产全生命周期治理体系**：[`guidelines/algorithm-governance.md`](guidelines/algorithm-governance.md)
- **代码审查基准与防御模式**：[`guidelines/code-review.md`](guidelines/code-review.md)
- **自动化回归测试规范**：[`guidelines/testing-guide.md`](guidelines/testing-guide.md)
