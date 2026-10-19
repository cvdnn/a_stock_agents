# 技能总包交付与「1 + 6」生产级投研重构分时执行清单 (Delivery & Skill Consolidation Execution Roadmap)

- **归属实施计划**：
  - 第一期（交付与安装闭环）：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md)
  - 第二期（「1 + 6」投研技能精简与极速测试重构）：[`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) (`SPEC-SKILL-002`)
- **权威设计规范 (SSOT)**：
  - [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md)（含 §9 专业机构股票投研六步闭环与符合性评估规范）
  - [`docs/specs/engineering/spec-skill-1plus6-consolidation-and-test-rearchitecture.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/spec-skill-1plus6-consolidation-and-test-rearchitecture.md)
- **审查评估报告**：
  - [`docs/audits/2026-10-16-skill-structure-review.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/audits/2026-10-16-skill-structure-review.md)
  - [`docs/audits/2026-10-19-skill-comprehensive-evaluation-and-governance-audit.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/audits/2026-10-19-skill-comprehensive-evaluation-and-governance-audit.md)
- **实施状态**：🚀 **第一期 24/24 已圆满闭环；第二期 `SPEC-SKILL-002`（`S2-01` ~ `S2-10`）推进中，当前唯一活跃指针：`[▶] 顺序 ⑮ (S2-04)`**

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
>    仅当该任务的代码改造完成、通过 C1~C6 投研符合性评估、且对应测试门禁在本地前台顺序实测全绿（`0 failed`）后，**持有锁的当前会话**才允许将 `[🚧 IN_PROGRESS: ...]` 更新为 `[x] 已完成`，并原子地点亮下一项为唯一的 `[▶]`。
> 4. **死锁恢复与熔断机制 (Deadlock Recovery)**：
>    若持有锁的会话因宿主工具异常崩溃中断且已确认完全退出，后续接管会话**必须在获得用户明确确认或下达接管指令后**，方可解除旧锁、复位或接力该任务。
> 5. **严禁测试后台执行，直接在任务中顺序执行 (Foreground Sequential Gate Execution)**：
>    在看板任务实施与交付门禁验证阶段，**严禁将测试用例或任何验证命令作为后台进程（Background Process / Background Task）挂起异步执行**（严禁触发界面 `Background Process Running` 挂起状态）。所有验证命令必须直接在当前任务交互流中**前台顺序同步执行**。

---

## 一、全局进度追踪看板 (Progress Dashboard)

| 阶段分类 | 任务范围 | 完成进度 | 阶段状态 | 当前活跃指针 |
| :--- | :--- | :---: | :---: | :--- |
| **第一期（阶段 0 ~ 阶段四）：交付与安装闭环** | `P0-01` ~ `P2-04` | **24 / 24 (100%)** | ✅ **已闭环** | 顺序 ① ~ ⑪ 全部完成（358 例门禁全绿） |
| **第二期·阶段五：底层 6 大支撑引擎缺口闭合** | `S2-01` ~ `S2-03` | **3 / 3 (100%)** | ✅ **已闭环** | 顺序 ⑫ ~ ⑭ 全部完成（S2-01~S2-03） |
| **第二期·阶段六：「1 + 6」生产级投研技能物理精简** | `S2-04` ~ `S2-07` | **0 / 4 (0%)** | ⏳ **推进中** | **`[▶] 顺序 ⑮ (S2-04)`** |
| **第二期·阶段七：极速测试重构与 WebAPI 独立分仓** | `S2-08` ~ `S2-10` | **0 / 3 (0%)** | ⏸️ **等待前序** | 等待 `S2-07` 完成解锁 |
| **全工程总计（第一期 + 第二期）** | 24 + 10 = 34 项任务 | **27 / 34 (79.4%)** | 🚀 **分时推进中** | **当前唯一入口：`[▶] 顺序 ⑮ (S2-04)`** |


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

#### [x] 顺序 ⑩
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P2-01` ~ `P2-03`**
- **关联权威规范**：
  [`docs/audits/2026-10-16-skill-structure-review.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/audits/2026-10-16-skill-structure-review.md) §4.3
- **任务名称**：**统一技能计数口径（20 入口）、README 宿主清单与测试文档映射修正**
- **进度状态**：`[x] 已完成（2026-10-19 实测通过）`
- **前置依赖**：代码与测试完成
- **核心动作**：
  1. `P2-01`：统一 `README.md`、`docs/index.md`、`docs/guidelines/architecture/web-aichat-architecture.md` 与 `tests/README.md` 计数口径为“19 项专业量化技能体系（+1 锚点总入口，共 20 个入口）”，在表格与架构图中补齐缺失的全部 20 个入口；
  2. `P2-02`：在宿主集成指南中正式增加 WorkBuddy，将第七节产品路线图中与 SSOT 规范矛盾的「摆脱第三方 AI 终端工具/宿主依赖」口径彻底修正对齐为「可选的 Web 辅助工作台与技能治理控制台」；
  3. `P2-03`：清理 `pyproject.toml` 中的 `testpaths` 死条目（`skill_bundle/skills`），更新 `tests/README.md` 与 `testing-guide.md` 基线收集数至实测 714（core 354）；
  4. 在 `tests/core/test_release_delivery_gate.py` 新增第 19 节「P2 文档与口径一致性常驻门禁」（3 例用例：`test_readme_and_docs_skill_count_alignment`、`test_readme_host_list_and_roadmap_alignment`、`test_testing_guide_and_test_readme_baseline_alignment`）。
- **验收门槛**：第 19 节 3 例自动化门禁实测全绿（0.59s），`test_docs_suite.py`（4 例）、`test_skill_suite_layout.py`（8 例）与 P0 核心离线极速门禁（244 例）实测全绿（0 failed）。

---

#### [x] 顺序 ⑪
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P2-04`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.1、§8.4
- **任务名称**：**独立 Release 仓库发布与 `npx skills add` 通用生态打通**
- **进度状态**：`[x] 已完成（2026-10-19 实测通过）`
- **前置依赖**：`P0-08` ~ `P0-10`、`P2-01` ~ `P2-03`（已全部达成 ✅）
- **核心动作**：
  1. 开发 `tools/packaging/publish_release.py` 发版与导出工具，支持导出标准规范的 Release 分发目录结构（包含 `skills/`、锚点总入口、19 个专业技能、`.codex-plugin/plugin.json`、`install.ps1`/`install.sh` 及全文件 `SHA256SUMS`），并提供 Git Release 孤立分支同步接口；
  2. 升级 `tools/packaging/common.py`，在 Release 归档元数据与 `INSTALL.json` 中注入 `universal_skills: skills`、`codex_plugin: .codex-plugin/plugin.json` 与 `ecosystem_command: npx skills add cvdnn/a-stock-agents -g`，并在归档根同步纳入 `.codex-plugin/plugin.json` 与 `README.md`；
  3. 编写 `docs/guidelines/engineering/release-distribution-guide.md`，并在 `README.md`、`docs/quickstart.md` 明确增加第四安装通道「通用 Skills CLI 一键接入」指引；
  4. 在 `.github/workflows/ci.yml` 跨平台矩阵增补 `publish_release.py --dry-run --json` 自动化打包验证步骤；
  5. 在 `tests/core/test_release_delivery_gate.py` 新增第 20 节常驻自动化门禁（4 例用例：`test_release_distribution_tree_export_and_json_contract`、`test_release_distribution_npx_skills_add_discovery_simulation`、`test_archive_standard_release_root_and_codex_plugin`、`test_publish_release_cli_smoke_and_zero_pollution`）。
- **验收门槛**：第 20 节 4 例用例实测全绿（34.89s），`test_skill_suite_layout.py` 与 `test_docs_suite.py` 12 例实测全绿（5.78s），极速离线核心门禁 244 例实测全绿（36.21s），发布交付链路 102 例门禁实测全绿（100 passed, 2 skipped / 317.47s）。**至此阶段四与全工程 24 项整改任务 100% 圆满闭环！**

---

### 阶段五（`SPEC-SKILL-002` Phase 1）：底层 6 大技术支撑引擎缺口闭合与循证底座升级

#### [x] 顺序 ⑫
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-01`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §9.1、§9.2、§9.4
- **任务名称**：**统一 `EvidenceEnvelope` 溯源信封 + 修复 G1/G2/G4（CLI 参数、真实双金叉与动态意图路由）**
- **进度状态**：`[x] 已完成（2026-10-19 实测通过：15 passed / 0 failed / 36.32s）`
- **前置依赖**：阶段四已完成 ✅
- **核心动作**：
  1. 在 `skill_bundle/runtime/core/` 新增统一循证溯源信封构造器 `build_evidence_meta(...)`，强制输出 `as_of_trading_day`、`quote_source`、`kline_bars_count`、`watermark_ready`、`fee_rule_ssot`；
  2. **修复 G1**：升级 `core/cli.py` 中 `action` 子命令参数解析，同时兼容 `astock action 600519`、`astock action --code 600519` 与 `astock action plan --code 600519`；
  3. **修复 G2**：升级 `core/execution/tools.py::_sync_astock_strategy_macd`，接入 `technical_indicators.second_golden_cross(klines)` 真实双波谷极值对比算法；
  4. **修复 G4**：升级 `core/execution/tools.py::_sync_astock_meta_routing`，接入 `IntentEvaluator.parse_user_query` 动态意图分流。
- **验收门槛**：C2/C3 符合性核验通过，前台顺序执行 `pytest tests/core/test_indicators.py tests/core/test_commands_suite.py -q` 全绿（`0 failed`）。

---

#### [x] 顺序 ⑬
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-02`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §9.1（阶段 ③ 择时定买 & 阶段 ⑤ 仓位风控）、§9.2
- **任务名称**：**实现退哥短线算法 `tuige.py` + 250 日同类信号历史胜率锚 + 修复 G3（五步真实 MA 股池审计）**
- **进度状态**：`[x] 已完成（2026-10-19 实测通过：29 passed / 0 failed / 5.85s）`
- **前置依赖**：`S2-01` 已达成 ✅
- **核心动作**：
  1. **修复 G6（退哥短线代码化）**：新增 `core/strategy/tuige.py`，实现涨停基因、缩量回踩 MA5/MA10、龙头首阴反包与连板接力纯 Python 判定引擎；
  2. **内建 250 日同类信号历史胜率锚（C4）**：在战法输出层自动回溯该股近 250 日同类买点的触发次数、T+5 胜率、盈亏比与 45bps 成本过滤结论；
  3. **修复 G3（五步真实 MA 股池审计）**：升级 `pool_manager.py` 与 `cmd_pool_audit`，重算真实 `MA5/10/20/60` 并检测止损跌破与均线偏离失效标的。
- **验收门槛**：C3/C4/C6 符合性核验通过，前台顺序执行 `pytest tests/core/test_strategy_suite.py tests/core/test_pool_schema.py -q` 全绿（`0 failed`）。

---

#### [x] 顺序 ⑭
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-03`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §9.1（阶段 ④ 穿透体检 & 阶段 ⑥ 回测验证）、§9.2
- **任务名称**：**实现滚动样本外回测（Rolling OOS）与过拟合三重警报 + 修复 G5（统一研报税费与三级止损口径）**
- **进度状态**：`[x] 已完成（2026-10-19 实测通过：22 passed / 0 failed / 64.00s）`
- **前置依赖**：`S2-02` 已达成 ✅
- **核心动作**：
  1. **修复 G6（样本外回测代码化）**：升级 `core/paper_trading/` 与 `backtest_cmds.py` 支持 `--oos` 滚动样本外检验，内建过拟合三重警报（`Sharpe > 3.5`、`WinRate > 75%`、`IS-OOS 衰减 > 50%`）；
  2. **修复 G5（费率与止损 SSOT）**：统一 `report_generator.py` 与 `investment_report.py` 费率（万 2.5 且最低 5 元 + 0.05% 印花税 + 过户费 + `math.ceil` 分位进位）与 `-3%/-5%/-8%` 三级止损。
- **验收门槛**：C2/C4/C6 符合性核验通过，前台顺序执行 `pytest tests/core/test_paper_trading_suite.py tests/core/test_robust_kline_and_report_html.py tests/core/test_commands_suite.py -q` 全绿（`22 passed / 0 failed`）。

---

### 阶段六（`SPEC-SKILL-002` Phase 2）：「1 + 6」生产级股票投研技能物理精简与网关重塑

#### [▶] 顺序 ⑮
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-04`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §9.1（阶段 ① 看盘知势、阶段 ② 选股立池、阶段 ③ 择时定买）
- **任务名称**：**物理构建前三大生产级投研技能（`astock-market-data`、`astock-smart-screener`、`astock-tactical-signals`）**
- **进度状态**：`[▶] 就绪待执行（启动时必须先原子加锁为 [🚧 IN_PROGRESS: <session_id> | <时间>]）`
- **前置依赖**：`S2-03` 已达成 ✅

- **核心动作**：
  1. 构建 `skill_bundle/skills/astock-market-data/`（吸收 `data-feed` + 大盘五维健康度 `market`）；
  2. 构建 `skill_bundle/skills/astock-smart-screener/`（吸收 `screener-5a` + `selection-model` + `quant-engine`）；
  3. 构建 `skill_bundle/skills/astock-tactical-signals/`（吸收 `strategy-mainboard` + `strategy-macd` + `strategy-chenxiaoqun` + `strategy-tuige`）；
  4. 每个技能配备合规 `SKILL.md`、精选 `references/` 与三级寻址 SSOT 转发壳。
- **验收门槛**：3 个新技能通过 C1~C6 符合性核验，Frontmatter、相对链接与转发壳自检通过。

---

#### [ ] 顺序 ⑯
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-05`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §9.1（阶段 ④ 穿透体检、阶段 ⑤ 仓位风控、阶段 ⑥ 回测验证、总控锚点）
- **任务名称**：**物理构建后三大生产级投研技能（`astock-deep-diagnose`、`astock-portfolio-action`、`astock-paper-backtest`）及升级 `a-stock-agents`**
- **进度状态**：`[ ] 等待 S2-04 完成解锁`
- **前置依赖**：`S2-04`
- **核心动作**：
  1. 构建 `skill_bundle/skills/astock-deep-diagnose/`（吸收 `platform-evaluate` + `agent-debate` + `report-html` + `report-archive`，内建金字塔结论先行与双向证据链）；
  2. 构建 `skill_bundle/skills/astock-portfolio-action/`（吸收 `action-execution` + `pool-dashboard` + `pool-audit` + 凯利头寸管理）；
  3. 构建 `skill_bundle/skills/astock-paper-backtest/`（吸收 `trade-paper` + `backtest-multi` + `model-validation`）；
  4. 升级总控锚点 `skill_bundle/skills/a-stock-agents/SKILL.md`（吸收 `meta-routing` + `knowledge-tips`，对齐 `1 + 6` 路由矩阵与 5 阶段卡片契约）。
- **验收门槛**：后 3 个专业技能与总控锚点通过 C1~C6 符合性核验。

---

#### [ ] 顺序 ⑰
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-06`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §9.3
- **任务名称**：**物理清退旧 19 技能目录 + 升级 `skills_manifest.json`、`SkillRegistry`（含旧别名兼容）、`cli.py`、`tools.py` 与 `doctor.py`**
- **进度状态**：`[ ] 等待 S2-05 完成解锁`
- **前置依赖**：`S2-05`
- **核心动作**：
  1. 物理删除 `skill_bundle/skills/` 下已被吸收的旧 19 个技能目录，确保持久化目录精确为 `1 + 6`（共 7 个）；
  2. 更新 `skills_manifest.json` 为 6 项核心业务技能（含 `research_stage` 与 `legacy_aliases`）；
  3. 升级 `SkillRegistry`、`tools.py`、`cli.py`、`cmd_skill_list` 与 `doctor.py`，内置 `LEGACY_SKILL_ALIASES` 100% 兼容旧 19 个技能名调用。
- **验收门槛**：前台运行 `python skill_bundle/runtime/doctor.py --json` 输出 `total_skills: 7`, `business_skills: 6`, `is_healthy: true`。

---

#### [ ] 顺序 ⑱
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-07`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §4、§6、§8、§9
- **任务名称**：**同步升级 Release 打包器、跨平台安装器（`install.ps1`/`install.sh`）与全仓规范文档口径（`1 + 6 = 7` 入口）**
- **进度状态**：`[ ] 等待 S2-06 完成解锁`
- **前置依赖**：`S2-06`
- **核心动作**：
  1. 升级 `tools/packaging/common.py`、`publish_release.py`、`install.ps1`、`install.sh` 对齐 `1 + 6`（7 入口）校验；
  2. 更新 `AGENTS.md`、`README.md`、`docs/index.md`、`docs/quickstart.md`、`skill-suite-portability-specification.md` 中的技能清单表与计数口径。
- **验收门槛**：前台运行 `python tools/packaging/publish_release.py --dry-run --json` 返回 `skills_count: 7, business_skills: 6, status: "success"`。

---

### 阶段七（`SPEC-SKILL-002` Phase 3）：极速测试体系重构、WebAPI 独立分仓与前端测试清退

#### [ ] 顺序 ⑲
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-08`**
- **关联权威规范**：
  [`docs/guidelines/engineering/testing-guide.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/testing-guide.md) §9.1、§9.2
- **任务名称**：**物理清退前端/浏览器测试（`tests/frontend/` & `tests/browser/`）+ 独立构建 `tests/webapi/`（4 大高内聚后端 API 模块）**
- **进度状态**：`[ ] 等待 S2-07 完成解锁`
- **前置依赖**：`S2-07`
- **核心动作**：
  1. 物理删除 `tests/frontend/`、`tests/browser/` 与 `tests/server/test_browser_e2e_security.py`；
  2. 建立 `tests/webapi/`（含懒加载 `tests/webapi/conftest.py` 及 `test_webapi_auth_and_session.py`、`test_webapi_market_and_sync.py`、`test_webapi_selection_api.py`、`test_webapi_agent_dispatch.py` 4 个模块），物理移除旧 `tests/server/`。
- **验收门槛**：前台顺序执行 `pytest tests/webapi -q` 全绿（`0 failed`，耗时 `< 6s`）。

---

#### [ ] 顺序 ⑳
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-09`**
- **关联权威规范**：
  [`docs/guidelines/engineering/testing-guide.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/testing-guide.md) §9.3、§9.4
- **任务名称**：**重构 `tests/core/`（6 大支撑引擎单测）与 `tests/skills/`（`1+6` 符合性评估与执行测试）+ 剥离 `tests/release/`**
- **进度状态**：`[ ] 等待 S2-08 完成解锁`
- **前置依赖**：`S2-08`
- **核心动作**：
  1. 将打包与安装器测试剥离至 `tests/release/test_release_packaging_smoke.py`（`-m release_pack`）；
  2. 重构 `tests/core/` 为对应 Engine A ~ Engine F 的 6 个纯内存极速单测文件；
  3. 重构 `tests/skills/` 为 `test_skill_suite_1plus6_contract.py`（含 C1~C6 符合性强制门禁）与 `test_skill_tools_execution.py`，清理旧冗余测试文件。
- **验收门槛**：前台顺序执行 `pytest tests/core tests/skills -q` 全绿（`0 failed`，耗时 `< 8s`）。

---

#### [ ] 顺序 ㉑
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md) + **`S2-10`**
- **关联权威规范**：
  [`docs/guidelines/engineering/testing-guide.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/testing-guide.md) §9
- **任务名称**：**升级根 `tests/conftest.py`、`tools/validation/check.py`、`tests/README.md` 与 CI 矩阵并完成全链路收官验收**
- **进度状态**：`[ ] 等待 S2-09 完成解锁`
- **前置依赖**：`S2-09`
- **核心动作**：
  1. 升级根 `tests/conftest.py`（解耦 FastAPI，确立 `core` / `webapi` / `release_pack` 分档）；
  2. 升级 `tools/validation/check.py`、`.github/workflows/ci.yml`、`tests/README.md` 与 `testing-guide.md` 实测数据；
  3. 前台顺序执行 `pytest -m core`、`pytest -m webapi`、`pytest -m release_pack` 完成收官验收并登记证据台账。
- **验收门槛**：三大门禁全部 `0 failed`，默认核心门禁 `pytest -m core` 耗时 `< 8s`，全工程 `34/34` 任务 100% 闭环！

---

## 四、分时断点续传与执行维护守则 (Session Continuity Protocol)

后续分时在不同会话中执行时，智能体与开发者必须严格遵守以下执行守则：
1. **断点寻址与原子加锁**：新会话开始时，通过读取本文档第一节与第三节寻找唯一的 `[▶]` 标记，第一步先将本文档及 `eng-skill-1plus6-and-test-rearchitecture-plan.md` 中的 `[▶]` 原子替换为 `[🚧 IN_PROGRESS: <session_id> | <时间>]` 并落盘；
2. **任务实施与测试门禁（严禁后台执行，直接在任务中顺序执行）**：
   - 必须先完成该任务要求的代码改造、C1~C6 符合性自检与用例编写；
   - **严禁后台执行**：必须直接在当前任务中前台顺序执行门禁验证，前台即时确认退出码 0，确保无回归；严禁挂起后台进程；
3. **标记推进与证据留痕**：
   - 任务完成后，将本文档及主计划中的当前项标记由 `[🚧 IN_PROGRESS: ...]` 改为 `[x]`；
   - 将紧随其后的下一顺序项标记由 `[ ]` 改为 `[▶]`；
   - 在主计划 `eng-skill-1plus6-and-test-rearchitecture-plan.md` 的第二节矩阵将状态改为 `[x]`，并在第五节验收证据台账中登记实测命令行、测试数量、耗时与 C1~C6 符合性结论。

