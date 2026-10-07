# 【数据同步】UI 核心功能清单

> 用途：指导 A-Stock Agents「数据同步」页面的信息架构、功能布局与交互状态设计。
> 依据：[现有界面规范](../guidelines/ui/market-data-sync-control-console-specification.md)、[数据同步规则](../guidelines/data/market-data-sync-specification.md)。
> 配色参考：[项目工程 UI 设计配色提取](./project-ui-color-tokens-extracted.md)。

建议沿用项目现有的 **运行控制、任务记录、高级设置** 三个页签。页面定位是行情数据的运行控制台，操作和结果都由系统接口提供，不依赖 AI 对话。

| 页面 | 用户需要完成的事 | 关键界面内容 |
|---|---|---|
| **运行控制** | 判断数据是否新鲜，并发起同步 | 交易日与市场阶段、服务状态、最近同步时间；P0 持仓、P1 自选/关注、P2 核心指数、P3 全市场的独立任务卡；同步进度、完整性体检、行情源状态、自动守护摘要 |
| **任务记录** | 追踪结果和处理失败 | 按日期、状态、任务类型及代码筛选；展示任务 ID、范围、模式、成功/失败数、耗时；查看详情、取消活动任务、重试失败任务 |
| **高级设置** | 管理后续同步策略 | 定时开关与执行时间、并发和批次大小、行情源优先级、完整性与修复策略、本地数据层信息、通达信导入 |

## 运行控制页的核心操作

首要操作是“同步选中范围”。P0 至 P2 应显示标的数量、最新数据日期和单独同步入口；P3 应显示范围、模式、批次及成功/失败进度。完整性区域需把正常数据、合规停牌和异常缺漏分开展示，并从真实缺漏明细发起修复。

## 现有能力与待接入能力

当前页面已具备三页签、任务列表与操作入口；P3 手动任务目前仅支持“指定代码＋增量同步”，全市场及沪深北分区选项仍被禁用；高级设置仍是不可保存的占位表单。因此，这些能力在设计稿中可作为目标状态展示，但当前产品界面应明确标为“待接入”，不要呈现为可用操作。

依据：[当前页面](../../web/index.html)、[P3 提交逻辑](../../web/js/app.js)、[实施看板](../specs/ui/market-data-sync-control-console-plan.md)。

## 状态与运行主体

所有模块至少设计 **加载、空数据、运行中、部分失败、失败、完成** 状态；任务提交后显示真实任务 ID。

界面需将 **Web 服务内巡检** 与 **独立 CLI 守护进程** 标成两个不同的运行主体，避免一个开关让用户误以为同时控制两者。依据：[现有调度逻辑](../../scripts/server/app.py)。

## 修订注记（2026-10-04，追加不改原文）

上文「现有能力与待接入能力」一节描述的是提交 `d873331` 时点的页面快照，已被提交 `b55d07c` 超越，现状更正为：

- P3 手动任务已支持**全市场/沪市/深市（仅增量）＋指定代码（全部模式）**；北交所因无权威股票清单数据源继续保持禁用（fail-closed），依据新浪权威清单源枚举，上游不可用时任务如实失败，不伪造清单；
- 高级设置已可真实保存：白名单与范围校验后原子落盘 `local/settings/data_sync.json`（0600），守护启停、P0/P1/P3 时间与并发改动重启后保持；`GET/PUT /api/data-sync/settings` 与 `GET /api/data-sync/overview` 已接入；
- P3 单任务互斥与「不抢占 P0/P1」由 `SYNC_ARBITER` 服务端强制（冲突创建返回 409），交易日定时增量默认 16:00 可配置；
- 唯一仍属"待接入"的：外部行情源优先级排序对取数执行层的实际驱动、以及市场级范围的全量重构/审计/修复组合。

验收证据与状态以[实施看板](../specs/ui/market-data-sync-control-console-plan.md)为准。

## 修订注记（2026-10-07，追加不改原文）

上文 2026-10-04 注记列出的「唯一仍属待接入」两项，现状更正为：

- **外部行情源优先级排序对取数执行层的驱动：已接入。** 新增 core 层只读设置访问器 `scripts/core/data/sync_settings.py`，`resolve_provider_order()` 解析 `external_sources.order` 与 `external_sources.enabled.*`（全禁用时回退内置默认并标注 `default:all_disabled`），`data_bridge.fetch_remote_kline_strictly` / `get_kline_robust` / 新增 `eastmoney_kline` 按该链遍历，失败日志携带 `chain_source`；`Ashare` 为多源聚合器，保留为不参与排序的末端兜底。
- **市场级范围的全量重构/审计/修复组合：仍保持禁用（fail-closed）。** 该组合对全市场属破坏性操作，继续按原设计不放开。

另：`base.timeout_seconds` 已接入任务创建、`cooperation.tdx_target_pool` 已接入通达信导入；其余仅持久化未接线的设置项由 `data_sync_settings.EXECUTION_WIRING` 常量逐项归类（`wired` / `persist_only`）并经 `GET /api/data-sync/settings` 的 `execution_wiring` 键对外披露，不再存在静默死配置。
