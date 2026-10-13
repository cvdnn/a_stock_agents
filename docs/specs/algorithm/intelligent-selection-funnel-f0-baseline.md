# 智能选股漏斗重设计 F0 基线与接口契约（2026-10-12）

> 对应计划：[intelligent-selection-funnel-redesign-plan.md](intelligent-selection-funnel-redesign-plan.md) · 本文记录 2026-10-12 的 F0 历史基线与隔离证据；后续工作范围以当前计划为准。F0 取证未改菜单、权限、筛选实现或用户模型。

## 1. 取证边界与当前状态

- 取证前 `HEAD`：`179ad386aee0c53ca60210d262b298400f73f792`，分支 `main`，工作树为空。
- 仅对本机 `local/server/chats.db` 作 SQLite `mode=ro` 的角色菜单查询；未查询用户、模型或 Provider 凭据。自定义角色数量为 **0**；三个内置角色的实际 `selection` 绑定与下表一致。新菜单对已有授权角色的兼容处理见第 2 节。
- 本次未调用真实行情源、真实 LLM，也未读取或修改现有模型。接口闭环使用临时 SQLite、模型目录、缓存和隔离身份验证；结果见第 6 节。

## 2. 侧栏、旧工作台与权限基线

| 项目 | 取证时行为与代码位置 | 智能选股工作区相关缺口 |
|---|---|---|
| 侧栏 | `web/index.html` 的 `.nav-item[data-tab="selection"]` 显示「策略选股」和 🔻；`#pane-selection` 承载整个 `SelModels` 工作台；`web/js/app.js::switchRightTab` 进入 `selection` 时调用 `SelModels.bootstrap()`。登录后的侧栏脚本按 `/api/auth/me` 返回的菜单码隐藏无权入口。DB 种子 `scripts/server/db.py::_seed_user_system` 中 `selection` 为 `parent_id=0`、排序 25、图标 🎯。 | 新建【智能选股】一级入口与独立 pane；原 DOM 所在位置仅为取证时状态，交互按当前计划的工作区基准建设。 |
| 工作台 | 内存默认 `selectionMode='runs'`；运行卡与模型卡按 `runs/models` 切换。现有编辑器、规则库、草稿并发修订、校验、发布/激活、调度、逐层轨迹、候选分页/筛选/CSV、研究/跟踪/评价均挂在同一 pane。运行 Tab 按钮仍写「选股列表」，标题写「选股记录」；另有结果研究等四个阶段 Tab。 | 运行/模型模式名称不一致；新工作区的布局和联动按参考图及当前计划设计。 |
| 模型列表/运行列表 | `GET /api/selection-models?model_type=...` 已支持模型类型过滤；`GET /api/selection-models/runs` 只接收 `limit/offset`，仓库先汇总所有模型运行再切片，没有类型过滤或 `total`。前端 bootstrap 读取所有模型和最近 50 条运行。 | 首期漏斗筛选需在服务端先按类型过滤、再统计与分页。 |
| 权限 | 模型接口使用 `require_selection(action)`，只检查 `selection.<action>`；`debug` 只限超级管理员。`selection` 父菜单目前未在模型 API 中复核。内置 `researcher` 有 `selection/view/track`；`model_author` 有 `selection/view/create/edit/run/track/evaluate`，本人模型激活由逐模型所有权补充校验；超级管理员全权限。 | 新菜单必须有独立查看码，同时模型动作仍逐项使用 `selection.*`，直接 API 也要检查两段权限。 |

### 智能选股权限边界

1. 新建一级菜单 `intelligent_selection`（`parent_id=0`）；不创建运行记录子菜单。
2. 智能选股查看必须同时满足 `intelligent_selection` 与 `selection.view`；写操作还需各自 `selection.create/edit/publish/activate/run/...`，激活继续执行本人模型所有权校验。`selection.debug` 继续只限超级管理员。菜单可见性与 API 采用同一门禁。
3. 种子迁移应在同一事务中，以 `INSERT OR IGNORE` 为**所有已有 `selection.view` 角色**补 `intelligent_selection`，包括将来可能存在的自定义角色；不得只按三个内置角色代码迁移，也不得因新菜单授予任何 `selection.*` 写动作。重复初始化应幂等。当前只读核查没有自定义角色，但测试需构造自定义角色覆盖该规则。
## 3. 5A 单次筛选的历史基线

`astock screen --help --json` 本次实际返回：位置参数 `codes`，`--codes`、`--dynamic`（说明列 `hot_sectors/liquidity/watchlist/balanced`）、`--pool`、`--allow-all-boards`、`--cyq`、`--limit`、`--json`。`cmd_screen` 同步调用 `DynamicUniverseEngine.generate_dynamic_universe()` 与 `StockScreener.screen()`；默认动态模式 `hot_sectors`，JSON 输出 `total_input/stage1_board/stage2_technical/stage3_scored/pool_mode_desc/results[]`。结果含 `code/name/price/change_pct/pe/sector/board_chg/avg_amount/scores/entry`，输出时移除 `klines/technical`。CLI 的 `--limit` 在 JSON 分支**不截断结果**，仅影响动态池规模。

现有 `POST /api/tasks` 可提交 `task_type=screen_5a`（或 `screener`），任务异步持久化到通用任务表，轮询 `GET /api/tasks/{task_id}`。其执行只转发 `params.limit` 和 `params.dynamic_mode` 到 `_sync_astock_screen_5a()`，封装结果为 `mode/rationale/total_screened/selected_count/top_stocks[]`。其中 `top_stocks[].total_score/board/rating` 从筛选结果顶层取值，而真实分数位于 `scores`、板块字段为 `sector`，因此这些字段可能为空。没有固定快照 ID、逐数据源水位或独立的策略运行身份。`StockScreener` 在无行情或无板块数据时可能返回空结果和零计数，任务包装层会将没有错误 `status` 的返回标为完成；现状不能把这种完成态当作成功筛选。

## 4. `quant` 文案编译路径与现状

- 系统配置的 `/api/models/roles` 读取 `llm_model_roles`，`/api/models/providers` 返回脱敏 Provider 投影；服务端 `get_model_roles()` 只取角色映射，`LLMProviderFactory.get_provider(role="quant")` 再按 Provider 状态校验。文案调用未要求 `tools` 能力，结构化 JSON 仅在回包后校验；显式 `quant` 绑定没有有效 `provider_id` 时工厂仍可能走通用模型查找/环境回退，F2 应改为量化角色失败关闭。隔离配置验证见第 6 节，不查询生产密钥。
- 弹窗 `web/js/selection-models/text_draft.js` 显示“LLM 模型标识”输入并向 `POST /api/selection-models/drafts/from-text` 发送可选 `model`。请求 Schema 允许该字段；`compile_text_with_llm()` 在提供 `model` 时改用显式模型并绕开 `quant` 角色绑定。F2 应拒绝 `mode=llm` 的单次覆盖，并处理旧调用兼容错误。
- 目前 `compile_llm_draft()` 固定构造单个 `post_close` 阶段，日程为 `15:35-23:59`，`missing_data_policy=reject`；无法忠实表达跨阶段或复杂布尔关系。该日程是阶段窗口，不是数据已齐备的证明；收盘执行仍须通过 `base_calendar/daily_kline/valuation` 水位及全市场覆盖门禁。

## 5. F1/F2 交接缺口

1. 侧栏旧入口和工作台仍同页，模型列表/运行列表混合类型；最近运行没有服务端类型过滤和准确总数。
2. 模型 API 缺独立菜单查看门禁。
3. 文案可覆盖 `quant`，当前仅生成单个收盘阶段；跨日阶段、字段目录及完整语义覆盖留待 F2。

## 6. 本次隔离运行证据

| 检查 | 本次结果 | 边界 |
|---|---|---|
| `git rev-parse HEAD`、`git status --porcelain=v1` | `179ad386aee0c53ca60210d262b298400f73f792`；取证前工作树干净 | 未读取用户模型 |
| `./bin/astock.ps1 screen --help --json` | 正常返回第 3 节所列参数 | 仅帮助输出，没有触发行情请求 |
| 角色 SQLite `mode=ro` 查询 | 3 个内置角色与第 2 节矩阵一致；自定义角色 0 | 只读菜单绑定，未读取用户或 Provider 凭据 |
| `.venv/Scripts/python.exe -m pytest -m core` | 本次 `244 passed, 354 deselected`，45.85s | 隔离临时测试库；P0 无失败 |
| `temp/f0_isolated_probe.py`（一次性脚本，执行后清理） | 隔离管理员创建 `funnel` 草稿并保存为修订 2；校验 2 阶段，发布 v1，显式选 v1 手工运行 `COMPLETED`；`stage_1/stage_2` 各查询到 1 条候选，运行和阶段 ID 对齐；`researcher` 列表 HTTP 200、创建 HTTP 403 | 进程内 TestClient；临时 SQLite、模型、缓存、日志、配置；输入来源 `request_records`，`data_snapshot_id=null`，只证明 API 与阶段轨迹闭环，不证明真实行情水位或正式信号 |
| 同次隔离 `quant` 配置 | `/api/models/roles` 指向假 Provider；启用时工厂解析 `f0-local-model`；未声明工具能力返回 `LLM_CAPABILITY_UNSUPPORTED`；停用后返回 `LLM_NOT_CONFIGURED` | 假本地地址，不发起 LLM 请求；不读取生产 Provider 或密钥 |
| 清理检查 | 探针报告 `temp_cleaned=true`；临时模型仅存在于探针目录 | 首次探针因预期候选响应含 `model_id` 而断言失败；接口实际以 `run_id` 关联，修正探针后成功，产品代码未改 |

F0 所要求的隔离取证已完成。项目 `AGENTS.md` 的测试分层规约仍要求定向 P1、全量、浏览器 E2E 与真实外网验证先获人工确认；本次未运行这些测试档位，也未调用真实行情或 LLM。后续阶段的实现验收应独立安排相应门禁。
