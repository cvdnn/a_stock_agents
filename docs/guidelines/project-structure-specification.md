# A-Stock Agents 项目工程结构与智能体工作区架构规范 (Project Structure & Workspace Specification)

> **文档类别**：工程规范 (Specification)  
> **适用范围**：全仓库 Python 源码、Web 前端、多智能体工作区、CLI 工具链与跨平台部署  
> **实施进度看板**：[`docs/specs/engineering/eng-project-structure-and-workspace.md`](../specs/engineering/eng-project-structure-and-workspace.md) (`SPEC-ENG-001`)

---

## 一、 核心设计哲学与四大架构基石 (Core Architecture Principles)

A-Stock Agents 作为一个高内聚、自包含且面向多智能体（Multi-Agent）协作的生产级 A 股量化投研系统，其工程结构严格遵循四大核心基石：

### 1. 零全局污染原则 (Zero Global Pollution)
- 本项目的全部 17 项技能（Skills）、系统提示词（Prompts）与量化引擎**完全就地运行在当前工程工作区内**；
- **严禁**将本项目的技能代码或环境依赖复制、软链接到操作系统的全局目录（如 `~/.gemini/config/skills`、`~/.hermes/skills` 或系统级 Python 路径）；
- 无论外部宿主智能体为 Google Antigravity、Hermes、Codex 还是 Claude Code，均在此工作区内就地触发执行，保证开发环境的完全自包含与宿主解耦。

### 2. 单一真理来源 (Single Source of Truth, SSOT) 与物理路径解耦
- 核心业务与量化算法统一归集于 `scripts/core/`，Web 服务网关归集于 `scripts/server/`，智能体就地技能存放在 `.agents/skills/`；
- **彻底根除代码库中的硬编码绝对路径与脆弱的软链接**。全链路必须使用动态项目根路径探测机制（`Path(__file__).resolve().parents[...]`），实现 Windows、Linux 与 macOS 全跨平台自洽运行。

### 3. 用户敏感数据强制物理隔离 (`output/`)
- 个人自选池、关注池、持仓档案、实盘交易流水账单、私人研报与本地缓存严格物理限定在 `output/` 目录；
- 安全打包发布工具（`bin/pack.py`）与版本控制系统（`.gitignore`）执行强制排除策略，严防任何用户个人敏感资产外泄。

### 4. 统一跨平台命令行门面 (Unified CLI Facade)
- 提供统一且语义对齐的 CLI 入口，各操作系统平台提供一致的体验（Windows CMD/PowerShell 下的 `.\bin\astock.cmd`、Linux/macOS 下的 `./bin/astock`，底层统一转发至 `python scripts/core/cli.py`）。

---

## 二、 工程目录拓扑全景 (Directory Hierarchy)

```text
a_stock_agents/
├── .agents/                 # ★ 智能体专属就地配置与技能资产 (零全局污染原则)
│   ├── manifests/           # 技能清单契约 (skills_manifest.json / yaml)
│   ├── prompts/             # AI 系统提示词与交易反应决策模版
│   │   ├── aichat_system_prompt.md       # AIChat 自然语言系统提示词与意图路由
│   │   ├── trading_action_prompts.md     # 实战动作单与风控指令提示词
│   │   └── trapped_diagnostic_prompts.md # 被套解套诊断决策树提示词
│   └── skills/              # 17 个标准化 Agent 就地技能包 (现代分层拓扑)
│       ├── astock-action-execution/      # 实战反应动作与精确保本价进位引擎
│       ├── astock-agent-debate/          # 7大AI分析师多空对抗辩论与决议
│       ├── astock-data-feed/             # A股全链路行情与技术指标数据引擎
│       ├── astock-knowledge-tips/        # 避坑指南与实战技巧库
│       ├── astock-meta-routing/          # 任务模型路由规则
│       ├── astock-model-validation/      # 外部时序 AI 模型样本外检验
│       ├── astock-platform-evaluate/     # 统一全流程投研与综合分析平台
│       ├── astock-pool-audit/            # 三大股池统一审查与清洗
│       ├── astock-pool-dashboard/        # 投研面板与股池生命周期管理
│       ├── astock-quant-engine/          # 工业级全流程量化工程引擎
│       ├── astock-report-archive/        # 报告结构化持久化与归档
│       ├── astock-report-html/           # 亚光白 1344px 居中交互报告规范
│       ├── astock-screener-5a/           # 5A 多维共振旋转选股模型
│       ├── astock-strategy-macd/         # 水下二次金叉与 MACD 底背离形态识别
│       ├── astock-strategy-mainboard/    # 主板流动性池多波段防御反击
│       ├── astock-strategy-tuige/        # 退哥短线与涨停接力规则体系
│       └── astock-trade-paper/           # A股模拟盘撮合交易与事件回测
├── bin/                     # 跨平台可执行入口与运维包装脚本
│   ├── astock / astock.cmd  # 全平台统一 CLI 启动器
│   ├── pack.py              # 纯净包安全发布工具
│   ├── run_skill.py         # 技能脚本就地执行器
│   └── update.py            # 安全热更新 + 数据快照备份 + 一键回滚
├── config/                  # 平台集中静态与环境配置中心
│   ├── config.yaml          # 主配置文件 (数据源、券商费率、三级风控止损参数)
│   ├── skills_manifest.json # 17 技能清单元数据与参数契约 (JSON)
│   ├── skills_manifest.yaml # 17 技能清单元数据与参数契约 (YAML)
│   └── stock_pools.yaml     # 预置关注池与基准测试对照股票池配置
├── docs/                    # 完整分级技术文档与架构设计规范中心
│   ├── index.md             # 全景知识库导图
│   ├── quickstart.md        # 快速上手向导
│   ├── guidelines/          # 工程规范、设计指南、系统架构与业务规则知识库
│   │   ├── README.md        # guidelines 知识导航中心与分类矩阵
│   │   ├── project-structure-specification.md # 本工程规范 (SSOT)
│   │   ├── ui-design-guide.md                 # UI 界面设计与交互指南
│   │   ├── web-aichat-architecture.md         # 独立 Web AIChat 与技能治理架构
│   │   ├── llm-provider-architecture.md       # 大模型双轨接入与角色分配架构
│   │   ├── token-security-architecture.md     # Token 链路安全网关架构
│   │   ├── a2ui-framework-architecture.md     # A2UI 前端渲染引擎架构
│   │   ├── a2ui-component-registry-specification.md # A2UI 组件库与注册机制规范
│   │   ├── broker-commission-rules.md         # 券商佣金与市场费率配置规则
│   │   ├── breakeven-calculation-rules.md     # 最低保本价精算与向上进位规则
│   │   ├── trading-execution-rules.md         # 实战交易反应动作与风控止损规则
│   │   ├── algorithm-governance.md            # 算法全生命周期治理指南
│   │   ├── code-review.md                     # 代码审查标准与红线清单
│   │   ├── testing-guide.md                   # 回归测试架构与规约
│   │   └── naming-conventions.md              # 架构命名规范与设计范式指南
│   ├── specs/               # 6 大领域实施进度与任务执行看板中心
│   │   ├── README.md        # 规范总览矩阵与落地进度看板
│   │   ├── engineering/     # SPEC-ENG-001 实施看板
│   │   ├── ui/              # SPEC-UI-001 实施看板
│   │   ├── architecture/    # SPEC-ARCH-001~003 实施看板
│   │   ├── a2ui/            # SPEC-A2UI-001~002 实施看板
│   │   ├── business/        # SPEC-BIZ-001~003 实施看板
│   │   └── algorithm/       # SPEC-ALGO-001 实施看板
│   ├── trading/             # 实战交易操作手册与快速参考
│   └── images/              # 架构全景图等静态资产
├── output/                  # ★ 用户私有数据强制隔离目录 (不纳入版本控制)
│   ├── pools/               # 自选·关注·持仓池 CSV
│   ├── positions/           # 持仓档案与实盘交易明细
│   ├── reports/             # 个股研报·多股报告·复盘 HTML
│   ├── cache/               # 本地计算缓存与盘中监控状态
│   └── backtest/            # 策略回测日志与绩效报告
├── scripts/                 # 系统核心 Python 源码工程
│   ├── core/                # 工业级量化金融内核
│   │   ├── cli.py           # 统一 CLI 子命令总路由器
│   │   ├── config.py        # 全局配置解析与热重载
│   │   ├── data/            # 4 级自动降级数据源桥接 (L1-L4)
│   │   ├── indicators/      # 零依赖纯 Python 经典技术指标库
│   │   ├── models/          # 5A 共振模型、AlgoRegistry 2.0
│   │   ├── strategy/        # 保本价精算、三级止损、三场景动作单
│   │   ├── multi_agent/     # 7 大 AI 分析师对抗辩论引擎
│   │   ├── paper_trading/   # 考虑平方根滑点与 T+1 规则的模拟盘
│   │   ├── governance/      # Skill 运行时中心与 Schema 校验
│   │   ├── monitor/         # 盘中守护与交易日历门控
│   │   └── reporting/       # 交互式单文件 HTML 研报渲染器
│   ├── server/              # FastAPI 服务网关与 Web 交互中枢
│   │   ├── app.py           # 统一应用入口与 FastAPI 装配
│   │   ├── run.py           # 服务启动入口
│   │   ├── db.py            # SQLite 会话与配置持久化
│   │   ├── models.py        # 共享数据契约模型
│   │   ├── agent/           # 原生 ReAct 智能体运行时 (react_runner, tools, events)
│   │   ├── api/             # 领域 RESTful 与 SSE 路由 (chat, models_mgmt, skills)
│   │   ├── llm/             # 大模型服务商适配与工厂 (factory, providers)
│   │   └── tasks/           # 异步任务与定时调度中枢
│   └── tools/               # 辅助工程与运维脚本
├── web/                     # 现代金融浅色风格 Web 投研前端
│   ├── index.html           # 现代单页 WebApp 主视图 (含 @操作符双栏浮窗与富文本输入框)
│   ├── css/                 # 样式系统 (style.css 金融色系、卡片、浮窗与标准属性)
│   └── js/                  # 前端控制逻辑与组件库
│       ├── app.js           # 业务主控制器 (AtOperatorRegistry、AtOperatorController、会话调度)
│       ├── charts.js        # 金融级 Canvas 图表
│       ├── ui_engine.js     # A2UI 核心动态调度与组件治理中枢
│       └── components/      # A2UI 领域组件包目录 (astock.js 等)
└── tests/                   # 核心领域回归测试套件 (Python 全量 + Node.js 前端交互)
    ├── test_commands_suite.py # 命令行总调度与子命令委托
    ├── test_data_suite.py   # 数据与配置基础设施
    ├── test_indicators.py   # 技术指标计算引擎
    ├── test_models_suite.py # 选股与多因子模型
    ├── test_strategy_suite.py # 实战策略与风控动作
    ├── test_paper_trading_suite.py # 模拟盘撮合与回测
    ├── test_security_suite.py # 安全脱敏与防御
    ├── test_monitor.py      # 盘中监控守护
    ├── test_pool_schema.py  # 股票池 Schema 校验
    ├── test_custom_output.py# 隔离环境与输出校验
    └── test_at_operator.js  # 前端 @操作符、股池排序、DOM退格与工作台联动测试
```

---

## 三、 核心子系统与职责边界 (Subsystem Responsibilities)

### 1. 智能体就地资产层 (`.agents/`)
- **`manifests/`**：存放 17 项技能的标准定义清单，定义每个技能的 CLI 命令模板、输入输出 JSON Schema、权限级别（只读 vs 交易写入）；
- **`prompts/`**：纳管投研助手对话意图识别提示词、交易动作生成提示词与被套解套决策树模版；
- **`skills/`**：包含 17 个按业务场景划分的标准就地技能，每个技能文件夹包含独立的 `SKILL.md` 指南与说明。

### 2. 核心量化底座层 (`scripts/core/`)
- 严格遵循高内聚、低耦合原则，不直接依赖任何外部 GUI 框架；
- 数据层（`data/`）实现自动 4 级降级（腾讯行情 -> 新浪行情 -> 东方财富 -> 本地缓存）；
- 策略执行层（`strategy/`）为所有交易指令计算提供单一真理来源（SSOT）。

### 3. Web 服务与网关层 (`scripts/server/` & `web/`)
- 采用 FastAPI 构建异步高并发网关，提供统一 REST API 与 SSE 长连接；
- 内置原生 ReAct Agent 推理循环，消除对第三方商业 Agent 平台的强绑定；
- Web 前端采用原生 Vanilla JavaScript 保持轻量与零编译构建依赖，集成 @操作符浮窗、富文本输入框与工作台联动中枢。

### 4. 测试套件层 (`tests/`)
- 维护 Python 核心量化引擎全量测试与 Node.js 前端 DOM 交互测试的确定性断言；
- 贯彻“测试先行，即测即删”铁律，保护基线测试永远处于 100% 绿灯幂等状态。

---

## 四、 跨平台路径与执行底座规范 (Cross-Platform Execution Rules)

1. **统一使用 `pathlib.Path`**：
   禁止任何针对物理路径的硬编码字符串拼接（如 `\` 或 `/`）。所有跨层级定位一律采用 `Path` 抽象：
   ```python
   # 规范推荐写法
   from pathlib import Path
   PROJECT_ROOT = Path(__file__).resolve().parents[2]
   CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
   ```
2. **命令调度一致性**：
   所有对外输出与执行调用必须遵循统一 CLI 契约，支持 `--json` 格式化管道输出。跨平台调用格式对比如下：
   - **Linux / macOS**：`./bin/astock <subcommand> --json`
   - **Windows**：`.\bin\astock.cmd <subcommand> --json`
   - **通用 Python 回退**：`python scripts/core/cli.py <subcommand> --json`
