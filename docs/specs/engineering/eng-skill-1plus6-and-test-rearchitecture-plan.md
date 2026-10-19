# 生产级投研技能「1 + 6」物理精简与极速测试体系重构实施计划

- **计划编号**：`SPEC-SKILL-002-PLAN`（归属 [`SPEC-SKILL-002`](spec-skill-1plus6-consolidation-and-test-rearchitecture.md)）
- **权威定义 (SSOT)**：
  - [`docs/guidelines/engineering/skill-suite-portability-specification.md`](../../guidelines/engineering/skill-suite-portability-specification.md) §9（专业机构股票投研六步全链路闭环与符合性评估规范）
  - [`docs/guidelines/engineering/testing-guide.md`](../../guidelines/engineering/testing-guide.md) §9（极速测试体系重构与 WebAPI 独立分仓规范）
- **关联分时执行看板**：[`docs/specs/engineering/delivery-execution-roadmap.md`](delivery-execution-roadmap.md)（第二期：顺序 ⑫ ~ ㉑）
- **前置评估依据**：[`docs/audits/2026-10-19-skill-comprehensive-evaluation-and-governance-audit.md`](../../audits/2026-10-19-skill-comprehensive-evaluation-and-governance-audit.md)
- **实施状态**：⏳ **推进中（3 / 10 完成，当前活跃指针：`[▶] S2-04`）**

---

## 一、原子分时执行与防并发排他铁律 (Kanban Atomic Execution Protocol)

> [!IMPORTANT]
> 本计划中的所有任务（`S2-01` ~ `S2-10`）与 [`delivery-execution-roadmap.md`](delivery-execution-roadmap.md) 看板严格双向绑定，任何执行会话**必须无条件遵守以下原子状态机协议**：
>
> 1. **原子状态转移图**：
>    `[ ] 未启动` $\xrightarrow{\text{前序完成点亮}}$ `[▶] 就绪待认领` $\xrightarrow{\text{会话启动第一步加锁}}$ `[🚧 IN_PROGRESS: <session_id> | <YYYY-MM-DDTHH:MM+08:00>]` $\xrightarrow{\text{前台门禁 0 failed 解锁}}$ `[x] 已完成`
> 2. **先加锁后动代码（Check-out Lock First）**：
>    扫描到唯一的 `[▶]` 任务准备启动时，**第一步操作必须且只能**先将本文件第三节及 `delivery-execution-roadmap.md` 中对应任务的 `[▶]` 原子替换为 `[🚧 IN_PROGRESS: <session_id> | <时间>]` 并落盘保存，随后才允许修改业务代码或测试文件。
> 3. **严禁并发抢跑与重复认领（Anti-Race Guard）**：
>    若看板中已存在 `[🚧 IN_PROGRESS: ...]` 或无 `[▶]` 标记，严禁任何其他会话重复认领或越级抢跑后续任务。
> 4. **前台顺序验证，严禁后台挂起（Foreground Sequential Gate）**：
>    所有验证与测试门禁命令**必须在当前任务流中前台顺序同步执行**，严禁作为后台任务（Background Process）挂起；每完成一步验证必须确认退出码为 `0` 且 `0 failed`，随后才允许将 `[🚧 IN_PROGRESS: ...]` 更新为 `[x]`，并原子点亮下一项为唯一的 `[▶]`。
> 5. **强制符合性评估（Conformance Gate C1~C6）**：
>    每个任务完成时，必须在第五节验收台账中同步登记 **C1~C6 六维符合性评估结论**（闭环归属、循证溯源、失败关闭、胜率锚定、金字塔结论、实战三原则与极速测试）。

---

## 二、任务总览矩阵 (Task Matrix)

状态图例：`[ ] 未启动` · `[▶] 就绪待执行` · `[🚧 IN_PROGRESS: ...]` · `[x] 已完成` · `[⊘] 阻塞`

### 阶段一（Phase 1）：底层 6 大技术支撑引擎缺口闭合与循证底座升级（`S2-01` ~ `S2-03`）

| 任务 ID | 看板顺序 | 任务名称 | 归属投研闭环阶段 | 状态 | 核心验收门槛 |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **`S2-01`** | **顺序 ⑫** | **统一 `EvidenceEnvelope` 溯源信封 + 修复 G1/G2/G4（CLI 参数、真实双金叉与动态意图路由）** | 总控锚点 + ① 看盘知势 + ③ 择时定买 | `[x]` | `evidence_meta` 生成器就绪；`tools.py` 接入 `second_golden_cross` 与 `IntentEvaluator`；`astock action` 兼容位置/具名参数 |
| **`S2-02`** | **顺序 ⑬** | **实现退哥短线算法 `tuige.py` + 250 日同类信号历史胜率锚 + 修复 G3（五步真实 MA 股池审计）** | ③ 择时定买 + ⑤ 仓位风控 | `[x]` | `tuige.py` 识别涨停回踩/首阴接力；所有战法信号内嵌 250 日胜率锚；`pool audit` 完成五步 MA 重算与失效止损清洗 |
| **`S2-03`** | **顺序 ⑭** | **实现滚动样本外回测（Rolling OOS）与过拟合三重警报 + 修复 G5（统一研报税费与三级止损口径）** | ④ 穿透体检 + ⑥ 回测验证 | `[x]` | `backtest` 支持 `--oos` 并输出 IS/OOS 衰减与过拟合三重警报；`report_generator.py` 费率与 `-3%/-5%/-8%` 口径 100% 统一 |

### 阶段二（Phase 2）：「1 + 6」生产级股票投研技能物理精简与网关重塑（`S2-04` ~ `S2-07`）

| 任务 ID | 看板顺序 | 任务名称 | 归属投研闭环阶段 | 状态 | 核心验收门槛 |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **`S2-04`** | **顺序 ⑮** | **物理构建前三大生产级投研技能（`astock-market-data`、`astock-smart-screener`、`astock-tactical-signals`）** | ① 看盘知势 + ② 选股立池 + ③ 择时定买 | `[▶]` | 3 个新技能物理目录、`SKILL.md`、精炼 `references/` 与 SSOT 转发壳完备，符合 C1~C6 规范 |

| **`S2-05`** | **顺序 ⑯** | **物理构建后三大生产级投研技能（`astock-deep-diagnose`、`astock-portfolio-action`、`astock-paper-backtest`）及升级 `a-stock-agents`** | 总控锚点 + ④ 穿透体检 + ⑤ 仓位风控 + ⑥ 回测验证 | `[ ]` | 后 3 个专业技能与总控锚点 `a-stock-agents` 升级完毕，内建金字塔结论先行与实战三原则契约 |
| **`S2-06`** | **顺序 ⑰** | **物理清退旧 19 技能目录 + 升级 `skills_manifest.json`、`SkillRegistry`（含旧别名兼容）、`cli.py`、`tools.py` 与 `doctor.py`** | 全链路 1 + 6 网关 | `[ ]` | `skill_bundle/skills/` 物理精确为 7 个目录；`LEGACY_SKILL_ALIASES` 100% 兼容旧 19 ID；`doctor.py --json` 返回 `total_skills: 7` 且 `is_healthy: true` |
| **`S2-07`** | **顺序 ⑱** | **同步升级 Release 打包器、跨平台安装器（`install.ps1`/`install.sh`）与全仓规范文档口径（`1 + 6 = 7` 入口）** | 交付与生态闭环 | `[ ]` | `common.py`、`publish_release.py`、`install.ps1`/`sh`、`AGENTS.md`、`README.md` 全面对齐 `1 + 6`（7 入口） |

### 阶段三（Phase 3）：极速测试体系重构、WebAPI 独立分仓与前端测试清退（`S2-08` ~ `S2-10`）

| 任务 ID | 看板顺序 | 任务名称 | 归属测试域 | 状态 | 核心验收门槛 |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **`S2-08`** | **顺序 ⑲** | **物理清退前端/浏览器测试（`tests/frontend/` & `tests/browser/`）+ 独立构建 `tests/webapi/`（4 大高内聚后端 API 模块）** | WebAPI 独立分仓 (`-m webapi`) | `[ ]` | `frontend/` 与 `browser/` 彻底移除；`tests/webapi/` 4 个模块 + 懒加载 `conftest.py` 独立运行 `< 6s` 且 `0 failed` |
| **`S2-09`** | **顺序 ⑳** | **重构 `tests/core/`（6 大支撑引擎单测）与 `tests/skills/`（`1+6` 符合性评估与执行测试）+ 剥离 `tests/release/`** | 极速核心门禁 (`-m core`) | `[ ]` | `tests/core/` (6 文件) + `tests/skills/` (2 文件) 纯内存确定性测试建成；重型打包移入 `tests/release/` (`-m release_pack`) |
| **`S2-10`** | **顺序 ㉑** | **升级根 `tests/conftest.py`、`tools/validation/check.py`、`tests/README.md` 与 CI 矩阵并完成全链路收官验收** | 全局门禁收官 | `[ ]` | 前台顺序实测：① `pytest -m core` `< 8s` 全绿；② `pytest -m webapi` `< 6s` 全绿；③ `pytest -m release_pack` 全绿 |

---

## 三、分时原子执行清单 (Detailed Atomic Execution Steps)

### 阶段一：底层 6 大技术支撑引擎缺口闭合与循证底座升级

#### `[x]` 顺序 ⑫：`S2-01` — 统一 `EvidenceEnvelope` 溯源信封 + 修复 G1/G2/G4（CLI 参数、真实双金叉与动态意图路由）
- **前置依赖**：无（第一顺位启动项）
- **加锁指令**：启动前先将本行 `[▶]` 与 `delivery-execution-roadmap.md` 顺序 ⑫ 的 `[▶]` 替换为 `[🚧 IN_PROGRESS: <session_id> | <时间>]`
- **核心动作**：
  1. 在 `skill_bundle/runtime/core/data/` 或 `core/governance/` 新增标准循证溯源信封构造函数 `build_evidence_meta(...)`，统一输出 `as_of_trading_day`、`quote_source`、`kline_bars_count`、`watermark_ready`、`fee_rule_ssot`；
  2. **修复 G1**：在 `skill_bundle/runtime/core/cli.py` 中升级 `action` 子命令参数解析，同时兼容 `astock action 600519`、`astock action --code 600519` 以及 `astock action plan --code 600519`；
  3. **修复 G2**：在 `skill_bundle/runtime/core/execution/tools.py` 中改造 `_sync_astock_strategy_macd`，接入 `technical_indicators.second_golden_cross(klines)` 真实双波谷极值对比与间距过滤算法，废弃单日 `dif/dea` 简单三元判断；
  4. **修复 G4**：在 `tools.py` 中改造 `_sync_astock_meta_routing`，动态调用 `IntentEvaluator.parse_user_query` 输出真实意图分流结果。
- **符合性自检（C1~C6）**：核验 C2（确定性计算与 `evidence_meta` 信封）、C3（K 线不足时 Fail-Closed）。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe -m pytest tests/core/test_indicators.py tests/core/test_commands_suite.py -q`

---

#### `[x]` 顺序 ⑬：`S2-02` — 实现退哥短线算法 `tuige.py` + 250 日同类信号历史胜率锚 + 修复 G3（五步真实 MA 股池审计）
- **前置依赖**：`S2-01` 完成并解锁 ✅
- **实施状态**：`[x] 已完成（2026-10-19 实测通过：29 passed / 0 failed / 5.85s）`
- **核心动作**：
  1. **修复 G6（退哥战法代码化）**：新增 `skill_bundle/runtime/core/strategy/tuige.py`，实现涨停基因识别、缩量回调踩 MA5/MA10 支撑、龙头首阴断板次日弱转强及连板分歧接力纯 Python 判定引擎，并接入 `strategy_cmds.py` 与 `tools.py`；
  2. **内建 250 日历史胜率锚（C4 标准）**：在 `core/models/strategy_evaluator.py` 与战法输出层封装 `attach_contextual_win_rate_anchor(code, klines, signal_type)`，使主板波段、MACD 水下双金叉、陈小群四大战法、退哥短线在发出买点信号时，自动附带近 250 日同类信号触发次数、T+5 胜率、平均盈亏比与 45bps 成本过滤结论；
  3. **修复 G3（五步真实 MA 股池审计）**：升级 `core/strategy/pool_manager.py` 与 `core/commands/portfolio_cmds.py::cmd_pool_audit`，对非空股池拉取最新日 K 重算真实 `MA5/MA10/MA20/MA60`、检测现价跌破止损位或偏离均线 >15% 的失效标的，输出结构化 `stale_records`、`breached_stops` 与修复建议。
- **符合性自检（C1~C6）**：核验 C3（空股池即刻终止）、C4（250 日历史胜率锚与 45bps 成本过滤）、C6（实战三原则内嵌）。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe -m pytest tests/core/test_strategy_suite.py tests/core/test_pool_schema.py -q`

---

#### `[x]` 顺序 ⑭：`S2-03` — 实现滚动样本外回测（Rolling OOS）与过拟合三重警报 + 修复 G5（统一研报税费与三级止损口径）
- **前置依赖**：`S2-02` 完成并解锁 ✅
- **实施状态**：`[x] 已完成（2026-10-19 实测通过：22 passed / 0 failed / 64.00s）`
- **核心动作**：
  1. **修复 G6（模型样本外检验代码化）**：在 `skill_bundle/runtime/core/paper_trading/` 与 `core/commands/backtest_cmds.py` 中实现滚动样本外（Rolling Out-of-Sample）验证器，支持 `--oos` 参数，自动计算样本内（IS）与样本外（OOS）夏普比、胜率、最大回撤对比，并内建**过拟合三重警报（`Sharpe > 3.5`、`WinRate > 75%`、`IS-to-OOS 收益衰减 > 50%`）**；
  2. **修复 G5（统一研报税费与止损 SSOT）**：检查并统一 `core/reporting/report_generator.py`、`investment_report.py` 及报告模板中的佣金率（统一引用万 2.5 且最低 5 元起收 + 0.05% 印花税 + 过户费 + `math.ceil` 向上进位至分位）与 `-3% / -5% / -8%` 三级风控止损阶梯，彻底消除万 1.2 等陈旧口径。
- **符合性自检（C1~C6）**：核验 C2（费率 SSOT）、C4（防过拟合三重警报）、C6（保本价 `math.ceil` 与三级止损一致）。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe -m pytest tests/core/test_paper_trading_suite.py tests/core/test_robust_kline_and_report_html.py tests/core/test_commands_suite.py -q`

---

### 阶段二：「1 + 6」生产级股票投研技能物理精简与网关重塑

#### `[▶]` 顺序 ⑮：`S2-04` — 物理构建前三大生产级投研技能（`astock-market-data`、`astock-smart-screener`、`astock-tactical-signals`）
- **前置依赖**：`S2-03` 完成并解锁 ✅
- **加锁指令**：启动前先将本行 `[▶]` 与 `delivery-execution-roadmap.md` 顺序 ⑮ 的 `[▶]` 替换为 `[🚧 IN_PROGRESS: <session_id> | <时间>]`

- **核心动作**：
  1. 创建 `skill_bundle/skills/astock-market-data/`（对应阶段 ① **看盘知势**）：整合原 `astock-data-feed` 与大盘五维评估 `market`，编写生产级 `SKILL.md`、精选 `references/` 与三级寻址转发脚本；
  2. 创建 `skill_bundle/skills/astock-smart-screener/`（对应阶段 ② **选股立池**）：整合原 `astock-screener-5a`、`astock-selection-model` 与 `astock-quant-engine` 截面因子选股，编写生产级 `SKILL.md`、精选 `references/` 与转发脚本；
  3. 创建 `skill_bundle/skills/astock-tactical-signals/`（对应阶段 ③ **择时定买**）：整合原 `astock-strategy-mainboard`、`astock-strategy-macd`、`astock-strategy-chenxiaoqun` 与 `astock-strategy-tuige`，编写生产级 `SKILL.md`、精选战法 `references/` 与转发脚本。
- **符合性自检（C1~C6）**：逐一核对 3 个新技能的 Frontmatter、自描述调用约定、六步闭环职责边界与零包外死链。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe -c "from pathlib import Path; assert all((Path('skill_bundle/skills')/s/'SKILL.md').is_file() for s in ['astock-market-data','astock-smart-screener','astock-tactical-signals']); print('OK')"`

---

#### `[ ]` 顺序 ⑯：`S2-05` — 物理构建后三大生产级投研技能（`astock-deep-diagnose`、`astock-portfolio-action`、`astock-paper-backtest`）及升级 `a-stock-agents`
- **前置依赖**：`S2-04` 完成并解锁
- **核心动作**：
  1. 创建 `skill_bundle/skills/astock-deep-diagnose/`（对应阶段 ④ **穿透体检**）：整合原 `astock-platform-evaluate`、7 角色多空辩论 `astock-agent-debate`、单文件交互报告 `astock-report-html` 与联合归档 `astock-report-archive`，内建「金字塔结论先行 + 六维正交矩阵 + 双向证据链 + 实战三原则」标准；
  2. 创建 `skill_bundle/skills/astock-portfolio-action/`（对应阶段 ⑤ **仓位风控**）：整合原 `astock-action-execution`、三级股池 `astock-pool-dashboard`、五步真实 MA 审计 `astock-pool-audit` 与受限凯利头寸管理；
  3. 创建 `skill_bundle/skills/astock-paper-backtest/`（对应阶段 ⑥ **回测验证**）：整合原 `astock-trade-paper`、多股轮动回测与 `astock-model-validation` 滚动样本外 OOS 检验；
  4. 升级总控锚点 `skill_bundle/skills/a-stock-agents/SKILL.md`：吸收原 `astock-meta-routing` 与 `astock-knowledge-tips` 精华，更新意图路由表为 `1 + 6` 投研全链路闭环，保留 5 阶段 AI 安装引导卡片契约。
- **符合性自检（C1~C6）**：逐一核对后 3 个专业技能及锚点技能的 C1~C6 完备性。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe -c "from pathlib import Path; assert all((Path('skill_bundle/skills')/s/'SKILL.md').is_file() for s in ['a-stock-agents','astock-deep-diagnose','astock-portfolio-action','astock-paper-backtest']); print('OK')"`

---

#### `[ ]` 顺序 ⑰：`S2-06` — 物理清退旧 19 技能目录 + 升级 `skills_manifest.json`、`SkillRegistry`（含旧别名兼容）、`cli.py`、`tools.py` 与 `doctor.py`
- **前置依赖**：`S2-05` 完成并解锁
- **核心动作**：
  1. 物理移除 `skill_bundle/skills/` 下已被合并吸收的旧 19 个技能目录，确保 `skill_bundle/skills/` 下精确只剩 `1 + 6` 共 **7 个物理目录**；
  2. 更新 `skill_bundle/assets/config/skills_manifest.json` 为 6 项生产级专业技能权威定义，每个技能显式声明所属的投研闭环阶段（`research_stage`）与 `legacy_aliases`；
  3. 升级 `skill_bundle/runtime/core/governance/skill_registry.py`、`core/execution/tools.py`、`core/cli.py`、`core/commands/portfolio_cmds.py::cmd_skill_list` 与 `skill_bundle/runtime/doctor.py`：
     - 一等注册 `1 + 6` 技能与新增规范 CLI 子命令（`diagnose`、`signal` 等）；
     - 内置 `LEGACY_SKILL_ALIASES` 映射表，100% 透明兼容原 19 个旧技能 ID 调用；
     - `doctor.py --json` 自检输出 `total_skills: 7`, `business_skills: 6`, `is_healthy: true`。
- **符合性自检（C1~C6）**：验证 `1 + 6` 物理唯一性、旧别名零断裂、CLI `--json` 零污染。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe skill_bundle/runtime/doctor.py --json`

---

#### `[ ]` 顺序 ⑱：`S2-07` — 同步升级 Release 打包器、跨平台安装器（`install.ps1`/`install.sh`）与全仓规范文档口径（`1 + 6 = 7` 入口）
- **前置依赖**：`S2-06` 完成并解锁
- **核心动作**：
  1. 更新 `tools/packaging/common.py`、`tools/packaging/publish_release.py`、`install.ps1`、`install.sh` 中的技能计数预期（从 `19/20` 统一升级为 `6 项生产级专业投研技能 + 1 项锚点总入口 = 7 个标准入口`）；
  2. 同步更新 `AGENTS.md`（技能全景清单表更新为 `1 + 6` 矩阵与测试规约）、`README.md`、`docs/index.md`、`docs/quickstart.md`、`docs/guidelines/engineering/skill-suite-portability-specification.md` 前言与第 6 节计数口径。
- **符合性自检（C1~C6）**：验证 `publish_release.py --dry-run --json` 与 `install.ps1 -Inspect -Json` 退出码 0。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe tools/packaging/publish_release.py --dry-run --json`

---

### 阶段三：极速测试体系重构、WebAPI 独立分仓与前端测试清退

#### `[ ]` 顺序 ⑲：`S2-08` — 物理清退前端/浏览器测试（`tests/frontend/` & `tests/browser/`）+ 独立构建 `tests/webapi/`（4 大高内聚后端 API 模块）
- **前置依赖**：`S2-07` 完成并解锁
- **核心动作**：
  1. **清退前端界面测试**：物理删除 `tests/frontend/`（30 个 Node.js 脚本）、`tests/browser/`（Edge 浏览器验收目录）以及 `tests/server/test_browser_e2e_security.py`；
  2. **独立分仓 WebUI 后端测试（`tests/webapi/`）**：
     - 创建 `tests/webapi/conftest.py`（内聚懒加载 FastAPI `app`、`auth_headers`、`client`、`anon_client` fixture）；
     - 将原 `tests/server/` 下的后端测试重整合并为 4 个高内聚文件：
       - `tests/webapi/test_webapi_auth_and_session.py`
       - `tests/webapi/test_webapi_market_and_sync.py`
       - `tests/webapi/test_webapi_selection_api.py`
       - `tests/webapi/test_webapi_agent_dispatch.py`
     - 物理清理旧 `tests/server/` 零散文件。
- **符合性自检**：确认 `tests/webapi/` 无任何前端 HTML/DOM 测试，且单独运行耗时 `< 6s`。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe -m pytest tests/webapi -q`

---

#### `[ ]` 顺序 ⑳：`S2-09` — 重构 `tests/core/`（6 大支撑引擎单测）与 `tests/skills/`（`1+6` 符合性评估与执行测试）+ 剥离 `tests/release/`
- **前置依赖**：`S2-08` 完成并解锁
- **核心动作**：
  1. 将重型跨平台打包、解压与安装器测试精简迁移至 `tests/release/test_release_packaging_smoke.py`（标记为 `release_pack` 档，脱离默认 `core` 门禁）；
  2. 重构 `tests/core/` 为对应 6 大底层技术支撑引擎的 6 个纯内存极速单元测试文件（`test_engine_a_data_sync.py` ~ `test_engine_f_infra_safety.py`），清理冗余慢速旧文件；
  3. 重构 `tests/skills/` 为 2 个核心技能门禁文件：
     - `tests/skills/test_skill_suite_1plus6_contract.py`（常驻校验 `1 + 6` 物理目录、Frontmatter、六步投研闭环归属、C1~C6 符合性声明与旧别名映射）；
     - `tests/skills/test_skill_tools_execution.py`（常驻校验 `1 + 6` 技能在 CLI 与 `TOOL_MAP` 下的端到端调用、`evidence_meta` 溯源信封、空池即刻终止、250 日胜率锚与实战交易三原则输出）；
  4. 清理旧 `tests/governance/` 中已被吸收合并的冗余文件。
- **符合性自检（C1~C6）**：确认 `tests/core/` + `tests/skills/` 100% 覆盖 C1~C6 断言且无子进程打包阻塞。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe -m pytest tests/core tests/skills -q`

---

#### `[ ]` 顺序 ㉑：`S2-10` — 升级根 `tests/conftest.py`、`tools/validation/check.py`、`tests/README.md` 与 CI 矩阵并完成全链路收官验收
- **前置依赖**：`S2-09` 完成并解锁
- **核心动作**：
  1. 升级根 `tests/conftest.py`：移除顶层 FastAPI/Browser 耦合，按 `core`（`tests/core/` + `tests/skills/`）、`webapi`（`tests/webapi/`）、`release_pack`（`tests/release/`）清晰分档；
  2. 升级 `tools/validation/check.py`、`.github/workflows/ci.yml`、`tests/README.md` 与 `docs/guidelines/engineering/testing-guide.md` 实测基线数据；
  3. 前台顺序执行三大门禁（`pytest -m core`、`pytest -m webapi`、`pytest -m release_pack`），将实测耗时与计数回填至本计划第五节验收台账与 `delivery-execution-roadmap.md`。
- **符合性自检（C1~C6）**：全仓 `0 failed`，默认核心门禁 `pytest -m core` 实测耗时 `< 8s`。
- **前台顺序验证命令**：
  `.venv/Scripts/python.exe -m pytest -m core -q`

---

## 四、新增或改动技能六维符合性评估表（Mandatory Conformance Checklist）

在执行 `S2-01` ~ `S2-10` 以及后续任何技能迭代时，必须对照以下标准逐项核验：

| 评估项 | 评估维度 | 核验内容 | 状态 |
| :---: | :--- | :--- | :---: |
| **C1** | **六步投研闭环归属** | 100% 映射至「看盘知势 $\to$ 选股立池 $\to$ 择时定买 $\to$ 穿透体检 $\to$ 仓位风控 $\to$ 回测验证」，严守 `1 + 6` 物理目录上限 | 待核验 |
| **C2** | **循证溯源与零幻觉** | 所有技能输出顶层携带 `evidence_meta`（交易日、数据源层级、K线根数、水位状态、费率SSOT），确定性 Python 计算 | 待核验 |
| **C3** | **可靠性与失败关闭** | 4 级行情降级；K 线不足或停牌时 Fail-Closed (`DATA_UNAVAILABLE`)；空股池即刻终止并提示登记格式 | 待核验 |
| **C4** | **策略有效性锚定** | 战法信号附带近 250 日同类信号胜率与盈亏比锚定；45bps 成本过滤；回测内建滚动 OOS 与过拟合三重警报 | 待核验 |
| **C5** | **六维覆盖与金字塔结论** | 覆盖宏观情绪/财务排雷/技术动能/量价筹码/游资博弈/风控精算；第一屏 BLUF 结论先行（评级+核心观点+证伪位） | 待核验 |
| **C6** | **实战三原则与极速测试** | 强制输出 `math.ceil` 保本卖出价 + `-3%/-5%/-8%` 三级止损 + 三场景反应单；`pytest -m core` 前台顺序 `< 8s` 全绿 | 待核验 |

---

## 五、分时执行验收证据台账 (Acceptance Evidence Ledger)

> 每完成一个原子任务，持锁会话必须在此处登记实测命令、通过数、耗时与 C1~C6 符合性结论：

| 任务 ID | 完成时间 | 执行会话 / 证据命令 | 实测结果 (Passed / Failed / 耗时) | C1~C6 符合性结论 |
| :--- | :--- | :--- | :--- | :---: |
| `S2-01` | 2026-10-19 15:18 | `6c6a30ef-ce7c-462f-9289-082e7694fe34` / `pytest tests/core/test_indicators.py tests/core/test_commands_suite.py -q` | 15 passed / 0 failed / 36.32s（极速离线核心 247 passed / 29.34s） | ✅ C1~C6 全部通过 |
| `S2-02` | 2026-10-19 15:52 | `5d020c5c-8a4b-4832-8ae9-242040811fc7` / `pytest tests/core/test_strategy_suite.py tests/core/test_pool_schema.py -q` | 29 passed / 0 failed / 5.85s（回归 15 passed / 0 failed / 46.40s；极速离线核心 252 passed / 47.34s） | ✅ C1~C6 全部通过 |
| `S2-03` | 2026-10-19 16:15 | `848ecb18-dd45-4750-8ba6-6803b054d380` / `pytest tests/core/test_paper_trading_suite.py tests/core/test_robust_kline_and_report_html.py tests/core/test_commands_suite.py -q` | 22 passed / 0 failed / 64.00s（定向 14 passed / 7.12s） | ✅ C1~C6 全部通过 |
| `S2-04` | 待执行 | — | — | — |

| `S2-05` | 待执行 | — | — | — |
| `S2-06` | 待执行 | — | — | — |
| `S2-07` | 待执行 | — | — | — |
| `S2-08` | 待执行 | — | — | — |
| `S2-09` | 待执行 | — | — | — |
| `S2-10` | 待执行 | — | — | — |
