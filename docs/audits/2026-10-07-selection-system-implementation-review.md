# 智能选股系统 · 实现情况审查与实施计划（2026-10-07）

> 审查对象：智能选股系统（Intelligent Stock Selection System，ISS）
> 权威规范（SSOT）：[`SPEC-ALGO-ISS-001`](../guidelines/algorithm/selection-system-specification.md)、[`SPEC-ALGO-ISS-MT-001`](../guidelines/algorithm/selection-model-types-specification.md)
> 决策看板：[`selection-system-plan.md`](../specs/algorithm/selection-system-plan.md)、[`pending-backlog-plan.md`](../specs/algorithm/pending-backlog-plan.md)
> 审查方法：规范/看板 × 代码 × 测试三方交叉核对（只读静态审查 + P0 核心门禁实测）
> 严重度分级：🔴 阻断（里程碑门禁未达）、🟡 缺口（层内未落地）、🟢 完善（覆盖度不足）

---

## 一、总体结论

看板自述状态为 **"规划中 (RFC)"**。全仓库检索 `selection-models` / `screen-model` / `SelectionModelTypeRegistry` / `CompiledSelectionPlan` **仅命中文档，无任何代码**。

结论：**策划与裁定完备（4 批裁定 + 里程碑 M-01～M-05），但工程落地仅完成"层级漏斗执行内核 + 数据装配 + 手工 CLI"一条底座链路；面向用户的自建模型、调度、API、Web 工作台全部缺失。**

> **批次一执行结果（2026-10-07）**：本文 §七 批次一（A1～A8，目标 M-02）**已全部交付并落盘**——核心引擎层由"底座链路"升级为**可编译、可哈希、可版本化、可发布/激活、可整链执行**：v2 Schema 与 v1→v2 内存迁移器、`definition_hash`/`plan_hash` 规范化哈希、嵌套 `AND/OR/NOT` AST（Kleene 强三值）、`CompiledSelectionPlan` 编译器、模型类型注册中心、规则参数 Schema 元数据、版本仓库（草稿悲观锁 + 发布/激活/回滚）、`run-all` 编排器。交付物与验证见本文 **§十一**。
> 仍缺：面向用户的自建模型向导、调度执行器、API、Web 工作台（属批次二/三），**M-03～M-05 判定不变**。

> **批次二执行结果（2026-10-07）**：本文 §七 批次二（B1～B7，目标 M-03）**已交付并落盘**——新增 `selection_models/scheduler.py`（内置 Tick 常驻 + `funnel daemon`/`tick`，真实读取 YAML 4 处 `schedule`、`TradeCalendar` 门控、优雅退出）、`run_lock.py`（运行锁粒度 `model_id+trade_date`、运行期持有、持有者可见）、`signal_latch.py`（`converge_at_window_end` 窗口末唯一终态 + 追加 `latched_by_run_id`）、`run_repository.py`（当日状态按交易日重建、跨日过期不恢复、运行元数据/候选落盘、90 天淘汰且信号切片受保护）、`paths.py`（§13.10 落盘唯一派生点）；`data_assembler` 扩展分层 `UniverseWatermark`（R-03/A-05）与覆盖率硬门禁；修复 W-10 市值缺失置零（底层 `tencent_quote` 缺失→`None`）并校验 W-09 单位口径。交付物与验证见本文 **§十二**。
> 仍缺：面向用户的自建模型向导、API、Web 工作台（属批次三），以及 D-11 增量同步就绪后的覆盖率 100% 实际达标。

> **批次三执行结果（2026-10-07）**：本文 §七 批次三（C1～C5，目标 M-04）**已交付并落盘**——新增 `scripts/server/api/selection_models.py`（§15 全套非二期端点 + 统一水印包裹）、`core/selection_models/catalog.py`（模型目录/空白与模板创建/文案草稿确定性解析/调度定义存储）；扩展 `run_repository.py`（逐阶段明细、候选轨迹、正式信号落盘与查询、按版本/状态/触发方式过滤分页）与 `paths.py`；`auth/dependencies.py` 新增 10 项选股权限（menu + action 两段式）与 `model_author` 内置角色种子（`db.py`）；`run_repository` 与 SSE 事件流（`run.started`/`stage.completed`/`run.finished`/`run.failed`/`heartbeat`，含 `run_id` 与水印）落地；Web 工作台新增 `web/js/selection-models/` **18 个模块**，`#pane-selection` 由 fail-closed 空壳升级为真实接口驱动。新增用例 `tests/server/test_selection_models_api.py`（17 例）。交付物与验证见本文 **§十三**。
> **M-04 判定**：发布门禁 2、3、10、18 对应的可交付能力已落地（空白创建→保存草稿→发布→激活→无编码运行；数字来自后端运行记录；正式运行与调试运行隔离；多模型多次运行互不覆盖）。**明确边界**：§15.3 的阶段 E 端点（`assessments`/`tracking-plans`/`evaluations`/`tuning-suggestions`）按裁定归**批次四（二期）**，本轮**不暴露**；G-01 技能登记仍待同步三处清单。

> **批次四执行结果（2026-10-07）**：本文 §七 批次四（E1～E5，阶段 E：结果研究/持续跟踪/评价/调优）**已交付并落盘**——新增 `market_view.py`（行情视图与统计基元：Bar 归一、涨跌停、MFE/MAE、未来数据检测、T+N 交易日历）、`position_policy.py`（可回测 `PositionPolicy`，缺账户规模/成交价不生成伪精确股数与保本价）、`backtest_service.py`（信号标记分析 vs 事件驱动策略回测**口径严格分离**，含 T+1/整手/涨跌停/摩擦成本/未来数据检测）、`result_assessment.py`（`ResultAssessment`：个股信息+入选证据+风险画像+相对表现+建仓持股策略）、`tracking_service.py` + `tracker_scheduler.py`（`TrackingPlan` 与**只追加**的 `TrackingObservation`、Tracker Tick 幂等且水位未就绪不写伪观察）、`model_evaluator.py`（`ModelEvaluation`：T+N 汇总、分层流失、规则分组、版本对比，D-16 阈值不足即 `EVALUATION_SAMPLE_INSUFFICIENT`）、`optimization_advisor.py`（只读 `OptimizationSuggestion`，`pending→accepted/ignored`，活动版本变化即 `STALE`）；`paths.py` 扩展阶段 E 落盘派生点；`selection_models.py` 注册 §15.3 阶段 E 端点与 `researcher`/`model_author` 权限边界。新增用例 `tests/core/test_selection_stage_e.py`（16 例，`core` 档）与 `tests/server/test_selection_stage_e_api.py`（4 例，`p1` 档）。交付物与验证见本文 **§十四**。
> **二期（阶段 E）判定**：发布门禁 12、14、15、16、17、19 对应的可交付能力已落地（回测/跟踪不表述为未来收益保证；观察可追溯至原始信号且重复 Tick 幂等；回测计入 A股约束与配置化摩擦成本并通过未来数据检测；样本不足不出强结论且建议不自动改版；建仓持股策略标识为研究方案、无自动下单路径；建议仅基于已完成历史运行与跟踪并可追溯 `run_id`）。**明确边界**：`screen-model` 族 CLI（§14）与 Web 结果研究/跟踪/评价页签（§16 8～10）未在本批次内接线；M-05（阶段 F 正式可用）判定不变。

按里程碑判定：**M-01 达成；M-02 达成（批次一交付）；M-03 部分达标（2026-10-07 批次二交付，调度侧全绿 + 发布门禁 1、4、5、6、7、11 落地；门禁 13 与覆盖率 100% 实际达标待 D-11 增量同步就绪）；M-04 达成（2026-10-07 批次三交付，发布门禁 2、3、10、18 落地）；二期（阶段 E）达成（2026-10-07 批次四交付，发布门禁 12、14、15、16、17、19 落地；`screen-model` 族 CLI 与 Web 结果研究页签待后续增强）；M-05 未启动。**

| 里程碑 | 内容 | 判定 |
|---|---|:--:|
| M-01 | 一期范围与规格冻结 | ✅ 达成 |
| M-02 | 阶段 A：配置与核心引擎 | ✅ 达成（2026-10-07 批次一交付；运行期版本绑定待批次 C 补验） |
| M-03 | 阶段 B：数据与调度 | 🟡 批次二交付：调度侧全绿、覆盖率硬门禁落地；100% 实际达标待 D-11（部分达标） |
| M-04 | 阶段 C+D：API/持久化与 Web | ✅ 达成（2026-10-07 批次三交付；发布门禁 2、3、10、18 落地） |
| M-05 | 阶段 F：正式可用 | 🔴 未启动 |
| 二期 | 阶段 E：结果研究/跟踪/调优 | ✅ 达成（2026-10-07 批次四交付；发布门禁 12、14、15、16、17、19 落地） |

---

## 二、口径说明（"智能选股"在本仓库含两个层次）

| 层次 | 定义 | 现状 |
|---|---|---|
| **① 智能选股系统 ISS** | `SPEC-ALGO-ISS-001` 定义的配置化选股平台 | **主体未落地，仅底座可用**（本文审查对象） |
| **② 既有独立选股能力** | 5A 五维共振旋转选股（`astock screen`）+ 三层漏斗 `StockScreener` | 已实现并有测试，与 ① **并行**、不复用入口 |

本审查针对 ①；② 仅作边界说明，不在整改范围。

---

## 三、分层落地矩阵

| 层 | 规划内容 | 落地情况 | 证据 |
|---|---|---|---|
| **核心引擎** | HFE、规则注册、三态求值、AND/OR/NOT AST | ✅ 具备（批次一）：三态 `RuleResult`、Kleene 强三值、`RuleRegistry`、`StageResult`；嵌套表达式树与 `NOT` 已落地（深度≤3 / 叶子≤200 校验，`all/any` 保留为快捷写法） | `scripts/core/strategy/funnel_engine.py` |
| **规则库** | 全量参数化、分钟拐点、三态改造 | ✅ 具备：21 类规则；分钟时间戳归一化校验、`earliest_possible_hit_time` 编译期推导、信号定性、窗口全参数化；**参数 Schema 元数据已就位（批次一 A7）** | `scripts/core/strategy/stock_funnel.py`、`scripts/core/selection_models/rule_registry.py` |
| **配置/版本** | v2 Schema、迁移器、`definition_hash`/`plan_hash`、版本仓库 | ✅ 具备（批次一）：v2 Schema + v1→v2 内存迁移器（幂等、加载告警）；规范化 JSON SHA-256 双哈希；版本仓库（单调发布号、内容不可变、草稿 `base_version/draft_revision` 冲突检测、悲观文件锁、激活/回滚/归档） | `scripts/core/selection_models/schemas.py`、`hash.py`、`definition_repository.py`、`version_repository.py` |
| **模型类型/构建器** | 类型注册中心、编译器、构建器、文案草稿解析 | ✅ 具备（批次一 + 批次三）：类型注册中心、`CompiledSelectionPlan` 编译器（批次一）；**用户模型构建器与文案草稿解析已落地**（`catalog.create_model`/`draft_from_text` + Web 向导，批次三） | `scripts/core/selection_models/model_type_registry.py`、`model_compiler.py`、`catalog.py` |
| **数据装配** | `finalized_local`/`intraday_capture`、水位门禁、快照清单 | 🟡 部分具备：`DataAssembler`、分钟归一化、`TradeCalendar` 已接 | `scripts/core/data/data_assembler.py` |
| **调度** | Scheduler Tick/daemon、运行锁、幂等、Signal Latch、跨日恢复 | ✅ 具备（批次二）：`SelectionScheduler` tick/daemon 真实读取 4 处 `schedule`、`TradeCalendar` 门控、运行锁、分层幂等键、Signal Latch、按交易日状态恢复，`schedule` 已由真实执行器读取（发布门禁 1 满足） | `scripts/core/selection_models/scheduler.py`、`run_lock.py`、`signal_latch.py`、`run_repository.py` |
| **CLI** | `funnel screen/regime/trigger/daemon` + 完整 `screen-model` 族 | 🟡 部分具备（批次二扩充）：`funnel validate/run/tick/daemon` 已接线；`funnel screen/regime/trigger` 与 `screen-model` 族待后续批次 | `scripts/core/cli.py` |
| **后端 API** | `/api/selection-models/*` 全套 + 权限码/角色 | ✅ 具备（批次三 + 批次四）：`selection_models.py` 落地 §15 全套端点（类型/规则/模型/草稿/版本/调试/运行/SSE/调度/结果/数据健康 + 阶段 E：评估/跟踪计划/观察/评价/调优建议）+ 统一水印包裹；10 项权限码与 `model_author`/`researcher` 角色落地 | `scripts/server/api/selection_models.py`、`auth/dependencies.py`、`server/db.py` |
| **前端工作台** | 模型中心、条件树/漏斗编辑器、版本管理、调试、运行时间线 | ✅ 具备（批次三）：`web/js/selection-models/` 18 个模块，四态真实、无 Mock 回退；`#pane-selection` 真实接口驱动 | `web/js/selection-models/*`、`web/index.html` |
| **结果研究/跟踪/调优** | Assessment/Tracking/Evaluation/Suggestion | ✅ 具备（批次四）：`ResultAssessment`/`TrackingPlan`/`TrackingObservation`/`ModelEvaluation`/`OptimizationSuggestion` 全链路落地，回测/跟踪/评价/建议可追溯至 `run_id` 与观察样本 | `scripts/core/selection_models/result_assessment.py`、`tracking_service.py`、`model_evaluator.py`、`optimization_advisor.py` |
| **技能登记** | 登记 `astock-selection-model`（G-01） | 🟡 未落地：技能清单仍 18 项，无 funnel 条目 | `config/skills_manifest.json` |

---

## 四、逐里程碑差距拆解

### M-02 · 配置与核心引擎（✅ 达成 · 2026-10-07 批次一交付）

| 验收项 | 状态 | 缺口（交付前） | 交付物 |
|---|:--:|---|---|
| 类型注册与发现 | ✅ | 无 `SelectionModelTypeRegistry`；首期 4 类型（`condition_tree`/`funnel` P0，`scoring_rank`/`composite` P2）零实现 | `selection_models/model_type_registry.py`（4 类型登记，P2 `publishable=False`） |
| `condition_tree` | ✅ | 维度组 + 布尔表达式树完全缺失 | `model_compiler._compile_condition_tree_stages`（维度组展开为层内表达式，循环引用检测）+ `funnel_engine` AST |
| 嵌套 AND/OR/NOT | ✅ | `logic` 仍只接受 `all/any`，无 group 节点、无 `NOT`、无深度(≤3)/叶子(≤200) 校验（T-01/S-04/S-05） | 就地升级 `funnel_engine`（`kleene_not` + `normalize/validate/evaluate_expression`） |
| 统一层级中间结构 | ✅ | 无 `CompiledSelectionPlan`、无 `plan_hash` 规范化复算 | `model_compiler.py` |
| v2 Schema + 迁移 | ✅ | 仍 `version: 1`；无 v1→v2 迁移器（S-01/T-06） | `schemas.py`（`migrate_to_v2` 幂等 + 加载告警，原文件不改写） |
| 版本仓库/草稿/发布/激活 | ✅ | 无 `definition_hash`、不可变版本、`base_version/draft_revision` 冲突检测、悲观文件锁（S-02/S-03/T-07） | `definition_repository.py`、`version_repository.py`、`file_lock.py` |
| 参数 Schema 齐备 | ✅ | 规则有默认值但无 JSON Schema 2020-12 元数据（S-06） | `rule_registry.py`（11 类规则参数 Schema + `x-*` UI 注解 + 校验） |
| `run-all` 按依赖执行 | ✅ | 仅单阶段 `funnel run --stage`；无编排器 | `orchestrator.py`（依赖图 + `order` 拓扑执行；`BLOCKED`/`EMPTY`/`WAITING_DATA` 收敛） |

> **M-02 已交付**：引擎类验收项全绿，发布门禁 8（配置错误在激活前被阻止：编译器对未知节点/规则/层级失败关闭）、门禁 9（已发布版本不可变 + 激活只切指针）落地。**一处保留**：运行实例的版本绑定属批次 C 的持久化职责，本轮以 `CompiledSelectionPlan` 冻结 `source_model.model_version` / `plan_hash` 作为契约实现。

### M-03 · 数据与调度（🟡 批次二交付 · 调度侧全绿、覆盖率硬门禁落地）

| 验收项 | 现状 | 缺口 |
|---|---|---|
| 双模式装配 | ✅ 已有 `assemble_daily`/`assemble_intraday`/`evaluate_data_gate`/`content_hash`/`resolve_universe` | 补齐 `UniverseWatermark` 分层分母（A-05/R-03） |
| `data_snapshot_id`/切片/哈希 | 🟡 部分 | 检查输入切片留存与 90 天淘汰（D-18） |
| **Scheduler Tick/daemon** | 🔴 零 | 无 `funnel daemon`/`tick`；`schedule` 声明后无执行器读取 → **发布门禁 1 未达**（O-01） |
| 运行锁/幂等/Signal Latch | 🔴 零 | 跨平台文件锁（粒度 `model_id+trade_date`）、分层幂等键、`converge_at_window_end` 收敛锁存（O-02/O-03） |
| 跨交易日状态恢复 | 🔴 零 | 落盘快照按交易日重建（O-04） |
| 交易日历门控 | 🟡 部分 | `TradeCalendar` 已有；需接入调度 |

> **关键路径阻塞**：D-11（证券主数据 + 分钟线 + 资金流持久化）未就绪时，D-12 的 **100% 覆盖率门槛将长期不达标**，会阻断全部正式信号。

> **批次二已交付**：Scheduler Tick/daemon（B1）、运行锁与分层幂等键（B2）、Signal Latch（B3）、按交易日状态恢复（B4）、`UniverseWatermark` 分层分母 + 覆盖率硬门禁（B5 逻辑）、§13.10 落盘规范与淘汰（B6）、W-09/W-10 修复（B7）均落盘并测试通过。**唯一保留**：D-11 增量同步未就绪 → 覆盖率 100% 的实际达标（发布门禁 13 的数据侧前提）仍不成立，故 M-03 判为**部分达标**。

### M-04 · API + Web（✅ 达成 · 2026-10-07 批次三交付）

| 层面 | 现状 | 交付物 |
|---|---|---|
| 后端 API | ✅ §15 非二期端点全部落地（类型/规则/模型/草稿/版本/差异/发布/激活/归档/校验/调试/运行/节点/候选/SSE/取消/调度/结果/数据健康）+ 统一水印包裹 | `scripts/server/api/selection_models.py`、`app.py`（router 注册） |
| 权限 | ✅ 10 项权限码（view/create/edit/publish/activate/run/track/evaluate/admin/debug）以「menu + action 两段式」映射为 `selection.<action>` 菜单；新增内置角色 `model_author`（不含 publish/activate/admin/debug）；`:debug` 仅 super_admin | `auth/dependencies.py`、`server/db.py`、`api/roles.py`（设计说明） |
| Web 工作台 | ✅ `web/js/selection-models/` 18 个模块（模型中心/向导/文案解析/规则库/属性抽屉/条件与漏斗编辑器/版本管理/调试/运行时间线/候选轨迹/调度/数据诊断/总览/状态基元）；`#pane-selection` 真实接口驱动、四态真实、无 Mock 回退 | `web/js/selection-models/*`、`web/index.html`、`web/css/style.css` |
| 持久化 | ✅ 逐阶段明细 `<run_id>/stages.json`、候选轨迹 `<run_id>/candidates.json`、正式信号 `pools/<date>/<model>.signals.json`、运行元数据过滤分页 | `run_repository.py`、`paths.py` |

> **明确边界**：§15.3 的阶段 E 端点（`assessments`/`tracking-plans`/`evaluations`/`tuning-suggestions`）在本批次**未注册**（按裁定归批次四）；**已于 2026-10-07 批次四补齐落地**（见 §七 批次四 与「二期 · 阶段 E」）。

### 二期 · 阶段 E（✅ 达成 · 2026-10-07 批次四交付）

| 层面 | 现状 | 交付物 |
|---|---|---|
| 结果研究评估 | ✅ `ResultAssessment`：个股信息快照 + 入选证据（命中层级/通过规则/观测值/同批排名）+ 风险画像 + 相对表现 + 建仓持股策略，绑定 `assessment_as_of`/`data_snapshot_id`，强制 `research_only` 与"非未来收益保证"口径 | `result_assessment.py`、`position_policy.py`、`market_view.py` |
| 回测分析 | ✅ 信号标记分析（Markout）与事件驱动策略回测**口径严格分离**；T+1/100 股整手/涨跌停不可成交/停牌、参数化佣金·印花税·过户费·滑点、未来数据检测；输出 CAGR/MaxDD/Sharpe/Calmar/胜率/盈亏比/换手率/平均持有期/MFE/MAE | `backtest_service.py` |
| 持续跟踪 | ✅ `TrackingPlan`（模式/周期/频率/基准价/基准/到期点/状态机）+ 只追加 `TrackingObservation`；独立 Tracker Tick 按交易日历执行到期观察、重复 Tick 幂等、水位未就绪不写伪观察、观察绑定 `run_id`/`signal_id` | `tracking_service.py`、`tracker_scheduler.py` |
| 模型评价 | ✅ `ModelEvaluation`：T+N 汇总、分层流失、规则通过/未通过分组（轨迹不完整即如实标注不可用）、市场门控分组、版本对比；D-16 阈值（样本≥30、周期≥20 交易日、基准沪深300）不足即 `EVALUATION_SAMPLE_INSUFFICIENT`；选股模型评价与 PositionPolicy 评价分列 | `model_evaluator.py` |
| 简单调优 | ✅ 只读 `OptimizationSuggestion`：证据可追溯 `run_id`、状态机 `pending→accepted/ignored`、活动版本变化即 `STALE`、`auto_apply=False`、无自动改版路径 | `optimization_advisor.py` |
| API 与权限 | ✅ §15.3 阶段 E 端点注册；`track`/`evaluate` 与 `activate` 权限相互独立（`researcher` 仅 view+track） | `scripts/server/api/selection_models.py` |

> **明确边界**：`screen-model` 族 CLI（§14 `assess`/`track`/`evaluate`/`tune`）与 Web「结果研究/持续跟踪/模型评估」页签（§16 8～10）未在本批次内接线；Tracker Tick 无独立 API 端点（由核心 `TrackerScheduler.tick` 与后续调度接线承载）。

---

## 五、已具备的可运行底座（真实可用，非演示）

- `astock funnel validate`：校验四阶段配置，输出阶段 ID、规则类型、`earliest_possible_hit_time`、`stage_schedules`、声明态 `ranking`/`risk_exit` 块。
- `astock funnel run --stage <id> [--assemble|--input]`：单阶段执行，含 §11.4 收盘水位门禁、盘中捕获装配、快照清单、`calendar_version` 元数据、失败关闭（数据不足不产出代码）。
- 三态判定链路完整：`passed` 仅为 `verdict==PASS` 的兼容投影，UNKNOWN 独立留痕，代理口径强制 `not_eligible_for_signal`。

---

## 六、关键阻断项与技术债

### 6.1 长期技术债（看板 §六 偏离项，须显式跟踪）

| 编号 | 内容 | 风险与配套要求 |
|---|---|---|
| **D-23** | 止损口径不统一（`config.py` -3/-5、`risk_position_manager` -6、`AGENTS.md` -3/-5/-8 三套并存） | 新增模块须在规则元数据声明引用口径；registry 加"口径来源"字段 + 门禁扫描（T-05） |
| **S-03** | 采用悲观锁 | 必须配套"超时释放 + 显式解锁 + 持有者可见"，否则浏览器异常关闭即死锁 |
| **D-11** | 主数据/分钟线/资金流三类持久化 | 工期与存储成本上升；与覆盖率 100% 强耦合 |

### 6.2 高危缺陷（启用前必修）

| 编号 | 内容 | 约束 |
|---|---|---|
| **W-09** | 市值单位"亿元→元"须在入库层单点换算，禁止二次换算/透传 | 修复前不得启用流通市值阈值 |
| **W-10** | 市值字段 `0 ≠ 缺失`，任一缺失置 `None` 并计入 `blocking_fields`，不得回退取另一口径 | 同上 |

---

## 七、实施计划

### 7.1 计划原则

1. **依赖门控、不做日期排程**：每批次以"依赖就绪 + 门禁通过"为唯一触发条件（延续看板 §七）。
2. **复用底座、不建平行运行时**：所有模型最终编译为统一层级计划，由 `funnel_engine` 单内核执行（SSOT §19 复用矩阵）。
3. **不伪造、不预发布**：未实现节点一律 fail-closed，禁止在 Web/API 显示为"可运行"。
4. **门禁双扣**：每批次同时对齐"§23 验收标准"与"§五 发布门禁"。

### 7.2 批次划分与任务清单

#### 批次一 · 核心引擎（目标 M-02，可立即启动）· ✅ 已完成（2026-10-07）

| 序号 | 任务 | 交付物 | 依赖 | 验收 | 完成 |
|:--:|---|---|---|---|:--:|
| A1 | v2 Schema 定义 + v1→v2 内存迁移器（幂等、加载告警） | `selection_models/schemas.py` | 无 | 存量 `funnel_strategy.yaml` 自动升级且行为不变 | ✅ |
| A2 | `definition_hash`/`plan_hash` 规范化 JSON + SHA-256 复算 | `selection_models/hash.py` | A1 | 键序/空白/数值写法无关，`calendar_version` 不入哈希 | ✅ |
| A3 | 嵌套 AND/OR/NOT AST 就地升级 `funnel_engine`（`all/any` 为快捷写法） | `funnel_engine.py` | 无 | Kleene 真值表全组合通过；深度≤3/叶子≤200 校验 | ✅ |
| A4 | `CompiledSelectionPlan` 编译器（condition_tree/funnel → 统一层级） | `model_compiler.py` | A2/A3 | 同版本同编译器 → 同 `plan_hash`；未知节点发布期失败 | ✅ |
| A5 | 类型注册中心（首期登记 4 类型，P2 类型不可发布） | `model_type_registry.py` | A4 | 类型发现/未知类型拒绝；P2 节点被编译器拒绝 | ✅ |
| A6 | 版本仓库 + 草稿 + 悲观文件锁 + 发布/激活/回滚 | `definition_repository.py`、`version_repository.py`、`file_lock.py` | A2 | 发布号单调、内容不可变、草稿冲突被拒、激活只切指针 | ✅ |
| A7 | 规则参数 Schema 元数据（JSON Schema 2020-12 子集 + UI 注解） | `rule_registry.py` | 无 | 表单可由 Schema 动态生成 | ✅ |
| A8 | 编排器 `run-all`（按 stage 依赖执行整链） | `orchestrator.py` | A4/A6 | 四层漏斗一键按依赖执行 | ✅ |

> **出口**：M-02 全绿（引擎类验收项）+ 发布门禁 8、9 —— **已达成**（交付物与验证见 §十一）。

#### 批次二 · 数据与调度（目标 M-03）

| 序号 | 任务 | 交付物 | 依赖 | 验收 | 完成 |
|:--:|---|---|---|---|:--:|
| B1 | 内置 Tick 常驻 `funnel daemon` + `TradeCalendar` 门控 | `selection_models/scheduler.py`、`funnel_cmds` | A6 | 真实读取 YAML 4 处 `schedule` 窗口；优雅退出 | ✅ |
| B2 | 运行锁（`model_id+trade_date`，运行期持有）+ 分层幂等键 | `run_lock.py`（与 T-07 同族） | B1 | 同分钟重复 Tick 不重复执行；多进程互斥 | ✅ |
| B3 | Signal Latch（`converge_at_window_end` 收敛锁存） | `signal_latch.py` | B2 | 窗口内仅待定；窗口末唯一终态 | ✅ |
| B4 | 跨交易日状态恢复（落盘快照 + 按交易日重建） | `run_repository.py` | B1 | 重启后当日状态可恢复 | ✅ |
| B5 | `UniverseWatermark` 分层分母 + 覆盖率门禁（R-03/A-05） | `data_assembler.py` 扩展 | D-11 | 硬门禁 100%，不达标整场降级 | ✅（逻辑；实际达标待 D-11） |
| B6 | 落盘目录规范（运行元数据/切片/候选/信号） | `paths.py` + 按 SSOT §13.10 | B1/B4 | 三桶规范；90 天淘汰/信号切片保留 | ✅ |
| B7 | 修复 W-09/W-10（市值单位 + 缺失置零） | 同步入库层 | — | 单位一致可校验；缺失不入比较 | ✅ |

> **出口**：M-03 全绿 + 发布门禁 1、4、5、6、7、11、13。**B5 强依赖 D-11 数据契约**——该数据侧前提未就绪，M-03 本轮判为**部分达标**（调度侧与门禁 1/4/5/6/7/11 已满足，门禁 13 与覆盖率 100% 实际达标待 D-11 增量同步）。

#### 批次三 · API 与 Web（目标 M-04）· ✅ 已完成（2026-10-07）

| 序号 | 任务 | 交付物 | 依赖 | 验收 | 完成 |
|:--:|---|---|---|---|:--:|
| C1 | Selection Model API（§15 全套）+ 统一水印包裹 | `scripts/server/api/selection_models.py` | A6/B1 | 契约与错误码齐备；越权拒绝 | ✅ |
| C2 | 权限码 10 项 + `model_author` 角色（复用 `role_menus` 两段式） | `api/roles.py` 扩展 + `auth/dependencies.py` + `server/db.py` | C1 | 矩阵对齐 W-02/C-03；`:debug` 仅 `super_admin` | ✅ |
| C3 | SSE 运行事件流（复用既有 SSE 基础设施） | `api/selection_models.py` | C1 | 事件含 `run_id` 与水印 | ✅ |
| C4 | 运行/阶段/候选/信号持久化存储 | `run_repository.py`、`paths.py`、`catalog.py` | B4 | 多模型多次运行互不覆盖 | ✅ |
| C5 | Web 工作台 18 模块（模型中心/向导/编辑器/调试/运行时间线） | `web/js/selection-models/*` | C1 | 四态真实（loading/empty/error/success）；无 Mock 回退 | ✅ |

> **出口**：M-04 全绿 + 发布门禁 2、3、10、18 —— **已达成**（交付物与验证见 §十三）。§15.3 阶段 E 端点按裁定归批次四。

#### 批次四 · 二期（阶段 E）· ✅ 已完成（2026-10-07）

| 序号 | 任务 | 交付物 | 依赖 | 完成 |
|:--:|---|---|---|:--:|
| E1 | 结果个股信息快照 + 入选证据聚合 | `result_assessment.py` | C4 | ✅ |
| E2 | 信号标记分析 + 事件驱动回测 + `PositionPolicy`（复用量化引擎） | `backtest_service.py`、`position_policy.py` | C4 | ✅ |
| E3 | 实时/T+N TrackingPlan + Tracker Tick + 观察存储 | `tracking_service.py`、`tracker_scheduler.py` | C4 | ✅ |
| E4 | 模型评价（T+N 汇总、分层流失、通过/未通过组对比） | `model_evaluator.py` | E3 | ✅ |
| E5 | 简单优化建议（只读、可追溯 `run_id`、不自动改版） | `optimization_advisor.py` | E4 | ✅ |

> **出口**：发布门禁 12、14、15、16、17、19 —— **已达成**（交付物与验证见 §十四）。

### 7.3 关键依赖与并行关系

```
批次一(A) ──► 批次二(B1..B4,B6) ──► 批次三(C) ──► 批次四(E)
                    ▲
        D-11 数据契约(B5) ── (与开发并行推进，为 M-03 关键路径)
```

- 批次一**不依赖外部数据契约**，可立即启动。
- B5（覆盖率 100%）与 D-11 数据持久化强耦合：**D-11 未就绪则 M-03 不得通过**。
- 批次三前端（C5）依赖后端 API（C1）就绪，否则维持 fail-closed。

---

## 八、测试与门禁现状

- **P0 核心门禁**：批次四交付后实测 **213 passed / 0 failed**（`python -m pytest -m core`；批次一 179 → 批次二 197 → 批次三 197 → 批次四 +16）。
- **批次三新增用例**：`tests/server/test_selection_models_api.py`（**17 例**，登记为 `p1` 档），覆盖类型/规则元数据、匿名 401、P2 类型拒绝、创建→校验→发布→激活→无编码运行、未激活版本失败关闭、数据不足失败关闭、版本不可变/单调/草稿冲突/激活回滚/归档、版本差异、多运行互不覆盖、`request_id` 幂等、调试与正式运行隔离、取消终态冲突、SSE 事件流、调度暂停恢复与非法窗口、数据健康不伪造覆盖率、文案草稿解析、`model_author` 权限边界（无 publish/debug）。实测 **17 passed / 0 failed**。
- **批次四新增用例**：`tests/core/test_selection_stage_e.py`（**16 例**，`core` 档）覆盖 Bar 归一失败关闭、涨跌停/板块、T+N 跨周末交易日历、未来数据检测、`PositionPolicy` 缺输入不伪造精度与整手/保本价进位、Markout 与策略回测口径分离、T+1 不当日卖出、涨停建仓不可成交、摩擦成本计入、结果评估 `research_only`/可追溯、跟踪只追加与重复 Tick 幂等、水位未就绪不写伪观察、评价样本不足不出强结论、单版本样本隔离、建议只读/`auto_apply=False`/活动版本变化即 `STALE`、越权状态被拒；`tests/server/test_selection_stage_e_api.py`（**4 例**，`p1` 档）覆盖评估/跟踪/观察/评价/建议接口、缺数据失败关闭、非法标识符不产生越权路径、`track`/`evaluate`/`activate` 权限相互独立。实测 **16 passed** + **4 passed / 0 failed**。
- **治理子集**：`test_production_authenticity / test_decoupling_suite / test_quality_gates / test_skill_contracts` 实测 **31 passed**（`#pane-selection` 由 fail-closed 空壳升级后仍满足全部结构断言：静态层无数字、按钮均接真实处理函数、无 canvas、无 Mock 回退）。前端 **29 个 Node 脚本**静态断言全通过（无 FAIL）。
- `tests/core/test_stock_funnel.py`：**37 用例**，覆盖 Kleene 真值表、分钟时间戳五形态归一化、进行中 Bar 排除、`earliest_possible_hit_time` 推导、信号定性、窗口参数化、失败关闭、declared block 标记校验——**底座测试质量高**。
- `tests/core/test_selection_models.py`：**28 用例**（批次一新增，登记为 `core` 档位），覆盖 v2 迁移与幂等、规范化哈希与 `plan_hash` 复算/口径版本联动、嵌套 AST 全组合与深度/叶子上限、类型注册与 P2 拒绝、条件树展开与循环引用、草稿冲突与悲观锁、发布单调与不可变/激活/回滚/归档、四层 `run-all` 与门控阻断。
- **缺口**：§22.4 前端测试（结果研究/跟踪/评估页签）与 `screen-model` 族 CLI 对应用例尚未落地；§22.2 Tracker Tick 用例**已落地**（批次四核心 2 例：到期执行/重复幂等/水位等待）；§22.3 API 集成测试**已覆盖阶段 E**（批次三 17 例 + 批次四 4 例）。
- **治理已纠偏**：2026-10-07 已删除工作台整屏假数据，改 fail-closed，并新增 `tests/governance/test_production_authenticity.py` 结构断言防回流。

---

## 九、风险与开放项

| 类型 | 编号 | 内容 | 处置建议 |
|---|---|---|---|
| 技术债 | D-23 | 止损口径不统一 | registry 登记口径来源 + 门禁扫描 |
| 技术债 | S-03 | 悲观锁 | 配套超时释放/显式解锁/持有者可见 |
| 技术债 | D-11 | 三类数据持久化 | 与 B5 覆盖率门禁联动排期 |
| 高危 | W-09/W-10 | 市值单位与缺失置零 | 修复前不得启用流通市值阈值 |
| 治理 | G-01 | 技能清单未登记 `astock-selection-model` | **触发条件已到**（批次一/三已完成）：待同步三处清单（`AGENTS.md` / `config/skills_manifest.json` / `.agents/manifests/skills_manifest.json`，18→19） |
| 契约 | (i) | Web 模型构建器无实现载体 | **已解除**：批次三 C5 已交付 `web/js/selection-models/*`（向导/编辑器/调试/时间线），`#pane-selection` 由 fail-closed 空壳升级为真实接口驱动 |

---

## 十、附：审查证据清单

| 类别 | 路径 | 用途 |
|---|---|---|
| 规范 | `docs/guidelines/algorithm/selection-system-specification.md` | SSOT 主规范 |
| 规范 | `docs/guidelines/algorithm/selection-model-types-specification.md` | 模型类型契约 |
| 看板 | `docs/specs/algorithm/selection-system-plan.md` | 裁定 + 里程碑 + 门禁 |
| 看板 | `docs/specs/algorithm/pending-backlog-plan.md` | 未完成项登记 |
| 引擎 | `scripts/core/strategy/funnel_engine.py` | 三态/注册/AST 现状 |
| 规则 | `scripts/core/strategy/stock_funnel.py` | 21 规则/分钟拐点/信号定性 |
| 装配 | `scripts/core/data/data_assembler.py` | 双模式装配/水位门禁 |
| CLI | `scripts/core/cli.py`、`scripts/core/commands/funnel_cmds.py` | 现有入口 |
| 配置 | `config/funnel_strategy.yaml` | v1 配置与 declared blocks |
| 测试 | `tests/core/test_stock_funnel.py` | 底座 37 用例 |
| 前端 | `web/index.html`（`#pane-selection`） | fail-closed 空壳 |

---

## 十一、批次一交付物与验证证据（2026-10-07）

### 11.1 新增/修改文件

| 类型 | 路径 | 说明 |
|---|---|---|
| 新增包 | `scripts/core/selection_models/__init__.py` | ISS 核心引擎包入口（§19 规划目录落地起点） |
| 新增 | `scripts/core/selection_models/schemas.py` | A1：v2 Schema、`migrate_to_v2`（幂等 + 告警）、`normalize_definition` |
| 新增 | `scripts/core/selection_models/hash.py` | A2：`canonical_json`（键序/空白/数值字面量归一）、`definition_hash`/`plan_hash` |
| 新增 | `scripts/core/selection_models/rule_registry.py` | A7：11 类规则参数 Schema + `x-*` UI 注解 + 参数校验 |
| 新增 | `scripts/core/selection_models/model_type_registry.py` | A5：4 类型登记（P0 可发布 / P2 不可发布） |
| 新增 | `scripts/core/selection_models/model_compiler.py` | A4：`CompiledSelectionPlan` / `CompiledStage` 编译器 |
| 新增 | `scripts/core/selection_models/file_lock.py` | A6：跨平台悲观文件锁（`fcntl`/`msvcrt` + 持有者可见） |
| 新增 | `scripts/core/selection_models/definition_repository.py` | A6：草稿读写 + `base_version/draft_revision` 冲突检测 + 编辑锁 |
| 新增 | `scripts/core/selection_models/version_repository.py` | A6：单调发布、不可变版本、激活/回滚/归档、`active.json` 指针 |
| 新增 | `scripts/core/selection_models/orchestrator.py` | A8：`run-all` 依赖图拓扑执行 + 状态收敛 + 内容派生 `run_id` |
| 修改 | `scripts/core/strategy/funnel_engine.py` | A3：受限 AST（`kleene_not` / `normalize|validate|evaluate_expression`）；`all/any` 向后兼容 |
| 新增测试 | `tests/core/test_selection_models.py` | 28 例核心契约测试 |
| 修改测试 | `tests/conftest.py` | 将新用例登记为 `core` 档位 |

### 11.2 验收与门禁实测

| 项 | 结果 |
|---|---|
| P0 核心门禁 `pytest -m core` | **179 passed / 0 failed**（13.7s） |
| 追加 governance 子集（authenticity / decoupling / quality_gates / skill_contracts） | **31 passed** |
| 存量 `config/funnel_strategy.yaml`（`version: 1`） | 加载期自动迁移为 v2 且**行为不变**（规则/`all/any` 语义原样），编译成功 |
| 四层漏斗 `run-all` | 一次跑通 → `COMPLETED`、`selected_codes=['600001']`；大盘门控失败 → `BLOCKED` 且不产出代码 |
| 发布门禁 8 | 未知节点类型/未知规则/不可执行层级/参数非法 → 编译器**发布期失败关闭** |
| 发布门禁 9 | 发布号单调（1→2→3）、已发布内容不可覆盖、激活只切指针（`pointer_revision` +1） |

### 11.3 明确边界（未越界声明）

- 未接线 CLI 子命令（`funnel`/`screen-model` 族）、未实现 Scheduler Tick/daemon、无 API 与 Web（属批次二/三）。
- `StockFunnelPipeline` 读取路径保持不变；迁移仅在 `schemas.load_definition` 加载期内存完成（原文件不改写）。
- `orchestrator` 为域无关执行内核，需盘中字段的层级要求种子记录已携带相应字段；**数据装配仍属批次 B**，本轮不伪造任何行情/候选。
- 运行实例的落盘持久化与版本绑定属批次 C；本轮以 `CompiledSelectionPlan` 冻结 `source_model.model_version` / `plan_hash` 提供契约。

## 十二、批次二交付物与验证证据（2026-10-07）

### 12.1 新增/修改文件

| 类型 | 路径 | 说明 |
|---|---|---|
| 新增 | `scripts/core/selection_models/paths.py` | B6：§13.10 落盘目录唯一派生点（output/config·cache·pools·reports·backtest、log、temp）+ 目录穿越白名单 |
| 新增 | `scripts/core/selection_models/run_lock.py` | B2：运行锁，粒度 `model_id+trade_date`，运行期持有、超时释放、持有者可见 |
| 新增 | `scripts/core/selection_models/run_repository.py` | B4/B6：当日可恢复状态（按交易日重建、跨日过期）、运行元数据、候选/信号落盘、90 天淘汰（信号切片受保护） |
| 新增 | `scripts/core/selection_models/signal_latch.py` | B3：`converge_at_window_end` 锁存（窗口内 pending、窗口末唯一终态、追加 `latched_by_run_id`） |
| 新增 | `scripts/core/selection_models/scheduler.py` | B1：`SelectionScheduler` tick/daemon，真实读取 4 处 `schedule`、`TradeCalendar` 门控、分层幂等、运行锁、Signal Latch 集成、优雅退出 |
| 修改 | `scripts/core/data/data_assembler.py` | B5：`build_universe_watermark` / `layer_denominator`（R-03/A-05）与清单 `candidate_pool_watermark`、`coverage_gate`；默认快照根对齐 §13.10 |
| 修改 | `scripts/core/data/data_bridge.py` | B7：`tencent_quote` 市值缺失由 `0` 改为 `None`（W-10 单点修复，单位仍为亿元 W-09） |
| 修改 | `scripts/core/commands/data_cmds.py` | B7：市值展示对 `None` 安全（`or 0`），不因缺失崩溃 |
| 修改 | `scripts/core/commands/funnel_cmds.py` | B1：接线 `funnel tick` / `funnel daemon`，daemon 心跳沉淀 `log/selection-models/<date>/scheduler.log` |
| 修改 | `scripts/core/cli.py` | B1：新增 `funnel tick` / `funnel daemon` 子命令与参数 |
| 新增测试 | `tests/core/test_selection_data_and_scheduling.py` | 16 例（B1～B7 契约）；登记为 `core` 档位 |
| 修改测试 | `tests/core/test_data_assembler.py` | +2 例：清单候选池水位与覆盖率门禁 |
| 修改测试 | `tests/conftest.py` | 新用例登记 `core` 档位 |

### 12.2 验收与门禁实测

| 项 | 结果 |
|---|---|
| P0 核心门禁 `pytest -m core` | **197 passed / 0 failed**（批次一后为 179；+16 新增 +2 扩充） |
| 发布门禁 1（`schedule` 被真实调度器读取） | `SelectionScheduler` 真实解析 YAML 4 处窗口，`funnel tick` 实测输出 `due_stages`/`heartbeat`/`next_run_at` |
| 发布门禁 4（节假日不运行早盘策略） | 周末 `2026-09-19`、节假日 `2026-10-07` → `SKIPPED_NON_TRADING_DAY`，`executed=[]` |
| 发布门禁 5（数据不足不生成代码） | `records_provider=None` → 阶段 `WAITING_DATA`、`selected_codes=[]`，且不占用幂等键可重试 |
| 发布门禁 6（重启后当日状态恢复） | 状态落 `<signal_date>/<model>.state.json`，同日可恢复；跨日 `expired_snapshot_from` 标记且不恢复 |
| 发布门禁 7（重复 Tick 不重复信号） | 同分钟二次 Tick → `IDEMPOTENT_SKIP`；下一分钟为新键可执行 |
| 发布门禁 11（路径符合工作区规范） | `paths.py` 三桶派生：output（config/cache/pools/reports/backtest）、log、temp；锁落 `temp/selection-models/locks` |
| B3 收敛锁存 | 窗口内仅 `pending`；`09:40` 收敛为唯一 `latched`；收敛后二次命中追加 `latched_by_run_id` 且终态不变 |
| B5 覆盖率硬门禁 | 主口径=有值标的数÷候选池标的数；不达标 `coverage_gate.passed=False, degraded=True`；mv 加权仅参考观测 |
| B7 W-09/W-10 | `tencent_quote` 市值缺失→`None`（不置 0）；有值时保持腾讯原始单位（亿元）不在本层换算 |
| CLI 冒烟 | `funnel tick`/`daemon --once` 输出结构完整；`funnel validate`/`run` 逐字节未回归 |

### 12.3 明确边界（未越界声明）

- **M-03 判为部分达标**：调度侧与发布门禁 1、4、5、6、7、11 已满足；**门禁 13 与 D-12 覆盖率 100% 的实际达标**依赖 D-11（证券主数据/分钟线/资金流增量同步）就绪，本轮只交付门禁**逻辑**，未伪造数据达标。
- 未接线 `funnel screen --mode` / `funnel regime` / `funnel trigger` 与 `screen-model` 族（属批次三）；未实现 API 与 Web 工作台。
- 调度 Tick 默认不自行采集行情：`records_provider` 由 `DataAssembler` 注入，缺数据一律失败关闭，不产出候选。

---

## 十三、批次三交付物与验证证据（2026-10-07）

### 13.1 新增/修改文件

| 类型 | 路径 | 说明 |
|---|---|---|
| 新增 | `scripts/core/selection_models/catalog.py` | C4/C5：模型目录（列表/详情）、空白与模板创建草稿、文案草稿**确定性**解析（未识别片段登记为 `ambiguities`）、调度定义存储 `ScheduleStore` |
| 修改 | `scripts/core/selection_models/paths.py` | C4：新增 `RUN_STAGES_FILE`/`RUN_CANDIDATES_FILE` 与 `run_stages_path`/`run_candidates_path` 派生点 |
| 修改 | `scripts/core/selection_models/run_repository.py` | C4：逐阶段明细、候选轨迹、正式信号落盘与 `query_signals`、`update_run`、按版本/状态/触发方式过滤分页；`signal_dates` 纳入信号文件 |
| 新增 | `scripts/server/api/selection_models.py` | C1/C3：§15 非二期端点全部落地 + `{status,data,error_code?,watermark}` 统一水印包裹 + SSE 事件流 |
| 修改 | `scripts/server/api/__init__.py`、`scripts/server/app.py` | C1：注册 `selection_models_router` |
| 修改 | `scripts/server/auth/dependencies.py` | C2：`SELECTION_PERMISSION_MENU`（10 项）与 `require_selection` 依赖（`:debug` 仅 super_admin） |
| 修改 | `scripts/server/db.py` | C2：种子新增父菜单 `selection` + 10 个动作菜单 + 内置角色 `model_author`（并幂等补齐超管/作者/投研用户绑定） |
| 修改 | `scripts/server/api/roles.py` | C2：回写「menu + action 两段式」权限落地设计说明（C-04） |
| 新增 | `web/js/selection-models/*.js`（18 个模块） | C5：api_client / store / state_views / model_center / overview / wizard / text_draft / rule_library / property_drawer / condition_editor / funnel_editor / version_manager / debug_panel / scheduler / data_health / candidate_trace / run_timeline / index |
| 修改 | `web/index.html` | C5：`#pane-selection` 按钮接真实处理函数（运行/校验/保存/发布/版本/调试/调度/数据诊断/停止/日志/导出）、新增属性抽屉容器、加载 18 个模块脚本 |
| 修改 | `web/css/style.css` | C5：工作台四态/模态/抽屉/时间线等样式 |
| 新增测试 | `tests/server/test_selection_models_api.py` | 17 例 API 集成测试（`p1` 档） |
| 修改测试 | `tests/conftest.py` | 新用例登记 `p1` 档位 |

### 13.2 验收与门禁实测

| 项 | 结果 |
|---|---|
| P0 核心门禁 `pytest -m core` | **197 passed / 0 failed**（无回归） |
| 批次三 API 集成 `pytest tests/server/test_selection_models_api.py` | **17 passed / 0 failed** |
| 治理子集（authenticity/decoupling/quality_gates/skill_contracts） | **31 passed** |
| 前端 Node 静态断言（29 脚本） | 全通过（无 FAIL） |
| 发布门禁 2（空白创建→保存草稿→发布→激活→无编码运行） | `condition_tree`/`funnel` 从空白创建；`validate`→`publish`（服务端分配 v1）→`activate`→`runs` 一次跑通，输出 `COMPLETED` 与 `selected_codes` |
| 发布门禁 3（Web 数字可追溯到后端运行记录） | 工作台所有模型/版本/运行/候选/结果/水位均来自 `/api/selection-models/*`；前端无 Mock 回退（治理断言通过） |
| 发布门禁 10（正式运行与调试隔离） | `debug/rule`、`debug/node` 返回水印 `debug=True`、`eligible_for_signal=False`，不落运行目录、不发信号、不出现在 `runs`/`results` |
| 发布门禁 18（多次运行互不覆盖） | 同一模型两次手工运行产生不同 `run_id` 与独立 `run.json`/`stages.json`/`candidates.json`；`request_id` 重试返回原运行（`deduplicated=true`） |
| C2 权限边界 | 匿名 401；超管全通；`model_author` 可 create 但 publish/debug 均 403（矩阵对齐 W-02/C-03、G-02） |
| C3 SSE 事件契约 | `runs/{run_id}/events` 输出 `run.started`/`stage.completed`/`run.finished`/`heartbeat`，每事件含 `run_id` 与水印（W-01） |
| 越权/路径安全 | `model_id`/`run_id` 经白名单校验；不接受任意路径；P2 类型不可创建（`MODEL_TYPE_UNKNOWN`） |

### 13.3 明确边界（未越界声明）

- **§15.3 阶段 E 端点未注册**：`assessments`/`tracking-plans`/`evaluations`/`tuning-suggestions` 按裁定归**批次四（二期）**，本轮不暴露为正式能力（对齐 §七 批次四与 M-05 前置约束）。
- **前端编辑器为参数级编辑**：条件组/漏斗阶段提供结构化渲染 + 参数 Schema 表单 + 草稿保存/校验/发布；拖拽排序等富交互未实现，属后续增强，不伪造任何运行态。
- **数据侧前提不变**：手工运行在无本地水位时**失败关闭**（`MODEL_DATA_MISSING`，不产码）；D-11 增量同步就绪前，覆盖率 100% 实际达标与 M-03 的判定不受本批次影响。
- **G-01 技能登记**仍未同步三处清单（18→19），不在本批次范围内。

---

## 十四、批次四交付物与验证证据（2026-10-07）

### 14.1 新增/修改文件

| 类型 | 路径 | 说明 |
|---|---|---|
| 新增 | `scripts/core/selection_models/market_view.py` | E1～E5 共用行情视图与统计基元：`Bar` 归一（缺字段失败关闭）、板块涨跌停、MFE/MAE、最大回撤、年化波动、ATR、均线、**未来数据检测**、`nth_trading_date`（T+N 交易日历）、复用费用配置与最低保本价（向上进位） |
| 新增 | `scripts/core/selection_models/position_policy.py` | E2：可回测 `PositionPolicy`（entry/position/risk/exit），风险预算仓位 + 单股上限（D-20）；缺账户规模/成交价→不生成伪精确股数与保本价；三级止损口径来源显式登记（D-23）；`research_only=True` |
| 新增 | `scripts/core/selection_models/backtest_service.py` | E2：`markout_analysis`（不假设交易）与 `event_backtest`（逐日事件驱动）**口径严格分离**；T+1/100 股整手/涨跌停不可成交/停牌；参数化佣金·最低收费·印花税·过户费·滑点；输出 CAGR/MaxDD/Sharpe/Calmar/胜率/盈亏比/换手率/平均持有期/MFE/MAE；`as_of` 未来数据检测 |
| 新增 | `scripts/core/selection_models/result_assessment.py` | E1：`ResultAssessmentService` —— 个股信息快照 + 入选解释（命中层级/通过规则/观测值/同批排名/证据链接）+ 技术与风险画像 + 历史行为 + 相对表现 + `PositionPolicy` + 两类回测摘要；绑定 `assessment_as_of`/`data_snapshot_id`；`research_only`/`future_returns_guaranteed=False` |
| 新增 | `scripts/core/selection_models/tracking_service.py` | E3：`TrackingPlan` 与**只追加** `TrackingObservation` 存储；状态机 `CREATED/ACTIVE/WAITING_DATA/COMPLETED/EXPIRED/CANCELLED/FAILED`；`(code, period)` 幂等追加、绝不覆盖历史 |
| 新增 | `scripts/core/selection_models/tracker_scheduler.py` | E3：独立 Tracker Tick —— 按交易日历执行**到期**观察、重复 Tick 幂等、水位未就绪进入 `WAITING_DATA` 且**不写伪观察**；观察绑定 `run_id`/`signal_id`/基准价/数据版本 |
| 新增 | `scripts/core/selection_models/model_evaluator.py` | E4：`ModelEvaluation` —— T+N 汇总、分层流失、规则分组（轨迹不完整如实不可用）、市场门控分组、版本对比；D-16 阈值不足返回 `EVALUATION_SAMPLE_INSUFFICIENT`；选股模型评价与 PositionPolicy 评价分列 |
| 新增 | `scripts/core/selection_models/optimization_advisor.py` | E5：只读 `OptimizationSuggestion` —— 六类建议 + 继续观察；证据可追溯 `run_id`；`pending→accepted/ignored`；活动版本变化即 `STALE`；`auto_apply=False`、无自动改版路径 |
| 修改 | `scripts/core/selection_models/paths.py` | 阶段 E 落盘派生点：`assessments`/`evaluations`/`backtest`/`suggestions`/`tracking` 计划与观察文件 |
| 修改 | `scripts/core/selection_models/__init__.py` | 包入口文档补登阶段 E 模块 |
| 修改 | `scripts/server/api/selection_models.py` | §15.3 阶段 E 端点注册 + 请求模型 + 失败关闭与水印；非法标识符不产生越权路径 |
| 新增测试 | `tests/core/test_selection_stage_e.py` | 16 例核心契约（`core` 档） |
| 新增测试 | `tests/server/test_selection_stage_e_api.py` | 4 例 API 集成（`p1` 档） |
| 修改测试 | `tests/conftest.py` | 新用例分层登记（`core` / `p1`） |

### 14.2 验收与门禁实测

| 项 | 结果 |
|---|---|
| P0 核心门禁 `pytest -m core` | **213 passed / 0 failed**（批次三后为 197；+16 新增） |
| 批次四核心用例 | `tests/core/test_selection_stage_e.py` **16 passed** |
| 批次四 API 用例 | `tests/server/test_selection_stage_e_api.py` **4 passed** |
| 治理子集 + 批次三 API 回归 | **52 passed / 0 failed** |
| 发布门禁 12（回测/跟踪不表述为未来收益保证） | 评估载荷 `interpretation` 明确"不代表未来收益"、`future_returns_guaranteed=False`；评价水印按样本充足度降级 |
| 发布门禁 14（跟踪可从原始信号追溯、重复 Tick 不重复观察） | 观察绑定 `run_id`/`signal_id`；同 `(code, period)` 重复 Tick 幂等跳过；水位未就绪进入 `WAITING_DATA` 且不落盘 |
| 发布门禁 15（A股约束 + 配置化摩擦成本 + 未来数据检测） | 事件驱动回测含 T+1、100 股整手、涨跌停不可成交、停牌跳过、佣金/最低收费/印花税/过户费/滑点；任一 bar 晚于 `as_of` 即拒绝回测 |
| 发布门禁 16（样本不足不出强结论、建议不自动改版） | 样本 <30 或观察周期 <20 交易日 → `EVALUATION_SAMPLE_INSUFFICIENT` + `strong_conclusion_allowed=False`；建议 `auto_apply=False`、`suggested_value=None`、仅"继续观察" |
| 发布门禁 17（建仓持股策略为研究方案、无自动下单路径） | `PositionPolicy.research_only=True` + `disclaimer`；模块无任何下单/交易调用 |
| 发布门禁 19（建议仅基于已完成历史运行与跟踪、可追溯 `run_id`） | 建议 `evidence_run_ids` + `statistical_window`；仅读取固化观察批次；状态标记不回写模型定义 |
| 权限边界（§22.3） | 匿名 401；`researcher`（view+track）可建跟踪计划但评价/调优/激活均 403；`model_author` 拥有 track/evaluate 但无 publish/activate/debug |

### 14.3 明确边界（未越界声明）

- **`screen-model` 族 CLI（§14 `assess`/`track`/`evaluate`/`tune`）未接线**：本批次只落地核心引擎与后端 API；CLI 外壳属后续增强，不伪造入口。
- **Web「结果研究/持续跟踪/模型评估」页签（§16 8～10）未接线**：`#pane-selection` 现有页签不新增假数据；新页签待前端批次补齐，接口已就绪。
- **Tracker Tick 无独立 API 端点**：由核心 `TrackerScheduler.tick` 承载（与选股调度同族的注入式 records_provider），后续调度接线时复用。
- **行业/复权口径**：`rel_industry_return_pct` 与 `adj_return_pct` 在无行业基准/复权数据时返回 `None`（如实标注，不伪造）。
- **M-05 判定不变**：阶段 F「正式可用」仍为未启动；D-11 数据侧前提不影响本批次判定。

---

> 本文为静态审查与规划文档，不构成任何个股投资建议。