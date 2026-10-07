# A-Stock Agents 测试用例架构与回归测试规范

本目录包含了 A-Stock Agents 项目的**全量功能回归测试套件**（Python 429 例 + Node.js 前端 29 脚本）。测试架构与系统工程架构全面对齐，划分为 **量化核心 (`core/`)**、**服务端与智能体 (`server/`)**、**架构与合规门禁 (`governance/`)** 以及 **前端交互 (`frontend/`)** 四大领域专属目录。

设计原则：**无外部网络强依赖（桩隔离）**、**核心门禁秒级反馈**、**断言必然执行**。

> 完整测试规范（编写硬性约束、整改记录、生产缺陷档案）见
> [`docs/guidelines/engineering/testing-guide.md`](../docs/guidelines/engineering/testing-guide.md)。
> 本文件是**目录级速查 + 执行入口**。

---

## 一、测试套件分层架构图

```text
tests/
├── conftest.py                   # ★ 分层唯一改动点：档位归属表(_TIER_BY_PATH/_TAGS_BY_PATH/_OVERRIDE_TAGS)
│                                 #   + 共享基座(app / auth_headers / client / anon_client / isolated_user_pools)
├── README.md                     # 本速查文档
├── core/                         # 【量化算法与核心底座】对应 scripts/core/ — 17 文件 / 182 用例
│   ├── test_algo_monitoring.py            # 算法运行时健康度与降级监控
│   ├── test_algo_registry.py              # 选股算法注册表与动态发现
│   ├── test_algorithm_optimizations.py    # 算法执行优化与向量化验证
│   ├── test_commands_suite.py             # 32 个模块化子命令注册、参数解析与 CLI 转发
│   ├── test_custom_output.py              # 自定义输出目录隔离与 ASTOCK_OUTPUT_DIR 环境变量
│   ├── test_data_assembler.py             # 数据装配(§11.3/11.4/11.7)、不可变快照清单与水位门禁
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
├── server/                       # 【服务端与智能体交互】对应 scripts/server/ — 17 文件 / 153 用例
│   ├── test_access_and_thought_fix.py     # 前缀推导与思考链提取验证
│   ├── test_agent_capability_execution.py # 智能体能力分发与执行链路
│   ├── test_agent_tool_technical_summary.py # 工具返回技术面摘要格式兼容性
│   ├── test_cors_security.py              # CORS 跨域白名单与安全策略
│   ├── test_data_sync_import.py           # 股池导入：预览只校验不落盘、提交尊重既有行
│   ├── test_data_sync_settings.py         # 数据同步设置：白名单范围校验、持久化与接线披露
│   ├── test_dataset_sync.py               # 数据集登记册同步管线（假 akshare 渠道 + 临时库）
│   ├── test_dataset_sync_funnel.py        # 资金/估值/分钟归档落盘、水位门禁与归档器去重
│   ├── test_debate_and_quant_tools.py     # 多空辩论与量化工具集成
│   ├── test_live_server_e2e.py            # 真实服务端到端集成 (需设置 A_STOCK_RUN_LIVE_E2E=1)
│   ├── test_llm_readiness.py              # 大模型配置与连通性就绪检查
│   ├── test_llm_stream_chunk_usage.py     # LLM 流式输出 Token 用量统计
│   ├── test_market_data_api.py            # 行情数据 REST API 端点
│   ├── test_market_data_sync_api.py       # 行情测速、守护控制、通达信导入与任务集成
│   ├── test_models_mgmt_security.py       # 模型凭证防泄漏与脱敏管理（含 SSRF 桩化 DNS）
│   ├── test_server_suite.py               # Web AIChat 后端数据库、会话与路由全套件
│   └── test_session_memory.py             # 会话记忆系统与多轮对话隔离
│
├── governance/                   # 【合规门禁、安全审计与架构契约】 — 10 文件 / 90 用例
│   ├── test_capability_truthfulness.py    # 真实性契约与虚假实现防护
│   ├── test_decoupling_suite.py           # 架构分层解耦与防循环依赖
│   ├── test_docs_suite.py                 # 文档真实性与反引号文件路径回归
│   ├── test_fail_fast_and_code_validation.py # 无数据即 fail-closed（DATA_UNAVAILABLE 契约）
│   ├── test_governance_suite.py           # 代码治理红线与合规审计
│   ├── test_production_authenticity.py    # 生产代码真实度校验
│   ├── test_quality_gates.py              # 算法质量门禁与准入标准
│   ├── test_security_audit.py             # 静态安全穿透测试与敏感文件保护
│   ├── test_security_suite.py             # HTML 报告 XSS 防御与 Zip Slip 路径穿越防御
│   └── test_skill_contracts.py            # 18 项就地技能的输入/输出契约测试
│
└── frontend/                     # 【前端 UI / DOM 仿真与交互】对应 web/ (Node.js) — 29 个独立脚本，不经 pytest 收集
    ├── test_at_operator.js                # @操作符浮窗布局、三池叠加排序与退格原子化删除
    ├── test_at_operator_null_safety.js    # @操作符空指针安全防御
    ├── test_chat_presentation.js          # 聊天卡片与交互式时间线渲染
    ├── test_chat_summary_markdown_and_html_report.js # Markdown/HTML 混合报告生成
    ├── test_data_sync_control_console.js  # 数据同步控制台 UI 契约
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

另有技能自带脚本级自测 2 个文件（`.agents/skills/*/scripts/test_*.py`，5 例），由 `testpaths` 一并收集。

---

## 二、分层门禁与执行策略（★ 先必要，后扩展，扩展需人工确认）

### 2.1 档位与标签模型

档位**不靠散落装饰器**，而是在 [`tests/conftest.py`](conftest.py) 的三张表里按文件集中声明，
收集期由 `pytest_collection_modifyitems` 自动补齐；改哪一档只改这一处。

| 表 | 作用 | 键粒度 |
| :--- | :--- | :--- |
| `_TIER_BY_PATH` | 优先级 `core` / `p1` / `p2`（互斥且全覆盖 429 例） | 文件 |
| `_TAGS_BY_PATH` | 能力标签 `slow` / `network` / `subprocess` / `e2e` / `live` | 文件 |
| `_OVERRIDE_TAGS` | 精准点名个别用例（键为 pytest `nodeid`，**不是** `item.name`） | 单用例 |

| 档位 | 用例数 | 判定标准 |
| :--- | ---: | :--- |
| **`core`** | **132** | **P0 契约门禁**——错了会直接产出假结论或造成资金/安全后果：数据装配与水位门禁、漏斗规则、技术指标、行情字段契约与费率 SSOT、落盘与零假数据、撮合与 T+1、税费保本与三级止损、真实性红线、XSS/Zip Slip、生产禁回落 mock |
| `p1` | 258 | 重要回归：服务端 REST 契约、设置持久化与接线披露、18 项技能契约、治理与质量门禁 |
| `p2` | 39 | 补充边界：文档真实性、注册表辅助路径、自定义输出目录 |

| 标签 | 用例数 | 含义 |
| :--- | ---: | :--- |
| `slow` | 94 | 单用例 > 1s（子进程冷启动、全市场扫描、完整辩论流水线） |
| `network` | 35 | 触达真实外网（行情降级重试、实时现价批量） |
| `subprocess` | 10 | 以子进程执行 CLI/脚本的集成用例 |
| `e2e` | 26 | 端到端链路（装配 → 规则 → 快照落盘） |
| `live` | 18 | 需预先启动真实服务，并显式开启 `A_STOCK_RUN_LIVE_E2E=1` 与 `A_STOCK_SERVER_TOKEN` |

### 2.2 执行顺序与确认门

**默认只执行 ①。② 用于定位。③~⑥ 一律先说明"核心门禁为何不足以覆盖本次改动 + 预计耗时 + 是否会触网/写盘"，取得人工确认后才跑。**

| 顺序 | 层级 | 命令 | 耗时 | 执行前提 |
| :--- | :--- | :--- | ---: | :--- |
| ① | **P0 核心（必跑）** | `-m core` | ~13s | 任何代码/测试改动后**无条件先跑**，唯一自动门禁 |
| ② | 核心离线极速（121 例） | `-m "core and not slow and not network and not subprocess"` | ~12s | ① 失败后定位时可自主使用 |
| ③ | 核心 + 重要回归（385 例） | `-m "core or p1"` | 介于 ①④ | **需人工确认** |
| ④ | 离线全量 | `-m "not network"` | ~64s | **需人工确认** |
| ⑤ | 全量串行 | （无参数） | ~68s | **需人工确认** |
| ⑥ | 全量并行 | `-n 4` | ~40s | **需人工确认**（需 `pytest-xdist`，已列入 `[test]` extras） |
| ⑦ | 含外网 | `-m network` | 视网络 | **需人工确认**，且须先告知会触达真实行情源 |
| ⑧ | 真实服务端 E2E | `A_STOCK_RUN_LIVE_E2E=1 pytest -m live` | 视环境 | **需人工确认**，须先启动已配置的服务 |

```bash
# ① 默认动作
.venv/bin/python -m pytest -m core

# ② 极速定位
.venv/bin/python -m pytest -m "core and not slow and not network and not subprocess"

# ③~⑥ 确认后再用
.venv/bin/python -m pytest -m "core or p1"
.venv/bin/python -m pytest -m "not network"
.venv/bin/python -m pytest
.venv/bin/python -m pytest -n 4

# 定位耗时来源
.venv/bin/python -m pytest -m core --durations=20
```

> 实测耗时（429 例，含约 8s 收集期固定开销）：① 12.5s ｜ ② 12.1s ｜ ④ 63.0s ｜ ⑤ 67.9s ｜ ⑥ 39.5s。
> `--strict-markers` 已启用，拼错的标记直接报错而非被静默忽略。
> **离线全量基线：0 failed**（394 passed · 35 例外网被 deselect · 0 skipped · 0 xfailed）。
> 以 `strict` 钉住的 4 个**生产缺陷**（`/api/watchlist` 捏造数据、静态 API Token 分支不可达、
> `/api/market/indices` 静态指数快照回落、`/api/portfolio/overview` 演示资金与收益）
> 已于 2026-10-07 全部修复并转为常驻回归用例，见测试指南 8.3。
> 含外网的 ⑤/⑥/⑦ 层需真实行情源，本轮未复跑，其数字为整改当期实测值。

**按目录执行**（`pytest tests/core/` 等）属"整目录无差别执行"，等价于跨入确认门；
日常请优先用 ①，仅在定位具体问题时使用单文件/单用例：

```bash
.venv/bin/python -m pytest tests/core/test_data_assembler.py -v
.venv/bin/python -m pytest tests/governance/test_skill_contracts.py -v
.venv/bin/python -m pytest "tests/core/test_stock_funnel.py::test_minute_timestamp_normalization_accepts_required_input_forms" -v
```

**前端（Node.js）** 29 个独立脚本静态断言 `web/*.html|js`，不经 pytest 收集：

```bash
node tests/frontend/test_at_operator.js
for f in tests/frontend/*.js; do node "$f" || echo "FAIL $f"; done   # 全量遍历属确认门范围
```

---

## 三、核心测试规约（必须严格遵守）

> 逐条细节与成因见 [`docs/guidelines/engineering/testing-guide.md`](../docs/guidelines/engineering/testing-guide.md) 第四、八章。

### 1. 规约一：功能修改，测试先行（Regression-First / TDD）
> **每次功能修改、新增或重构，必须先在对应领域子目录下升级/修改测试用例。**

- **修改量化算法/指标/策略** → `tests/core/`；**API/会话/模型路由** → `tests/server/`；
  **质量门禁/Skill 契约/安全** → `tests/governance/`；**前端 UI/交互** → `tests/frontend/`。
- 先观察用例在旧逻辑下失败（Red），再实现新逻辑使其通过（Green）。
- 交付前必须通过 ① P0 核心门禁；若改动落在 `p1` 覆盖面，须在结论中明确"建议追加 ③"，把决策权交回评审者。

### 2. 规约二：临时用例生命周期（Ephemeral Fix Tests Rule）
> 针对单次优化的临时用例，验证完成后必须合并沉淀或删除，严禁平铺堆积。

- 临时排查脚本写于 `scratch/` 或 `temp/`，验证后即删；
- 严禁以 `test_p0_fixes.py` 之类任务名长期堆在 `tests/` 根目录；
- 沉淀出的边界/契约断言必须并入对应标准领域套件；
- 严禁把中间产物写入 `output/`（用户交付物唯一落盘区）。

### 3. 规约三：断言必须"必然执行"（Anti-Vacuous-Assertion）
> **`if 条件: assert ...` 等于没有断言**——条件不成立时用例静默变绿。

- 要么用 fixture/monkeypatch **构造前提**后无条件断言；
- 要么 `pytest.skip("原因")`，让"未验证"在报告里可见。

### 4. 规约四：同文件严禁重名 `def test_`
Python 同名函数后者覆盖前者，前者**永不执行**而收集数看起来正常。历史上曾因此静默丢失 2 个用例（46 行死代码）。

### 5. 规约五：HTTP 用例必须走共享基座
`/api/*` 中间件默认要求有效用户会话（fail-closed）。裸建 `TestClient(app)` 会恒得 401，导致"403 越权防护"一类断言从未被真正验证（历史上 25 个用例因此空跑）。

| 需求 | 必须使用 |
| :--- | :--- |
| 已登录访问 | `client` |
| 断言"未登录被拒" | `anon_client` |
| 需要原始 app | `app`（会话级单例，勿再 `create_app()`） |
| 凭证须签在别的库 | 对该 `db_path` 单独 `create_auth_token` |

### 6. 规约六：严禁触碰用户真实目录
`output/pools/*.csv`、`output/reports/`、`local/market_data/`、`cache/` 均为用户私有资产或生产数据区。

- 读写股票池 / 断言"池为空" → `isolated_user_pools`（临时**空池**，表头取自 `pool_schema` SSOT；
  注意 `init_output_templates()` 会把 `.example` 的示例持仓行一并复制，导致空池分支根本无法触发）；
- 建 SQLite → `tmp_path`；`unittest.TestCase` 用 `tempfile.mkdtemp()` + `addCleanup`。

### 7. 规约七：外网 / DNS / 连通性必须桩化
行情取数桩 `DataBridge.get_realtime_quote`/`tencent_kline`/`get_kline_robust`；URL 探测桩 `urllib.request.urlopen`；
DNS 桩 `socket.getaddrinfo`（**桩 IP 必须用真公网段**，`203.0.113.0/24` 已被 `ipaddress` 判为 private）。
确需保留外网时必须打 `network` 标签。

### 8. 规约八：昂贵流水线只跑一次
用 canned 输入喂**真实**装配逻辑并以 **module 级 fixture** 复用；分发链路（`execute_tool`）单独验证——
注意必须 `monkeypatch.setitem(TOOL_MAP, ...)`，patch 模块级同名属性不生效。

### 9. 规约九：生产缺陷用 `xfail(strict=True)` 钉住
用例是对的、生产代码错时，**不得**删除或放宽断言。`reason` 须写清缺陷事实与代码位置；
`strict=True` 保证一旦修好会以 XPASS 失败强制提醒移除标记，绝不静默放行假数据。
