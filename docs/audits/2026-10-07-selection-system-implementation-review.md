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

按里程碑判定：**M-01 达成；M-02 部分进展（未达）；M-03～M-05 未达；二期（阶段 E）未启动。**

| 里程碑 | 内容 | 判定 |
|---|---|:--:|
| M-01 | 一期范围与规格冻结 | ✅ 达成 |
| M-02 | 阶段 A：配置与核心引擎 | 🟡 底座有、主体缺（未达） |
| M-03 | 阶段 B：数据与调度 | 🔴 数据侧有底、调度侧为零（未达） |
| M-04 | 阶段 C+D：API/持久化与 Web | 🔴 零实现（未达） |
| M-05 | 阶段 F：正式可用 | 🔴 未启动 |
| 二期 | 阶段 E：结果研究/跟踪/调优 | ⬜ 未启动 |

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
| **核心引擎** | HFE、规则注册、三态求值、AND/OR/NOT AST | 🟡 大部分具备：三态 `RuleResult`、Kleene 强三值、`RuleRegistry`、`StageResult`；**嵌套表达式树/NOT 未实现**（`logic` 仍仅 `all/any`） | `scripts/core/strategy/funnel_engine.py` |
| **规则库** | 全量参数化、分钟拐点、三态改造 | ✅ 具备：21 类规则；分钟时间戳归一化校验、`earliest_possible_hit_time` 编译期推导、信号定性、窗口全参数化 | `scripts/core/strategy/stock_funnel.py` |
| **配置/版本** | v2 Schema、迁移器、`definition_hash`/`plan_hash`、版本仓库 | 🔴 未具备：现为 `version: 1`；无哈希、无版本仓库、无草稿锁 | `config/funnel_strategy.yaml` |
| **模型类型/构建器** | 类型注册中心、编译器、构建器、文案草稿解析 | 🔴 未具备：规划目录 `scripts/core/selection_models/` 不存在 | §19 规划目录零文件 |
| **数据装配** | `finalized_local`/`intraday_capture`、水位门禁、快照清单 | 🟡 部分具备：`DataAssembler`、分钟归一化、`TradeCalendar` 已接 | `scripts/core/data/data_assembler.py` |
| **调度** | Scheduler Tick/daemon、运行锁、幂等、Signal Latch、跨日恢复 | 🔴 未具备：无 `funnel daemon`/`tick`；`schedule` 仅被加载校验，无执行器读取 → **发布门禁 1 未满足** | `scripts/core/commands/funnel_cmds.py` |
| **CLI** | `funnel screen/regime/trigger/daemon` + 完整 `screen-model` 族 | 🟡 部分具备：仅 `funnel validate` 与 `funnel run` | `scripts/core/cli.py` |
| **后端 API** | `/api/selection-models/*` 全套 + 权限码/角色 | 🔴 未具备：`scripts/server` 零命中，`app.py` 路由表无 selection router | `scripts/server/app.py` |
| **前端工作台** | 模型中心、条件树/漏斗编辑器、版本管理、调试、运行时间线 | 🔴 仅 fail-closed 空壳：`#pane-selection` DOM+CSS 在，假数据已删、按钮 disabled；无 `web/js/selection-models/*` | `web/index.html` |
| **结果研究/跟踪/调优** | Assessment/Tracking/Evaluation/Suggestion | 🔴 未具备（已裁定移入二期阶段 E） | — |
| **技能登记** | 登记 `astock-selection-model`（G-01） | 🟡 未落地：技能清单仍 18 项，无 funnel 条目 | `config/skills_manifest.json` |

---

## 四、逐里程碑差距拆解

### M-02 · 配置与核心引擎（🟡 部分进展）

| 验收项 | 现状 | 缺口 | 交付物 |
|---|---|---|---|
| 类型注册与发现 | 无 | 无 `SelectionModelTypeRegistry`；首期 4 类型（`condition_tree`/`funnel` P0，`scoring_rank`/`composite` P2）零实现 | `selection_models/model_type_registry.py` |
| `condition_tree` | 无 | 维度组 + 布尔表达式树完全缺失 | 同上 + `expression_evaluator.py` |
| 嵌套 AND/OR/NOT | 无 | `logic` 仍只接受 `all/any`，无 group 节点、无 `NOT`、无深度(≤3)/叶子(≤200) 校验（T-01/S-04/S-05） | 就地升级 `funnel_engine` |
| 统一层级中间结构 | 无 | 无 `CompiledSelectionPlan`、无 `plan_hash` 规范化复算 | `model_compiler.py` |
| v2 Schema + 迁移 | 无 | 仍 `version: 1`；无 v1→v2 迁移器（S-01/T-06） | `schemas.py` + 迁移器 |
| 版本仓库/草稿/发布/激活 | 无 | 无 `definition_hash`、不可变版本、`base_version/draft_revision` 冲突检测、悲观文件锁（S-02/S-03/T-07） | `definition_repository.py`、`version_repository.py` |
| 参数 Schema 齐备 | 部分 | 规则有默认值但无 JSON Schema 2020-12 元数据（S-06） | `rule_registry.py` 元数据 |
| `run-all` 按依赖执行 | 无 | 仅单阶段 `funnel run --stage`；无编排器 | `orchestrator.py` |

> **M-02 是当前最近的、自包含的目标**——不依赖外部数据契约，可独立推进。

### M-03 · 数据与调度（🔴 数据侧有底、调度侧为零）

| 验收项 | 现状 | 缺口 |
|---|---|---|
| 双模式装配 | ✅ 已有 `assemble_daily`/`assemble_intraday`/`evaluate_data_gate`/`content_hash`/`resolve_universe` | 补齐 `UniverseWatermark` 分层分母（A-05/R-03） |
| `data_snapshot_id`/切片/哈希 | 🟡 部分 | 检查输入切片留存与 90 天淘汰（D-18） |
| **Scheduler Tick/daemon** | 🔴 零 | 无 `funnel daemon`/`tick`；`schedule` 声明后无执行器读取 → **发布门禁 1 未达**（O-01） |
| 运行锁/幂等/Signal Latch | 🔴 零 | 跨平台文件锁（粒度 `model_id+trade_date`）、分层幂等键、`converge_at_window_end` 收敛锁存（O-02/O-03） |
| 跨交易日状态恢复 | 🔴 零 | 落盘快照按交易日重建（O-04） |
| 交易日历门控 | 🟡 部分 | `TradeCalendar` 已有；需接入调度 |

> **关键路径阻塞**：D-11（证券主数据 + 分钟线 + 资金流持久化）未就绪时，D-12 的 **100% 覆盖率门槛将长期不达标**，会阻断全部正式信号。

### M-04 · API + Web（🔴 零）

| 层面 | 现状 | 缺口 |
|---|---|---|
| 后端 API | 零 | 路由表无 selection router；§15 全部端点缺失；10 个权限码与 `model_author` 角色未注册 |
| Web 工作台 | fail-closed 空壳 | `#pane-selection` DOM 与 CSS 在，但假数据已删、按钮 disabled；`web/js/selection-models/*` 18 个规划模块全缺 |

### 二期 · 阶段 E（⬜ 未启动）

`ResultAssessment`/`TrackingPlan`/`TrackingObservation`/`ModelEvaluation`/`OptimizationSuggestion` 存储与服务全无。

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

#### 批次一 · 核心引擎（目标 M-02，可立即启动）

| 序号 | 任务 | 交付物 | 依赖 | 验收 |
|:--:|---|---|---|---|
| A1 | v2 Schema 定义 + v1→v2 内存迁移器（幂等、加载告警） | `selection_models/schemas.py` | 无 | 存量 `funnel_strategy.yaml` 自动升级且行为不变 |
| A2 | `definition_hash`/`plan_hash` 规范化 JSON + SHA-256 复算 | `selection_models/hash.py` | A1 | 键序/空白/数值写法无关，`calendar_version` 不入哈希 |
| A3 | 嵌套 AND/OR/NOT AST 就地升级 `funnel_engine`（`all/any` 为快捷写法） | `funnel_engine.py` | 无 | Kleene 真值表全组合通过；深度≤3/叶子≤200 校验 |
| A4 | `CompiledSelectionPlan` 编译器（condition_tree/funnel → 统一层级） | `model_compiler.py` | A2/A3 | 同版本同编译器 → 同 `plan_hash`；未知节点发布期失败 |
| A5 | 类型注册中心（首期登记 4 类型，P2 类型不可发布） | `model_type_registry.py` | A4 | 类型发现/未知类型拒绝；P2 节点被编译器拒绝 |
| A6 | 版本仓库 + 草稿 + 悲观文件锁 + 发布/激活/回滚 | `definition_repository.py`、`version_repository.py` | A2 | 发布号单调、内容不可变、草稿冲突被拒、激活只切指针 |
| A7 | 规则参数 Schema 元数据（JSON Schema 2020-12 子集 + UI 注解） | `rule_registry.py` | 无 | 表单可由 Schema 动态生成 |
| A8 | 编排器 `run-all`（按 stage 依赖执行整链） | `orchestrator.py` | A4/A6 | 四层漏斗一键按依赖执行 |

> **出口**：M-02 全绿（引擎类验收项）+ 发布门禁 8、9。

#### 批次二 · 数据与调度（目标 M-03）

| 序号 | 任务 | 交付物 | 依赖 | 验收 |
|:--:|---|---|---|---|
| B1 | 内置 Tick 常驻 `funnel daemon` + `TradeCalendar` 门控 | `selection_models/scheduler.py`、`funnel_cmds` | A6 | 真实读取 YAML 4 处 `schedule` 窗口；优雅退出 |
| B2 | 运行锁（`model_id+trade_date`，运行期持有）+ 分层幂等键 | 锁模块（与 T-07 同族） | B1 | 同分钟重复 Tick 不重复执行；多进程互斥 |
| B3 | Signal Latch（`converge_at_window_end` 收敛锁存） | `signal_latch.py` | B2 | 窗口内仅待定；窗口末唯一终态 |
| B4 | 跨交易日状态恢复（落盘快照 + 按交易日重建） | `run_repository.py` | B1 | 重启后当日状态可恢复 |
| B5 | `UniverseWatermark` 分层分母 + 覆盖率门禁（R-03/A-05） | `data_assembler.py` 扩展 | D-11 | 硬门禁 100%，不达标整场降级 |
| B6 | 落盘目录规范（运行元数据/切片/候选/信号） | 按 SSOT §13.10 | B1/B4 | 三桶规范；90 天淘汰/信号切片保留 |
| B7 | 修复 W-09/W-10（市值单位 + 缺失置零） | 同步入库层 | — | 单位一致可校验；缺失不入比较 |

> **出口**：M-03 全绿 + 发布门禁 1、4、5、6、7、11、13。**B5 强依赖 D-11 数据契约**。

#### 批次三 · API 与 Web（目标 M-04）

| 序号 | 任务 | 交付物 | 依赖 | 验收 |
|:--:|---|---|---|---|
| C1 | Selection Model API（§15 全套）+ 统一水印包裹 | `scripts/server/api/selection_models.py` | A6/B1 | 契约与错误码齐备；越权拒绝 |
| C2 | 权限码 10 项 + `model_author` 角色（复用 `role_menus` 两段式） | `api/roles.py` 扩展 | C1 | 矩阵对齐 W-02/C-03；`:debug` 仅 `super_admin` |
| C3 | SSE 运行事件流（复用既有 SSE 基础设施） | `api/selection_models.py` | C1 | 事件含 `run_id` 与水印 |
| C4 | 运行/阶段/候选/信号持久化存储 | `run_repository.py` 等 | B4 | 多模型多次运行互不覆盖 |
| C5 | Web 工作台 18 模块（模型中心/向导/编辑器/调试/运行时间线） | `web/js/selection-models/*` | C1 | 四态真实（loading/empty/error/success）；无 Mock 回退 |

> **出口**：M-04 全绿 + 发布门禁 2、3、10、18。

#### 批次四 · 二期（阶段 E）

| 序号 | 任务 | 交付物 | 依赖 |
|:--:|---|---|---|
| E1 | 结果个股信息快照 + 入选证据聚合 | `result_assessment.py` | C4 |
| E2 | 信号标记分析 + 事件驱动回测 + `PositionPolicy`（复用量化引擎） | `backtest_service.py`、`position_policy.py` | C4 |
| E3 | 实时/T+N TrackingPlan + Tracker Tick + 观察存储 | `tracking_service.py`、`tracker_scheduler.py` | C4 |
| E4 | 模型评价（T+N 汇总、分层流失、通过/未通过组对比） | `model_evaluator.py` | E3 |
| E5 | 简单优化建议（只读、可追溯 `run_id`、不自动改版） | `optimization_advisor.py` | E4 |

> **出口**：发布门禁 12、14、15、16、17、19。

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

- **P0 核心门禁**：实测 **151 passed / 0 failed**（`python -m pytest -m core`；命令退出码 1 的根因是沙箱拦截 `/opt/conda` 下 `.pyc` 写入，非用例失败）。
- `tests/core/test_stock_funnel.py`：**37 用例**，覆盖 Kleene 真值表、分钟时间戳五形态归一化、进行中 Bar 排除、`earliest_possible_hit_time` 推导、信号定性、窗口参数化、失败关闭、declared block 标记校验——**底座测试质量高**。
- **缺口**：§22.2 调度测试、§22.3 API 集成测试、§22.4 前端测试对应用例**全不存在**（被测对象不存在）。
- **治理已纠偏**：2026-10-07 已删除工作台整屏假数据，改 fail-closed，并新增 `tests/governance/test_production_authenticity.py` 结构断言防回流。

---

## 九、风险与开放项

| 类型 | 编号 | 内容 | 处置建议 |
|---|---|---|---|
| 技术债 | D-23 | 止损口径不统一 | registry 登记口径来源 + 门禁扫描 |
| 技术债 | S-03 | 悲观锁 | 配套超时释放/显式解锁/持有者可见 |
| 技术债 | D-11 | 三类数据持久化 | 与 B5 覆盖率门禁联动排期 |
| 高危 | W-09/W-10 | 市值单位与缺失置零 | 修复前不得启用流通市值阈值 |
| 治理 | G-01 | 技能清单未登记 `astock-selection-model` | 批次一结束后同步三处清单（18→19） |
| 契约 | (i) | Web 模型构建器无实现载体 | 批次三 C5 交付前维持 fail-closed |

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

> 本文为静态审查与规划文档，不构成任何个股投资建议。