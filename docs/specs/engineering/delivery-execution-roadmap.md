# 技能总包交付与安装整改分时执行清单 (Delivery & Installation Execution Roadmap)

- **归属实施计划**：[`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md)
- **权威设计规范 (SSOT)**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md)
- **审查评估报告**：[`docs/audits/2026-10-16-skill-structure-review.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/audits/2026-10-16-skill-structure-review.md)
- **实施状态**：🚧 **实施中**（基座 7/7 完成；全局进度 7/24 完成 29.2%；P0 阻断剩余 3 项；当前就绪活跃断点：`[▶] P0-08`）

> **文档定位与使用指引**：
> 本清单专用于**跨会话分时执行、断点续传追踪与自动化任务认领**。所有执行项严格按照**「执行或规范文档文件 + 任务号」**格式登记。
> 智能体或开发者在任意新会话中启动任务时，直接搜索定位 `[▶]` 标记即可锁定当前唯一执行起点；完成验收并通关门禁后，将当前项更新为 `[x]` 并将下一项置为 `[▶]`。

---

## 一、全局进度追踪看板 (Progress Dashboard)

| 阶段分类 | 任务范围 | 完成进度 | 阶段状态 | 当前活跃指针 |
| :--- | :--- | :---: | :---: | :--- |
| **阶段 0：基础交付基座** | `P0-01` ~ `P0-07` | **7 / 7 (100%)** | ✅ **已闭环** | 全部门禁全绿（312 passed） |
| **阶段一：P0 交付阻断攻坚** | `P0-08` ~ `P0-10` | **0 / 3 (0.0%)** | 🚧 **当前执行攻坚中** | **`[▶] P0-08`（当前就绪）** |
| **阶段二：P1 双模态安装与升级** | `P1-08` ~ `P1-10` | **0 / 3 (0.0%)** | ⏳ 等待阶段一完成 | 待 `P0-09` 交付安装核心 |
| **阶段三：P1 源码工程质量治理** | `P1-01` ~ `P1-07` | **0 / 7 (0.0%)** | ⏳ 等待排期推进 | `P1-06` 结构对齐先期已打底 |
| **阶段四：P2 文档与通用生态** | `P2-01` ~ `P2-04` | **0 / 4 (0.0%)** | ⏳ 等待最终发版 | `P2-03` 测试映射已先期修正 |
| **全工程总计** | 全套 24 项整改任务 | **7 / 24 (29.2%)** | 🚧 实施推进中 | **唯一执行起点：`[▶] 顺序 ①: P0-08`** |

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

#### [▶] 顺序 ①
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P0-08`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.1、§4.2
- **任务名称**：**Release 产物锚点技能架构与转发壳三级寻址改造**
- **进度状态**：`[▶] 当前就绪（下一步优先执行）`
- **前置依赖**：`P0-01` ~ `P0-07`（已全部达成 ✅）
- **核心动作**：
  1. 修改 `tools/packaging/common.py`，构建期将公共 `runtime/`、`assets/`、`references/` 收敛注入总入口 `skills/a-stock-agents/`（锚点技能）；
  2. 升级转发壳模板实现“自定位 ➔ 兄弟定位 `../a-stock-agents/` ➔ 系统收据定位 `install.json`”；
  3. 在 `tests/core/test_release_delivery_gate.py` 新增锚点打包与寻址断言。
- **验收门槛**：单个技能被剥离到独立临时目录时，仍能通过兄弟定位或收据定位唤起 `doctor.py` 并通过 P0 门禁。
- **执行命令参考**：`.venv/Scripts/python.exe -m pytest tests/core/test_release_delivery_gate.py -q`

---

#### [ ] 顺序 ②
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P0-09`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.2、§8.3
- **任务名称**：**统一安装底层脚本核心 `install.ps1` / `install.sh` 开发**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：`P0-08`（产物具备锚点技能与三级寻址结构）
- **核心动作**：
  1. 编写跨平台安装核心 `install.ps1`（Windows）与 `install.sh`（POSIX），支持 `-Inspect`、`-Agent <list>`、`-Method <link|copy>`、`-Yes` 与 `--json`；
  2. 在 `%LOCALAPPDATA%/a_stock_agents/`（或 POSIX 数据根）建立专用 `.venv`，安装依赖并落盘 `install.json`（持久化 `python_path` 与 `runtime_root`）。
- **验收门槛**：在临时沙箱中执行 `install.ps1 -Inspect -Json` 与安装链路，退出码 0，生成的收据包含 20 个入口就绪证明与 SHA256。
- **执行命令参考**：`powershell -File install.ps1 -Inspect -Json`

---

#### [ ] 顺序 ③
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P0-10`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.2、§5
- **任务名称**：**逐技能粒度平级注册与“宿主发现模拟”自动化门禁**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：`P0-09`（统一安装脚本具备逐技能挂载能力）
- **核心动作**：
  1. 重构宿主注册逻辑，废弃链接整个 `skills/` 的错误行为，改为在宿主技能根创建 20 个平级独立链接（Hermes 写入 `external_dirs`）；
  2. 在 `tests/core/test_release_delivery_gate.py` 新增模拟门禁，模拟 Codex、Hermes、WorkBuddy 的单层扫描逻辑，**断言 20 个入口检出率 100%**。
- **验收门槛**：P0 核心门禁 `pytest -m core` 全绿，三宿主发现数全部恒等于 20。**至此 P0 交付阻断项全部闭环！**

---

### 阶段二：P1 双模态安装交互体验与生命周期（从“能装”到“极佳体验”）

#### [ ] 顺序 ④
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-08`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.4、§8.5
- **任务名称**：**模态一落地：AI 安装引导提示词与 5 类信息卡片渲染契约**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：`P0-09`、`P0-10`
- **核心动作**：在发版说明与快速上手中固化自包含提示词；在总入口 `a-stock-agents/SKILL.md` 中固化安装状态机，在 AIChat / AIWork 中分 5 阶段输出结构化信息卡片（宿主选择、配置登记、安全评估、任务导轨、实战交付）。

---

#### [ ] 顺序 ⑤
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-09`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.6
- **任务名称**：**模态二落地：终端 TUI 键盘多选导轨菜单开发**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：`P0-09`
- **核心动作**：在 `install.ps1` 与 `install.sh` 中检测 TTY 环境，自动激活控制台交互式菜单：支持光标上下移动、空格勾选、回车确认；展示 Universal 宿主与特有 AI 工具分类；加入 Overwrites 冲突保护。

---

#### [ ] 顺序 ⑥
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-10`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.7
- **任务名称**：**多版本原子切换与一键回滚升级链实现**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：`P0-09`
- **核心动作**：代码安装路径规范为 `releases/<version>/`，由 `current` 符号链接挂载；实现 `install.ps1 -Update` 与 `-Rollback`；确保升级与回滚全程 100% 隔离用户资产。

---

### 阶段三：P1 源码工程单一来源治理与自动化看守（开发内聚度收口）

#### [ ] 顺序 ⑦
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-01` ~ `P1-05`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §2、§3
- **任务名称**：**源码单一来源收敛（腾讯解析器、监控模板、指标权威、CLI 双后端合一、死路径清理）**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：P0 门禁保持全绿
- **核心动作**：取消技能 templates 下的重复下标解析豁免，由 AST 哨兵守住；合并 `ta_entry_monitor`；回测脚本统一复用 `core.indicators` 与 `combo_scorer`；双后端合一。

---

#### [ ] 顺序 ⑧
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-06`**
- **关联权威规范**：
  [`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §6
- **任务名称**：**CLI `--json` 输出结构契约与 `skill list` 输出测试**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：`P1-01` ~ `P1-05`
- **核心动作**：对 20 个入口逐一进行子进程执行校验，断言标准输出必须为合法 JSON，且包含最低保本价、三级止损、三动作单铁律字段。

---

#### [ ] 顺序 ⑨
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P1-07`**
- **关联权威规范**：
  [`docs/guidelines/engineering/testing-guide.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/testing-guide.md) §3.2
- **任务名称**：**引入 GitHub Actions CI 流水线**
- **进度状态**：`[ ] 待执行`
- **前置依赖**：P0 与 P1-06 门禁
- **核心动作**：建立 Windows + Linux 跨平台自动化测试矩阵，在 PR 和发版时自动跑通 P0 门禁、发布链路检验与隔离解压验收。

---

### 阶段四：P2 文档口径对齐与通用生态分发（公开发布准备）

#### [ ] 顺序 ⑩
- **执行/规范文档文件 + 任务号**：
  [`docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-skill-suite-delivery-remediation-plan.md) + **`P2-01` ~ `P2-03`**
- **关联权威规范**：
  [`docs/audits/2026-10-16-skill-structure-review.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/audits/2026-10-16-skill-structure-review.md) §4.3
- **任务名称**：**统一技能计数口径（20 入口）、README 宿主清单与测试文档映射修正**
- **进度状态**：`[ ] 待执行`
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
2. **任务实施与测试门禁**：
   - 必须先完成该任务要求的代码改造与用例编写；
   - 必须运行 P0 核心门禁验证（`.venv/Scripts/python.exe -m pytest -m core -q`），确保无回归；
3. **标记推进与证据留痕**：
   - 任务完成后，将本文档及主计划中的当前项标记由 `[▶]` 改为 `[x]`；
   - 将紧随其后的下一顺序项标记由 `[ ]` 改为 `[▶]`；
   - 在主计划 `eng-skill-suite-delivery-remediation-plan.md` 的第二节矩阵将状态改为 `☑`，在第三节可勾选清单中打勾；
   - 在主计划第五节验收证据表中追加实测命令行、测试数量、耗时与结果边界。
