# A-Stock Agents 代码审查报告（2026-09-10）

> 审查范围：`scripts/server/`（config、app、db、llm/ 全部 provider 与工厂、agent/react_runner、agent/tools、api/ 全部 8 文件、tasks/task_manager）、`web/js/`（api.js、app.js、components/astock.js、ui_engine.js、charts.js）、`scripts/core/governance/`（skill_registry、auditor、models）、`scripts/core/` 抽查（config.py、strategy/execution_action_engine.py、models/multi_dim_model.py、strategy/pool_schema.py）
> 审查方法：3 路并行子代理逐文件审查 + 主线程交叉复核全部高危项 + 回归测试取证
> 审查基准：[docs/guidelines/code-review.md](../guidelines/code-review.md) 8 项强制检查项 + AGENTS.md 实战交易三原则
> 严重度分级：🔴 高（伪造成功/绕过安全门/资金决策失真）、🟡 中（结果失真/分层违规/健壮性）、🟢 低（规范与可维护性）

## 测试证据

- `python -m pytest tests/test_production_authenticity.py tests/test_capability_truthfulness.py -q` → **5 passed**
- `node tests/test_frontend_production_safety.js` → **PASS**

⚠️ 测试全绿与本报告 H4/H5 违规并存，说明真实性门禁的扫描模式存在盲区（见整改建议第 5 条）。

---

## 一、结论总览

| 检查项 | 结论 |
|---|---|
| 1. 生产真实性 | ⚠️ 后端基本通过；前端 4 处违规（含活代码） |
| 2. Skill 单一入口 | ❌ 双路径绕过治理（聊天主路径 + 后台任务路径） |
| 3. 分层方向 | ⚠️ core 业务算法归属正确，但 core.governance 反向依赖 server（5 处） |
| 4. 凭据边界 | ✅ 通过（遗留 SSRF DNS 盲区、明文存储 2 项中危） |
| 5. 失败语义 | ✅ 后端通过；前端会话列表失败态违规 |
| 6-7. 测试与证据 | ✅ 已附命令与计数 |
| 8. 用户数据保护 | ✅ 无静默删除；股池 CSV 非原子写入 1 项中危 |

---

## 二、🔴 高危（5 项，均经主线程亲自复核确认）

### H1. 聊天主路径完全绕过治理 Skill 入口

- 位置：`scripts/server/agent/react_runner.py:198`
- 注册表仅用于生成工具 schema（react_runner.py:123-124），实际执行直接调 `execute_tool`。由此绕过 `scripts/core/governance/skill_registry.py:368-512` 的四道防线：
  1. **enabled 检查被绕过**（skill_registry.py:392）：被治理控制台停用的技能，只要 LLM 从历史上下文拿到旧工具名仍会被 TOOL_MAP（tools.py:452-494）直接执行；
  2. **SIMULATION 安全门被绕过**（skill_registry.py:401）：`astock-trade-paper` 要求 `require_confirmation=True`，但聊天路径调 `_sync_astock_trade_paper`（tools.py:323-346）可直接下单/撤单，无二次确认拦截；
  3. **超时熔断被绕过**（skill_registry.py:446）：`execute_tool`（tools.py:505）的 `run_in_executor` 无 timeout，慢工具挂起整个 ReAct 循环；
  4. **审计被绕过**：聊天路径技能调用不入审计，`/api/skills/audit/stats` 严重失真。
- 建议：`react_runner.py:198` 改为调用 `registry.execute_skill()`，确认状态经前端确认事件回传。

### H2. 后台任务默认自动确认，架空 require_confirmation

- 位置：`scripts/server/tasks/task_manager.py:292`
- `confirmed=params.get("confirmed", True)` —— 任何走后台任务触发的 `astock-trade-paper`（SIMULATION 级）都会自动通过人工确认门禁。
- 建议：默认值改为 `False`。

### H3. 保本价失败后用粗糙兜底公式渲染成功

- 位置：`scripts/server/agent/tools.py:227-229`
- core 的 `ExecutionActionEngine.generate_action` 未产出保本价时，server 层用 `math.ceil(eff_cost * 1.001 * 100) / 100.0`（0.1% 摩擦近似）兜底，仍以 success 返回并流入 RiskCardEvent。
- 对小成交额仓位（如 1000 元成交额，最低 5 元佣金占 0.5% > 0.1%），该兜底价会**低估保本价**，方向性危险，违反检查项 1「失败后不得渲染成功」与 AGENTS.md 实战三原则第一条（印花税 0.05% + 佣金万 2.5 最低 5 元 + 过户费精算、强制向上进位）。
- 且兜底费率未走 `get_market_config()`（core/config.py:312-324），用户改佣金配置后兜底进一步失真；同函数 tools.py:231-233 三级止损兜底百分比（`eff_cost * 0.97 / 0.95 / 0.92`）亦硬编码于 server 层。
- 建议：改为返回 `ANALYSIS_INCOMPLETE` error，费率一律走 core 配置。

### H4. 前端编造数值仍存活

- `web/js/charts.js:517,527`：净值曲线图例硬编码 `"策略净值 (当前 +34.28%)"`、`"沪深300 (+8.65%)"`，无论后端传入什么净值数据都绘制这两个数，与真实 strategyData 完全脱钩。
- `web/js/app.js:245`：等待后端期间即展示「持仓综合评分88分」summary（会渲染进 AI 消息头部）；同模式 app.js:2652/2657/2761 的「成功调度量化计算流水线」「>85分龙头池」「完成截面因子处理」均属前置断言成功。
- `web/js/app.js:449`：向 AI 提问框注入硬编码「最大回撤(-8.24%)与夏普比率(1.84)」，污染模型输入；app.js:445 硬编码「突破 3,450 点」。
- `web/js/components/astock.js:102-110`：仅有 benchmark 名称时输出固定结论「28日均线多头共振」+「放量突破」徽章；:121 副标题硬编码「零轴下方水下二次金叉验底形态」；:182 属性缺失时兜底编造标的「300750 宁德时代」。
- 建议：全部改为由真实数据计算或渲染 unavailable 空状态。

### H5. 前端静态假会话 + 定时假成功

- `web/js/app.js:53-75`：20 条编造历史会话（HistoricalSessions）DOMContentLoaded 即渲染；`initSessionsFromBackend`（app.js:700-721）仅在**后端成功返回非空**时才替换（:705），catch 分支只 `console.warn`（:718-720）——后端不可用时假会话作为「用户历史」持续展示且可点击。
- `web/js/app.js:106-130`：无限滚动用 `setTimeout` 500ms 后弹「已成功自动加载历史会话」，数据源为静态数组而非任何存储，属典型定时假成功。
- 建议：后端失败时渲染空/不可用状态；删除静态数组与假成功提示。

---

## 三、🟡 中危

### 生产真实性 / 失败语义

| 位置 | 问题 |
|---|---|
| `scripts/server/agent/tools.py:380-387` | `_sync_astock_strategy_tuige` 返回硬编码交易口诀且 `status:"success"`，未按规范标为未实现 |
| `tools.py:422-432` | `_sync_astock_knowledge_tips` 固定 3 条 tips 以 success 返回 |
| `tools.py:439-447` | `_sync_astock_meta_routing` 恒返回 `recommended_model:"flash"` |
| `tools.py:331` | `core.paper_trading.account_manager` 模块不存在，import 永远抛异常被吞后返回 unavailable——「靠异常实现的未实现」，SIMULATION 风控等级无法真正行使 |
| `web/js/app.js:1329-1347` | 死代码假 K 线生成器 `generateKlines`（Math.random 合成、锚定硬编码日期），全仓无调用点，应删除 |
| `web/js/app.js:2655-2783` | 休眠假研报模板（编造选股 94.2/91.8 分、保本价 ¥320.26、DIF 极值 -4.20/-8.60、IC 0.068/IR 1.45 等）；当前经 `streamAIResponse` 不可达，但一次重构即复活，应删除 |
| `app.js:1239,1264,872` | 强制 `+` 号格式化（`+${total_return}%`），后端返回负值时显示虚假「跑赢」 |
| `app.js:1384-1448` | @ 操作符静态股票池：池归属（isHolding/holdingRatio）永远来自硬编码配置，与真实 `pool list` 脱钩 |
| `web/js/ui_engine.js:205-419` | 水合管线无 onError/abort 失败终态，骨架将永久悬挂；且 mountSkeleton/hydrate* 全仓无调用方，属休眠代码 |

### 分层方向

| 位置 | 问题 |
|---|---|
| `core/governance/skill_registry.py:236,291,438`、`core/governance/auditor.py:37,62` | core → server 反向 import 共 5 处（`server.db` 的 skill 持久化、`server.agent.tools.execute_tool`），形成 `server.api.skills → core.governance → server.*` 循环依赖，靠函数内延迟 import 掩盖；审计持久化失败时静默降级内存（auditor.py:47-57），审计记录可丢失。建议依赖注入（protocol/回调注册） |
| `tools.py:390-407` | `_sync_astock_strategy_macd` 在 server 层简化重实现 MACD 形态分类（无底背离/波谷对比），与 core 引擎口径不一致，应下沉 core |
| `skill_registry.py:434-440` | `register_handler()` 全仓零调用，17 项技能无一注册正式 handler，治理执行实为 core→server 反向委托，「单一入口」仅形式存在 |
| `task_manager.py:254-274` | 跨模块引用 `server.agent.tools` 下划线私有函数（`_sync_astock_screen_5a` 等） |

### 凭据 / 安全

| 位置 | 问题 |
|---|---|
| `server/api/models_mgmt.py:101-104` | SSRF 校验只查 IP 字面量不做 DNS 解析——解析到内网/169.254.169.254 的公网域名可通过（DNS rebinding 同理）。`follow_redirects=False` 已封死重定向，剩余为恶意域名直连内网。建议解析后复检 IP |
| `server/config.py:66-67` | 仅配置 `ANTHROPIC_API_KEY` 时 `default_model=""`，空串无法命中 factory fallback 链，Anthropic 用户默认路由失效（最终 raise LLM_MODEL_UNAVAILABLE） |
| `server/db.py:120` | api_key 明文存 SQLite（output/cache/chats.db），无加密/掩码 |
| `server/api/skills.py:50-62` | PATCH 无鉴权即可停用技能或关闭 `require_confirmation`，与安全门禁设计意图不符（本地单机风险有限） |

### 用户数据保护

| 位置 | 问题 |
|---|---|
| `core/strategy/pool_schema.py:177-183`、`pool_manager.py:45-68` | 股池 CSV（用户持仓 positions.csv 等）以 `"w"` 非原子覆写，写入中途崩溃即损坏；已定义的 BACKUPS_DIR（core/config.py:200）日常从不使用。建议临时文件 + rename 原子化 |
| `server/config.py:16` | 会话库与技能审计记录放 `output/cache/chats.db`——任何「清缓存」逻辑将连带删除用户会话与审计记录。建议迁移至专设 state/ 目录 |

---

## 四、🟢 低危（摘录）

- `server/llm/__init__.py:9,21`：MockLLMProvider 公开导出，可绕过工厂门禁（当前无其他调用点，防御性问题）。
- `server/llm/factory.py:80`：`"11434" in b_url or b_url.endswith("/v1")` 启发式覆盖面过宽；:158 `"text-embedding"` 前缀会命中聊天分支；:63 死代码。
- `server/db.py:777`：`int(data.get("timeout_seconds", 60))` 直调层无防护。
- `react_runner.py:272` / `openai_provider.py:64-65`：异常原文（可能含上游响应体）写入日志，存在日志膨胀/间接泄漏面。
- `server/api/market_data.py:64-72`：`get_portfolio_overview` 无 try/except，异常返回裸 500 与 `_unavailable` 风格不一致。
- `web/js/api.js:138-151`：SSE terminal 置位后未 `reader.cancel()`，轻微资源泄漏。
- `web/js/app.js:3663-3683`：roles 后端保存失败静默降级 localStorage 仍弹「已成功保存」；:4596 策略开关仅本地 toast 不持久化。
- `web/js/components/astock.js:38-39,63-64`：MarketRadar 对畸形 props 无存在性校验。
- `report_generator.py:211`：同日重跑覆盖同名报告，建议时间戳加时分秒。
- `core/models/multi_dim_model.py:53-57,64-69`：`except ImportError` 平面回退 import 历史遗留。

---

## 五、✅ 通过项（要点）

- **Mock 门禁严密**：生产模式禁 Mock（factory.py:136-141 直接抛 `LLMReadinessError`）；`A_STOCK_RUNTIME_MODE` 默认 production（server/config.py:84）；default_model 推断链只看真实环境变量密钥；health API 仅测试模式暴露 mock（health.py:42-43）。
- **CORS 合规**：显式过滤 `*`（config.py:78）、默认仅 4 个 localhost 来源、`allow_credentials=False`（app.py:55）、headers 不含 Authorization、`Origin: null` 精确匹配不通过。
- **密钥投影合规**：`_public_provider` 剥离 api_key、按 `_SENSITIVE_HEADER_NAMES` 过滤 custom_headers、仅补 `has_api_key`（models_mgmt.py:58-78）；连接测试只收 `provider_id`；浏览器 localStorage 无密钥（仅 `astock_model_roles`），旧 `astock_llm_providers` 主动清除（app.js:3014,3659）；api_key 只进内存、保存后输入框清空。
- **出站 URL 校验**：拒绝非 HTTP(S)、userinfo、云 metadata 主机、link-local/multicast/reserved/非环回私有 IP；`follow_redirects=False` + timeout 限 1-60s。
- **失败语义正确（后端）**：market_data 未接通端点全部 503 unavailable（market_data.py:27-36）；空池/无持仓/监控未运行返回真实空状态并带 `source`/`as_of`；SSE 门禁失败仅发单个 typed error 无 success done（react_runner.py:64-74）；RiskCard 仅 `status=="success"` 才发出（react_runner.py:205）；token 计数仅取自 provider 真实 usage chunk；task_manager 失败/超时语义正确。
- **历史伪造点已清除**：全目录 grep `0.065`/`52.*48`/`百万`/`fixed`/`simulated` 等模式无命中。
- **前端传输层**：`api.js` `_fetchJSON` 严格抛错无数据兜底；SSE `terminal` 机制保证 onError/onDone 恰好一次；聊天打字机完全由真实 SSE delta 驱动，无 setTimeout 合成文本；工作台五大加载器后端单向取数、catch 整体替换为 unavailable；技能测试严格区分四种状态。
- **core 层归属正确**：core/config.py SSOT（市场前缀、费率常量、输出目录隔离、`init_output_templates` 仅文件缺失时初始化不覆盖用户 CSV）；execution_action_engine 业务算法在 core 且无 server 依赖。
- **升级安全**：tools/update.py 升级前强制快照备份、显式跳过 `output/user_data/backups`、Zip-Slip 防护、临时目录清理只删 `cache/_update_temp`。
- **清单一致**：config/skills_manifest.json 17 项技能与 SKILL_SCHEMAS 一一对应；API 控制台测试路径完整走 `registry.execute_skill`。

---

## 六、整改优先级建议

1. **P0-A（资金安全）**：H3 保本价兜底改为返回 `ANALYSIS_INCOMPLETE` error；费率走 `get_market_config()`。
2. **P0-B（治理）**：`react_runner.py:198` 改走 `registry.execute_skill()`（确认状态经前端事件回传）；`task_manager.py:292` 默认 `confirmed=False`。
3. **P0-C（前端真实性）**：删除 charts.js 假图例、app.js 假会话/定时假成功/245 与 449 行编造数值、astock.js 固定结论，改由数据计算。
4. **P1**：tuige/knowledge-tips/meta-routing 伪 success → unavailable；依赖注入消除 core→server 反向依赖；SSRF DNS 解析后复检；Anthropic 默认模型路由修复。
5. **P1-测试**：扩充 `test_production_authenticity.py` 扫描模式覆盖本轮盲区（当前 5 passed 与 H4/H5 并存说明门禁模式过窄）。
6. **P2**：股池 CSV 原子写入 + 备份；chats.db 迁出 cache 目录；PATCH 鉴权；死代码清理（generateKlines、休眠假研报、ui_engine 水合管线、MockLLMProvider 导出）。

---

## 附：审查线程分工

| 线程 | 范围 | 状态 |
|---|---|---|
| 子代理（server 层） | server/ 真实性、失败语义、凭据边界 | ✅ 完成 |
| 子代理（web 前端） | web/js/ 5 文件生产安全 | ✅ 完成 |
| 子代理（治理与分层） | skill_registry、分层方向、用户数据保护 | ✅ 完成 |
| 主线程 | 高危项交叉复核（react_runner:198、tools.py:227-229、task_manager:292、app.js:53-75、charts.js:517-527）+ 回归测试取证 | ✅ 完成 |
