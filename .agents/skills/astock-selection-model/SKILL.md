---
name: astock-selection-model
version: "1.0.0"
author: ""
description: 配置化智能选股系统（ISS，SPEC-ALGO-ISS-001）。用于把"用户自建选股模型"从零代码创建、编译、发布、激活到交易日调度运行的全生命周期，并提供结果研究与持续跟踪评估。适用于用户提到"智能选股""自建选股模型""层级漏斗""条件树""模型版本/发布/激活""选股调度""结果研究""跟踪评估"等场景。
---

# 智能选股系统（ISS）

把"我想要一套可复用、可版本化、可调度的选股规则"转成可编译、可发布、可审计、可回滚的模型资产。

## 定位与边界

- 本技能对应权威规范 `SPEC-ALGO-ISS-001`，核心代码在 [selection_models 包](../../../scripts/core/selection_models/__init__.py)。
- 与既有 5A 选股（`astock screen`）**并行且不复用入口**：5A 是单次多维打分，ISS 是"模型资产 + 版本 + 调度 + 结果研究"的平台。
- **不直连外部数据源**：ISS 是本地行情数据体系的消费者，数据不足一律失败关闭，不产出任何候选代码。
- 正式信号按裁定归二期；一期仅输出观察候选并标记 `not_eligible_for_signal`。

## 里程碑现状（截至 2026-10-07）

| 里程碑 | 内容 | 判定 |
|---|---|---|
| M-02 | 阶段 A：配置与核心引擎 | 已达成 |
| M-03 | 阶段 B：数据与调度 | 部分达标（覆盖率 100% 实际达标待 D-11 数据持久化） |
| M-04 | 阶段 C+D：API 与 Web | 已达成 |
| 二期 | 阶段 E：结果研究/跟踪/调优 | 已达成 |
| M-05 | 阶段 F：正式可用 | 未启动 |

## 统一 CLI 入口

约定全部追加 `--json` 获取结构化输出：

- `astock funnel validate --json`：校验四阶段漏斗配置（阶段 ID、规则类型、`earliest_possible_hit_time`、`stage_schedules`）。
- `astock funnel run --stage <阶段> [--assemble] --json`：执行单阶段，含收盘水位门禁、盘中捕获装配与快照清单。
- `astock funnel tick --json`：执行一次调度 Tick（交易日门禁 + 分层幂等 + 运行锁）。
- `astock funnel daemon [--once] --json`：常驻调度守护（每分钟 Tick，优雅退出）。

> 后端 API 在前缀 `/api/selection-models` 下提供模型/草稿/版本/调试/运行/调度/结果/数据健康与阶段 E（评估/跟踪/调优）端点，Web 工作台在 `#pane-selection` 页签内真实接口驱动。

## 核心概念

1. **模型类型（Model Type）**：首期可发布 `condition_tree`（条件树）与 `funnel`（漏斗）；`scoring_rank`/`composite` 为 P2，不可发布。
2. **统一层级计划（CompiledSelectionPlan）**：任意模型类型统一编译为同一层级中间结构，由同一 `funnel_engine` 单内核执行。
3. **三级版本标识**：`version`（模型内单调发布号）/ `definition_hash`（规则与参数）/ `plan_hash`（额外含编译器版本与数据契约）；`calendar_version` 不入哈希。
4. **草稿-发布-激活**：草稿可编辑（悲观锁 + `base_version/draft_revision` 冲突检测）；发布后不可变；激活只切指针，激活旧版即回滚。
5. **运行隔离**：正式运行只加载"已发布且已激活"的版本；`debug/*` 只读编译中间产物与规则轨迹，不落运行目录、不发信号。
6. **调度语义**：分层幂等键 + 交易日历门控 + 运行锁；`converge_at_window_end` 在窗口末收敛为唯一终态。

## 使用流程（零代码路径）

1. **建模型**：Web 向导（空白/模板）或中文文案建模型（未识别片段登记为 `ambiguities`）。
2. **编辑**：条件树/漏斗编辑器按参数 Schema 动态渲染；规则参数全部可配置并纳入 `definition_hash`。
3. **校验**：编译期失败关闭（未知节点/未知规则/不可执行层级/参数非法一律拒绝）。
4. **发布**：服务端分配单调不可变版本；**激活**后才可运行。
5. **运行**：手工运行（`runs`）或调度运行（`funnel tick/daemon`）；数据不足失败关闭（`MODEL_DATA_MISSING`）。
6. **结果研究**：对最终候选生成个股信息、入选证据、风险画像、相对表现与建仓持股策略（研究方案，非交易指令）。
7. **持续跟踪**：创建实时/T+N 跟踪计划，观察只追加、可追溯 `run_id`，重复 Tick 幂等。
8. **评价与调优**：样本充足才出结论（否则 `EVALUATION_SAMPLE_INSUFFICIENT`）；优化建议只读、可追溯 `run_id`、**不自动改版**。

## 纪律与红线

- **不伪造**：数据不足不产出代码；前端无 Mock 回退；所有数字来自落盘运行记录。
- **不预发布**：未实现节点一律 fail-closed，禁止在 Web/API 显示为"可运行"。
- **不越权**：权限以"menu + action 两段式"落地；`:debug` 仅 `super_admin`；`track`/`evaluate`/`publish`/`activate` 相互独立。
- **不自动改版**：优化建议 `auto_apply=False`，活动版本变化即标记 `STALE`。

## 关键参考

- 主规范：[selection-system-specification.md](../../../docs/guidelines/algorithm/selection-system-specification.md)
- 模型类型契约：`docs/guidelines/algorithm/selection-model-types-specification.md`
- 实施看板：`docs/specs/algorithm/selection-system-plan.md`
- 实现审查：`docs/audits/2026-10-07-selection-system-implementation-review.md`

## 回答风格

- 先给"当前处于哪一层/哪个里程碑/是否可运行"的结论，再给证据与统一 CLI 命令。
- 涉及选股结论时，必须同时给出精确最低保本卖出价、三级止损阶梯与三场景动作单（见工作区规则）。
- 不给"必涨"语言；样本不足只登记"继续观察"。