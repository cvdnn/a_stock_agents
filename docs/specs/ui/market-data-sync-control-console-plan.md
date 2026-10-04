# 行情数据同步控制台实施计划与验收看板

> 规范编号：`SPEC-UI-003`
> 权威定义 (SSOT)：[`market-data-sync-control-console-specification.md`](../../guidelines/ui/market-data-sync-control-console-specification.md)
> **实施状态**：实施中（矩阵 1–10 已完成；外部源排序执行层接入、浏览器人工核验与前端 Node 回归执行待完成）

## 一、规范核心定位摘要

- 将【数据同步】收敛为与现有系统一致的一级菜单三页控制台。
- 运行控制、任务追溯与高级设置均使用确定性接口，不加载 AI 助手。
- P3 全市场同步采用“交易日定时增量 + 控制台手动选择”模式，并服从 P0/P1 优先级与单任务互斥约束。
- 具体视觉、交互、接口与可访问性契约以权威定义为准，本看板只追踪落地与验收。

## 二、实施任务矩阵

| 任务 | 关联代码路径 | 状态 |
|:---|:---|:---:|
| 建立三 Tab 语义结构与无 AI 全宽工作区 | `web/index.html` | ✅ 已完成 |
| 落地运行控制页、任务记录页和高级设置页样式 | `web/css/style.css` | ✅ 已完成 |
| 接入任务创建、列表、详情、取消与重试 | `web/js/api.js`、`web/js/app.js` | ✅ 已完成 |
| 在运行控制页增加 P3 全市场进度、自动状态和手动范围选择 | `web/index.html`、`web/js/app.js`、`web/css/style.css` | ✅ 已完成 |
| 删除数据同步随机测速、延迟成功和静态成功数据 | `web/js/app.js` | ✅ 已完成 |
| 新增数据同步概览与设置接口（实际落于 `GET/PUT /api/data-sync/*`） | `scripts/server/api/data_sync.py`、`scripts/server/app.py` | ✅ 已完成 |
| 将设置安全持久化至 `local/settings/data_sync.json`（白名单+范围校验、0600 原子写、回读刷新） | `scripts/server/services/data_sync_settings.py` | ✅ 已完成 |
| 统一新任务类型为 `data_sync`，读取历史任务时兼容 `sync` | `scripts/server/tasks/task_manager.py`、`scripts/server/api/tasks.py` | ✅ 已完成 |
| 定时守护每轮读取有效设置并遵守 P0/P1/P3 启停、时间与优先级 | `scripts/core/data/sync_daemon.py`、`scripts/server/app.py` | ✅ 已完成 |
| 实现 P3 单任务互斥、批次进度和 P0/P1 优先资源仲裁（SYNC_ARBITER + 创建前 409 预检；执行器共享、让路式仲裁） | `scripts/core/data/sync_daemon.py`、`scripts/server/tasks/task_manager.py` | ✅ 已完成 |
| 将外部行情源优先级与本地 SQLite 数据层配置分离（设置模型已独立并校验；排序接入取数执行层为后续项） | `scripts/server/services/data_sync_settings.py`、`web/index.html` | 🟨 部分完成 |
| 建立前端结构、交互、无 AI 与失败恢复测试 | `tests/frontend/` | 🟨 断言已升级，本环境无 Node 未执行 |
| 建立设置校验、概览真实性、P3 调度与互斥测试（23 项） | `tests/server/test_data_sync_settings.py` | ✅ 已完成 |
| 更新 UI 权威规范、实施矩阵和项目总索引 | `docs/guidelines/`、`docs/specs/`、`docs/index.md` | 🟨 进行中 |

## 三、里程碑推进

```mermaid
timeline
    title SPEC-UI-003 数据同步控制台实施路线
    M1 文档基线 : 规范与实施看板分离 : 全局索引登记
    M2 结构与样式 : 三 Tab 页面结构 : 现有视觉 Token 复用 : AI 助手隔离
    M3 真实数据接入 : 任务 API : 概览与设置 API : P3 定时增量与手动范围选择
    M4 验收收敛 : 前端回归 : 后端回归 : 响应式与可访问性核验
```

## 四、验收与验证证据

| 断言 | 测试路径 | 当前结果 |
|:---|:---|:---:|
| 数据同步保持一级菜单并具备三个可访问 Tab | `tests/frontend/` | ✅ 已验证 |
| 数据同步页面不显示 AI 助手且不触发模型调用 | `tests/frontend/` | ✅ 已验证 |
| 页面不存在随机测速、模拟进度和伪造成功结果 | `tests/frontend/`、代码扫描 | ✅ 已验证 |
| 手动同步创建真实 `data_sync` 任务并可跟踪 | `tests/frontend/`、`tests/server/` | ✅ 已验证 |
| 活动任务可取消，失败任务可重试 | `tests/frontend/`、`tests/server/` | ✅ 已验证 |
| 设置字段经过白名单和范围校验（拒绝而非静默夹紧，未知字段/越界/HH:MM/排序完整性/P0≤P1） | `tests/server/test_data_sync_settings.py` | ✅ 已验证 |
| 设置落盘路径位于 `local/` 且文件 0600、不进入版本控制、损坏回退默认并如实标注 | `tests/server/`、`.gitignore` | ✅ 已验证 |
| P3 仅在交易日按有效设置时间（默认 16:00）自动执行增量同步；开关与时间可配置 | `tests/server/`（判定纯函数）、`server/app.py` 协程 | ✅ 自动化已验证（实盘 16:00 自然触发待观察期） |
| P3 手动任务支持市场/代码范围选择，全量模式必须二次确认；市场级范围仅增量、北交所 fail-closed | `tests/frontend/`、`tests/server/` | 🟨 后端已验证（bj/审计组合拒绝），前端断言待 Node 环境执行 |
| P3 单任务互斥且不得抢占 P0/P1 任务（SYNC_ARBITER + 创建前 409） | `tests/server/` | ✅ 已验证 |
| 新任务统一创建为 `data_sync`，历史 `sync` 记录仍可读取 | `tests/frontend/`、`tests/server/` | ✅ 已验证 |
| 外部行情源与本地 SQLite 数据层在设置模型中相互独立 | `tests/frontend/`、`tests/server/` | 🟨 设置模型独立性已验证；取数执行层排序接入为后续项 |
| 窄屏无页面级横向滚动，键盘可切换 Tab | 浏览器核验、`tests/frontend/` | 🟨 自动化已验证，浏览器受认证遮罩阻断 |
| 前端与后端相关回归测试通过 | `tests/frontend/`、`tests/server/` | 🟨 后端 45/45 通过（2026-10-04 实测）；前端 Node 测试本环境无运行时未执行 |

## 五、变更日志

| 日期 | 变更摘要 |
|:---|:---|
| 2026-09-24 | 建立 `SPEC-UI-003`，将三页控制台权威定义与实施看板按项目双范式拆分归档 |
| 2026-09-24 | 归入“行情数据同步系统”功能系列，新增 P3 定时增量、手动范围选择、资源仲裁与配置分层契约 |
| 2026-09-24 | 完成实施矩阵 1–5：三 Tab 无 AI 控制台、真实任务 API 交互、P3 手动控制与伪成功清理；新增前端回归测试 |
| 2026-10-04 | 审查发现看板滞后于代码：概览/设置接口、`data_sync` 任务统一与守护开关实为已实现（接口落于 `/api/market_data/*`），矩阵按实况回写 |
| 2026-10-04 | 落地设置白名单校验与 `local/settings/data_sync.json` 0600 原子持久化（`server/services/data_sync_settings.py`），守护启停与并发设置写穿、重启不回跳；新增 `GET/PUT /api/data-sync/settings` 与 `GET /api/data-sync/overview` |
| 2026-10-04 | 落地 P3 全市场/沪深增量枚举（新浪权威清单源，北交所无源拒绝）、交易日定时增量（默认 16:00 可配置）、SYNC_ARBITER 单任务互斥与不抢占 P0/P1、创建前 409 预检、分批进度与 degraded 如实上报；前端解除市场级范围封禁并接入有效设置回显 |
| 2026-10-04 | 清理 `/api/monitor/stream` 最后一片硬编码假数据（示例事件/恒真监控/伪造 12ms 延迟），对齐既有 `not_running` 契约；新增后端回归 23 项（`tests/server/test_data_sync_settings.py`），同步域 45/45 通过 |
