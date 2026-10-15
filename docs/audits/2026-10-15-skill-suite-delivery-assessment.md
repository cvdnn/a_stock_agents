# 技能总包交付形态与技能开发工程评估报告

- **评估日期**：2026-10-15
- **评估对象**：`a_stock_agents` 仓库当前的「技能总包发布」与「技能开发工程 + Release 交付」两种规划方案
- **评估方法**：只读静态审阅（目录结构、契约文件、打包链路、宿主适配、测试分层与覆盖取证），未运行测试、未构建 Release、未修改任何源码
- **权威定义 (SSOT)**：[技能总包、唯一来源与跨平台接入评估规范](../guidelines/engineering/skill-suite-portability-specification.md)
- **后续计划**：[技能交付闭环整改实施计划](../specs/engineering/eng-skill-suite-delivery-remediation-plan.md)

> 本报告为一次性审查留痕，**只增不改**。所有结论均给出文件路径证据；未实测项一律标注「未验证」，不以静态推断替代真机结论。

---

## 一、评估对象与前置约束

用户给定的两项规划方案：

1. 整个项目作为 skill 总包发布，兼容 AI 工具 **WorkBuddy / Hermes Desktop / Codex**；
2. 项目定位为 skill 技能开发工程，实现技能功能与测试策略算法，再发布 Release 给 AI 工具使用。

**关键前置约束（决定结论走向）**：项目以「在 AI 工具软件中注册为技能」的方式在 AIChat / AIWork 中使用，**不考虑** AI 工具软件内以项目 / 工作区 / 文件夹形式加载技能的用法。

即：仅存在「技能注册」一条接入路径，不存在「打开仓库当项目」的兜底模式。这一约束与 [skill-suite-portability-specification.md](../guidelines/engineering/skill-suite-portability-specification.md) 第 9-11 行「不再将 AI 工具打开本仓库作为工作区或项目后发现技能列为产品模式」一致。

---

## 二、总体结论

两种方案不是二选一，而是同一件事的两层：**方案 2 是工程骨架，方案 1 是交付形态**。

| 维度 | 方案 1：整个项目作为 skill 总包发布 | 方案 2：技能开发工程 + Release 交付 |
| :--- | :--- | :--- |
| 定位是否正确 | 是方案 2 的交付形态，不能独立成立 | 定位正确，且仓库已写成规范并落地骨架 |
| 当前完成度 | 约 40%（能产出候选 ZIP，三个宿主均无法原生识别） | 约 75%（目录 / 单一来源 / 数据根分流 / 归档纪律到位） |
| 阻断项 | S1–S7（详见第四节） | T1–T10（详见第五节） |

**核心判断**：

> 在「只走技能注册」的约束下，唯一可行路径是「方案 2 的工程定位 + 方案 1 收敛为『单一总入口技能 + 固定安装根 + 宿主引用注册』」，而非「把整个项目打成一个大 ZIP 交给三个宿主自动识别 20 个技能」。

代码自身已承认该结论：[common.py](../../tools/packaging/common.py) 生成的 `INSTALL.json` 内写有 `host_scan_status: "unverified"`、`native_import_verified: false`，并附 notice「Native host import and skill discovery require separate acceptance」。**因此当前对外不能宣称「兼容 WorkBuddy / Hermes / Codex」。**

---

## 三、现状盘点：已做对的部分（应保留的资产）

| # | 资产 | 证据 |
| :-: | :--- | :--- |
| A1 | **单一来源守住**：技能侧 `.py` 共 6890 行，`runtime/core` 49538 行，占比约 13.9%；其中 80 个为 33/34 行纯转发壳（`sys.path` 注入 + `from core.X import *` + `runpy` 兜底），零算法体 | `skill_bundle/skills/**/*.py`、`skill_bundle/runtime/core/**` |
| A2 | **转发壳有常驻门禁**：要求转发壳 ≥50 个且必含 SSOT 标记 | `tests/core/test_commands_suite.py`（`test_skills_forwarders_import_cleanly`） |
| A3 | **数据根分流设计正确**：以 `bundle.json` 的 `distribution` 字段区分开发态（仓库根）与 Release 态（OS 用户数据目录），显式 `A_STOCK_WORKSPACE_ROOT` 优先，三平台分支齐全 | [workspace.py](../../skill_bundle/runtime/core/workspace.py) `default_data_root` |
| A4 | **归档纪律严格**：仅遍历 `PACKAGE_ROOT`，排除 `.env*` / `config.yaml` / 符号链接 / `__pycache__`，后缀白名单，写 sha256，注入 `distribution=release` 且不回写源文件 | [common.py](../../tools/packaging/common.py) |
| A5 | **发布红线有唯一技术执行点**：`distribution != 'release'` 直接拒绝注册开发源码 | [host.py](../../tools/host_adapters/host.py) |
| A6 | **引用式注册而非拷贝**：幂等、防环、防覆盖物理目录、receipt 归属校验、卸载只删入口不删目标、Windows junction 回落、非 Windows 相对 symlink | [references.py](../../tools/host_adapters/references.py) |
| A7 | **业务正确性测试属优秀水平**：596 个测试函数 / 15160 行；P0 分层门禁（227 例 / 约 80s）；AST 级数值哨兵防写死行情；fail-closed 鉴权基座；`xfail(strict=True)` 缺陷档案制；9 个环境变量进程级隔离 | `tests/`、[testing-guide.md](../guidelines/engineering/testing-guide.md) |

---

## 四、方案 1 的结构性阻断问题

### S1【致命】归档根没有 SKILL.md，宿主无法识别为技能

ZIP 根仅有 `INSTALL.json` / `requirements.txt` / `LICENSE` / `host_adapters/` + 一层 `skill_bundle/`。三个宿主的原生导入模型基本是「一个技能 = 一个含 SKILL.md 的目录」，不会递归识别集合内 20 个技能。

规范第 74-76 行已自述「不能由『支持 ZIP/SKILL.md』推断会递归识别集合内全部技能」——当前产物正踩在该条上。

**证据**：[common.py](../../tools/packaging/common.py) `package_project` 归档结构；`INSTALL.json` 的 `skill_entries: 20` 为自声明元数据，非宿主扫描结果。

### S2【致命】共享 runtime 位于技能目录之外，与宿主管理单位冲突

宿主的管理单位是技能目录；而算法在 `skill_bundle/runtime/core`，技能在 `skill_bundle/skills/<id>`。一旦宿主把 `skills/<id>` 单独复制/移动进自管目录，转发壳「向上找 `bundle.json`」立即失效，**技能退化为空壳**。

这是规范第 62-68 行两难（「不要复制 19 份共享运行时」 vs 「宿主只支持单技能导入」）的正面冲突，**当前无解**。

### S3【高】Release 内没有 `bin/`，但 19 个专业技能 SKILL.md 全都指示调用它

`common.py` 只打包 `PACKAGE_ROOT`（即 `skill_bundle`），`bin/` 在包外。而以下文件均写有 `.\bin\astock.ps1` / `./bin/astock`：

- [astock-data-feed/SKILL.md](../../skill_bundle/skills/astock-data-feed/SKILL.md) 第 21-27 行
- [astock-platform-evaluate/SKILL.md](../../skill_bundle/skills/astock-platform-evaluate/SKILL.md) 第 21-28 行
- [astock-pool-dashboard/SKILL.md](../../skill_bundle/skills/astock-pool-dashboard/SKILL.md) 第 98-109 行
- 以及 `references/` 下多处（全仓共 19 处命中）

宿主侧照抄必失败。

**对照**：总入口写法是正确的——[a-stock-agents/SKILL.md](../../skill_bundle/skills/a-stock-agents/SKILL.md) 第 15 行写「Windows 调用 runtime/astock.ps1，macOS/Linux 调用 runtime/astock」。**19 个专业技能沿用了开发仓库口径，未同步。**

### S4【高】SKILL.md / references 大量隐含「CWD = 开发仓库根」

| 形态 | 实例 |
| :--- | :--- |
| 相对仓库根脚本路径 | `SKILL_DIR="skill_bundle/skills/astock-data-feed/scripts"`（`astock-data-feed/references/full-reference.md` 等） |
| cron 示例隐含仓库根 | `cd /path/to/a_stock_agents && ./bin/astock ...`（`astock-pool-dashboard/SKILL.md`） |
| 指向包外目录的链接 | `[selection-system-specification.md](../../../docs/guidelines/algorithm/...)`（位于 `astock-selection-model/SKILL.md` 第 72 行）——`docs/` 不入包，链接必断 |

安装态下代码根在宿主目录、数据根在 `%LOCALAPPDATA%`、CWD 由宿主决定，指令与链接双失效。

### S5【高】WorkBuddy 明确没有可用接入路径

[host.py](../../tools/host_adapters/host.py) 对 `workbuddy` 直接返回 `HOST_REFERENCE_SUPPORT_UNVERIFIED` 且 `copy_fallback: false`。三个目标宿主中**有一个是空的**；Hermes 为 `external_dirs`、Codex 为 `reference-only`，均仅为 `configured_target`，非「已验收」。

### S6【高】依赖声明碎片化 + Release 无依赖安装步骤

- `core` 硬依赖 `MyTT`（[fetch_technical.py](../../skill_bundle/runtime/core/data/fetch_technical.py) 第 44 行）与 `akshare-proxy-patch`，但其**唯一声明处是技能目录内的** [astock-data-feed/requirements.txt](../../skill_bundle/skills/astock-data-feed/requirements.txt)（20 行手写，`akshare>=1.18.0`）；
- `pyproject.toml` 的 `full` extra 为 `akshare>=1.12.0` 且**无 MyTT**，版本口径与技能清单冲突；
- Release 内并存两份互不同步的依赖清单；
- `INSTALL.json` **无任何依赖安装说明**，违反规范第 74 行「INSTALL.json 必须明确…依赖安装」；
- 启动器只找 `python3`，不校验版本、不装依赖；`setup.sh` 只运行 `doctor.py`。**宿主装完后由谁执行 pip install，链路是断的。**

### S7【中高】安装脚本污染宿主环境（2026-10-15 已整改）

原始问题已记录为历史快照（本段审计时态不覆盖原证据）：`astock-agent-debate/scripts/setup.sh` 曾以裸 `python3` 全局 pip install、联网 clone 外部仓库、将凭据写入 `temp/vendor/.env`、安装时执行外网/LLM 冒烟、固定父目录层数探测根路径，并残留旧技能 ID `ta-multi-agent-analysis`。

整改结果：脚本现为只读 doctor 自检辅助入口；只允许显式隔离解释器（`A_STOCK_PYTHON` / `VIRTUAL_ENV` / Bundle 外部 `.venv`），无解释器时 fail-closed；凭据只指引至 `local/settings/.env`；不再 clone、pip install 或执行 LLM 冒烟；使用 `bundle.json` 向上探测根目录。`SKILL.md` 相应删除过时外部安装步骤，新增静态门禁守卫。

---

## 五、方案 2 的工程侧问题（技能实现与测试策略）

### T1【致命】发布链路测试近乎为零

发布链路自动化门禁在 2026-10-15 评估时基本为零覆盖；此后已由 `tests/core/test_release_delivery_gate.py` 的 P0 常驻门禁覆盖 20 个 frontmatter、真实启动器、doctor/run_skill、`check_workspace_health` 直接调用、`package_project`、`skill_resource`、宿主注册红线、依赖 SSOT、三平台隔离解压与 doctor 冒烟。

评估时的风险推演仍保留为历史：zip 执行位丢失可能导致 Linux/macOS 解压后启动器不可执行；平台参数错可能导致归档缺少 host_adapters。

### T2【高】头号发布红线没有哨兵

[host.py](../../tools/host_adapters/host.py) 的「拒绝注册开发源」「`bundle.json` 缺失检查」「workbuddy 未验证分支」**全部 0 覆盖**。三个平台 shim 使用裸导入 `from host import main`，打包后被置于归档 `host_adapters/` 平级目录，宿主解压后能否 import 成功**无验证**。[project.py](../../tools/host_adapters/project.py)（已退役入口，必须拒绝调用）同样无哨兵。

### T3【高】`--json` 是智能体交互的唯一接口，却 0 断言

AGENTS.md 将「必须追加 `--json` 获取结构化数据」列为跨平台执行底座契约。`tests/` 下 `--json` 的 19 处命中**全部是 argv 字面量**，仅喂给 `parser.parse_args`；**没有一处执行后 `json.loads(stdout)` 校验 `status` / `data` / 错误体**。`astock skill list` 从未被执行。

另发现 [test_commands_suite.py](../../tests/core/test_commands_suite.py) 的 `expected_commands` **不含 `funnel` 与 `pattern`**，而 AGENTS.md 与 `test_skill_contracts.py` 均在使用这两组命令 → 被误删不会报警。

### T4【中高】SSOT 在 `assets/templates/` 存在监管盲区

[tencent_fields.py](../../skill_bundle/runtime/core/data/tencent_fields.py) 第 3-12 行自称「腾讯 L1 快照解析的单点真实源」，并写明「严禁在其他文件重复定义」，core 内 6 处已收敛；但技能目录内**仍有 9 处独立下标解析**：

`pool_audit.py`、`sandbox.py`、`monitor_watchdog.py`、`ta_entry_monitor.py`、`entry_monitor_hardcoded_ma20.py`、`monitor_limit_order.py`、`periodic_reminder.py`、`portfolio_review.py`（含技能内互相逐字符拷贝）。

现有门禁用 `"templates" not in p.parts` **显式豁免 templates** → 盲区。该文件头部已记录历史事故：「曾用一整套错位的下标，导致降级模式下把买一价当作 PE 输出」。

### T5【中高】`ta_entry_monitor` 双份且已分叉，活的是弱版本

| 项 | 公共实现（**活的**） | 技能副本（**孤儿**） |
| :--- | :--- | :--- |
| 路径 | `runtime/core/multi_agent/templates/ta_entry_monitor.py.template` | `skills/astock-agent-debate/assets/templates/ta_entry_monitor.py` |
| 行数 | 105 | 180（+71%） |
| 根路径探测 | 依赖**已不存在的** `scripts/core/` 布局 | bundle 引导 + `from core.workspace import PROJECT_ROOT` |
| 功能 | 两档信号，无状态持久化 | 三档信号 / 状态去重 / 每日重置 |

且两处死回退指向已废弃技能 ID `ta-multi-agent-analysis` 的旧布局 `skills/<id>/templates/`，**永不可达**。

### T6【中】评分口径被 fork，与 AGENTS.md 冲突

[local_ma20_backtest.py](../../skill_bundle/skills/astock-knowledge-tips/scripts/local_ma20_backtest.py) 自实现 MA/EMA/MACD/RSI，注释自称「简化 100 分制：均线 25 + MACD 40 + 量价 15」，并自实现回测指标，绕过权威 [combo_scorer.py](../../skill_bundle/runtime/core/models/combo_scorer.py)（484 行）→ **同一标的会产出与 `astock evaluate` 不一致的分数**。文件头自述动机为「规避 SSL 超时 / 沙箱无外网」，属为绕开环境问题而 fork 算法。

### T7【中】`pool audit` 双后端

[pool_audit.py](../../skill_bundle/skills/astock-pool-audit/scripts/pool_audit.py)（124 行，自带 `quote_batch()` / `ma_of()`）是 manifest 中**唯一指向技能脚本的 `entry_point`**；同时 [portfolio_cmds.py](../../skill_bundle/runtime/core/commands/portfolio_cmds.py) 内 `cmd_pool_audit` 是另一套实现。同一命令存在两个语义不同的后端。

### T8【中】3 处死路径

`investment_report.py`、`position_manager.py`、`predictor.py` 均将 `A_DATA_DIR` 拼为 `PROJECT_ROOT/.../core/data` 以查找 `fetch_patched.py`——该文件实际在 `skills/astock-data-feed/scripts/`，且 `PROJECT_ROOT` 是**可写数据根**（Release 态下不含代码）→ 子进程调用恒失败。`model_cmds.py` 另向用户打印已迁移的旧路径。

### T9【高】测试基线不可信 + 无 CI

- `.github/**` **0 命中**，仓库无任何 CI；「① 无条件先跑」完全依赖智能体自觉；
- 两处**静态可判定的必然失败**藏在 p1/p2 档：
  - `tests/governance/test_security_audit.py` 的 `/api/docs/save` 用例：被测端点硬编码 `Path(__file__).parent×3` → 实际写 `apps/web-console/output/reports/`，测试却断言 `<repo>/output/reports/`，清理也删错文件；`.gitignore` 的 `output/**` 未锚定仓库根 → 残留静默；
  - `tests/core/test_custom_output.py` 的 7 个子进程指向**已删除的** `.agents/skills/`，`_resolve()` 对该前缀不做存在性检查 → 退出码 2 必失败。
- 而 testing-guide 明令「**禁止默认全量**」→ 这两处失败在正常工作流中**永远不会被发现**，「离线全量 0 failed / 395 passed」的基线声明已失效；
- `tests/skills/` 两个文件既未登记档位也未登记标签（违反自定规则）；`testpaths` 第二项 `skill_bundle/skills` 收集 **0 例**（死配置）。

### T10【中】文档口径漂移，直接影响技能发现

| 项 | 不一致 |
| :--- | :--- |
| 技能数 | README 标题「**17** 大智能体技能体系」+ 表格 17 行、`docs/index.md`「**18** 技能」、`tests/README.md`「**18** 项」、实际 **19**（+1 总入口 = 20 入口） |
| 宿主清单 | README 第四节标题为「Antigravity / Hermes / Codex」，**未含 WorkBuddy**，与目标宿主不符 |
| 产品路线矛盾 | README 第七节「为了进一步**摆脱对第三方 AI 终端工具的宿主环境依赖**…构建自包含 Web 版本」与规范第 9-11 行「WebUI 只是可选开发调试应用，Release 基础能力不能依赖它」**直接矛盾** |
| 测试文档 | `tests/README.md` 目录映射仍指向不存在的 `scripts/core`、`scripts/server`、`web/`；core 文件数少报 6、server 少报 3；`browser_e2e` 三处数字互相矛盾（7 / 8 / 实际 14） |

---

## 六、三种交付形态对比

| 形态 | 做法 | 评价 |
| :--- | :--- | :--- |
| **A. 单入口 + 固定安装根 + 引用注册**（**推荐**） | 整个集合安装到固定代码根（如 `%LOCALAPPDATA%/a_stock_agents/bundle`）；宿主技能目录内仅放一个**链接/引用**指向 Release 内 `skills/a-stock-agents`；宿主发现 **1 个入口 / 19 项可路由能力** | 完全符合规范第 62-68 行「只安装一个完整版本单元」；不复制 19 份 runtime；卸载只删入口。前提是宿主支持目录引用（Windows junction 需真机验证，WorkBuddy 未验证） |
| B. 每技能自包含（vendored runtime） | 20 个技能各带一份 runtime | 直接违反「不要复制 19 份共享运行时」；包体膨胀约 20 倍；算法更新需同步 20 份。**T4 / T5 已是该病症的发作样本** |
| C. 宿主原生格式适配层 | 每宿主一个 builder 输出其原生容器 | 长期正确方向，前提是先取得三个宿主的**官方导入契约**（多技能容器 / 根清单 / 元数据 schema / 依赖与执行权限 / 升级卸载 / 缓存刷新）。当前 3 个 `build_*.py` 仅将同一 ZIP 更换 platform 标签，规范第 74-76 行已明确「平台标签不能替代格式适配」 |

**推荐路线**：先 A（打通「装得上、找得到、跑得起来」并自动化验收），再按宿主官方契约做 C；**B 排除**。

---

## 七、结论

**1. 方案 1 可行吗？**
作为「一个 ZIP 交给三个宿主自动识别 20 个技能」——**不可行**（S1 / S2 / S5）。
作为「完整集合安装到固定根 + 单入口引用注册」——**可行，但必须先完成 P0 阶段**（见后续计划 P0-1 / P0-2 / P0-4）。
当前状态代码自身标注 `unverified`，**不能对外宣称兼容**；三个宿主中 WorkBuddy 连适配路径都仍为空。

**2. 方案 2 可行吗？**
**定位正确，应坚持为主线**，且已落地大半（单一来源、数据根分流、归档纪律、引用注册、业务测试均达标）。
但「测试策略」这一半当前**只覆盖业务正确性，交付链路是盲区**（T1–T3）：技能在开发仓库里算得对、不造假、不越权，但**打出来的包在别人机器上装得上、找得到、跑得起来，这三件事目前没有一条自动化保障**。

> 一句话：**方案 2 是骨架，方案 1 是骨架上尚未长好的交付肌肉；不要为「总包能发」而走形态 B 的自包含路线，那会把已守住的 SSOT 一次性赔掉。**

---

## 附：证据索引

| 类型 | 路径 |
| :--- | :--- |
| 权威规范 | [skill-suite-portability-specification.md](../guidelines/engineering/skill-suite-portability-specification.md) |
| 打包链路 | [common.py](../../tools/packaging/common.py)、`build_codex.py` / `build_hermes.py` / `build_workbuddy.py`、[pack.py](../../bin/pack.py) |
| 宿主适配 | [host.py](../../tools/host_adapters/host.py)、[references.py](../../tools/host_adapters/references.py)、`codex.py` / `hermes.py` / `workbuddy.py` / `project.py` / `windows_junction.ps1` |
| 运行时契约 | [workspace.py](../../skill_bundle/runtime/core/workspace.py)、`bootstrap.py` / `doctor.py` / `run_skill.py` / `cli.py` |
| 启动器 | `bin/astock` / `bin/astock.ps1` / `bin/astock.cmd`、`skill_bundle/runtime/astock*` |
| 技能入口 | `skill_bundle/skills/*/SKILL.md`（20 个）、[skills_manifest.json](../../skill_bundle/assets/config/skills_manifest.json) |
| 单一来源违规样本 | [tencent_fields.py](../../skill_bundle/runtime/core/data/tencent_fields.py)、`skills/astock-agent-debate/assets/templates/ta_entry_monitor.py`、`skills/astock-knowledge-tips/scripts/local_ma20_backtest.py`、`skills/astock-pool-audit/scripts/pool_audit.py` |
| 测试体系 | [testing-guide.md](../guidelines/engineering/testing-guide.md)、`tests/conftest.py`、[tests/README.md](../../tests/README.md) |
| 一次性验收脚本 | [verify_release_scope.py](../../tools/development/verify_release_scope.py) |