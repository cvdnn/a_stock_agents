# A-Stock Agents 测试用例架构与回归测试规范

本目录包含了 A-Stock Agents 项目的**全量功能回归测试套件**。测试架构与系统工程架构全面对齐，划分为 **量化核心 (`core/`)**、**服务端与智能体 (`server/`)**、**架构与合规门禁 (`governance/`)** 以及 **前端交互 (`frontend/`)** 四大领域专属目录。

所有用例统一遵循**无外部网络强依赖（Mock 隔离）**、**秒级运行**与**高覆盖率**的设计原则。

---

## 一、测试套件分层架构图

```text
tests/
├── conftest.py                   # 全局 pytest 配置与跨目录测试基座
├── README.md                     # 本规范文档
├── core/                         # 【量化算法与核心底座】对应 scripts/core/
│   ├── test_algo_monitoring.py            # 算法运行时健康度与降级监控
│   ├── test_algo_registry.py              # 选股算法注册表与动态发现
│   ├── test_algorithm_optimizations.py    # 算法执行优化与向量化验证
│   ├── test_commands_suite.py             # 32 个模块化子命令注册、参数解析与 CLI 转发
│   ├── test_custom_output.py              # 自定义输出目录隔离与 ASTOCK_OUTPUT_DIR 环境变量
│   ├── test_data_suite.py                 # QuoteDict 多别名索引、防注入白名单与费率常量 SSOT
│   ├── test_data_sync.py                  # 行情数据本地化落盘与增量同步引擎
│   ├── test_dynamic_universe.py           # 全市场流动性标的动态提取与板块权限控制
│   ├── test_indicators.py                 # 技术指标计算（MA/MACD/KDJ/RSI/BOLL/ATR）与缺口回补
│   ├── test_models_suite.py               # 5A 多因子打分、单调趋势评分与缺失维度归一化
│   ├── test_monitor.py                    # 交易日历网关（开盘/闭市状态机）与状态去重存储
│   ├── test_paper_trading_suite.py        # 模拟盘撮合引擎、涨跌停封板拦截与 T+1 状态机
│   ├── test_pool_schema.py                # 股票池 CSV 字段契约与黑名单过滤规则
│   ├── test_robust_kline_and_report_html.py # DataBridge 多级降级 K 线与自包含报告生成管道
│   ├── test_stock_funnel.py               # 股票漏斗筛选阶段与分钟级时间戳校验
│   └── test_strategy_suite.py             # 解套决策树、动作引擎真实契约与网格中轴算法
│
├── server/                       # 【服务端与智能体交互】对应 scripts/server/
│   ├── test_access_and_thought_fix.py     # 前缀推导与思考链提取验证
│   ├── test_agent_capability_execution.py # 智能体能力分发与执行链路
│   ├── test_agent_tool_technical_summary.py # 工具返回技术面摘要格式兼容性
│   ├── test_cors_security.py              # CORS 跨域白名单与安全策略
│   ├── test_debate_and_quant_tools.py     # 多空辩论与量化工具集成
│   ├── test_live_server_e2e.py            # 真实服务端到端集成 (需设置 A_STOCK_RUN_LIVE_E2E=1)
│   ├── test_llm_readiness.py              # 大模型配置与连通性就绪检查
│   ├── test_llm_stream_chunk_usage.py     # LLM 流式输出 Token 用量统计
│   ├── test_market_data_api.py            # 行情数据 REST API 端点
│   ├── test_models_mgmt_security.py       # 模型凭证防泄漏与脱敏管理
│   ├── test_server_suite.py               # Web AIChat 后端数据库、会话与路由全套件
│   └── test_session_memory.py             # 会话记忆系统与多轮对话隔离
│
├── governance/                   # 【合规门禁、安全审计与架构契约】
│   ├── test_capability_truthfulness.py    # 真实性契约与虚假实现防护
│   ├── test_decoupling_suite.py           # 架构分层解耦与防循环依赖
│   ├── test_docs_suite.py                 # 文档真实性与反引号文件路径回归
│   ├── test_fail_fast_and_code_validation.py # 快速失败防御与代码语法验证
│   ├── test_governance_suite.py           # 代码治理红线与合规审计
│   ├── test_production_authenticity.py    # 生产代码真实度校验
│   ├── test_quality_gates.py              # 算法质量门禁与准入标准
│   ├── test_security_audit.py             # 静态安全穿透测试与敏感文件保护
│   ├── test_security_suite.py             # HTML 报告 XSS 防御与 Zip Slip 路径穿越防御
│   └── test_skill_contracts.py            # 18 项就地技能的输入/输出契约测试
│
└── frontend/                     # 【前端 UI / DOM 仿真与交互】对应 web/ (Node.js)
    ├── test_at_operator.js                # @操作符浮窗布局、三池叠加排序与退格原子化删除
    ├── test_at_operator_null_safety.js    # @操作符空指针安全防御
    ├── test_chat_presentation.js          # 聊天卡片与交互式时间线渲染
    ├── test_chat_summary_markdown_and_html_report.js # Markdown/HTML 混合报告生成
    ├── test_dynamic_title_refinement.js   # 对话标题智能动态提炼
    ├── test_frontend_production_safety.js # 前端无侵入生产安全检查
    ├── test_frontend_session_memory.js    # 前端会话存储与切换
    ├── test_html_task_execution_and_content_truth.js # HTML 文件真伪性验证
    ├── test_initial_view_and_session_focus.js # 初始视图焦点与布局控制
    ├── test_markdown_render.js            # Markdown 解析与代码高亮
    ├── test_market_adaptive_layout.js     # 大盘行情自适应分栏布局
    ├── test_message_actions_lifecycle.js  # 消息重试、复制与撤销生命周期
    ├── test_model_popup_selector.js       # 模型切换浮窗交互
    ├── test_model_role_defaults.js        # 角色默认模型分配
    ├── test_model_settings_security.js    # 前端 API Key 存储安全
    ├── test_new_chat_submission_flow.js   # 新建会话与首次提交流程
    ├── test_session_delete_snapshot_isolation.js # 会话删除与快照隔离
    ├── test_session_history_consistency.js# 会话历史一致性校验
    ├── test_session_item_actions.js       # 侧边栏会话项操作
    ├── test_stream_jitter_and_summary_workflow.js # 流式输出防抖与摘要持久化
    ├── test_task_execution_ui.js          # 任务四级树执行进度条与抽屉呈现
    ├── test_task_summary_and_workbench_full_doc.js # 交付物在工作区完整展开
    ├── test_watchlist_deduplication.js    # 自选股列表去重
    ├── test_workbench_copilot_launcher_and_workspace_greetings.js # 问候语与快捷启动
    ├── test_workbench_header_module_actions.js # 工作台顶部导航栏交互
    ├── test_workbench_sections_isolation.js # 工作台各板块独立性
    ├── test_workspace_html_and_markdown.js# 工作区双格式呈现模式
    └── test_workspace_markdown_and_guide.js # 引导文档与工作区渲染
```

---

## 二、运行回归测试指南

### 1. 运行全量 Python 测试（自动递归全部子目录）
```bash
pytest tests/ -v
# 或通过项目虚拟环境：
.venv/bin/python -m pytest tests/ -v
```

### 2. 按领域分别运行 Python 测试套件
```bash
# 1. 量化底座与策略模型回归 (Core)
.venv/bin/python -m pytest tests/core/ -v

# 2. 治理门禁与契约安全审计 (Governance)
.venv/bin/python -m pytest tests/governance/ -v

# 3. 后端服务与路由 (Server)
.venv/bin/python -m pytest tests/server/ -v
```

### 3. 运行指定单用例示例
```bash
# 验证数据层与行情
.venv/bin/python -m pytest tests/core/test_data_suite.py -v

# 验证 18 个 Skill 契约
.venv/bin/python -m pytest tests/governance/test_skill_contracts.py -v

# 验证文档链接真实性
.venv/bin/python -m pytest tests/governance/test_docs_suite.py -v
```

### 4. 运行前端交互与 DOM 仿真测试 (Node.js)
```bash
# 验证 @操作符浮窗、富文本输入框与三池联动
node tests/frontend/test_at_operator.js

# 验证富文本聊天呈现引擎
node tests/frontend/test_chat_presentation.js
```

---

## 三、核心测试规约（必须严格遵守）

### 1. 规约一：功能修改，测试先行（Regression-First / TDD）
> **每次功能修改、新增或重构，必须先在对应领域子目录下升级/修改测试用例。**

- **修改量化算法/指标/策略**：在 `tests/core/` 对应的套件中更新断言；
- **修改 API 接口/会话/模型路由**：在 `tests/server/` 对应的套件中更新断言；
- **修改代码质量门禁/Skill契约**：在 `tests/governance/` 对应的套件中更新断言；
- **修改前端 UI/交互组件**：在 `tests/frontend/` 对应的用例中更新断言。

### 2. 规约二：临时优化用例生命周期规约（Ephemeral Fix Tests Rule）
> **针对某次特定缺陷调试的临时测试用例在验证完成后应及时合并沉淀，严禁将临时脚本随意平铺。**
