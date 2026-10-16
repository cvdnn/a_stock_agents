# 技能总包交付与安装整改分时执行清单 (Delivery & Installation Execution Roadmap)

- **归属实施计划**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md)
- **权威设计规范 (SSOT)**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md)
- **审查评估报告**：[`docs/audits/2026-10-16-skill-structure-review.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/audits/2026-10-16-skill-structure-review.md)
- **实施状态**：🚧 **实施中**（基座 7/7 完成；阶段一 P0 阻断 3/3 闭环；阶段二 3/3 闭环；阶段三 7/7 闭环；阶段四 0/4 准备中；全局进度 20/24 完成 83.3%；当前就绪指针：`[▶] 顺序 ⑩ (P2-01 ~ P2-03 统一文档与口径)`）

> [!IMPORTANT]
> ### 🔒 看板原子执行与防并发排他规约 (Kanban Atomic Execution & Anti-Race Protocol)
> 为彻底杜绝多个智能体或会话并发执行同一清单任务点、产生代码覆盖冲突或重复消耗算力，所有调用方**必须强制遵守以下原子执行铁律**：
> 1. **原子认领加锁 (Check-out Lock)**：
>    任何会话在扫描看板发现 `[▶]` 并准备启动任务时，**第一步操作必须且只能**先将该任务的 `[▶]` 标记原子替换为排他在途锁：
>    `[🚧 IN_PROGRESS: <session_id> | <YYYY-MM-DDTHH:MM+08:00>]`，并立即保存落盘。同时将顶部看板的活跃指针同步更新为在途状态。
> 2. **防重复认领与防抢跑铁律 (Strict Anti-Duplication & Anti-Race Guard)**：
>    - 若看板中当前**不存在 `[▶]`**（全部为 `[x]` 或已存在 `[🚧 IN_PROGRESS: ...]`），**其他任何会话坚决严禁自行认领、严禁擅自抢跑后续任务、严禁并发执行同一或不同清单任务点**！
>    - 若新会话启动时扫描到看板已存在 `[🚧 IN_PROGRESS: ...]`，**必须立刻终止认领并主动汇报**：“检测到前序任务已在进行中（会话 ID: xxx），严格等待其执行完成”，坚决禁止盲目重入或强行修改同一文件。
> 3. **原子交付与解锁 (Check-in & Unlock)**：
>    仅当该任务的代码改造完成、对应测试门禁与 P0 核心门禁在本地实测全绿（`0 failed`）后，**持有锁的当前会话**才允许将 `[🚧 IN_PROGRESS: ...]` 更新为 `[x] 已完成`，并原子地点亮下一项为唯一的 `[▶]`。
> 4. **死锁恢复与熔断机制 (Deadlock Recovery)**：
>    若持有锁的会话因宿主工具异常崩溃中断且已确认完全退出，后续接管会话**必须在获得用户明确确认或下达接管指令后**，方可解除旧锁、复位或接力该任务。
> 5. **严禁测试后台执行，直接在任务中顺序执行 (Foreground Sequential Gate Execution)**：
>    在看板任务实施与交付门禁验证阶段，**严禁将测试用例或任何验证命令作为后台进程（Background Process / Background Task）挂起异步执行**（严禁触发界面 `Background Process Running` 挂起状态）。所有验证命令必须直接在当前任务交互流中**前台顺序同步执行**。若门禁包含较多子进程或打包用例，必须按流水线分步顺序在前台串行跑通（① 极速离线门禁 ➔ ② 任务改动定向门禁 ➔ ③ 交付链路门禁），步步确认退出码 0，杜绝单命令逃逸至后台。

---

## 一、全局进度追踪看板 (Progress Dashboard)

| 阶段分类 | 任务范围 | 完成进度 | 阶段状态 | 当前活跃指针 |
| :--- | :--- | :---: | :---: | :--- |
| **阶段 0：基础交付基座** | `P0-01` ~ `P0-07` | **7 / 7 (100%)** | ✅ **已闭环** | 全部门禁全绿（312 passed） |
| **阶段一：P0 交付阻断攻坚** | `P0-08` ~ `P0-10` | **3 / 3 (100%)** | ✅ **已闭环** | 全部门禁全绿（328 passed，P0 阻断项全部解除） |
| **阶段二：P1 双模态安装与升级** | `P1-08` ~ `P1-10` | **3 / 3 (100%)** | ✅ **已闭环** | **全额达成（多版本原子切换与一键回滚升级链落地）** |
| **阶段三：P1 源码工程质量治理** | `P1-01` ~ `P1-07` | **7 / 7 (100%)** | ✅ **已闭环** | **全额达成（单一来源治理与跨平台 CI 矩阵落地）** |
| **阶段四：P2 文档与通用生态** | `P2-01` ~ `P2-04` | **0 / 4 (0.0%)** | ⏳ 等待最终发版 | `P2-03` 测试映射已先期修正 |
| **全工程总计** | 全套 24 项整改任务 | **20 / 24 (83.3%)** | 🚧 实施推进中 | **唯一执行起点：`[▶] 顺序 ⑩: P2-01 ~ P2-03`** |

---

## 二、已完成基座回顾（阶段 0，100% 达成）

| 状态 | 任务号 | 核心交付点 | 门禁与证据 |
| :-: | :--- | :--- | :--- |
| [x] | `P0-01` | 统一 20 技能自描述调用约定，彻底清除 `bin/astock` 与包外相对链接 | `test_release_delivery_gate.py` 第 10 节 4 例入 core 档全绿 |
| [x] | `P0-02` | 新增发布链路 P0 门禁（frontmatter 20 参数化 / 启动器 / 自诊断 / 打包行为） | 36 例入 core 档全绿 |
| [x] | `P0-03` | 宿主注册红线与三平台 shim 加哨兵（拒绝注册开发源、bundle 缺失校验） | 第 7 节 10 例入 core 档全绿 |
| [x] | `P0-04` | 依赖声明收敛单一来源（`pyproject.toml`）+ `INSTALL.json` 补安装说明 | 3+1 门禁用例入 core 档全绿 |
| [x] | `P0-05` | 安装脚本去宿主污染（隔离解释器探测、凭据进 `local/settings/.env`） | 静态守卫用例入 core 档全绿 |
| [x] | `P0-06` | 隔离解压验收常驻化（跨三平台独立构建解压跑通 doctor exit 0） | 第 8 节 4 例入 core 档全绿 |
| [x] | `P0-07` | 修复目录迁移后 p1 既有腐化（docs 端点硬编码、备份原型声明、旧路径） | ③ 复测 558 passed / 0 failed 全绿 |

---

## 三、分时顺序执行清单 (11 步详细链路)

### 阶段一：P0 交付阻断攻坚（底层产物与宿主识别闭环，必须最优先执行）

#### [x] 顺序 ①
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P0-08`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.1、§4.2
- **任务名称**：**Release 产物锚点技能架构与转发壳三级寻址改造**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：`P0-01` ~ `P0-07`（已全部达成 ✅）
- **核心动作**：
  1. 修改 `tools/packaging/common.py`，构建期将公共 `runtime/`、`assets/`、`references/` 收敛注入总入口 `skills/a-stock-agents/`（锚点技能）；
  2. 升级转发壳模板实现“自定位 ➔ 兄弟定位 `../a-stock-agents/` ➔ 系统收据定位 `install.json`”；
  3. 在 `tests/core/test_release_delivery_gate.py` 新增锚点打包与寻址断言。
- **验收门槛**：单个技能被剥离到独立临时目录时，仍能通过兄弟定位或收据定位唤起 `doctor.py` 并通过 P0 门禁。
- **执行命令参考**：`.venv/Scripts/python.exe -m pytest tests/core/test_release_delivery_gate.py -q`

---

#### [x] 顺序 ②
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P0-09`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.2、§8.3
- **任务名称**：**统一安装底层脚本核心 `install.ps1` / `install.sh` 开发**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：`P0-08`（产物具备锚点技能与三级寻址结构）
- **核心动作**：
  1. 编写跨平台安装核心 `install.ps1`（Windows）与 `install.sh`（POSIX），支持 `-Inspect`、`-Agent <list>`、`-Method <link|copy>`、`-Yes`、`-Doctor` 与 `--json`；
  2. 在 `%LOCALAPPDATA%/a_stock_agents/`（或 POSIX 数据根）建立专用 `.venv`，安装依赖并落盘 `install.json`（持久化 `python_path`、`bundle_root`、`runtime_root`、`anchor_root` 与 20 项技能证明及 SHA256）；
  3. 构建器 `tools/packaging/common.py` 将 `install.ps1` 与 `install.sh`（0o755 执行位）随包打包至 Release 归档根，并在 `INSTALL.json` 声明 `installer` 键；
  4. 新增 `test_release_delivery_gate.py` 第 12 节 5 项常驻门禁（参数化探测、隔离沙箱安装、收据自检冒烟、Release 归档随包与执行位、安全零宿主污染守卫）。
- **验收门槛**：在临时沙箱中执行 `install.ps1 -Inspect -Json` 与安装链路，退出码 0，生成的收据包含 20 个入口就绪证明与 SHA256。
- **执行命令参考**：`powershell -File install.ps1 -Inspect -Json`

---

#### [x] 顺序 ③
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P0-10`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.2、§5
- **任务名称**：**逐技能粒度平级注册与“宿主发现模拟”自动化门禁**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：`P0-09`（统一安装脚本具备逐技能挂载能力）
- **核心动作**：
  1. 重构宿主注册逻辑，废弃链接整个 `skills/` 的错误行为，在 `tools/host_adapters/references.py` 与 `host.py` 实现 `register_skills` 与 `unregister_skills`（为 20 个入口分别创建平级独立链接，并在 Hermes 支持写入 `external_dirs`）；
  2. 升级 `install.ps1` 与 `install.sh` 的 `-Agent` 挂载逻辑，统一改为逐技能粒度平级注册与卸载，写入 `.a-stock-suite.json` 套件收据；
  3. 在 `tests/core/test_release_delivery_gate.py` 新增第 13 节 6 例门禁，分别针对 Codex（单层扫描 + plugin 校验）、Hermes（`skills.external_dirs` 扫描 + 本地平级目录）与 WorkBuddy（单层扫描）进行模拟；
  4. 验证 H1 缺陷负向对照（嵌套链接 0 发现）与 P0-10 修复正向对照（单层平级扫描 20 发现，100% 检出）。
- **验收门槛**：P0 核心门禁 `pytest -m core` 全绿（328 passed / 2 skipped / 225.90s，退出码 0），三宿主模拟发现数恒等于 20。**至此阶段一 P0 交付阻断项全部闭环！**

---

### 阶段二：P1 双模态安装交互体验与生命周期（从“能装”到“极佳体验”）

#### [x] 顺序 ④
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-08`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.2、§5.2
- **任务名称**：**模态一落地：AI 安装引导提示词与 5 类信息卡片渲染契约**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：`P0-09`、`P0-10`（阶段一 P0 交付阻断项已全部闭环 ✅）
- **核心动作**：
  1. 在 `README.md`、`docs/quickstart.md`、`skill-suite-portability-specification.md` 固化标准化 AI Copilot Bootstrap Prompt，明确 Release 仓库地址、安装器调用规范、强制 `--json` 与 5 阶段 SOP 流水线；
  2. 在总入口 `skill_bundle/skills/a-stock-agents/SKILL.md` 固化 5 阶段状态机（探测 ➔ 交互 ➔ 审计 ➔ 执行 ➔ 交付）与 5 类信息卡片渲染契约（卡片 1 宿主选择、卡片 2 数据源与凭据、卡片 3 安全审计、卡片 4 批量流水线任务导轨、卡片 5 交付实战测试）；
  3. 同步扩展 `skill_bundle/references/prompts/aichat_system_prompt.md` 意图路由；
  4. 在 `tests/core/test_release_delivery_gate.py` 新增第 14 节 3 例门禁（提示词文档一致性、5类信息卡片渲染契约、总入口调用约定与不变量保护）。
- **验收门槛**：3 例门禁入 core 档全绿（`test_release_delivery_gate.py` 76 passed / 2 skipped / 171.33s 全绿）。

---

#### [x] 顺序 ⑤
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-09`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.6、§8.3
- **任务名称**：**模态二落地：终端 TUI 键盘多选导轨菜单开发与 Overwrites 冲突保护**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：`P0-09`、`P0-10`
- **核心动作**：
  1. 在 `install.ps1` 与 `install.sh` 中检测 TTY 终端环境（及 `-Tui` 显式开关），自动激活控制台交互式多选导轨菜单：支持 `↑`/`↓`/`k`/`j` 光标移动、`Space` 切换选中、`Enter` 确认、`m` 切换链接/复制、`a` 全选/取消、`q`/`Esc` 退出；
  2. 菜单分类明确分离 Universal agents（`.agents/skills`）与 Additional agents（Hermes、WorkBuddy、Codex）；
  3. 增加 Overwrites 冲突保护哨兵：检测宿主目标路径是否已存在非链接物理目录，默认 fail-closed（exit 1，`OVERWRITE_CONFLICT`）拒绝强行覆写破坏用户既有资产，支持 `-Force` / `--force` 显式豁免；
  4. `-Inspect -Json` 与安装收据增补 `overwrites_count` 与 `conflicts` 机器结构化字段；
  5. 在 `tests/core/test_release_delivery_gate.py` 新增第 15 节 5 项常驻门禁（TUI 导轨契约、Overwrites 物理目录冲突拦截、Force 强行覆盖、Junction 既有挂载兼容、Inspect 冲突字段审计）。
- **验收门槛**：第 15 节 5 例门禁入 `core` 档全绿（`test_release_delivery_gate.py` 81 passed / 2 skipped，P0 核心门禁 336 passed / 2 skipped / 0 failed 全绿）。
- **并发历史与冲突化解记录**：2026-10-16 17:08 CST 曾发生会话 `f476776b` 与 `26492035` 并发认领撞车；`26492035` 率先完成并通过 5 例门禁合并落地；`f476776b` 检测到外部合并后自适应平滑让步，顺延接力 `P1-10`。经全量核心门禁验证（342 passed），双会话成果完全融合，无代码覆盖撕裂。

---

#### [x] 顺序 ⑥
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-10`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.7
- **任务名称**：**多版本原子切换与一键回滚升级链实现**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：`P0-09`（统一安装脚本具备多版本与收据基础）
- **核心动作**：
  1. 代码安装路径规范化为 `$TARGET_DATA_ROOT/releases/<version>/`，由 `$TARGET_DATA_ROOT/current` 符号链接/Junction 挂载；宿主技能注册统一通过 `current/skills/<id>` 链式寻址，达成零拷贝瞬时生效；
  2. 实现 `install.ps1` 与 `install.sh` 的 `-Update [-Version <tag>] [-SourceDir <dir>]`：支持安全解压/部署新版本至 `releases/<new_version>` ➔ 完整性验证 ➔ `doctor.py` 冒烟守卫 ➔ 冒烟成功原子重定向 `current` Junction ➔ 更新收据（登记 `previous_version`、`updated_at`、`current_target` 并重算摘要）；若冒烟失败坚决熔断，不切换 `current`；
  3. 实现 `install.ps1` 与 `install.sh` 的 `-Rollback`：校验上一版本完整性 ➔ 原子重定向 `current` Junction 瞬时回退至上一可用版本 ➔ 交换版本并登记 `rolled_back_at`；无历史版本时阻断；
  4. 用户资产物理隔离铁律：升级与回滚全程严禁触碰数据根下的 `output/`、`local/`、`log/`，自选股 CSV、报告与凭据比特级 100% 留存；
  5. 在 `tests/core/test_release_delivery_gate.py` 新增第 16 节 6 项常驻门禁（多版本目录结构与隔离布局、升级与零拷贝切换、一键回滚、冒烟失败熔断阻断、私有数据 100% 留存验证、无前序版本安全拦截）。
- **验收门槛**：第 16 节 6 例门禁入 `core` 档全绿（`test_release_delivery_gate.py` 87 passed / 2 skipped，P0 核心门禁 342 passed / 2 skipped / 0 failed 全绿）。**至此阶段二 P1 双模态安装与升级任务 100% 闭环！**
- **接力执行与归档记录**：会话 `f476776b` 在 `P1-09` 被合并后主动顺延认领本任务，历时 35 分钟完整交付并通关 342 例核心门禁。

---

### 阶段三：P1 源码工程单一来源治理与自动化看守（开发内聚度收口）

#### [x] 顺序 ⑦
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-01` ~ `P1-05`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §2、§3
- **任务名称**：**源码单一来源收敛（腾讯解析器、监控模板、指标权威、CLI 双后端合一、死路径清理）**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：P0 门禁与阶段二门禁保持全绿
- **核心动作**：
  1. `P1-01`：将全工程独立腾讯快照下标解析收敛至 `core.data.tencent_fields` 单一来源，技能目录 0 处独立下标解析；移除 `test_commands_suite.py` 中 `templates` 豁免，并在 `tests/core/test_data_suite.py` 增加 AST 级哨兵 `test_no_unauthoritative_tencent_parsing` 严格常驻防守；
  2. `P1-02`：将强版本能力（三档信号 [RED]/[ORANGE]/[GREEN]、入场回踩信号、状态持久化与去重、每日重置、复用 `core.data.tencent_fields`）合并进 `runtime/core/multi_agent/templates/ta_entry_monitor.py.template`，物理删除 `astock-agent-debate/assets/templates/ta_entry_monitor.py` 副本，修正根路径探测，移除指向已删除旧技能的死回退路径；
  3. `P1-03`：重构 `local_ma20_backtest.py`，移除手写 MA/EMA/评分/回测指标，改为统一复用 `core.indicators.technical_indicators`、`core.models.combo_scorer` 与 `core.paper_trading.backtest_metrics`，仅保留轻量离线适配层；
  4. `P1-04`：`cmd_pool_audit` 增加对 `--data`（池路径）参数支持，`skills/astock-pool-audit/scripts/pool_audit.py` 彻底重构为薄转发壳（对齐公共 CLI 后端）；
  5. `P1-05`：修复 `position_manager.py`、`investment_report.py`、`predictor.py` 中的死脚本路径（`A_DATA_DIR`、`fetch_patched.py`），修正 `model_cmds.py` 中打印的陈旧监控脚本路径。
- **验收门槛**：`test_data_suite.py`（含新 AST 哨兵 12 例）、`test_commands_suite.py`（5 例 forwarders 校验无豁免）、`test_strategy_suite.py`、`test_models_suite.py`、`test_paper_trading_suite.py` 等门禁实测全绿（0 failed）。

---

#### [x] 顺序 ⑧
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-06`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §6
- **任务名称**：**CLI `--json` 输出结构契约与 `skill list` 输出测试**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：`P1-01` ~ `P1-05`
- **核心动作**：
  1. 修复报告生成器 `generate_simple_report` 的标准输出污染，增加 `verbose=False` 开关，确保 `--json` 输出首尾字符严格为纯净 JSON（消除 `报告已保存: ...` 污染）；
  2. 修复 `portfolio_cmds.py` 中的 `cmd_skill_list`，优先读取 `core.workspace.SKILLS_ROOT`，在纯文本下输出 20 个入口，在 `--json` 下输出包含 `total=20` 与完整清单的结构体，与 `skills_manifest.json`（19项业务+1项锚点）严格双向对齐；
  3. 在 `tests/core/test_commands_suite.py` 新增子命令并发 `--json` 契约与三原则断言；
  4. 在 `tests/core/test_release_delivery_gate.py` 新增第 17 节 3 项常驻门禁（`test_skill_list_discovery_and_manifest_alignment`、`test_cli_json_zero_pollution_contract`、`test_cli_json_trade_principles_structural_contract`），严格校验最低保本价、三级止损（-3%, -5%, -8%）与三场景即时动作单（冲高/震荡/急跌）铁律字段。
- **验收门槛**：第 17 节 3 例门禁实测通过，`test_commands_suite.py` 7 例全绿，P0 核心门禁（346 passed / 2 skipped / 0 failed）全绿。

---

#### [x] 顺序 ⑨
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-07`**
- **关联权威规范**：
  [`docs/guidelines/engineering/testing-guide.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/testing-guide.md) §3.2
- **任务名称**：**引入 GitHub Actions CI 流水线**
- **进度状态**：`[x] 已完成（2026-10-16 实测通过）`
- **前置依赖**：P0 与 P1-06 门禁（已全部达成 ✅）
- **核心动作**：
  1. 建立 `.github/workflows/ci.yml` 跨平台自动化测试矩阵（`ubuntu-latest` + `windows-latest` × Python 3.10/3.11/3.12）；
  2. 声明 PR 与 push（main/tags v*）触发条件、concurrency 自动取消陈旧构建与 least-privilege 权限 (contents: read)；
  3. 流水线覆盖 ① P0 核心门禁（`pytest -m core`）、发布交付链路门禁与隔离解压验收（`test_release_delivery_gate.py`）、Release 打包与 doctor 诊断冒烟校验（`doctor.py`）、以及各平台专用安装器冒烟（Linux `install.sh -Inspect -Json` 与 Windows `install.ps1 -Inspect -Json`）；
  4. 在 `tests/core/test_release_delivery_gate.py` 新增第 18 节 3 项常驻自动化门禁（CI 结构与 YAML 契约、矩阵与测试门禁覆盖、零敏感与主机绝对路径守卫）。
- **验收门槛**：第 18 节 3 例门禁全绿，P0 核心门禁（349 passed / 2 skipped / 0 failed）全绿。**至此阶段三 P1 源码工程质量治理 100% 闭环！**

---

### 阶段四：P2 文档口径对齐与通用生态分发（公开发布准备）

#### [▶] 顺序 ⑩
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P2-01` ~ `P2-03`**
- **关联权威规范**：
  [`docs/audits/2026-10-16-skill-structure-review.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/audits/2026-10-16-skill-structure-review.md) §4.3
- **任务名称**：**统一技能计数口径（20 入口）、README 宿主清单与测试文档映射修正**
- **进度状态**：`[▶] 当前就绪（下一步优先执行）`
- **前置依赖**：代码与测试完成
- **核心动作**：明确统一为“1 个总入口（锚点）+ 19 项专业量化技能”，宿主清单正式包含 WorkBuddy；清理废弃测试映射。

---

#### [ ] 顺序 ⑪
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P2-04`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.1
- **任务名称**：**独立 Release 仓库发布与 `npx skills add` 通用生态打通**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：`P0-08` ~ `P0-10`、`P2-01` ~ `P2-03`
- **核心动作**：搭建独立 Release 分发仓库，将经过 `P0-08` 锚点装配的 Release 产物发布，正式支持社区一行命令接入：`npx skills add cvdnn/a-stock-agents -g`。

---

## 四、分时断点续传与执行维护守则 (Session Continuity Protocol)

后续分时在不同会话中执行时，智能体与开发者必须严格遵守以下执行守则：
1. **断点寻址**：新会话开始时，通过读取本文档第一节与第三节寻找 `[▶]` 标记，即可瞬间定位当前唯一的执行起点；
2. **任务实施与测试门禁（严禁后台执行，直接在任务中顺序执行）**：
   - 必须先完成该任务要求的代码改造与用例编写；
   - **严禁后台执行**：必须直接在当前任务中前台顺序执行门禁验证（如先跑极速离线内核门禁，再跑本任务定向门禁，前台即时确认退出码 0），确保无回归；严禁挂起后台进程；
3. **标记推进与证据留痕**：
   - 任务完成后，将本文档及主计划中的当前项标记由 `[▶]` 改为 `[x]`；
   - 将紧随其后的下一顺序项标记由 `[ ]` 改为 `[▶]`；
   - 在主计划 `eng-skill-suite-delivery-remediation-plan.md` 的第二节矩阵将状态改为 `☑`，在第三节可勾选清单中打勾；
   - 在主计划第五节验收证据表中追加实测命令行、测试数量、耗时与结果边界。
