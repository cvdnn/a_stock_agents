# 技能开发工程与 Release 交付规范

> 修订日期：2026-10-14
> 权威范围：工程目录、技能唯一来源、Release 构建及跨平台验收
> 实施记录：[改造计划](../../specs/engineering/eng-skill-suite-portability-plan.md)

## 1. 项目定位

项目只有两个主要用途：技能开发工程和技能交付集合。开发工程实现、调试、测试技能功能，从唯一源码构建 Release；WorkBuddy、Hermes Desktop、Codex 的 AIChat/AIWork 使用已交付版本。

不再将“AI 工具打开本仓库作为工作区或项目后发现技能”列为产品模式，不维护项目发现链接或双模式适配目录。开发人员在仓库执行 CLI 和测试属于工程操作，与 AI 工具技能安装分开。

产品名称为 `a_stock_agents`；标准总入口标识及目录为 `a-stock-agents`。`skill_bundle` 是集合源码目录，不是单个技能，不在集合根放置名称不匹配的 SKILL.md。集合含总入口与19项专业技能，共20个标准入口。

## 2. 完整目录与所有权

```text
a_stock_agents/                         # 开发仓库
├── skill_bundle/                       # 唯一可交付源码集合
│   ├── bundle.json                     # 集合身份、版本、资源布局
│   ├── skills/
│   │   ├── a-stock-agents/SKILL.md      # 总入口：路由与编排
│   │   └── <19项专业skill-id>/
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

SKILL.md 的 name 必须与所属目录一致；description 描述明确触发条件。标准字段及平台扩展按目标工具验证。脚本、资源和说明由所有者维护一次；公共实现放 runtime/core，技能 scripts 调用公共实现并仅保留自己的业务编排。不得将整个引擎分别塞进20个技能目录。

WebUI 保留为开发调试和验收应用，复用公共算法；Release 基础能力不能依赖其登录、HTTP服务、端口6300或开发服务器。需要后台任务、模型或网络的技能必须声明运行依赖。

## 3. 单一来源与生成产物

技能源码、业务清单、公共模板及配置定义各维护一份。有效用户设置由独立数据根下 local/settings/application.yaml 提供，支持 A_STOCK_CONFIG_PATH；不能打包开发者现有设置。

Release 是从源码生成的版本快照，允许宿主安装到自身管理目录，不是第二份维护源码。不得手动修改 ZIP 再回写源码，也不维护平台镜像。平台元数据和安装说明由共用构建器派生，平台差异只放适配层。发布版本整体包含 skills/runtime/assets/references，禁止只复制技能目录造成依赖缺失。

同一接收端若需要共享多个技能的引擎，只安装一个完整版本单元。宿主只支持单技能导入时，评估总入口交付或可验证的集合安装机制；不要复制19份共享运行时。只发现总入口必须报告1个入口、19项可路由能力，不能报告独立发现20个技能。

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

开发验收：元数据20项、业务清单19项；公共实现一份；技能编排和资源可定位；核心 CLI 不导入 Web服务；源配置及UI既有修改保留。自动测试按 [测试规范](testing-guide.md) 仅运行P0，其余先取得人工确认。

产物验收：归档路径安全、排除私有数据、依赖闭包、版本一致、SHA256、启动器编码及执行位；在没有开发仓库的隔离路径解压后诊断和调用。仅能解压或诊断不代表技能安装通过。

宿主验收按 Windows/macOS/Linux × WorkBuddy/Hermes Desktop/Codex 登记版本、格式、独立发现数、能力调用、更新和卸载结果。AIChat/AIWork分别记录实际入口可用性。真实环境未运行就标未验证；发布公告列出已验与未验项目。先生成候选包，完成所需门禁后再发布正式 Release，不自动提交或推送。

此前项目发现/工作区双模式方案及其链接验收仅作历史记录，不再是现行目标。

## 7. 开发辅助入口

初始化使用tools/development/setup.ps1或setup.sh；共享manage.py实现依赖选择、失败退出与离线诊断。基础requirements从现有锁导出，安装当前test/browser/full选项时以其约束版本；现有锁缺少部分测试extras，不声称开发环境整体锁定。默认安装test依赖，browser/full显式选择，不自动运行扩展测试。Web通过run-web启动并将输出保存到log/web-console。Docker归属tools/containers/web-console，仓库为context，Dockerfile专用忽略规则放在Dockerfile旁；代码/app和可写数据/data分离，output/local/log持久化，temp用可销毁tmpfs。production保留为鉴权策略标识，不表示开发容器已达到生产部署验收。

旧ZIP覆盖更新入口退役并拒绝调用；开发仓库通过Git维护。离线验证入口为tools/validation/check.py，默认doctor，--core显式选择P0。旧混合verify脚本只保留在迁移日志中供恢复，不作为活跃工具。requirements.txt由tools/development/export_dependencies.py在核对基础声明一致后从uv.lock离线导出（导出工具需Python3.11+），不手工维护第二份依赖。
