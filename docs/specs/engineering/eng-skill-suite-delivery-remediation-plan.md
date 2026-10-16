# 技能交付闭环整改实施计划

- **规范编号**：归属 `SPEC-ENG-001`
- **权威定义 (SSOT)**：[技能总包、唯一来源与跨平台接入评估规范](../../guidelines/engineering/skill-suite-portability-specification.md)
- **评估依据**：[2026-10-15 交付形态评估报告](../../audits/2026-10-15-skill-suite-delivery-assessment.md) 与 [2026-10-16 规范审查与安装评估报告](../../audits/2026-10-16-skill-structure-review.md)
- **实施状态**：🚧 实施中（基座 7/7 项已完成；当前全局进度 7/24 项完成 29.2%；P0 交付阻断剩余 3 项；当前就绪活跃断点：`[▶] P0-08`）


> 本计划只承载**任务矩阵、执行标记与验收门槛**。目录树、路径规则、链接与权限规则的正文一律以 SSOT 为准，本文件不复述。
> 与 [eng-skill-suite-portability-plan.md](eng-skill-suite-portability-plan.md) 并行跟踪：后者记录结构迁移历史，本计划承接其遗留的「扩展验收待完成」部分。

---

## 一、整改目标与不变量

**目标**：把「技能在开发仓库里算得对」扩展为「打出来的 Release 在宿主机器上**装得上、找得到、跑得起来**」，并让这三件事具备可重复的自动化保障。

**整改总原则（2026-10-15 授权）**：声明与事实不一致时，**以实测事实为准直接修正既有不规范定义**——包括 `AGENTS.md`、`testing-guide.md`、`tests/README.md`、`pyproject.toml`、`tests/conftest.py` 档位表、CLI 期望清单等既有声明文件；不为绕开过期声明而新建第二套口径。每处修正必须：① 以实测命令为依据；② 保留历史快照为「历史记录」而非删除；③ 修正后过 P0 门禁并在第五节留痕。

**必须保持的不变量（整改过程中不得破坏）**：

| # | 不变量 | 依据 |
| :-: | :--- | :--- |
| I1 | 技能源码单一来源在 `skill_bundle/skills/`，公共实现单一来源在 `skill_bundle/runtime/core/`，不得在技能目录复制引擎 | SSOT 第 58 行 |
| I2 | Release 不依赖符号链接/junction，归档内为实体文件，由 `bundle.json` 定位集合根 | SSOT 第 82 行 |
| I3 | 开发数据根为仓库，Release 数据根为 OS 用户数据目录；升级不得覆盖用户状态 | SSOT 第 88 行 |
| I4 | 拒绝以开发源码作为宿主注册目标 | SSOT 第 78 行 |
| I5 | 归档强制排除 `local/output/log/temp/.env`、开发发现链接与源码机器绝对路径 | SSOT 第 72 行 |
| I6 | 现有 P0 核心门禁（`pytest -m core`）必须保持全绿，不得为让新用例通过而放宽既有断言 | [testing-guide.md](../../guidelines/engineering/testing-guide.md) |
| I7 | 未实测项一律标注「未验证」，不得由平台命名或静态推断宣称宿主兼容 | SSOT 第 76、96 行 |

**范围边界**：本计划不新建第二套源码镜像、不为三个宿主维护平台镜像、不引入形态 B（每技能自带 runtime）。宿主原生格式适配（形态 C）另立后续计划。

---

## 二、任务矩阵

状态图例：`☐ 未启动` · `[▶] 就绪待执行` · `◐ 进行中` · `☑ 已完成` · `⊘ 阻塞` · `— 不适用`

### P0 交付阻断项（必须先完成，未完成不得发布正式 Release）

| 任务 ID | 任务 | 状态 | 验收门槛 |
| :--- | :--- | :---: | :--- |
| `P0-01` | 技能文档去开发仓库相对路径，统一自描述调用式 | ☑ | 20 个 SKILL.md 与 `references/` 内不再出现依赖 CWD 的仓库相对路径或包外链接 |
| `P0-02` | 新增发布链路 P0 门禁（frontmatter / 启动器 / 自诊断 / 打包行为） | ☑ | 新用例纳入 `core` 档并随 `pytest -m core` 常跑；`package_project` 8 项行为全部有正向或反向断言 |
| `P0-03` | 宿主注册红线与三平台 shim 加哨兵 | ☑ | 「拒绝注册开发源」「bundle.json 缺失」「workbuddy 未验证分支」均有断言且必然执行 |
| `P0-04` | 依赖声明收敛单一来源 + `INSTALL.json` 补安装说明 | ☑ | 全仓仅一处声明 `MyTT` / `akshare-proxy-patch`；版本口径一致；`INSTALL.json` 含依赖安装与 Python 下限 |
| `P0-05` | 安装脚本去宿主污染 | ☑ | 无对宿主全局解释器的 pip install；凭据落 `local/settings/.env`；安装流程无外网/LLM 调用；无固定父目录层数；无废弃技能 ID；P0 门禁通过 |
| `P0-06` | 隔离解压验收转为可重复、不改源码树的常驻用例 | ☑ | 可在隔离路径解压 Release 并跑通自诊断；执行过程不修改源码树；纳入 P0 门禁 |
| `P0-07` | 修复迁移后 P1/P2 既有失败并锚定 `output/` 忽略规则 | ☑ | 离线全量恢复 0 failed；`.gitignore` 的 `output/**` 锚定仓库根 |
| `P0-08` | Release 产物锚点技能架构与转发壳三级寻址 | [▶] | 构建期将公共 runtime 注入 `a-stock-agents`；转发壳支持自定位/兄弟/收据三级定位；隔离解压验收通过 |
| `P0-09` | 统一安装底层脚本核心 `install.ps1` / `install.sh` | ☐ | 支持 `-Inspect`、`-Agent`、`-Method`、`--json`；支持隔离建 venv、装依赖与 doctor 自检冒烟 |
| `P0-10` | 逐技能粒度注册与“宿主发现模拟”门禁 | ☐ | 注册粒度改为逐技能链接；新增自动化门禁模拟 Universal / Hermes / WorkBuddy 扫描，断言 20 入口均被发现 |

### P1 质量与一致性

| 任务 ID | 任务 | 状态 | 验收门槛 |
| :--- | :--- | :---: | :--- |
| `P1-01` | 腾讯解析器收敛至 `tencent_fields` 单一来源 | ☐ | 技能目录内 0 处独立下标解析；templates 豁免取消并由 AST 哨兵看守 |
| `P1-02` | `ta_entry_monitor` 模板二选一收敛 | ☐ | 仅存一份，能力以强版本为准；两处死回退清除 |
| `P1-03` | `local_ma20_backtest.py` 复用权威评分与指标 | ☐ | 不再自实现 MA/EMA/MACD/RSI 与 100 分制；仅保留离线读盘适配层 |
| `P1-04` | `pool audit` 双后端合一 | ☐ | 同一命令只有一个后端实现；manifest `entry_point` 指向保持不变或同步更新 |
| `P1-05` | 修复死路径与陈旧路径打印 | ☐ | 3 处 `A_DATA_DIR` 改由 `core.workspace` 或既有常量定位；不再向用户打印已迁移路径 |
| `P1-06` | CLI `--json` 输出结构契约 + `skill list` 输出测试 | ◐ | `expected_commands` 已对齐 46 个注册子命令（2026-10-15）；执行型 `--json` 结构断言与 `skill list` 输出测试仍待补 |
| `P1-07` | 引入 CI，承载 P0 与发布链路门禁 | ☐ | 至少覆盖 ① 核心门禁 + 发布链路门禁 + 隔离解压验收 |
| `P1-08` | 模态一落地：AI 安装引导提示词与 5 类信息卡片渲染契约 | ☐ | 提示词模板进入发版说明；总入口与安装流支持 5 阶段卡片状态机输出 |
| `P1-09` | 模态二落地：终端 TUI 键盘多选导轨菜单 | ☐ | 终端有 TTY 时自动启动键盘上下/空格多选菜单，对齐截图交互与 Overwrites 冲突保护 |
| `P1-10` | 多版本原子切换与一键回滚升级链 | ☐ | `releases/<tag>` + `current` Junction 机制落地；支持 `-Update` 与 `-Rollback`，用户数据 100% 留存 |

### P2 文档口径

| 任务 ID | 任务 | 状态 | 验收门槛 |
| :--- | :--- | :---: | :--- |
| `P2-01` | 统一技能计数口径 | ☐ | README / `docs/index.md` / `tests/README.md` 一致为 19 项业务技能（+1 总入口 = 20 入口） |
| `P2-02` | README 宿主清单与产品路线对齐规范 | ☐ | 宿主名含 WorkBuddy；第七节不再宣称「摆脱宿主依赖」为产品路线 |
| `P2-03` | 测试文档映射与死配置修正 | ◐ | 基线数字 / 目录映射 / `.agents` 旧路径 / `testpaths` 死条目 / 档位漏登记已于 2026-10-15 修正；testing-guide 8.x 历史章节与 `pyproject` 注释的最终复核仍待 `P0-07` 复测后收口 |
| `P2-04` | 独立 Release 仓库发布与 `npx skills add` 通用生态打通 | ☐ | 发布构建产物到 Release 分支/仓库，支持 `npx skills add cvdnn/a-stock-agents -g` |

---

## 三、可勾选执行清单

> 执行时在对应条目的 `[ ]` 内打 `x`，并同步回填第二节矩阵状态与第五节的证据登记。

### P0 交付阻断项

- [x] **`P0-01` 技能文档去开发仓库相对路径**（2026-10-15 完成，`test_release_delivery_gate.py` 第 10 节 4 例入 `core` 档）
  - 已落地：
    1. **调用约定统一**：全部 19 项专业技能统一声明自描述「调用约定」，明确从真实路径向上定位含 `bundle.json` 的集合根（`$BUNDLE`），使用 Windows `$BUNDLE/runtime/astock.ps1` 与 POSIX `$BUNDLE/runtime/astock` 薄启动器（回退 `python $BUNDLE/runtime/cli.py`），正式调用追加 `--json`，并统一回链 `references/execution-contract.md`；总入口 `a-stock-agents/SKILL.md` 保持对齐；
    2. **彻底清除 `bin/astock*`**：全包所有 SKILL.md、Markdown 与 `setup.sh` 中的 `bin/astock*` 相对路径清零；
    3. **包外链接与断链清零**：全包 103 个 Markdown 文件经 AST 扫描断言 0 处链接逃逸出 `skill_bundle/`，0 处失效断链（`astock-selection-model`、`historical-session-tips-full` 的包外 `docs/` 链接已转为设计文档文本声明）；
    4. **去 CWD 依赖**：`astock-pool-dashboard` 的 crontab 定时调度等示例去除 `cd /path/to/a_stock_agents`，说明以绝对路径调用并说明 cron 环境变量规则；
    5. **常驻自动化门禁**：`test_release_delivery_gate.py` 新增第 10 节 4 项测试（统一调用约定声明、零 `bin/astock` 引用、包内相对链接防逃逸且物理存在、定时任务去 `cd` 依赖），纳入 `core` 档。
  - 门槛：`pytest -m core` 全绿 ✅（312 passed / 2 skipped / 54.72s）；新增 4 例用例 ✅；全包 Markdown 零包外链接、零断链、零 bin/astock ✅。

- [x] **`P0-02` 新增发布链路 P0 门禁**（2026-10-15 完成，`tests/core/test_release_delivery_gate.py`，36 例入 `core` 档）
  - 已覆盖：
    1. 20 个 SKILL.md 的 YAML frontmatter 可解析、`name` 与目录名一致、`description` 非空（参数化 20 例，实测前置预验 20/20 健康）；
    2. 三平台启动器真实执行（`.ps1` / `.cmd` 经真实子进程冒烟 + 失败退出码透传断言 `exit 2`；POSIX 分支 `skipif` 分离，待 posix CI 实测）；
    3. `bootstrap.py` 正向（经 doctor 子进程链路覆盖）、`doctor.py` 正向（stdout 合法 JSON + `is_healthy` + 退出码 0）、`run_skill.py` 六场景矩阵（`--list` 健康输出 / 缺参 exit 2 / 三种非法 `--params` exit 2 / 未知技能 JSON 错误体 + exit 1）；
    4. **直接调用** `check_workspace_health()` 断言完整 8 键结构（替代手写复制条件）；
    5. `package_project` 行为：后缀白名单反向断言（含无后缀特例精确枚举）、`.env*`/`config.yaml`/私有根排除 + zip-slip 粗检、sha256 sidecar 存在/格式/摘要一致、host_adapters 4 件套随包（platform=codex）、zip POSIX 执行位（`astock`/`.sh`→`0o755`、普通文件→`0o644`、`create_system==3`）、`INSTALL.json` 全字段（含诚实声明 `native_import_verified=False`）、根三件套（`INSTALL.json`/`requirements.txt`/`LICENSE`）、打包 JSONL 审计记录（含 sha256 与 `host_installation_verified=False`）；
    6. `skill_resource()` 防逃逸双分支（非法技能 ID + 越界路径）与合法路径解析。
  - 附带整改：移除旧打包用例的 `A_STOCK_NO_BUILD=1` 一键 skip 口子（`test_skill_suite_layout.py`）；子进程场景按 `test_custom_output` 先例 `ThreadPoolExecutor` 并行化（新文件单跑 42s，其中并行矩阵 22s+7s）。
  - 门槛：`pytest -m core` 全绿 ✅（291 passed / 2 skipped / 81.82s）；新增用例数 36 ≥ 15 ✅；`conftest.py` 双登记（`_TIER_BY_PATH` core + `_TAGS_BY_PATH` `{subprocess, slow}`）✅。

- [x] **`P0-03` 宿主注册红线与三平台 shim 加哨兵**（2026-10-15 完成，`test_release_delivery_gate.py` 第 7 节 10 例）
  - 已覆盖（全部经真实 shim 子进程驱动——`host.py` 为库模块，CLI 入口即三个平台 shim，天然验证「裸导入在脚本目录下可解析」）：
    1. `bundle.json` 缺失 → exit 2（`bundle.json missing`）；
    2. **头号发布红线**：`--bundle skill_bundle`（开发源，marker 无 `distribution=release`）→ exit 2 + `Release required; development source cannot be registered`——AGENTS.md「不将开发源码注册到全局技能目录」的唯一技术执行点首次有哨兵；
    3. 无 `--entry` 时三平台 `configured_target` 模式矩阵（codex/workbuddy=reference-only、hermes=external_dirs；`host_scan_status=unverified`、`copy_fallback=False`）；
    4. workbuddy + `--entry` → `HOST_REFERENCE_SUPPORT_UNVERIFIED` + 断言**入口目录未被创建**（无复制回退铁律）；
    5. codex + `--entry` → 引用式注册成功（入口 resolve 指向唯一源，源码不动）；
    6. **归档平级目录可导入**：从 codex 归档解压 `host_adapters/` 后 shim 独立可执行（发现并修正用例设计：打包按平台只携带对应 shim——codex 包内为 codex.py + host.py + references.py + windows_junction.ps1，无其他平台 shim）；
    7. 退役入口 `project.py` → 非零退出 + `retired` / `Build a Release` 消息（防误改回可用状态）。
  - 门槛：断言必然执行（无 `if 条件: assert`；workbuddy 分支额外断言 `not entry.exists()`）✅；P0 门禁全绿 ✅（300 passed / 2 skipped / 69.30s）。

- [x] **`P0-04` 依赖声明收敛单一来源 + `INSTALL.json` 补安装说明**（2026-10-15 完成）
  - 已落地：
    1. **声明收敛**：`pyproject.toml` `[project.optional-dependencies].full` 增补 `MyTT>=2.9.0`、`akshare-proxy-patch>=0.5.0`，akshare 口径统一为 `>=1.18.0`（uv.lock 实锁 1.18.88/94，原技能清单与 pyproject 的 1.18/1.12 双口径冲突消除）——**全仓依赖版本声明唯一来源**；
    2. **技能级清单改纯引用**：`skill_bundle/skills/astock-data-feed/requirements.txt` 的 20 行手写版本清单替换为 `-r ../../../requirements.txt`（开发仓库与 Release 归档两种布局下均解析到根清单，已测试验证）；
    3. **构建期派生 `requirements-full.txt`**：`common.py` 新增 `_full_extra_requirements()` 从 pyproject 派生 full extra，随包写入归档根（`-r requirements.txt` + extras，注释声明派生属性）——符合 SSOT「平台元数据和安装说明由共用构建器派生」，不是第二份手工清单；
    4. **`INSTALL.json` 增补 4 键**：`python_requirement`（3.9+）、`dependency_install`（基础 + 数据源增强两级安装路径）、`launcher`（三平台入口）、`health_check`（doctor.py 退出码契约）——宿主装完后首次有完整安装与运行指引。
  - 新增/扩展门禁用例 3+1：`test_dependency_declarations_have_single_source`（全仓 requirements 文件纯引用 + 根基础导出不含 extras）、`test_archive_requirements_full_is_derived_from_pyproject`、`test_skill_requirements_reference_resolves_in_dev_and_release`、INSTALL.json 用例扩 4 键断言。
  - 门槛：全仓仅 pyproject 一处声明 `MyTT`/`akshare-proxy-patch` ✅；Release 内不再并存两份互不同步清单（技能级为 `-r` 引用，full 为构建派生物）✅；`pytest -m core` 全绿 ✅（303 passed / 2 skipped）。
  - **遗留边界**：`pyproject` full 增补后 `uv.lock` 尚未联网重锁（`uv lock` 需解析新依赖，属外部网络操作，待人工确认后执行并重新离线导出根 requirements.txt）；当前根 requirements.txt（--no-dev 基础导出）本就不含 extras，Release 基础安装路径不受影响。

- [x] **`P0-05` 安装脚本去宿主污染**（2026-10-15 完成，P0 门禁实测通过）
  - 已重写 `astock-agent-debate/scripts/setup.sh` 为只读自检辅助入口：
    1. `bundle.json` 向上探测 Bundle 根，移除固定父目录层数；
    2. 解释器只接受显式 `A_STOCK_PYTHON`、已激活 `VIRTUAL_ENV` 或 Bundle 外部 `.venv`，未发现隔离解释器时提示并 exit 1；不回落裸 `python3`，不执行任何 `pip install`；
    3. 移除 `git clone` 外部仓库、明文凭据写入 `temp/vendor/.env`、安装期外网/LLM 冒烟；改为指引凭据存放于 `local/settings/.env` / `A_STOCK_CONFIG_PATH`；
    4. 文档移除外部 clone/pip install/旧技能名和 vendor 路径示例，统一说明 CLI 用法及 A-Stock 19 项前置技能；
    5. 新增 `test_setup_scripts_do_not_pollute_host_environment`，对全部 3 个 setup.sh 建立静态守卫（无 pip install / git clone / 临时 vendor / 旧 ID / 固定层级路径，必须 bundle.json 探测）；
    6. `astock-data-feed/setup.sh` 与 `astock-platform-evaluate/setup.sh` 保持原有 doctor 自检流程不变，三者都通过守卫。
  - 已知限制：Phase 2 TradingAgents 外部依赖库需用户自行准备到 `TRADING_AGENTS_ROOT` 并配置隔离环境；脚本不再自动联网克隆/安装，避免静默副作用。
  - 门槛：静态守卫定向用例 1 passed ✅；完整 P0 `-m core`：308 passed / 2 skipped / 358 deselected，134.83s，退出码 0 ✅；收集基线 668（core 档 310）。

- [x] **`P0-06` 隔离解压验收常驻化**（2026-10-15 完成，`tests/core/test_release_delivery_gate.py` 第 8 节 4 例）
  - 已落地：
    1. **三平台常驻验收**：`test_isolated_extraction_and_doctor_smoke_across_platforms` 参数化覆盖 codex / hermes / workbuddy，构建产物解压到临时隔离根，设置独立 `A_STOCK_WORKSPACE_ROOT`，清空 `PYTHONPATH` 与全部 `A_STOCK_*` 开发环境变量，断言 zip-slip 防御、20 个 SKILL.md 存在、doctor.py 退出码 0 且 `is_healthy=True`；
    2. **数据根与代码根解耦断言**：断言 doctor 报告的 `workspace_root` 精确绑定到独立隔离目录（而非开发仓库根），`package_root` 精确指向解压目录下的 `skill_bundle`；
    3. **源码树零修改守卫**：记录 `bundle.json`、`SKILL.md`、`setup.sh`、`.gitignore` 在执行前后的 sha256 摘要，断言前后完全一致；
    4. **构建幂等性用例**：`test_isolated_packaging_and_verification_is_idempotent` 验证连续两次构建条目清单及内容完全一致；
    5. **旧脚本破坏性逻辑安全退役**：[verify_release_scope.py](file:///c:/Users/cvdnn/coding/a_stock_agents/tools/development/verify_release_scope.py) 头部追加废弃说明，彻底移除其此前覆写 `setup.sh`、`SKILL.md`、`.gitignore` 的破坏性代码，转为只读候选验证工具。
  - 门槛：解压在 `temp/` 或 OS 临时目录完成，验证完毕自动清理 ✅；`pytest -m core` 全绿 ✅（307 passed / 2 skipped / 65.77s）；源码树零修改断言通过 ✅。

- [x] **`P0-07` 修复迁移后 p1 档既有腐化（③ 实测 5 failed）并锚定忽略规则**（2026-10-15 完成，③ 复测 0 failed）
  - 背景实测（2026-10-15，③ `-m "core or p1"`：553 passed / 5 failed）：5 处失败均为 2026-10-14 目录迁移后的 p1 档腐化，P0 门禁不可见。逐项处置（均已落地）：
    1. **生产缺陷（3 处，`/api/docs` 端点家族）✅ 已修复**：`apps/web-console/backend/server/app.py` 的 `read_workspace_doc`/`save_workspace_doc` 改经 `core.workspace.WORKSPACE_ROOT` + `core.config.OUTPUT_REPORTS_DIR` 解析（测试态随 `A_STOCK_OUTPUT_DIR` 重定向到隔离目录，不再写源码树/真实 `output/`）；白名单 `.agents/skills` 旧路径改 `SKILLS_ROOT`/`ASSETS_ROOT`；`forbidden_prefixes` 扩充（`apps`/`web-console`/`frontend`/`skill_bundle`/`tools`/`bin`/`docs`），堵住 `apps/web-console/frontend/index.html` 覆写绕过；rel_path 对重定向目录回退绝对路径；
    2. **断言语义修正（1 处）✅ 已修复**：`['10','20','50']` 实为 `issPageSize` 合法分页控件选项值，非伪造数据——`test_production_authenticity` 结构断言 1 增加剥离 `<select>` 块的语义修正；断言 5 首次执行到并暴露 `frontend/backup/智能选股工作台_3ffded1.html` 缺「非生产设计原型」声明（其余 3 个备份页已有），已补声明；
    3. **测试侧旧路径（1 处 + 原 H2）✅ 已修复**：`test_data_sync_settings.py` 的 `market_path` 改指 `apps/web-console/backend/server/api/market_data.py`；`test_custom_output.py` 的 7 个 `.agents/skills/` 子进程路径改 `skill_bundle/skills/`，`_resolve()` 增加存在性 fail-fast，`test_default_output_untouched` 修正空转断言（规约三）；
    4. `.gitignore` 的 `output/**` 锚定仓库根（`/output/**`）✅ 已修复。
  - 门槛：③ 复测 **558 passed / 0 failed**（380.27s）✅；不再有写源码树的用例（docs/save 落点经隔离重定向）✅；生产缺陷处置未改弱任何断言（`docs` 断言族、AST 哨兵、防回归断言全部保留）✅。
  - 边界：`p2` 档（含 `test_custom_output` 修复项）未纳入本轮实测；离线全量 `not network`（578 例）复跑前不引用「全量 0 failed」。

- [ ] **`P0-08` Release 产物锚点技能架构与转发壳三级寻址**（▶ 当前就绪 / 下一步优先执行）
  - 背景：通用生态工具（如 `npx skills add`）只搬运单个技能子目录，现有平级 `runtime/` 结构脱离后导致 20 个技能全部瘫痪。
  - 动作：
    1. 构建器 `tools/packaging/common.py` 调整归档装配：将公共 `runtime/`、`assets/`、`references/` 收敛注入到 `skills/a-stock-agents/`（锚点技能）中，其余 19 个专业技能保持轻量；
    2. 转发壳模板升级为三级渐进式寻址：① 自身目录向上探测 `bundle.json` -> ② 探测兄弟目录 `../a-stock-agents/bundle.json`（穿透符号链接）-> ③ 探测系统固定安装收据 `%LOCALAPPDATA%/a_stock_agents/install.json`；失败时 fail-closed 提示 `ANCHOR_SKILL_MISSING`；
    3. `tests/core/test_release_delivery_gate.py` 新增常驻断言覆盖三级寻址分支与锚点打包结构。
  - 门槛：解压后仅将单个技能目录或全部技能移至临时目录，均能通过兄弟定位或收据定位正常唤起 `doctor.py` 并通过 P0 门禁。

- [ ] **`P0-09` 统一安装底层脚本核心 `install.ps1` / `install.sh`**
  - 背景：缺乏开箱即用的跨平台部署脚本，缺少 venv 自动构建、依赖安装与 `--json` 机器接口。
  - 动作：
    1. 编写跨平台安装核心 `install.ps1`（Windows）与 `install.sh`（POSIX），支持 `-Inspect`（环境探测）、`-Agent <list>`（指定宿主）、`-Method <link|copy>`（挂载方式）、`-Yes`（跳过确认）与 `--json` 输出；
    2. 脚本自动在数据根 `%LOCALAPPDATA%/a_stock_agents/`（或 POSIX 对应路径）下构建独立隔离的 `.venv`，不污染宿主全局 Python；
    3. 自动安装 `requirements.txt` 并执行 `doctor.py --json` 验证全部 20 个入口可用性，输出持久化凭证 `install.json`；
    4. 增加常驻自动化测试，在临时沙箱环境中模拟运行 `install.ps1 -Inspect -Json` 与安装链路。
  - 门槛：脚本在隔离环境一键执行成功，退出码 0，生成的 `install.json` 包含 20 个入口就绪证明与 SHA256 校验。

- [ ] **`P0-10` 逐技能粒度注册与“宿主发现模拟”门禁**
  - 背景：现有 `host.py` 将整个 `skills/` 目录作为一个链接注册，导致只扫一层的宿主（Codex/Hermes/WorkBuddy）完全无法发现子技能（H1 阻断项）。
  - 动作：
    1. `tools/host_adapters/host.py` 与 `references.py` 注册逻辑调整为**逐技能粒度**（20 个链接：`<宿主技能根>/<id>` -> `current/skills/<id>`）；
    2. 新增离线自动化门禁：针对 Codex（`plugin.json` + `skills/`）、Hermes（`skills.external_dirs` 扫描）、WorkBuddy（`~/.workbuddy/skills/<id>/SKILL.md` 一层扫描）分别模拟宿主发现逻辑；
    3. 断言三种宿主模拟器均能 100% 发现全部 20 个入口（1 个总入口 + 19 项专业技能）。
  - 门槛：新增门禁纳入 `tests/core/test_release_delivery_gate.py`，三宿主发现数全部恒等于 20，`pytest -m core` 全绿。

### P1 质量与一致性

- [ ] **`P1-01` 腾讯解析器收敛至 `tencent_fields` 单一来源**
  - 动作：技能目录内 8 个模板/脚本的独立下标解析改为 `from core.data.tencent_fields import ...`。
  - 落点：`skills/astock-pool-audit/scripts/pool_audit.py`、`skills/astock-pool-dashboard/scripts/sandbox.py`、`skills/astock-data-feed/assets/templates/monitor_watchdog.py`、`skills/astock-agent-debate/assets/templates/ta_entry_monitor.py`、`skills/astock-pool-dashboard/assets/templates/entry_monitor_hardcoded_ma20.py`、`skills/astock-knowledge-tips/assets/templates/{monitor_limit_order,periodic_reminder,portfolio_review}.py`。
  - 门槛：取消现有 `"templates" not in p.parts` 豁免，新增 AST 级哨兵禁止独立下标解析。

- [ ] **`P1-02` `ta_entry_monitor` 模板二选一收敛**
  - 动作：将技能侧强版本能力（三档信号 / 状态去重 / 每日重置）合并进 core 模板，删除技能 assets 副本；修正 core 模板失效的根路径探测；清除两处指向废弃技能 ID 的死回退。

- [ ] **`P1-03` `local_ma20_backtest.py` 复用权威评分与指标**
  - 动作：`ma/ema/tech/combo_score/backtest` 改为调用 `core.indicators.technical_indicators`、`core.models.combo_scorer`、`core.paper_trading.backtest_metrics`；仅保留「从本地落盘读 K 线」的离线适配层。

- [ ] **`P1-04` `pool audit` 双后端合一**
  - 动作：确定唯一后端（建议以公共 CLI `cmd_pool_audit` 为准），技能脚本改为薄转发壳；同步更新 manifest `entry_point`。

- [ ] **`P1-05` 修复死路径与陈旧路径打印**
  - 落点：`core/reporting/investment_report.py`、`core/strategy/position_manager.py`、`skills/astock-pool-dashboard/scripts/predictor.py`、`core/commands/model_cmds.py`。

- [ ] **`P1-06` CLI `--json` 输出结构契约 + `skill list` 输出测试**
  - 动作：对代表性命令执行后 `json.loads(stdout)` 并校验 `status` / `data` / 错误体结构；`skill list` 输出与 manifest 条目数对齐；`expected_commands` 补齐 `funnel` / `pattern`。

- [ ] **`P1-07` 引入 CI**
  - 动作：新增 CI 配置，承载 ① 核心门禁 + 发布链路门禁 + 隔离解压验收。
  - 门槛：PR 上强制运行，失败即阻断。

- [ ] **`P1-08` 模态一落地：AI 安装引导提示词与 5 类信息卡片渲染契约**
  - 背景：避免用户发送模糊指令导致 AI 幻觉和乱装，固化自包含提示词与卡片交互规范。
  - 动作：
    1. 在 `README.md`、发版模板与快速上手指南中固化「一键复制给 AI 的标准化安装指令模板（AI Copilot Bootstrap Prompt）」；
    2. 在总入口 `a-stock-agents/SKILL.md` 中增加安装引导技能分支，当检测到未安装或被显式调用时，按规范分 5 阶段输出结构化信息卡片（宿主勾选、配置项与数据源、安全摘要、任务导轨流水线、交付实战指令）；
    3. 编写静态测试断言提示词模板中的 URL、参数、SOP 阶段标记完整无误。
  - 门槛：在主流 LLM（Claude / GPT / Gemini）中粘贴该提示词能准确触发 5 阶段卡片交互。

- [ ] **`P1-09` 模态二落地：终端 TUI 键盘多选导轨菜单**
  - 动作：在 `install.ps1` 与 `install.sh` 中增加基于控制台的交互式多选导轨（对齐截图）：支持键盘上下光标、空格勾选、回车确认；展示 Universal 列表与 Additional agents（Hermes / WorkBuddy）；增加 Overwrites 冲突保护检测（遇真实同名目录拒绝覆盖）。
  - 门槛：在 Windows Terminal / PowerShell 7 与 macOS Terminal 中键盘操作顺畅，回车后无缝触发静默安装。

- [ ] **`P1-10` 多版本原子切换与一键回滚升级链**
  - 动作：
    1. 版本安装路径规范化为 `%LOCALAPPDATA%/a_stock_agents/releases/<version>/`，由 `current` 软链接统一寻址；
    2. 实现 `install.ps1 -Update [-Version <tag>]`：下载新版 -> 校验 -> 建独立目录 -> 比对依赖 Hash 按需更新 -> 原子重定向 `current` 链接 -> doctor 冒烟；
    3. 实现 `install.ps1 -Rollback`：冒烟失败或人工回退时，瞬时切回上一可用版本；
    4. 验证用户数据根（`output/`、`local/`）在升级与回滚全程 100% 物理隔离不被覆盖。
  - 门槛：新增升级与回滚自动化集成测试，断言升级前后自选股 CSV 与配置无任何修改。

### P2 文档口径与生态扩展

- [ ] **`P2-01` 统一技能计数口径** — 落点：`README.md`、`docs/index.md`、`tests/README.md`。
- [ ] **`P2-02` README 宿主清单与产品路线对齐规范** — 落点：`README.md` 第四、七节。
- [ ] **`P2-03` 测试文档映射与死配置修正** — 落点：`tests/README.md`、`pyproject.toml` 的 `testpaths`、`tests/conftest.py` 的档位登记。
- [ ] **`P2-04` 独立 Release 仓库发布与 `npx skills add` 通用生态打通** — 落点：搭建独立 release 分支/仓库，按通用 Skills 规范打通 `npx skills add cvdnn/a-stock-agents -g`。

---

## 四、门禁与测试策略要求

| 要求 | 内容 |
| :--- | :--- |
| 默认门禁 | 仍以 `pytest -m core` 为唯一自动门禁；新增的发布链路用例必须归入 `core` 档，否则不构成保障 |
| 扩展门禁 | 涉及 `p1` 覆盖面（服务端 API、设置接线、技能契约）时，须在结论中明确建议追加 ③，决策权交回用户 |
| 用例铁律 | 沿用 [testing-guide.md](../../guidelines/engineering/testing-guide.md) 第四章；本次新增用例额外要求：断言必然执行、不写真实 `output/local/log/temp`、不依赖 `PROJECT_ROOT == 仓库根` 这一隐式前提 |
| 缺陷建档 | 新暴露的生产缺陷先以 `xfail(strict=True)` 建档，禁止为让看板变绿而放宽断言 |
| 基线修正 | 完成 `P0-07` 后，须同步修正 testing-guide 与 `tests/README.md` 中已失效的基线数字与目录映射 |
| 禁止事项 | 不得为「让发布用例通过」而调整 `ALLOWED_SUFFIXES`、放宽排除规则或跳过打包 |

---

## 五、验收证据与留痕

| 项 | 要求 |
| :--- | :--- |
| 每项任务 | 在第二节矩阵回填状态，并在本表追加一行证据（命令、环境、结果、边界） |
| 证据格式 | 命令 + 平台/解释器版本 + pass/fail 数 + 耗时 + **明确边界**（不得由单平台结论外推跨平台） |
| 宿主验收 | 按 Windows / macOS / Linux × WorkBuddy / Hermes Desktop / Codex 分别登记版本、格式、独立发现数、能力调用、更新与卸载结果；AIChat 与 AIWork 分别记录实际入口可用性 |
| 未验证声明 | 真实环境未运行即标注「未验证」；发布公告须列出已验与未验项目 |
| 证据落点 | 构建与解压证据写入 `log/`（不发布）；可分享的交付报告写入 `output/reports/` |

**证据登记表（执行时逐行追加）**

| 日期 | 任务 ID | 命令 | 环境 | 结果 | 边界 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-10-15 | 计划建立 | `.venv/Scripts/python.exe -m pytest -m core -q` | Windows / 本地 `.venv` | 255 passed、358 deselected、2 warnings、102.39s | 仅验证本次「文档新增」未破坏 P0；不代表交付链路已被验证 |
| 2026-10-15 | `P1-06`（部分） | `python -c "from core.cli import build_parser; ..."` 枚举注册子命令 | Windows / 本地 `.venv` | 46 个子命令实测；`expected_commands` 从 38 补齐至 46（新增 `funnel` / `pattern` / `chenxiaoqun` / `debate` / `dataset` / `screen-model` / `server` / `ui`） | 期望清单对齐后 8 个命令被误删将触发 `p1` 档报警；执行型 `--json` 结构断言未补 |
| 2026-10-15 | `P2-03`（部分） | `pytest --collect-only -q`（及 `-m core/p1/p2/slow/network/subprocess/e2e/live/browser_e2e/②/③/not network` 分档） | Windows / 本地 `.venv` | 收集 613（core 255 / p1 303 / p2 55 / slow 110 / network 35 / subprocess 26 / e2e 31 / live 18 / browser_e2e 16；② 244、③ 558、not network 578；目录分布 core 305 / server 195 / governance 92 / skills 5 / browser 16）；据此修正 `AGENTS.md`、`testing-guide.md`、`tests/README.md` 基线与目录映射，`pyproject.toml` 移除 `testpaths` 死条目 `skill_bundle/skills`，`conftest.py` 补登记 3 个漏档位文件为显式 `p2` | 均为收集期静态计数，非执行通过证据；离线全量「0 failed」声明按 `P0-07` 前不恢复 |
| 2026-10-15 | 修正后终验 | `.venv/Scripts/python.exe -m pytest -m core -q` | Windows / 本地 `.venv` | 255 passed、358 deselected、2 warnings、80.64s，退出码 0 | 改动含 `p1` 档文件（`test_commands_suite.py` 期望清单），P0 绿不足以覆盖——建议取得人工确认后追加执行 ③（`-m "core or p1"`，558 例）验证 `p1` 档无回归 |
| 2026-10-15 | ③（用户确认后执行） | `.venv/Scripts/python.exe -m pytest -m "core or p1" -q` | Windows / 本地 `.venv` | **553 passed / 5 failed**、55 deselected、355.66s。5 处失败经根因定位均为 2026-10-14 目录迁移后的 p1 档既有腐化（`app.py:346/453` workspace 根硬编码 ×3、`index.html` 静态残留数值 ×1、`test_data_sync_settings.py:487` 旧路径 ×1），与本轮修正无关（`test_commands_suite` 46 命令断言通过） | 失败项已并入 `P0-07` 扩容任务；触网约 30 例 network 用例正常执行；`p2` 档（H2 `.agents/skills` 旧路径）未在本轮范围，仍待验 |
| 2026-10-15 | `P0-07`（用户确认后执行） | 修复 `app.py`（workspace 根 + reports 沙箱 + forbidden 前缀 + `.agents` 白名单清理）、`test_production_authenticity`（select 剥离语义修正）、`test_security_audit`（沙箱断言）、`test_data_sync_settings`（market_data 新路径）、`test_custom_output`（7 路径 + fail-fast + 反空转断言）、`frontend/backup/智能选股工作台_3ffded1.html`（非生产声明）、`.gitignore`（`/output/**` 锚定） | Windows / 本地 `.venv` | 定向 28 例 → 27 passed 修复 backup 声明后 → 1 passed；P0 `-m core`：255 passed / 114.67s；③ 复测：**558 passed / 0 failed** / 55 deselected / 380.27s | ③ 0 failed 达成；`p2` 档与离线全量 `not network`（578 例）未复跑，不引用「全量 0 failed」；未触网新增（network 用例为既有 ③ 范围） |
| 2026-10-15 | `P0-02`（用户确认后执行） | 新增 `tests/core/test_release_delivery_gate.py`（36 例：frontmatter 20 参数化 + 启动器/入口/打包/防逃逸 16 例）；`conftest.py` 双登记；移除 `A_STOCK_NO_BUILD=1` skip 口子 | Windows / 本地 `.venv` | 前置预验：20 个 frontmatter 全部健康、入口契约实测（启动器 version/坏命令 exit 2、doctor exit 0、run_skill 六场景）；定向 44 passed / 2 skipped / 42.44s；**P0 `-m core`：291 passed / 2 skipped / 358 deselected / 81.82s**；收集基线更新：总 651（core 档 293 / core 目录 343） | 2 个 skip 为 POSIX 启动器分支（win32 按设计跳过，待 posix CI 实测）；③ 收集 596 例（新 38 例并入后）未整体复跑；打包归档断言含探测实测（380 条目 / host_adapters 4 文件 / 执行位 / 根三件套） |
| 2026-10-15 | `P0-03`（用户确认后执行） | `test_release_delivery_gate.py` 新增第 7 节「宿主注册红线与三平台 shim」10 例（经真实 shim 子进程驱动；`fake_release_bundle` fixture 构造最小合法 Release） | Windows / 本地 `.venv` | 前置实测红线行为（dev 源 exit 2 + `Release required`、`project.py` exit 1、codex/workbuddy JSON 契约）；定向 10 passed / 7.54s（修正 1 处用例自误：归档按平台只携带对应 shim）；**P0 `-m core`：300 passed / 2 skipped / 358 deselected / 69.30s**；收集基线：总 660（core 档 302） | 全部子进程冷启动轻量（host_adapters 仅标准库导入，单例 < 2s）；③ 收集 605 例未整体复跑；Windows junction 注册路径在 codex `--entry` 用例中实际走通（本机权限允许） |
| 2026-10-15 | `P0-04`（用户确认后执行） | `pyproject.toml` full extra 增补 MyTT/akshare-proxy-patch + akshare 口径统一 1.18；技能级 requirements.txt 改 `-r ../../../requirements.txt` 纯引用；`common.py` 新增 `_full_extra_requirements()` 派生归档根 `requirements-full.txt` + `INSTALL.json` 4 新键；门禁新增 3 用例 + INSTALL 用例扩展 | Windows / 本地 `.venv` | 前置核实：根 requirements.txt（uv.lock --no-dev 导出）与 uv.lock 均不含 MyTT/akshare-proxy-patch（此前唯一声明处为技能级手写清单）；定向 6 passed / 5.05s；**P0 `-m core`：303 passed / 2 skipped / 358 deselected / 133.26s**；收集基线：总 663（core 档 305） | **遗留边界：`uv.lock` 未联网重锁**（pyproject full 增补后锁与声明暂不同步，`uv lock` + 重新导出根 requirements.txt 待人工确认）；根 requirements 基础导出本就不含 extras，Release 基础安装不受影响；③ 收集 608 例未整体复跑 |
| 2026-10-15 | `P0-06`（用户确认后执行） | `test_release_delivery_gate.py` 新增第 8 节 4 例（三平台隔离解压与 doctor 自诊断常驻断言 + 源码树零修改守卫 + 构建幂等性）；`verify_release_scope.py` 移除破坏性覆写代码转为只读 | Windows / 本地 `.venv` | 前置验证：跨三平台独立构建解压跑通 doctor exit 0 且 20 技能健康；定向 4 passed / 9.29s；**P0 `-m core`：307 passed / 2 skipped / 358 deselected / 65.77s**；收集基线：总 667（core 档 309） | 旧脚本曾隐蔽覆写 setup.sh/SKILL.md/.gitignore，现已彻底解耦；测试执行前后 4 关键源文件 sha256 零漂移守卫生效；③ 收集 612 例未整体复跑 |
| 2026-10-15 | `P0-05`（用户确认后执行） | 重写 `astock-agent-debate/scripts/setup.sh` 为隔离解释器自检与凭据指引；更新技能说明；新增全部 setup.sh 零污染静态守卫 | Windows / 本地 `.venv` | 定向守卫 1 passed；**P0 `-m core`：308 passed / 2 skipped / 358 deselected / 134.83s，退出码 0**；收集基线：总 668（core 档 310） | setup 不执行全局安装、克隆、LLM/网络试跑或凭据写入；外部 TradingAgents 仅保留为用户自行准备的可选依赖；③ 收集 613 例未整体复跑 |
| 2026-10-15 | `P0-01`（用户确认后执行） | 统一 20 技能自描述调用约定 + 清除 bin/astock 与包外链接 + 新增第 10 节 4 例常驻守卫 | Windows / 本地 `.venv` | 定向 4 passed / 0.80s；**P0 `-m core`：312 passed / 2 skipped / 358 deselected / 54.72s，退出码 0**；收集基线：总 672（core 档 314） | 全包 103 Markdown 零包外链接、零断链、零 bin/astock 引用；19 专业技能与总入口调用口径统一；测试看守常驻；③ 收集 617 例未整体复跑 |

---

## 六、分时执行顺序与全局进度追踪清单 (Execution Sequence & Progress Roadmap)

> **分时调用与断点续传机制**：本节严格将 24 项整改任务编排为 11 个执行步序，按**「执行或规范文档文件 + 任务号」**格式标准化登记，作为跨会话、分时调用、断点续传的权威进度看板。
> **状态标记约定**：
> - `[x]` **已完成**：已完成代码实现并通关常驻门禁，第五节已留存验收证据；
> - `[▶]` **当前就绪 / 下一步优先执行**：前置依赖已全部就绪，作为下次会话或下一步工作的明确起点指针；
> - `[ ]` **待执行**：待前序步骤通过验收后顺次解锁。

### 6.1 全局进度追踪看板 (Progress Dashboard)

| 阶段分类 | 任务范围 | 完成进度 | 阶段状态 | 当前活跃指针 |
| :--- | :--- | :---: | :---: | :--- |
| **阶段 0：基础交付基座** | `P0-01` ~ `P0-07` | **7 / 7 (100%)** | ✅ **已闭环** | 全部门禁全绿（312 passed） |
| **阶段一：P0 交付阻断攻坚** | `P0-08` ~ `P0-10` | **0 / 3 (0.0%)** | 🚧 **当前执行攻坚中** | **`[▶] P0-08`（当前就绪）** |
| **阶段二：P1 双模态安装与升级** | `P1-08` ~ `P1-10` | **0 / 3 (0.0%)** | ⏳ 等待阶段一完成 | 待 `P0-09` 交付安装核心 |
| **阶段三：P1 源码工程质量治理** | `P1-01` ~ `P1-07` | **0 / 7 (0.0%)** | ⏳ 等待排期推进 | `P1-06` 结构对齐先期已打底 |
| **阶段四：P2 文档与通用生态** | `P2-01` ~ `P2-04` | **0 / 4 (0.0%)** | ⏳ 等待最终发版 | `P2-03` 测试映射已先期修正 |
| **全工程总计** | 全套 24 项整改任务 | **7 / 24 (29.2%)** | 🚧 实施推进中 | **唯一执行起点：`[▶] 顺序 ①: P0-08`** |

---

### 6.2 分时顺序执行清单 (11 步详细链路)

#### 阶段一：P0 交付阻断攻坚（底层产物与宿主识别闭环，必须最优先执行）

- [▶] **顺序 ①**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P0-08`**
  - **任务名称**：**Release 产物锚点技能架构与转发壳三级寻址改造**
  - **进度状态**：`[▶] 当前就绪（下一步优先执行）`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §8.1、§4.2
  - **前置依赖**：`P0-01` ~ `P0-07`（已全部达成 ✅）
  - **核心动作**：修改 `tools/packaging/common.py`，构建期将公共 `runtime/`、`assets/`、`references/` 收敛注入总入口 `skills/a-stock-agents/`；升级转发壳模板实现“自定位 ➔ 兄弟定位 `../a-stock-agents/` ➔ 收据定位 `install.json`”；在 `tests/core/test_release_delivery_gate.py` 新增锚点打包与寻址断言。
  - **验收门槛**：单个技能被剥离到独立临时目录时，仍能通过兄弟定位或收据定位唤起 `doctor.py` 并通过 P0 门禁。
  - **执行命令参考**：`.venv/Scripts/python.exe -m pytest tests/core/test_release_delivery_gate.py -q`

- [ ] **顺序 ②**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P0-09`**
  - **任务名称**：**统一安装底层脚本核心 `install.ps1` / `install.sh` 开发**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §8.2、§8.3
  - **前置依赖**：`P0-08`（产物具备锚点技能与三级寻址结构）
  - **核心动作**：编写跨平台安装核心 `install.ps1`（Windows）与 `install.sh`（POSIX），支持 `-Inspect`、`-Agent <list>`、`-Method <link|copy>`、`-Yes` 与 `--json`；在 `%LOCALAPPDATA%/a_stock_agents/`（或 POSIX 数据根）建立专用 `.venv`，安装依赖并落盘 `install.json`（持久化 `python_path` 与 `runtime_root`）。
  - **验收门槛**：在临时沙箱中执行 `install.ps1 -Inspect -Json` 与安装链路，退出码 0，生成的收据包含 20 个入口就绪证明与 SHA256。
  - **执行命令参考**：`powershell -File install.ps1 -Inspect -Json`

- [ ] **顺序 ③**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P0-10`**
  - **任务名称**：**逐技能粒度平级注册与“宿主发现模拟”自动化门禁**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §8.2、§5
  - **前置依赖**：`P0-09`（统一安装脚本具备逐技能挂载能力）
  - **核心动作**：重构宿主注册逻辑，废弃链接整个 `skills/` 的错误行为，改为在宿主技能根创建 20 个平级独立链接（Hermes 写入 `external_dirs`）；在 `tests/core/test_release_delivery_gate.py` 新增模拟门禁，模拟 Codex、Hermes、WorkBuddy 的单层扫描逻辑，**断言 20 个入口检出率 100%**。
  - **验收门槛**：P0 核心门禁 `pytest -m core` 全绿，三宿主发现数全部恒等于 20。**至此 P0 交付阻断项全部闭环！**

---

#### 阶段二：P1 双模态安装交互体验与生命周期（从“能装”到“极佳体验”）

- [ ] **顺序 ④**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P1-08`**
  - **任务名称**：**模态一落地：AI 安装引导提示词与 5 类信息卡片渲染契约**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §8.4、§8.5
  - **前置依赖**：`P0-09`、`P0-10`
  - **核心动作**：在发版说明与快速上手中固化自包含提示词；在总入口 `a-stock-agents/SKILL.md` 中固化安装状态机，在 AIChat / AIWork 中分 5 阶段输出结构化信息卡片（宿主选择、配置登记、安全评估、任务导轨、实战交付）。

- [ ] **顺序 ⑤**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P1-09`**
  - **任务名称**：**模态二落地：终端 TUI 键盘多选导轨菜单开发**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §8.6
  - **前置依赖**：`P0-09`
  - **核心动作**：在 `install.ps1` 与 `install.sh` 中检测 TTY 环境，自动激活控制台交互式菜单：支持光标上下移动、空格勾选、回车确认；展示 Universal 宿主与特有 AI 工具分类；加入 Overwrites 冲突保护。

- [ ] **顺序 ⑥**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P1-10`**
  - **任务名称**：**多版本原子切换与一键回滚升级链实现**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §8.7
  - **前置依赖**：`P0-09`
  - **核心动作**：代码安装路径规范为 `releases/<version>/`，由 `current` 符号链接挂载；实现 `install.ps1 -Update` 与 `-Rollback`；确保升级与回滚全程 100% 隔离用户资产。

---

#### 阶段三：P1 源码工程单一来源治理与自动化看守（开发内聚度收口）

- [ ] **顺序 ⑦**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P1-01` ~ `P1-05`**
  - **任务名称**：**源码单一来源收敛（腾讯解析器、监控模板、指标权威、CLI 双后端合一、死路径清理）**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §2、§3
  - **前置依赖**：P0 门禁保持全绿
  - **核心动作**：取消技能 templates 下的重复下标解析豁免，由 AST 哨兵守住；合并 `ta_entry_monitor`；回测脚本统一复用 `core.indicators` 与 `combo_scorer`；双后端合一。

- [ ] **顺序 ⑧**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P1-06`**
  - **任务名称**：**CLI `--json` 输出结构契约与 `skill list` 输出测试**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §6
  - **前置依赖**：`P1-01` ~ `P1-05`
  - **核心动作**：对 20 个入口逐一进行子进程执行校验，断言标准输出必须为合法 JSON，且包含最低保本价、三级止损、三动作单铁律字段。

- [ ] **顺序 ⑨**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P1-07`**
  - **任务名称**：**引入 GitHub Actions CI 流水线**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/testing-guide.md`](../guidelines/engineering/testing-guide.md) §3.2
  - **前置依赖**：P0 与 P1-06 门禁
  - **核心动作**：建立 Windows + Linux 跨平台自动化测试矩阵，在 PR 和发版时自动跑通 P0 门禁、发布链路检验与隔离解压验收。

---

#### 阶段四：P2 文档口径对齐与通用生态分发（公开发布准备）

- [ ] **顺序 ⑩**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P2-01` ~ `P2-03`**
  - **任务名称**：**统一技能计数口径（20 入口）、README 宿主清单与测试文档映射修正**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/audits/2026-10-16-skill-structure-review.md`](../../audits/2026-10-16-skill-structure-review.md) §4.3
  - **前置依赖**：代码与测试完成
  - **核心动作**：明确统一为“1 个总入口（锚点）+ 19 项专业量化技能”，宿主清单正式包含 WorkBuddy；清理废弃测试映射。

- [ ] **顺序 ⑪**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](eng-skill-suite-delivery-remediation-plan.md) + **`P2-04`**
  - **任务名称**：**独立 Release 仓库发布与 `npx skills add` 通用生态打通**
  - **进度状态**：`[ ] 待执行`
  - **关联规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](../guidelines/engineering/skill-suite-portability-specification.md) §8.1
  - **前置依赖**：`P0-08` ~ `P0-10`、`P2-01` ~ `P2-03`
  - **核心动作**：搭建独立 Release 分发仓库，将经过 `P0-08` 锚点装配的 Release 产物发布，正式支持社区一行命令接入：`npx skills add cvdnn/a-stock-agents -g`。

---

### 6.3 分时断点续传与执行维护守则 (Session Continuity Protocol)

后续分时在不同会话中执行时，智能体与开发者必须严格遵守以下执行守则：
1. **断点寻址**：新会话开始时，通过读取本文档第 6.1 节与 6.2 节寻找 `[▶]` 标记，即可瞬间定位当前唯一的执行起点；
2. **任务实施与测试门禁**：
   - 必须先完成该任务要求的代码改造与用例编写；
   - 必须运行 P0 核心门禁验证（`.venv/Scripts/python.exe -m pytest -m core -q`），确保无回归；
3. **标记推进与证据留痕**：
   - 任务完成后，将当前项标记由 `[▶]` 改为 `[x]`；
   - 将紧随其后的下一顺序项标记由 `[ ]` 改为 `[▶]`；
   - 在第二节矩阵将状态改为 `☑`，在第三节可勾选清单中打勾；
   - 在第五节验收证据表中追加实测命令行、测试数量、耗时与结果边界。

---

## 七、状态维护约定

1. 任务状态变更时，**必须**同时更新第二节矩阵与第三节勾选项，二者不得脱节。
2. 每完成一项，**必须**在第五节证据表追加一行，不得以「本地跑过」代替留痕。
3. 全部 P0 完成后，方可将本计划状态置为「🚧 实施中」并向「✅ 已完成」推进；在 P0 未全绿前，**严禁**声明交付闭环成立。
4. 本计划不复制 SSOT 正文；若需修订目录规则、链接策略或数据根语义，一律修改 SSOT 后回链。