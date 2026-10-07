# A-Stock Agents 回归测试与质量保证指南

> 适用：工程核心开发、代码贡献者、测试与持续集成（CI）、以及在本工作区内代为执行测试的智能体
> **实施进度看板**：[`eng-runtime-and-test-remediation-plan.md`](../../specs/engineering/eng-runtime-and-test-remediation-plan.md) (`SPEC-ENG-001`)
> **分层执行入口**：[`tests/conftest.py`](../../../tests/conftest.py)（档位表 + 共享基座） · [`tests/README.md`](../../../tests/README.md)

---

## 一、测试核心哲学

A-Stock Agents 作为涉及实盘模拟交易、选股量化与策略执行的高确定性系统，测试套件是保障系统正确性、安全性和稳定性的第一道防线。

### 规约一：功能修改，测试先行（Regression-First / TDD）

**每次功能修改、功能重构或新增特性前，必须先升级修改测试用例，用于项目功能回归测试。**

- **测试先行**：修改已有接口或增加业务逻辑时，必须先在对应模块的领域回归测试套件中更新预期输入输出断言与异常分支防护。
- **红灯到绿灯**：先观察用例在旧逻辑下失败（Red），再实现新逻辑使测试全部通过（Green）。
- **零回归交付**：交付前必须通过 **P0 核心门禁**（见第三章），并按第三章的确认门决定是否扩展到全量。

### 规约二：临时优化用例生命周期规约（Ephemeral Fix Tests Rule）

**针对某次优化的测试用例仅作为临时用例验证功能后便删除。**

- **临时用例定位**：在代码审查、线上排障、性能分析或单次微调时，临时编写的排查用例属于「探索性临时验证代码」。
- **即测即删要求**：
  1. 临时排查用例应当编写在 `scratch/` 目录下或以临时脚本执行，在验证当前优化生效后，**必须立即删除**。
  2. 严禁以临时缺陷编号或任务名（例如 `test_p0_fixes.py`、`test_p1_fixes.py`）作为文件名永久堆积在 `tests/` 根目录。
  3. 若该次优化沉淀出了通用的边界测试、契约防线或核心回归用例，必须将断言提炼整合至对应的**标准领域测试套件**中。
  4. 严禁把中间产物写入 `output/`（用户交付物唯一落盘区）；一次性验证脚本落 `temp/` 并在结束时清理。

### 规约三：断言必须"必然执行"（Anti-Vacuous-Assertion Rule）

**一个在特定环境下会被整体跳过的断言，等于没有断言。**

- 严禁 `if 条件: assert ...` 形式——条件不成立时用例静默通过，却在看板上记为"绿"。
- 正确写法二选一：
  1. **构造前提**：用 fixture / monkeypatch 把条件强制成所需状态，再无条件断言；
  2. **显式跳过**：条件确实不可控时 `pytest.skip("原因")`，让"未验证"在报告里可见。

---

## 二、测试套件分层体系（物理结构）

```
tests/
├── conftest.py          # ★ 档位归属表 + 共享基座（鉴权/隔离/临时库），分层策略唯一改动点
├── README.md            # 目录级速查与执行入口
├── core/        (17 文件 / 182 用例)  # 量化底座：装配、漏斗、指标、模型、撮合、策略、同步
├── server/      (17 文件 / 153 用例)  # 服务端：REST API、会话与记忆、LLM 就绪、数据同步控制台
├── governance/  (10 文件 /  91 用例)  # 架构与合规门禁：解耦、真实性、安全审计、技能契约
└── frontend/    (29 文件 / Node.js)   # 前端 DOM 与交互仿真，不经 pytest 收集，单独 `node` 执行

.agents/skills/*/scripts/test_*.py     # 技能自带脚本级自测（2 文件），由 testpaths 一并收集
```

> 用例总数 **430**（`core/` + `server/` + `governance/` + 技能脚本）。目录分层描述"测什么"，
> 与下述档位分层（"多重要、多快"）是两个正交维度。

---

## 三、档位分层与执行策略（核心优先 · 扩展需确认）

### 3.1 档位模型

档位**不靠散落装饰器**，而是在 [`tests/conftest.py`](../../../tests/conftest.py) 的三张表里按文件集中声明，收集期由 `pytest_collection_modifyitems` 自动补齐：

| 表 | 作用 | 键粒度 |
| :--- | :--- | :--- |
| `_TIER_BY_PATH` | 优先级归档 `core` / `p1` / `p2`（互斥全覆盖） | 文件 |
| `_TAGS_BY_PATH` | 能力标签 `slow` / `network` / `subprocess` / `e2e` / `live` | 文件 |
| `_OVERRIDE_TAGS` | 精准点名个别用例（键为 pytest `nodeid`，非 `item.name`） | 单用例 |

| 档位 | 用例数 | 判定标准 |
| :--- | ---: | :--- |
| **`core`** | **132** | **P0 契约门禁**：错了会直接产出假结论或造成资金/安全后果——数据装配与水位门禁、漏斗规则、技术指标、行情字段契约与费率 SSOT、落盘与零假数据、撮合与 T+1、税费保本与三级止损、真实性红线、XSS/Zip Slip、生产禁回落 mock |
| `p1` | 259 | 重要回归：服务端 REST 契约、设置持久化与接线披露、18 项技能契约、治理与质量门禁 |
| `p2` | 39 | 补充边界：文档真实性、注册表辅助路径、自定义输出目录 |

| 标签 | 用例数 | 含义 |
| :--- | ---: | :--- |
| `slow` | 94 | 单用例 > 1s（子进程冷启动、全市场扫描、完整辩论流水线） |
| `network` | 35 | 触达真实外网（行情降级重试、实时现价批量） |
| `subprocess` | 10 | 以子进程执行 CLI/脚本的集成用例 |
| `e2e` | 26 | 端到端链路（装配 → 规则 → 快照落盘） |
| `live` | 18 | 需预先启动真实服务并显式开启 `A_STOCK_RUN_LIVE_E2E=1` 与 `A_STOCK_SERVER_TOKEN` |

> `--strict-markers` 已启用：拼错的标记直接报错，不会被静默忽略。

### 3.2 执行策略：先必要，后扩展，扩展需人工确认

**默认只跑 P0 核心门禁。任何超出核心的执行，都必须先确认再评估。**

| 顺序 | 层级 | 命令 | 耗时 | 执行前提 |
| :--- | :--- | :--- | ---: | :--- |
| ① | **P0 核心（必跑）** | `pytest -m core` | ~13s | 任何代码/测试改动后**无条件先跑**，作为唯一自动门禁 |
| ② | 核心离线子集（极速反馈） | `pytest -m "core and not slow and not network and not subprocess"` | ~12s | ①失败后定位时可自主使用 |
| ③ | 核心 + 重要回归 | `pytest -m "core or p1"` | 介于 ① 与 ④ 之间 | **需人工确认**后执行 |
| ④ | 离线全量 | `pytest -m "not network"` | ~64s | **需人工确认**后执行 |
| ⑤ | 全量串行 | `pytest` | ~68s | **需人工确认**后执行 |
| ⑥ | 全量并行 | `pytest -n 4` | ~40s | **需人工确认**后执行（需 `pytest-xdist`） |
| ⑦ | 含外网 | `pytest -m network` | 视网络 | **需人工确认**，且须先告知会触达真实行情源 |
| ⑧ | 端到端真实服务 | `A_STOCK_RUN_LIVE_E2E=1 pytest -m live` | 视环境 | **需人工确认**，须先启动已配置的服务 |

**对代为执行测试的智能体的硬约束：**

1. **禁止默认全量**：完成改动后只执行 ①；不得把 `pytest`（全量）、`pytest -n X`、`pytest -m "core or p1"` 当作默认动作。
2. **必须先征询再扩展**：需要跑 ③~⑧ 时，先说明「为什么核心门禁不足以覆盖本次改动」「预计耗时」「是否会触网/写盘」，取得确认后才执行。
3. **核心门禁绿 ≠ 可以交付**：若改动落在 `p1` 覆盖面（服务端 API、设置接线、技能契约），必须在建议里明确指出"建议追加执行 ③"，把决策权交回用户，而非自行跳过或自行全跑。
4. **失败即止**：① 出现失败时立刻停止并报告，不得用"全量里别的用例也挂了"来稀释定位。

### 3.3 各档位归属如何变更

- **新增测试文件**：在 `_TIER_BY_PATH` 登记档位（未登记默认落 `p2`）；若耗外网/慢，同步登记 `_TAGS_BY_PATH`。
- **个别用例需降级/点名**：写进 `_OVERRIDE_TAGS`，键用 `文件::类::用例` 形式的 `nodeid`。
- **判档口径**：断言假数据、资金/安全、实盘动作单正确性 → `core`；接口契约与配置生效链路 → `p1`；文案、清单、辅助路径 → `p2`。

---

## 四、用例编写硬性规范

以下每一条都对应一次真实缺陷整改，**新增用例必须遵守，Review 时逐条对照**。

### 4.1 严禁同文件重复函数名（静默覆盖）

Python 同名 `def` 后者覆盖前者，前者**永远不会执行**，而收集数看起来正常。
> 曾发现 `tests/server/test_data_sync_settings.py` 有 2 个用例被逐字节重复定义，46 行死代码。

自查：`grep -c "^def test_x" file` 或对文件做函数名去重统计。

### 4.2 HTTP 用例一律走 conftest 基座，禁止裸建 TestClient

`/api/*` 中间件默认要求**有效用户会话**（fail-closed，不存在"单机开发免鉴权"旁路）。
不带凭证自建 `TestClient(app)` 会恒得 401，于是"403 越权防护"一类断言**从未被真正验证过**。

| 需求 | 必须使用 |
| :--- | :--- |
| 已登录访问 | `client`（已注入会话凭证，已进入 lifespan） |
| 断言"未登录被拒" | `anon_client` |
| 需要原始 app | `app`（会话级单例，勿再 `create_app()`） |
| 凭证须签在别的库 | 参照 `test_session_memory.py`：对目标 `db_path` 单独 `create_auth_token` |

### 4.3 严禁写用户真实目录

`output/pools/*.csv`、`output/reports/`、`local/market_data/`、`cache/` 都是用户私有资产或生产数据区。

| 场景 | 做法 |
| :--- | :--- |
| 读写股票池 / 持仓 / 断言"池为空" | 声明 `isolated_user_pools` fixture（临时**空池**，表头来自 `pool_schema` SSOT） |
| 建 SQLite 库 | `tmp_path`；`unittest.TestCase` 用 `tempfile.mkdtemp()` + `addCleanup` |
| 临时解压/中间产物 | `temp/`，用例内自行清理 |

> 注意：`init_output_templates()` 会把 `.example` 的**示例数据行**（600519 贵州茅台）一并复制进
> `positions.csv`，使"空池"分支根本无法触发。因此 `isolated_user_pools` 刻意只写表头。

### 4.4 外网、DNS、连通性探测必须桩化

真实网络会让用例**随环境漂移**且**间歇性失败**。必须桩在正确的接缝上：

- 行情取数：`DataBridge.get_realtime_quote` / `tencent_kline` / `get_kline_robust`
- URL 探测：`urllib.request.urlopen`
- DNS：`socket.getaddrinfo`（SSRF 守卫在发请求前做真实解析，虚构域名必 400）
  - **桩 IP 必须用真公网段**（如 `93.184.216.34`）；`203.0.113.0/24`（TEST-NET-3）已被 Python
    `ipaddress` 归入 `is_private`，会被 SSRF 守卫"正确地"拒绝
- 确实要保留真实外网依赖时：打 `network` 标签，并在文档/命令里可被 `-m "not network"` 摘除

### 4.5 昂贵流水线只允许跑一次

被测对象若同时包含"流水线本体"与"分发路由"，应分开验证：

- 流水线：用 canned 输入喂**真实**装配逻辑，用 **module 级 fixture** 跑一次并复用
- 分发链路（`execute_tool`）：桩化 `TOOL_MAP` 条目即可，**无需重跑流水线**
  - ⚠️ `execute_tool` 取的是 `TOOL_MAP.get(name)` 持有的**函数对象引用**，
    因此必须 `monkeypatch.setitem(TOOL_MAP, ...)`；patch 模块级同名属性**不会生效**

### 4.6 等待用轮询，不用固定 sleep 堆叠

后台任务断言应按小步长轮询并带总超时（如 20ms 步进 + 10s deadline），
禁止 `time.sleep(0.1) × 10` 这类"白等"。

### 4.7 生产缺陷用 `xfail(strict=True)` 钉住，禁止改弱断言

当用例是对的、生产代码是错的：**不得**为了让看板变绿而删除/放宽断言，也不得改测试去迁就实现。

```python
@pytest.mark.xfail(strict=True, reason="生产缺陷（非用例问题）：<精确位置 + 现象 + 违反的规约>")
```

- `reason` 必须写清缺陷事实与代码位置，使其成为一份可执行的缺陷档案；
- `strict=True` 保证该缺陷一旦修好，会以 **XPASS 失败**强制提醒移除标记；
- 若生产契约已被**有意**推翻（如鉴权从"免鉴权兜底"改为"fail-closed"），则应更新用例期望，
  并在 docstring 里说明旧期望为何失效，避免下一个人再改回去。

---

## 五、共享基座 fixture 清单（`tests/conftest.py`）

| Fixture | 作用域 | 用途 |
| :--- | :--- | :--- |
| `app` | session | FastAPI 单例，避免每例重复装配 |
| `auth_headers` | session | 有效用户会话凭证（写入测试库 `A_STOCK_DB_PATH`） |
| `client` | function | 已鉴权且进入 lifespan 的 `TestClient` |
| `anon_client` | function | 无凭证 `TestClient`，专供鉴权拒绝类断言 |
| `isolated_user_pools` | function | 临时**空**股票池目录，改绑所有模块级池路径常量 |

进程级环境（在 import 前设定，测试与本机数据天然隔离）：
`A_STOCK_RUNTIME_MODE=test` · `A_STOCK_DEFAULT_MODEL=mock` · `A_STOCK_DB_PATH` · `A_STOCK_DATA_SYNC_SETTINGS_FILE`。

---

## 六、运行方式速查

```bash
# ① P0 核心门禁（默认动作，约 13s）
.venv/bin/python -m pytest -m core

# ② 核心离线极速（剔除子进程/外网/慢）
.venv/bin/python -m pytest -m "core and not slow and not network and not subprocess"

# 单文件 / 单用例
.venv/bin/python -m pytest tests/core/test_data_assembler.py -v
.venv/bin/python -m pytest "tests/core/test_stock_funnel.py::test_minute_timestamp_normalization_accepts_required_input_forms" -v

# 定位耗时来源
.venv/bin/python -m pytest -m core --durations=20

# ③~⑥ 扩展层：取得人工确认后执行（见 3.2）
.venv/bin/python -m pytest -m "core or p1"
.venv/bin/python -m pytest -m "not network"
.venv/bin/python -m pytest            # 全量串行
.venv/bin/python -m pytest -n 4       # 全量并行（需 pytest-xdist，已在 [test] extras 声明）

# 前端（Node.js，29 个独立脚本，不经 pytest 收集）
node tests/frontend/test_at_operator.js
for f in tests/frontend/*.js; do node "$f" || echo "FAIL $f"; done
```

---

## 七、贡献代码检查清单（Checklist）

在发起 PR 或推送提交前，逐条自检：

- [ ] 是否**先**在对应领域套件更新/新增用例，并观察到红灯？
- [ ] `pytest -m core` 是否全绿（132 passed）？
- [ ] 若改动落在 `p1` 覆盖面，是否已就"追加执行 ③/⑤"征询过确认？
- [ ] 新用例是否无外网强依赖？若确有，是否已打 `network` 标签？
- [ ] 是否无同文件重名 `def test_`？（4.1）
- [ ] HTTP 用例是否走 `client` / `anon_client`，而非裸建 TestClient？（4.2）
- [ ] 是否未写入 `output/`、`local/`、`cache/` 真实目录？（4.3）
- [ ] 是否存在 `if 条件: assert` 式空断言？（规约三）
- [ ] 面对生产缺陷，是否用 `xfail(strict=True)` 而非改弱断言？（4.7）
- [ ] 边界（0 值、空数据、越界、注入字符、非数值脏字段）是否覆盖？
- [ ] 新增文件是否已在 `_TIER_BY_PATH` 登记档位？

---

## 八、本次整改记录（2026-10-07）

### 8.1 结果对比

| 指标 | 整改前 | 整改后 |
| :--- | ---: | ---: |
| 全量耗时（串行） | 96.75s | 67.89s |
| 全量耗时（`-n 4` 并行） | 不可用（未装 xdist） | 39.47s |
| P0 核心门禁 | 无此概念 | **12.74s / 132 例** |
| 离线可跑全量 | 25 例必失败或依赖外网 | 64.24s / `not network` **395 passed** |
| 失败用例 | **29 failed** | **0 failed**（离线 395 passed · 35 deselected；0 skipped · 0 xfail） |
| 静默丢失的用例 | 2（重复定义覆盖） | 0 |
| 永不断言的用例 | 2（条件式空断言） | 0 |

### 8.2 单项耗时削减

| 用例 | 前 | 后 | 手法 |
| :--- | ---: | ---: | :--- |
| `test_custom_output_prioritization_and_isolation` | 22.99s | 5.45s | 13 次子进程 `ThreadPoolExecutor` 并行 + 落盘迁至临时目录 |
| `TestAgentTools::test_execute_action_plan_tool` | 4.80s | 0.01s | 固定行情输入（被测对象是保本价进位与三级止损算法） |
| `TestAgentTools::test_execute_quote_tool` | 4.80s | 0.01s | 同上，并消除条件式空断言 |
| `test_market_data_ping_endpoint` | 1.61s | 0.06s | 桩化 3 路外网探测；拆为"部分可达/全断网"两个确定场景 |
| `test_debate_and_quant_tools`（整文件） | 7.15s | 4.8s | 完整 7 分析师流水线由 2 遍降为 1 遍 module fixture 复用；分发用例改桩 `TOOL_MAP` |
| `test_fail_fast_and_code_validation`（整文件） | ~6.7s | <0.5s | 4 个真实网络重试用例合并为 1 个 `DataBridge` 空桩参数化（5 工具） |
| `test_data_sync_settings` 任务轮询 | 固定 100ms×10 | 20ms 步进 | 带总超时的快速轮询 |
| `test_data_sync.py`（26 例） | 真实 `local/` 建库 | 每例独立临时目录 | 离开 209MB 生产库同目录 |

### 8.3 由测试暴露的生产缺陷

**已修**

1. `core/data/data_layer.py` — `normalize_minute_timestamp` 不识别 `...Z` UTC 后缀（Python 3.10 的
   `fromisoformat` 不支持 `Z`，而项目声明 `requires-python >=3.9`）。
2. `core/reporting/report_generator.py` — 非数值 `price`（`'100<script>'`）直接 `float()` 使整份报告
   生成崩溃；同时 `<title>` / `<h1>` 使用了**未转义**的 `raw_name`/`raw_code`，是真实 XSS 注入点。
3. `tools/update.py` — 使用了未导入的 `TEMP_DIR`，导致 zip-slip 防护路径直接 `NameError`，防护形同虚设。
4. `server/api/market_data.py::GET /api/watchlist` **整端点捏造数据**（2026-10-07 修复）：池为空时回填
   8 只硬编码自选股，`price=0` 兜底 `328.56`、`change_pct` 兜底 `2.77`、`net_inflow` 写死 `+1.28亿`，
   `active_detail` 更写死成交额/行业/PE/PB/均线/资金流/北向/主力持仓全套画像——违反《零虚假数据原则》。
   现改为：空池如实 `status=empty` + `source=config/stock_pools.yaml` + 空数组；行情缺失字段一律 `None`
   由前端显示 `--`；无真实来源的口径（行业/概念/PB/52 周/MA/资金流/北向/主力）不再伪造，取不到现价时
   `active_stock_detail=None`，让 Hero 卡走"数据源不可用"而不是伪装有效盘口。
   用例：`tests/server/test_market_data_api.py::test_empty_watchlist_is_a_sourced_empty_state`
5. `server/app.py` 鉴权中间件 — **静态 API Token（`A_STOCK_SERVER_TOKEN`）完全失效**（2026-10-07 修复）：
   原实现在"携带 Bearer 但非有效会话 token"时直接 `return 401`，永不达静态分支；不带 `Authorization`
   又因 `if auth_header and ...` 恒假而同样 401 → 无浏览器会话的机器集成（cron/CLI/外部编排）已无任何
   合法入口，该分支为不可达死代码。现改为：会话校验不成立后，用 `hmac.compare_digest` 常数时间比对配置值，
   命中才放行；错误 token 仍 `401 invalid_token`、无凭证仍 `401 unauthorized`（兜底不等于旁路）。
   用例：`tests/governance/test_security_audit.py::test_static_api_token_still_authenticates_machine_integrations`

6. `server/api/market_data.py::GET /api/market/indices` **静态指数快照回落**（2026-10-07 修复）：
   实时源不可达时整块返回 `BASELINE_INDICES` 冻结快照（上证 3888.11 / 深证 13471.26 / 创业板 3322.04 /
   科创50 1553.39 及各自的写死 sparkline），却标 `status="success"` + `source="baseline_fallback"`，
   把某一天的收盘画面当成"今日实时行情"渲染；缺日K时还用 `[昨收, 今开, 最低, (今开+最高)/2, 最高, 现价]`
   拼一条假分时曲线；只取到 1~3 路真报价时又因 `len(indices) >= 4` 把真数据整片丢弃去换假快照。
   现改为：快照常量整体删除；有报价即交付（齐 4 路 `success`，不足则 `partial`），走势只在有真实日K时
   以"收盘序列末点换现价"生成，否则为空数组；不可达但有缓存 → `status="stale"` + `cached_as_of` +
   `cache_age_seconds`；两者皆无 → `unavailable` + 空数组。用例：
   `tests/server/test_market_data_api.py::test_market_indices_fails_closed_without_snapshot_fallback`
   等 5 例（含 `never_synthesizes_sparkline` / `appends_live_price_to_real_kline_series` /
   `reuses_cache_only_as_labelled_stale` / `marks_partial_instead_of_throwing_away_real_quotes`）。
7. `server/api/market_data.py::GET /api/portfolio/overview` **键名错配 + 演示资金收益**（2026-10-07 修复）：
   汇总读 `h["price"]` / `h["shares"]`，而 `position_manager` 的真实字段是 `cur_price` / `qty` /
   `market_value`，键名不匹配使持仓市值恒为 ¥0.00、仓位占比恒 0%；现金写死 `100000.0`，今日盈亏写死
   `+¥1,850.00 / 1.45%`，总收益 `18.5%`、年化 `22.3%`，空仓分支照样报"总资产 ¥100,000.00、可用现金 100%"。
   现改为：按真实字段汇总 `position_cost` / `position_market_value` / `floating_pnl(_pct)`；
   账户级现金台账与逐日净值序列本端点无数据源，`total_assets` / `available_cash` / `position_ratio` /
   `cash_ratio` / `today_pnl` / `total_return_pct` / `annualized_return_pct` / `risk_status` 一律 `None`
   并以 `account_state="not_wired"` 明示，`donut_data` 为空数组。用例：
   `tests/server/test_market_data_api.py::test_portfolio_overview_aggregates_real_position_fields`。

> 6 与 7 属"复查 4/5 时发现的同源残留"，同一轮内一并修掉：它们同样违反《零虚假数据原则》，
> 且 6 的旧用例 `test_market_indices_returns_live_or_fallback_data`（断言 `price > 3000`、
> `len(sparkline) > 0`）**本身就在给假数据上锁**，已删除并由 5 个桩化用例取代
> （顺带把该用例从 `network` 覆写表摘除，指数端点从此离线可验）。

### 8.4 测试自身的缺陷修复

| 问题 | 影响 | 处置 |
| :--- | :--- | :--- |
| 25 个 HTTP 用例不带会话凭证 | 恒 401；其中 10 个"403 越权防护"断言从未真正校验过 403 | 引入 conftest `client`/`anon_client`，删除各文件重复 `auth_headers`/`client` |
| `test_data_sync_settings.py` 2 个用例字节级重复定义 | 后者覆盖前者，46 行死代码，收集数虚高 | 删除重复定义 |
| `test_security_audit.py` 2 个 "Execution plan alias" 重复用例 | 与既有断言完全重叠 | 合并为参数化用例 |
| `test_auth_middleware_flow` 断言已过时的"免鉴权兜底" | 与现行 fail-closed 设计相反 | 按现行契约重写（匿名 401 / 伪造 401 / 有效会话 200 / 白名单 / OPTIONS） |
| `import_tdx` 用例写入用户真实自选池 | 污染私有数据 | 改用 `isolated_user_pools` 并断言落点 |
| `test_action_plan_missing_code_defensive_behavior` 读真实持仓 | 断言随本机数据漂移而 FAIL | 隔离空池后断言必然执行 |
| `test_live_server_e2e.py` 整文件与现行契约脱节 | ① 不带任何凭证，`/api/*` fail-closed 后除 `/api/health` 外全取 401 被 `status == 200` 判死；② 仍断言 `sentiment.score > 0`、`ranks.gainers` 非空、`analysis.sharpe_ratio > 0`、`monitor.is_monitoring is True`、`watchlist` 画像含数值 `capital_flow`——等于给已清除的伪造数据上锁；③ `urllib` 调用无 `from __future__ import annotations`，`dict \| None` 注解在 3.9 上直接 TypeError | 整体重写：以 `A_STOCK_SERVER_TOKEN` 走机器集成凭证（未设置即整组 skip，不假装通过），断言对齐 503/空态/stale/partial 契约，新增 `assert_no_fabricated_snapshot` 反向哨兵与"匿名必须 401"的门禁 |
| SSRF 用例依赖真实 DNS 与虚构域名 | 必 400 或随网络漂移 | 桩化 `getaddrinfo` 为公网 IP，仍完整走校验分支 |
| `_OVERRIDE_TAGS` 曾用 `item.name` 拼键 | 类内用例永不命中（`item.name` 不含类名） | 改用 `nodeid` 匹配 |

### 8.5 防复现哨兵（AST 级，2026-10-07 增）

`tests/governance/test_production_authenticity.py::test_market_projection_has_no_hardcoded_market_values`
把"零虚假数据"从**逐串黑名单**升级为**语法树判定**：

- 只解析 `Dict` 字面量中被列为"市场事实 / 账户事实"的键（`price`/`change_pct`/`sparkline`/
  `net_inflow`/`capital_flow`/`total_assets`/`today_pnl`/`annualized_return_pct` … 共 50 个）；
- 取值若展开后含**数字字面量**或**形似金额的字符串**（`328.56`、`'+1.28亿'`、`"+¥1,850.00"`、
  `[3941.39, …]`、`{"main_net": "+5.82亿"}`）即判失败；`None`、空容器、以及来自计算/数据源的
  表达式（`round(...)`、条件式、f-string、变量）一律放行；
- 因此缺陷档案里对历史假值的**文字叙述**写在 docstring/注释里不会误报，而把这些值重新写回
  响应装配代码会立刻红——旧黑名单"恰好不含任何一条"的漏检模式（见前端审计第 7 项）从此不再依赖
  人工记得补串。

自检口径：8 条历史伪造写法全部被抓出，7 条合法写法（含 `f"{x:.2f}万手" if x else None`、
`spark[:-1] + [price]`）全部放行。
