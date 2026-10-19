# 技能开发工程与 Release 交付规范

> 修订日期：2026-10-14
> 权威范围：工程目录、技能唯一来源、Release 构建及跨平台验收
> 实施记录：[改造计划](../../specs/engineering/eng-skill-suite-portability-plan.md)

## 1. 项目定位

项目只有两个主要用途：技能开发工程和技能交付集合。开发工程实现、调试、测试技能功能，从唯一源码构建 Release；WorkBuddy、Hermes Desktop、Codex 的 AIChat/AIWork 使用已交付版本。

不再将“AI 工具打开本仓库作为工作区或项目后发现技能”列为产品模式，不维护项目发现链接或双模式适配目录。开发人员在仓库执行 CLI 和测试属于工程操作，与 AI 工具技能安装分开。

产品名称为 `a_stock_agents`；标准总入口标识及目录为 `a-stock-agents`。`skill_bundle` 是集合源码目录，不是单个技能，不在集合根放置名称不匹配的 SKILL.md。集合含总入口与6项生产级专业技能，共7个标准入口（内建对旧 19 技能别名 100% 透明兼容）。

## 2. 完整目录与所有权

```text
a_stock_agents/                         # 开发仓库
├── skill_bundle/                       # 唯一可交付源码集合
│   ├── bundle.json                     # 集合身份、版本、资源布局
│   ├── skills/
│   │   ├── a-stock-agents/SKILL.md      # 总入口：路由与编排
│   │   └── <6项生产级专业skill-id>/
│   │       ├── SKILL.md                # 标准前置元数据与操作指令
│   │       ├── scripts/                # 可选：技能自有编排/实现
│   │       ├── references/             # 可选：专业说明
│   │       ├── assets/                 # 可选：技能资源
│   │       └── templates/或formulas/   # 现有专属资源，按需保留
│   ├── runtime/
│   │   ├── bootstrap.py / cli.py / run_skill.py / doctor.py
│   │   ├── astock / astock.ps1 / astock.cmd
│   │   └── core/                      # 唯一公共算法与治理实现
│   ├── assets/
│   │   ├── config/skills_manifest.json # 唯一业务技能清单
│   │   └── templates/                 # 公共模板；schema按需要增设
│   └── references/                    # 公共执行契约与提示词
├── apps/web-console/                  # 可选开发调试应用，默认不发给宿主
│   ├── backend/server/                # HTTP、认证及界面适配
│   └── frontend/                      # WebUI
├── tools/
│   ├── packaging/                     # 共用构建器与三个平台打包入口
│   ├── host_adapters/                 # Release 接收端辅助注册工具
│   ├── validation/                    # 开发验证工具
│   ├── development/                   # setup、run-web、迁移工具，不交付
│   ├── containers/web-console/        # 可选Web调试Docker，不交付
│   └── legacy/                        # 旧命令薄转发
├── tests/                             # 分层自动测试，包含技能测试
├── docs/                              # 工程规范、设计及验收记录
├── bin/                               # 开发 CLI 薄入口
├── pyproject.toml / requirements.txt / uv.lock
├── local/                             # 开发私有设置，禁止发布
├── output/packages/                   # 生成的候选 Release 及校验文件
├── output/reports/                    # 开发或用户交付结果
├── log/                               # 执行及构建日志
└── temp/                              # 可清理中间产物
```

SKILL.md 的 name 必须与所属目录一致；description 描述明确触发条件。标准字段及平台扩展按目标工具验证。脚本、资源和说明由所有者维护一次；公共实现放 runtime/core，技能 scripts 调用公共实现并仅保留自己的业务编排。不得将整个引擎分别塞进7个技能目录。

WebUI 保留为开发调试和验收应用，复用公共算法；Release 基础能力不能依赖其登录、HTTP服务、端口6300或开发服务器。需要后台任务、模型或网络的技能必须声明运行依赖。

## 3. 单一来源与生成产物

技能源码、业务清单、公共模板及配置定义各维护一份。有效用户设置由独立数据根下 local/settings/application.yaml 提供，支持 A_STOCK_CONFIG_PATH；不能打包开发者现有设置。

Release 是从源码生成的版本快照，允许宿主安装到自身管理目录，不是第二份维护源码。不得手动修改 ZIP 再回写源码，也不维护平台镜像。平台元数据和安装说明由共用构建器派生，平台差异只放适配层。发布版本整体包含 skills/runtime/assets/references，禁止只复制技能目录造成依赖缺失。

同一接收端若需要共享多个技能的引擎，只安装一个完整版本单元。宿主只支持单技能导入时，评估总入口交付或可验证的集合安装机制；不要复制6份共享运行时。只发现总入口必须报告1个入口、6项可路由能力，不能报告独立发现7个技能。

## 4. Release 构建与安装边界

三个构建入口为 tools/packaging/build_codex.py、build_hermes.py、build_workbuddy.py，共用 common.py。构建输出使用 output/packages；不包含 apps、tests、docs、local、output、log、temp、.env、.venv、开发发现链接或源码机器绝对路径。

当前脚本输出的是完整集合候选 ZIP 与 SHA256，不是已经通过原生客户端导入验收的安装包。INSTALL.json 必须明确安装格式、预计技能入口数、实际宿主验收状态、依赖安装和独立数据目录。平台标签不能替代格式适配。

后续原生格式适配须按目标版本官方契约实施：多技能容器是否支持、根清单、SKILL 元数据、依赖执行权限、升级卸载及缓存刷新分别确认。不能由“支持 ZIP/SKILL.md”推断会递归识别集合内全部技能。未验证项不能标为支持。

接收端注册工具只能接受解压的 Release，不能将开发仓库作为安装目标。用户级安装需明确授权；开发安装脚本不会注册宿主或写入全局技能目录。生成安装版本副本与禁止维护源码镜像不是同一限制。

## 5. 跨平台路径及链接

Release 不依赖符号链接、junction 或硬链接。归档内保留实体文件，公共资源由 bundle.json 标识的集合根定位。Windows、macOS、Linux 分别提供薄启动器；POSIX脚本使用 LF 和执行位，不携带 .venv。

只有实际宿主注册需要且验证支持时才使用目录引用。Windows链接受权限和文件系统限制，可验证本地junction；macOS/Linux可验证符号链接。失败报告原因，不自动复制另一套运行时。卸载只移除有归属凭据的入口，保留版本源码和用户数据。不得将本机链接带进 Release。

PACKAGE_ROOT、RUNTIME_ROOT、SKILLS_ROOT是代码根，统一从 core.workspace 导入；WORKSPACE_ROOT 名称保留为兼容的可写数据根，语义不再表示 AI 工具项目模式。PROJECT_ROOT 仅为旧代码的数据根兼容别名。运行路径不依赖CWD或固定父目录层数。

开发默认数据根为仓库；Release默认数据根为操作系统用户数据目录下 a_stock_agents，显式 A_STOCK_WORKSPACE_ROOT/A_STOCK_AGENTS_ROOT 优先。Windows使用 LOCALAPPDATA（无值时用户目录/AppData/Local），macOS使用 ~/Library/Application Support，Linux使用 XDG_DATA_HOME（无值时 ~/.local/share）。用户output/log/temp/local与安装缓存分离，升级不能覆盖用户状态。

## 6. 验收与发布门槛

开发验收：技能总入口与元数据7项、核心业务技能清单6项（内嵌旧19项别名兼容映射）；公共实现一份；技能编排和资源可定位；核心 CLI 不导入 Web服务；源配置及UI既有修改保留。自动测试按 [测试规范](testing-guide.md) 仅运行P0，其余先取得人工确认。

产物验收：归档路径安全、排除私有数据、依赖闭包、版本一致、SHA256、启动器编码及执行位；在没有开发仓库的隔离路径解压后诊断和调用。仅能解压或诊断不代表技能安装通过。

宿主验收按 Windows/macOS/Linux × WorkBuddy/Hermes Desktop/Codex 登记版本、格式、独立发现数、能力调用、更新和卸载结果。AIChat/AIWork分别记录实际入口可用性。真实环境未运行就标未验证；发布公告列出已验与未验项目。先生成候选包，完成所需门禁后再发布正式 Release，不自动提交或推送。

此前项目发现/工作区双模式方案及其链接验收仅作历史记录，不再是现行目标。

## 7. 开发辅助入口

初始化使用tools/development/setup.ps1或setup.sh；共享manage.py实现依赖选择、失败退出与离线诊断。基础requirements从现有锁导出，安装当前test/browser/full选项时以其约束版本；现有锁缺少部分测试extras，不声称开发环境整体锁定。默认安装test依赖，browser/full显式选择，不自动运行扩展测试。Web通过run-web启动并将输出保存到log/web-console。Docker归属tools/containers/web-console，仓库为context，Dockerfile专用忽略规则放在Dockerfile旁；代码/app和可写数据/data分离，output/local/log持久化，temp用可销毁tmpfs。production保留为鉴权策略标识，不表示开发容器已达到生产部署验收。

旧ZIP覆盖更新入口退役并拒绝调用；开发仓库通过Git维护。离线验证入口为tools/validation/check.py，默认doctor，--core显式选择P0。旧混合verify脚本只保留在迁移日志中供恢复，不作为活跃工具。requirements.txt由tools/development/export_dependencies.py在核对基础声明一致后从uv.lock离线导出（导出工具需Python3.11+），不手工维护第二份依赖。

## 8. 双模态安装与宿主发现契约 (Dual-Modality Installation & Host Discovery Contract)

### 8.1 统一内核与双模态架构原则 (One Core Engine, Two Presentation Layers)
项目安装与升级体系坚持“同一套底层部署引擎、两种交互表面”的设计铁律，严禁分化为两套割裂的安装脚本：
- **底层统一内核**：由统一安装脚本（`install.ps1` / `install.sh`）承载 Release 下载解压、SHA256 校验、宿主目录探测、符号链接/Junction 挂载、隔离 Python `.venv` 创建、依赖安装、`doctor.py` 冒烟与安装收据（`install.json`）落盘；支持 `--json` 参数输出纯结构化机器数据。
- **模态一（AI 任务中协助安装）**：在 AIChat / AIWork 中由 AI 智能体后台调用底层内核的 `--json` 接口，在前端以 5 阶段渐进式**信息卡片（Interactive Cards）**引导用户完成交互选择与安全确认。
- **模态二（终端命令行手动安装）**：在 PowerShell / Bash 终端中运行，检测到 TTY 控制台时自动呈现交互式 TUI 导轨菜单（键盘上下移动、空格勾选、回车确认）；支持命令行参数（`-Agent`、`-Method`、`-Yes`）用于脚本或 CI 自动化。
- **通用生态通道**：通过构建期派生的通用技能结构，支持 `npx skills add cvdnn/a-stock-agents -g` 直接接入通用 Skills 生态。

> [!IMPORTANT]
> **平台与技能职责边界红线 (Platform vs Skill Boundary)**
> - **平台侧 WebUI 与 Docker**：`tools/containers/web-console/` 下的 Dockerfile 及 Compose 编排属于平台侧 Web 控制台（`apps/web-console/`）的功能开发与调试部署范畴，**与用户技能安装（Skill Installation）完全无关**。
> - **用户技能安装与 AI 协助安装**：AI 协助安装与终端安装器（`install.ps1` / `install.sh`）的目标是将 7 个量化决策技能入口（1 锚点 + 6 核心业务）接入用户环境或 AI 宿主（Universal / Hermes / WorkBuddy / Codex），建立本地 Python 隔离虚拟环境。**Docker 绝不参与 AI 帮忙安装的任何流程、提示词与交互卡片**。

### 8.2 模态一：AI 任务协助安装与信息卡片交互规范
若用户仅输入模糊的“帮我安装炒股技能”，大模型易产生幻觉（盲目全局 `pip install`、误删配置或丢失宿主上下文）。官方文档与发版页必须提供**自包含、可一键复制给 AI 的标准化安装指令提示词（AI Copilot Bootstrap Prompt）**：

> **标准 AI 安装指令模板**：
> ```markdown
> 请帮我安全安装与配置「A-Stock Agents (A股全流程量化实战决策智能体技能总包)」。
> 本项目为生产级量化工程，严禁自行编写临时爬虫或随意 pip install。请严格遵循以下执行契约与渐进式卡片交互 SOP：
> 
> 【安装源与执行协议】
> 1. 项目 Release 仓库: https://github.com/cvdnn/a-stock-agents/releases/latest
> 2. 基础安装引导器:
>    - Windows (PowerShell): `irm https://github.com/cvdnn/a-stock-agents/releases/latest/download/install.ps1 | iex` (或本地 `.\install.ps1`)
>    - POSIX (Bash): `curl -fsSL https://github.com/cvdnn/a-stock-agents/releases/latest/download/install.sh | bash`
> 3. 所有命令交互与状态查询必须追加 `--json` 参数以获取结构化数据。
> 
> 【执行任务流水线 (SOP)】
> - 阶段 1 [探测环境]：调用安装引导器 `-Inspect -Json`，探测当前系统已安装的 AI 工具（Codex/Hermes/WorkBuddy/Universal目录）。
> - 阶段 2 [配置交互]：暂停执行，向我呈现【信息卡片 1：宿主选择】与【信息卡片 2：数据源偏好】，等待我做出选择。
> - 阶段 3 [安全确认]：根据我的选择，生成【信息卡片 3：安装前摘要与安全审计】，提示挂载路径、依赖清单与权限范围，等待我确认。
> - 阶段 4 [分级执行]：获得确认后，组装参数调用 `install.ps1 -Agent <已选项> -Method link -Yes -Json`，并在工作区以 L1/L2 批量子任务卡片呈现部署进度。
> - 阶段 5 [冒烟交付]：运行 `doctor.py --json` 验证全部 7 个入口，输出【信息卡片 5：交付与快速实战指令】。
> 
> 请先执行阶段 1，并向我输出【信息卡片 1】开始安装引导。
> ```

AI 在接收该提示词后必须按规范输出 5 类信息卡片：
1. **卡片 1：宿主接入偏好卡片**：列出探测到的 Universal (`~/.agents/skills`)、Hermes Desktop (`~/.hermes`)、WorkBuddy (`~/.workbuddy/skills`) 供勾选；
2. **卡片 2：数据源与配置卡片**：区分开箱即用的 L1 免费源与可选进阶库（AkShare/MyTT）及私有凭据登记（写入 `local/settings/.env`）；
3. **卡片 3：安装摘要与安全审计卡片**：列出目标代码路径、隔离数据根、Overwrites 冲突检测结果、权限隔离声明，提供“确认安装”动作；
4. **卡片 4：分级流水线进度卡片**：按照 AGENTS.md 规范展示批量父任务与原子子任务执行进度（下载校验、宿主挂载、环境构建、依赖安装、doctor 自检）；
5. **卡片 5：交付与实战体验卡片**：提示各宿主专用调用语法（Codex `$a-stock-agents` / Hermes `/a-stock-agents` / WorkBuddy `@a-stock-agents`），并提供 3 个即时量化体检快捷动作。

### 8.3 模态二：终端命令行手动安装与 TUI 导轨规范
针对开发者与运维场景，终端运行 `install.ps1` 或 `install.sh` 时，自动进入 TUI 交互式选择菜单：
- 使用键盘上下键导航、空格键切换勾选、回车键确认；
- 明确划分 `Universal (.agents/skills)` 与 `Additional agents`（Hermes / WorkBuddy / 自定义目录）；
- 展现安装方式单选（Symlink/Junction 推荐 vs Copy 物理复制）；
- 严格执行 **Overwrites 哨兵**：若宿主目录已存在非链接的同名物理目录，强制拒绝盲目覆盖，保护用户历史文件；
- 自动化与无交互支持：提供 `-Inspect`、`-Agent <列表>`、`-Method <link|copy>`、`-Yes`、`-Update`、`-Rollback`、`-Uninstall`、`-Doctor` 与 `--json` 参数。

### 8.4 锚点技能架构 (Anchor Skill) 与三级寻址模型
为解决通用生态安装器（如 `npx skills add`）只拷贝单个技能子目录、丢失平级 `runtime/` 导致的运行时瘫痪问题，Release 构建期执行架构重组：
1. **锚点技能布局**：将公共 `runtime/`、`assets/`、`references/` 收敛注入到总入口 `skills/a-stock-agents/` 中，总入口升级为携带完整共享引擎的“锚点技能”；其余 6 个专业技能保持轻量，仅保留说明与转发壳；
2. **三级寻址规范**：转发壳寻找引擎的逻辑升级为三级渐进式定位：
   - **自定位**：向上查找自身目录的 `bundle.json`（单包完整解压场景）；
   - **兄弟定位**：查找兄弟目录 `../a-stock-agents/bundle.json`（通用生态 `npx skills add` 或逐技能链接进宿主技能根场景，穿透符号链接天然连通）；
   - **收据定位**：读取系统固定安装收据 `%LOCALAPPDATA%/a_stock_agents/install.json` 中的全局安装根；
   - 三级均失败时，fail-closed 返回 `ANCHOR_SKILL_MISSING`，提示必须同时安装 `a-stock-agents` 锚点入口。

### 8.5 多版本原子升级与回滚规范
1. **多版本物理隔离**：代码版本解压至 `%LOCALAPPDATA%/a_stock_agents/releases/<version>/`，通过 `current` 软链接/Junction 指向当前激活版本；所有宿主注册的技能入口均指向 `current/skills/<id>`；
2. **零拷贝原子切换**：升级时下载新版本至独立目录，验证通过后仅需原子重定向 `current` 软链接，无需逐一重建几十个宿主技能入口；
3. **升级失败一键回滚**：若新版 doctor 冒烟未通过或执行异常，运行 `install.ps1 -Rollback` 即刻将 `current` 切换回上一可用版本；
4. **用户数据永不覆盖**：用户的自选池、交易记录、回测报告、私有配置严格位于 `%LOCALAPPDATA%/a_stock_agents/`（与 `releases/` 同级物理隔离），代码升级与卸载严禁触碰用户数据。

### 8.6 生命周期执行报告体系规范 (Lifecycle Execution Report Specification)
针对“技能安装部署、多版本平滑升级、升级熔断阻断、故障一键回滚、宿主引用卸载”等关键运维操作，安装引导器（`install.ps1` 与 `install.sh`）在操作执行后必须自动生成全链路执行审计报告，实现修改透明、备份可溯与故障自明。

1. **双格式报告协同**：
   - **人类可读 Markdown 报告**：落盘至 `%LOCALAPPDATA%/a_stock_agents/output/reports/lifecycle/lifecycle_report_<action>_<timestamp>.md`，并软链/镜像至同目录的 `latest_lifecycle_report.md`，提供包含状态徽章、起止耗时、环境概览、过程修改清单、备份情况审计与 Doctor 冒烟结论的直观可视化报告；
   - **机器可读 JSON 审计收据**：落盘至 `%LOCALAPPDATA%/a_stock_agents/log/lifecycle/lifecycle_<action>_<timestamp>.json` 与 `latest_lifecycle.json`，提供结构化审计数据（包含流水号 `report_id`、退出码、平台环境、修改文件/链接、收据备份路径及数据隔离策略状态）。

2. **五大生命周期场景审计要素**：
   - **安装部署 (Installation)**：记录目录初始化清单、Release 解压部署、虚拟环境隔离构建、可选依赖跳过/安装、宿主多级挂载详情与 Doctor 冒烟结果；同时在 `install.json` 根收据中注入 `latest_execution_report` 元数据；
   - **平滑升级 (Upgrade)**：在变更发生前先自动镜像备份旧版收据至 `install.json.bak`；校验新版本 7 项技能完整性并执行隔离环境冒烟验证。若冒烟通过，原子切换 `current` 软链接并生成 `success` 升级报告；
   - **升级阻断与熔断保护 (Update Aborted Guard)**：若新版冒烟自检失败，**严禁切换 current 软链接**，坚决守住当前运行版本；生成状态为 `aborted` 的阻断报告，详细记录 Doctor 失败现场、保留未激活的新版镜像供排查，并退出码 `1` 阻止上游继续；
   - **一键回滚 (Rollback)**：读取 `install.json.bak` 或历史收据，验证回滚目标版本目录的完整性；原子重定向 `current` 软链接至历史可用版本；生成记录版本跳变（如 `v3.1.0 -> v3.0.0`）的回滚审计报告；
   - **宿主引用卸载 (Uninstallation)**：仅安全切断和清理指定宿主（如 `Universal`、`Hermes`、`WorkBuddy`）目录下的平级技能符号链接/Junction 与收据，**100% 物理隔离保留用户的自选池、交易记录、回测报告与私有配置**；生成卸载报告详细列出已清理的引用路径。

   - 三存储桶物理隔离铁律遵守：
   - Markdown 最终报告属于交付物，存放在 `output/reports/lifecycle/`；
   - JSON 运行轨迹与审计追踪存放在 `log/lifecycle/`；
   - 安装临时缓存与中间下载物存放在 `temp/` 并在执行完毕后清理；
   - 绝不将审计报告或收据散落至技能源码或外部宿主目录。

---

## 9. 专业机构股票投研全链路闭环与技能设计符合性评估规范 (`SPEC-SKILL-002`)

> **生效日期**：2026-10-19
> **关联架构规范**：[`docs/specs/engineering/spec-skill-1plus6-consolidation-and-test-rearchitecture.md`](../../specs/engineering/spec-skill-1plus6-consolidation-and-test-rearchitecture.md)
> **关联分时实施计划**：[`docs/specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md`](../../specs/engineering/eng-skill-1plus6-and-test-rearchitecture-plan.md)
> **强制约束力**：本章节为项目技能设计、重构、合并与准入的**最高业务与架构准则**。后续任何新增技能、改动既有技能契约或扩展底层投研算法，**必须无条件先通过 9.4 节的符合性评估（Conformance Assessment）**，未通过评估严禁合入主干。

### 9.1 专业机构股票投研六步全链路闭环模型 (Six-Stage Institutional Research Closed-Loop)

本项目拒绝“碎片化、玩具级、单指标堆砌”的技能设计，严格遵循专业买方投研机构的**六步全链路标准实战闭环**，并将前台技能物理精简收敛为 **`1 + 6` 架构（`1` 个总控锚点技能 + `6` 个生产级专业股票投研技能）**：

$$\text{① 看盘知势} \longrightarrow \text{② 选股立池} \longrightarrow \text{③ 择时定买} \longrightarrow \text{④ 穿透体检} \longrightarrow \text{⑤ 仓位风控} \longrightarrow \text{⑥ 回测验证}$$

| 闭环阶段 | 机构投研核心命题 | 对应「1 + 6」生产级技能 (`skill_bundle/skills/`) | 对应底层技术支撑引擎 (`skill_bundle/runtime/core/`) | 阶段输入 / 输出核心契约 |
| :---: | :--- | :--- | :--- | :--- |
| **总控锚点** | **意图分流 · 环境自检 · 数据水位调度** | **`a-stock-agents`**<br>*(总入口锚点技能)* | **Engine A** (`core/data/` 同步守护)<br>**Engine F** (`core/governance/` + `doctor.py`) | **输入**：自然语言投研诉求或运维指令<br>**输出**：精准技能路由、数据水位就绪证明、5阶段安装/诊断卡片 |
| **阶段 ①<br>看盘知势** | **当前市场处于什么情绪周期？资金主线在哪？标的真实量价筹码如何？** | **`astock-market-data`**<br>*(全景行情与大盘五维情绪中枢)* | **Engine A** (`DataBridge` 4级容灾 + 分钟切片)<br>**Engine B** (`MarketAssessor` + `technical_indicators`) | **输入**：指数/个股代码、周期参数<br>**输出**：含 `evidence_meta` 的实时报价、复权K线、筹码获利盘、五维大盘健康度（趋势/情绪/量能/结构/资金）与主线周期灯号 |
| **阶段 ②<br>选股立池** | **全市场 5000+ 标的中，哪些符合主线共振、财务健康且具备正 Alpha？** | **`astock-smart-screener`**<br>*(智能漏斗与多因子选股中心)* | **Engine B** (`pv_factors` + `fundamental_filter`)<br>**Engine C** (`selection_models/` AST漏斗编译 + 版本库 + T+N跟踪) | **输入**：选股模式（`5a` / `funnel` / `quant`）、条件树或截面参数<br>**输出**：五大财务排雷后的候选标的池、多维共振得分、模型版本 SHA256 与 T+1/3/5/10 跟踪评估账本 |
| **阶段 ③<br>择时定买** | **候选股当前是否出现高胜率、高盈亏比的确定性买点信号？** | **`astock-tactical-signals`**<br>*(A股实战战法与形态信号雷达)* | **Engine D** (`chenxiaoqun` + `tuige` + `second_golden_cross` + 主板波段)<br>**Engine E** (`StrategyEvaluator` 250日胜率回溯) | **输入**：标的代码、战法类型（`mainboard` / `macd` / `chenxiaoqun` / `tuige`）<br>**输出**：战法触发判定、**近 250 日同类信号历史胜率与盈亏比锚定**、45bps 摩擦成本过滤结果 |
| **阶段 ④<br>穿透体检** | **买入或持有前，基本面有无暗雷？多空双方核心证据链与证伪位是什么？** | **`astock-deep-diagnose`**<br>*(个股全维循证诊断与多空研判)* | **Engine B** (`ComboScorer` 100分制 + 基本面排雷)<br>**Engine D** (`TrappedPositionAnalyzer` 解套树)<br>**Engine F** (`ta_analyze` 7角色对抗 + `report_generator`) | **输入**：标的代码、可选持仓成本/股数、`--debate`、`--html`<br>**输出**：**金字塔结论先行卡片（S~D评级+一句话核心观点+证伪位）**、六维循证矩阵、7角色多空证据链、自包含 HTML 研报 |
| **阶段 ⑤<br>仓位风控** | **买多少仓位？精确到分的保本价是多少？盘中冲高/震荡/跳水如何机械应对？** | **`astock-portfolio-action`**<br>*(三级股池治理与保本反应中枢)* | **Engine D** (`execution_action_engine` + `pool_manager` 五步MA审计 + `risk_position_manager` 受限凯利) | **输入**：关注/自选/持仓三级池指令，或 `代码 + 成本 + 股数`<br>**输出**：空池即刻拦截提示、五步真实 MA 重算与失效止损清洗、`math.ceil` 保本卖出价、`-3%/-5%/-8%` 三级止损、三场景反应单、凯利建议仓位 |
| **阶段 ⑥<br>回测验证** | **策略与动作在考虑 T+1、涨跌停、滑点税费及样本外（OOS）下是否依然有效？** | **`astock-paper-backtest`**<br>*(高保真模拟盘与样本外回测中心)* | **Engine E** (`paper_trading/engine` + `multi_backtest_engine` + 滚动 OOS 检验器) | **输入**：模拟下单指令或回测区间/组合配置（`--oos`）<br>**输出**：SQLite 多账户真实撮合流水、净值与回撤曲线、滚动样本外（Rolling OOS）绩效与**过拟合三重警报** |

---

### 9.2 生产级股票投研技能五大黄金品质准则 (Five Production-Grade Quality Pillars)

所有归属 `skill_bundle/skills/` 的技能必须满足以下五项生产级标准，严禁退化为“静态文本参考壳”或“无根据的观点输出”：

1. **准则一：功能准确性与确定性计算（Accuracy & Deterministic SSOT）**
   - 凡涉及行情字段解析、技术指标（MA/MACD/KDJ/RSI/BOLL/ATR）、截面因子（MAD 去极值、Z-Score 标准化）、税费保本价与止损位计算，**100% 由 `skill_bundle/runtime/core/` 下的确定性 Python 算法计算得出**，严禁大模型心算或估算。
2. **准则二：全链路可循证性（Verifiability & Evidence Envelope）**
   - 每个技能返回的 JSON 顶层必须携带统一的数据溯源信封 `evidence_meta`（包含 `as_of_trading_day`、`quote_source`、`kline_bars_count`、`watermark_ready`、`fee_rule_ssot`）；
   - 任何投研评级与多空结论必须附带可核验的量化数值锚点与正反双向证据链（看多催化剂 vs 看空证伪条件）。
3. **准则三：工业级高可靠性与失败关闭（Reliability & Fail-Closed Guard）**
   - 外部行情具备 4 级自动容灾降级（腾讯 $\to$ 东财 $\to$ 新浪 $\to$ 本地水位快照）；
   - 当 K 线长度不足、数据水位未就绪、标的停牌或股票池为空时，必须严格执行 **Fail-Closed（失败关闭）**，返回明确错误码（如 `DATA_UNAVAILABLE`、`EMPTY_POOL_STOP`），严禁捏造默认值或虚构演示股票。
4. **准则四：策略实战有效性与历史胜率锚定（Strategy Effectiveness & Win-Rate Anchor）**
   - 任何择时买点或形态信号不得孤立输出，必须同步联动：
     1. **大盘情绪门控**：大盘健康度低于阈值时自动抑制激进追涨信号；
     2. **个股历史胜率锚定**：自动回溯该股近 250 日同类信号的历史触发次数、T+5 胜率与盈亏比；
     3. **摩擦成本与过拟合过滤**：扣除双边 45bps 冲击与税费成本后仍具正期望，且通过样本内外衰减比（IS/OOS）过拟合检验。
5. **准则五：分析面全覆盖与核心观点突出（Full Six-Dimensional Coverage & BLUF Pyramid）**
   - **六维正交全覆盖**：全面覆盖「宏观大盘情绪、基本面财务排雷、技术趋势动能、量价筹码结构、游资微观博弈、风控头寸精算」六个正交分析面；
   - **金字塔结论先行（BLUF）**：输出结构强制遵循「第一屏：核心评级与一句话主观点（含触发价/证伪位） $\to$ 第二屏：实战交易三原则动作单（`ceil`保本价 + 三级止损 + 三场景应对） $\to$ 第三屏：六维循证数据明细」。

---

### 9.3 技能边界与反碎片化铁律 (Anti-Fragmentation & Boundary Rules)

为防止技能数量再次失控膨胀，确立以下三条物理边界铁律：
1. **总量硬上限铁律（`1 + 6` 架构锁死）**：
   - 仓库内一等技能目录总数固定为 **`1` 个总入口锚点技能（`a-stock-agents`） + `6` 个专业投研技能（共 7 个物理目录）**；
   - 严禁将单一技术指标（如单独的 KDJ、BOLL、MACD）、单一游资席位、单一文件导出格式（如 HTML 渲染、Markdown 归档）或纯静态避坑文档拆分为独立的一级技能目录。
2. **新增能力归并原则（Capability Absorption First）**：
   - 新研发的选股因子必须并入 `astock-smart-screener`；
   - 新研发的择时形态或游资战法必须作为 `--tactic <name>` 子模态并入 `astock-tactical-signals`；
   - 新研发的财务排雷或估值模型必须并入 `astock-deep-diagnose`；
   - 新研发的数据同步或基础设施能力必须下沉至 `runtime/core/` 的 6 大支撑引擎，并通过 `a-stock-agents` 运维子命令暴露。
3. **向后兼容别名映射（Zero-Breakage Alias Mapping）**：
   - 原 19 项旧技能 ID 在 `SkillRegistry.LEGACY_SKILL_ALIASES` 与 `tools.py` 中长期保留透明路由映射，确保外部宿主或历史脚本调用旧技能名时自动转发至对应的 `1 + 6` 新技能。

---

### 9.4 新增或改动技能强制符合性评估门禁 (Mandatory Conformance Assessment Gate)

**自本规范生效起，任何针对技能或核心投研算法的 PR、需求新增或代码改动，必须在设计文档与提交说明中填写并通过以下《投研技能六维符合性评估表》；自动化门禁（`tests/skills/test_skill_suite_1plus6_contract.py`）将对物理结构与输出契约做常驻强制校验：**

| 评估编号 | 符合性评估维度 | 强制核验标准（一票否决项） | 评估结论 (`PASS` / `REJECT`) |
| :---: | :--- | :--- | :---: |
| **C1** | **投研六步闭环归属与反碎片化评估** | 1. 改动是否明确归属于「看盘知势 / 选股立池 / 择时定买 / 穿透体检 / 仓位风控 / 回测验证」六步闭环之一？<br>2. 是否遵守 `1 + 6` 目录总量上限（未违规新增碎片化一级技能目录）？ | 必达 |
| **C2** | **计算准确性与循证溯源评估** | 1. 核心数值是否 100% 由 `runtime/core/` 确定性代码产出（无静态字典充数或 LLM 口算）？<br>2. JSON 输出是否包含完整合规的 `evidence_meta` 溯源信封与双向证据链？ | 必达 |
| **C3** | **可靠性、失败关闭与空池保护评估** | 1. 外部数据源异常、K 线不足或停牌时是否严格 Fail-Closed（绝不伪造默认行情）？<br>2. 涉及股池分析时是否严格执行「空股池即刻终止并提示登记格式」铁律？ | 必达 |
| **C4** | **策略实战有效性与防过拟合评估** | 1. 择时/选股信号是否附带近 250 日同类信号历史胜率与盈亏比锚定？<br>2. 是否计入双边税费与冲击成本（45bps 门槛）及样本外（OOS）衰减检验？ | 必达 |
| **C5** | **分析面完整性与金字塔结论突出评估** | 1. 诊断/选股是否覆盖相关正交分析维度（含基本面五大排雷与大盘五维情绪门控）？<br>2. 输出是否遵循「金字塔结论先行（BLUF）」，第一屏即给出评级、核心论点与证伪位？ | 必达 |
| **C6** | **实战交易三原则与极速测试门禁评估** | 1. 个股建议是否强制包含：`math.ceil` 分位保本卖出价 + `-3%/-5%/-8%` 三级止损 + 三场景动作单？<br>2. 是否已增补纯内存确定性单元测试，且在前台顺序执行 `pytest -m core` 全绿（耗时 `< 8s`）？ | 必达 |


