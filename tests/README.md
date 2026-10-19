# A-Stock Agents 测试用例架构与回归测试规范 (SPEC-SKILL-002)

本目录包含了 A-Stock Agents 项目的**全量功能回归测试套件**（经 `SPEC-SKILL-002` 体系重构，彻底清退前端 30 脚本与浏览器 16 例，实现纯内存秒级核心门禁与独立 WebAPI 分仓）。测试架构与系统工程架构全面对齐，划分为 **量化核心 (`core/`)**、**技能契约与执行 (`skills/`)**、**WebUI 后端独立分仓 (`webapi/`)**、**发布交付冒烟 (`release/`)** 以及 **合规架构治理 (`governance/`)** 五大高内聚领域专属目录。

设计原则：**无外部网络强依赖（桩隔离）**、**核心门禁秒级反馈 (< 8s)**、**前端零自动化测试**、**断言必然执行**。

> 完整测试规范（编写硬性约束、整改记录、生产缺陷档案）见
> [`docs/guidelines/engineering/testing-guide.md`](../docs/guidelines/engineering/testing-guide.md)。
> 本文件是**目录级速查 + 执行入口**。

---

## 一、测试套件分层架构图

```text
tests/
├── conftest.py                   # ★ 分层唯一改动点：档位归属表(_TIER_BY_PATH/_TAGS_BY_PATH) + 共享基座
├── README.md                     # 本速查文档
├── core/                         # 【6 大纯内存底层支撑技术引擎】对应 SPEC-SKILL-002 Engine A ~ F — 6 文件 / 34 用例
│   ├── test_engine_a_data_sync.py        # Engine A: 行情增量同步、4级降级与水位门禁
│   ├── test_engine_b_factors_tech.py     # Engine B: 零依赖技术指标(MA/MACD/KDJ/BOLL/ATR)与五大财务排雷
│   ├── test_engine_c_funnel_iss.py       # Engine C: AST条件树编译、四阶漏斗与ISS版本调度
│   ├── test_engine_d_tactics_risk.py     # Engine D: math.ceil保本价、三级止损(-3%/-5%/-8%)、三大战法与五步MA审计
│   ├── test_engine_e_paper_backtest.py   # Engine E: 真实滑点与T+1撮合、多股轮动、滚动OOS与过拟合三重警报
│   └── test_engine_f_infra_safety.py     # Engine F: 交易日历网关、三桶目录隔离、HTML XSS防护与费率SSOT
│
├── skills/                       # 【1 + 6 生产级投研技能符合性与执行】— 2 文件 / 10 用例
│   ├── test_skill_suite_1plus6_contract.py  # 1+6 物理目录、Frontmatter、六步闭环归属与旧别名兼容
│   └── test_skill_tools_execution.py        # 1+6 技能端到端调用、evidence_meta 溯源信封、空池拦截与实战三原则
│
├── webapi/                       # 【WebUI 后端独立分仓 (-m webapi)】对应 apps/web-console/backend/server/ — 4 文件 / 42 用例
│   ├── conftest.py                       # WebAPI 专属懒加载 fixture (FastAPI app, auth_headers, client, anon_client)
│   ├── test_webapi_auth_and_session.py   # 会话 CRUD、消息记忆、RBAC 权限、CORS 安全与模型凭据脱敏
│   ├── test_webapi_market_and_sync.py    # 行情零虚假数据、持仓全景 sourced empty、4级 ping 探针与同步设置
│   ├── test_webapi_selection_api.py      # 选股模型 REST/SSE 接口、阶段 E 跟踪/评价与越权拦截
│   └── test_webapi_agent_dispatch.py     # Web Agent 工具调用分发、空池引导提示词与 LLM 就绪性守卫
│
├── release/                      # 【发布交付与打包安装集成 (-m release_pack)】— 1 文件 / 13 用例
│   └── test_release_packaging_smoke.py   # 跨平台 ZIP 打包、目录隔离解压、install.ps1/install.sh 模拟安装与生命周期
│
└── governance/                   # 【合规门禁、安全审计与架构契约 (-m p1 / p2)】— 9 文件 / 83 用例
    ├── test_capability_truthfulness.py   # 真实性契约与虚假实现防护
    ├── test_decoupling_suite.py          # 架构分层解耦与跨板块权限控制
    ├── test_docs_suite.py                # 文档真实性与反引号文件路径回归
    ├── test_fail_fast_and_code_validation.py # 无数据即 fail-closed (DATA_UNAVAILABLE 契约)
    ├── test_governance_suite.py          # 1+6 治理红线、异步任务队列与端口探针
    ├── test_production_authenticity.py   # 生产代码真实度校验
    ├── test_quality_gates.py             # 算法质量门禁与前端/浏览器彻底清退守卫
    ├── test_security_audit.py            # 静态安全穿透测试与敏感文件保护
    └── test_security_suite.py            # HTML 报告 XSS 防御与 Zip Slip 路径穿越防御
```

---

## 二、三大分层门禁与执行策略（★ 严禁后台挂起，直接在任务中顺序执行）

### 2.1 档位与标签模型

档位在 [`tests/conftest.py`](conftest.py) 中按文件集中声明，收集期由 `pytest_collection_modifyitems` 自动补齐。

| 档位 | 用例数 | 耗时标准 | 判定标准与覆盖面 |
| :--- | ---: | :---: | :--- |
| **`core`** | **44** | **< 8s**（秒级） | **P0 纯内存极速核心门禁**：6 大底层支撑技术引擎（Engine A ~ F）+ 1+6 投研技能符合性评估（C1~C6）与执行契约，任何改动必跑，无条件前台同步执行 |
| **`webapi`** | **42** | **< 28s** | **WebUI 后端独立分仓门禁**：FastAPI 路由、Bearer 鉴权、RBAC、数据同步、选股模型 REST/SSE 与智能体工具分发 |
| **`release_pack`**| **13** | **< 18s** | **发布交付与打包安装门禁**：ZIP 归档构建、三平台安装器执行、目录隔离解压冒烟与生命周期校验 |
| **`p1`** | **79** | ~30s | **治理与架构合规门禁**：真实性契约、代码解耦、安全穿透、数据不可用失败关闭 |
| **`p2`** | **4** | ~1s | **文档与辅助路径回归**：文档反引号路径检验、辅助工具自检 |

### 2.2 前台顺序执行命令速查

> **【禁止后台执行铁律】**：严禁将测试命令作为后台进程（Background Process / Background Task）挂起异步执行（避免界面产生 `Background Process Running`）。所有门禁与测试必须在任务当前上下文中**直接前台顺序执行**。

```bash
# ① P0 核心门禁（默认必跑，纯内存确定性测试，耗时 < 8s）
python -m pytest -m core -q

# ② WebUI 后端门禁（WebAPI 独立分仓，耗时 < 28s）
python -m pytest -m webapi -q

# ③ 发布交付与打包安装集成门禁（耗时 < 18s）
python -m pytest -m release_pack -q

# ④ 质量门禁流水线（带双层动态进度条与智能裁剪）
python tools/validation/check.py
python tools/validation/check.py --core
python tools/validation/check.py --webapi
python tools/validation/check.py --release-pack
```

---

## 三、用例编写铁律（Review 逐条对照）

1. **断言必须必然执行**：严禁 `if 条件: assert`；
2. **同文件禁重名 `def test_`**：避免静默覆盖与收集数虚高；
3. **HTTP 用例必须走 `client`/`anon_client`**：杜绝因无凭证导致批量 401；
4. **禁写真实目录**：必须使用 `isolated_user_pools` 或 `tmp_path`；
5. **外网与 DNS 必须桩化**：确需网络则打 `network` 标签；
6. **前端界面零测试**：严禁设计任何针对前端 HTML/CSS/DOM 的自动化测试。
