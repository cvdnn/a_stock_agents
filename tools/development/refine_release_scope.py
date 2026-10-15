"""One-time scope migration; not part of the distributed runtime."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def edit(relative, transform):
    path = ROOT / relative
    before = path.read_text(encoding='utf-8')
    after = transform(before)
    if after != before:
        path.write_text(after, encoding='utf-8', newline='\n')


SPEC = '''# 技能开发工程与 Release 交付规范

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
│   ├── development/                   # 工程迁移工具，不交付
│   └── legacy/                        # 旧命令薄转发
├── tests/                             # 分层自动测试，包含技能测试
├── docs/                              # 工程规范、设计及验收记录
├── bin/                               # 开发 CLI 薄入口
├── install.ps1 / install.sh           # 只初始化开发依赖及诊断
├── run.ps1 / run.sh                    # 开发 Web 调试入口
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
'''


def main():
    (ROOT/'docs/guidelines/engineering/skill-suite-portability-specification.md').write_text(SPEC, encoding='utf-8')
    edit('skill_bundle/runtime/core/workspace.py', lambda s: s.replace(
        "WORKSPACE_ROOT = Path(os.environ.get('A_STOCK_WORKSPACE_ROOT') or os.environ.get('A_STOCK_AGENTS_ROOT') or PACKAGE_ROOT.parent).expanduser().resolve()",
        '''def default_data_root(package_root, environment=None, platform=None):
    """Development data stay local; installed versions never write host caches."""
    environment = os.environ if environment is None else environment
    platform = __import__('sys').platform if platform is None else platform
    explicit = environment.get('A_STOCK_WORKSPACE_ROOT') or environment.get('A_STOCK_AGENTS_ROOT')
    if explicit:
        return Path(explicit).expanduser().resolve()
    marker = json.loads((package_root / 'bundle.json').read_text(encoding='utf-8'))
    if marker.get('distribution') != 'release':
        return package_root.parent
    home = Path.home()
    if platform == 'win32':
        base = Path(environment.get('LOCALAPPDATA') or home / 'AppData/Local')
    elif platform == 'darwin':
        base = home / 'Library/Application Support'
    else:
        candidate = Path(environment.get('XDG_DATA_HOME') or home / '.local/share')
        base = candidate if candidate.is_absolute() else home / '.local/share'
    return (base / 'a_stock_agents').expanduser().resolve()

WORKSPACE_ROOT = default_data_root(PACKAGE_ROOT)''').replace(
        s[s.index('def setup_workspace_mount():'):s.index('def check_workspace_health():')], '').replace(
        "            'agents_skills_mounted':(WORKSPACE_ROOT/'.agents/skills').resolve()==SKILLS_ROOT.resolve(),\n", ''))
    edit('tools/packaging/common.py', lambda s: s.replace("platform='project'", "platform='collection'").replace(
        "OUTPUT_DIR/'packages'", "ROOT/'output/packages'").replace("'mode':'reference-only'", "'mode':'release-candidate-collection'").replace(
        "'notice':'Extract once in a new environment. Register the original skills directory; never duplicate it for another mode.'",
        "'native_import_verified':False, 'data_root':'OS user data/a_stock_agents or explicit A_STOCK_WORKSPACE_ROOT',\n                  'notice':'Complete collection candidate. Native host import and skill discovery require separate acceptance. Do not register the development repository.'").replace(
        'archive.writestr(info,path.read_bytes())',
        "content=path.read_bytes()\n            if path==PACKAGE_ROOT/'bundle.json':\n                marker=json.loads(content)\n                marker['distribution']='release'\n                content=json.dumps(marker,ensure_ascii=False,indent=2).encode('utf-8')\n            archive.writestr(info,content)").replace("platform!='project'", "platform in {'codex','hermes','workbuddy'}").replace("main(platform='project')", "main(platform='collection')"))
    edit('tools/host_adapters/host.py', lambda s: s.replace('registration is explicit and project-scoped by default', 'registration accepts only a received Release').replace(
        "    if args.entry:", "    marker=json.loads((bundle/'bundle.json').read_text(encoding='utf-8'))\n    if marker.get('distribution')!='release':parser.error('Release required; development source cannot be registered')\n    if args.entry:"))
    edit('tools/host_adapters/project.py', lambda s: '"""Retired project-discovery entry point. Use Release delivery instead."""\nif __name__ == "__main__":\n    raise SystemExit("Project discovery is retired. Build a Release using tools/packaging/build_<platform>.py")\n')
    edit('install.ps1', lambda s: re.sub(r'# 4\. 工作区就地挂载与目录初始化.*?# 5\. 运行快速自检', '# 4. 开发环境离线诊断\n# 5. 运行快速自检', s, flags=re.S).replace('[5/5]', '[4/4]').replace(' 就地使用指引（零全局污染，开箱即用）：',' 开发与 Release 构建指引：').replace("Write-Host '   - Antigravity: 直接打开当前项目作为工作区，自动就地识别 18 项技能'", "Write-Host '   - 构建候选包: python tools/packaging/build_codex.py --json'").replace("Write-Host '   - Hermes/Codex: 当前目录下直接调用 .\\bin\\astock.ps1 <子命令> --json'", "Write-Host '   - AI工具通过已验收的 Release 使用技能；本脚本不注册宿主'"))
    edit('install.sh', lambda s: s.replace('# 4. 设置执行权限与工作区就地挂载', '# 4. 设置开发启动器权限').replace('[4/5] 设置执行权限与工作区就地挂载 (.agents/skills)...','[3/4] 设置开发启动器执行权限...').replace('"${VENV_PY}" tools/host_adapters/project.py\n','').replace('[5/5]', '[4/4]').replace(' 就地使用指引（零全局污染，开箱即用）：',' 开发与 Release 构建指引：').replace('   - Antigravity: 直接打开当前项目作为工作区，自动就地挂载 18 项技能','   - 构建候选包: python tools/packaging/build_codex.py --json').replace('   - Hermes/Codex: 当前目录下直接调用 ./bin/astock <subcommand> --json','   - AI工具通过已验收的 Release 使用技能；本脚本不注册宿主'))
    edit('AGENTS.md', lambda s: re.sub(r'> \[!IMPORTANT\].*?## 当前源码与接入契约', '> [!IMPORTANT]\n> 本仓库用于技能开发和 Release 构建。AI 工具使用发布版本；不维护项目发现模式，不将开发源码注册到全局技能目录。Release 是生成产物，不作为第二套源码维护。\n\n## 当前源码与接入契约', s, count=1, flags=re.S).replace('；`.agents/skills`仅是本机发现引用','；不建立`.agents/skills`项目发现入口').replace('项目内引用允许使用经验证的符号链接/Windows junction；失败不复制。','Release本身不依赖链接；接收端引用允许使用经验证的符号链接/Windows junction；失败不复制。').replace('from scripts.core.workspace import PROJECT_ROOT','from core.workspace import PROJECT_ROOT'))
    edit('README.md', lambda s: re.sub(r'项目内`\.agents/skills`.*?\n\n', '本仓库用于技能实现、测试与 Release 构建。AI工具通过发布版本使用技能，不维护打开仓库后发现技能的项目模式。\n\n', s, count=1, flags=re.S).replace('归档是完整集合的版本快照，不是强制复制式宿主导入包，也不作为第二套源码维护。','归档是完整集合候选快照，不作为第二套源码维护；三个平台的原生导入和全部技能发现仍须独立验收。').replace('.agents/skills 挂载与自检','离线结构自检').replace('> **自动就地挂载保障**：'+s.split('> **自动就地挂载保障**：')[1].split('\n')[0] if '> **自动就地挂载保障**：' in s else '__unused__', '> **开发安装边界**：安装脚本仅初始化开发环境及诊断，不注册AI工具技能。').replace(s[s.index('本项目原生支持 **项目级'):s.index('\n## 五、')], '''本仓库是开发工程；宿主使用 Release。开发者先执行 P0 和产物闭包验证，再按目标平台格式完成实际安装、发现和调用验收。

```bash
python tools/packaging/build_codex.py --json
python tools/packaging/build_hermes.py --json
python tools/packaging/build_workbuddy.py --json
```

当前输出为完整集合候选 ZIP，不能据此宣称客户端直接导入兼容。20个标准入口与19项业务能力分别计数；只发现总入口的宿主记1个入口。安装版本不携带开发私有配置，用户数据与安装缓存分离。

完整目录、平台适配和验收要求见[Release交付规范](docs/guidelines/engineering/skill-suite-portability-specification.md)。
'''))
    edit('docs/guidelines/engineering/project-structure-specification.md', lambda s: re.sub(r'> \*\*目标设计补充.*?\n', '> **现行范围**：[技能开发与Release交付规范](skill-suite-portability-specification.md) 是目录与交付的权威定义；本文件保留工程运行约束。旧工作区发现设计已退役。\n', s, count=1).replace('；`.agents/skills`仅为引用入口','；不维护项目发现入口').replace('均在此工作区内就地触发执行，保证开发环境的完全自包含与宿主解耦。','使用发布的Release；开发工程独立实现和测试技能功能。').replace('**严禁**将本项目的技能代码、配置或环境依赖复制到操作系统的全局目录','开发初始化不得将源码、私有配置或环境依赖复制到操作系统的全局目录').replace('python scripts/core/cli.py','python skill_bundle/runtime/cli.py'))
    edit('skill_bundle/references/execution-contract.md', lambda s: s.replace('默认集合父目录。','开发默认仓库根；Release默认操作系统用户数据目录下a_stock_agents，安装缓存不作为可写数据目录。').replace('项目发现入口仅引用skills目录；链接失败不复制。','AI工具使用Release；开发仓库不提供项目发现入口。Release不依赖链接，宿主注册需要的引用另行验收。'))
    edit('docs/specs/engineering/eng-skill-suite-portability-plan.md', lambda s: s.replace('Windows P0及项目引用验证通过；','旧Windows项目引用已退役；').replace('实现三系统引用式宿主接入及诊断','实现三个目标的Release格式适配及安装诊断').replace('快照不形成第二套有效运行目录','生成快照不作为第二套维护源码')+'\n## 2026-10-14 最新用途收敛\n\n现行目标仅为开发工程与技能Release交付集合。此前项目引用及双模式方案保留为历史，不作为验收要求。开发安装脚本不再挂载技能；接入工具拒绝开发源码；候选包派生release标识并使用独立用户数据根。原生宿主导入、发现及三系统实测仍未验证，不能由平台命名的ZIP推定通过。\n')


if __name__ == '__main__':
    main()
